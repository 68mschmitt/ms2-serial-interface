#!/usr/bin/env python3
"""
replay_ecu_protocol.py - Replay captured ECU data with full protocol emulation.

Creates a virtual serial port that speaks the Megasquirt newserial protocol.
TunerStudio (or any MS-compatible tool) can connect to this virtual port
and receive the captured data as if it were a live ECU.

Supports both simple commands (Q, A) and CAN-style commands (r table offset count).

Usage:
    # Basic replay (loops by default)
    python replay_ecu_protocol.py capture.bin

    # Custom port path
    python replay_ecu_protocol.py capture.bin --link /dev/pts/virtual_ecu

    # Single playthrough (no loop)
    python replay_ecu_protocol.py capture.bin --no-loop

    # Then connect TunerStudio to the virtual port shown

Protocol Tables (CAN commands):
    - Table 0x07 (7):  OUTPC realtime data (209 bytes)
    - Table 0x0e (14): Version info (60 bytes)
    - Table 0x0f (15): Signature query (20 bytes)
"""

from __future__ import annotations

import argparse
import binascii
import os
import pty
import select
import struct
import sys
import termios
import time
from dataclasses import dataclass
from pathlib import Path


# MS2 Protocol Table Numbers
TABLE_OUTPC = 0x07  # Realtime output channels (209 bytes)
TABLE_VERSION = 0x0E  # Version info (60 bytes)
TABLE_SIGNATURE = 0x0F  # Signature string (20 bytes)


def crc32_ms(data: bytes) -> int:
    """CRC32 as used by Megasquirt (standard CRC32)."""
    return binascii.crc32(data) & 0xFFFFFFFF


def build_response(flag: int, payload: bytes) -> bytes:
    """
    Build a newserial response packet.

    Format: [size:2][flag:1][payload:N][crc32:4]
    Size is big-endian and includes flag byte.
    CRC32 is over flag+payload.
    """
    data = bytes([flag]) + payload
    return struct.pack(">H", len(data)) + data + struct.pack(">I", crc32_ms(data))


def read_raw_bytes(fd: int, timeout: float = 0.1) -> bytes | None:
    """Read raw bytes from file descriptor without any framing."""
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None
    try:
        return os.read(fd, 1024)
    except OSError:
        return None


def read_framed_request(fd: int, remaining: bytes, timeout: float = 0.1) -> tuple[bytes | None, bytes]:
    """
    Read a newserial framed request from file descriptor.

    Args:
        fd: File descriptor to read from
        remaining: Leftover bytes from previous read
        timeout: Read timeout in seconds

    Returns:
        Tuple of (payload or None, remaining bytes)
    """
    buffer = remaining

    # Need at least 2 bytes for size header
    if len(buffer) < 2:
        ready, _, _ = select.select([fd], [], [], timeout)
        if ready:
            try:
                buffer += os.read(fd, 1024)
            except OSError:
                return None, buffer

    if len(buffer) < 2:
        return None, buffer

    size = struct.unpack(">H", buffer[:2])[0]

    if size == 0 or size > 1024:
        # Invalid size, discard this byte and try again
        return None, buffer[1:]

    # Need size + 2 (header) + 4 (crc) bytes total
    total_needed = 2 + size + 4

    # Read more if needed
    attempts = 0
    while len(buffer) < total_needed and attempts < 100:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if ready:
            try:
                chunk = os.read(fd, total_needed - len(buffer))
                if chunk:
                    buffer += chunk
            except OSError:
                break
        attempts += 1

    if len(buffer) < total_needed:
        return None, buffer

    # Extract and verify
    payload = buffer[2:2 + size]
    crc_bytes = buffer[2 + size:2 + size + 4]
    remaining_bytes = buffer[total_needed:]

    crc_rx = struct.unpack(">I", crc_bytes)[0]
    crc_calc = crc32_ms(payload)

    if crc_rx != crc_calc:
        # CRC mismatch, skip this packet
        return None, remaining_bytes

    return payload, remaining_bytes

@dataclass
class CaptureFrame:
    """Single captured OUTPC frame with timestamp."""

    timestamp_us: int
    outpc_data: bytes


def load_capture(capture_path: Path) -> tuple[str, int, list[CaptureFrame]]:
    """
    Load captured OUTPC frames from file.

    Returns:
        Tuple of (signature, block_size, frames)
    """
    frames: list[CaptureFrame] = []

    with open(capture_path, "rb") as f:
        magic = f.read(8)

        if magic == b"MS2CAP02":
            sig_len = struct.unpack("<I", f.read(4))[0]
            signature = f.read(sig_len).decode("utf-8", errors="replace")
        elif magic == b"MS2CAP01":
            _baud = struct.unpack("<I", f.read(4))[0]
            signature = "MS2Extra comms330NP"
        else:
            raise ValueError(f"Unknown capture format: {magic!r}")

        while True:
            header = f.read(10)
            if len(header) < 10:
                break

            timestamp_us, length = struct.unpack("<QH", header)
            outpc_data = f.read(length)
            if len(outpc_data) < length:
                break

            frames.append(CaptureFrame(timestamp_us, outpc_data))

    if not frames:
        raise ValueError("Capture file contains no frames")

    block_size = len(frames[0].outpc_data)
    return signature, block_size, frames


def format_duration(total_us: int) -> str:
    """Format microseconds as human-readable duration."""
    seconds = total_us / 1_000_000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def configure_pty_as_serial(fd: int) -> None:
    """
    Configure a PTY to behave like a raw serial port.
    """
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0  # iflag: no input processing
    attrs[1] = 0  # oflag: no output processing
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0  # lflag: raw mode
    attrs[6][termios.VMIN] = 1
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def parse_r_command(payload: bytes) -> tuple[int, int, int, int] | None:
    """
    Parse CAN-style 'r' read command.

    Format: r + canId(1) + table(1) + offset(2, big-endian) + count(2, big-endian)

    Returns: (can_id, table, offset, count) or None if invalid
    """
    if len(payload) < 7 or payload[0] != ord("r"):
        return None

    can_id = payload[1]
    table = payload[2]
    offset = struct.unpack(">H", payload[3:5])[0]
    count = struct.unpack(">H", payload[5:7])[0]

    return can_id, table, offset, count


def run_replay_server(
    capture_path: Path,
    link_path: str,
    speed: float = 1.0,
    loop: bool = True,
    debug: bool = False,
    signature_override: str | None = None,
) -> None:
    """
    Run ECU emulator serving captured data.
    """
    # Load capture
    print(f"Loading capture: {capture_path}")
    try:
        signature, block_size, frames = load_capture(capture_path)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error loading capture: {e}", file=sys.stderr)
        sys.exit(1)

    total_duration_us = frames[-1].timestamp_us - frames[0].timestamp_us

    # Override signature if requested
    if signature_override:
        signature = signature_override
        print(f"  Signature override: {signature}")

    # Prepare response data
    # Signature: padded/truncated to exactly 20 bytes (null-terminated)
    sig_bytes = signature.encode("utf-8")[:19] + b"\x00"
    sig_response = sig_bytes.ljust(20, b"\x00")

    # Version info: same signature, padded to 60 bytes
    version_response = sig_bytes.ljust(60, b"\x00")
    print(f"  Signature: {signature}")
    print(f"  Frames: {len(frames)}")
    print(f"  Block size: {block_size} bytes")
    print(f"  Duration: {format_duration(total_duration_us)}")

    # Create pseudo-terminal pair
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)

    # Configure as raw serial
    print(f"\nConfiguring PTY for serial emulation...")
    try:
        configure_pty_as_serial(master_fd)
        configure_pty_as_serial(slave_fd)
        print("  PTY configured in raw mode")
    except termios.error as e:
        print(f"  Warning: Could not configure PTY: {e}")

    # Create symlink
    link = Path(link_path)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(slave_path)

    print(f"\n{'=' * 60}")
    print("ECU Replay Server Running")
    print(f"{'=' * 60}")
    print(f"Virtual port: {link_path}")
    print(f"  -> {slave_path}")
    print(f"Speed: {speed}x | Loop: {loop}")
    print(f"\nSupported commands:")
    print(f"  F (unframed)        -> Protocol version '002'")
    print(f"  Q / r canId 0x0f ... -> Signature ({len(sig_response)} bytes)")
    print(f"  S / r canId 0x0e ... -> Version ({len(version_response)} bytes)")
    print(f"  A / r canId 0x07 ... -> OUTPC data ({block_size} bytes)")
    print(f"\nConnect TunerStudio to: {link_path}")
    print("Press Ctrl+C to stop\n")

    frame_index = 0
    request_count = 0
    outpc_request_count = 0
    start_time = time.time()
    loop_count = 0
    read_buffer = b""  # Buffer for handling partial reads

    try:
        while True:
            ready, _, _ = select.select([master_fd], [], [], 0.05)
            if not ready:
                continue

            # Debug mode: peek at raw bytes
            if debug:
                try:
                    peek = os.read(master_fd, 128)
                    if peek:
                        print(f"\n  [DEBUG] Raw: {peek.hex()}")
                    continue
                except OSError:
                    continue

            # Read raw bytes first
            try:
                raw_data = os.read(master_fd, 1024)
                if not raw_data:
                    continue
                read_buffer += raw_data
            except OSError:
                continue

            # Process buffer - check for unframed 'F' command first
            while read_buffer:
                # Check for unframed 'F' (protocol version query) - single byte 0x46
                if read_buffer[0:1] == b'F':
                    # Respond with unframed "002" (protocol version 2)
                    os.write(master_fd, b'002')
                    print("  [F] Protocol version query -> '002' (unframed)")
                    request_count += 1
                    read_buffer = read_buffer[1:]
                    continue

                # Try to parse as framed newserial request
                request, read_buffer = read_framed_request(master_fd, read_buffer, timeout=0.1)
                if request is None:
                    # Not enough data for a complete frame, wait for more
                    break

                request_count += 1
                response = None
                cmd_desc = ""

                # Handle simple commands (Q, A, S)
                if request == b"Q":
                    response = build_response(0x00, sig_response)
                    cmd_desc = f"[Q] Signature -> {signature}"
                    print(f"  {cmd_desc}")
                elif request == b"A":
                    frame = frames[frame_index]
                    response = build_response(0x01, frame.outpc_data)
                    outpc_request_count += 1
                    frame_index = (frame_index + 1) % len(frames)
                    if frame_index == 0 and loop:
                        loop_count += 1
                    cmd_desc = "[A] OUTPC data"

                elif request == b"S":
                    response = build_response(0x00, version_response)
                    cmd_desc = f"[S] Version -> {signature}"
                    print(f"  {cmd_desc}")

                # Handle CAN-style 'r' read commands
                elif request[0:1] == b"r":
                    parsed = parse_r_command(request)
                    if parsed:
                        can_id, table, offset, count = parsed

                        if table == TABLE_SIGNATURE:  # 0x0F - Signature
                            # Return requested bytes from signature
                            data = sig_response[offset : offset + count]
                            response = build_response(0x00, data)
                            cmd_desc = f"[r] Table 0x0F Signature ({count} bytes)"
                            print(f"  {cmd_desc}")
                            print(f"      Sending: {data.hex()}")
                            print(f"      As text: {data.rstrip(b'\x00').decode('utf-8', errors='replace')}")
                        elif table == TABLE_VERSION:  # 0x0E - Version info
                            data = version_response[offset : offset + count]
                            response = build_response(0x00, data)
                            cmd_desc = f"[r] Table 0x0E Version ({count} bytes)"
                            print(f"  {cmd_desc}")

                        elif table == TABLE_OUTPC:  # 0x07 - OUTPC
                            frame = frames[frame_index]
                            data = frame.outpc_data[offset : offset + count]
                            response = build_response(0x01, data)
                            outpc_request_count += 1
                            frame_index = (frame_index + 1) % len(frames)
                            if frame_index == 0 and loop:
                                loop_count += 1
                            cmd_desc = f"[r] Table 0x07 OUTPC ({count} bytes)"

                        elif table in (0x04, 0x05, 0x06, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D):  # Config pages
                            # Return zeros for configuration data (replay doesn't have tune data)
                            page_data = bytes(count)
                            response = build_response(0x00, page_data)
                            cmd_desc = f"[r] Table 0x{table:02X} Page data ({count} bytes) -> zeros"
                            if request_count <= 20:
                                print(f"  {cmd_desc}")

                        else:
                            # Unknown table - return zeros to avoid errors
                            page_data = bytes(count)
                            response = build_response(0x00, page_data)
                            cmd_desc = f"[r] Unknown table 0x{table:02X} ({count} bytes) -> zeros"
                            print(f"  {cmd_desc}")
                    else:
                        response = build_response(0x83, b"")
                        cmd_desc = f"[r] Invalid format: {request.hex()}"
                        print(f"  {cmd_desc}")

                else:
                    # Unknown command
                    response = build_response(0x83, b"")
                    cmd_desc = f"[?] Unknown: {request[:8].hex()}"
                    if request_count <= 10:
                        print(f"  {cmd_desc}")

                # Send response
                if response:
                    os.write(master_fd, response)

                # Progress display (for OUTPC requests)
                if outpc_request_count > 0 and outpc_request_count % 10 == 0:
                    elapsed = time.time() - start_time
                    pct = (frame_index / len(frames)) * 100
                    rate = outpc_request_count / elapsed if elapsed > 0 else 0
                    loop_info = f" L{loop_count}" if loop_count > 0 else ""
                    print(
                        f"\r  Frame {frame_index:5d}/{len(frames)} ({pct:5.1f}%){loop_info} | "
                        f"{rate:5.1f} Hz | Total: {request_count}  ",
                        end="",
                        flush=True,
                    )

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\nShutting down...")
        print(f"  Runtime: {elapsed:.1f}s")
        print(f"  Total requests: {request_count}")
        print(f"  OUTPC requests: {outpc_request_count}")
        if loop_count > 0:
            print(f"  Loops: {loop_count}")

    finally:
        if link.is_symlink():
            link.unlink()
        os.close(master_fd)
        os.close(slave_fd)
        print("Cleanup complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Replay captured ECU data - TunerStudio compatible",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s cold_start.bin
  %(prog)s cold_start.bin --link /tmp/virtual_ecu
  %(prog)s cold_start.bin --no-loop
  %(prog)s cold_start.bin --debug

Then connect TunerStudio to the virtual port.
        """,
    )
    parser.add_argument("capture", help="Capture file (.bin)")
    parser.add_argument(
        "--link",
        "-l",
        default="/tmp/ms2_replay",
        help="Virtual serial port path (default: /tmp/ms2_replay)",
    )
    parser.add_argument(
        "--speed",
        "-s",
        type=float,
        default=1.0,
        help="Playback speed multiplier (default: 1.0)",
    )
    parser.add_argument(
        "--no-loop",
        action="store_true",
        help="Stop at end instead of looping",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw received bytes (destructive - for debugging only)",
    )
    parser.add_argument(
        "--signature",
        help="Override signature string (must match TunerStudio INI)",
    )
    args = parser.parse_args()

    capture_path = Path(args.capture)
    if not capture_path.exists():
        print(f"Error: Capture file not found: {capture_path}", file=sys.stderr)
        sys.exit(1)

    run_replay_server(
        capture_path,
        args.link,
        args.speed,
        loop=not args.no_loop,
        debug=args.debug,
        signature_override=args.signature,
    )


if __name__ == "__main__":
    main()

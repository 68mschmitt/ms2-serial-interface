#!/usr/bin/env python3
"""
replay_ecu_protocol.py - Replay captured ECU data with full protocol emulation.

Creates a virtual serial port that speaks the Megasquirt newserial protocol.
TunerStudio (or any MS-compatible tool) can connect to this virtual port
and receive the captured data as if it were a live ECU.

Usage:
    # Basic replay (loops by default)
    python replay_ecu_protocol.py capture.bin

    # Custom port path
    python replay_ecu_protocol.py capture.bin --link /dev/pts/virtual_ecu

    # Single playthrough (no loop)
    python replay_ecu_protocol.py capture.bin --no-loop

    # Then connect TunerStudio to the virtual port shown

Protocol:
    - Responds to "Q" command with captured ECU signature
    - Responds to "A" command with next OUTPC frame from capture
    - Supports CAN-style "r" read commands
    - Properly frames all responses with length + CRC32
"""

from __future__ import annotations

import argparse
import binascii
import os
import pty
import select
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path


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


def read_request(fd: int, timeout: float = 0.1) -> bytes | None:
    """
    Read a newserial request from file descriptor.

    Returns the payload (without framing) or None on timeout/error.
    """
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None

    try:
        # Read size header (2 bytes, big-endian)
        size_bytes = os.read(fd, 2)
        if len(size_bytes) < 2:
            return None
        size = struct.unpack(">H", size_bytes)[0]

        if size == 0 or size > 1024:
            # Invalid size, drain buffer
            os.read(fd, 1024)
            return None

        # Read payload
        payload = b""
        while len(payload) < size:
            chunk = os.read(fd, size - len(payload))
            if not chunk:
                break
            payload += chunk

        if len(payload) < size:
            return None

        # Read and verify CRC (4 bytes, big-endian)
        crc_bytes = os.read(fd, 4)
        if len(crc_bytes) < 4:
            return None

        crc_rx = struct.unpack(">I", crc_bytes)[0]
        crc_calc = crc32_ms(payload)
        if crc_rx != crc_calc:
            return None

        return payload

    except OSError:
        return None


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

    Raises:
        ValueError: If file format is invalid
        FileNotFoundError: If file doesn't exist
    """
    frames: list[CaptureFrame] = []

    with open(capture_path, "rb") as f:
        magic = f.read(8)

        if magic == b"MS2CAP02":
            # Current format with signature
            sig_len = struct.unpack("<I", f.read(4))[0]
            signature = f.read(sig_len).decode("utf-8", errors="replace")
        elif magic == b"MS2CAP01":
            # Legacy format - read baud, use default signature
            _baud = struct.unpack("<I", f.read(4))[0]
            signature = "MS2Extra comms330NP"
        else:
            raise ValueError(f"Unknown capture format: {magic!r}")

        # Read all frames
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

    # Determine block size from first frame
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


def run_replay_server(
    capture_path: Path,
    link_path: str,
    speed: float = 1.0,
    loop: bool = True,
    timing_mode: bool = False,
) -> None:
    """
    Run ECU emulator serving captured data.

    Args:
        capture_path: Path to capture file
        link_path: Path for virtual serial port symlink
        speed: Playback speed multiplier (1.0 = realtime)
        loop: Whether to loop playback
        timing_mode: If True, respect original timing; if False, serve on-demand
    """
    # Load capture
    print(f"Loading capture: {capture_path}")
    try:
        signature, block_size, frames = load_capture(capture_path)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error loading capture: {e}", file=sys.stderr)
        sys.exit(1)

    total_duration_us = frames[-1].timestamp_us - frames[0].timestamp_us

    print(f"  Signature: {signature}")
    print(f"  Frames: {len(frames)}")
    print(f"  Block size: {block_size} bytes")
    print(f"  Duration: {format_duration(total_duration_us)}")

    # Create pseudo-terminal pair
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)

    # Create symlink for easy access
    link = Path(link_path)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(slave_path)

    print(f"\n{'=' * 60}")
    print("ECU Replay Server Running")
    print(f"{'=' * 60}")
    print(f"Virtual port: {link_path}")
    print(f"  -> {slave_path}")
    print(f"Speed: {speed}x")
    print(f"Loop: {loop}")
    print(f"\nConnect TunerStudio or ms2d to: {link_path}")
    print("Press Ctrl+C to stop\n")

    frame_index = 0
    request_count = 0
    a_request_count = 0
    start_time = time.time()
    loop_count = 0

    try:
        while True:
            # Wait for request from client (TunerStudio, ms2d, etc.)
            request = read_request(master_fd, timeout=0.05)

            if not request:
                continue

            request_count += 1
            cmd = chr(request[0]) if request else "?"

            if request == b"Q":
                # Signature query
                response = build_response(0x00, signature.encode("utf-8") + b"\x00")
                os.write(master_fd, response)
                print(f"  [Q] Signature query -> {signature}")

            elif request == b"A":
                # Realtime data request - serve next frame
                frame = frames[frame_index]
                response = build_response(0x01, frame.outpc_data)
                os.write(master_fd, response)

                a_request_count += 1

                # Advance frame index
                frame_index += 1
                if frame_index >= len(frames):
                    if loop:
                        frame_index = 0
                        loop_count += 1
                        print(f"\n  [LOOP {loop_count}] Restarting from frame 0")
                    else:
                        print(f"\n  [END] Capture playback complete")
                        break

                # Progress display
                elapsed = time.time() - start_time
                pct = (frame_index / len(frames)) * 100
                rate = a_request_count / elapsed if elapsed > 0 else 0
                print(
                    f"\r  Frame {frame_index:5d}/{len(frames)} ({pct:5.1f}%) | "
                    f"{rate:5.1f} Hz | Requests: {request_count}  ",
                    end="",
                    flush=True,
                )

            elif request[0:1] == b"r":
                # CAN-style read command
                # Format: r + canId (1) + table (1) + offset (2) + count (2)
                # For OUTPC reads (table 7), serve current frame
                if len(request) >= 6:
                    table = request[2] if len(request) > 2 else 0
                    if table == 7:  # OUTPC table
                        frame = frames[frame_index]
                        response = build_response(0x01, frame.outpc_data)
                        os.write(master_fd, response)
                    else:
                        # Unknown table - send empty response
                        response = build_response(0x00, b"")
                        os.write(master_fd, response)
                else:
                    response = build_response(0x83, b"")  # Error
                    os.write(master_fd, response)

            elif request == b"S":
                # Some tools send "S" for status/version
                response = build_response(0x00, signature.encode("utf-8") + b"\x00")
                os.write(master_fd, response)

            else:
                # Unknown command - log and send error
                if request_count <= 10 or request_count % 100 == 0:
                    hex_str = request[:16].hex()
                    if len(request) > 16:
                        hex_str += "..."
                    print(f"\n  [?] Unknown command: {hex_str}")
                response = build_response(0x83, b"")  # Unrecognized command
                os.write(master_fd, response)

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\nShutting down...")
        print(f"  Runtime: {elapsed:.1f}s")
        print(f"  Requests: {request_count}")
        print(f"  Frames served: {a_request_count}")
        if loop_count > 0:
            print(f"  Loops completed: {loop_count}")

    finally:
        # Cleanup
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
  # Basic replay (loops continuously)
  %(prog)s cold_start.bin

  # Custom virtual port path
  %(prog)s cold_start.bin --link /tmp/virtual_ecu

  # Single playthrough without looping
  %(prog)s cold_start.bin --no-loop

  # Faster playback for quick testing
  %(prog)s cold_start.bin --speed 2.0

Then connect TunerStudio:
  1. Project -> Project Properties -> Settings
  2. Set serial port to the virtual port path shown
  3. Click "Connect"
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
    )


if __name__ == "__main__":
    main()

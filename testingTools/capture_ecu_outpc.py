#!/usr/bin/env python3
"""
capture_ecu_outpc.py - Capture OUTPC blocks from ECU for replay.

Actively polls the ECU using the Megasquirt newserial protocol,
capturing raw OUTPC data blocks that can be replayed later.

Usage:
    # Capture 5 minutes of data
    python capture_ecu_outpc.py --port /dev/ttyUSB0 --duration 300 --output cold_start.bin

    # Capture at higher poll rate
    python capture_ecu_outpc.py --port /dev/ttyUSB0 --duration 60 --hz 50 --output high_rate.bin

File Format (MS2CAP02):
    8 bytes:  magic "MS2CAP02"
    4 bytes:  signature length (uint32 LE)
    N bytes:  signature string
    Then repeating frames:
        8 bytes:  timestamp_us (uint64 LE) - microseconds since capture start
        2 bytes:  outpc_length (uint16 LE)
        N bytes:  outpc_data
"""

from __future__ import annotations

import argparse
import binascii
import serial
import struct
import sys
import time
from pathlib import Path


def crc32_ms(data: bytes) -> int:
    """CRC32 as used by Megasquirt (standard CRC32)."""
    return binascii.crc32(data) & 0xFFFFFFFF


def build_request(payload: bytes) -> bytes:
    """Build newserial request packet."""
    return (
        struct.pack(">H", len(payload)) + payload + struct.pack(">I", crc32_ms(payload))
    )


def read_response(ser: serial.Serial, timeout: float = 1.0) -> tuple[int, bytes] | None:
    """
    Read newserial response from serial port.

    Returns:
        Tuple of (flag, payload) on success, None on failure.
        Flag 0x00 = success, 0x01 = realtime data, 0x8x = error
    """
    ser.timeout = timeout

    # Read size (2 bytes, big-endian)
    size_bytes = ser.read(2)
    if len(size_bytes) < 2:
        return None
    size = struct.unpack(">H", size_bytes)[0]

    # Read payload
    payload = ser.read(size)
    if len(payload) < size:
        return None

    # Read and verify CRC (4 bytes, big-endian)
    crc_bytes = ser.read(4)
    if len(crc_bytes) < 4:
        return None

    crc_rx = struct.unpack(">I", crc_bytes)[0]
    if crc_rx != crc32_ms(payload):
        return None

    # Return flag and data separately
    return payload[0], payload[1:]


def query_signature(ser: serial.Serial) -> str | None:
    """Query ECU signature string."""
    ser.write(build_request(b"Q"))
    resp = read_response(ser, timeout=2.0)
    if not resp:
        return None
    return resp[1].rstrip(b"\x00").decode("utf-8", errors="replace")


def capture_outpc(
    port: str,
    baud: int,
    output: Path,
    duration: float,
    poll_hz: float = 30,
) -> bool:
    """
    Capture OUTPC blocks by polling ECU.

    Args:
        port: Serial port path (e.g., /dev/ttyUSB0)
        baud: Baud rate (typically 115200)
        output: Output file path
        duration: Capture duration in seconds
        poll_hz: Polling rate in Hz

    Returns:
        True on success, False on failure.
    """
    try:
        ser = serial.Serial(port, baud, timeout=1.0)
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}", file=sys.stderr)
        return False

    # Query signature first
    print(f"Connecting to ECU on {port} @ {baud} baud...")
    signature = query_signature(ser)
    if not signature:
        print("Error: No response to signature query", file=sys.stderr)
        print("  - Check that ECU is powered on", file=sys.stderr)
        print("  - Check serial port and baud rate", file=sys.stderr)
        ser.close()
        return False

    print(f"ECU Signature: {signature}")

    # Open output file
    print(f"Output: {output}")
    print(f"Duration: {duration}s @ {poll_hz}Hz")
    print("Press Ctrl+C to stop early\n")

    frame_count = 0
    error_count = 0

    with open(output, "wb") as f:
        # Write header
        f.write(b"MS2CAP02")  # Magic + version
        sig_bytes = signature.encode("utf-8")
        f.write(struct.pack("<I", len(sig_bytes)))
        f.write(sig_bytes)

        start_time = time.time()
        poll_interval = 1.0 / poll_hz
        next_poll = start_time

        try:
            while (time.time() - start_time) < duration:
                now = time.time()

                # Wait for next poll time
                if now < next_poll:
                    time.sleep(min(0.001, next_poll - now))
                    continue

                # Schedule next poll
                next_poll += poll_interval
                # Don't let it fall too far behind
                if next_poll < now:
                    next_poll = now + poll_interval

                # Request OUTPC data ("A" command)
                ser.write(build_request(b"A"))
                resp = read_response(ser, timeout=0.5)

                if resp and resp[0] == 0x01:
                    outpc_data = resp[1]
                    timestamp_us = int((now - start_time) * 1_000_000)

                    # Write frame: timestamp (8) + length (2) + data
                    f.write(struct.pack("<QH", timestamp_us, len(outpc_data)))
                    f.write(outpc_data)
                    f.flush()

                    frame_count += 1
                    elapsed = now - start_time
                    rate = frame_count / elapsed if elapsed > 0 else 0
                    print(
                        f"\r  {elapsed:.1f}s | {frame_count} frames | "
                        f"{rate:.1f} Hz | {len(outpc_data)} bytes/frame  ",
                        end="",
                        flush=True,
                    )
                else:
                    error_count += 1
                    if error_count <= 5:
                        print(f"\n  [!] No response or error (count: {error_count})")
                    elif error_count == 6:
                        print("  [!] Suppressing further error messages...")

        except KeyboardInterrupt:
            print("\n\n  Capture interrupted by user")

    ser.close()

    # Summary
    actual_duration = time.time() - start_time
    print(f"\nCapture complete!")
    print(f"  Frames: {frame_count}")
    print(f"  Errors: {error_count}")
    print(f"  Duration: {actual_duration:.1f}s")
    print(f"  Avg Rate: {frame_count / actual_duration:.1f} Hz")
    print(f"  File: {output}")
    print(f"  Size: {output.stat().st_size} bytes")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Capture ECU OUTPC data for replay testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic capture
  %(prog)s --port /dev/ttyUSB0 --duration 60

  # High-rate capture for detailed analysis
  %(prog)s --port /dev/ttyUSB0 --duration 30 --hz 50 --output high_rate.bin

  # Long capture session
  %(prog)s --port /dev/ttyUSB0 --duration 600 --output drive_session.bin
        """,
    )
    parser.add_argument(
        "--port", "-p", required=True, help="Serial port (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--baud", "-b", type=int, default=115200, help="Baud rate (default: 115200)"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="ecu_capture.bin",
        help="Output file (default: ecu_capture.bin)",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=60,
        help="Capture duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--hz", type=float, default=30, help="Poll rate in Hz (default: 30)"
    )
    args = parser.parse_args()

    output_path = Path(args.output)

    # Warn if overwriting
    if output_path.exists():
        print(f"Warning: {output_path} already exists and will be overwritten")

    success = capture_outpc(
        args.port,
        args.baud,
        output_path,
        args.duration,
        args.hz,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

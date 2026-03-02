#!/usr/bin/env python3
"""
test_replay_connection.py - Test that the replay server is responding correctly.

Tests both simple commands (Q, A) and CAN-style commands (r table offset count).

Usage:
    # First start the replay server:
    python replay_ecu_protocol.py capture.bin --link /tmp/ms2_replay

    # Then in another terminal, test it:
    python test_replay_connection.py /tmp/ms2_replay
"""

from __future__ import annotations

import argparse
import binascii
import struct
import sys
import time

try:
    import serial
except ImportError:
    print("Error: pyserial required. Install with: pip install pyserial")
    sys.exit(1)


def crc32_ms(data: bytes) -> int:
    """CRC32 as used by Megasquirt."""
    return binascii.crc32(data) & 0xFFFFFFFF


def build_request(payload: bytes) -> bytes:
    """Build newserial request packet with framing."""
    return (
        struct.pack(">H", len(payload)) + payload + struct.pack(">I", crc32_ms(payload))
    )


def read_response(ser: serial.Serial, timeout: float = 2.0) -> tuple[int, bytes] | None:
    """Read newserial response with framing."""
    ser.timeout = timeout

    # Read size (2 bytes, big-endian)
    size_bytes = ser.read(2)
    if len(size_bytes) < 2:
        print(f"  Error: Only got {len(size_bytes)} bytes for size header")
        return None
    size = struct.unpack(">H", size_bytes)[0]
    print(f"  Response size: {size} bytes")

    # Read payload (flag + data)
    payload = ser.read(size)
    if len(payload) < size:
        print(f"  Error: Only got {len(payload)}/{size} payload bytes")
        return None

    # Read CRC
    crc_bytes = ser.read(4)
    if len(crc_bytes) < 4:
        print(f"  Error: Only got {len(crc_bytes)} CRC bytes")
        return None

    crc_rx = struct.unpack(">I", crc_bytes)[0]
    crc_calc = crc32_ms(payload)
    if crc_rx != crc_calc:
        print(f"  Error: CRC mismatch (rx={crc_rx:08x}, calc={crc_calc:08x})")
        return None

    # payload[0] is flag, payload[1:] is data
    return payload[0], payload[1:]


def test_simple_commands(ser: serial.Serial) -> bool:
    """Test simple Q and A commands."""
    print("=" * 50)
    print("Testing SIMPLE commands (Q, A)")
    print("=" * 50)
    print()
    success = True

    # Test Q command
    print("Test: Signature Query (Q command)")
    print("-" * 40)
    request = build_request(b"Q")
    print(f"  Sending: {request.hex()}")
    ser.write(request)

    response = read_response(ser)
    if response:
        flag, data = response
        print(f"  Flag: 0x{flag:02x}")
        signature = data.rstrip(b"\x00").decode("utf-8", errors="replace")
        print(f"  Signature: {signature}")
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL - No valid response")
        success = False
    print()

    # Test A command
    print("Test: Realtime Data (A command)")
    print("-" * 40)
    request = build_request(b"A")
    print(f"  Sending: {request.hex()}")
    ser.write(request)

    response = read_response(ser)
    if response:
        flag, data = response
        print(f"  Flag: 0x{flag:02x}")
        print(f"  Data length: {len(data)} bytes")
        if len(data) >= 8:
            rpm = struct.unpack_from("<H", data, 6)[0]
            print(f"  RPM (offset 6): {rpm}")
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL - No valid response")
        success = False
    print()

    return success


def test_can_commands(ser: serial.Serial) -> bool:
    """Test CAN-style 'r' commands (what TunerStudio actually uses)."""
    print("=" * 50)
    print("Testing CAN-STYLE commands (r table offset count)")
    print("=" * 50)
    print()
    success = True

    # Test signature query: r canId=0 table=0x0F offset=0 count=20
    print("Test: CAN Signature Query (r 0x00 0x0F 0x0000 0x0014)")
    print("-" * 40)
    # Build payload: 'r' + canId + table + offset(2, BE) + count(2, BE)
    payload = b"r" + bytes([0x00, 0x0F]) + struct.pack(">HH", 0, 20)
    request = build_request(payload)
    print(f"  Payload: {payload.hex()}")
    print(f"  Full request: {request.hex()}")
    ser.write(request)

    response = read_response(ser)
    if response:
        flag, data = response
        print(f"  Flag: 0x{flag:02x}")
        print(f"  Data length: {len(data)} bytes")
        signature = data.rstrip(b"\x00").decode("utf-8", errors="replace")
        print(f"  Signature: {signature}")
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL - No valid response")
        success = False
    print()

    # Test version info: r canId=0 table=0x0E offset=0 count=60
    print("Test: CAN Version Query (r 0x00 0x0E 0x0000 0x003C)")
    print("-" * 40)
    payload = b"r" + bytes([0x00, 0x0E]) + struct.pack(">HH", 0, 60)
    request = build_request(payload)
    print(f"  Payload: {payload.hex()}")
    print(f"  Full request: {request.hex()}")
    ser.write(request)

    response = read_response(ser)
    if response:
        flag, data = response
        print(f"  Flag: 0x{flag:02x}")
        print(f"  Data length: {len(data)} bytes")
        version = data.rstrip(b"\x00").decode("utf-8", errors="replace")
        print(f"  Version: {version}")
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL - No valid response")
        success = False
    print()

    # Test OUTPC data: r canId=0 table=0x07 offset=0 count=209
    print("Test: CAN OUTPC Query (r 0x00 0x07 0x0000 0x00D1)")
    print("-" * 40)
    payload = b"r" + bytes([0x00, 0x07]) + struct.pack(">HH", 0, 209)
    request = build_request(payload)
    print(f"  Payload: {payload.hex()}")
    print(f"  Full request: {request.hex()}")
    ser.write(request)

    response = read_response(ser)
    if response:
        flag, data = response
        print(f"  Flag: 0x{flag:02x}")
        print(f"  Data length: {len(data)} bytes")
        if len(data) >= 8:
            rpm = struct.unpack_from("<H", data, 6)[0]
            print(f"  RPM (offset 6): {rpm}")
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL - No valid response")
        success = False
    print()

    return success


def test_rapid_polling(ser: serial.Serial, use_can: bool = False) -> bool:
    """Test rapid polling."""
    cmd_type = "CAN (r 0x07)" if use_can else "Simple (A)"
    print(f"Test: Rapid Polling - {cmd_type} (10 requests)")
    print("-" * 40)

    if use_can:
        payload = b"r" + bytes([0x00, 0x07]) + struct.pack(">HH", 0, 209)
        request = build_request(payload)
    else:
        request = build_request(b"A")

    successful = 0
    start = time.time()

    for i in range(10):
        ser.write(request)
        response = read_response(ser, timeout=1.0)
        if response:
            successful += 1

    elapsed = time.time() - start
    rate = successful / elapsed if elapsed > 0 else 0
    print(f"  Successful: {successful}/10")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Rate: {rate:.1f} Hz")

    if successful == 10:
        print("  ✓ PASS")
        return True
    elif successful > 5:
        print("  ~ PARTIAL - Some requests failed")
        return True
    else:
        print("  ✗ FAIL - Too many failures")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test replay server connection (simple and CAN commands)",
    )
    parser.add_argument("port", help="Virtual serial port (e.g., /tmp/ms2_replay)")
    parser.add_argument("--baud", "-b", type=int, default=115200, help="Baud rate")
    parser.add_argument(
        "--can-only", action="store_true", help="Only test CAN commands"
    )
    parser.add_argument(
        "--simple-only", action="store_true", help="Only test simple commands"
    )
    args = parser.parse_args()

    print(f"Testing connection to: {args.port}")
    print(f"Baud rate: {args.baud}")
    print()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=2.0)
    except serial.SerialException as e:
        print(f"Error opening port: {e}")
        sys.exit(1)

    results = []

    if not args.can_only:
        results.append(("Simple commands", test_simple_commands(ser)))
        results.append(("Simple rapid poll", test_rapid_polling(ser, use_can=False)))

    if not args.simple_only:
        results.append(("CAN commands", test_can_commands(ser)))
        results.append(("CAN rapid poll", test_rapid_polling(ser, use_can=True)))

    ser.close()

    # Summary
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests PASSED - Ready for TunerStudio")
    else:
        print("Some tests FAILED - Check replay server")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

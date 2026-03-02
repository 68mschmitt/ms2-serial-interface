#!/usr/bin/env python3
"""
Test script to verify F command handling in the simulator/replay server.
Simulates TunerStudio's connection sequence.
"""

import binascii
import os
import struct
import sys
import time


def crc32_ms(data: bytes) -> int:
    """CRC32 as used by Megasquirt."""
    return binascii.crc32(data) & 0xFFFFFFFF


def build_request(payload: bytes) -> bytes:
    """Build a framed newserial request."""
    return (
        struct.pack(">H", len(payload)) + payload + struct.pack(">I", crc32_ms(payload))
    )


def read_response(fd: int, timeout: float = 1.0) -> bytes | None:
    """Read a framed response."""
    import select

    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None

    try:
        size_bytes = os.read(fd, 2)
        if len(size_bytes) < 2:
            return None
        size = struct.unpack(">H", size_bytes)[0]

        payload = b""
        while len(payload) < size:
            chunk = os.read(fd, size - len(payload))
            if not chunk:
                break
            payload += chunk

        crc_bytes = os.read(fd, 4)
        return payload
    except OSError:
        return None


def test_connection(port_path: str):
    """Test the TunerStudio connection sequence."""
    print(f"Testing connection to: {port_path}")

    if not os.path.exists(port_path):
        print(f"ERROR: Port {port_path} does not exist")
        return False

    # Use a regular file open for PTY
    fd = os.open(port_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

    # Clear non-blocking for simplicity
    import fcntl

    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

    success = True

    try:
        # Step 1: Send unframed 'F' command (protocol version query)
        print("\n1. Sending unframed 'F' command...")
        os.write(fd, b"F")
        time.sleep(0.2)

        import select

        ready, _, _ = select.select([fd], [], [], 1.0)
        if ready:
            response = os.read(fd, 10)
            print(f"   Response: {response!r}")
            if response == b"002":
                print("   ✓ SUCCESS: Protocol version query handled correctly!")
            else:
                print(f"   ✗ FAILED: Expected b'002', got {response!r}")
                success = False
        else:
            print("   ✗ FAILED: No response to F command (timeout)")
            success = False

        # Step 2: Send framed signature query (r command for table 0x0F)
        print(
            "\n2. Sending framed signature query (r canId=0 table=0x0F offset=0 count=20)..."
        )
        # r + canId(1) + table(1) + offset(2) + count(2)
        sig_request = b"r" + bytes([0, 0x0F]) + struct.pack(">HH", 0, 20)
        os.write(fd, build_request(sig_request))
        time.sleep(0.2)

        response = read_response(fd)
        if response:
            # Response is flag(1) + payload
            flag = response[0]
            payload = response[1:]
            sig_text = payload.rstrip(b"\x00").decode("utf-8", errors="replace")
            print(f"   Flag: 0x{flag:02X}")
            print(f"   Signature: '{sig_text}'")
            print(f"   ✓ SUCCESS: Signature query worked!")
        else:
            print("   ✗ FAILED: No response to signature query")
            success = False

        # Step 3: Send framed OUTPC query (r command for table 0x07)
        print(
            "\n3. Sending framed OUTPC query (r canId=0 table=0x07 offset=0 count=209)..."
        )
        outpc_request = b"r" + bytes([0, 0x07]) + struct.pack(">HH", 0, 209)
        os.write(fd, build_request(outpc_request))
        time.sleep(0.2)

        response = read_response(fd)
        if response:
            flag = response[0]
            payload = response[1:]
            print(f"   Flag: 0x{flag:02X}")
            print(f"   OUTPC data: {len(payload)} bytes")
            if len(payload) >= 4:
                # Try to decode some known fields
                rpm_raw = (
                    struct.unpack("<H", payload[6:8])[0] if len(payload) > 8 else 0
                )
                print(f"   Sample: RPM raw value = {rpm_raw}")
            print(f"   ✓ SUCCESS: OUTPC query worked!")
        else:
            print("   ✗ FAILED: No response to OUTPC query")
            success = False

    finally:
        os.close(fd)

    print("\n" + "=" * 50)
    if success:
        print("ALL TESTS PASSED - TunerStudio should be able to connect!")
    else:
        print("SOME TESTS FAILED - Check the output above")

    return success


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ms2_ecu_sim"
    sys.exit(0 if test_connection(port) else 1)

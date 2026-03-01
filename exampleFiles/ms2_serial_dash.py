#!/usr/bin/env python3
"""
ms2pnp_dashboard_fixed.py

Fixes based on your captures:
- outpc multi-byte fields are little-endian
- battery appears at offset 28 (not 26)
- afr1 appears at offset 30 (not 28)
- TPS can go slightly negative; clamp to 0..100 like TS display
"""

from __future__ import annotations
import argparse, binascii, struct, time, sys
import serial


def crc32_u32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def read_exact(ser: serial.Serial, n: int, timeout_s: float) -> bytes:
    buf = bytearray()
    t0 = time.time()
    while len(buf) < n:
        if time.time() - t0 > timeout_s:
            raise TimeoutError(f"Timed out reading {n} bytes (got {len(buf)})")
        chunk = ser.read(n - len(buf))
        if chunk:
            buf.extend(chunk)
    return bytes(buf)


def send_newserial(ser: serial.Serial, payload: bytes, timeout_s: float) -> bytes:
    pkt = struct.pack(">H", len(payload)) + payload + struct.pack(">L", crc32_u32(payload))
    ser.write(pkt)
    ser.flush()

    hdr = read_exact(ser, 2, timeout_s)
    (length,) = struct.unpack(">H", hdr)
    data = read_exact(ser, length, timeout_s)
    crc = read_exact(ser, 4, timeout_s)
    (crc_rx,) = struct.unpack(">L", crc)

    if crc_rx != crc32_u32(data):
        raise ValueError("CRC mismatch")

    return data


def u16le(b: bytes, off: int) -> int:
    return struct.unpack_from("<H", b, off)[0]


def s16le(b: bytes, off: int) -> int:
    return struct.unpack_from("<h", b, off)[0]


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def decode(outpc: bytes) -> dict:
    # Seconds appears big-endian in your capture (0x0100 -> 256)
    seconds = struct.unpack_from(">H", outpc, 0)[0]

    rpm = u16le(outpc, 6)
    advance = s16le(outpc, 8) * 0.1
    map_kpa = s16le(outpc, 18) * 0.1

    # Fahrenheit branch (matches your real-looking temps)
    mat_f = s16le(outpc, 20) * 0.1
    clt_f = s16le(outpc, 22) * 0.1

    # TPS looks right when pressed but slightly negative at rest -> clamp like TS
    tps_pct = s16le(outpc, 24) * 0.1
    tps_pct = clamp(tps_pct, 0.0, 100.0)

    # SHIFTED REGION (based on your raw bytes):
    # battery at 28-29, afr1 at 30-31
    batt_v = s16le(outpc, 28) * 0.1
    afr1 = s16le(outpc, 30) * 0.1

    return {
        "seconds": seconds,
        "rpm": rpm,
        "advance": advance,
        "map": map_kpa,
        "tps": tps_pct,
        "clt_f": clt_f,
        "mat_f": mat_f,
        "batt": batt_v,
        "afr1": afr1,
        "len": len(outpc),
    }


def print_dashboard(d: dict, warn: str | None = None):
    sys.stdout.write("\033[H")
    sys.stdout.write(
f"""
================ MS2PNP LIVE DATA =================

RPM:        {d['rpm']:6d}
Advance:    {d['advance']:6.1f} deg
MAP:        {d['map']:6.1f} kPa
TPS:        {d['tps']:6.1f} %

Coolant:    {d['clt_f']:6.1f} F
MAT:        {d['mat_f']:6.1f} F

Battery:    {d['batt']:6.2f} V
AFR1:       {d['afr1']:6.2f}

ECU Sec:    {d['seconds']:6d}
Payload:    {d['len']} bytes

Status:     {warn or "OK"}
====================================================
"""
    )
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--hz", type=float, default=15)
    ap.add_argument("--timeout-ms", type=int, default=300)
    ap.add_argument("--expect-len", type=int, default=210)
    args = ap.parse_args()

    timeout_s = args.timeout_ms / 1000.0
    delay = 1.0 / max(args.hz, 0.1)

    with serial.Serial(args.port, args.baud, timeout=timeout_s, write_timeout=timeout_s) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        sys.stdout.write("\033[2J")  # clear screen once
        sys.stdout.flush()

        q = send_newserial(ser, b"Q", 1.0)
        print(f"# Connected: {q[:80].decode(errors='replace')}", file=sys.stderr)

        warn = None
        while True:
            try:
                outpc = send_newserial(ser, b"A", timeout_s)
                if len(outpc) != args.expect_len:
                    warn = f"A len {len(outpc)} (expected {args.expect_len})"
                else:
                    warn = None
                d = decode(outpc)
                print_dashboard(d, warn=warn)
            except Exception as e:
                print_dashboard(
                    {"seconds": 0, "rpm": 0, "advance": 0.0, "map": 0.0, "tps": 0.0,
                     "clt_f": 0.0, "mat_f": 0.0, "batt": 0.0, "afr1": 0.0, "len": 0},
                    warn=f"ERROR: {e}"
                )
            time.sleep(delay)


if __name__ == "__main__":
    main()

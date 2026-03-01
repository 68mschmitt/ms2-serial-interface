#!/usr/bin/env python3
"""
inspect_capture.py - Inspect and analyze captured ECU data files.

Useful for verifying capture integrity, viewing statistics,
and extracting specific frames for debugging.

Usage:
    # Show capture info and statistics
    python inspect_capture.py capture.bin

    # Dump specific frames
    python inspect_capture.py capture.bin --dump 0-10

    # Export to CSV for analysis
    python inspect_capture.py capture.bin --export data.csv --ini ../cfg.ini
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FieldDef:
    """Field definition from INI file."""

    name: str
    data_type: str
    offset: int
    units: str
    scale: float
    translate: float

    @property
    def size(self) -> int:
        return {"U08": 1, "S08": 1, "U16": 2, "S16": 2, "U32": 4, "S32": 4}.get(
            self.data_type, 2
        )

    @property
    def struct_format(self) -> str:
        formats = {
            "U08": "<B",
            "S08": "<b",
            "U16": "<H",
            "S16": "<h",
            "U32": "<I",
            "S32": "<i",
        }
        return formats.get(self.data_type, "<H")


@dataclass
class CaptureFrame:
    """Single captured OUTPC frame."""

    timestamp_us: int
    outpc_data: bytes


def load_capture(capture_path: Path) -> tuple[str, list[CaptureFrame]]:
    """Load capture file and return (signature, frames)."""
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

    return signature, frames


def parse_ini_fields(ini_path: Path) -> dict[str, FieldDef]:
    """Parse OutputChannels section from INI file."""
    content = ini_path.read_text(encoding="utf-8", errors="replace")
    # Strip hash-line prefixes if present
    content = re.sub(r"^#[A-Z]{2}\|", "", content, flags=re.MULTILINE)

    fields: dict[str, FieldDef] = {}
    in_output_channels = False

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue

        if line.startswith("["):
            in_output_channels = line.strip("[]") == "OutputChannels"
            continue

        if not in_output_channels:
            continue

        if "=" not in line or "{" in line:
            continue

        match = re.match(r"(\w+)\s*=\s*(.+)", line)
        if not match:
            continue

        name = match.group(1)
        parts = [p.strip() for p in match.group(2).split(",")]

        if len(parts) < 3:
            continue

        field_type = parts[0].lower()
        if field_type not in ("scalar", "bits"):
            continue

        data_type = parts[1].upper()
        try:
            offset = int(parts[2])
        except ValueError:
            continue

        if field_type == "scalar":
            units = parts[3].strip('"') if len(parts) > 3 else ""
            try:
                scale = float(parts[4]) if len(parts) > 4 else 1.0
                translate = float(parts[5]) if len(parts) > 5 else 0.0
            except ValueError:
                scale, translate = 1.0, 0.0
            fields[name] = FieldDef(name, data_type, offset, units, scale, translate)

    return fields


def decode_field(data: bytes, field: FieldDef) -> float:
    """Decode a field value from OUTPC data."""
    if field.offset + field.size > len(data):
        return 0.0
    raw = struct.unpack_from(field.struct_format, data, field.offset)[0]
    return (raw + field.translate) * field.scale


def format_duration(us: int) -> str:
    """Format microseconds as readable duration."""
    seconds = us / 1_000_000
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.1f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m {secs:.0f}s"


def show_info(capture_path: Path) -> None:
    """Display capture file information."""
    file_size = capture_path.stat().st_size
    signature, frames = load_capture(capture_path)

    if not frames:
        print("Capture contains no frames")
        return

    duration_us = frames[-1].timestamp_us - frames[0].timestamp_us
    block_size = len(frames[0].outpc_data)
    avg_interval = duration_us / (len(frames) - 1) if len(frames) > 1 else 0
    avg_rate = 1_000_000 / avg_interval if avg_interval > 0 else 0

    # Check for timing anomalies
    intervals = []
    for i in range(1, len(frames)):
        intervals.append(frames[i].timestamp_us - frames[i - 1].timestamp_us)

    min_interval = min(intervals) if intervals else 0
    max_interval = max(intervals) if intervals else 0

    print(f"Capture File: {capture_path}")
    print(f"  File size: {file_size:,} bytes")
    print(f"  Signature: {signature}")
    print()
    print(f"Frames: {len(frames)}")
    print(f"  Block size: {block_size} bytes")
    print(f"  Duration: {format_duration(duration_us)}")
    print(f"  Average rate: {avg_rate:.1f} Hz")
    print()
    print("Timing:")
    print(f"  Avg interval: {avg_interval / 1000:.2f} ms")
    print(f"  Min interval: {min_interval / 1000:.2f} ms")
    print(f"  Max interval: {max_interval / 1000:.2f} ms")

    # Flag potential issues
    if max_interval > avg_interval * 3:
        print(f"  ⚠ Warning: Large gap detected ({max_interval / 1000:.1f} ms)")


def dump_frames(
    capture_path: Path, frame_range: str, ini_path: Path | None = None
) -> None:
    """Dump specific frames from capture."""
    signature, frames = load_capture(capture_path)

    # Parse range (e.g., "0-10", "5", "100-")
    if "-" in frame_range:
        parts = frame_range.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else len(frames)
    else:
        start = int(frame_range)
        end = start + 1

    start = max(0, start)
    end = min(len(frames), end)

    # Load field definitions if INI provided
    fields: dict[str, FieldDef] = {}
    if ini_path:
        fields = parse_ini_fields(ini_path)

    # Key fields to display
    key_fields = ["rpm", "map", "tps", "afr1", "coolant", "batteryVoltage", "advance"]
    display_fields = [f for f in key_fields if f in fields]

    print(f"Frames {start} to {end - 1}:")
    print()

    for i in range(start, end):
        frame = frames[i]
        time_sec = frame.timestamp_us / 1_000_000

        print(f"Frame {i}: t={time_sec:.3f}s, {len(frame.outpc_data)} bytes")

        if display_fields:
            values = []
            for fname in display_fields:
                val = decode_field(frame.outpc_data, fields[fname])
                unit = fields[fname].units
                values.append(f"{fname}={val:.1f}{unit}")
            print(f"  {', '.join(values)}")
        else:
            # Show hex dump
            hex_str = frame.outpc_data[:32].hex()
            print(f"  {hex_str}...")

        print()


def export_csv(capture_path: Path, csv_path: Path, ini_path: Path) -> None:
    """Export capture to CSV file."""
    signature, frames = load_capture(capture_path)
    fields = parse_ini_fields(ini_path)

    if not fields:
        print("Error: No fields parsed from INI file", file=sys.stderr)
        sys.exit(1)

    # Sort fields by offset for consistent column order
    sorted_fields = sorted(fields.values(), key=lambda f: f.offset)

    print(f"Exporting {len(frames)} frames with {len(sorted_fields)} fields...")

    with open(csv_path, "w") as f:
        # Header
        headers = ["timestamp_s"] + [field.name for field in sorted_fields]
        f.write(",".join(headers) + "\n")

        # Data
        for frame in frames:
            time_sec = frame.timestamp_us / 1_000_000
            values = [f"{time_sec:.6f}"]
            for field in sorted_fields:
                val = decode_field(frame.outpc_data, field)
                values.append(f"{val:.4f}")
            f.write(",".join(values) + "\n")

    print(f"Exported to: {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect and analyze captured ECU data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("capture", help="Capture file (.bin)")
    parser.add_argument(
        "--dump", "-d", metavar="RANGE", help="Dump frames (e.g., '0-10', '5', '100-')"
    )
    parser.add_argument("--export", "-e", metavar="CSV", help="Export to CSV file")
    parser.add_argument(
        "--ini", "-i", metavar="PATH", help="INI file for field decoding"
    )
    args = parser.parse_args()

    capture_path = Path(args.capture)
    if not capture_path.exists():
        print(f"Error: File not found: {capture_path}", file=sys.stderr)
        sys.exit(1)

    ini_path = Path(args.ini) if args.ini else None

    if args.export:
        if not ini_path:
            print("Error: --ini required for CSV export", file=sys.stderr)
            sys.exit(1)
        export_csv(capture_path, Path(args.export), ini_path)
    elif args.dump:
        dump_frames(capture_path, args.dump, ini_path)
    else:
        show_info(capture_path)


if __name__ == "__main__":
    main()

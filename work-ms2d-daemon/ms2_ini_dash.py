#!/usr/bin/env python3
"""
ms2_ini_dash.py

A Megasquirt 2 dashboard that parses the TunerStudio INI file to determine
the correct OutputChannels structure for decoding realtime data.

Usage:
    python ms2_ini_dash.py --port /dev/ttyUSB0 --ini cfg.ini
"""

from __future__ import annotations
import argparse
import binascii
import re
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import serial


# =============================================================================
# INI Parsing
# =============================================================================


@dataclass
class FieldDef:
    """Definition of a single output channel field."""

    name: str
    field_type: str  # "scalar" or "bits"
    data_type: str  # U08, S08, U16, S16, U32, S32
    offset: int
    units: str
    scale: float
    translate: float
    bit_range: tuple[int, int] | None = None  # For bits fields: (low_bit, high_bit)

    @property
    def size(self) -> int:
        """Size in bytes for this data type."""
        return {
            "U08": 1,
            "S08": 1,
            "U16": 2,
            "S16": 2,
            "U32": 4,
            "S32": 4,
        }.get(self.data_type, 2)

    @property
    def signed(self) -> bool:
        return self.data_type.startswith("S")

    @property
    def struct_format(self) -> str:
        """Return struct format character for this type (little-endian)."""
        formats = {
            "U08": "B",
            "S08": "b",
            "U16": "H",
            "S16": "h",
            "U32": "I",
            "S32": "i",
        }
        return "<" + formats.get(self.data_type, "H")


def parse_ini_output_channels(ini_path: Path) -> tuple[dict[str, FieldDef], int]:
    """
    Parse the [OutputChannels] section from a TunerStudio INI file.

    Returns:
        Tuple of (field_definitions dict, ochBlockSize)
    """
    content = ini_path.read_text(encoding="utf-8", errors="replace")

    # Remove the #XX| line prefixes that appear in this INI format
    content = re.sub(r"^#[A-Z]{2}\|", "", content, flags=re.MULTILINE)

    fields: dict[str, FieldDef] = {}
    och_block_size = 209  # Default
    in_output_channels = False

    # Track conditional compilation state
    condition_stack: list[bool] = []  # True = active, False = skip

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith(";"):
            continue

        # Handle conditional compilation
        if line.startswith("#if "):
            # For simplicity, we'll assume FAHRENHEIT (not CELSIUS) and not CAN_COMMANDS
            condition = line[4:].strip()
            if condition == "CELSIUS":
                condition_stack.append(False)
            elif condition == "CAN_COMMANDS":
                condition_stack.append(False)
            else:
                condition_stack.append(True)
            continue
        elif line == "#else":
            if condition_stack:
                condition_stack[-1] = not condition_stack[-1]
            continue
        elif line == "#endif":
            if condition_stack:
                condition_stack.pop()
            continue

        # Skip if we're in an inactive conditional block
        if condition_stack and not all(condition_stack):
            continue

        # Section headers
        if line.startswith("["):
            section = line.strip("[]")
            in_output_channels = section == "OutputChannels"
            continue

        if not in_output_channels:
            continue

        # Parse ochBlockSize
        if "ochBlockSize" in line and "=" in line:
            match = re.search(r"ochBlockSize\s*=\s*(\d+)", line)
            if match:
                och_block_size = int(match.group(1))
            continue

        # Skip calculated fields (contain curly braces)
        if "{" in line:
            continue

        # Skip command definitions
        if "ochGetCommand" in line:
            continue

        # Parse field definitions
        if "=" in line:
            field = parse_field_line(line)
            if field:
                fields[field.name] = field

    return fields, och_block_size


def parse_field_line(line: str) -> FieldDef | None:
    """Parse a single field definition line."""
    # Format: name = type, datatype, offset, "units", scale, translate
    # Or:     name = bits, datatype, offset, [low:high], "label0", "label1", ...

    match = re.match(r"(\w+)\s*=\s*(.+)", line)
    if not match:
        return None

    name = match.group(1)
    rest = match.group(2).strip()

    # Split by comma, but respect quoted strings
    parts = split_respecting_quotes(rest)
    if len(parts) < 3:
        return None

    field_type = parts[0].strip().lower()
    data_type = parts[1].strip().upper()

    # Parse offset
    try:
        offset = int(parts[2].strip())
    except ValueError:
        return None

    if field_type == "scalar":
        # scalar, TYPE, OFFSET, "units", scale, translate
        units = parts[3].strip().strip('"') if len(parts) > 3 else ""

        # Parse scale (might be an expression)
        scale = 1.0
        if len(parts) > 4:
            scale = parse_numeric_or_expr(parts[4].strip())

        # Parse translate
        translate = 0.0
        if len(parts) > 5:
            translate = parse_numeric_or_expr(parts[5].strip())

        return FieldDef(
            name=name,
            field_type="scalar",
            data_type=data_type,
            offset=offset,
            units=units,
            scale=scale,
            translate=translate,
        )

    elif field_type == "bits":
        # bits, TYPE, OFFSET, [low:high], "label0", ...
        bit_range = None
        if len(parts) > 3:
            bit_match = re.search(r"\[(\d+):(\d+)\]", parts[3])
            if bit_match:
                bit_range = (int(bit_match.group(1)), int(bit_match.group(2)))

        return FieldDef(
            name=name,
            field_type="bits",
            data_type=data_type,
            offset=offset,
            units="",
            scale=1.0,
            translate=0.0,
            bit_range=bit_range,
        )

    return None


def split_respecting_quotes(s: str) -> list[str]:
    """Split string by comma, but don't split inside quoted strings."""
    parts = []
    current = []
    in_quote = False
    quote_char = None

    for char in s:
        if char in ('"', "'") and not in_quote:
            in_quote = True
            quote_char = char
            current.append(char)
        elif char == quote_char and in_quote:
            in_quote = False
            quote_char = None
            current.append(char)
        elif char == "," and not in_quote:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))

    return parts


def parse_numeric_or_expr(s: str) -> float:
    """Parse a numeric value or simple expression."""
    s = s.strip()

    # Direct numeric
    try:
        return float(s)
    except ValueError:
        pass

    # Handle expressions like { 0.010 * (maf_range + 1) }
    # For now, just try to extract a simple number
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass

    return 1.0


# =============================================================================
# Serial Communication (Megasquirt "newserial" protocol)
# =============================================================================


def crc32_ms(data: bytes) -> int:
    """Calculate CRC32 as used by Megasquirt."""
    return binascii.crc32(data) & 0xFFFFFFFF


def read_exact(ser: serial.Serial, n: int, timeout_s: float) -> bytes:
    """Read exactly n bytes from serial port with timeout."""
    buf = bytearray()
    t0 = time.time()
    while len(buf) < n:
        if time.time() - t0 > timeout_s:
            raise TimeoutError(f"Timeout reading {n} bytes (got {len(buf)})")
        chunk = ser.read(n - len(buf))
        if chunk:
            buf.extend(chunk)
    return bytes(buf)


def send_command(ser: serial.Serial, payload: bytes, timeout_s: float) -> bytes:
    """
    Send a command using the Megasquirt newserial protocol.

    Request:  [2-byte size BE] [payload] [4-byte CRC32 BE]
    Response: [2-byte size BE] [payload with flag byte] [4-byte CRC32 BE]
    """
    # Build and send request
    pkt = (
        struct.pack(">H", len(payload)) + payload + struct.pack(">I", crc32_ms(payload))
    )
    ser.write(pkt)
    ser.flush()

    # Read response header
    hdr = read_exact(ser, 2, timeout_s)
    length = struct.unpack(">H", hdr)[0]

    # Read response payload and CRC
    data = read_exact(ser, length, timeout_s)
    crc_bytes = read_exact(ser, 4, timeout_s)
    crc_rx = struct.unpack(">I", crc_bytes)[0]

    # Verify CRC
    if crc_rx != crc32_ms(data):
        raise ValueError(
            f"CRC mismatch: expected {crc32_ms(data):08x}, got {crc_rx:08x}"
        )

    return data


# =============================================================================
# Data Decoding
# =============================================================================


def decode_field(data: bytes, field: FieldDef) -> float | int:
    """Decode a single field from the data buffer."""
    if field.offset + field.size > len(data):
        return 0

    # Unpack raw value
    try:
        raw_value = struct.unpack_from(field.struct_format, data, field.offset)[0]
    except struct.error:
        return 0

    # Handle bits fields
    if field.field_type == "bits" and field.bit_range:
        low, high = field.bit_range
        mask = (1 << (high - low + 1)) - 1
        raw_value = (raw_value >> low) & mask
        return raw_value

    # Apply scale and translate: userValue = (msValue + translate) * scale
    return (raw_value + field.translate) * field.scale


def decode_outpc(data: bytes, fields: dict[str, FieldDef]) -> dict[str, Any]:
    """Decode all fields from outpc data."""
    result = {}
    for name, field in fields.items():
        result[name] = decode_field(data, field)
    return result


# =============================================================================
# Dashboard Display
# =============================================================================

# Key fields to display (in order), with formatting
DASHBOARD_FIELDS = [
    ("rpm", "RPM", "{:6.0f}", ""),
    ("advance", "Advance", "{:6.1f}", "deg"),
    ("map", "MAP", "{:6.1f}", "kPa"),
    ("tps", "TPS", "{:6.1f}", "%"),
    ("coolant", "Coolant", "{:6.1f}", ""),  # Units from INI
    ("mat", "IAT", "{:6.1f}", ""),
    ("batteryVoltage", "Battery", "{:6.2f}", "V"),
    ("afr1", "AFR1", "{:6.2f}", ""),
    ("afr2", "AFR2", "{:6.2f}", ""),
    ("pulseWidth1", "PW1", "{:6.3f}", "ms"),
    ("dwell", "Dwell", "{:6.2f}", "ms"),
    ("veCurr1", "VE", "{:6.1f}", "%"),
    ("egoCorrection1", "EGO Corr", "{:6.1f}", "%"),
    ("accelEnrich", "Accel Enr", "{:6.2f}", "ms"),
    ("warmupEnrich", "Warmup", "{:6.0f}", "%"),
    ("baroCorrection", "Baro Corr", "{:6.1f}", "%"),
    ("gammaEnrich", "Gamma", "{:6.0f}", "%"),
    ("seconds", "ECU Time", "{:6.0f}", "s"),
]


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, value))


def print_dashboard(
    decoded: dict[str, Any],
    fields: dict[str, FieldDef],
    block_size: int,
    actual_size: int,
    warn: str | None = None,
):
    """Print the dashboard to terminal."""
    # Move cursor to home position
    sys.stdout.write("\033[H")

    lines = [
        "",
        "================== MS2 LIVE DATA ==================",
        "",
    ]

    for field_name, display_name, fmt, default_units in DASHBOARD_FIELDS:
        if field_name in decoded:
            value = decoded[field_name]

            # Get units from INI if available
            units = default_units
            if field_name in fields and fields[field_name].units:
                units = fields[field_name].units

            # Special handling for TPS (clamp like TunerStudio)
            if field_name == "tps":
                value = clamp(value, 0.0, 100.0)

            try:
                formatted = fmt.format(value)
            except (ValueError, TypeError):
                formatted = f"{value:>6}"

            lines.append(f"  {display_name:<12} {formatted} {units}")

    lines.extend(
        [
            "",
            f"  {'Payload':<12} {actual_size} bytes (expected {block_size})",
            f"  {'Status':<12} {warn or 'OK'}",
            "",
            "===================================================",
            "",
            "  Press Ctrl+C to exit",
            "",
        ]
    )

    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Megasquirt 2 dashboard with INI-based decoding"
    )
    parser.add_argument(
        "--port", required=True, help="Serial port (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument("--ini", required=True, help="Path to TunerStudio INI file")
    parser.add_argument(
        "--baud", type=int, default=115200, help="Baud rate (default: 115200)"
    )
    parser.add_argument(
        "--hz", type=float, default=10, help="Update rate in Hz (default: 10)"
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=500,
        help="Serial timeout in ms (default: 500)",
    )
    parser.add_argument(
        "--list-fields", action="store_true", help="List all parsed fields and exit"
    )
    args = parser.parse_args()

    ini_path = Path(args.ini)
    if not ini_path.exists():
        print(f"Error: INI file not found: {ini_path}", file=sys.stderr)
        sys.exit(1)

    # Parse INI file
    print(f"Parsing INI file: {ini_path}", file=sys.stderr)
    fields, block_size = parse_ini_output_channels(ini_path)
    print(
        f"Found {len(fields)} output channel fields, block size: {block_size}",
        file=sys.stderr,
    )

    if args.list_fields:
        print("\nParsed OutputChannel fields:")
        print("-" * 80)
        for name, field in sorted(fields.items(), key=lambda x: x[1].offset):
            print(
                f"  {field.offset:3d}  {name:<20} {field.data_type:<4} "
                f"scale={field.scale:<10.6f} units={field.units}"
            )
        sys.exit(0)

    timeout_s = args.timeout_ms / 1000.0
    delay = 1.0 / max(args.hz, 0.1)

    # Connect to ECU
    print(f"Connecting to {args.port} at {args.baud} baud...", file=sys.stderr)

    with serial.Serial(
        args.port, args.baud, timeout=timeout_s, write_timeout=timeout_s
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Clear screen
        sys.stdout.write("\033[2J")
        sys.stdout.flush()

        # Send Q command to get ECU signature
        try:
            sig = send_command(ser, b"Q", 2.0)
            # Skip first byte (flag byte in response)
            sig_str = sig[1:].decode(errors="replace").rstrip("\x00")
            print(f"Connected: {sig_str}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not read ECU signature: {e}", file=sys.stderr)

        time.sleep(0.5)

        # Main loop
        warn = None
        while True:
            try:
                # Request realtime data
                response = send_command(ser, b"A", timeout_s)

                # Response includes a flag byte at the start
                # Flag 0x01 = realtime data
                if len(response) > 0:
                    flag = response[0]
                    outpc = response[1:]  # Skip flag byte
                else:
                    outpc = response

                # Check size
                if len(outpc) != block_size:
                    warn = f"Size mismatch: got {len(outpc)}, expected {block_size}"
                else:
                    warn = None

                # Decode and display
                decoded = decode_outpc(outpc, fields)
                print_dashboard(decoded, fields, block_size, len(outpc), warn)

            except TimeoutError as e:
                print_dashboard({}, fields, block_size, 0, f"TIMEOUT: {e}")
            except ValueError as e:
                print_dashboard({}, fields, block_size, 0, f"ERROR: {e}")
            except Exception as e:
                print_dashboard({}, fields, block_size, 0, f"ERROR: {e}")

            time.sleep(delay)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Clear screen and show exit message
        sys.stdout.write("\033[2J\033[H")
        print("Dashboard stopped.")
        sys.exit(0)

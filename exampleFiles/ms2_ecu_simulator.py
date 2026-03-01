#!/usr/bin/env python3
"""
ms2_ecu_simulator.py

Simulates a Megasquirt 2 ECU for testing the dashboard.
Creates a virtual serial port pair and responds to the newserial protocol.

Usage:
    # Terminal 1: Start simulator
    python ms2_ecu_simulator.py --ini cfg.ini

    # Terminal 2: Connect dashboard to the virtual port shown
    python ms2_ini_dash.py --port /tmp/ms2_ecu_sim --ini cfg.ini
"""

from __future__ import annotations
import argparse
import binascii
import math
import os
import pty
import random
import re
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# INI Parsing (subset needed for simulation)
# =============================================================================


@dataclass
class FieldDef:
    """Definition of a single output channel field."""

    name: str
    field_type: str
    data_type: str
    offset: int
    units: str
    scale: float
    translate: float
    bit_range: tuple[int, int] | None = None

    @property
    def size(self) -> int:
        return {"U08": 1, "S08": 1, "U16": 2, "S16": 2, "U32": 4, "S32": 4}.get(
            self.data_type, 2
        )

    @property
    def signed(self) -> bool:
        return self.data_type.startswith("S")

    @property
    def struct_format(self) -> str:
        formats = {
            "U08": "B",
            "S08": "b",
            "U16": "H",
            "S16": "h",
            "U32": "I",
            "S32": "i",
        }
        return "<" + formats.get(self.data_type, "H")


def parse_ini_output_channels(ini_path: Path) -> tuple[dict[str, FieldDef], int, str]:
    """Parse OutputChannels section and signature from INI."""
    content = ini_path.read_text(encoding="utf-8", errors="replace")
    content = re.sub(r"^#[A-Z]{2}\|", "", content, flags=re.MULTILINE)

    fields: dict[str, FieldDef] = {}
    och_block_size = 209
    signature = "MS2Extra comms330NP"  # Default MSPNP2 signature

    in_output_channels = False
    condition_stack: list[bool] = []

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue

        # Handle conditionals
        if line.startswith("#if "):
            cond = line[4:].strip()
            condition_stack.append(cond not in ("CELSIUS", "CAN_COMMANDS"))
            continue
        elif line == "#else":
            if condition_stack:
                condition_stack[-1] = not condition_stack[-1]
            continue
        elif line == "#endif":
            if condition_stack:
                condition_stack.pop()
            continue

        if condition_stack and not all(condition_stack):
            continue

        # Get signature
        if "signature" in line and "=" in line:
            match = re.search(r'signature\s*=\s*"([^"]+)"', line)
            if match:
                signature = match.group(1)

        # Section headers
        if line.startswith("["):
            in_output_channels = line.strip("[]") == "OutputChannels"
            continue

        if not in_output_channels:
            continue

        if "ochBlockSize" in line:
            match = re.search(r"ochBlockSize\s*=\s*(\d+)", line)
            if match:
                och_block_size = int(match.group(1))
            continue

        if "{" in line or "ochGetCommand" in line:
            continue

        if "=" in line:
            f = parse_field_line(line)
            if f:
                fields[f.name] = f

    return fields, och_block_size, signature


def parse_field_line(line: str) -> FieldDef | None:
    """Parse a field definition line."""
    match = re.match(r"(\w+)\s*=\s*(.+)", line)
    if not match:
        return None

    name = match.group(1)
    parts = split_respecting_quotes(match.group(2))
    if len(parts) < 3:
        return None

    field_type = parts[0].strip().lower()
    data_type = parts[1].strip().upper()

    try:
        offset = int(parts[2].strip())
    except ValueError:
        return None

    if field_type == "scalar":
        units = parts[3].strip().strip('"') if len(parts) > 3 else ""
        scale = parse_numeric(parts[4]) if len(parts) > 4 else 1.0
        translate = parse_numeric(parts[5]) if len(parts) > 5 else 0.0
        return FieldDef(name, "scalar", data_type, offset, units, scale, translate)
    elif field_type == "bits":
        bit_range = None
        if len(parts) > 3:
            m = re.search(r"\[(\d+):(\d+)\]", parts[3])
            if m:
                bit_range = (int(m.group(1)), int(m.group(2)))
        return FieldDef(name, "bits", data_type, offset, "", 1.0, 0.0, bit_range)
    return None


def split_respecting_quotes(s: str) -> list[str]:
    parts, current, in_quote = [], [], False
    for c in s:
        if c == '"':
            in_quote = not in_quote
            current.append(c)
        elif c == "," and not in_quote:
            parts.append("".join(current))
            current = []
        else:
            current.append(c)
    if current:
        parts.append("".join(current))
    return parts


def parse_numeric(s: str) -> float:
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        m = re.search(r"[-+]?\d*\.?\d+", s)
        return float(m.group()) if m else 1.0


# =============================================================================
# Engine Simulation
# =============================================================================


@dataclass
class EngineState:
    """Simulated engine state with realistic behavior."""

    # Core parameters
    rpm: float = 850.0
    target_rpm: float = 850.0
    map_kpa: float = 35.0
    tps: float = 0.0

    # Temperatures (Fahrenheit)
    coolant: float = 180.0
    mat: float = 85.0

    # Fuel/ignition
    afr: float = 14.7
    advance: float = 15.0
    pulse_width: float = 2.5
    dwell: float = 3.0

    # Battery
    battery: float = 14.1

    # Timing
    start_time: float = field(default_factory=time.time)

    # State
    running: bool = True
    cranking: bool = False
    warmup: bool = False

    # Simulation mode
    mode: str = "idle"  # idle, cruise, accel, decel
    mode_timer: float = 0.0

    def update(self, dt: float):
        """Update engine state for one time step."""
        self.mode_timer -= dt

        # Randomly change driving mode
        if self.mode_timer <= 0:
            self._change_mode()

        # Update based on mode
        if self.mode == "idle":
            self.target_rpm = 850 + random.uniform(-20, 20)
            self.tps = max(0, self.tps - dt * 50)
            self.map_kpa = 30 + random.uniform(-2, 2)
            self.afr = 14.7 + random.uniform(-0.3, 0.3)
            self.advance = 18 + random.uniform(-1, 1)

        elif self.mode == "cruise":
            self.target_rpm = 2800 + random.uniform(-100, 100)
            self.tps = 25 + random.uniform(-3, 3)
            self.map_kpa = 55 + random.uniform(-5, 5)
            self.afr = 14.5 + random.uniform(-0.2, 0.2)
            self.advance = 28 + random.uniform(-2, 2)

        elif self.mode == "accel":
            self.target_rpm = min(6500, self.target_rpm + dt * 2000)
            self.tps = min(95, self.tps + dt * 100)
            self.map_kpa = min(100, 40 + self.tps * 0.6)
            self.afr = 12.5 + random.uniform(-0.3, 0.3)  # Rich under load
            self.advance = max(10, 35 - self.map_kpa * 0.2)

        elif self.mode == "decel":
            self.target_rpm = max(1200, self.target_rpm - dt * 1500)
            self.tps = max(0, self.tps - dt * 80)
            self.map_kpa = max(20, self.map_kpa - dt * 30)
            self.afr = 15.5 + random.uniform(-0.2, 0.2)  # Lean on decel
            self.advance = 25 + random.uniform(-2, 2)

        # Smooth RPM changes
        rpm_diff = self.target_rpm - self.rpm
        self.rpm += rpm_diff * min(1.0, dt * 5)
        self.rpm = max(0, self.rpm)

        # RPM affects other params
        self.pulse_width = 1.5 + (self.map_kpa / 100) * 8 + random.uniform(-0.1, 0.1)
        self.dwell = 2.5 + random.uniform(-0.1, 0.1)

        # Temperature simulation (slowly drift toward operating temp)
        target_coolant = 190 if self.rpm > 500 else 70
        self.coolant += (target_coolant - self.coolant) * dt * 0.01
        self.coolant += random.uniform(-0.5, 0.5)

        target_mat = 90 + (self.rpm / 6500) * 30
        self.mat += (target_mat - self.mat) * dt * 0.05
        self.mat += random.uniform(-0.2, 0.2)

        # Battery voltage (slight variation, drops slightly at high RPM due to load)
        self.battery = 14.1 - (self.rpm / 6500) * 0.3 + random.uniform(-0.05, 0.05)

        # Warmup state
        self.warmup = self.coolant < 160
        self.cranking = False

    def _change_mode(self):
        """Randomly change driving mode."""
        modes = ["idle", "cruise", "accel", "decel"]
        weights = [0.3, 0.35, 0.2, 0.15]

        # Bias based on current state
        if self.rpm < 1000:
            weights = [0.2, 0.3, 0.4, 0.1]  # More likely to accel from idle
        elif self.rpm > 5000:
            weights = [0.1, 0.2, 0.1, 0.6]  # More likely to decel from high RPM

        self.mode = random.choices(modes, weights)[0]
        self.mode_timer = random.uniform(2.0, 8.0)

    @property
    def seconds(self) -> int:
        """ECU uptime in seconds."""
        return int(time.time() - self.start_time)


def encode_field(buffer: bytearray, field: FieldDef, value: float):
    """Encode a value into the buffer at the field's offset."""
    if field.offset + field.size > len(buffer):
        return

    # Reverse the decode formula: msValue = userValue / scale - translate
    if field.scale != 0:
        raw = (value / field.scale) - field.translate
    else:
        raw = value

    # Clamp to type range
    type_ranges = {
        "U08": (0, 255),
        "S08": (-128, 127),
        "U16": (0, 65535),
        "S16": (-32768, 32767),
        "U32": (0, 4294967295),
        "S32": (-2147483648, 2147483647),
    }
    lo, hi = type_ranges.get(field.data_type, (0, 65535))
    raw = max(lo, min(hi, int(raw)))

    # Pack into buffer
    struct.pack_into(field.struct_format, buffer, field.offset, raw)


def build_outpc(
    state: EngineState, fields: dict[str, FieldDef], block_size: int
) -> bytes:
    """Build the outpc data block from engine state."""
    buffer = bytearray(block_size)

    # Map state attributes to field names
    state_map = {
        "seconds": state.seconds,
        "rpm": state.rpm,
        "advance": state.advance,
        "map": state.map_kpa,
        "tps": state.tps,
        "coolant": state.coolant,
        "mat": state.mat,
        "batteryVoltage": state.battery,
        "afr1": state.afr,
        "afr2": state.afr + random.uniform(-0.2, 0.2),
        "pulseWidth1": state.pulse_width,
        "pulseWidth2": state.pulse_width,
        "dwell": state.dwell,
        "barometer": 101.3,
        "knock": 0.0,
        "egoCorrection1": 100.0 + random.uniform(-3, 3),
        "egoCorrection2": 100.0 + random.uniform(-3, 3),
        "airCorrection": 100.0,
        "warmupEnrich": 100 + (20 if state.warmup else 0),
        "accelEnrich": 0.0,
        "tpsfuelcut": 100,
        "baroCorrection": 100.0,
        "gammaEnrich": 100 + (10 if state.warmup else 0),
        "veCurr1": 75 + (state.map_kpa / 100) * 50,
        "veCurr2": 75 + (state.map_kpa / 100) * 50,
        "coldAdvDeg": 2.0 if state.warmup else 0.0,
        "TPSdot": random.uniform(-5, 5),
        "MAPdot": random.uniform(-10, 10),
        "fuelload": state.map_kpa,
        "ignload": state.map_kpa,
        "afrtgt1": 14.7 if state.tps < 80 else 12.5,
        "afrtgt2": 14.7 if state.tps < 80 else 12.5,
        "iacstep": 30 if state.rpm < 1000 else 0,
        "idleDC": 35 if state.rpm < 1000 else 0,
    }

    # Engine status bits
    engine_bits = 0
    if state.running:
        engine_bits |= 0x01  # ready
    if state.cranking:
        engine_bits |= 0x02  # crank
    if state.warmup:
        engine_bits |= 0x0C  # startw + warmup
    state_map["engine"] = engine_bits
    state_map["squirt"] = 0x28 if state.running else 0  # inj1 + sched1

    # Encode all fields
    for name, value in state_map.items():
        if name in fields:
            encode_field(buffer, fields[name], value)

    return bytes(buffer)


# =============================================================================
# Serial Protocol
# =============================================================================


def crc32_ms(data: bytes) -> int:
    """Calculate CRC32 as used by Megasquirt."""
    return binascii.crc32(data) & 0xFFFFFFFF


def build_response(flag: int, payload: bytes) -> bytes:
    """Build a newserial response packet."""
    data = bytes([flag]) + payload
    return struct.pack(">H", len(data)) + data + struct.pack(">I", crc32_ms(data))


def read_request(fd: int, timeout: float = 1.0) -> bytes | None:
    """Read a newserial request from file descriptor."""
    import select

    # Wait for data
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None

    # Read size header
    try:
        size_bytes = os.read(fd, 2)
        if len(size_bytes) < 2:
            return None
        size = struct.unpack(">H", size_bytes)[0]

        # Read payload
        payload = b""
        while len(payload) < size:
            chunk = os.read(fd, size - len(payload))
            if not chunk:
                break
            payload += chunk

        # Read CRC
        crc_bytes = os.read(fd, 4)
        if len(crc_bytes) < 4:
            return None

        crc_rx = struct.unpack(">I", crc_bytes)[0]
        if crc_rx != crc32_ms(payload):
            print(f"  [!] CRC mismatch", file=sys.stderr)
            return None

        return payload
    except OSError:
        return None


# =============================================================================
# Main Simulator
# =============================================================================


def run_simulator(ini_path: Path, link_path: str, update_hz: float = 50):
    """Run the ECU simulator."""
    # Parse INI
    print(f"Parsing INI: {ini_path}")
    fields, block_size, signature = parse_ini_output_channels(ini_path)
    print(f"  Found {len(fields)} fields, block size: {block_size}")
    print(f"  Signature: {signature}")

    # Create pseudo-terminal pair
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    print(f"\nVirtual serial port created: {slave_path}")

    # Create symlink for easier access
    link = Path(link_path)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(slave_path)
    print(f"Symlink created: {link_path} -> {slave_path}")

    print(f"\n{'=' * 60}")
    print(f"ECU Simulator running!")
    print(f"{'=' * 60}")
    print(f"\nConnect your dashboard with:")
    print(f"  python ms2_ini_dash.py --port {link_path} --ini {ini_path}")
    print(f"\nPress Ctrl+C to stop\n")

    # Initialize engine state
    state = EngineState()
    last_update = time.time()

    # Stats
    request_count = 0
    last_stats = time.time()

    try:
        while True:
            # Update engine simulation
            now = time.time()
            dt = now - last_update
            last_update = now
            state.update(dt)

            # Check for incoming request
            request = read_request(master_fd, timeout=0.02)

            if request:
                request_count += 1
                cmd = chr(request[0]) if request else "?"

                if request == b"Q":
                    # Signature query
                    response = build_response(0x00, signature.encode() + b"\x00")
                    os.write(master_fd, response)

                elif request == b"A":
                    # Realtime data request
                    outpc = build_outpc(state, fields, block_size)
                    response = build_response(0x01, outpc)
                    os.write(master_fd, response)

                else:
                    # Unknown command - send error
                    response = build_response(0x83, b"")  # Unrecognized command
                    os.write(master_fd, response)

            # Print stats periodically
            if now - last_stats > 2.0:
                print(
                    f"\r  Mode: {state.mode:6s} | RPM: {state.rpm:5.0f} | "
                    f"MAP: {state.map_kpa:5.1f} | TPS: {state.tps:4.1f}% | "
                    f"Requests: {request_count:5d}  ",
                    end="",
                    flush=True,
                )
                last_stats = now

            # Small sleep to prevent CPU spin
            time.sleep(1.0 / update_hz)

    except KeyboardInterrupt:
        print("\n\nShutting down simulator...")
    finally:
        # Cleanup
        if link.is_symlink():
            link.unlink()
        os.close(master_fd)
        os.close(slave_fd)
        print("Cleanup complete.")


def main():
    parser = argparse.ArgumentParser(description="Megasquirt 2 ECU Simulator")
    parser.add_argument("--ini", required=True, help="Path to TunerStudio INI file")
    parser.add_argument(
        "--link",
        default="/tmp/ms2_ecu_sim",
        help="Path for virtual serial port symlink (default: /tmp/ms2_ecu_sim)",
    )
    parser.add_argument(
        "--hz", type=float, default=50, help="Internal update rate in Hz (default: 50)"
    )
    args = parser.parse_args()

    ini_path = Path(args.ini)
    if not ini_path.exists():
        print(f"Error: INI file not found: {ini_path}", file=sys.stderr)
        sys.exit(1)

    run_simulator(ini_path, args.link, args.hz)


if __name__ == "__main__":
    main()

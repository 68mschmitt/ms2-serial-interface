"""
TunerStudio INI file parser for MS2Extra ECU.

Parses the INI file to extract:
- Signature
- OutputChannels definitions (field names, types, offsets, scales)
- Constants definitions
- ochBlockSize
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class FieldDef:
    """Definition of a single output channel or constant field."""

    name: str
    field_type: str  # scalar, bits, array
    data_type: str  # U08, S08, U16, S16, U32, S32
    offset: int
    units: str = ""
    scale: float = 1.0
    translate: float = 0.0
    bit_range: Optional[tuple[int, int]] = None
    array_size: Optional[int] = None
    page: int = 1  # Page number (1-indexed as in INI)

    @property
    def size(self) -> int:
        """Get the size in bytes for this data type."""
        sizes = {
            "U08": 1,
            "S08": 1,
            "U16": 2,
            "S16": 2,
            "U32": 4,
            "S32": 4,
        }
        base_size = sizes.get(self.data_type, 2)
        if self.array_size:
            return base_size * self.array_size
        return base_size

    @property
    def signed(self) -> bool:
        """Check if this is a signed type."""
        return self.data_type.startswith("S")

    @property
    def struct_format(self) -> str:
        """Get the struct pack/unpack format character."""
        formats = {
            "U08": "B",
            "S08": "b",
            "U16": "H",
            "S16": "h",
            "U32": "I",
            "S32": "i",
        }
        fmt = formats.get(self.data_type, "H")
        return ">" + fmt  # Big-endian (Megasquirt protocol)


@dataclass
class INIConfig:
    """Parsed INI configuration."""

    signature: str = "MS2Extra comms330NP"
    och_block_size: int = 209
    output_channels: dict[str, FieldDef] = field(default_factory=dict)
    constants: dict[str, FieldDef] = field(default_factory=dict)
    pages: dict[int, dict] = field(default_factory=dict)

    # Protocol settings
    query_command: str = "Q"
    och_get_command: str = "A"
    can_commands: bool = True


class INIParser:
    """Parser for TunerStudio INI files."""

    def __init__(self, ini_path: Path):
        self.ini_path = Path(ini_path)
        self.config = INIConfig()
        self._condition_stack: list[bool] = []
        self._current_section: str = ""
        self._current_page: int = 0

    def parse(self) -> INIConfig:
        """Parse the INI file and return configuration."""
        content = self.ini_path.read_text(encoding="utf-8", errors="replace")

        # Remove conditional prefixes (e.g., #XR|)
        content = re.sub(r"^#[A-Z]{2}\|", "", content, flags=re.MULTILINE)

        for line in content.splitlines():
            self._process_line(line.strip())

        return self.config

    def _process_line(self, line: str):
        """Process a single line from the INI file."""
        if not line or line.startswith(";"):
            return

        # Handle preprocessor conditionals
        if line.startswith("#if "):
            cond = line[4:].strip()
            # For simulator, treat most conditions as true except CELSIUS
            is_true = cond not in ("CELSIUS",)
            if cond == "CAN_COMMANDS":
                is_true = self.config.can_commands
            self._condition_stack.append(is_true)
            return
        elif line == "#else":
            if self._condition_stack:
                self._condition_stack[-1] = not self._condition_stack[-1]
            return
        elif line == "#endif":
            if self._condition_stack:
                self._condition_stack.pop()
            return
        elif line.startswith("#set "):
            var = line[5:].strip()
            if var == "CAN_COMMANDS":
                self.config.can_commands = True
            return
        elif line.startswith("#unset "):
            var = line[7:].strip()
            if var == "CAN_COMMANDS":
                self.config.can_commands = False
            return

        # Skip if inside a false conditional
        if self._condition_stack and not all(self._condition_stack):
            return

        # Check for section headers
        if line.startswith("["):
            self._current_section = line.strip("[]")
            return

        # Extract signature
        if "signature" in line.lower() and "=" in line:
            match = re.search(r'signature\s*=\s*"([^"]+)"', line, re.IGNORECASE)
            if match:
                self.config.signature = match.group(1)
            return

        # Process based on section
        if self._current_section == "OutputChannels":
            self._parse_output_channel(line)
        elif self._current_section == "Constants":
            self._parse_constant(line)

    def _parse_output_channel(self, line: str):
        """Parse an OutputChannels line."""
        # Handle ochBlockSize
        if "ochBlockSize" in line:
            match = re.search(r"ochBlockSize\s*=\s*(\d+)", line)
            if match:
                self.config.och_block_size = int(match.group(1))
            return

        # Skip non-field lines
        if "{" in line or "ochGetCommand" in line or "deadValue" in line:
            return

        # Parse field definition
        field_def = self._parse_field_line(line)
        if field_def:
            self.config.output_channels[field_def.name] = field_def

    def _parse_constant(self, line: str):
        """Parse a Constants line."""
        # Handle page directive
        if line.strip().startswith("page"):
            match = re.search(r"page\s*=\s*(\d+)", line)
            if match:
                self._current_page = int(match.group(1))
            return

        # Parse field definition
        field_def = self._parse_field_line(line)
        if field_def:
            # Assign the current page to this constant
            field_def.page = self._current_page
            self.config.constants[field_def.name] = field_def

    def _parse_field_line(self, line: str) -> Optional[FieldDef]:
        """Parse a field definition line."""
        match = re.match(r"(\w+)\s*=\s*(.+)", line)
        if not match:
            return None

        name = match.group(1)
        parts = self._split_respecting_quotes(match.group(2))

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
            units = parts[3].strip().strip('"') if len(parts) > 3 else ""
            scale = self._parse_numeric(parts[4]) if len(parts) > 4 else 1.0
            translate = self._parse_numeric(parts[5]) if len(parts) > 5 else 0.0
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
            bit_range = None
            if len(parts) > 3:
                m = re.search(r"\[(\d+):(\d+)\]", parts[3])
                if m:
                    bit_range = (int(m.group(1)), int(m.group(2)))
            return FieldDef(
                name=name,
                field_type="bits",
                data_type=data_type,
                offset=offset,
                bit_range=bit_range,
            )

        elif field_type == "array":
            # Parse array size from format like [6] or [6x6]
            array_size = None
            if len(parts) > 3:
                m = re.search(r"\[\s*(\d+)(?:x\d+)?\s*\]", parts[3])
                if m:
                    array_size = int(m.group(1))
            units = parts[4].strip().strip('"') if len(parts) > 4 else ""
            scale = self._parse_numeric(parts[5]) if len(parts) > 5 else 1.0
            translate = self._parse_numeric(parts[6]) if len(parts) > 6 else 0.0
            return FieldDef(
                name=name,
                field_type="array",
                data_type=data_type,
                offset=offset,
                units=units,
                scale=scale,
                translate=translate,
                array_size=array_size,
            )

        return None

    @staticmethod
    def _split_respecting_quotes(s: str) -> list[str]:
        """Split string by commas, respecting quoted sections."""
        parts = []
        current = []
        in_quote = False

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

    @staticmethod
    def _parse_numeric(s: str) -> float:
        """Parse a numeric value from string, handling expressions."""
        s = s.strip()
        try:
            return float(s)
        except ValueError:
            # Try to extract a numeric value
            m = re.search(r"[-+]?\d*\.?\d+", s)
            return float(m.group()) if m else 1.0


def parse_ini(ini_path: Path) -> INIConfig:
    """Convenience function to parse an INI file."""
    parser = INIParser(ini_path)
    return parser.parse()

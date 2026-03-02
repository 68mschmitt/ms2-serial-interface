"""
Configuration page builder for MS2Extra ECU simulator.

Converts MSQ tune data into binary page format that TunerStudio expects.
This allows the simulator to serve actual tune data instead of zeros.
"""

from __future__ import annotations
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import xml.etree.ElementTree as ET

try:
    from .ini_parser import INIConfig, FieldDef
except ImportError:
    from ini_parser import INIConfig, FieldDef


@dataclass
class PageConfig:
    """Configuration for a single page."""

    page_num: int  # Page number in INI (1-7)
    table_id: int  # Table ID for protocol (0x04, 0x05, etc.)
    size: int  # Page size in bytes (typically 1024)


# MS2Extra page mapping from INI
# pageIdentifier shows: \x04, \x05, \x0a, \x08, \x09, \x0b, \x0c for pages 1-7
# But MSQ files use 0-indexed page numbers (0-6)
# page_num here matches MSQ file page numbers
MS2_PAGES = [
    PageConfig(page_num=0, table_id=0x04, size=1024),  # MSQ page 0 = INI page 1
    PageConfig(page_num=1, table_id=0x05, size=1024),  # MSQ page 1 = INI page 2
    PageConfig(page_num=2, table_id=0x0A, size=1024),  # MSQ page 2 = INI page 3
    PageConfig(page_num=3, table_id=0x08, size=1024),  # MSQ page 3 = INI page 4
    PageConfig(page_num=4, table_id=0x09, size=1024),  # MSQ page 4 = INI page 5
    PageConfig(page_num=5, table_id=0x0B, size=1024),  # MSQ page 5 = INI page 6
    PageConfig(page_num=6, table_id=0x0C, size=1024),  # MSQ page 6 = INI page 7
]


class PageBuilder:
    """Builds binary configuration pages from MSQ tune data."""

    def __init__(self, ini_config: INIConfig):
        self.ini_config = ini_config
        self.pages: dict[int, bytearray] = {}  # table_id -> page data

        # Initialize empty pages
        for page_cfg in MS2_PAGES:
            self.pages[page_cfg.table_id] = bytearray(page_cfg.size)

    def load_from_msq(self, msq_path: Path) -> bool:
        """
        Load configuration data from MSQ file.

        Args:
            msq_path: Path to MSQ file

        Returns:
            True if loaded successfully
        """
        content = msq_path.read_text(encoding="utf-8", errors="replace")

        # Remove line-prefix markers
        content = re.sub(r"^#[A-Z]{2}\|", "", content, flags=re.MULTILINE)

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            print(f"Error parsing MSQ: {e}")
            return False

        ns = {"msq": "http://www.msefi.com/:msq"}

        # Parse each page
        for page_elem in root.findall("msq:page", ns) + root.findall("page"):
            page_num = int(page_elem.get("number", -1))

            # Find the corresponding table_id
            page_cfg = next((p for p in MS2_PAGES if p.page_num == page_num), None)
            if not page_cfg:
                continue

            # Process constants in this page
            # INI pages are 1-indexed, MSQ pages are 0-indexed
            ini_page_num = page_num + 1
            for const in page_elem.findall("msq:constant", ns) + page_elem.findall(
                "constant"
            ):
                name = const.get("name")
                if not name:
                    continue

                # Find the field definition in INI
                field = self.ini_config.constants.get(name)
                if not field:
                    continue

                # Verify the field belongs to this page (INI uses 1-indexed pages)
                if field.page != ini_page_num:
                    continue

                # Parse and encode the value
                self._encode_constant(page_cfg.table_id, field, const)

        return True

    def _encode_constant(self, table_id: int, field: FieldDef, const_elem: ET.Element):
        """Encode a constant value into the page buffer."""
        text = (const_elem.text or "").strip()

        # Get page buffer
        buffer = self.pages.get(table_id)
        if buffer is None:
            return

        # Check bounds
        if field.offset + field.size > len(buffer):
            return

        # Handle different field types
        if field.field_type == "bits":
            self._encode_bits(buffer, field, text, const_elem)
        elif field.field_type == "scalar":
            self._encode_scalar(buffer, field, text)
        elif field.field_type == "array":
            self._encode_array(buffer, field, text, const_elem)

    def _encode_bits(
        self, buffer: bytearray, field: FieldDef, text: str, elem: ET.Element
    ):
        """Encode a bits field."""
        if not field.bit_range:
            return

        lo_bit, hi_bit = field.bit_range

        # Try to find the index of the value in the enum
        # The text might be quoted like '"4"' for nCylinders
        text = text.strip('"')

        # For numeric-like values, try direct conversion
        try:
            value = int(float(text))
        except ValueError:
            # For string enums, we'd need the enum list from INI
            # For now, just use 0
            value = 0

        # Read current byte, modify bits, write back
        current = buffer[field.offset]

        # Create mask for the bit range
        num_bits = hi_bit - lo_bit + 1
        mask = ((1 << num_bits) - 1) << lo_bit

        # Clear bits and set new value
        current &= ~mask
        current |= (value << lo_bit) & mask

        buffer[field.offset] = current

    def _encode_scalar(self, buffer: bytearray, field: FieldDef, text: str):
        """Encode a scalar field."""
        try:
            user_value = float(text)
        except ValueError:
            return

        # Apply reverse transformation: msValue = userValue / scale - translate
        if field.scale != 0:
            ms_value = user_value / field.scale - field.translate
        else:
            ms_value = user_value

        # Clamp and convert to integer
        ms_value = int(round(ms_value))

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
        ms_value = max(lo, min(hi, ms_value))

        # Pack into buffer (big-endian for MS2Extra)
        fmt = self._get_struct_format(field.data_type, big_endian=True)
        try:
            struct.pack_into(fmt, buffer, field.offset, ms_value)
        except struct.error:
            pass

    def _encode_array(
        self, buffer: bytearray, field: FieldDef, text: str, elem: ET.Element
    ):
        """Encode an array field."""
        # Parse array values
        values = []
        for part in text.split():
            part = part.strip()
            if not part:
                continue
            try:
                values.append(float(part))
            except ValueError:
                values.append(0.0)

        if not values:
            return

        # Get element size
        elem_sizes = {"U08": 1, "S08": 1, "U16": 2, "S16": 2, "U32": 4, "S32": 4}
        elem_size = elem_sizes.get(field.data_type, 2)

        # Get type range for clamping
        type_ranges = {
            "U08": (0, 255),
            "S08": (-128, 127),
            "U16": (0, 65535),
            "S16": (-32768, 32767),
            "U32": (0, 4294967295),
            "S32": (-2147483648, 2147483647),
        }
        lo, hi = type_ranges.get(field.data_type, (0, 65535))

        # Get struct format
        fmt = self._get_struct_format(field.data_type, big_endian=True)

        # Encode each value
        for i, user_value in enumerate(values):
            offset = field.offset + i * elem_size
            if offset + elem_size > len(buffer):
                break

            # Apply reverse transformation
            if field.scale != 0:
                ms_value = user_value / field.scale - field.translate
            else:
                ms_value = user_value

            ms_value = int(round(ms_value))
            ms_value = max(lo, min(hi, ms_value))

            try:
                struct.pack_into(fmt, buffer, offset, ms_value)
            except struct.error:
                pass

    @staticmethod
    def _get_struct_format(data_type: str, big_endian: bool = True) -> str:
        """Get struct format string for data type."""
        formats = {
            "U08": "B",
            "S08": "b",
            "U16": "H",
            "S16": "h",
            "U32": "I",
            "S32": "i",
        }
        fmt = formats.get(data_type, "H")
        prefix = ">" if big_endian else "<"
        return prefix + fmt

    def get_page_data(self, table_id: int) -> bytes:
        """Get the binary data for a page."""
        if table_id in self.pages:
            return bytes(self.pages[table_id])
        return bytes(1024)  # Return zeros for unknown pages

    def get_page_slice(self, table_id: int, offset: int, count: int) -> bytes:
        """Get a slice of page data."""
        data = self.get_page_data(table_id)
        return data[offset : offset + count]


def load_tune_pages(ini_config: INIConfig, msq_path: Path) -> Optional[PageBuilder]:
    """
    Load tune pages from MSQ file.

    Args:
        ini_config: Parsed INI configuration
        msq_path: Path to MSQ file

    Returns:
        PageBuilder with loaded data, or None on failure
    """
    builder = PageBuilder(ini_config)
    if builder.load_from_msq(msq_path):
        return builder
    return None


def save_pages_to_file(page_data: dict[int, bytes], filepath: Path) -> bool:
    """
    Save page data to a binary file.

    File format:
    - 4 bytes: magic "MS2P"
    - 4 bytes: version (1)
    - 4 bytes: number of pages
    - For each page:
        - 1 byte: table_id
        - 2 bytes: page size (big-endian)
        - N bytes: page data

    Args:
        page_data: Dict of table_id -> page bytes
        filepath: Path to save file

    Returns:
        True if saved successfully
    """
    import struct

    try:
        with open(filepath, "wb") as f:
            # Magic and version
            f.write(b"MS2P")
            f.write(struct.pack(">I", 1))  # version
            f.write(struct.pack(">I", len(page_data)))

            # Write each page
            for table_id, data in sorted(page_data.items()):
                f.write(struct.pack("B", table_id))
                f.write(struct.pack(">H", len(data)))
                f.write(data)

        return True
    except OSError as e:
        print(f"Error saving pages: {e}")
        return False


def load_pages_from_file(filepath: Path) -> Optional[dict[int, bytes]]:
    """
    Load page data from a binary file.

    Args:
        filepath: Path to saved pages file

    Returns:
        Dict of table_id -> page bytes, or None on failure
    """
    import struct

    try:
        with open(filepath, "rb") as f:
            # Check magic
            magic = f.read(4)
            if magic != b"MS2P":
                print(f"Invalid pages file: bad magic")
                return None

            # Version
            version = struct.unpack(">I", f.read(4))[0]
            if version != 1:
                print(f"Unsupported pages file version: {version}")
                return None

            # Number of pages
            num_pages = struct.unpack(">I", f.read(4))[0]

            # Read pages
            pages = {}
            for _ in range(num_pages):
                table_id = struct.unpack("B", f.read(1))[0]
                size = struct.unpack(">H", f.read(2))[0]
                data = f.read(size)
                if len(data) != size:
                    print(f"Truncated pages file")
                    return None
                pages[table_id] = data

        return pages
    except OSError as e:
        print(f"Error loading pages: {e}")
        return None
    except struct.error as e:
        print(f"Error parsing pages file: {e}")
        return None

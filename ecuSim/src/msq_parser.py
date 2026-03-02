"""
MSQ tune file parser.

Parses TunerStudio MSQ (MegaSquirt Configuration) XML files to extract
tune data including VE tables, AFR targets, and configuration constants.
"""

from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TuneData:
    """Parsed tune data from MSQ file."""

    # Metadata
    signature: str = ""
    tune_comment: str = ""
    write_date: str = ""
    firmware_info: str = ""

    # Configuration pages
    pages: dict[int, dict[str, Any]] = field(default_factory=dict)

    # PC Variables (TunerStudio settings)
    pc_variables: dict[str, Any] = field(default_factory=dict)

    # Common extracted values for easy access
    ve_table1: Optional[list[list[float]]] = None
    ve_table2: Optional[list[list[float]]] = None
    afr_table1: Optional[list[list[float]]] = None
    spark_table1: Optional[list[list[float]]] = None

    # Fuel settings
    req_fuel: float = 0.0
    stoich: float = 14.7

    # Engine config
    num_cylinders: int = 4
    num_injectors: int = 4


class MSQParser:
    """Parser for TunerStudio MSQ XML files."""

    def __init__(self, msq_path: Path):
        self.msq_path = Path(msq_path)
        self.tune = TuneData()

    def parse(self) -> TuneData:
        """Parse the MSQ file and return tune data."""
        content = self.msq_path.read_text(encoding="utf-8", errors="replace")

        # Remove line-prefix markers (e.g., #XR|)
        content = re.sub(r"^#[A-Z]{2}\|", "", content, flags=re.MULTILINE)

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse MSQ file: {e}")

        # Parse bibliography
        self._parse_bibliography(root)

        # Parse version info
        self._parse_version_info(root)

        # Parse pages
        self._parse_pages(root)

        # Extract common tables
        self._extract_common_tables()

        return self.tune

    def _parse_bibliography(self, root: ET.Element):
        """Parse the bibliography element."""
        ns = {"msq": "http://www.msefi.com/:msq"}
        bib = root.find("msq:bibliography", ns) or root.find("bibliography")

        if bib is not None:
            self.tune.tune_comment = bib.get("tuneComment", "")
            self.tune.write_date = bib.get("writeDate", "")

    def _parse_version_info(self, root: ET.Element):
        """Parse the versionInfo element."""
        ns = {"msq": "http://www.msefi.com/:msq"}
        ver = root.find("msq:versionInfo", ns) or root.find("versionInfo")

        if ver is not None:
            self.tune.signature = ver.get("signature", "")
            self.tune.firmware_info = ver.get("firmwareInfo", "")

    def _parse_pages(self, root: ET.Element):
        """Parse all page elements."""
        ns = {"msq": "http://www.msefi.com/:msq"}

        for page in root.findall("msq:page", ns) + root.findall("page"):
            page_num = int(page.get("number", 0))
            page_data = {}

            # Parse constants
            for const in page.findall("msq:constant", ns) + page.findall("constant"):
                name = const.get("name")
                if name:
                    value = self._parse_value(const)
                    page_data[name] = value

            # Parse pcVariables
            for var in page.findall("msq:pcVariable", ns) + page.findall("pcVariable"):
                name = var.get("name")
                if name:
                    value = self._parse_value(var)
                    self.tune.pc_variables[name] = value

            self.tune.pages[page_num] = page_data

    def _parse_value(self, element: ET.Element) -> Any:
        """Parse a value from a constant or pcVariable element."""
        text = (element.text or "").strip()

        # Check for array (multi-line values)
        if "\n" in text or element.get("cols") or element.get("rows"):
            return self._parse_array(text, element)

        # Check for quoted string
        if text.startswith('"') and text.endswith('"'):
            return text.strip('"')

        # Try to parse as number
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    def _parse_array(self, text: str, element: ET.Element) -> list:
        """Parse an array value."""
        values = []

        # Split by whitespace and newlines
        parts = text.split()

        for part in parts:
            part = part.strip()
            if not part:
                continue
            try:
                if "." in part:
                    values.append(float(part))
                else:
                    values.append(int(part))
            except ValueError:
                values.append(part)

        # Reshape if cols/rows specified
        cols = int(element.get("cols", 0))
        rows = int(element.get("rows", 0))

        if cols > 1 and rows > 1 and len(values) == cols * rows:
            # Reshape into 2D array
            return [values[i * cols : (i + 1) * cols] for i in range(rows)]

        return values

    def _extract_common_tables(self):
        """Extract commonly used tables from parsed data."""
        # VE Table 1 (usually on page 5)
        for page_num, page_data in self.tune.pages.items():
            if "veTable1" in page_data:
                self.tune.ve_table1 = page_data["veTable1"]
            if "veTable2" in page_data:
                self.tune.ve_table2 = page_data["veTable2"]
            if "afrTable1" in page_data:
                self.tune.afr_table1 = page_data["afrTable1"]
            if "advanceTable1" in page_data:
                self.tune.spark_table1 = page_data["advanceTable1"]

            # Engine config
            if "nCylinders" in page_data:
                val = page_data["nCylinders"]
                if isinstance(val, str):
                    # Parse from string like "4"
                    try:
                        self.tune.num_cylinders = int(val)
                    except ValueError:
                        pass
                elif isinstance(val, (int, float)):
                    self.tune.num_cylinders = int(val)

            if "reqFuel" in page_data:
                self.tune.req_fuel = float(page_data["reqFuel"])

            if "stoich" in page_data:
                self.tune.stoich = float(page_data["stoich"])


def parse_msq(msq_path: Path) -> TuneData:
    """Convenience function to parse an MSQ file."""
    parser = MSQParser(msq_path)
    return parser.parse()


def load_latest_tune(project_path: Path) -> Optional[TuneData]:
    """
    Load the most recent tune file from a project directory.

    Args:
        project_path: Path to project directory or parent directory

    Returns:
        TuneData or None if no tune files found
    """
    project_path = Path(project_path)

    # Look for MSQ files
    msq_files = list(project_path.glob("*.msq"))

    # Also check parent directory
    if not msq_files:
        msq_files = list(project_path.parent.glob("*.msq"))

    if not msq_files:
        return None

    # Sort by modification time, newest first
    msq_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Try to parse the newest one
    for msq_file in msq_files:
        try:
            return parse_msq(msq_file)
        except Exception:
            continue

    return None

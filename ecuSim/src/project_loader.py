"""
TunerStudio project configuration loader.

Loads configuration from TunerStudio project directories, including:
- project.properties (serial port, baud rate, etc.)
- mainController.ini (ECU definition)
- custom.ini (custom fields)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from .ini_parser import INIParser, INIConfig
except ImportError:
    from ini_parser import INIParser, INIConfig


@dataclass
class ProjectConfig:
    """TunerStudio project configuration."""

    # Project info
    project_name: str = ""
    project_path: Optional[Path] = None

    # Serial settings
    com_port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200

    # File paths
    ini_file: Optional[Path] = None
    tune_file: Optional[Path] = None

    # ECU settings
    can_id: int = 0
    firmware_description: str = ""

    # INI config (populated after loading)
    ini_config: Optional[INIConfig] = None


def parse_properties_file(path: Path) -> dict[str, str]:
    """Parse a Java-style properties file."""
    props = {}

    if not path.exists():
        return props

    content = path.read_text(encoding="utf-8", errors="replace")

    for line in content.splitlines():
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        # Handle escaped characters in keys
        # TunerStudio uses backslash escapes like "Com\ Port"
        if "=" in line:
            # Find the first unescaped =
            key_end = 0
            i = 0
            while i < len(line):
                if line[i] == "\\" and i + 1 < len(line):
                    i += 2  # Skip escaped character
                    continue
                if line[i] == "=":
                    key_end = i
                    break
                i += 1

            if key_end > 0:
                key = line[:key_end].replace("\\ ", " ").strip()
                value = line[key_end + 1 :].strip()
                props[key] = value

    return props


def load_project(project_path: Path) -> ProjectConfig:
    """
    Load a TunerStudio project configuration.

    Args:
        project_path: Path to the project directory (containing project.properties)

    Returns:
        ProjectConfig with loaded settings
    """
    project_path = Path(project_path)
    config = ProjectConfig(project_path=project_path)

    # Load project.properties
    props_file = project_path / "project.properties"
    if props_file.exists():
        props = parse_properties_file(props_file)

        # Extract settings
        config.project_name = props.get("projectName", "")
        config.baud_rate = int(props.get("baudRate", "115200"))
        config.can_id = int(props.get("canId", "0"))
        config.firmware_description = props.get("firmwareDescription", "")

        # Serial port - try multiple property names
        for key in [
            "commPort",
            "CommSettingCom Port",
            "CommSettingMSCommDriver.RS232 Serial InterfaceCom Port",
            "CommSettingbarfCommDriver.RS232 Serial InterfaceCom Port",
        ]:
            if key in props and props[key]:
                config.com_port = props[key]
                break

        # INI file
        ini_name = props.get("ecuConfigFile", "mainController.ini")
        config.ini_file = project_path / ini_name

        # Last tune file
        tune_name = props.get("lastDisplayedTuneFile", "")
        if tune_name:
            # Remove "Modified - " prefix if present
            tune_name = re.sub(r"^Modified - ", "", tune_name)
            # Try relative to project and parent directories
            for base in [project_path, project_path.parent]:
                tune_path = base / tune_name
                if tune_path.exists():
                    config.tune_file = tune_path
                    break

    # Load INI file
    if config.ini_file and config.ini_file.exists():
        parser = INIParser(config.ini_file)
        config.ini_config = parser.parse()
    else:
        # Try default location
        default_ini = project_path / "mainController.ini"
        if default_ini.exists():
            config.ini_file = default_ini
            parser = INIParser(default_ini)
            config.ini_config = parser.parse()

    return config


def find_project_dir(start_path: Path) -> Optional[Path]:
    """
    Find a TunerStudio project directory.

    Searches for project.properties file starting from start_path
    and moving up through parent directories.

    Args:
        start_path: Starting directory for search

    Returns:
        Path to project directory or None if not found
    """
    current = Path(start_path).resolve()

    # Check if start_path itself is a project dir
    if (current / "project.properties").exists():
        return current

    # Check projectCfg subdirectory (common TunerStudio layout)
    project_cfg = current / "projectCfg"
    if project_cfg.exists() and (project_cfg / "project.properties").exists():
        return project_cfg

    # Search parent directories
    for parent in current.parents:
        if (parent / "project.properties").exists():
            return parent
        project_cfg = parent / "projectCfg"
        if project_cfg.exists() and (project_cfg / "project.properties").exists():
            return project_cfg

    return None

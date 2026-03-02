#!/usr/bin/env python3
"""
MS2Extra ECU Simulator

Simulates a Megasquirt 2 Extra ECU for testing with TunerStudio.
Creates a virtual serial port (PTY) and responds to the newserial protocol.

Usage:
    # Start with TunerStudio project directory (recommended)
    python simulator.py --project ../debugs/miata-tuning/projectCfg/

    # With page persistence (auto-saves when TunerStudio writes)
    python simulator.py --project ../debugs/miata-tuning/projectCfg/ --pages pages.bin

    # Capture workflow (let TunerStudio teach the simulator):
    # 1. Start with --pages but no MSQ file
    # 2. Connect TunerStudio, click "Send to Controller" when prompted
    # 3. Exit simulator (Ctrl+C) - pages are saved
    # 4. Restart - pages are loaded from file, no more mismatch!

    # Connect TunerStudio to the virtual port shown in output
"""

from __future__ import annotations
import argparse
import os
import pty
import select
import sys
import termios
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.ini_parser import INIParser, INIConfig
from src.engine_state import EngineState, ScenarioRunner
from src.protocol import SerialProtocol, RequestBuffer, ProtocolConfig
from src.outpc_builder import OUTPCBuilder
from src.project_loader import load_project, find_project_dir
from src.page_builder import PageBuilder, MS2_PAGES, save_pages_to_file, load_pages_from_file


def configure_pty_as_serial(fd: int) -> None:
    """Configure a PTY to behave like a raw serial port."""
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0  # iflag: no input processing
    attrs[1] = 0  # oflag: no output processing
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0  # lflag: raw mode (no echo, no canonical)
    attrs[6][termios.VMIN] = 1
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


class ECUSimulator:
    """Main ECU simulator class."""

    def __init__(
        self,
        ini_config: INIConfig,
        page_builder: PageBuilder | None = None,
        link_path: str = "/tmp/ecuSim",
        update_hz: float = 50,
        pages_file: Path | None = None,
        debug_values: bool = False,
    ):
        self.ini_config = ini_config
        self.page_builder = page_builder
        self.link_path = link_path
        self.update_hz = update_hz
        self.pages_file = pages_file
        self.debug_values = debug_values

        # Initialize engine state
        self.state = EngineState()
        self.scenario = ScenarioRunner(self.state)

        # Initialize protocol
        proto_config = ProtocolConfig(
            signature=ini_config.signature,
            och_block_size=ini_config.och_block_size,
        )
        self.protocol = SerialProtocol(proto_config)

        # Initialize OUTPC builder
        self.outpc_builder = OUTPCBuilder(ini_config, self.state, debug_values=debug_values)
        self.protocol.set_outpc_builder(self.outpc_builder.build)

        # Initialize page data from multiple sources (priority order):
        # 1. Saved pages file (if exists)
        # 2. Page builder from MSQ
        # 3. Empty pages (will capture from TunerStudio writes)
        self._init_pages()

        # Request buffer
        self.request_buffer = RequestBuffer(self.protocol)

        # PTY file descriptors
        self.master_fd: int = -1
        self.slave_fd: int = -1

        # Stats
        self.request_count = 0
        self.start_time = time.time()

    def _init_pages(self):
        """Initialize page data from available sources."""
        pages_loaded_from = None

        # Try loading saved pages first
        if self.pages_file and self.pages_file.exists():
            saved_pages = load_pages_from_file(self.pages_file)
            if saved_pages:
                for table_id, data in saved_pages.items():
                    self.protocol.set_page_data(table_id, data)
                pages_loaded_from = f"saved file ({self.pages_file.name})"

        # Fall back to page builder if no saved pages
        if not pages_loaded_from and self.page_builder:
            for page_cfg in MS2_PAGES:
                page_data = self.page_builder.get_page_data(page_cfg.table_id)
                self.protocol.set_page_data(page_cfg.table_id, page_data)
            pages_loaded_from = "MSQ tune file"

        # Initialize empty pages if nothing else available
        if not pages_loaded_from:
            for page_cfg in MS2_PAGES:
                self.protocol.set_page_data(page_cfg.table_id, bytes(page_cfg.size))
            pages_loaded_from = "empty (will capture from TunerStudio)"

        self._pages_source = pages_loaded_from

    def start(self):
        """Start the simulator."""
        # Create pseudo-terminal pair
        self.master_fd, self.slave_fd = pty.openpty()
        slave_path = os.ttyname(self.slave_fd)

        # Configure as raw serial
        try:
            configure_pty_as_serial(self.master_fd)
            configure_pty_as_serial(self.slave_fd)
        except termios.error as e:
            print(f"Warning: Could not configure PTY: {e}", file=sys.stderr)

        # Create symlink
        link = Path(self.link_path)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(slave_path)

        # Print startup info
        self._print_startup_info(slave_path)

        # Main loop
        try:
            self._run_loop()
        except KeyboardInterrupt:
            print("\n\nShutting down simulator...")
        finally:
            self._cleanup(link)

    def _print_startup_info(self, slave_path: str):
        """Print startup information."""
        print("=" * 70)
        print("MS2Extra ECU Simulator")
        print("=" * 70)
        print()
        print(f"  Signature:     {self.ini_config.signature}")
        print(f"  Block Size:    {self.ini_config.och_block_size} bytes")
        print(f"  Output Fields: {len(self.ini_config.output_channels)}")
        print(f"  Pages Source:  {self._pages_source}")
        if self.pages_file:
            print(f"  Pages File:    {self.pages_file}")
        print()
        print(f"  Virtual Port:  {slave_path}")
        print(f"  Symlink:       {self.link_path}")
        print()
        print("-" * 70)
        print("TunerStudio Connection:")
        print(f"  1. Open TunerStudio")
        print(f"  2. Go to Communications > Settings")
        print(f"  3. Set Serial Port to: {self.link_path}")
        print(f"  4. Set Baud Rate to: 115200")
        print(f"  5. Click 'Test Port' or connect")
        print("-" * 70)
        print()
        if self.pages_file:
            print("Page data will be auto-saved on exit if modified.")
        print("Press Ctrl+C to stop")
        print()

    def _run_loop(self):
        """Main simulation loop."""
        last_update = time.time()
        last_stats = time.time()

        while True:
            # Update engine simulation
            now = time.time()
            dt = now - last_update
            last_update = now

            self.state.update(dt)
            self.scenario.update(dt)

            # Check for incoming data
            ready, _, _ = select.select([self.master_fd], [], [], 0.02)
            if ready:
                try:
                    raw_data = os.read(self.master_fd, 1024)
                    if raw_data:
                        self.request_buffer.add_data(raw_data)
                except OSError:
                    pass

            # Process requests
            while True:
                response = self.request_buffer.get_next_response()
                if response is None:
                    break

                self.request_count += 1
                try:
                    os.write(self.master_fd, response)
                except OSError:
                    pass

            # Print stats periodically
            if now - last_stats > 2.0:
                self._print_stats()
                last_stats = now

            # Sleep to control loop rate
            time.sleep(1.0 / self.update_hz)

    def _print_stats(self):
        """Print current statistics."""
        s = self.state
        print(
            f"\r  Mode: {s.mode:6s} | "
            f"RPM: {s.rpm:5.0f} | "
            f"MAP: {s.map_kpa:5.1f} kPa | "
            f"TPS: {s.tps:4.1f}% | "
            f"AFR: {s.afr:4.1f} | "
            f"Requests: {self.request_count:6d}  ",
            end="",
            flush=True,
        )

    def _cleanup(self, link: Path):
        """Clean up resources and save pages if modified."""
        # Save pages if modified and we have a pages file configured
        if self.pages_file and self.protocol.is_pages_modified():
            print("\nSaving modified page data...")
            page_data = self.protocol.get_all_page_data()
            if save_pages_to_file(page_data, self.pages_file):
                print(f"  Saved {len(page_data)} pages to {self.pages_file}")
            else:
                print("  Failed to save pages!")

        if link.is_symlink():
            link.unlink()
        if self.master_fd >= 0:
            os.close(self.master_fd)
        if self.slave_fd >= 0:
            os.close(self.slave_fd)
        print("Cleanup complete.")


def find_msq_file(project_dir: Path) -> Path | None:
    """Find the most recent MSQ file in or near the project directory."""
    # Check common locations
    search_paths = [
        project_dir,
        project_dir.parent,
        project_dir.parent / "CurrentTune.msq",
    ]

    # Look for CurrentTune.msq first
    for path in [
        project_dir.parent / "CurrentTune.msq",
        project_dir / "CurrentTune.msq",
    ]:
        if path.exists():
            return path

    # Find all MSQ files
    msq_files = []
    for base in [project_dir, project_dir.parent]:
        msq_files.extend(base.glob("*.msq"))

    if not msq_files:
        return None

    # Return newest
    msq_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return msq_files[0]


def load_config(args) -> tuple[INIConfig, PageBuilder | None]:
    """Load INI configuration and optionally tune data."""
    ini_config = None
    page_builder = None
    msq_path = None

    # Try project directory first
    if args.project:
        project_path = Path(args.project)
        if not project_path.exists():
            print(
                f"Error: Project directory not found: {project_path}", file=sys.stderr
            )
            sys.exit(1)

        # Find project.properties
        project_dir = find_project_dir(project_path)
        if not project_dir:
            print(
                f"Error: No project.properties found in {project_path}", file=sys.stderr
            )
            sys.exit(1)

        print(f"Loading project: {project_dir}")
        project = load_project(project_dir)

        if project.ini_config:
            ini_config = project.ini_config

            # Find MSQ file
            if args.tune:
                msq_path = Path(args.tune)
            else:
                msq_path = find_msq_file(project_dir)
        else:
            print(f"Error: Could not load INI from project", file=sys.stderr)
            sys.exit(1)

    # Try explicit INI file
    elif args.ini:
        ini_path = Path(args.ini)
        if not ini_path.exists():
            print(f"Error: INI file not found: {ini_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Loading INI: {ini_path}")
        parser = INIParser(ini_path)
        ini_config = parser.parse()

        # Try to find MSQ file
        if args.tune:
            msq_path = Path(args.tune)
        else:
            msq_path = find_msq_file(ini_path.parent)

    else:
        print("Error: Must specify --project or --ini", file=sys.stderr)
        sys.exit(1)

    # Load tune data if MSQ file found
    if msq_path and msq_path.exists():
        print(f"Loading tune: {msq_path.name}")
        page_builder = PageBuilder(ini_config)
        if page_builder.load_from_msq(msq_path):
            print(f"  Loaded {len(ini_config.constants)} constants into pages")
        else:
            print(f"  Warning: Failed to load tune data")
            page_builder = None
    else:
        print("No tune file found - TunerStudio will show settings mismatch")
        print("  Use --tune to specify an MSQ file")

    return ini_config, page_builder


def main():
    parser = argparse.ArgumentParser(
        description="MS2Extra ECU Simulator for TunerStudio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with project directory
  %(prog)s --project ../debugs/miata-tuning/projectCfg/

  # With page persistence (recommended)
  %(prog)s --project ../debugs/miata-tuning/projectCfg/ --pages pages.bin

  # Capture from TunerStudio (no MSQ needed):
  # 1. Start simulator with --pages
  # 2. Connect TunerStudio, send settings to controller
  # 3. Exit (Ctrl+C) to save, restart to use saved pages
  %(prog)s --ini path/to/mainController.ini --pages pages.bin
        """,
    )

    parser.add_argument(
        "--project",
        "-p",
        help="Path to TunerStudio project directory",
    )

    parser.add_argument(
        "--ini",
        "-i",
        help="Path to TunerStudio INI file",
    )

    parser.add_argument(
        "--tune",
        "-t",
        help="Path to MSQ tune file (auto-detected if not specified)",
    )

    parser.add_argument(
        "--link",
        "-l",
        default="/tmp/ecuSim",
        help="Path for virtual serial port symlink (default: /tmp/ecuSim)",
    )

    parser.add_argument(
        "--hz",
        type=float,
        default=50,
        help="Internal update rate in Hz (default: 50)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--pages",
        help="Path to pages file for persistence (loads on start, saves on exit)",
    )

    parser.add_argument(
        "--debug-values",
        action="store_true",
        help="Output incrementing debug values instead of simulated engine data (for testing decode)",
    )

    args = parser.parse_args()

    # Load INI configuration and tune data
    ini_config, page_builder = load_config(args)

    print()
    print(f"Signature: {ini_config.signature}")
    print(f"Output channels: {len(ini_config.output_channels)}")
    print(f"Constants: {len(ini_config.constants)}")
    print(f"Block size: {ini_config.och_block_size}")
    print()

    # Create and start simulator
    pages_file = Path(args.pages) if args.pages else None
    debug_values = getattr(args, 'debug_values', False)
    simulator = ECUSimulator(
        ini_config=ini_config,
        page_builder=page_builder,
        link_path=args.link,
        update_hz=args.hz,
        pages_file=pages_file,
        debug_values=debug_values,
    )

    simulator.start()


if __name__ == "__main__":
    main()

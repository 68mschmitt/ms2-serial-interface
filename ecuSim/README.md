# MS2Extra ECU Simulator

A comprehensive ECU simulator for testing TunerStudio with Megasquirt 2 Extra configurations.

## Overview

This simulator creates a virtual serial port that speaks the MS2Extra "newserial" protocol, allowing TunerStudio to connect as if it were a real ECU. The simulator:

- Parses your actual TunerStudio INI file for accurate field definitions
- Simulates realistic engine behavior (RPM, MAP, temperatures, etc.)
- Responds to all standard TunerStudio commands
- Supports your miata-tuning project configuration

## Quick Start

### Using your Miata tuning project

```bash
cd ecuSim
python simulator.py --project ../debugs/miata-tuning/projectCfg/
```

### Using a specific INI file

```bash
python simulator.py --ini ../debugs/miata-tuning/projectCfg/mainController.ini
```

### Connect TunerStudio

1. Start the simulator (it will display the virtual serial port path)
2. Open TunerStudio
3. Go to **Communications → Settings**
4. Set **Serial Port** to: `/tmp/ecuSim` (or the path shown)
5. Set **Baud Rate** to: `115200`
6. Click **Connect**

## Features

### Engine Simulation

The simulator models realistic engine behavior with multiple driving modes:

- **Idle**: ~850 RPM, low MAP, closed throttle
- **Cruise**: ~2800 RPM, partial throttle, moderate load
- **Acceleration**: RPM climbing, high throttle, rich mixture
- **Deceleration**: RPM dropping, closed throttle, lean mixture

The simulator automatically transitions between modes to create realistic data patterns.

### Protocol Support

Implements the MS2Extra "newserial" protocol including:

- `Q` / `S` - Signature query
- `A` - Simple realtime data request
- `r` - CAN-style read (OUTPC, signature, version, config pages)
- `w` - CAN-style write (acknowledged but not stored)
- `F` - Protocol version query

### Output Channels

Simulates 100+ output channels matching the MS2Extra format:

- Engine speed (RPM)
- Manifold pressure (MAP)
- Throttle position (TPS)
- Air/fuel ratio (AFR)
- Coolant and air temperatures
- Ignition advance
- Injector pulse width
- Battery voltage
- And many more...

## Project Structure

```
ecuSim/
├── simulator.py          # Main entry point
├── README.md             # This file
└── src/
    ├── __init__.py
    ├── ini_parser.py     # TunerStudio INI file parser
    ├── engine_state.py   # Engine simulation logic
    ├── protocol.py       # MS2Extra serial protocol
    ├── outpc_builder.py  # Output channels data builder
    ├── project_loader.py # TunerStudio project loader
    └── msq_parser.py     # MSQ tune file parser
```

## Command Line Options

```
usage: simulator.py [-h] [--project PROJECT] [--ini INI] [--link LINK] [--hz HZ] [--verbose]

Options:
  --project, -p    Path to TunerStudio project directory
  --ini, -i        Path to TunerStudio INI file
  --link, -l       Path for virtual serial port symlink (default: /tmp/ecuSim)
  --hz             Internal update rate in Hz (default: 50)
  --verbose, -v    Enable verbose output
```

## Examples

### Basic usage with project directory

```bash
python simulator.py --project ../debugs/miata-tuning/projectCfg/
```

### Custom symlink location

```bash
python simulator.py --project ../debugs/miata-tuning/projectCfg/ --link /dev/pts/virtual_ecu
```

### Higher update rate

```bash
python simulator.py --project ../debugs/miata-tuning/projectCfg/ --hz 100
```

## Supported ECU Signature

The simulator uses the signature from your INI file:

```
MS2Extra comms330NP
```

This is the standard MS2Extra 3.3.x PNP signature for your Miata.

## Technical Details

### Protocol Format

The newserial protocol uses CRC32-wrapped packets:

```
Request:  [size:2][payload][crc32:4]
Response: [size:2][flag:1][payload][crc32:4]
```

- Size: Big-endian, includes flag byte
- CRC32: Standard polynomial (0xEDB88320), covers flag + payload

### Virtual Serial Port

The simulator uses Python's `pty` module to create a pseudo-terminal pair. The slave side is exposed via a symlink at the specified location (default: `/tmp/ecuSim`).

## Troubleshooting

### TunerStudio can't connect

1. Check that the simulator is running
2. Verify the serial port path in TunerStudio matches the symlink
3. Ensure baud rate is set to 115200
4. Try clicking "Detect" in TunerStudio's serial port dropdown

### Gauges show zero values

1. Make sure the INI file loaded correctly (check startup output)
2. Verify the INI file matches your TunerStudio project

### Permission denied on serial port

The `/tmp` location should be accessible. If using a different location, ensure write permissions.

## Development

### Adding new output channels

Edit `src/outpc_builder.py` and add the field name and value to `_get_field_values()`.

### Modifying engine behavior

Edit `src/engine_state.py` to adjust simulation parameters or add new driving scenarios.

### Protocol extensions

Edit `src/protocol.py` to add support for additional commands.

## License

MIT License - Feel free to modify and use as needed.

## Related Projects

- [MS2D](../README.md) - Megasquirt 2 Serial Daemon for real ECU communication
- [miata-tuning](../debugs/miata-tuning/) - Your Miata tune files and configurations

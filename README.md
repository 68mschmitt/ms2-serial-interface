# MS2D - Megasquirt 2 Serial Daemon

A high-performance C daemon for real-time communication with Megasquirt 2 ECUs. Decodes serial data and exposes it via JSON-RPC over Unix socket, with client libraries for C and Node.js, plus a web-based dashboard.

## Features

- **Real-time ECU data** at 30 Hz polling rate
- **JSON-RPC API** over Unix socket for easy integration
- **Auto-configuration** from TunerStudio project directories
- **Client libraries** for C and Node.js
- **Web dashboard** with animated SVG gauges
- **Memory-safe** - validated with Valgrind (zero leaks)

## Architecture

```
┌─────────────┐     Serial      ┌─────────────┐    Unix Socket    ┌─────────────┐
│  MS2 ECU    │◄───(115200)────►│   ms2d      │◄────(JSON-RPC)───►│   Clients   │
│  (Engine)   │                 │  (Daemon)   │                   │  C/Node/Web │
└─────────────┘                 └─────────────┘                   └─────────────┘
                                      │
                                      ▼
                               ┌─────────────┐
                               │  INI Parser │
                               │ (134 fields)│
                               └─────────────┘
```

## Quick Start

### 1. Build the Daemon

```bash
cd ms2d
make
```

### 2. Run with Simulator (for testing)

```bash
# Terminal 1: Start ECU simulator
python3 ms2_ecu_simulator.py --ini cfg.ini

# Terminal 2: Start daemon
cd ms2d
./ms2d --port /tmp/ms2_ecu_sim --ini ../cfg.ini
```

### 3. Run with Real ECU

```bash
cd ms2d
./ms2d --port /dev/ttyUSB0 --ini ../cfg.ini
```

### 4. Auto-configure from TunerStudio Project

```bash
cd ms2d
./ms2d --project ../projectCfg/
```

## Web Dashboard

A real-time dashboard with animated gauges:

```bash
# Start the dashboard server
cd ms2d-dashboard
node server.js

# Open browser to http://localhost:3000
```

Features:
- Round SVG gauges for RPM, AFR, Coolant
- Bar gauges for MAP, TPS, Advance
- Value cards for secondary metrics
- Engine status flags
- 30 Hz refresh rate

## JSON-RPC API

The daemon exposes these methods via Unix socket (`/tmp/ms2d.sock`):

### get_status
```bash
echo '{"method":"get_status","params":{},"id":1}' | nc -U /tmp/ms2d.sock
```
```json
{"result":{"connected":true,"signature":"MS2Extra","request_count":42,"last_poll_timestamp_ms":1234567890}}
```

### get_value
```bash
echo '{"method":"get_value","params":{"field":"rpm"},"id":1}' | nc -U /tmp/ms2d.sock
```
```json
{"result":{"name":"rpm","value":2500,"units":"RPM","last_poll_timestamp_ms":1234567890}}
```

### get_values
```bash
echo '{"method":"get_values","params":{"fields":["rpm","map","tps"]},"id":1}' | nc -U /tmp/ms2d.sock
```
```json
{"result":{"values":[{"name":"rpm","value":2500,"units":"RPM"},{"name":"map","value":95,"units":"kPa"}]}}
```

### get_all
```bash
echo '{"method":"get_all","params":{},"id":1}' | nc -U /tmp/ms2d.sock
```
Returns all 134 decoded fields.

### list_fields
```bash
echo '{"method":"list_fields","params":{},"id":1}' | nc -U /tmp/ms2d.sock
```
```json
{"result":["rpm","map","tps","afr1","advance","coolant",...]}
```

## Client Libraries

### C Client

```c
#include "ms2_client.h"

int main() {
    ms2_client_t *client = ms2_connect("/tmp/ms2d.sock");
    
    double rpm = ms2_get_value(client, "rpm");
    printf("RPM: %.0f\n", rpm);
    
    ms2_disconnect(client);
    return 0;
}
```

Build:
```bash
gcc -o myapp myapp.c -L./ms2d -lms2client
```

### Node.js Client

```javascript
const { MS2Client } = require('./ms2d/clients/ms2_client');

async function main() {
    const client = new MS2Client('/tmp/ms2d.sock');
    await client.connect();
    
    const rpm = await client.getValue('rpm');
    console.log('RPM:', rpm.value);
    
    await client.disconnect();
}
```

## Command Line Options

```
Usage: ./ms2d [OPTIONS]

Options:
  -p, --port <path>      Serial port (e.g., /dev/ttyUSB0)
  -i, --ini <path>       INI file path
  -s, --socket <path>    Unix socket path (default: /tmp/ms2d.sock)
  -P, --project <dir>    TunerStudio project directory (auto-configures)
  -v, --verbose          Enable verbose logging
  -h, --help             Print help

Examples:
  ./ms2d --port /dev/ttyUSB0 --ini cfg.ini
  ./ms2d --project ./projectCfg/
```

## Project Structure

```
.
├── ms2d/                       # Main daemon
│   ├── src/                    # C source files
│   │   ├── main.c              # Entry point, argument parsing
│   │   ├── serial_comm.c       # Serial communication (newserial protocol)
│   │   ├── ini_parser.c        # TunerStudio INI parser
│   │   ├── decoder.c           # OUTPC data decoder
│   │   ├── rpc_server.c        # JSON-RPC over Unix socket
│   │   ├── project_parser.c    # TunerStudio project parser
│   │   └── util.c              # CRC32, timestamps, utilities
│   ├── include/                # Header files
│   ├── clients/                # Client libraries (C, Node.js)
│   ├── vendor/cjson/           # JSON library
│   └── Makefile
│
├── ms2d-dashboard/             # Web dashboard
│   ├── server.js               # HTTP server (bridges to Unix socket)
│   └── public/
│       ├── index.html          # Dashboard HTML
│       ├── style.css           # Dark theme styling
│       └── app.js              # Frontend JavaScript
│
├── cfg.ini                     # MS2 INI file (field definitions)
├── projectCfg/                 # Example TunerStudio project
└── ms2_ecu_simulator.py        # ECU simulator for testing
```

## Configuration

### INI File Mode

Provide the serial port and INI file explicitly:

```bash
./ms2d --port /dev/ttyUSB0 --ini cfg.ini
```

### Project Directory Mode

Point to a TunerStudio project folder and the daemon auto-discovers:
- Serial port from `project.properties`
- Baud rate from `project.properties`
- INI file (`mainController.ini` or as configured)
- Custom fields from `custom.ini`

```bash
./ms2d --project ./projectCfg/
```

## Performance

| Metric | Value |
|--------|-------|
| ECU Poll Rate | 30 Hz |
| Dashboard Refresh | 30 Hz |
| Serial Baud Rate | 115200 |
| OUTPC Block Size | 209 bytes |
| Decoded Fields | 134 |
| RPC Response Time | < 10ms |
| Memory Usage | ~2-5 MB |

## Supported Fields

The daemon decodes 134 fields including:

**Engine**
- `rpm` - Engine RPM
- `advance` - Ignition timing (degrees)
- `engine` - Engine status bits

**Fueling**
- `afr1`, `afr2` - Air/fuel ratio
- `pulseWidth1`, `pulseWidth2` - Injector pulse width (ms)
- `veCurr1` - Current VE (%)
- `accelEnrich` - Acceleration enrichment

**Sensors**
- `map` - Manifold pressure (kPa)
- `tps` - Throttle position (%)
- `coolant` - Coolant temperature
- `mat` - Intake air temperature
- `batteryVoltage` - Battery voltage

**Status**
- `crank` - Cranking flag
- `warmup` - Warmup enrichment active
- `tpsaccaen` - TPS acceleration enrichment active

Run `list_fields` to see all available fields.

## Troubleshooting

### Daemon won't connect
- Verify serial port: `ls -la /dev/ttyUSB*`
- Check permissions: `sudo chmod 666 /dev/ttyUSB0`
- Verify baud rate matches ECU (default 115200)

### RPC clients can't connect
- Check socket exists: `ls -la /tmp/ms2d.sock`
- Verify daemon is running: `pgrep ms2d`

### Dashboard shows "Disconnected"
- Ensure daemon is running
- Check browser console for errors
- Verify `node server.js` is running

## Development

### Build from Source

```bash
cd ms2d
make clean
make
```

### Run Tests

```bash
# With simulator
python3 ms2_ecu_simulator.py --ini cfg.ini &
./ms2d --port /tmp/ms2_ecu_sim --ini cfg.ini &

# Test RPC
echo '{"method":"get_status","id":1}' | nc -U /tmp/ms2d.sock
```

### Memory Check

```bash
valgrind --leak-check=full ./ms2d --port /tmp/ms2_ecu_sim --ini cfg.ini
```

## License

See LICENSE file for details.

## References

- [Megasquirt Documentation](https://www.msextra.com/)
- [TunerStudio](https://tunerstudio.com/)
- [Newserial Protocol](./serial.pdf)

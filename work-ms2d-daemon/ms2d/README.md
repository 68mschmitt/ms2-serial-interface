# MS2D - Megasquirt 2 Daemon

A high-performance daemon for real-time communication with Megasquirt 2 ECUs over serial connections. Provides RPC-based access to ECU sensor data, field definitions, and CAN command capabilities.

## Project Description

MS2D is a C-based daemon that:
- Connects to Megasquirt 2 ECUs via serial port (RS-232/USB)
- Polls ECU OUTPC data at 10Hz for real-time sensor values
- Exposes a Unix socket RPC interface for client applications
- Supports both INI-based and TunerStudio project-based configuration
- Provides field decoding with scale/translate transformations
- Enables CAN command transmission to the ECU
- Includes C and Node.js client libraries for easy integration

## Build Instructions

### Prerequisites
- GCC compiler with C99 support
- POSIX-compliant system (Linux, macOS, BSD)
- pthread library
- Standard C library with socket support

### Building

```bash
# Build daemon and client library
make all

# Build daemon only
make ms2d

# Build client library only
make libms2client.a

# Install to /usr/local
make install

# Clean build artifacts
make clean
```

### Build Output
- `ms2d` - Daemon executable
- `libms2client.a` - Static client library for C applications
- `build/` - Object files and intermediate artifacts

## Usage Examples

### Mode 1: INI File Configuration

Run the daemon with explicit serial port and INI file:

```bash
./ms2d --port /dev/ttyUSB0 --ini cfg.ini
```

This mode requires:
- `--port` - Serial port path (e.g., `/dev/ttyUSB0` or `/tmp/ms2_ecu_sim` for simulator)
- `--ini` - Path to MS2 INI file containing field definitions

Optional parameters:
- `--socket /tmp/ms2d.sock` - Unix socket path (default: `/tmp/ms2d.sock`)
- `--verbose` - Enable verbose logging

### Mode 2: TunerStudio Project Configuration

Run the daemon with a TunerStudio project directory:

```bash
./ms2d --project ./projectCfg/
```

This mode:
- Automatically discovers `project.properties` and `custom.ini`
- Extracts serial port, baud rate, and field definitions
- Requires no additional configuration files

Optional parameters:
- `--socket /tmp/ms2d.sock` - Override Unix socket path
- `--verbose` - Enable verbose logging

### Simulator Mode

For testing without hardware:

```bash
./ms2d --port /tmp/ms2_ecu_sim --ini cfg.ini
```

The daemon will attempt to connect to a simulator on the specified port.

## RPC Method Documentation

The daemon exposes the following RPC methods via Unix socket:

### 1. `get_field` - Retrieve Single Field Value

**Request:**
```json
{
  "method": "get_field",
  "params": {
    "field_name": "rpm"
  }
}
```

**Response:**
```json
{
  "result": {
    "name": "rpm",
    "value": 2500.5,
    "units": "RPM",
    "timestamp_ms": 1234567890
  }
}
```

**Description:** Retrieves the current value of a single field from the ECU. Returns the decoded value with units and timestamp.

---

### 2. `get_all_fields` - Retrieve All Field Values

**Request:**
```json
{
  "method": "get_all_fields",
  "params": {}
}
```

**Response:**
```json
{
  "result": {
    "values": [
      {
        "name": "rpm",
        "value": 2500.5,
        "units": "RPM",
        "timestamp_ms": 1234567890
      },
      {
        "name": "batteryVoltage",
        "value": 13.8,
        "units": "V",
        "timestamp_ms": 1234567890
      }
    ],
    "count": 2
  }
}
```

**Description:** Retrieves all available field values from the ECU in a single request. Useful for dashboard applications.

---

### 3. `get_status` - Retrieve Daemon Status

**Request:**
```json
{
  "method": "get_status",
  "params": {}
}
```

**Response:**
```json
{
  "result": {
    "connected": true,
    "signature": "MS2extra 3.4.6",
    "fields_count": 256,
    "last_poll_ms": 1234567890
  }
}
```

**Description:** Returns daemon connection status, ECU signature, field count, and last poll timestamp.

---

### 4. `list_fields` - List Available Field Names

**Request:**
```json
{
  "method": "list_fields",
  "params": {}
}
```

**Response:**
```json
{
  "result": {
    "fields": [
      "rpm",
      "batteryVoltage",
      "coolant",
      "tps",
      "map"
    ],
    "count": 5
  }
}
```

**Description:** Returns a list of all available field names that can be queried.

---

### 5. `send_can_command` - Send CAN Command to ECU

**Request:**
```json
{
  "method": "send_can_command",
  "params": {
    "can_id": 0x100,
    "data": [0x01, 0x02, 0x03, 0x04]
  }
}
```

**Response:**
```json
{
  "result": {
    "status": "success",
    "bytes_sent": 4
  }
}
```

**Description:** Sends a CAN command to the ECU. Requires CAN commands to be enabled in configuration.

---

## Client Library Examples

### C Client Example

```c
#include "ms2_client.h"
#include <stdio.h>

int main() {
    // Connect to daemon
    ms2_client_t *client = ms2_connect("/tmp/ms2d.sock");
    if (!client) {
        fprintf(stderr, "Failed to connect\n");
        return 1;
    }

    // Get daemon status
    int connected = 0;
    char signature[256] = {0};
    ms2_get_status(client, &connected, signature, sizeof(signature));
    printf("Connected: %s\n", connected ? "yes" : "no");
    printf("Signature: %s\n", signature);

    // Get single field value
    double rpm = ms2_get_value(client, "rpm");
    printf("RPM: %.1f\n", rpm);

    // Get multiple field values
    const char *fields[] = {"rpm", "batteryVoltage", "coolant"};
    double values[3] = {0};
    ms2_get_values(client, fields, 3, values);
    printf("RPM: %.1f, Battery: %.2f V, Coolant: %.1f\n", 
           values[0], values[1], values[2]);

    // List all available fields
    int field_count = 0;
    char **field_names = ms2_list_fields(client, &field_count);
    printf("Total fields: %d\n", field_count);
    for (int i = 0; i < field_count && i < 10; i++) {
        printf("  %s\n", field_names[i]);
    }
    ms2_free_fields(field_names, field_count);

    // Disconnect
    ms2_disconnect(client);
    return 0;
}
```

**Compilation:**
```bash
gcc -o my_app my_app.c -L. -lms2client -I./include
```

---

### Node.js Client Example

```javascript
const { MS2Client } = require('./ms2_client');

async function main() {
  const client = new MS2Client('/tmp/ms2d.sock');

  try {
    // Connect to daemon
    await client.connect();
    console.log('Connected to daemon');

    // Get daemon status
    const status = await client.getStatus();
    console.log('Status:', status);

    // Get single field value
    const rpm = await client.getValue('rpm');
    console.log('RPM:', rpm);

    // Get multiple field values
    const values = await client.getValues(['rpm', 'batteryVoltage', 'tps']);
    console.log('Values:', values);

    // Get all field values
    const allValues = await client.getAll();
    console.log('Total fields:', allValues.values.length);

    // List available fields
    const fields = await client.listFields();
    console.log('Available fields:', fields.slice(0, 10));

    // Disconnect
    await client.disconnect();
  } catch (err) {
    console.error('Error:', err.message);
  }
}

main();
```

**Usage:**
```bash
node ms2_client_example.js /tmp/ms2d.sock
```

---

## Architecture

### Core Components

- **Daemon (ms2d)** - Main process managing ECU communication
- **Serial Communication** - Low-level serial port I/O with timeout handling
- **INI Parser** - Parses MS2 INI files for field definitions
- **Project Parser** - Parses TunerStudio project configurations
- **Decoder** - Decodes raw OUTPC data using field definitions
- **RPC Server** - Unix socket-based RPC interface
- **Client Libraries** - C and Node.js client implementations

### Data Flow

```
ECU (Serial) → Daemon (Poll 10Hz) → OUTPC Buffer → RPC Clients
                                   ↓
                            Field Definitions
                            (INI or Project)
```

## Configuration

### INI File Format

The INI file defines field locations and transformations:

```ini
[OutputChannels]
rpm = 0, u16, 0, 1, 0, "RPM"
batteryVoltage = 2, u08, 0, 0.1, 0, "V"
coolant = 3, s08, 0, 1, -40, "°C"
```

### Project Directory Format

TunerStudio project directories contain:
- `project.properties` - Connection settings
- `custom.ini` - Custom field definitions

## Error Handling

The daemon returns error codes for all operations:

- `MS2D_SUCCESS` (0) - Operation successful
- `MS2D_ERROR_IO` (1) - I/O error
- `MS2D_ERROR_PARSE` (2) - Parse error
- `MS2D_ERROR_INVALID_ARG` (3) - Invalid argument
- `MS2D_ERROR_MEMORY` (4) - Memory allocation error
- `MS2D_ERROR_TIMEOUT` (5) - Operation timeout
- `MS2D_ERROR_SERIAL` (6) - Serial communication error
- `MS2D_ERROR_CONFIG` (7) - Configuration error
- `MS2D_ERROR_THREAD` (8) - Thread operation error

## Performance

- **Poll Rate:** 10 Hz (100ms intervals)
- **RPC Response Time:** < 10ms typical
- **Memory Usage:** ~2-5 MB depending on field count
- **CPU Usage:** < 1% on modern systems

## Troubleshooting

### Daemon won't connect to ECU
- Verify serial port path: `ls -la /dev/ttyUSB*`
- Check baud rate matches ECU configuration (typically 115200)
- Ensure INI file path is correct and readable

### RPC clients can't connect
- Verify socket path exists: `ls -la /tmp/ms2d.sock`
- Check daemon is running: `ps aux | grep ms2d`
- Ensure socket permissions allow client access

### Fields not decoding correctly
- Verify INI file field definitions match ECU firmware
- Check OUTPC buffer size matches configuration
- Review field offset and scale/translate values

## License

See LICENSE file for details.

## Support

For issues, feature requests, or contributions, please refer to the project repository.

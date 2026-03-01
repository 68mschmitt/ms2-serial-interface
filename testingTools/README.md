# MS2D Testing Tools

Tools for capturing, replaying, and verifying ECU data from Megasquirt 2 ECUs.

## Tools

### capture_ecu_outpc.py
Captures OUTPC data blocks from a real ECU by actively polling it.

```bash
# Basic capture (60 seconds at 30Hz)
python capture_ecu_outpc.py --port /dev/ttyUSB0

# Longer capture with custom output
python capture_ecu_outpc.py --port /dev/ttyUSB0 --duration 300 --output cold_start.bin

# High-rate capture for detailed analysis
python capture_ecu_outpc.py --port /dev/ttyUSB0 --hz 50 --output high_rate.bin
```

### replay_ecu_protocol.py
Creates a virtual serial port that emulates a Megasquirt ECU, serving captured data.
TunerStudio or ms2d can connect to this virtual port.

```bash
# Start replay server (loops by default)
python replay_ecu_protocol.py cold_start.bin

# Then connect TunerStudio to: /tmp/ms2_replay
# Or connect ms2d:
#   ./ms2d --port /tmp/ms2_replay --ini ../cfg.ini
```

### inspect_capture.py
Analyze and inspect captured data files.

```bash
# Show capture statistics
python inspect_capture.py cold_start.bin

# Dump specific frames with decoded values
python inspect_capture.py cold_start.bin --dump 0-10 --ini ../cfg.ini

# Export to CSV for external analysis
python inspect_capture.py cold_start.bin --export data.csv --ini ../cfg.ini
```

## Capture File Format (MS2CAP02)

Binary format optimized for compact storage and fast loading:

```
Header:
    8 bytes:  Magic "MS2CAP02"
    4 bytes:  Signature length (uint32 LE)
    N bytes:  ECU signature string

Frames (repeating):
    8 bytes:  Timestamp in microseconds since start (uint64 LE)
    2 bytes:  OUTPC data length (uint16 LE)
    N bytes:  Raw OUTPC data block
```

## Workflow

### Recording at the Car

1. Connect laptop to ECU via serial/USB adapter
2. Run capture tool during desired scenario:
   ```bash
   # Cold start capture
   python capture_ecu_outpc.py -p /dev/ttyUSB0 -d 300 -o cold_start.bin
   
   # Driving capture
   python capture_ecu_outpc.py -p /dev/ttyUSB0 -d 600 -o drive_session.bin
   ```

### Testing at Your Desk

1. Start replay server:
   ```bash
   python replay_ecu_protocol.py cold_start.bin
   ```

2. Connect your tools:
   - **TunerStudio**: Set port to `/tmp/ms2_replay` and connect
   - **ms2d daemon**: `./ms2d --port /tmp/ms2_replay --ini cfg.ini`

3. Verify decoded values match between TunerStudio and your implementation

## Recommended Capture Scenarios

| Scenario | Duration | Description |
|----------|----------|-------------|
| Cold start | 5-10 min | Engine cold → warm idle |
| Idle | 2 min | Steady idle after warmup |
| Rev test | 30 sec | Rev to redline in neutral |
| Cruise | 5 min | Highway steady state |
| Acceleration | 1 min | Hard acceleration runs |
| Deceleration | 1 min | Engine braking / overrun |

## Requirements

- Python 3.10+
- pyserial (`pip install pyserial`)

For capture only - replay uses only standard library.

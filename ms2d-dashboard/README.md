# MS2D Dashboard

Minimal web dashboard for viewing Megasquirt 2 ECU data via the ms2d daemon.

## Quick Start

### 1. Start the ECU simulator (if no real ECU)
```bash
cd /home/mschmitt/projects/tmp/miata/work-ms2d-daemon
python3 ms2_ecu_simulator.py --ini cfg.ini
```

### 2. Start the ms2d daemon
```bash
cd /home/mschmitt/projects/tmp/miata/work-ms2d-daemon/ms2d
./ms2d --port /tmp/ms2_ecu_sim --ini ../cfg.ini
```

### 3. Start the dashboard server
```bash
cd /home/mschmitt/projects/tmp/miata/ms2d-dashboard
node server.js
```

### 4. Open browser
Navigate to: **http://localhost:3000**

## Custom Socket Path

If your daemon uses a different socket:
```bash
node server.js /path/to/ms2d.sock
```

## Features

- Real-time RPM, MAP, TPS gauges with animated bars
- Secondary values: AFR, timing, coolant, IAT, voltage, pulse width, duty cycle, VE
- Engine status flags: Running, Cranking, Warmup, Accel, Decel
- 5 Hz update rate
- Auto-reconnect on connection loss
- Dark theme, responsive design

## Files

- `server.js` - Node.js HTTP server (bridges Unix socket to HTTP)
- `public/index.html` - Dashboard layout
- `public/style.css` - Dark theme styling
- `public/app.js` - Frontend polling and updates

## Architecture

```
Browser → HTTP → server.js → Unix Socket → ms2d daemon → ECU
```

The server.js uses the ms2_client.js from the ms2d project to communicate
with the daemon over Unix socket, then exposes HTTP endpoints for the browser.

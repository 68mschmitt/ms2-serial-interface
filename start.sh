#!/bin/bash
#
# Startup script for MS2D daemon and dashboard
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MS2D_DIR="$SCRIPT_DIR/work-ms2d-daemon/ms2d"
DASHBOARD_DIR="$SCRIPT_DIR/ms2d-dashboard"

# Default port (can be overridden with --port)
PORT="/dev/ttyUSB0"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down..."
    
    # Kill background jobs
    if [[ -n "$DASHBOARD_PID" ]]; then
        kill "$DASHBOARD_PID" 2>/dev/null
        wait "$DASHBOARD_PID" 2>/dev/null
    fi
    
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start dashboard in background
echo "Starting ms2d-dashboard..."
cd "$DASHBOARD_DIR"
node server.js &
DASHBOARD_PID=$!
echo "Dashboard started (PID: $DASHBOARD_PID)"
echo "Dashboard available at http://localhost:3000"
echo ""

# Start ms2d daemon with infinite retry loop
echo "Starting ms2d daemon (will retry on failure)..."
cd "$MS2D_DIR"

while true; do
    echo "[$(date '+%H:%M:%S')] Starting ms2d..."
    ./ms2d --port "$PORT" --project "$SCRIPT_DIR/projectCfg"
    
    EXIT_CODE=$?
    echo "[$(date '+%H:%M:%S')] ms2d exited with code $EXIT_CODE"
    
    # Check if dashboard is still running
    if ! kill -0 "$DASHBOARD_PID" 2>/dev/null; then
        echo "Dashboard died, restarting..."
        cd "$DASHBOARD_DIR"
        node server.js &
        DASHBOARD_PID=$!
        cd "$MS2D_DIR"
    fi
    
    echo "Retrying in 2 seconds..."
    sleep 2
done

#!/bin/bash
#
# Demo script: Starts ECU simulator with pages, then runs start.sh against it
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECU_SIM_DIR="$SCRIPT_DIR/ecuSim"
SIMULATED_PORT="/tmp/ecuSim"

# Track all child PIDs
ECU_SIM_PID=""
START_SH_PID=""

# Cleanup function - kill all children
cleanup() {
    echo ""
    echo "Shutting down demo..."
    
    # Kill start.sh and its children (dashboard, daemon)
    if [[ -n "$START_SH_PID" ]]; then
        # Kill the process group to get all children
        kill -TERM -"$START_SH_PID" 2>/dev/null
        wait "$START_SH_PID" 2>/dev/null
    fi
    
    # Kill ECU simulator
    if [[ -n "$ECU_SIM_PID" ]]; then
        kill -TERM "$ECU_SIM_PID" 2>/dev/null
        wait "$ECU_SIM_PID" 2>/dev/null
    fi
    
    # Clean up the symlink
    rm -f "$SIMULATED_PORT" 2>/dev/null
    
    echo "Demo stopped."
    exit 0
}

# Trap signals for cleanup
trap cleanup SIGINT SIGTERM EXIT

# Start ECU simulator with pages option
echo "Starting ECU Simulator with pages..."
cd "$ECU_SIM_DIR"
python3 simulator.py --project "$SCRIPT_DIR/projectCfg" --pages pages.bin &
ECU_SIM_PID=$!
echo "ECU Simulator started (PID: $ECU_SIM_PID)"

# Wait for simulator to create the virtual port
echo "Waiting for simulator to initialize..."
for i in {1..10}; do
    if [[ -e "$SIMULATED_PORT" ]]; then
        echo "Simulator ready at $SIMULATED_PORT"
        break
    fi
    sleep 0.5
done

if [[ ! -e "$SIMULATED_PORT" ]]; then
    echo "Error: Simulator failed to create $SIMULATED_PORT"
    exit 1
fi

echo ""

# Run start.sh in background (not exec) so we can clean up
cd "$SCRIPT_DIR"
setsid ./start.sh --port "$SIMULATED_PORT" &
START_SH_PID=$!

# Wait for start.sh to finish (or be killed)
wait "$START_SH_PID" 2>/dev/null

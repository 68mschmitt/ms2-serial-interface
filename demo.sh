#!/bin/bash
#
# Demo script: Starts ECU simulator with pages, then runs start.sh against it
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECU_SIM_DIR="$SCRIPT_DIR/ecuSim"
SIMULATED_PORT="/tmp/ecuSim"

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down demo..."
    
    # Kill ECU simulator
    if [[ -n "$ECU_SIM_PID" ]]; then
        kill "$ECU_SIM_PID" 2>/dev/null
        wait "$ECU_SIM_PID" 2>/dev/null
    fi
    
    exit 0
}

trap cleanup SIGINT SIGTERM

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
    cleanup
    exit 1
fi

echo ""

# Run start.sh with the simulated port
cd "$SCRIPT_DIR"
exec ./start.sh --port "$SIMULATED_PORT"

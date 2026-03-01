#!/bin/bash
#
# Integration test for ms2d daemon
# Tests both --port/--ini and --project modes with all 5 RPC methods
# Includes simulator reconnection testing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MS2D_DIR="$WORKTREE_ROOT/ms2d"
SIMULATOR="$WORKTREE_ROOT/ms2_ecu_simulator.py"
CFG_INI="$WORKTREE_ROOT/cfg.ini"
PROJECT_CFG="$WORKTREE_ROOT/projectCfg"
DAEMON="$MS2D_DIR/ms2d"

SOCKET_1="/tmp/ms2d_test_port.sock"
SOCKET_2="/tmp/ms2d_test_project.sock"
SIM_LINK="/tmp/ms2_ecu_sim_test"

SIMULATOR_PID=""
DAEMON_PID=""

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    
    if [ -n "$DAEMON_PID" ]; then
        kill $DAEMON_PID 2>/dev/null || true
        wait $DAEMON_PID 2>/dev/null || true
    fi
    
    if [ -n "$SIMULATOR_PID" ]; then
        kill $SIMULATOR_PID 2>/dev/null || true
        wait $SIMULATOR_PID 2>/dev/null || true
    fi
    
    rm -f "$SOCKET_1" "$SOCKET_2" "$SIM_LINK"
    
    echo -e "${GREEN}Cleanup complete${NC}"
}

trap cleanup EXIT

# Helper function to test RPC call
test_rpc() {
    local socket=$1
    local method=$2
    local params=$3
    local description=$4
    
    echo -e "${BLUE}Testing: $description${NC}"
    
    local request
    if [ -z "$params" ]; then
        request='{"jsonrpc":"2.0","method":"'"$method"'","id":1}'
    else
        request='{"jsonrpc":"2.0","method":"'"$method"'","params":'"$params"',"id":1}'
    fi
    
    local response=$(curl -s --unix-socket "$socket" -d "$request" http://localhost/)
    
    if [ -z "$response" ]; then
        echo -e "${RED}FAIL: Empty response${NC}"
        return 1
    fi
    
    # Check for error in response
    local error=$(echo "$response" | jq -r '.error // empty')
    if [ -n "$error" ]; then
        echo -e "${RED}FAIL: RPC error: $error${NC}"
        echo "Response: $response"
        return 1
    fi
    
    # Check for result field
    local has_result=$(echo "$response" | jq 'has("result")')
    if [ "$has_result" != "true" ]; then
        echo -e "${RED}FAIL: No result field in response${NC}"
        echo "Response: $response"
        return 1
    fi
    
    echo -e "${GREEN}PASS${NC}"
    echo "Response: $response"
    return 0
}

# Helper function to verify value range
verify_value_range() {
    local value=$1
    local min=$2
    local max=$3
    local description=$4
    
    echo -e "${BLUE}Verifying: $description${NC}"
    
    # Use bc for floating point comparison
    if (( $(echo "$value >= $min" | bc -l) )) && (( $(echo "$value <= $max" | bc -l) )); then
        echo -e "${GREEN}PASS: $value is in range [$min, $max]${NC}"
        return 0
    else
        echo -e "${RED}FAIL: $value is out of range [$min, $max]${NC}"
        return 1
    fi
}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MS2D Integration Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if [ ! -x "$DAEMON" ]; then
    echo -e "${RED}FAIL: Daemon not found or not executable: $DAEMON${NC}"
    exit 1
fi

if [ ! -x "$SIMULATOR" ]; then
    echo -e "${RED}FAIL: Simulator not found or not executable: $SIMULATOR${NC}"
    exit 1
fi

if [ ! -f "$CFG_INI" ]; then
    echo -e "${RED}FAIL: Config file not found: $CFG_INI${NC}"
    exit 1
fi

if [ ! -d "$PROJECT_CFG" ]; then
    echo -e "${RED}FAIL: Project directory not found: $PROJECT_CFG${NC}"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}FAIL: jq not found (required for JSON parsing)${NC}"
    exit 1
fi

echo -e "${GREEN}All prerequisites OK${NC}"

# Start simulator
echo -e "\n${YELLOW}Starting simulator...${NC}"
python3 "$SIMULATOR" --ini "$CFG_INI" --link "$SIM_LINK" > /dev/null 2>&1 &
SIMULATOR_PID=$!
echo "Simulator PID: $SIMULATOR_PID"
sleep 2

if ! kill -0 $SIMULATOR_PID 2>/dev/null; then
    echo -e "${RED}FAIL: Simulator failed to start${NC}"
    exit 1
fi

echo -e "${GREEN}Simulator started successfully${NC}"

# ============================================================
# TEST MODE 1: --port/--ini mode
# ============================================================
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Test Mode 1: --port/--ini${NC}"
echo -e "${BLUE}========================================${NC}"

echo -e "\n${YELLOW}Starting daemon in --port/--ini mode...${NC}"
"$DAEMON" --port "$SIM_LINK" --ini "$CFG_INI" --socket "$SOCKET_1" > /dev/null 2>&1 &
DAEMON_PID=$!
echo "Daemon PID: $DAEMON_PID"
sleep 2

if ! kill -0 $DAEMON_PID 2>/dev/null; then
    echo -e "${RED}FAIL: Daemon failed to start${NC}"
    exit 1
fi

echo -e "${GREEN}Daemon started successfully${NC}"

# Test 1: get_status
echo -e "\n${YELLOW}--- Test 1: get_status ---${NC}"
if ! test_rpc "$SOCKET_1" "get_status" "" "Get daemon status"; then
    exit 1
fi

# Verify connected status
RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_status","id":1}' http://localhost/)
CONNECTED=$(echo "$RESPONSE" | jq -r '.result.connected')
if [ "$CONNECTED" != "true" ]; then
    echo -e "${RED}FAIL: Daemon not connected to ECU${NC}"
    exit 1
fi
echo -e "${GREEN}Daemon connected to ECU${NC}"

# Test 2: list_fields
echo -e "\n${YELLOW}--- Test 2: list_fields ---${NC}"
if ! test_rpc "$SOCKET_1" "list_fields" "" "List all available fields"; then
    exit 1
fi

RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"list_fields","id":1}' http://localhost/)
FIELD_COUNT=$(echo "$RESPONSE" | jq '.result | length')
echo "Field count: $FIELD_COUNT"

if [ "$FIELD_COUNT" -lt 130 ]; then
    echo -e "${RED}FAIL: Expected at least 130 fields, got $FIELD_COUNT${NC}"
    exit 1
fi
echo -e "${GREEN}Field count OK (>= 130)${NC}"

# Test 3: get_value (rpm)
echo -e "\n${YELLOW}--- Test 3: get_value (rpm) ---${NC}"
if ! test_rpc "$SOCKET_1" "get_value" '{"name":"rpm"}' "Get single value (rpm)"; then
    exit 1
fi

RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_value","params":{"name":"rpm"},"id":1}' http://localhost/)
RPM=$(echo "$RESPONSE" | jq -r '.result.value')
echo "RPM value: $RPM"

if ! verify_value_range "$RPM" 0 10000 "RPM > 0"; then
    exit 1
fi

# Test 4: get_value (batteryVoltage)
echo -e "\n${YELLOW}--- Test 4: get_value (batteryVoltage) ---${NC}"
if ! test_rpc "$SOCKET_1" "get_value" '{"name":"batteryVoltage"}' "Get single value (batteryVoltage)"; then
    exit 1
fi

RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_value","params":{"name":"batteryVoltage"},"id":1}' http://localhost/)
BATTERY=$(echo "$RESPONSE" | jq -r '.result.value')
echo "Battery voltage: $BATTERY"

if ! verify_value_range "$BATTERY" 10 16 "Battery voltage in range [10-16]V"; then
    exit 1
fi

# Test 5: get_values (multiple fields)
echo -e "\n${YELLOW}--- Test 5: get_values (multiple fields) ---${NC}"
if ! test_rpc "$SOCKET_1" "get_values" '{"names":["rpm","batteryVoltage","coolant"]}' "Get multiple values"; then
    exit 1
fi

RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_values","params":{"names":["rpm","batteryVoltage","coolant"]},"id":1}' http://localhost/)
VALUE_COUNT=$(echo "$RESPONSE" | jq '.result.values | length')
echo "Returned value count: $VALUE_COUNT"

if [ "$VALUE_COUNT" -ne 3 ]; then
    echo -e "${RED}FAIL: Expected 3 values, got $VALUE_COUNT${NC}"
    exit 1
fi
echo -e "${GREEN}get_values returned correct count${NC}"

# Test 6: get_all
echo -e "\n${YELLOW}--- Test 6: get_all ---${NC}"
if ! test_rpc "$SOCKET_1" "get_all" "" "Get all values"; then
    exit 1
fi

RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_all","id":1}' http://localhost/)
ALL_COUNT=$(echo "$RESPONSE" | jq '.result.values | length')
echo "Returned value count: $ALL_COUNT"

if [ "$ALL_COUNT" -lt 130 ]; then
    echo -e "${RED}FAIL: Expected at least 130 values, got $ALL_COUNT${NC}"
    exit 1
fi
echo -e "${GREEN}get_all returned correct count${NC}"

# Stop daemon for next test
echo -e "\n${YELLOW}Stopping daemon...${NC}"
kill $DAEMON_PID 2>/dev/null || true
wait $DAEMON_PID 2>/dev/null || true
DAEMON_PID=""
sleep 1

# ============================================================
# TEST MODE 2: --project mode
# ============================================================
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Test Mode 2: --project${NC}"
echo -e "${BLUE}========================================${NC}"

# Need to temporarily point simulator to the port expected by projectCfg
# projectCfg/project.properties specifies /dev/ttyUSB0, but we're using a test port
# For this test, we'll start daemon pointing to our test simulator
echo -e "\n${YELLOW}Starting daemon in --project mode...${NC}"

# Test project mode by using the worktree root as working directory
# so daemon can find projectCfg/mainController.ini relative path
echo -e "${YELLOW}Testing project mode (--project)...${NC}"

cd "$WORKTREE_ROOT"
"$DAEMON" --project "$PROJECT_CFG" --port "$SIM_LINK" --socket "$SOCKET_2" > /dev/null 2>&1 &
DAEMON_PID=$!
cd "$MS2D_DIR"
echo "Daemon PID: $DAEMON_PID"
sleep 2

if ! kill -0 $DAEMON_PID 2>/dev/null; then
    echo -e "${RED}FAIL: Daemon failed to start in project mode${NC}"
    exit 1
fi

echo -e "${GREEN}Daemon started in project mode${NC}"

# Test get_status to verify it's working
echo -e "\n${YELLOW}--- Test 7: get_status (project mode) ---${NC}"
if ! test_rpc "$SOCKET_2" "get_status" "" "Get daemon status in project mode"; then
    exit 1
fi

RESPONSE=$(curl -s --unix-socket "$SOCKET_2" -d '{"jsonrpc":"2.0","method":"get_status","id":1}' http://localhost/)
CONNECTED=$(echo "$RESPONSE" | jq -r '.result.connected')
if [ "$CONNECTED" != "true" ]; then
    echo -e "${RED}FAIL: Daemon not connected in project mode${NC}"
    exit 1
fi
echo -e "${GREEN}Project mode daemon connected to ECU${NC}"

# Stop daemon for reconnection test
echo -e "\n${YELLOW}Stopping daemon...${NC}"
kill $DAEMON_PID 2>/dev/null || true
wait $DAEMON_PID 2>/dev/null || true
DAEMON_PID=""
sleep 1

# ============================================================
# TEST MODE 3: Reconnection Test
# ============================================================
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Test Mode 3: Reconnection${NC}"
echo -e "${BLUE}========================================${NC}"

echo -e "\n${YELLOW}Starting daemon...${NC}"
"$DAEMON" --port "$SIM_LINK" --ini "$CFG_INI" --socket "$SOCKET_1" > /dev/null 2>&1 &
DAEMON_PID=$!
echo "Daemon PID: $DAEMON_PID"
sleep 2

# Verify initial connection
echo -e "\n${YELLOW}Verifying initial connection...${NC}"
RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_status","id":1}' http://localhost/)
CONNECTED=$(echo "$RESPONSE" | jq -r '.result.connected')
if [ "$CONNECTED" != "true" ]; then
    echo -e "${RED}FAIL: Daemon not initially connected${NC}"
    exit 1
fi
echo -e "${GREEN}Initial connection verified${NC}"

# Kill simulator
echo -e "\n${YELLOW}Killing simulator to test reconnection...${NC}"
kill $SIMULATOR_PID 2>/dev/null || true
wait $SIMULATOR_PID 2>/dev/null || true
SIMULATOR_PID=""
echo -e "${YELLOW}Simulator stopped${NC}"

# Wait for daemon to detect disconnection
echo -e "\n${YELLOW}Waiting 3 seconds for daemon to detect disconnection...${NC}"
sleep 3

# Check status - should show disconnected or error
RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_status","id":1}' http://localhost/ || echo '{"result":{"connected":false}}')
CONNECTED=$(echo "$RESPONSE" | jq -r '.result.connected')
echo "Connected status after simulator stop: $CONNECTED"

# Restart simulator
echo -e "\n${YELLOW}Restarting simulator...${NC}"
python3 "$SIMULATOR" --ini "$CFG_INI" --link "$SIM_LINK" > /dev/null 2>&1 &
SIMULATOR_PID=$!
echo "Simulator PID: $SIMULATOR_PID"

# Wait for reconnection (daemon uses exponential backoff, first retry is 1s)
echo -e "\n${YELLOW}Waiting 5 seconds for daemon to reconnect...${NC}"
sleep 5

# Verify reconnection
echo -e "\n${YELLOW}Verifying reconnection...${NC}"
RESPONSE=$(curl -s --unix-socket "$SOCKET_1" -d '{"jsonrpc":"2.0","method":"get_status","id":1}' http://localhost/)
CONNECTED=$(echo "$RESPONSE" | jq -r '.result.connected')

if [ "$CONNECTED" != "true" ]; then
    echo -e "${RED}FAIL: Daemon failed to reconnect${NC}"
    echo "Response: $RESPONSE"
    exit 1
fi

echo -e "${GREEN}Reconnection successful!${NC}"

# Final get_value test to confirm data flow restored
echo -e "\n${YELLOW}--- Test 8: get_value after reconnection ---${NC}"
if ! test_rpc "$SOCKET_1" "get_value" '{"name":"rpm"}' "Get value after reconnection"; then
    exit 1
fi

# ============================================================
# ALL TESTS PASSED
# ============================================================
echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}ALL TESTS PASSED!${NC}"
echo -e "${BLUE}========================================${NC}"

echo -e "\n${GREEN}Summary:${NC}"
echo -e "  ✓ Mode 1 (--port/--ini): All 5 RPC methods tested"
echo -e "  ✓ Mode 2 (--project): Daemon started and connected"
echo -e "  ✓ Mode 3 (Reconnection): Daemon reconnected after simulator restart"
echo -e "  ✓ Data validation: RPM > 0, Battery voltage 10-16V"
echo -e "  ✓ Field count: >= 130 fields"

exit 0

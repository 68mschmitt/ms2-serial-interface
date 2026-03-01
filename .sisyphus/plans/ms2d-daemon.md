# MS2 Serial Decoder Daemon (ms2d) - C Implementation

## TL;DR

> **Quick Summary**: Build a C daemon that parses TunerStudio INI files, communicates with Megasquirt 2 ECU via serial, and exposes decoded real-time engine data through JSON-RPC over Unix socket. Supports auto-configuration from TunerStudio project directories.
> 
> **Deliverables**:
> - `ms2d` daemon binary (C)
> - `libms2client` C client library
> - `ms2_client.js` Node.js client module
> - Makefile for building
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 → Task 3 → Task 5 → Task 7 → Task 8 → Task 10

---

## Context

### Original Request
Create a C-based serial decoder daemon that:
1. Parses TunerStudio INI files for OutputChannel definitions
2. Communicates with MS2 ECU via newserial protocol
3. Exposes decoded data via RPC to other processes (JSON-RPC over Unix socket)

### Interview Summary
**Key Discussions**:
- RPC mechanism: Unix Socket + JSON-RPC (confirmed)
- Client languages: C and JavaScript/Node (confirmed)
- Simulation: Not built-in, use existing `ms2_ecu_simulator.py`
- Baud rate: Default 115200, but read from project.properties if available
- Node.js client: Pure JavaScript (no native addon)
- Data freshness: Include `last_poll_timestamp_ms` in responses
- Error recovery: Retry indefinitely on serial disconnect
- **Project directory mode**: Auto-discover settings from TunerStudio project

**Research Findings**:
- Reference implementation exists: `ms2_ini_dash.py` (577 lines)
- INI file at `cfg.ini` has OutputChannels at line 5019, 134 fields parsed
- ECU signature: "MS2Extra comms330NP"
- Block size: 209 bytes (ochBlockSize)
- INI has `#XX|` line prefixes that must be stripped
- Protocol: 2-byte BE length + payload + 4-byte BE CRC32

### Metis Review
**Identified Gaps** (addressed):
- INI location confirmed: `cfg.ini` line 5019 has OutputChannels
- Baud rate: hardcoded 115200
- Staleness tracking: include timestamp in responses
- Error recovery: retry indefinitely with backoff
- Node.js: pure JS implementation

---

## Work Objectives

### Core Objective
Create a robust, production-ready C daemon that decodes Megasquirt 2 ECU data and makes it available to other processes via JSON-RPC. Support both explicit configuration and auto-discovery from TunerStudio project directories.

### Concrete Deliverables
- `ms2d/` directory with complete C project
- `ms2d` binary that runs as daemon
- `libms2client.a` static library + `ms2_client.h` header
- `ms2_client.js` Node.js module
- `Makefile` with `all`, `clean`, `install` targets

### Definition of Done
- [ ] `./ms2d --project ./projectCfg/` auto-configures from TunerStudio project
- [ ] `./ms2d --port /tmp/ms2_ecu_sim --ini cfg.ini` works with explicit config
- [ ] `curl --unix-socket /tmp/ms2d.sock` returns valid JSON-RPC responses
- [ ] C client library compiles and links against daemon
- [ ] Node.js client can connect and retrieve values
- [ ] No memory leaks (valgrind clean)

### Must Have
- INI parser that extracts OutputChannels (scalar and bits types)
- Project directory parser (project.properties, custom.ini merging)
- Newserial protocol implementation (Q and A commands)
- JSON-RPC server with 5 methods: get_value, get_values, get_all, list_fields, get_status
- Thread-safe shared state with mutex
- Signal handling (SIGTERM, SIGINT for clean shutdown)
- Reconnection logic with exponential backoff

### Must NOT Have (Guardrails)
- **No write commands to ECU** (read-only daemon)
- **No HTTP/WebSocket/TCP interfaces** (Unix socket only)
- **No D-Bus integration** (keep it simple)
- **No systemd unit file** (user can create)
- **No multiple ECU support** (single serial connection)
- **No INI expression evaluation** (extract first number only)
- **No hot-reload of INI** (requires restart)
- **No native Node.js addon** (pure JS only)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (existing Python simulator)
- **Automated tests**: Tests-after (C doesn't have built-in test framework)
- **Framework**: Shell scripts with curl + jq for RPC testing

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Daemon**: Use Bash to start daemon, curl to test RPC, check exit codes
- **C client**: Compile test program, run against daemon, verify output
- **Node.js client**: Run with node, verify JSON output

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - headers, build system, utilities):
├── Task 1: Project structure + Makefile + main headers [quick]
├── Task 2: Utility functions (CRC32, timestamps, error strings) [quick]
└── Task 3: cJSON vendoring or pkg-config setup [quick]

Wave 2 (Core modules - can parallelize):
├── Task 4: Project directory parser (project.properties, custom.ini) [unspecified-high]
├── Task 5: INI parser implementation [deep]
├── Task 6: Serial communication (newserial protocol) [deep]
└── Task 7: Data decoder implementation [unspecified-high]

Wave 3 (Integration):
├── Task 8: RPC server (Unix socket + JSON-RPC) [deep]
├── Task 9: Main daemon loop + signal handling [unspecified-high]
└── Task 10: Integration testing with simulator [unspecified-high]

Wave 4 (Clients):
├── Task 11: C client library [unspecified-high]
└── Task 12: Node.js client module [quick]

Wave FINAL (Verification):
├── F1: Full integration test [deep]
├── F2: Memory leak check with valgrind [unspecified-high]
├── F3: Code review [unspecified-high]
└── F4: Documentation review [quick]
```

### Dependency Matrix
| Task | Depends On | Blocks |
|------|------------|--------|
| 1 | - | 2,3,4,5,6,7,8,9 |
| 2 | 1 | 6,7,8 |
| 3 | 1 | 8 |
| 4 | 1 | 5,9 |
| 5 | 1,4 | 7,9 |
| 6 | 1,2 | 9 |
| 7 | 1,2,5 | 9 |
| 8 | 1,2,3 | 9 |
| 9 | 4,5,6,7,8 | 10,11,12 |
| 10 | 9 | F1-F4 |
| 11 | 9 | F1 |
| 12 | 9 | F1 |

### Agent Dispatch Summary
- **Wave 1**: 3 tasks → `quick` (simple scaffolding)
- **Wave 2**: 4 tasks → `deep`/`unspecified-high` (core algorithm work)
- **Wave 3**: 3 tasks → `deep`/`unspecified-high` (integration)
- **Wave 4**: 2 tasks → `unspecified-high`/`quick`
- **Wave FINAL**: 4 tasks → verification agents

---

## TODOs

---

- [ ] 1. Project Structure + Makefile + Headers

  **What to do**:
  - Create directory structure: `ms2d/{src,include,clients}`
  - Create `Makefile` with targets: `all`, `clean`, `install`, `ms2d`, `libms2client.a`
  - Use `-Wall -Wextra -pthread` flags
  - Create main header `include/ms2d.h` with all type definitions (copy from draft)
  - Create module headers: `ini_parser.h`, `serial_comm.h`, `decoder.h`, `rpc_server.h`, `project_parser.h`
  - Each header should have include guards and function prototypes

  **Must NOT do**:
  - Don't implement functions yet (headers only)
  - Don't add autoconf/cmake (simple Makefile only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (foundation)
  - **Blocks**: Tasks 2-9

  **References**:
  - `.sisyphus/drafts/ms2d-daemon.md:93-115` - File structure spec
  - `ms2_ini_dash.py:1-50` - Data types and constants reference

  **Acceptance Criteria**:
  - [ ] `ls ms2d/include/*.h` returns 6 header files
  - [ ] `make -n` in ms2d/ shows valid build plan (no errors)
  - [ ] Headers compile: `gcc -c -I ms2d/include -x c /dev/null` succeeds

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Makefile dry-run succeeds
    Tool: Bash
    Preconditions: ms2d/ directory exists with Makefile
    Steps:
      1. cd ms2d && make -n
      2. Check exit code is 0
      3. Output contains "gcc" commands
    Expected Result: Exit code 0, output shows compilation commands
    Evidence: .sisyphus/evidence/task-1-makefile-dryrun.txt

  Scenario: Headers have include guards
    Tool: Bash
    Preconditions: All .h files exist
    Steps:
      1. grep -l "#ifndef.*_H" ms2d/include/*.h | wc -l
      2. Should equal number of header files
    Expected Result: All 6 headers have include guards
    Evidence: .sisyphus/evidence/task-1-include-guards.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): add project structure and headers`
  - Files: `ms2d/Makefile`, `ms2d/include/*.h`

---

- [ ] 2. Utility Functions (CRC32, timestamps, errors)

  **What to do**:
  - Create `src/util.c` with:
    - `uint32_t ms2d_crc32(const uint8_t *data, size_t len)` - Standard CRC32
    - `uint64_t ms2d_timestamp_ms(void)` - Milliseconds since epoch
    - `const char *ms2d_error_str(ms2d_error_t err)` - Error code to string
    - `int ms2d_field_size(ms2d_data_type_t type)` - Return byte size for type
  - CRC32 must match `binascii.crc32` from Python (standard polynomial 0xEDB88320)
  - Use `clock_gettime(CLOCK_REALTIME, ...)` for timestamps

  **Must NOT do**:
  - Don't use external CRC library (implement directly)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1)
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Tasks 5, 6, 7
  - **Blocked By**: Task 1

  **References**:
  - `ms2_ini_dash.py:177-179` - CRC32 implementation reference
  - Standard CRC32 polynomial: 0xEDB88320

  **Acceptance Criteria**:
  - [ ] `ms2d_crc32("123456789", 9)` returns `0xCBF43926` (standard test vector)
  - [ ] Compiles without warnings: `gcc -Wall -c src/util.c`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: CRC32 matches Python implementation
    Tool: Bash
    Preconditions: util.c compiled into test program
    Steps:
      1. Create test program that prints ms2d_crc32("123456789", 9)
      2. Compile and run: gcc -o crc_test crc_test.c src/util.c && ./crc_test
      3. Compare output to Python: python3 -c "import binascii; print(hex(binascii.crc32(b'123456789') & 0xFFFFFFFF))"
    Expected Result: Both output 0xcbf43926
    Evidence: .sisyphus/evidence/task-2-crc32-test.txt

  Scenario: Timestamp returns reasonable value
    Tool: Bash
    Preconditions: Test program exists
    Steps:
      1. Call ms2d_timestamp_ms() twice with 100ms sleep between
      2. Verify difference is 90-110ms
    Expected Result: Timestamps differ by ~100ms
    Evidence: .sisyphus/evidence/task-2-timestamp-test.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): add utility functions (CRC32, timestamps)`
  - Files: `ms2d/src/util.c`

---

- [ ] 3. cJSON Integration

  **What to do**:
  - Download cJSON (single header + source): https://github.com/DaveGamble/cJSON
  - Place `cJSON.h` and `cJSON.c` in `ms2d/vendor/cjson/`
  - Update Makefile to compile cJSON as part of build
  - Verify it compiles with project flags

  **Must NOT do**:
  - Don't use system-installed cJSON (vendor it for portability)
  - Don't modify cJSON source

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1)
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Task 7
  - **Blocked By**: Task 1

  **References**:
  - https://github.com/DaveGamble/cJSON/blob/master/cJSON.h
  - https://github.com/DaveGamble/cJSON/blob/master/cJSON.c

  **Acceptance Criteria**:
  - [ ] `ms2d/vendor/cjson/cJSON.h` exists
  - [ ] `gcc -c ms2d/vendor/cjson/cJSON.c` compiles without errors

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: cJSON compiles cleanly
    Tool: Bash
    Preconditions: cJSON files downloaded
    Steps:
      1. gcc -Wall -c ms2d/vendor/cjson/cJSON.c -o /tmp/cjson.o
      2. Check exit code
    Expected Result: Exit code 0, no warnings
    Evidence: .sisyphus/evidence/task-3-cjson-compile.txt

  Scenario: cJSON creates valid JSON
    Tool: Bash
    Preconditions: Test program using cJSON
    Steps:
      1. Create minimal test that creates {"test": 42} with cJSON
      2. Compile and run, pipe to jq for validation
    Expected Result: jq parses output successfully
    Evidence: .sisyphus/evidence/task-3-cjson-test.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): vendor cJSON library`
  - Files: `ms2d/vendor/cjson/cJSON.h`, `ms2d/vendor/cjson/cJSON.c`

---

- [ ] 4. Project Directory Parser (project.properties + custom.ini)

  **What to do**:
  - Create `src/project_parser.c` implementing:
    - `ms2d_error_t ms2d_project_parse(const char *project_dir, ms2d_config_t *config)`
    - Parse `project.properties` for connection settings:
      - Extract `Com Port` from key containing `Com\ Port=` (e.g., `/dev/ttyUSB0`)
      - Extract `Baud Rate` from key containing `Baud\ Rate=` (e.g., `115200`)
      - Extract `ecuConfigFile` to get INI filename (e.g., `mainController.ini`)
      - Extract `canId` for multi-ECU setups (default: 0)
      - Extract `ecuSettings` flags (e.g., `FAHRENHEIT|CAN_COMMANDS`)
    - Parse `custom.ini` for user-defined OutputChannels:
      - Find `[OutputChannels]` section
      - Parse any user-added scalar/bits fields
      - These get MERGED with base INI fields (custom overrides base)
    - Handle the `#XX|` line prefix format (same as main INI)
    - Store results in config struct:
      ```c
      typedef struct {
        char serial_port[256];
        int baud_rate;
        char ini_file[256];
        int can_id;
        bool fahrenheit;
        bool can_commands;
        // Custom fields from custom.ini
        ms2d_field_t *custom_fields;
        int num_custom_fields;
      } ms2d_config_t;
      ```

  **Must NOT do**:
  - Don't parse all project.properties keys (only connection-relevant ones)
  - Don't fail if custom.ini has no OutputChannels (it's optional)
  - Don't require project directory mode (--port/--ini still works)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - Reason: File parsing with specific key extraction patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2)
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 7)
  - **Blocks**: Tasks 5 (INI parser needs config), 9 (main uses config)
  - **Blocked By**: Task 1

  **References**:
  - `projectCfg/project.properties` - Example file with real settings
  - Key patterns to extract:
    - `CommSettingMSCommDriver.RS232\ Serial\ InterfaceCom\ Port=/dev/ttyUSB0`
    - `CommSettingMSCommDriver.RS232\ Serial\ InterfaceBaud\ Rate=115200`
    - `ecuConfigFile=mainController.ini`
    - `ecuSettings=CAN_COMMANDS|FAHRENHEIT|...`
    - `canId=0`
  - `projectCfg/custom.ini` - User extension file

  **Acceptance Criteria**:
  - [ ] `ms2d_project_parse("./projectCfg", &config)` succeeds
  - [ ] `config.serial_port` equals `/dev/ttyUSB0`
  - [ ] `config.baud_rate` equals `115200`
  - [ ] `config.ini_file` equals `mainController.ini`
  - [ ] `config.fahrenheit` is `true` (extracted from ecuSettings)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Parse project.properties extracts serial port
    Tool: Bash
    Preconditions: project_parser.c compiled into test program
    Steps:
      1. Create test that calls ms2d_project_parse("./projectCfg", &config)
      2. Print config.serial_port
      3. Verify equals "/dev/ttyUSB0"
    Expected Result: Serial port extracted correctly
    Evidence: .sisyphus/evidence/task-4-serial-port.txt

  Scenario: Parse ecuSettings flags
    Tool: Bash
    Preconditions: Test program exists
    Steps:
      1. Parse projectCfg directory
      2. Check config.fahrenheit == true
      3. Check config.can_commands == true (from CAN_COMMANDS flag)
    Expected Result: Both flags correctly extracted
    Evidence: .sisyphus/evidence/task-4-ecu-settings.txt

  Scenario: Missing custom.ini OutputChannels doesn't fail
    Tool: Bash
    Preconditions: custom.ini exists but has empty OutputChannels
    Steps:
      1. Parse projectCfg directory (custom.ini has empty OutputChannels)
      2. Verify parse succeeds
      3. Verify config.num_custom_fields == 0
    Expected Result: Parse succeeds with zero custom fields
    Evidence: .sisyphus/evidence/task-4-empty-custom.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): add project directory parser`
  - Files: `ms2d/src/project_parser.c`, `ms2d/include/project_parser.h`


- [ ] 5. INI Parser Implementation

  **What to do**:
  - Create `src/ini_parser.c` implementing:
    - `ms2d_error_t ms2d_ini_parse(const char *path, ms2d_state_t *state)`
    - `ms2d_error_t ms2d_ini_merge_custom(ms2d_state_t *state, const ms2d_field_t *custom, int count)` - Merge custom.ini fields
    - Strip `#XX|` prefix from each line (2 chars + pipe)
    - Handle `#if`/`#else`/`#endif` conditionals (check config for FAHRENHEIT/CAN_COMMANDS)
    - Parse `[OutputChannels]` section only
    - Extract `ochBlockSize` value
    - Extract `signature` from `[TunerStudio]` section
    - Parse scalar fields: `name = scalar, TYPE, OFFSET, "units", scale, translate`
    - Parse bits fields: `name = bits, TYPE, OFFSET, [low:high], ...`
    - Skip calculated fields (contain `{`)
  - Store results in `state->fields[]`, `state->num_fields`, `state->outpc_size`
  - Use formula from INI: `userValue = (msValue + translate) * scale`

  **Must NOT do**:
  - Don't parse Constants, Curves, or other sections
  - Don't evaluate expressions (extract first number only)
  - Don't use external INI parsing library

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - Reason: Complex parsing logic with multiple edge cases

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2)
  - **Parallel Group**: Wave 2 (with Tasks 4, 6, 7)
  - **Blocks**: Tasks 7, 9
  - **Blocked By**: Tasks 1, 4

  **References**:
  - `ms2_ini_dash.py:74-154` - Python INI parser implementation
  - `cfg.ini:5019-5220` - OutputChannels section example
  - `ms2_ini_dash.py:84` - Line prefix stripping: `re.sub(r"^#[A-Z]{2}\|", "", ...)`

  **Acceptance Criteria**:
  - [ ] Parses `cfg.ini` and finds 130+ fields
  - [ ] `rpm` field: offset=6, type=U16, scale=1.0
  - [ ] `batteryVoltage` field: offset=26, type=S16, scale=0.1
  - [ ] `outpc_size` = 209
  - [ ] Merging custom fields works (custom overrides base)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Parser extracts correct field count
    Tool: Bash
    Preconditions: ini_parser.c compiled into test program
    Steps:
      1. Create test that calls ms2d_ini_parse("cfg.ini", &state)
      2. Print state.num_fields
      3. Verify >= 130
    Expected Result: Field count >= 130
    Evidence: .sisyphus/evidence/task-5-field-count.txt

  Scenario: Key fields have correct offsets
    Tool: Bash
    Preconditions: Test program with field lookup
    Steps:
      1. Find "rpm" field, verify offset=6, type=U16
      2. Find "batteryVoltage" field, verify offset=26
      3. Find "afr1" field, verify offset=28
    Expected Result: All three fields match expected values
    Evidence: .sisyphus/evidence/task-5-field-offsets.txt

  Scenario: Block size extracted correctly
    Tool: Bash
    Preconditions: Parser completed
    Steps:
      1. Parse cfg.ini
      2. Print state.outpc_size
    Expected Result: outpc_size == 209
    Evidence: .sisyphus/evidence/task-5-block-size.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): implement INI parser for OutputChannels`
  - Files: `ms2d/src/ini_parser.c`

---

- [ ] 6. Serial Communication (newserial protocol)

  **What to do**:
  - Create `src/serial_comm.c` implementing:
    - `ms2d_error_t ms2d_serial_open(ms2d_state_t *state)` - Open and configure port
    - `ms2d_error_t ms2d_serial_close(ms2d_state_t *state)` - Close port
    - `ms2d_error_t ms2d_serial_send(ms2d_state_t *state, const uint8_t *cmd, size_t len, uint8_t *response, size_t *resp_len)` - Send command, receive response
    - `ms2d_error_t ms2d_serial_query_signature(ms2d_state_t *state)` - Send 'Q', store signature
    - `ms2d_error_t ms2d_serial_poll_outpc(ms2d_state_t *state)` - Send 'A', store in outpc_buffer
  - Protocol format:
    - Request: `[2-byte BE length][payload][4-byte BE CRC32]`
    - Response: `[2-byte BE length][flag byte][data][4-byte BE CRC32]`
  - Configure serial: 115200 baud, 8N1, no flow control
  - Use `select()` for timeout handling
  - Verify CRC32 on responses

  **Must NOT do**:
  - Don't implement write commands (read-only)
  - Don't implement CAN passthrough

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - Reason: Low-level serial I/O with protocol state machine

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2)
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 7)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `ms2_ini_dash.py:177-219` - Python newserial implementation
  - `ms2_ecu_simulator.py:261-295` - Protocol from ECU side
  - `serial.pdf` - Official protocol documentation

  **Acceptance Criteria**:
  - [ ] Opens `/tmp/ms2_ecu_sim` (virtual port from simulator)
  - [ ] 'Q' command returns signature containing "MS2Extra"
  - [ ] 'A' command returns 209 bytes of data
  - [ ] CRC validation rejects corrupted responses

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Connect to simulator and query signature
    Tool: Bash
    Preconditions: ms2_ecu_simulator.py running in background
    Steps:
      1. Start simulator: python3 ms2_ecu_simulator.py --ini cfg.ini &
      2. Wait 1 second for startup
      3. Run serial test program against /tmp/ms2_ecu_sim
      4. Call ms2d_serial_query_signature()
      5. Verify signature contains "MS2Extra"
    Expected Result: Signature matches expected value
    Evidence: .sisyphus/evidence/task-6-signature.txt

  Scenario: Poll outpc returns correct size
    Tool: Bash
    Preconditions: Simulator running, serial connected
    Steps:
      1. Call ms2d_serial_poll_outpc()
      2. Check state.outpc_len == 209
    Expected Result: outpc_len == 209
    Evidence: .sisyphus/evidence/task-6-outpc-size.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): implement newserial protocol communication`
  - Files: `ms2d/src/serial_comm.c`

---

- [ ] 7. Data Decoder Implementation

  **What to do**:
  - Create `src/decoder.c` implementing:
    - `double ms2d_decode_field(const ms2d_state_t *state, const ms2d_field_t *field)` - Decode single field
    - `ms2d_error_t ms2d_decode_all(const ms2d_state_t *state, ms2d_value_t *values, int *count)` - Decode all fields
    - `const ms2d_field_t *ms2d_find_field(const ms2d_state_t *state, const char *name)` - Lookup by name
  - Decoding formula: `userValue = (msValue + translate) * scale`
  - Handle data types: U08, S08, U16, S16, U32, S32 (little-endian)
  - Handle bits fields: extract bit range, no scale/translate
  - Thread-safe: functions take const state, don't modify

  **Must NOT do**:
  - Don't modify state (read-only decoder)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2)
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 1, 2, 5

  **References**:
  - `ms2_ini_dash.py:284-306` - Python decode_field implementation
  - `ms2_ecu_simulator.py:206-231` - Encoding (reverse operation)

  **Acceptance Criteria**:
  - [ ] Decodes rpm=2500 correctly from raw bytes
  - [ ] Decodes batteryVoltage=14.1 correctly (with scale 0.1)
  - [ ] Bits fields extract correct bit ranges

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Decode RPM from known bytes
    Tool: Bash
    Preconditions: Decoder compiled, test program exists
    Steps:
      1. Create outpc buffer with bytes [0xC4, 0x09] at offset 6 (2500 LE)
      2. Call ms2d_decode_field for "rpm"
      3. Verify result == 2500.0
    Expected Result: Decoded value == 2500.0
    Evidence: .sisyphus/evidence/task-7-decode-rpm.txt

  Scenario: Decode battery voltage with scale
    Tool: Bash
    Preconditions: Test program with known data
    Steps:
      1. Create buffer with 141 (0x8D, 0x00) at offset 26
      2. Call ms2d_decode_field for "batteryVoltage"
      3. Verify result == 14.1 (141 * 0.1)
    Expected Result: Decoded value == 14.1
    Evidence: .sisyphus/evidence/task-7-decode-battery.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): implement data decoder`
  - Files: `ms2d/src/decoder.c`

---

- [ ] 8. RPC Server (Unix Socket + JSON-RPC)

  **What to do**:
  - Create `src/rpc_server.c` implementing:
    - `ms2d_error_t ms2d_rpc_init(ms2d_state_t *state)` - Create Unix socket, bind, listen
    - `ms2d_error_t ms2d_rpc_accept(ms2d_state_t *state)` - Accept new client (non-blocking)
    - `ms2d_error_t ms2d_rpc_handle(ms2d_state_t *state, int client_fd)` - Handle one request
    - `void ms2d_rpc_shutdown(ms2d_state_t *state)` - Close socket, unlink file
  - Implement 5 JSON-RPC methods:
    1. `get_value` - Single field: `{"method":"get_value","params":{"field":"rpm"},"id":1}`
    2. `get_values` - Multiple fields: `{"method":"get_values","params":{"fields":["rpm","map"]},"id":2}`
    3. `get_all` - All fields with timestamp
    4. `list_fields` - Array of field names
    5. `get_status` - Connected status, signature, request count
  - All responses include `last_poll_timestamp_ms`
  - Use cJSON for JSON parsing/generation
  - Handle errors with JSON-RPC error objects: `{"error":{"code":-32601,"message":"Method not found"},"id":1}`
  - Remove socket file before bind (handle stale socket)

  **Must NOT do**:
  - Don't implement batch requests
  - Don't implement notifications (request/response only)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - Reason: Multiple RPC methods with JSON handling

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2, late start)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 1, 2, 3

  **References**:
  - `.sisyphus/drafts/ms2d-daemon.md:40-80` - JSON-RPC protocol spec
  - JSON-RPC 2.0 spec: https://www.jsonrpc.org/specification

  **Acceptance Criteria**:
  - [ ] Socket created at `/tmp/ms2d.sock`
  - [ ] `curl --unix-socket /tmp/ms2d.sock -d '{"method":"list_fields","id":1}'` returns JSON array
  - [ ] Invalid method returns error object with code -32601

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: list_fields returns field names
    Tool: Bash
    Preconditions: RPC server running (can be standalone test)
    Steps:
      1. Start test RPC server on /tmp/ms2d_test.sock
      2. curl --unix-socket /tmp/ms2d_test.sock -d '{"method":"list_fields","id":1}'
      3. Pipe to jq '.result | length'
      4. Verify count > 50
    Expected Result: Array with 130+ field names
    Evidence: .sisyphus/evidence/task-8-list-fields.txt

  Scenario: get_value returns correct structure
    Tool: Bash
    Preconditions: RPC server with mock data
    Steps:
      1. curl --unix-socket /tmp/ms2d_test.sock -d '{"method":"get_value","params":{"field":"rpm"},"id":2}'
      2. Verify response has .result.name, .result.value, .result.units
    Expected Result: Valid JSON with name/value/units
    Evidence: .sisyphus/evidence/task-8-get-value.txt

  Scenario: Invalid method returns error
    Tool: Bash
    Preconditions: RPC server running
    Steps:
      1. curl --unix-socket /tmp/ms2d_test.sock -d '{"method":"invalid","id":3}'
      2. Check for .error.code in response
    Expected Result: Response contains error.code == -32601
    Evidence: .sisyphus/evidence/task-8-error-handling.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): implement JSON-RPC server over Unix socket`
  - Files: `ms2d/src/rpc_server.c`

---

- [ ] 9. Main Daemon Loop + Signal Handling

  **What to do**:
  - Create `src/main.c` implementing:
    - Argument parsing: `--port`, `--ini`, `--socket`, `--verbose`, `--help`, `--project`
    - **NEW**: `--project <dir>` mode that auto-loads from TunerStudio project directory
    - If `--project` given: parse project.properties for port/baud, use ecuConfigFile for INI
    - Signal handlers for SIGTERM, SIGINT (set `state.running = false`)
    - Main loop:
      1. Poll ECU at configured rate (default 10Hz)
      2. Accept new RPC clients (non-blocking)
      3. Handle pending RPC requests
      4. Sleep remaining time in loop iteration
    - Reconnection logic: If serial fails, retry with exponential backoff (1s, 2s, 4s, max 30s)
    - Thread architecture:
      - Main thread: RPC server accept/handle
      - Worker thread: Serial polling loop
    - Mutex protection for `outpc_buffer` and `outpc_len`
  - Default socket path: `/tmp/ms2d.sock`
  - Default poll rate: 10 Hz

  **Must NOT do**:
  - Don't daemonize (let systemd/screen handle that)
  - Don't write PID file

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on all modules)
  - **Blocks**: Tasks 10, 11, 12
  - **Blocked By**: Tasks 4, 5, 6, 7, 8

  **References**:
  - `ms2_ini_dash.py:443-487` - Python main loop reference
  - POSIX signal handling best practices

  **Acceptance Criteria**:
  - [ ] `./ms2d --help` prints usage (shows --project option)
  - [ ] `./ms2d --port /tmp/ms2_ecu_sim --ini cfg.ini` connects and runs
  - [ ] `./ms2d --project ./projectCfg/` auto-configures and connects
  - [ ] Ctrl+C causes clean shutdown (no zombie processes)
  - [ ] Serial disconnect triggers reconnection attempts

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Daemon starts and connects to simulator
    Tool: Bash
    Preconditions: Simulator running
    Steps:
      1. python3 ms2_ecu_simulator.py --ini cfg.ini &
      2. sleep 1
      3. ./ms2d --port /tmp/ms2_ecu_sim --ini cfg.ini --socket /tmp/ms2d.sock &
      4. sleep 2
      5. curl --unix-socket /tmp/ms2d.sock -d '{"method":"get_status","id":1}'
      6. Verify .result.connected == true
    Expected Result: Status shows connected=true
    Evidence: .sisyphus/evidence/task-9-daemon-connect.txt

  Scenario: Clean shutdown on SIGTERM
    Tool: Bash
    Preconditions: Daemon running
    Steps:
      1. Start daemon in background, capture PID
      2. sleep 1
      3. kill -TERM $PID
      4. wait $PID
      5. Check exit code is 0
      6. Verify /tmp/ms2d.sock is removed
    Expected Result: Clean exit, socket cleaned up
    Evidence: .sisyphus/evidence/task-9-clean-shutdown.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): implement main daemon with signal handling`
  - Files: `ms2d/src/main.c`

---

- [ ] 10. Integration Testing with Simulator

  **What to do**:
  - Create `ms2d/test/integration_test.sh` script that:
    1. Starts simulator in background
    2. Starts daemon in background (test both --port/--ini AND --project modes)
    3. Runs curl tests for all 5 RPC methods
    4. Verifies response structure and values
    5. Cleans up processes
  - Test all RPC methods end-to-end
  - Verify data values are reasonable (RPM > 0, battery ~14V, etc.)
  - Test reconnection by killing and restarting simulator
  - **NEW**: Test project directory mode with ./projectCfg/

  **Must NOT do**:
  - Don't require manual verification

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: F1-F4
  - **Blocked By**: Task 9

  **References**:
  - All previous task QA scenarios
  - `projectCfg/` directory for project mode testing

  **Acceptance Criteria**:
  - [ ] `./test/integration_test.sh` exits with code 0
  - [ ] All 5 RPC methods return valid responses
  - [ ] Decoded values match simulator output
  - [ ] Project directory mode test passes

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Full integration test passes
    Tool: Bash
    Preconditions: All components built
    Steps:
      1. cd ms2d && ./test/integration_test.sh
      2. Check exit code
    Expected Result: Exit code 0, all tests pass
    Evidence: .sisyphus/evidence/task-10-integration.txt

  Scenario: Project directory mode works
    Tool: Bash
    Preconditions: Simulator running, daemon not started
    Steps:
      1. ./ms2d --project ../projectCfg/ --socket /tmp/ms2d_project.sock &
      2. sleep 2
      3. curl --unix-socket /tmp/ms2d_project.sock -d '{"method":"get_status","id":1}'
      4. Verify .result.connected == true
    Expected Result: Auto-configured from project directory
    Evidence: .sisyphus/evidence/task-10-project-mode.txt
  ```

  **Commit**: YES
  - Message: `test(ms2d): add integration test script`
  - Files: `ms2d/test/integration_test.sh`

---

- [ ] 11. C Client Library

  **What to do**:
  - Create `ms2d/clients/ms2_client.h` with:
    ```c
    typedef struct ms2_client ms2_client_t;
    ms2_client_t *ms2_connect(const char *socket_path);
    void ms2_disconnect(ms2_client_t *client);
    double ms2_get_value(ms2_client_t *client, const char *field);
    int ms2_get_values(ms2_client_t *client, const char **fields, int count, double *values);
    char **ms2_list_fields(ms2_client_t *client, int *count);
    int ms2_get_status(ms2_client_t *client, int *connected, char *signature, size_t sig_len);
    void ms2_free_fields(char **fields, int count);
    ```
  - Create `ms2d/clients/ms2_client.c` implementing the library
  - Use Unix socket + JSON-RPC internally
  - Handle connection errors gracefully (return -1 or NULL)
  - Create `ms2d/clients/ms2_client_example.c` with usage example

  **Must NOT do**:
  - Don't require cJSON in client (inline minimal JSON)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 4)
  - **Parallel Group**: Wave 4 (with Task 12)
  - **Blocks**: F1
  - **Blocked By**: Task 9

  **References**:
  - Task 8 RPC protocol specification
  - Standard Unix socket client patterns

  **Acceptance Criteria**:
  - [ ] `libms2client.a` builds without errors
  - [ ] Example program compiles and links
  - [ ] Example connects to daemon and prints RPM value

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: C client retrieves RPM value
    Tool: Bash
    Preconditions: Daemon running with simulator
    Steps:
      1. Compile example: gcc -o client_test clients/ms2_client_example.c -L. -lms2client
      2. Run: ./client_test /tmp/ms2d.sock
      3. Verify output contains "rpm:" followed by a number
    Expected Result: RPM value printed (e.g., "rpm: 2500.0")
    Evidence: .sisyphus/evidence/task-11-c-client.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): add C client library`
  - Files: `ms2d/clients/ms2_client.h`, `ms2d/clients/ms2_client.c`, `ms2d/clients/ms2_client_example.c`

---

- [ ] 12. Node.js Client Module

  **What to do**:
  - Create `ms2d/clients/ms2_client.js` implementing:
    ```javascript
    class MS2Client {
      constructor(socketPath)
      async connect()
      async disconnect()
      async getValue(field)
      async getValues(fields)
      async getAll()
      async listFields()
      async getStatus()
    }
    module.exports = { MS2Client, connect: async (path) => { ... } }
    ```
  - Use Node.js `net` module for Unix socket
  - JSON-RPC over socket (newline-delimited JSON)
  - Create `ms2d/clients/ms2_client_example.js` with usage example
  - No external dependencies (pure Node.js)

  **Must NOT do**:
  - Don't use native addons
  - Don't require npm packages

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 4)
  - **Parallel Group**: Wave 4 (with Task 11)
  - **Blocks**: F1
  - **Blocked By**: Task 9

  **References**:
  - Node.js `net` module documentation
  - Task 8 RPC protocol specification

  **Acceptance Criteria**:
  - [ ] `node ms2_client_example.js /tmp/ms2d.sock` prints RPM value
  - [ ] No npm dependencies required

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Node.js client retrieves values
    Tool: Bash
    Preconditions: Daemon running
    Steps:
      1. node clients/ms2_client_example.js /tmp/ms2d.sock
      2. Verify output contains field values
    Expected Result: JSON output with rpm, map, tps values
    Evidence: .sisyphus/evidence/task-12-nodejs-client.txt
  ```

  **Commit**: YES
  - Message: `feat(ms2d): add Node.js client module`
  - Files: `ms2d/clients/ms2_client.js`, `ms2d/clients/ms2_client_example.js`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Memory Leak Check** — `unspecified-high`
  Run daemon under valgrind: `valgrind --leak-check=full ./ms2d --port /tmp/ms2_ecu_sim --ini cfg.ini`. Run integration tests. Check valgrind output for leaks. "definitely lost: 0 bytes" required for APPROVE.
  Output: `Valgrind Summary | Leaks: N bytes | VERDICT: APPROVE/REJECT`

- [ ] F3. **Code Quality Review** — `unspecified-high`
  Run `gcc -Wall -Wextra -Werror` on all sources. Check for: unused variables, missing return statements, uninitialized variables. Review all malloc/free pairs. Check socket/fd cleanup in all error paths.
  Output: `Warnings [N] | Resource Leaks [N] | VERDICT: APPROVE/REJECT`

- [ ] F4. **Documentation Check** — `quick`
  Verify README.md exists with: build instructions, usage examples, RPC method documentation. Verify all public functions have header comments.
  Output: `README sections [N/5] | Function docs [N%] | VERDICT: APPROVE/REJECT`

---

## Commit Strategy

| Task | Commit Message | Files |
|------|----------------|-------|
| 1 | `feat(ms2d): add project structure and headers` | `ms2d/Makefile`, `ms2d/include/*.h` |
| 2 | `feat(ms2d): add utility functions (CRC32, timestamps)` | `ms2d/src/util.c` |
| 3 | `feat(ms2d): vendor cJSON library` | `ms2d/vendor/cjson/*` |
| 4 | `feat(ms2d): add project directory parser` | `ms2d/src/project_parser.c` |
| 5 | `feat(ms2d): implement INI parser for OutputChannels` | `ms2d/src/ini_parser.c` |
| 6 | `feat(ms2d): implement newserial protocol communication` | `ms2d/src/serial_comm.c` |
| 7 | `feat(ms2d): implement data decoder` | `ms2d/src/decoder.c` |
| 8 | `feat(ms2d): implement JSON-RPC server over Unix socket` | `ms2d/src/rpc_server.c` |
| 9 | `feat(ms2d): implement main daemon with signal handling` | `ms2d/src/main.c` |
| 10 | `test(ms2d): add integration test script` | `ms2d/test/integration_test.sh` |
| 11 | `feat(ms2d): add C client library` | `ms2d/clients/ms2_client.*` |
| 12 | `feat(ms2d): add Node.js client module` | `ms2d/clients/ms2_client.js` |

---

## Success Criteria

### Verification Commands
```bash
# Build
cd ms2d && make
# Expected: no errors, ms2d binary and libms2client.a created

# Start simulator
python3 ../ms2_ecu_simulator.py --ini ../cfg.ini &

# Start daemon (explicit config mode)
./ms2d --port /tmp/ms2_ecu_sim --ini ../cfg.ini --socket /tmp/ms2d.sock &

# Start daemon (project directory mode)
./ms2d --project ../projectCfg/ --socket /tmp/ms2d_project.sock &

# Test RPC
curl --unix-socket /tmp/ms2d.sock -d '{"method":"get_status","id":1}'
# Expected: {"result":{"connected":true,"signature":"MS2Extra..."},"id":1}

curl --unix-socket /tmp/ms2d.sock -d '{"method":"get_value","params":{"field":"rpm"},"id":2}'
# Expected: {"result":{"name":"rpm","value":XXXX.X,"units":"RPM"},"id":2}

# Test C client
./clients/ms2_client_example /tmp/ms2d.sock
# Expected: prints rpm value

# Test Node.js client
node clients/ms2_client_example.js /tmp/ms2d.sock
# Expected: prints field values as JSON

# Memory check
valgrind --leak-check=full ./ms2d --port /tmp/ms2_ecu_sim --ini ../cfg.ini &
# ... run tests ...
# Expected: "definitely lost: 0 bytes"
```

### Final Checklist
- [ ] `ms2d` daemon binary builds and runs
- [ ] Connects to simulator via virtual serial port
- [ ] All 5 RPC methods return valid JSON responses
- [ ] **Project directory mode** auto-discovers settings from TunerStudio project
- [ ] C client library compiles and works
- [ ] Node.js client works without npm dependencies
- [ ] No memory leaks under valgrind
- [ ] Clean shutdown on SIGTERM/SIGINT
- [ ] Reconnects automatically on serial disconnect

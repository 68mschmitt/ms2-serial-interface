# MS2D Daemon Makefile
# Targets: all, clean, install, ms2d, libms2client.a

CC := gcc
CFLAGS := -Wall -Wextra -pthread -std=c99 -fPIC
CFLAGS_DEBUG := $(CFLAGS) -g -O0
CFLAGS_RELEASE := $(CFLAGS) -O2

# Directories
SRC_DIR := src
INCLUDE_DIR := include
CLIENT_DIR := clients
BUILD_DIR := build
VENDOR_DIR := vendor
TEST_DIR := test

# Source files
DAEMON_SOURCES := $(wildcard $(SRC_DIR)/*.c)
CJSON_SOURCES := $(wildcard $(VENDOR_DIR)/cjson/*.c)
CLIENT_SOURCES := $(wildcard $(CLIENT_DIR)/*.c)
TEST_SOURCES := $(wildcard $(TEST_DIR)/*.c)

# Object files
DAEMON_OBJECTS := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.o,$(DAEMON_SOURCES))
CJSON_OBJECTS := $(patsubst $(VENDOR_DIR)/cjson/%.c,$(BUILD_DIR)/vendor_%.o,$(CJSON_SOURCES))
CLIENT_OBJECTS := $(patsubst $(CLIENT_DIR)/%.c,$(BUILD_DIR)/client_%.o,$(CLIENT_SOURCES))
TEST_OBJECTS := $(patsubst $(TEST_DIR)/%.c,$(BUILD_DIR)/test_%.o,$(TEST_SOURCES))

# Output targets
DAEMON_TARGET := ms2d
CLIENT_LIB := libms2client.a

# Include paths
INCLUDES := -I$(INCLUDE_DIR) -I$(VENDOR_DIR)

# Default target
.PHONY: all
all: $(DAEMON_TARGET) $(CLIENT_LIB)

# Create build directory
$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

# Compile daemon object files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS_DEBUG) $(INCLUDES) -c $< -o $@

# Compile vendor object files
$(BUILD_DIR)/vendor_%.o: $(VENDOR_DIR)/cjson/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS_DEBUG) $(INCLUDES) -c $< -o $@

# Compile client object files
$(BUILD_DIR)/client_%.o: $(CLIENT_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS_DEBUG) $(INCLUDES) -c $< -o $@

# Compile test object files
$(BUILD_DIR)/test_%.o: $(TEST_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS_DEBUG) $(INCLUDES) -c $< -o $@
# Link daemon executable
$(DAEMON_TARGET): $(DAEMON_OBJECTS) $(CJSON_OBJECTS)
	$(CC) $(CFLAGS_DEBUG) -pthread $^ -o $@

# Create client library
$(CLIENT_LIB): $(CLIENT_OBJECTS)
	ar rcs $@ $^

# Install targets
.PHONY: install
install: $(DAEMON_TARGET) $(CLIENT_LIB)
	@echo "Installing ms2d daemon and client library..."
	@mkdir -p /usr/local/bin
	@mkdir -p /usr/local/lib
	@mkdir -p /usr/local/include/ms2d
	install -m 755 $(DAEMON_TARGET) /usr/local/bin/
	install -m 644 $(CLIENT_LIB) /usr/local/lib/
	install -m 644 $(INCLUDE_DIR)/*.h /usr/local/include/ms2d/

# Clean build artifacts
.PHONY: clean
clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(BUILD_DIR)
	rm -f $(DAEMON_TARGET)
	rm -f $(CLIENT_LIB)

# Help target
.PHONY: help
help:
	@echo "MS2D Daemon Build System"
	@echo "Available targets:"
	@echo "  all       - Build daemon and client library (default)"
	@echo "  ms2d      - Build daemon executable only"
	@echo "  libms2client.a - Build client library only"
	@echo "  install   - Install daemon and library to /usr/local"
	@echo "  clean     - Remove build artifacts"
	@echo "  help      - Show this help message"

.PHONY: ms2d
ms2d: $(DAEMON_TARGET)

.PHONY: libms2client.a
libms2client.a: $(CLIENT_LIB)

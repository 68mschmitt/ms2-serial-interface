#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../include/ms2d.h"
#include "../include/decoder.h"

/**
 * Test program for decoder functions
 * Tests with known values from MS2 OUTPC data
 */

void test_decode_rpm(void) {
    printf("=== Test 1: Decode RPM ===\n");
    
    // Create minimal state
    ms2d_state_t state = {0};
    
    // Create OUTPC buffer with RPM at offset 6
    // RPM = 2500 in little-endian U16: 0xC4 0x09
    // 2500 = 0x09C4 = (196 + 9*256)
    uint8_t buffer[256] = {0};
    buffer[6] = 0xC4;  // Low byte
    buffer[7] = 0x09;  // High byte
    
    state.outpc_buffer = buffer;
    state.outpc_len = sizeof(buffer);
    
    // Define rpm field
    ms2d_field_t rpm_field = {0};
    strncpy(rpm_field.name, "rpm", sizeof(rpm_field.name));
    rpm_field.type = MS2D_TYPE_U16;
    rpm_field.offset = 6;
    rpm_field.scale = 1.0;
    rpm_field.translate = 0.0;
    strncpy(rpm_field.units, "RPM", sizeof(rpm_field.units));
    
    // Decode
    double rpm = ms2d_decode_field(&state, &rpm_field);
    
    printf("  Decoded RPM: %.1f\n", rpm);
    printf("  Expected: 2500.0\n");
    
    // Verify
    if (rpm >= 2499.9 && rpm <= 2500.1) {
        printf("  ✓ PASS\n\n");
    } else {
        printf("  ✗ FAIL: Expected 2500.0, got %.1f\n\n", rpm);
        exit(1);
    }
}

void test_decode_battery(void) {
    printf("=== Test 2: Decode Battery Voltage ===\n");
    
    // Create minimal state
    ms2d_state_t state = {0};
    
    // Create OUTPC buffer with battery voltage at offset 26
    // Battery = 14.1V, encoded as 141 (0x8D) with scale 0.1
    // 141 in little-endian S16: 0x8D 0x00
    uint8_t buffer[256] = {0};
    buffer[26] = 0x8D;  // 141 low byte
    buffer[27] = 0x00;  // 141 high byte
    
    state.outpc_buffer = buffer;
    state.outpc_len = sizeof(buffer);
    
    // Define batteryVoltage field
    ms2d_field_t battery_field = {0};
    strncpy(battery_field.name, "batteryVoltage", sizeof(battery_field.name));
    battery_field.type = MS2D_TYPE_S16;
    battery_field.offset = 26;
    battery_field.scale = 0.1;
    battery_field.translate = 0.0;
    strncpy(battery_field.units, "V", sizeof(battery_field.units));
    
    // Decode: userValue = (141 + 0) * 0.1 = 14.1
    double voltage = ms2d_decode_field(&state, &battery_field);
    
    printf("  Decoded voltage: %.2f\n", voltage);
    printf("  Expected: 14.10\n");
    
    // Verify
    if (voltage >= 14.09 && voltage <= 14.11) {
        printf("  ✓ PASS\n\n");
    } else {
        printf("  ✗ FAIL: Expected 14.10, got %.2f\n\n", voltage);
        exit(1);
    }
}

void test_find_field(void) {
    printf("=== Test 3: Find Field by Name ===\n");
    
    // Create state with multiple fields
    ms2d_state_t state = {0};
    ms2d_field_t fields[3] = {0};
    
    strncpy(fields[0].name, "rpm", sizeof(fields[0].name));
    fields[0].type = MS2D_TYPE_U16;
    fields[0].offset = 6;
    
    strncpy(fields[1].name, "batteryVoltage", sizeof(fields[1].name));
    fields[1].type = MS2D_TYPE_S16;
    fields[1].offset = 26;
    
    strncpy(fields[2].name, "map", sizeof(fields[2].name));
    fields[2].type = MS2D_TYPE_S16;
    fields[2].offset = 8;
    
    state.fields = fields;
    state.num_fields = 3;
    
    // Test finding existing field
    const ms2d_field_t *found = ms2d_find_field(&state, "batteryVoltage");
    if (found && strcmp(found->name, "batteryVoltage") == 0 && found->offset == 26) {
        printf("  ✓ Found 'batteryVoltage' at offset 26\n");
    } else {
        printf("  ✗ FAIL: Could not find 'batteryVoltage'\n");
        exit(1);
    }
    
    // Test finding non-existent field
    const ms2d_field_t *not_found = ms2d_find_field(&state, "nonexistent");
    if (not_found == NULL) {
        printf("  ✓ Correctly returned NULL for non-existent field\n");
    } else {
        printf("  ✗ FAIL: Should return NULL for non-existent field\n");
        exit(1);
    }
    
    printf("  ✓ PASS\n\n");
}

void test_decode_all(void) {
    printf("=== Test 4: Decode All Fields ===\n");
    
    // Create state with fields and buffer
    ms2d_state_t state = {0};
    
    // Create buffer with known values
    uint8_t buffer[256] = {0};
    buffer[6] = 0xC4;  // rpm = 2500
    buffer[7] = 0x09;
    buffer[26] = 0x8D; // battery = 14.1
    buffer[27] = 0x00;
    
    state.outpc_buffer = buffer;
    state.outpc_len = sizeof(buffer);
    
    // Create fields
    ms2d_field_t fields[2] = {0};
    
    strncpy(fields[0].name, "rpm", sizeof(fields[0].name));
    fields[0].type = MS2D_TYPE_U16;
    fields[0].offset = 6;
    fields[0].scale = 1.0;
    fields[0].translate = 0.0;
    strncpy(fields[0].units, "RPM", sizeof(fields[0].units));
    
    strncpy(fields[1].name, "batteryVoltage", sizeof(fields[1].name));
    fields[1].type = MS2D_TYPE_S16;
    fields[1].offset = 26;
    fields[1].scale = 0.1;
    fields[1].translate = 0.0;
    strncpy(fields[1].units, "V", sizeof(fields[1].units));
    
    state.fields = fields;
    state.num_fields = 2;
    
    // Decode all
    ms2d_value_t values[2];
    int count = 0;
    
    ms2d_error_t err = ms2d_decode_all(&state, values, &count);
    
    if (err != MS2D_SUCCESS) {
        printf("  ✗ FAIL: ms2d_decode_all returned error %d\n", err);
        exit(1);
    }
    
    if (count != 2) {
        printf("  ✗ FAIL: Expected 2 values, got %d\n", count);
        exit(1);
    }
    
    printf("  Decoded %d fields:\n", count);
    for (int i = 0; i < count; i++) {
        printf("    %s: %.2f %s\n", values[i].name, values[i].value, values[i].units);
    }
    
    // Verify values
    if (values[0].value >= 2499.9 && values[0].value <= 2500.1) {
        printf("  ✓ RPM correct\n");
    } else {
        printf("  ✗ FAIL: RPM incorrect (%.1f)\n", values[0].value);
        exit(1);
    }
    
    if (values[1].value >= 14.09 && values[1].value <= 14.11) {
        printf("  ✓ Battery voltage correct\n");
    } else {
        printf("  ✗ FAIL: Battery voltage incorrect (%.2f)\n", values[1].value);
        exit(1);
    }
    
    printf("  ✓ PASS\n\n");
}

void test_data_types(void) {
    printf("=== Test 5: Data Types ===\n");
    
    ms2d_state_t state = {0};
    uint8_t buffer[256] = {0};
    state.outpc_buffer = buffer;
    state.outpc_len = sizeof(buffer);
    
    // Test U08
    buffer[0] = 200;
    ms2d_field_t u08_field = {.type = MS2D_TYPE_U08, .offset = 0, .scale = 1.0, .translate = 0.0};
    double u08_val = ms2d_decode_field(&state, &u08_field);
    printf("  U08: 200 -> %.0f ", u08_val);
    if (u08_val == 200.0) printf("✓\n"); else { printf("✗\n"); exit(1); }
    
    // Test S08 (negative)
    buffer[1] = 0xFF; // -1 in signed 8-bit
    ms2d_field_t s08_field = {.type = MS2D_TYPE_S08, .offset = 1, .scale = 1.0, .translate = 0.0};
    double s08_val = ms2d_decode_field(&state, &s08_field);
    printf("  S08: 0xFF -> %.0f ", s08_val);
    if (s08_val == -1.0) printf("✓\n"); else { printf("✗\n"); exit(1); }
    
    // Test U32 - little endian: 0x12345678 = bytes[0x78, 0x56, 0x34, 0x12]
    buffer[10] = 0x78;  // Low byte
    buffer[11] = 0x56;
    buffer[12] = 0x34;
    buffer[13] = 0x12;  // High byte
    ms2d_field_t u32_field = {.type = MS2D_TYPE_U32, .offset = 10, .scale = 1.0, .translate = 0.0};
    double u32_val = ms2d_decode_field(&state, &u32_field);
    printf("  U32: 0x12345678 -> %.0f ", u32_val);
    if (u32_val == 305419896.0) printf("✓\n"); else { printf("✗ (got %.0f)\n", u32_val); exit(1); }
    
    // Test S32 (negative)
    buffer[20] = 0xFF;  // -1 in signed 32-bit
    buffer[21] = 0xFF;
    buffer[22] = 0xFF;
    buffer[23] = 0xFF;
    ms2d_field_t s32_field = {.type = MS2D_TYPE_S32, .offset = 20, .scale = 1.0, .translate = 0.0};
    double s32_val = ms2d_decode_field(&state, &s32_field);
    printf("  S32: 0xFFFFFFFF -> %.0f ", s32_val);
    if (s32_val == -1.0) printf("✓\n"); else { printf("✗\n"); exit(1); }
    
    // Test scale and translate
    buffer[30] = 0x0A; // 10
    ms2d_field_t scaled_field = {.type = MS2D_TYPE_U08, .offset = 30, .scale = 2.5, .translate = 5.0};
    double scaled_val = ms2d_decode_field(&state, &scaled_field);
    // (10 + 5) * 2.5 = 37.5
    printf("  Scale/Translate: (10 + 5) * 2.5 -> %.1f ", scaled_val);
    if (scaled_val == 37.5) printf("✓\n"); else { printf("✗\n"); exit(1); }
    
    printf("  ✓ PASS\n\n");
}

int main(void) {
    printf("MS2D Decoder Test Suite\n");
    printf("========================\n\n");
    
    test_decode_rpm();
    test_decode_battery();
    test_find_field();
    test_decode_all();
    test_data_types();
    
    printf("========================\n");
    printf("All tests passed! ✓\n");
    
    return 0;
}

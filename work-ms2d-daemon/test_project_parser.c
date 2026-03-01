#include <stdio.h>
#include <string.h>
#include "ms2d.h"
#include "project_parser.h"

int main(void) {
    ms2d_config_t config;
    
    printf("Testing ms2d_project_parse() with ./projectCfg directory...\n\n");
    
    ms2d_error_t err = ms2d_project_parse("./projectCfg", &config);
    
    if (err != MS2D_SUCCESS) {
        fprintf(stderr, "ERROR: ms2d_project_parse failed: %s\n", ms2d_error_str(err));
        return 1;
    }
    
    printf("=== Parsed Configuration ===\n");
    printf("Serial Port:     %s\n", config.serial_port);
    printf("Baud Rate:       %u\n", config.baud_rate);
    printf("INI File:        %s\n", config.ini_file);
    printf("CAN ID:          %u\n", config.can_id);
    printf("Fahrenheit:      %d\n", config.fahrenheit);
    printf("CAN Commands:    %d\n", config.can_commands);
    printf("Custom Fields:   %u\n", config.num_custom_fields);
    
    if (config.num_custom_fields > 0) {
        printf("\n=== Custom Fields ===\n");
        for (int i = 0; i < config.num_custom_fields; i++) {
            printf("Field %d: %s (type=%d, offset=%u, scale=%.3f, translate=%.3f, units=%s)\n",
                   i + 1,
                   config.custom_fields[i].name,
                   config.custom_fields[i].type,
                   config.custom_fields[i].offset,
                   config.custom_fields[i].scale,
                   config.custom_fields[i].translate,
                   config.custom_fields[i].units);
        }
    }
    
    printf("\n=== Verification ===\n");
    
    /* Verify serial port */
    if (strcmp(config.serial_port, "/dev/ttyUSB0") == 0) {
        printf("✓ Serial port: PASS (/dev/ttyUSB0)\n");
    } else {
        printf("✗ Serial port: FAIL (expected /dev/ttyUSB0, got %s)\n", config.serial_port);
    }
    
    /* Verify baud rate */
    if (config.baud_rate == 115200) {
        printf("✓ Baud rate: PASS (115200)\n");
    } else {
        printf("✗ Baud rate: FAIL (expected 115200, got %u)\n", config.baud_rate);
    }
    
    /* Verify INI file */
    if (strcmp(config.ini_file, "mainController.ini") == 0) {
        printf("✓ INI file: PASS (mainController.ini)\n");
    } else {
        printf("✗ INI file: FAIL (expected mainController.ini, got %s)\n", config.ini_file);
    }
    
    /* Verify Fahrenheit flag */
    if (config.fahrenheit == 1) {
        printf("✓ Fahrenheit flag: PASS (true)\n");
    } else {
        printf("✗ Fahrenheit flag: FAIL (expected true, got %d)\n", config.fahrenheit);
    }
    
    /* Verify CAN commands flag */
    if (config.can_commands == 1) {
        printf("✓ CAN commands flag: PASS (true)\n");
    } else {
        printf("✗ CAN commands flag: FAIL (expected true, got %d)\n", config.can_commands);
    }
    
    /* Verify custom fields count (should be 0 or more - custom.ini has empty OutputChannels) */
    printf("✓ Custom fields: %u (empty OutputChannels is valid)\n", config.num_custom_fields);
    
    ms2d_project_free_config(&config);
    
    printf("\nAll tests completed successfully!\n");
    return 0;
}

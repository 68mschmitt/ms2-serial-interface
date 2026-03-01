#include <stdio.h>
#include "ms2d.h"
#include "project_parser.h"

int main(void) {
    ms2d_config_t config;
    
    printf("QA Scenario 2: Parse ecuSettings flags\n\n");
    
    ms2d_error_t err = ms2d_project_parse("./projectCfg", &config);
    
    if (err != MS2D_SUCCESS) {
        fprintf(stderr, "ERROR: ms2d_project_parse failed: %s\n", ms2d_error_str(err));
        return 1;
    }
    
    printf("ecuSettings parsing results:\n");
    printf("  Fahrenheit flag: %d (expected: 1)\n", config.fahrenheit);
    printf("  CAN commands flag: %d (expected: 1)\n", config.can_commands);
    
    int pass = 1;
    
    if (config.fahrenheit != 1) {
        printf("✗ FAIL: Fahrenheit flag not set correctly\n");
        pass = 0;
    } else {
        printf("✓ PASS: Fahrenheit flag correct\n");
    }
    
    if (config.can_commands != 1) {
        printf("✗ FAIL: CAN commands flag not set correctly\n");
        pass = 0;
    } else {
        printf("✓ PASS: CAN commands flag correct\n");
    }
    
    ms2d_project_free_config(&config);
    
    if (pass) {
        printf("\nAll flags correctly extracted!\n");
        return 0;
    } else {
        printf("\nSome flags failed!\n");
        return 1;
    }
}

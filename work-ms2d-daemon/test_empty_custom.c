#include <stdio.h>
#include "ms2d.h"
#include "project_parser.h"

int main(void) {
    ms2d_config_t config;
    
    printf("QA Scenario 3: Missing custom.ini OutputChannels doesn't fail\n\n");
    
    ms2d_error_t err = ms2d_project_parse("./projectCfg", &config);
    
    if (err != MS2D_SUCCESS) {
        fprintf(stderr, "✗ FAIL: ms2d_project_parse failed: %s\n", ms2d_error_str(err));
        return 1;
    }
    
    printf("✓ PASS: Parse succeeded\n");
    printf("Custom fields count: %u\n", config.num_custom_fields);
    
    if (config.num_custom_fields == 0) {
        printf("✓ PASS: num_custom_fields == 0 (empty OutputChannels handled correctly)\n");
    } else {
        printf("Note: Found %u custom fields (OutputChannels not empty)\n", config.num_custom_fields);
    }
    
    ms2d_project_free_config(&config);
    
    printf("\nTest completed successfully!\n");
    return 0;
}

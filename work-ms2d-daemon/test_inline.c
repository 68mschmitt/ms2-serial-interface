#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char serial_port[256];
    unsigned int baud_rate;
} test_config_t;

static char *trim_whitespace(char *str) {
    char *end;
    while (*str == ' ' || *str == '\t') str++;
    if (*str == 0) return str;
    end = str + strlen(str) - 1;
    while (end > str && (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r'))
        end--;
    end[1] = '\0';
    return str;
}

int main() {
    FILE *fp = fopen("./projectCfg/project.properties", "r");
    if (!fp) {
        fprintf(stderr, "Failed to open file\n");
        return 1;
    }
    
    test_config_t config;
    memset(&config, 0, sizeof(config));
    config.baud_rate = 115200;
    
    char line[1024];
    int line_num = 0;
    while (fgets(line, sizeof(line), fp)) {
        line_num++;
        
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') {
            continue;
        }
        
        char *eq = strchr(line, '=');
        if (!eq) continue;
        
        *eq = '\0';
        char *key = trim_whitespace(line);
        char *value = trim_whitespace(eq + 1);
        
        /* Parse serial port - look for keys containing "Com\ Port" */
        if ((strstr(key, "Com Port") != NULL || strstr(key, "Com\\ Port") != NULL) && value[0] != '\0') {
            printf("Line %d: Matched Com Port\n", line_num);
            printf("  Key: [%s]\n", key);
            printf("  Value: [%s]\n", value);
            printf("  Value length: %zu\n", strlen(value));
            printf("  Value[0] = %d ('%c')\n", value[0], value[0]);
            
            strncpy(config.serial_port, value, sizeof(config.serial_port) - 1);
            config.serial_port[sizeof(config.serial_port) - 1] = '\0';
            
            printf("  After copy: config.serial_port = [%s]\n", config.serial_port);
        }
    }
    
    fclose(fp);
    
    printf("\nFinal config.serial_port: [%s]\n", config.serial_port);
    printf("Length: %zu\n", strlen(config.serial_port));
    
    return 0;
}

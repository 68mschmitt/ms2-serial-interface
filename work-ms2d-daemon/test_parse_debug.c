#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
        
        if (strstr(key, "Com\\ Port") != NULL) {
            printf("Line %d: Found 'Com\\ Port'\n", line_num);
            printf("  Key: [%s]\n", key);
            printf("  Value: [%s]\n", value);
        }
    }
    
    fclose(fp);
    return 0;
}

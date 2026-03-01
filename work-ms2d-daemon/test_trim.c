#include <stdio.h>
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
    char test1[] = "\n";
    char test2[] = "  \n";
    char test3[] = "/dev/ttyUSB0\n";
    char test4[] = "  /dev/ttyUSB0  \n";
    
    printf("Test 1: [%s] -> [%s] (len=%zu)\n", test1, trim_whitespace(test1), strlen(trim_whitespace(test1)));
    
    strcpy(test2, "  \n");
    printf("Test 2: '  \\n' -> [%s] (len=%zu)\n", trim_whitespace(test2), strlen(trim_whitespace(test2)));
    
    strcpy(test3, "/dev/ttyUSB0\n");
    printf("Test 3: '/dev/ttyUSB0\\n' -> [%s] (len=%zu)\n", trim_whitespace(test3), strlen(trim_whitespace(test3)));
    
    strcpy(test4, "  /dev/ttyUSB0  \n");
    printf("Test 4: '  /dev/ttyUSB0  \\n' -> [%s] (len=%zu)\n", trim_whitespace(test4), strlen(trim_whitespace(test4)));
    
    return 0;
}

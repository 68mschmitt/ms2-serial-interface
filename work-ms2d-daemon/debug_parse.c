#include <stdio.h>
#include <string.h>

int main() {
    const char *key = "CommSettingMSCommDriver.RS232\\ Serial\\ InterfaceCom\\ Port";
    
    printf("Key: [%s]\n", key);
    printf("Looking for 'Com Port': %s\n", strstr(key, "Com Port") ? "FOUND" : "NOT FOUND");
    printf("Looking for 'Com\\ Port': %s\n", strstr(key, "Com\\ Port") ? "FOUND" : "NOT FOUND");
    
    // The actual pattern in the file
    char *pos = strstr(key, "Com");
    while (pos) {
        printf("Found 'Com' at position %ld: [%.20s]\n", pos - key, pos);
        pos = strstr(pos + 1, "Com");
    }
    
    return 0;
}

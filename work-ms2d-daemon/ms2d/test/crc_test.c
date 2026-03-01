#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "include/ms2d.h"

int main(void)
{
    /* Test vector: "123456789" should produce 0xCBF43926 */
    const char *test_data = "123456789";
    uint32_t result = ms2d_crc32((const uint8_t *)test_data, strlen(test_data));
    
    printf("CRC32 Test Vector\n");
    printf("Input: \"%s\"\n", test_data);
    printf("Expected: 0xcbf43926\n");
    printf("Got:      0x%08x\n", result);
    
    if (result == 0xCBF43926) {
        printf("PASS\n");
        return 0;
    } else {
        printf("FAIL\n");
        return 1;
    }
}

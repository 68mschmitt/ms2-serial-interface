#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include "include/ms2d.h"

int main(void)
{
    printf("Timestamp Test\n");
    
    uint64_t ts1 = ms2d_timestamp_ms();
    printf("Timestamp 1: %lu ms\n", ts1);
    
    /* Sleep for 100ms */
    usleep(100000);
    
    uint64_t ts2 = ms2d_timestamp_ms();
    printf("Timestamp 2: %lu ms\n", ts2);
    
    uint64_t diff = ts2 - ts1;
    printf("Difference: %lu ms\n", diff);
    
    /* Allow 90-110ms range for OS jitter */
    if (diff >= 90 && diff <= 110) {
        printf("PASS (difference within 90-110ms range)\n");
        return 0;
    } else {
        printf("FAIL (difference outside expected range)\n");
        return 1;
    }
}

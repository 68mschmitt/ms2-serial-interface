#define _POSIX_C_SOURCE 199309L
#include <stdint.h>
#include <stddef.h>
#include <time.h>
#include <string.h>
#include "../include/ms2d.h"

/**
 * CRC32 calculation using standard polynomial 0xEDB88320
 * Matches Python binascii.crc32() output
 */
uint32_t ms2d_crc32(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xFFFFFFFF;
    
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xEDB88320;
            } else {
                crc >>= 1;
            }
        }
    }
    
    return crc ^ 0xFFFFFFFF;
}

/**
 * Get current time in milliseconds since epoch
 * Uses CLOCK_REALTIME for wall-clock time
 */
uint64_t ms2d_timestamp_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    
    uint64_t ms = (uint64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
    return ms;
}

/**
 * Convert error code to human-readable string
 */
const char *ms2d_error_str(ms2d_error_t err)
{
    switch (err) {
        case MS2D_SUCCESS:
            return "Success";
        case MS2D_ERROR_IO:
            return "I/O error";
        case MS2D_ERROR_PARSE:
            return "Parse error";
        case MS2D_ERROR_INVALID_ARG:
            return "Invalid argument";
        case MS2D_ERROR_MEMORY:
            return "Memory allocation error";
        case MS2D_ERROR_TIMEOUT:
            return "Timeout";
        case MS2D_ERROR_SERIAL:
            return "Serial communication error";
        case MS2D_ERROR_CONFIG:
            return "Configuration error";
        case MS2D_ERROR_THREAD:
            return "Thread error";
        default:
            return "Unknown error";
    }
}

/**
 * Get byte size for a data type
 * Returns -1 for BITS type (variable size)
 */
int ms2d_field_size(ms2d_data_type_t type)
{
    switch (type) {
        case MS2D_TYPE_U08:
        case MS2D_TYPE_S08:
            return 1;
        case MS2D_TYPE_U16:
        case MS2D_TYPE_S16:
            return 2;
        case MS2D_TYPE_U32:
        case MS2D_TYPE_S32:
            return 4;
        case MS2D_TYPE_BITS:
            return -1;  /* Variable size */
        default:
            return -1;
    }
}

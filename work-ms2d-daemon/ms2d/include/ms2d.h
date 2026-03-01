#ifndef MS2D_H
#define MS2D_H

#include <stdint.h>
#include <stddef.h>
#include <pthread.h>
#include <time.h>

/* Error codes */
typedef enum {
    MS2D_SUCCESS = 0,
    MS2D_ERROR_IO = 1,
    MS2D_ERROR_PARSE = 2,
    MS2D_ERROR_INVALID_ARG = 3,
    MS2D_ERROR_MEMORY = 4,
    MS2D_ERROR_TIMEOUT = 5,
    MS2D_ERROR_SERIAL = 6,
    MS2D_ERROR_CONFIG = 7,
    MS2D_ERROR_THREAD = 8
} ms2d_error_t;

/* Data types for MS2 fields */
typedef enum {
    MS2D_TYPE_U08 = 0,      /* unsigned 8-bit */
    MS2D_TYPE_S08 = 1,      /* signed 8-bit */
    MS2D_TYPE_U16 = 2,      /* unsigned 16-bit */
    MS2D_TYPE_S16 = 3,      /* signed 16-bit */
    MS2D_TYPE_U32 = 4,      /* unsigned 32-bit */
    MS2D_TYPE_S32 = 5,      /* signed 32-bit */
    MS2D_TYPE_BITS = 6      /* bit field */
} ms2d_data_type_t;

/* Field definition */
typedef struct {
    char name[64];          /* Field name */
    ms2d_data_type_t type;  /* Data type */
    uint16_t offset;        /* Byte offset in OUTPC */
    float scale;            /* Scale factor */
    float translate;        /* Translation offset */
    char units[32];         /* Unit string */
} ms2d_field_t;

/* Value representation */
typedef struct {
    char name[64];          /* Field name */
    double value;           /* Computed value */
    char units[32];         /* Unit string */
    uint64_t timestamp_ms;  /* Timestamp in milliseconds */
} ms2d_value_t;

/* Configuration structure */
typedef struct {
    char serial_port[256];  /* Serial port path (e.g., /dev/ttyUSB0) */
    uint32_t baud_rate;     /* Baud rate (e.g., 115200) */
    char ini_file[256];     /* Path to MS2 INI file */
    uint16_t can_id;        /* CAN ID for commands */
    int fahrenheit;         /* 1 for Fahrenheit, 0 for Celsius */
    int can_commands;       /* 1 to enable CAN commands */
    ms2d_field_t *custom_fields;  /* Custom field definitions */
    uint16_t num_custom_fields;    /* Number of custom fields */
} ms2d_config_t;

/* Main daemon state */
typedef struct {
    ms2d_field_t *fields;   /* Field definitions */
    uint16_t num_fields;    /* Number of fields */
    uint8_t *outpc_buffer;  /* OUTPC data buffer */
    size_t outpc_len;       /* Current OUTPC data length */
    size_t outpc_size;      /* OUTPC buffer size */
    int serial_fd;          /* Serial port file descriptor */
    pthread_mutex_t mutex;  /* Synchronization mutex */
    int running;            /* 1 if daemon is running */
    ms2d_config_t config;   /* Configuration */
} ms2d_state_t;

/* Utility functions */
uint32_t ms2d_crc32(const uint8_t *data, size_t len);
uint64_t ms2d_timestamp_ms(void);
const char *ms2d_error_str(ms2d_error_t err);
int ms2d_field_size(ms2d_data_type_t type);

#endif /* MS2D_H */

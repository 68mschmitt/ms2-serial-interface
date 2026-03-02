#include "ms2d.h"
#include "decoder.h"
#include <string.h>
#include <stdint.h>

/**
 * Extract integer value from OUTPC buffer based on data type
 * Handles big-endian byte order for multi-byte values (Megasquirt protocol)
 */
static int32_t extract_raw_value(const uint8_t *buffer, size_t buffer_len, 
                                  const ms2d_field_t *field) {
    uint16_t offset = field->offset;
    ms2d_data_type_t type = field->type;
    
    // Calculate field size
    int field_size = ms2d_field_size(type);
    if (field_size < 0) {
        // BITS type - assume we read from a U16 or U32 at offset
        // For bits fields, we'll read the base integer type
        // For simplicity, read 4 bytes (U32) to handle any bits field
        if ((size_t)(offset + 4) > buffer_len) {
            return 0;
        }
        // Read as U32 big-endian
        uint32_t val = (buffer[offset] << 24) |
                       (buffer[offset+1] << 16) |
                       (buffer[offset+2] << 8) |
                       buffer[offset+3];
        return (int32_t)val;
    }
    
    // Check bounds
    if ((size_t)(offset + field_size) > buffer_len) {
        return 0;
    }
    
    // Extract based on type (big-endian, Megasquirt protocol)
    switch (type) {
        case MS2D_TYPE_U08:
            return buffer[offset];
            
        case MS2D_TYPE_S08:
            return (int8_t)buffer[offset];
            
        case MS2D_TYPE_U16: {
            uint16_t val = (buffer[offset] << 8) | buffer[offset+1];
            return val;
        }
            
        case MS2D_TYPE_S16: {
            uint16_t raw = (buffer[offset] << 8) | buffer[offset+1];
            return (int16_t)raw;
        }
            
        case MS2D_TYPE_U32: {
            uint32_t val = (buffer[offset] << 24) |
                          (buffer[offset+1] << 16) |
                          (buffer[offset+2] << 8) |
                          buffer[offset+3];
            return (int32_t)val;  // Cast to signed for consistency
        }
            
        case MS2D_TYPE_S32: {
            uint32_t raw = (buffer[offset] << 24) |
                          (buffer[offset+1] << 16) |
                          (buffer[offset+2] << 8) |
                          buffer[offset+3];
            return (int32_t)raw;
        }
            
        default:
            return 0;
    }
}

/**
 * Decode single field from OUTPC buffer
 * Formula: userValue = (msValue + translate) * scale
 * For BITS fields: extract bit range, no scale/translate
 */
double ms2d_decode_field(const ms2d_state_t *state, const ms2d_field_t *field) {
    if (!state || !field) {
        return 0.0;
    }
    
    // Use state's OUTPC buffer
    const uint8_t *buffer = state->outpc_buffer;
    size_t buffer_len = state->outpc_len;
    
    if (!buffer || buffer_len == 0) {
        return 0.0;
    }
    
    // Extract raw value
    int32_t raw_value = extract_raw_value(buffer, buffer_len, field);
    
    // Handle BITS fields: extract bit range, no scaling
    if (field->type == MS2D_TYPE_BITS) {
        // For bits fields, the offset/size info is embedded in field definition
        // In MS2 INI format: bits fields have offset pointing to base value
        // and bit range [low:high] stored elsewhere (not in this struct yet)
        // For now, just return raw value (caller must handle bit extraction)
        // TODO: Add bit_low, bit_high to ms2d_field_t struct
        return (double)raw_value;
    }
    
    // Apply scale and translate: userValue = (msValue + translate) * scale
    double result = ((double)raw_value + (double)field->translate) * (double)field->scale;
    return result;
}

/**
 * Decode all fields from state's OUTPC buffer
 * Populates values array with current decoded values
 */
ms2d_error_t ms2d_decode_all(const ms2d_state_t *state, ms2d_value_t *values, int *count) {
    if (!state || !values || !count) {
        return MS2D_ERROR_INVALID_ARG;
    }
    
    if (!state->fields || state->num_fields == 0) {
        *count = 0;
        return MS2D_SUCCESS;
    }
    
    uint64_t timestamp = ms2d_timestamp_ms();
    
    // Decode each field
    for (uint16_t i = 0; i < state->num_fields; i++) {
        const ms2d_field_t *field = &state->fields[i];
        
        // Decode field value
        double decoded_value = ms2d_decode_field(state, field);
        
        // Fill value struct
        strncpy(values[i].name, field->name, sizeof(values[i].name) - 1);
        values[i].name[sizeof(values[i].name) - 1] = '\0';
        
        values[i].value = decoded_value;
        
        strncpy(values[i].units, field->units, sizeof(values[i].units) - 1);
        values[i].units[sizeof(values[i].units) - 1] = '\0';
        
        values[i].timestamp_ms = timestamp;
    }
    
    *count = state->num_fields;
    return MS2D_SUCCESS;
}

/**
 * Find field by name in state's field array
 * Returns pointer to field or NULL if not found
 */
const ms2d_field_t *ms2d_find_field(const ms2d_state_t *state, const char *name) {
    if (!state || !name) {
        return NULL;
    }
    
    if (!state->fields) {
        return NULL;
    }
    
    // Linear search through fields (case-sensitive)
    for (uint16_t i = 0; i < state->num_fields; i++) {
        if (strcmp(state->fields[i].name, name) == 0) {
            return &state->fields[i];
        }
    }
    
    return NULL;
}

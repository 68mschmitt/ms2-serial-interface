#ifndef MS2D_DECODER_H
#define MS2D_DECODER_H

#include "ms2d.h"

/**
 * Decode OUTPC data buffer into field values
 * 
 * @param state Daemon state with field definitions
 * @param buffer Raw OUTPC data
 * @param buffer_len Length of buffer
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_decode_outpc(ms2d_state_t *state, const uint8_t *buffer, size_t buffer_len);

/**
 * Extract single value from OUTPC buffer
 * 
 * @param field Field definition
 * @param buffer OUTPC data buffer
 * @param buffer_len Length of buffer
 * @return Decoded value as double
 */
double ms2d_decode_field(const ms2d_field_t *field, const uint8_t *buffer, size_t buffer_len);

/**
 * Get all current values as ms2d_value_t array
 * 
 * @param state Daemon state
 * @param values Pointer to value array (allocated by function)
 * @param num_values Pointer to store number of values
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_get_values(ms2d_state_t *state, ms2d_value_t **values, uint16_t *num_values);

/**
 * Free allocated values array
 * 
 * @param values Value array to free
 */
void ms2d_free_values(ms2d_value_t *values);

/**
 * Validate OUTPC data checksum
 * 
 * @param buffer OUTPC data buffer
 * @param buffer_len Length of buffer
 * @return 1 if valid, 0 if invalid
 */
int ms2d_validate_checksum(const uint8_t *buffer, size_t buffer_len);

/**
 * Apply scale and translate to raw value
 * 
 * @param raw_value Raw value from buffer
 * @param scale Scale factor
 * @param translate Translation offset
 * @return Scaled and translated value
 */
double ms2d_apply_scaling(double raw_value, float scale, float translate);

#endif /* MS2D_DECODER_H */

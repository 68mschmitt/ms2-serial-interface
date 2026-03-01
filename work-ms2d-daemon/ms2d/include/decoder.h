#ifndef MS2D_DECODER_H
#define MS2D_DECODER_H

#include "ms2d.h"

/**
 * Decode single field from state's OUTPC buffer
 * Formula: userValue = (msValue + translate) * scale
 * For BITS fields: extract bit range, no scale/translate
 * Thread-safe: takes const state, doesn't modify
 * 
 * @param state Daemon state with OUTPC buffer and field definitions
 * @param field Field definition
 * @return Decoded value as double
 */
double ms2d_decode_field(const ms2d_state_t *state, const ms2d_field_t *field);

/**
 * Decode all fields from state's OUTPC buffer
 * Populates values array with current decoded values
 * Thread-safe: takes const state, doesn't modify
 * 
 * @param state Daemon state with OUTPC buffer and field definitions
 * @param values Pre-allocated array to store decoded values (must be large enough)
 * @param count Pointer to store number of values decoded
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_decode_all(const ms2d_state_t *state, ms2d_value_t *values, int *count);

/**
 * Find field by name in state's field array
 * Thread-safe: takes const state, doesn't modify
 * 
 * @param state Daemon state with field definitions
 * @param name Field name to search for (case-sensitive)
 * @return Pointer to field or NULL if not found
 */
const ms2d_field_t *ms2d_find_field(const ms2d_state_t *state, const char *name);


#endif /* MS2D_DECODER_H */

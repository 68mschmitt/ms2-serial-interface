#ifndef MS2D_INI_PARSER_H
#define MS2D_INI_PARSER_H

#include "ms2d.h"

/**
 * Parse MS2 INI file and extract field definitions
 * 
 * @param ini_file Path to INI file
 * @param fields Pointer to field array (allocated by function)
 * @param num_fields Pointer to store number of fields
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_ini_parse(const char *ini_file, ms2d_field_t **fields, uint16_t *num_fields);

/**
 * Free allocated field definitions
 * 
 * @param fields Field array to free
 */
void ms2d_ini_free_fields(ms2d_field_t *fields);

/**
 * Get field by name
 * 
 * @param fields Field array
 * @param num_fields Number of fields
 * @param name Field name to search for
 * @return Pointer to field or NULL if not found
 */
ms2d_field_t* ms2d_ini_get_field(ms2d_field_t *fields, uint16_t num_fields, const char *name);

/**
 * Validate INI file format
 * 
 * @param ini_file Path to INI file
 * @return MS2D_SUCCESS if valid, error code otherwise
 */
ms2d_error_t ms2d_ini_validate(const char *ini_file);

#endif /* MS2D_INI_PARSER_H */

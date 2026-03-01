#ifndef MS2D_PROJECT_PARSER_H
#define MS2D_PROJECT_PARSER_H

#include "ms2d.h"

/**
 * Parse TunerStudio project directory configuration
 * 
 * Parses project.properties and custom.ini from a TunerStudio project directory
 * to extract connection settings and custom field definitions.
 * 
 * @param project_dir Path to TunerStudio project directory
 * @param config Pointer to config structure to populate
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_project_parse(const char *project_dir, ms2d_config_t *config);

/**
 * Load project configuration from file
 * 
 * @param config_file Path to configuration file
 * @param config Pointer to config structure to populate
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_project_load_config(const char *config_file, ms2d_config_t *config);

/**
 * Save project configuration to file
 * 
 * @param config_file Path to configuration file
 * @param config Configuration to save
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_project_save_config(const char *config_file, const ms2d_config_t *config);

/**
 * Validate project configuration
 * 
 * @param config Configuration to validate
 * @return MS2D_SUCCESS if valid, error code otherwise
 */
ms2d_error_t ms2d_project_validate_config(const ms2d_config_t *config);

/**
 * Parse custom field definitions from project file
 * 
 * @param project_file Path to project file
 * @param fields Pointer to field array (allocated by function)
 * @param num_fields Pointer to store number of fields
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_project_parse_fields(const char *project_file, ms2d_field_t **fields, uint16_t *num_fields);

/**
 * Get project metadata
 * 
 * @param project_file Path to project file
 * @param name Buffer for project name
 * @param name_len Size of name buffer
 * @param version Buffer for version string
 * @param version_len Size of version buffer
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_project_get_metadata(const char *project_file, char *name, size_t name_len,
                                        char *version, size_t version_len);

/**
 * Free project configuration resources
 * 
 * @param config Configuration to free
 */
void ms2d_project_free_config(ms2d_config_t *config);

#endif /* MS2D_PROJECT_PARSER_H */

#define _POSIX_C_SOURCE 200809L
#include "project_parser.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

/* Helper to build file path */
static void build_path(char *dest, size_t dest_size, const char *dir, const char *file) {
    snprintf(dest, dest_size, "%s/%s", dir, file);
}

/* Helper to check if file exists */
static int file_exists(const char *path) {
    struct stat st;
    return stat(path, &st) == 0;
}

/* Helper to trim whitespace */
static char *trim_whitespace(char *str) {
    char *end;
    /* Trim leading whitespace */
    while (*str == ' ' || *str == '\t' || *str == '\n' || *str == '\r') str++;
    if (*str == 0) return str;
    /* Trim trailing whitespace */
    end = str + strlen(str) - 1;
    while (end > str && (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r'))
        end--;
    end[1] = '\0';
    return str;
}

/* Helper to parse ecuSettings flags */
static void parse_ecu_settings(const char *value, ms2d_config_t *config) {
    char *copy = strdup(value);
    char *token = strtok(copy, "|");
    
    while (token != NULL) {
        token = trim_whitespace(token);
        if (strcmp(token, "FAHRENHEIT") == 0) {
            config->fahrenheit = 1;
        } else if (strcmp(token, "CAN_COMMANDS") == 0) {
            config->can_commands = 1;
        }
        token = strtok(NULL, "|");
    }
    
    free(copy);
}

/* Parse project.properties file */
static ms2d_error_t parse_project_properties(const char *path, ms2d_config_t *config) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        return MS2D_ERROR_IO;
    }
    
    char line[1024];
    while (fgets(line, sizeof(line), fp)) {
        /* Skip comments and empty lines */
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') {
            continue;
        }
        
        /* Look for key=value pairs */
        char *eq = strchr(line, '=');
        if (!eq) continue;
        
        *eq = '\0';
        char *key = trim_whitespace(line);
        char *value = trim_whitespace(eq + 1);
        
        /* Parse serial port - look for keys ending with "Com Port" */
        if ((strstr(key, "Com Port") != NULL || strstr(key, "Com\\ Port") != NULL) && value[0] != '\0') {
            strncpy(config->serial_port, value, sizeof(config->serial_port) - 1);
            config->serial_port[sizeof(config->serial_port) - 1] = '\0';
        }
        /* Parse baud rate - look for keys ending with "Baud Rate" */
        else if ((strstr(key, "Baud Rate") != NULL || strstr(key, "Baud\\ Rate") != NULL) && value[0] != '\0') {
            config->baud_rate = (uint32_t)atoi(value);
        }
        /* Parse INI file */
        else if (strcmp(key, "ecuConfigFile") == 0) {
            strncpy(config->ini_file, value, sizeof(config->ini_file) - 1);
            config->ini_file[sizeof(config->ini_file) - 1] = '\0';
        }
        /* Parse CAN ID */
        else if (strcmp(key, "canId") == 0) {
            config->can_id = (uint16_t)atoi(value);
        }
        /* Parse ECU settings flags */
        else if (strcmp(key, "ecuSettings") == 0) {
            parse_ecu_settings(value, config);
        }
    }
    
    fclose(fp);
    return MS2D_SUCCESS;
}

/* Helper to strip #XX| prefix from line */
static char *strip_line_prefix(char *line) {
    /* Check for #XX| prefix (4 characters) */
    if (strlen(line) >= 4 && line[0] == '#' && line[3] == '|') {
        return line + 4;
    }
    return line;
}

/* Parse custom.ini [OutputChannels] section */
static ms2d_error_t parse_custom_ini(const char *path, ms2d_config_t *config) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        /* custom.ini is optional, not an error if missing */
        config->custom_fields = NULL;
        config->num_custom_fields = 0;
        return MS2D_SUCCESS;
    }
    
    char line[1024];
    int in_output_channels = 0;
    int field_count = 0;
    ms2d_field_t *fields = NULL;
    int fields_capacity = 0;
    
    while (fgets(line, sizeof(line), fp)) {
        char *processed_line = strip_line_prefix(line);
        char *trimmed = trim_whitespace(processed_line);
        
        /* Check for [OutputChannels] section */
        if (strcmp(trimmed, "[OutputChannels]") == 0) {
            in_output_channels = 1;
            continue;
        }
        
        /* Check for start of new section */
        if (trimmed[0] == '[' && in_output_channels) {
            /* End of OutputChannels section */
            break;
        }
        
        /* Skip if not in OutputChannels section */
        if (!in_output_channels) {
            continue;
        }
        
        /* Skip comments and empty lines */
        if (trimmed[0] == ';' || trimmed[0] == '\0') {
            continue;
        }
        
        /* Parse field definition: name = scalar, type, offset, "units", scale, translate */
        /* or: name = bits, type, offset, [bits] */
        char *eq = strchr(trimmed, '=');
        if (!eq) continue;
        
        *eq = '\0';
        char *name = trim_whitespace(trimmed);
        char *value = trim_whitespace(eq + 1);
        
        /* Allocate/expand fields array if needed */
        if (field_count >= fields_capacity) {
            fields_capacity = fields_capacity == 0 ? 8 : fields_capacity * 2;
            ms2d_field_t *new_fields = realloc(fields, fields_capacity * sizeof(ms2d_field_t));
            if (!new_fields) {
                free(fields);
                fclose(fp);
                return MS2D_ERROR_MEMORY;
            }
            fields = new_fields;
        }
        
        /* Parse the field */
        ms2d_field_t *field = &fields[field_count];
        memset(field, 0, sizeof(ms2d_field_t));
        strncpy(field->name, name, sizeof(field->name) - 1);
        
        /* Parse comma-separated values */
        char *token = strtok(value, ",");
        int token_idx = 0;
        
        while (token != NULL && token_idx < 6) {
            token = trim_whitespace(token);
            
            switch (token_idx) {
                case 0: /* type (scalar or bits) */
                    /* Will determine actual data type from token 1 */
                    break;
                case 1: /* data type */
                    if (strcmp(token, "U08") == 0) field->type = MS2D_TYPE_U08;
                    else if (strcmp(token, "S08") == 0) field->type = MS2D_TYPE_S08;
                    else if (strcmp(token, "U16") == 0) field->type = MS2D_TYPE_U16;
                    else if (strcmp(token, "S16") == 0) field->type = MS2D_TYPE_S16;
                    else if (strcmp(token, "U32") == 0) field->type = MS2D_TYPE_U32;
                    else if (strcmp(token, "S32") == 0) field->type = MS2D_TYPE_S32;
                    break;
                case 2: /* offset */
                    field->offset = (uint16_t)atoi(token);
                    break;
                case 3: /* units (quoted) or bits spec */
                    /* Remove quotes if present */
                    if (token[0] == '"') {
                        char *end_quote = strchr(token + 1, '"');
                        if (end_quote) {
                            *end_quote = '\0';
                            strncpy(field->units, token + 1, sizeof(field->units) - 1);
                        }
                    }
                    break;
                case 4: /* scale */
                    field->scale = atof(token);
                    break;
                case 5: /* translate */
                    field->translate = atof(token);
                    break;
            }
            
            token = strtok(NULL, ",");
            token_idx++;
        }
        
        field_count++;
    }
    
    fclose(fp);
    
    config->custom_fields = fields;
    config->num_custom_fields = field_count;
    
    return MS2D_SUCCESS;
}

/**
 * Parse TunerStudio project directory configuration
 */
ms2d_error_t ms2d_project_parse(const char *project_dir, ms2d_config_t *config) {
    if (!project_dir || !config) {
        return MS2D_ERROR_INVALID_ARG;
    }
    
    /* Initialize config with defaults */
    memset(config, 0, sizeof(ms2d_config_t));
    config->baud_rate = 115200;
    config->can_id = 0;
    config->fahrenheit = 0;
    config->can_commands = 0;
    config->custom_fields = NULL;
    config->num_custom_fields = 0;
    
    /* Build path to project.properties */
    char properties_path[512];
    build_path(properties_path, sizeof(properties_path), project_dir, "project.properties");
    
    /* Check if project.properties exists */
    if (!file_exists(properties_path)) {
        return MS2D_ERROR_IO;
    }
    
    /* Parse project.properties */
    ms2d_error_t err = parse_project_properties(properties_path, config);
    if (err != MS2D_SUCCESS) {
        return err;
    }
    
    /* Build path to custom.ini (optional) */
    char custom_ini_path[512];
    build_path(custom_ini_path, sizeof(custom_ini_path), project_dir, "custom.ini");
    
    /* Parse custom.ini if it exists */
    err = parse_custom_ini(custom_ini_path, config);
    if (err != MS2D_SUCCESS) {
        return err;
    }
    
    return MS2D_SUCCESS;
}

/**
 * Free project configuration resources
 */
void ms2d_project_free_config(ms2d_config_t *config) {
    if (config && config->custom_fields) {
        free(config->custom_fields);
        config->custom_fields = NULL;
        config->num_custom_fields = 0;
    }
}

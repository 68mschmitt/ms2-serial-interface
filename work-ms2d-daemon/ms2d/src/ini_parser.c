#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../include/ms2d.h"

#define MS2D_COND_STACK_MAX 64
#define MS2D_LINE_MAX 2048
#define MS2D_INITIAL_FIELDS_CAPACITY 200

static char *trim_whitespace(char *str)
{
    if (!str) {
        return str;
    }

    while (*str && isspace((unsigned char)*str)) {
        str++;
    }

    if (*str == '\0') {
        return str;
    }

    char *end = str + strlen(str) - 1;
    while (end > str && isspace((unsigned char)*end)) {
        end--;
    }
    end[1] = '\0';

    return str;
}

static char *strip_xx_prefix(char *line)
{
    if (!line) {
        return line;
    }

    if (line[0] == '#'
        && isupper((unsigned char)line[1])
        && isupper((unsigned char)line[2])
        && line[3] == '|') {
        return line + 4;
    }

    return line;
}

static ms2d_data_type_t map_data_type(const char *type)
{
    if (!type) {
        return MS2D_TYPE_U16;
    }

    if (strcmp(type, "U08") == 0) return MS2D_TYPE_U08;
    if (strcmp(type, "S08") == 0) return MS2D_TYPE_S08;
    if (strcmp(type, "U16") == 0) return MS2D_TYPE_U16;
    if (strcmp(type, "S16") == 0) return MS2D_TYPE_S16;
    if (strcmp(type, "U32") == 0) return MS2D_TYPE_U32;
    if (strcmp(type, "S32") == 0) return MS2D_TYPE_S32;

    return MS2D_TYPE_U16;
}

static float parse_first_number(const char *token, float fallback)
{
    if (!token) {
        return fallback;
    }

    char *end_ptr = NULL;
    float direct = strtof(token, &end_ptr);
    if (end_ptr && end_ptr != token) {
        return direct;
    }

    const char *p = token;
    while (*p) {
        if (*p == '+' || *p == '-' || *p == '.' || isdigit((unsigned char)*p)) {
            char *inner_end = NULL;
            float n = strtof(p, &inner_end);
            if (inner_end && inner_end != p) {
                return n;
            }
        }
        p++;
    }

    return fallback;
}

static int split_csv_preserving_quotes(char *input, char **parts, int max_parts)
{
    if (!input || !parts || max_parts <= 0) {
        return 0;
    }

    int count = 0;
    int in_quotes = 0;
    char quote_char = '\0';
    char *start = input;

    for (char *p = input; ; p++) {
        char c = *p;

        if ((c == '"' || c == '\'') && !in_quotes) {
            in_quotes = 1;
            quote_char = c;
        } else if (in_quotes && c == quote_char) {
            in_quotes = 0;
            quote_char = '\0';
        }

        if (c == '\0' || (c == ',' && !in_quotes)) {
            if (count < max_parts) {
                if (c == ',') {
                    *p = '\0';
                }
                parts[count++] = trim_whitespace(start);
            }

            if (c == '\0' || count >= max_parts) {
                break;
            }

            start = p + 1;
        }
    }

    return count;
}

static int eval_condition(const char *expr, const ms2d_state_t *state)
{
    if (!expr || !state) {
        return 1;
    }

    if (strcmp(expr, "FAHRENHEIT") == 0) {
        return state->config.fahrenheit ? 1 : 0;
    }

    if (strcmp(expr, "CELSIUS") == 0) {
        return state->config.fahrenheit ? 0 : 1;
    }

    if (strcmp(expr, "CAN_COMMANDS") == 0) {
        return state->config.can_commands ? 1 : 0;
    }

    if (strcmp(expr, "NOT_CAN_COMMANDS") == 0) {
        return state->config.can_commands ? 0 : 1;
    }

    return 1;
}

static int conditionally_active(const int *stack, int depth)
{
    for (int i = 0; i < depth; i++) {
        if (!stack[i]) {
            return 0;
        }
    }
    return 1;
}

static void parse_signature_line(const char *line, char *signature, size_t signature_len)
{
    if (!line || !signature || signature_len == 0) {
        return;
    }

    const char *eq = strchr(line, '=');
    if (!eq) {
        return;
    }

    const char *first_quote = strchr(eq + 1, '"');
    if (!first_quote) {
        return;
    }

    const char *second_quote = strchr(first_quote + 1, '"');
    if (!second_quote || second_quote <= first_quote + 1) {
        return;
    }

    size_t n = (size_t)(second_quote - (first_quote + 1));
    if (n >= signature_len) {
        n = signature_len - 1;
    }

    memcpy(signature, first_quote + 1, n);
    signature[n] = '\0';
}

static ms2d_error_t ensure_capacity(ms2d_field_t **fields, int *capacity, int needed)
{
    if (!fields || !capacity) {
        return MS2D_ERROR_INVALID_ARG;
    }

    if (needed <= *capacity) {
        return MS2D_SUCCESS;
    }

    int new_capacity = (*capacity > 0) ? *capacity : MS2D_INITIAL_FIELDS_CAPACITY;
    while (new_capacity < needed) {
        new_capacity *= 2;
    }

    ms2d_field_t *new_fields = realloc(*fields, (size_t)new_capacity * sizeof(ms2d_field_t));
    if (!new_fields) {
        return MS2D_ERROR_MEMORY;
    }

    *fields = new_fields;
    *capacity = new_capacity;
    return MS2D_SUCCESS;
}

static int parse_output_channel_field(const char *name, char *value, ms2d_field_t *field)
{
    if (!name || !value || !field) {
        return 0;
    }

    char *parts[16];
    int part_count = split_csv_preserving_quotes(value, parts, 16);
    if (part_count < 3) {
        return 0;
    }

    const char *kind = parts[0];
    if (strcmp(kind, "scalar") != 0 && strcmp(kind, "bits") != 0) {
        return 0;
    }

    memset(field, 0, sizeof(*field));
    strncpy(field->name, name, sizeof(field->name) - 1);
    field->name[sizeof(field->name) - 1] = '\0';
    field->offset = (uint16_t)strtoul(parts[2], NULL, 10);

    if (strcmp(kind, "bits") == 0) {
        field->type = MS2D_TYPE_BITS;
        field->scale = 1.0f;
        field->translate = 0.0f;
        field->units[0] = '\0';
        return 1;
    }

    field->type = map_data_type(parts[1]);
    field->scale = (part_count > 4) ? parse_first_number(parts[4], 1.0f) : 1.0f;
    field->translate = (part_count > 5) ? parse_first_number(parts[5], 0.0f) : 0.0f;

    if (part_count > 3) {
        char *units = trim_whitespace(parts[3]);
        if (units[0] == '"') {
            units++;
        }
        size_t len = strlen(units);
        if (len > 0 && units[len - 1] == '"') {
            units[len - 1] = '\0';
        }
        strncpy(field->units, units, sizeof(field->units) - 1);
        field->units[sizeof(field->units) - 1] = '\0';
    }

    return 1;
}

ms2d_error_t ms2d_ini_parse(const char *path, ms2d_state_t *state)
{
    if (!path || !state) {
        return MS2D_ERROR_INVALID_ARG;
    }

    FILE *fp = fopen(path, "r");
    if (!fp) {
        return MS2D_ERROR_IO;
    }

    free(state->fields);
    state->fields = NULL;
    state->num_fields = 0;
    state->outpc_size = 0;

    ms2d_field_t *fields = NULL;
    int capacity = 0;
    int count = 0;

    int in_output_channels = 0;
    int in_tunerstudio = 0;

    int cond_stack[MS2D_COND_STACK_MAX];
    int cond_depth = 0;

    char line[MS2D_LINE_MAX];
    char signature[128] = {0};

    while (fgets(line, sizeof(line), fp)) {
        char *work = strip_xx_prefix(line);
        char *trimmed = trim_whitespace(work);

        if (*trimmed == '\0' || *trimmed == ';') {
            continue;
        }

        if (strncmp(trimmed, "#if", 3) == 0 && isspace((unsigned char)trimmed[3])) {
            if (cond_depth < MS2D_COND_STACK_MAX) {
                char *expr = trim_whitespace(trimmed + 3);
                cond_stack[cond_depth++] = eval_condition(expr, state);
            }
            continue;
        }

        if (strcmp(trimmed, "#else") == 0) {
            if (cond_depth > 0) {
                cond_stack[cond_depth - 1] = !cond_stack[cond_depth - 1];
            }
            continue;
        }

        if (strcmp(trimmed, "#endif") == 0) {
            if (cond_depth > 0) {
                cond_depth--;
            }
            continue;
        }

        if (!conditionally_active(cond_stack, cond_depth)) {
            continue;
        }

        if (trimmed[0] == '[') {
            in_output_channels = (strcmp(trimmed, "[OutputChannels]") == 0);
            in_tunerstudio = (strcmp(trimmed, "[TunerStudio]") == 0);
            continue;
        }

        if (in_tunerstudio && strncmp(trimmed, "signature", 9) == 0) {
            parse_signature_line(trimmed, signature, sizeof(signature));
            continue;
        }

        if (!in_output_channels) {
            continue;
        }

        if (strncmp(trimmed, "ochBlockSize", 12) == 0) {
            char *eq = strchr(trimmed, '=');
            if (eq) {
                state->outpc_size = (size_t)strtoul(eq + 1, NULL, 10);
            }
            continue;
        }

        if (strstr(trimmed, "{") != NULL) {
            continue;
        }

        char *eq = strchr(trimmed, '=');
        if (!eq) {
            continue;
        }

        *eq = '\0';
        char *name = trim_whitespace(trimmed);
        char *value = trim_whitespace(eq + 1);
        if (*name == '\0' || *value == '\0') {
            continue;
        }

        ms2d_error_t cap_err = ensure_capacity(&fields, &capacity, count + 1);
        if (cap_err != MS2D_SUCCESS) {
            free(fields);
            fclose(fp);
            return cap_err;
        }

        if (parse_output_channel_field(name, value, &fields[count])) {
            count++;
        }
    }

    fclose(fp);

    (void)signature;

    if (count > UINT16_MAX) {
        free(fields);
        return MS2D_ERROR_PARSE;
    }

    if (count == 0) {
        free(fields);
        return MS2D_ERROR_PARSE;
    }

    state->fields = fields;
    state->num_fields = (uint16_t)count;

    return MS2D_SUCCESS;
}

ms2d_error_t ms2d_ini_merge_custom(ms2d_state_t *state, const ms2d_field_t *custom, int count)
{
    if (!state) {
        return MS2D_ERROR_INVALID_ARG;
    }

    if (!custom || count <= 0) {
        return MS2D_SUCCESS;
    }

    if (!state->fields && state->num_fields > 0) {
        return MS2D_ERROR_PARSE;
    }

    int base_count = (int)state->num_fields;
    int capacity = base_count > 0 ? base_count : MS2D_INITIAL_FIELDS_CAPACITY;
    if (capacity < base_count + count) {
        while (capacity < base_count + count) {
            capacity *= 2;
        }
    }

    ms2d_field_t *merged = state->fields;
    if (capacity > base_count) {
        merged = realloc(state->fields, (size_t)capacity * sizeof(ms2d_field_t));
        if (!merged) {
            return MS2D_ERROR_MEMORY;
        }
    }

    for (int i = 0; i < count; i++) {
        const ms2d_field_t *src = &custom[i];
        int replaced = 0;

        for (int j = 0; j < base_count; j++) {
            if (strncmp(merged[j].name, src->name, sizeof(merged[j].name)) == 0) {
                merged[j] = *src;
                replaced = 1;
                break;
            }
        }

        if (!replaced) {
            if (base_count >= capacity) {
                int new_capacity = capacity * 2;
                ms2d_field_t *grown = realloc(merged, (size_t)new_capacity * sizeof(ms2d_field_t));
                if (!grown) {
                    state->fields = merged;
                    return MS2D_ERROR_MEMORY;
                }
                merged = grown;
                capacity = new_capacity;
            }
            merged[base_count++] = *src;
        }
    }

    if (base_count > UINT16_MAX) {
        state->fields = merged;
        return MS2D_ERROR_PARSE;
    }

    state->fields = merged;
    state->num_fields = (uint16_t)base_count;

    return MS2D_SUCCESS;
}

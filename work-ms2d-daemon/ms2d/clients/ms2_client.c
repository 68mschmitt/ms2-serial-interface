#define _POSIX_C_SOURCE 200809L

#include "ms2_client.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

/**
 * Client state structure (opaque to users)
 */
struct ms2_client {
    char socket_path[108];  /* Store socket path for reconnection */
    int request_id;
};

/**
 * Internal helper to send a JSON-RPC request and read response.
 * Opens a new connection for each request (server closes after response).
 * Returns malloc'd JSON response string, or NULL on error.
 */
static char *rpc_call(ms2_client_t *client, const char *method, const char *params_json)
{
    if (!client || !method) {
        return NULL;
    }

    /* Connect to daemon for this request */
    int sockfd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sockfd < 0) {
        return NULL;
    }

    /* Set receive timeout (5 seconds) */
    struct timeval timeout;
    timeout.tv_sec = 5;
    timeout.tv_usec = 0;
    if (setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) {
        close(sockfd);
        return NULL;
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, client->socket_path, sizeof(addr.sun_path) - 1);

    if (connect(sockfd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sockfd);
        return NULL;
    }

    /* Build JSON-RPC 2.0 request */
    char request[4096];
    int request_len;
    if (params_json && params_json[0] != '\0') {
        request_len = snprintf(request, sizeof(request),
                               "{\"jsonrpc\":\"2.0\",\"method\":\"%s\",\"params\":%s,\"id\":%d}",
                               method, params_json, client->request_id);
    } else {
        request_len = snprintf(request, sizeof(request),
                               "{\"jsonrpc\":\"2.0\",\"method\":\"%s\",\"id\":%d}",
                               method, client->request_id);
    }
    client->request_id++;

    if (request_len >= (int)sizeof(request)) {
        close(sockfd);
        return NULL; /* Request too large */
    }

    /* Send request */
    ssize_t sent = send(sockfd, request, (size_t)request_len, 0);
    if (sent != request_len) {
        close(sockfd);
        return NULL;
    }

    /* Read response */
    char buffer[65536];
    ssize_t received = recv(sockfd, buffer, sizeof(buffer) - 1, 0);
    if (received <= 0) {
        close(sockfd);
        return NULL;
    }
    buffer[received] = '\0';

    close(sockfd);
    return strdup(buffer);
}

/**
 * Parse JSON string and extract a double value at the given path.
 * Minimal JSON parser - extracts first number after '"key":'
 */
static double extract_double(const char *json, const char *key)
{
    if (!json || !key) {
        return 0.0;
    }

    /* Search for "key": pattern */
    char pattern[256];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);
    const char *pos = strstr(json, pattern);
    if (!pos) {
        return 0.0;
    }

    /* Skip to colon and whitespace */
    pos = strchr(pos, ':');
    if (!pos) {
        return 0.0;
    }
    pos++;
    while (*pos == ' ' || *pos == '\t' || *pos == '\n' || *pos == '\r') {
        pos++;
    }

    /* Parse number */
    return strtod(pos, NULL);
}

/**
 * Extract string value at the given path.
 * Returns malloc'd string or NULL.
 */
static char *extract_string(const char *json, const char *key)
{
    if (!json || !key) {
        return NULL;
    }

    /* Search for "key": pattern */
    char pattern[256];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);
    const char *pos = strstr(json, pattern);
    if (!pos) {
        return NULL;
    }

    /* Find opening quote */
    pos = strchr(pos, ':');
    if (!pos) {
        return NULL;
    }
    pos++;
    while (*pos == ' ' || *pos == '\t' || *pos == '\n' || *pos == '\r') {
        pos++;
    }
    if (*pos != '"') {
        return NULL;
    }
    pos++; /* Skip opening quote */

    /* Find closing quote */
    const char *end = pos;
    while (*end && *end != '"') {
        if (*end == '\\' && *(end + 1) != '\0') {
            end += 2; /* Skip escaped character */
        } else {
            end++;
        }
    }
    if (*end != '"') {
        return NULL;
    }

    /* Copy string */
    size_t len = (size_t)(end - pos);
    char *result = malloc(len + 1);
    if (!result) {
        return NULL;
    }
    memcpy(result, pos, len);
    result[len] = '\0';
    return result;
}

/**
 * Extract integer value at the given path.
 */
static int extract_int(const char *json, const char *key)
{
    if (!json || !key) {
        return 0;
    }

    /* Search for "key": pattern */
    char pattern[256];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);
    const char *pos = strstr(json, pattern);
    if (!pos) {
        return 0;
    }

    /* Skip to colon and whitespace */
    pos = strchr(pos, ':');
    if (!pos) {
        return 0;
    }
    pos++;
    while (*pos == ' ' || *pos == '\t' || *pos == '\n' || *pos == '\r') {
        pos++;
    }

    /* Handle boolean true/false */
    if (strncmp(pos, "true", 4) == 0) {
        return 1;
    }
    if (strncmp(pos, "false", 5) == 0) {
        return 0;
    }

    /* Parse integer */
    return atoi(pos);
}

/* ========== Public API Implementation ========== */

ms2_client_t *ms2_connect(const char *socket_path)
{
    if (!socket_path) {
        return NULL;
    }

    /* Allocate client structure */
    ms2_client_t *client = malloc(sizeof(ms2_client_t));
    if (!client) {
        return NULL;
    }

    /* Store socket path for future requests */
    strncpy(client->socket_path, socket_path, sizeof(client->socket_path) - 1);
    client->socket_path[sizeof(client->socket_path) - 1] = '\0';
    client->request_id = 1;

    /* Test connection */
    int test_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (test_fd < 0) {
        free(client);
        return NULL;
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);

    if (connect(test_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(test_fd);
        free(client);
        return NULL;
    }

    close(test_fd);
    return client;
}

void ms2_disconnect(ms2_client_t *client)
{
    if (!client) {
        return;
    }

    free(client);
}

double ms2_get_value(ms2_client_t *client, const char *field)
{
    if (!client || !field) {
        return 0.0;
    }

    /* Build params JSON: {"name":"field"} */
    char params[512];
    snprintf(params, sizeof(params), "{\"name\":\"%s\"}", field);

    /* Call RPC */
    char *response = rpc_call(client, "get_value", params);
    if (!response) {
        return 0.0;
    }

    /* Extract value from result.value */
    double value = extract_double(response, "value");
    free(response);
    return value;
}

int ms2_get_values(ms2_client_t *client, const char **fields, int count, double *values)
{
    if (!client || !fields || !values || count <= 0) {
        return -1;
    }

    /* Build params JSON: {"names":["field1","field2",...]} */
    char params[4096];
    int offset = 0;
    offset += snprintf(params + offset, sizeof(params) - offset, "{\"names\":[");

    for (int i = 0; i < count; i++) {
        if (i > 0) {
            offset += snprintf(params + offset, sizeof(params) - offset, ",");
        }
        offset += snprintf(params + offset, sizeof(params) - offset, "\"%s\"", fields[i]);
    }
    offset += snprintf(params + offset, sizeof(params) - offset, "]}");

    if (offset >= (int)sizeof(params)) {
        return -1; /* Buffer overflow */
    }

    /* Call RPC */
    char *response = rpc_call(client, "get_values", params);
    if (!response) {
        return -1;
    }

    /* Extract values from result.values array */
    /* Minimal parsing: Find "values":[...] and extract numbers */
    const char *values_start = strstr(response, "\"values\":");
    if (!values_start) {
        free(response);
        return -1;
    }

    /* Skip to array opening bracket */
    const char *pos = strchr(values_start, '[');
    if (!pos) {
        free(response);
        return -1;
    }
    pos++;

    /* Parse numbers */
    for (int i = 0; i < count; i++) {
        /* Skip whitespace and commas */
        while (*pos && (*pos == ' ' || *pos == '\t' || *pos == '\n' || *pos == '\r' || *pos == ',')) {
            pos++;
        }
        if (*pos == ']') {
            break; /* End of array */
        }

        /* Parse number */
        char *endptr;
        values[i] = strtod(pos, &endptr);
        if (pos == endptr) {
            free(response);
            return -1; /* Parse error */
        }
        pos = endptr;
    }

    free(response);
    return 0;
}

char **ms2_list_fields(ms2_client_t *client, int *count)
{
    if (!client || !count) {
        return NULL;
    }
    *count = 0;

    /* Call RPC */
    char *response = rpc_call(client, "list_fields", NULL);
    if (!response) {
        return NULL;
    }

    /* Count fields in result array */
    /* Find "result":[ and count strings until ] */
    const char *result_start = strstr(response, "\"result\":");
    if (!result_start) {
        free(response);
        return NULL;
    }

    const char *array_start = strchr(result_start, '[');
    if (!array_start) {
        free(response);
        return NULL;
    }

    /* Count strings */
    int num_fields = 0;
    const char *pos = array_start + 1;
    while (*pos && *pos != ']') {
        /* Skip whitespace */
        while (*pos && (*pos == ' ' || *pos == '\t' || *pos == '\n' || *pos == '\r' || *pos == ',')) {
            pos++;
        }
        if (*pos == '"') {
            num_fields++;
            pos++; /* Skip opening quote */
            /* Skip to closing quote */
            while (*pos && *pos != '"') {
                if (*pos == '\\' && *(pos + 1) != '\0') {
                    pos += 2;
                } else {
                    pos++;
                }
            }
            if (*pos == '"') {
                pos++;
            }
        } else if (*pos == ']') {
            break;
        } else {
            pos++;
        }
    }

    if (num_fields == 0) {
        free(response);
        return NULL;
    }

    /* Allocate array */
    char **fields = malloc(sizeof(char *) * (size_t)num_fields);
    if (!fields) {
        free(response);
        return NULL;
    }

    /* Extract field names */
    int field_idx = 0;
    pos = array_start + 1;
    while (*pos && *pos != ']' && field_idx < num_fields) {
        /* Skip whitespace and commas */
        while (*pos && (*pos == ' ' || *pos == '\t' || *pos == '\n' || *pos == '\r' || *pos == ',')) {
            pos++;
        }
        if (*pos == '"') {
            pos++; /* Skip opening quote */
            const char *name_start = pos;
            /* Find closing quote */
            while (*pos && *pos != '"') {
                if (*pos == '\\' && *(pos + 1) != '\0') {
                    pos += 2;
                } else {
                    pos++;
                }
            }
            if (*pos == '"') {
                size_t name_len = (size_t)(pos - name_start);
                fields[field_idx] = malloc(name_len + 1);
                if (fields[field_idx]) {
                    memcpy(fields[field_idx], name_start, name_len);
                    fields[field_idx][name_len] = '\0';
                    field_idx++;
                }
                pos++; /* Skip closing quote */
            }
        } else if (*pos == ']') {
            break;
        } else {
            pos++;
        }
    }

    free(response);
    *count = field_idx;
    return fields;
}

int ms2_get_status(ms2_client_t *client, int *connected, char *signature, size_t sig_len)
{
    if (!client) {
        return -1;
    }

    /* Call RPC */
    char *response = rpc_call(client, "get_status", NULL);
    if (!response) {
        return -1;
    }

    /* Extract fields */
    if (connected) {
        *connected = extract_int(response, "connected");
    }

    if (signature && sig_len > 0) {
        char *sig_str = extract_string(response, "signature");
        if (sig_str) {
            strncpy(signature, sig_str, sig_len - 1);
            signature[sig_len - 1] = '\0';
            free(sig_str);
        } else {
            signature[0] = '\0';
        }
    }

    free(response);
    return 0;
}

void ms2_free_fields(char **fields, int count)
{
    if (!fields) {
        return;
    }

    for (int i = 0; i < count; i++) {
        free(fields[i]);
    }
    free(fields);
}

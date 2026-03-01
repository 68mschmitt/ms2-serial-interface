#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include "../include/decoder.h"
#include "../include/ms2d.h"
#include "../vendor/cjson/cJSON.h"

#define MS2D_RPC_DEFAULT_SOCKET_PATH "/tmp/ms2d.sock"
#define MS2D_RPC_MAX_REQUEST_SIZE 16384
#define MS2D_RPC_BACKLOG 16

static int g_rpc_server_fd = -1;
static char g_rpc_socket_path[108] = MS2D_RPC_DEFAULT_SOCKET_PATH;
static uint64_t g_rpc_request_count = 0;
static uint64_t g_rpc_last_poll_timestamp_ms = 0;
static char g_rpc_signature[128] = "unknown";
static pthread_mutex_t g_rpc_mutex = PTHREAD_MUTEX_INITIALIZER;

static ms2d_error_t rpc_make_nonblocking(int fd)
{
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) {
        return MS2D_ERROR_IO;
    }

    if (fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
        return MS2D_ERROR_IO;
    }

    return MS2D_SUCCESS;
}

static cJSON *rpc_make_base_response(const cJSON *id)
{
    cJSON *response = cJSON_CreateObject();
    if (!response) {
        return NULL;
    }

    if (!cJSON_AddStringToObject(response, "jsonrpc", "2.0")) {
        cJSON_Delete(response);
        return NULL;
    }

    cJSON *id_copy = id ? cJSON_Duplicate((cJSON *)id, 1) : cJSON_CreateNull();
    if (!id_copy || !cJSON_AddItemToObject(response, "id", id_copy)) {
        cJSON_Delete(id_copy);
        cJSON_Delete(response);
        return NULL;
    }

    return response;
}

static cJSON *rpc_make_error_response(const cJSON *id, int code, const char *message)
{
    cJSON *response = rpc_make_base_response(id);
    if (!response) {
        return NULL;
    }

    cJSON *error_obj = cJSON_CreateObject();
    if (!error_obj) {
        cJSON_Delete(response);
        return NULL;
    }

    if (!cJSON_AddNumberToObject(error_obj, "code", code)
        || !cJSON_AddStringToObject(error_obj, "message", message)
        || !cJSON_AddItemToObject(response, "error", error_obj)) {
        cJSON_Delete(error_obj);
        cJSON_Delete(response);
        return NULL;
    }

    return response;
}

static cJSON *rpc_make_result_response(const cJSON *id, cJSON *result)
{
    cJSON *response = rpc_make_base_response(id);
    if (!response) {
        cJSON_Delete(result);
        return NULL;
    }

    if (!cJSON_AddItemToObject(response, "result", result)) {
        cJSON_Delete(result);
        cJSON_Delete(response);
        return NULL;
    }

    return response;
}

static uint64_t rpc_update_last_poll_timestamp(void)
{
    uint64_t now = ms2d_timestamp_ms();

    pthread_mutex_lock(&g_rpc_mutex);
    g_rpc_last_poll_timestamp_ms = now;
    pthread_mutex_unlock(&g_rpc_mutex);

    return now;
}

static uint64_t rpc_get_last_poll_timestamp(void)
{
    uint64_t ts;

    pthread_mutex_lock(&g_rpc_mutex);
    ts = g_rpc_last_poll_timestamp_ms;
    pthread_mutex_unlock(&g_rpc_mutex);

    return ts;
}

static uint64_t rpc_increment_request_count(void)
{
    uint64_t count;

    pthread_mutex_lock(&g_rpc_mutex);
    g_rpc_request_count++;
    count = g_rpc_request_count;
    pthread_mutex_unlock(&g_rpc_mutex);

    return count;
}

static int rpc_extract_json_body(char *request_buf, size_t request_len, char **json_start, size_t *json_len)
{
    if (!request_buf || !json_start || !json_len) {
        return 0;
    }

    if (request_len >= 5
        && (memcmp(request_buf, "POST ", 5) == 0 || memcmp(request_buf, "GET ", 4) == 0)) {
        char *header_end = strstr(request_buf, "\r\n\r\n");
        if (!header_end) {
            return 0;
        }

        size_t header_len = (size_t)(header_end - request_buf) + 4;
        char *len_header = strstr(request_buf, "Content-Length:");
        size_t body_len = request_len - header_len;

        if (len_header) {
            len_header += strlen("Content-Length:");
            while (*len_header == ' ' || *len_header == '\t') {
                len_header++;
            }
            body_len = (size_t)strtoul(len_header, NULL, 10);
            if (header_len + body_len > request_len) {
                return 0;
            }
        }

        *json_start = request_buf + header_len;
        *json_len = body_len;
        return 1;
    }

    *json_start = request_buf;
    *json_len = request_len;
    return 1;
}

static ms2d_error_t rpc_write_response(int client_fd, const char *request_buf, size_t request_len, const char *json)
{
    if (!request_buf || !json) {
        return MS2D_ERROR_INVALID_ARG;
    }

    size_t json_len = strlen(json);
    const int is_http = (request_len >= 5 && memcmp(request_buf, "POST ", 5) == 0)
                        || (request_len >= 4 && memcmp(request_buf, "GET ", 4) == 0);

    if (!is_http) {
        ssize_t written = send(client_fd, json, json_len, 0);
        return (written < 0 || (size_t)written != json_len) ? MS2D_ERROR_IO : MS2D_SUCCESS;
    }

    char header[512];
    int header_len = snprintf(header,
                              sizeof(header),
                              "HTTP/1.1 200 OK\r\n"
                              "Content-Type: application/json\r\n"
                              "Content-Length: %zu\r\n"
                              "Connection: close\r\n"
                              "\r\n",
                              json_len);
    if (header_len < 0 || (size_t)header_len >= sizeof(header)) {
        return MS2D_ERROR_IO;
    }

    ssize_t sent_header = send(client_fd, header, (size_t)header_len, 0);
    if (sent_header < 0 || (size_t)sent_header != (size_t)header_len) {
        return MS2D_ERROR_IO;
    }

    ssize_t sent_body = send(client_fd, json, json_len, 0);
    if (sent_body < 0 || (size_t)sent_body != json_len) {
        return MS2D_ERROR_IO;
    }

    return MS2D_SUCCESS;
}

static cJSON *rpc_method_get_value(ms2d_state_t *state, const cJSON *params)
{
    if (!cJSON_IsObject(params)) {
        return NULL;
    }

    const cJSON *field_json = cJSON_GetObjectItemCaseSensitive((cJSON *)params, "field");
    if (!field_json) {
        field_json = cJSON_GetObjectItemCaseSensitive((cJSON *)params, "name");
    }
    if (!cJSON_IsString(field_json) || !field_json->valuestring || field_json->valuestring[0] == '\0') {
        return NULL;
    }
    if (pthread_mutex_lock(&state->mutex) != 0) {
        return NULL;
    }

    const ms2d_field_t *field = ms2d_find_field(state, field_json->valuestring);
    if (!field) {
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    double value = ms2d_decode_field(state, field);
    uint64_t ts = rpc_update_last_poll_timestamp();

    cJSON *result = cJSON_CreateObject();
    if (result
        && cJSON_AddStringToObject(result, "name", field->name)
        && cJSON_AddNumberToObject(result, "value", value)
        && cJSON_AddStringToObject(result, "units", field->units)
        && cJSON_AddNumberToObject(result, "last_poll_timestamp_ms", (double)ts)) {
        pthread_mutex_unlock(&state->mutex);
        return result;
    }

    cJSON_Delete(result);
    pthread_mutex_unlock(&state->mutex);
    return NULL;
}

static cJSON *rpc_method_get_values(ms2d_state_t *state, const cJSON *params)
{
    if (!cJSON_IsObject(params)) {
        return NULL;
    }

    const cJSON *fields = cJSON_GetObjectItemCaseSensitive((cJSON *)params, "fields");
    if (!fields) {
        fields = cJSON_GetObjectItemCaseSensitive((cJSON *)params, "names");
    }
    if (!cJSON_IsArray(fields)) {
        return NULL;
    }
    if (pthread_mutex_lock(&state->mutex) != 0) {
        return NULL;
    }

    cJSON *result = cJSON_CreateObject();
    cJSON *values = cJSON_CreateArray();
    if (!result || !values) {
        cJSON_Delete(result);
        cJSON_Delete(values);
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    cJSON *field_item = NULL;
    cJSON_ArrayForEach(field_item, (cJSON *)fields) {
        if (!cJSON_IsString(field_item) || !field_item->valuestring) {
            cJSON_Delete(result);
            cJSON_Delete(values);
            pthread_mutex_unlock(&state->mutex);
            return NULL;
        }

        const ms2d_field_t *field = ms2d_find_field(state, field_item->valuestring);
        if (!field) {
            cJSON_Delete(result);
            cJSON_Delete(values);
            pthread_mutex_unlock(&state->mutex);
            return NULL;
        }

        cJSON *value_obj = cJSON_CreateObject();
        if (!value_obj) {
            cJSON_Delete(result);
            cJSON_Delete(values);
            pthread_mutex_unlock(&state->mutex);
            return NULL;
        }

        if (!cJSON_AddStringToObject(value_obj, "name", field->name)
            || !cJSON_AddNumberToObject(value_obj, "value", ms2d_decode_field(state, field))
            || !cJSON_AddStringToObject(value_obj, "units", field->units)
            || !cJSON_AddItemToArray(values, value_obj)) {
            cJSON_Delete(value_obj);
            cJSON_Delete(result);
            cJSON_Delete(values);
            pthread_mutex_unlock(&state->mutex);
            return NULL;
        }
    }

    uint64_t ts = rpc_update_last_poll_timestamp();
    int ok = cJSON_AddItemToObject(result, "values", values)
             && cJSON_AddNumberToObject(result, "last_poll_timestamp_ms", (double)ts);
    pthread_mutex_unlock(&state->mutex);

    if (!ok) {
        cJSON_Delete(result);
        return NULL;
    }

    return result;
}

static cJSON *rpc_method_get_all(ms2d_state_t *state)
{
    if (pthread_mutex_lock(&state->mutex) != 0) {
        return NULL;
    }

    if (!state->fields || state->num_fields == 0) {
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    ms2d_value_t *decoded = calloc(state->num_fields, sizeof(ms2d_value_t));
    if (!decoded) {
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    int count = 0;
    ms2d_error_t err = ms2d_decode_all(state, decoded, &count);
    if (err != MS2D_SUCCESS || count < 0) {
        free(decoded);
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    cJSON *result = cJSON_CreateObject();
    cJSON *values = cJSON_CreateArray();
    if (!result || !values) {
        cJSON_Delete(result);
        cJSON_Delete(values);
        free(decoded);
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    for (int i = 0; i < count; i++) {
        cJSON *value_obj = cJSON_CreateObject();
        if (!value_obj
            || !cJSON_AddStringToObject(value_obj, "name", decoded[i].name)
            || !cJSON_AddNumberToObject(value_obj, "value", decoded[i].value)
            || !cJSON_AddStringToObject(value_obj, "units", decoded[i].units)
            || !cJSON_AddItemToArray(values, value_obj)) {
            cJSON_Delete(value_obj);
            cJSON_Delete(result);
            cJSON_Delete(values);
            free(decoded);
            pthread_mutex_unlock(&state->mutex);
            return NULL;
        }
    }

    uint64_t ts = rpc_update_last_poll_timestamp();
    int ok = cJSON_AddItemToObject(result, "values", values)
             && cJSON_AddNumberToObject(result, "last_poll_timestamp_ms", (double)ts);
    free(decoded);
    pthread_mutex_unlock(&state->mutex);

    if (!ok) {
        cJSON_Delete(result);
        return NULL;
    }

    return result;
}

static cJSON *rpc_method_list_fields(ms2d_state_t *state)
{
    if (pthread_mutex_lock(&state->mutex) != 0) {
        return NULL;
    }

    cJSON *fields = cJSON_CreateArray();
    if (!fields) {
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    for (uint16_t i = 0; i < state->num_fields; i++) {
        cJSON *name = cJSON_CreateString(state->fields[i].name);
        if (!name || !cJSON_AddItemToArray(fields, name)) {
            cJSON_Delete(name);
            cJSON_Delete(fields);
            pthread_mutex_unlock(&state->mutex);
            return NULL;
        }
    }

    pthread_mutex_unlock(&state->mutex);
    return fields;
}

static cJSON *rpc_method_get_status(ms2d_state_t *state)
{
    cJSON *result = cJSON_CreateObject();
    if (!result) {
        return NULL;
    }

    pthread_mutex_lock(&g_rpc_mutex);
    uint64_t request_count = g_rpc_request_count;
    uint64_t ts = g_rpc_last_poll_timestamp_ms;
    char signature[sizeof(g_rpc_signature)];
    memcpy(signature, g_rpc_signature, sizeof(signature));
    pthread_mutex_unlock(&g_rpc_mutex);

    int connected = 0;
    if (pthread_mutex_lock(&state->mutex) == 0) {
        connected = (state->serial_fd >= 0) ? 1 : 0;
        pthread_mutex_unlock(&state->mutex);
    }

    if (!cJSON_AddBoolToObject(result, "connected", connected)
        || !cJSON_AddStringToObject(result, "signature", signature)
        || !cJSON_AddNumberToObject(result, "request_count", (double)request_count)
        || !cJSON_AddNumberToObject(result, "last_poll_timestamp_ms", (double)ts)) {
        cJSON_Delete(result);
        return NULL;
    }

    return result;
}

ms2d_error_t ms2d_rpc_init(ms2d_state_t *state)
{
    if (!state) {
        return MS2D_ERROR_INVALID_ARG;
    }

    const char *env_path = getenv("MS2D_RPC_SOCKET_PATH");
    if (env_path && env_path[0] != '\0') {
        strncpy(g_rpc_socket_path, env_path, sizeof(g_rpc_socket_path) - 1);
        g_rpc_socket_path[sizeof(g_rpc_socket_path) - 1] = '\0';
    } else {
        strncpy(g_rpc_socket_path, MS2D_RPC_DEFAULT_SOCKET_PATH, sizeof(g_rpc_socket_path) - 1);
        g_rpc_socket_path[sizeof(g_rpc_socket_path) - 1] = '\0';
    }

    if (g_rpc_server_fd >= 0) {
        close(g_rpc_server_fd);
        g_rpc_server_fd = -1;
    }

    unlink(g_rpc_socket_path);

    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        return MS2D_ERROR_IO;
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, g_rpc_socket_path, sizeof(addr.sun_path) - 1);

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        return MS2D_ERROR_IO;
    }

    if (listen(fd, MS2D_RPC_BACKLOG) < 0) {
        close(fd);
        unlink(g_rpc_socket_path);
        return MS2D_ERROR_IO;
    }

    ms2d_error_t nb_err = rpc_make_nonblocking(fd);
    if (nb_err != MS2D_SUCCESS) {
        close(fd);
        unlink(g_rpc_socket_path);
        return nb_err;
    }

    pthread_mutex_lock(&g_rpc_mutex);
    g_rpc_request_count = 0;
    g_rpc_last_poll_timestamp_ms = ms2d_timestamp_ms();
    strncpy(g_rpc_signature, "unknown", sizeof(g_rpc_signature) - 1);
    g_rpc_signature[sizeof(g_rpc_signature) - 1] = '\0';
    pthread_mutex_unlock(&g_rpc_mutex);

    g_rpc_server_fd = fd;
    return MS2D_SUCCESS;
}

ms2d_error_t ms2d_rpc_handle(ms2d_state_t *state, int client_fd)
{
    if (!state || client_fd < 0) {
        return MS2D_ERROR_INVALID_ARG;
    }

    char request_buf[MS2D_RPC_MAX_REQUEST_SIZE + 1];
    ssize_t received = recv(client_fd, request_buf, MS2D_RPC_MAX_REQUEST_SIZE, 0);
    if (received <= 0) {
        return MS2D_ERROR_IO;
    }

    request_buf[received] = '\0';

    char *json_payload = NULL;
    size_t json_len = 0;
    if (!rpc_extract_json_body(request_buf, (size_t)received, &json_payload, &json_len)) {
        cJSON *err = rpc_make_error_response(NULL, -32700, "Parse error");
        char *out = err ? cJSON_PrintUnformatted(err) : NULL;
        if (out) {
            rpc_write_response(client_fd, request_buf, (size_t)received, out);
        }
        free(out);
        cJSON_Delete(err);
        return MS2D_ERROR_PARSE;
    }

    char *json_copy = calloc(json_len + 1, 1);
    if (!json_copy) {
        return MS2D_ERROR_MEMORY;
    }
    memcpy(json_copy, json_payload, json_len);

    cJSON *request = cJSON_Parse(json_copy);
    free(json_copy);

    cJSON *response = NULL;
    const cJSON *id = NULL;

    if (!request) {
        response = rpc_make_error_response(NULL, -32700, "Parse error");
    } else if (!cJSON_IsObject(request)) {
        response = rpc_make_error_response(NULL, -32600, "Invalid Request");
    } else {
        id = cJSON_GetObjectItemCaseSensitive(request, "id");
        const cJSON *method = cJSON_GetObjectItemCaseSensitive(request, "method");
        const cJSON *params = cJSON_GetObjectItemCaseSensitive(request, "params");

        if (!id || !method || !cJSON_IsString(method) || !method->valuestring) {
            response = rpc_make_error_response(id, -32600, "Invalid Request");
        } else {
            (void)rpc_increment_request_count();

            if (strcmp(method->valuestring, "get_value") == 0) {
                cJSON *result = rpc_method_get_value(state, params);
                response = result ? rpc_make_result_response(id, result)
                                  : rpc_make_error_response(id, -32602, "Invalid params");
            } else if (strcmp(method->valuestring, "get_values") == 0) {
                cJSON *result = rpc_method_get_values(state, params);
                response = result ? rpc_make_result_response(id, result)
                                  : rpc_make_error_response(id, -32602, "Invalid params");
            } else if (strcmp(method->valuestring, "get_all") == 0) {
                cJSON *result = rpc_method_get_all(state);
                response = result ? rpc_make_result_response(id, result)
                                  : rpc_make_error_response(id, -32602, "Invalid params");
            } else if (strcmp(method->valuestring, "list_fields") == 0) {
                cJSON *result = rpc_method_list_fields(state);
                response = result ? rpc_make_result_response(id, result)
                                  : rpc_make_error_response(id, -32602, "Invalid params");
            } else if (strcmp(method->valuestring, "get_status") == 0) {
                cJSON *result = rpc_method_get_status(state);
                response = result ? rpc_make_result_response(id, result)
                                  : rpc_make_error_response(id, -32602, "Invalid params");
            } else {
                response = rpc_make_error_response(id, -32601, "Method not found");
            }
        }
    }

    if (response) {
        (void)cJSON_AddNumberToObject(response,
                                      "last_poll_timestamp_ms",
                                      (double)rpc_get_last_poll_timestamp());
    }

    char *json_out = response ? cJSON_PrintUnformatted(response) : NULL;
    ms2d_error_t write_err = MS2D_SUCCESS;
    if (!json_out) {
        write_err = MS2D_ERROR_MEMORY;
    } else {
        write_err = rpc_write_response(client_fd, request_buf, (size_t)received, json_out);
    }

    free(json_out);
    cJSON_Delete(response);
    cJSON_Delete(request);

    return write_err;
}

ms2d_error_t ms2d_rpc_accept(ms2d_state_t *state)
{
    if (!state || g_rpc_server_fd < 0) {
        return MS2D_ERROR_INVALID_ARG;
    }

    int client_fd = accept(g_rpc_server_fd, NULL, NULL);
    if (client_fd < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return MS2D_ERROR_TIMEOUT;
        }
        return MS2D_ERROR_IO;
    }

    ms2d_error_t err = ms2d_rpc_handle(state, client_fd);
    close(client_fd);
    return err;
}

void ms2d_rpc_shutdown(ms2d_state_t *state)
{
    (void)state;

    if (g_rpc_server_fd >= 0) {
        close(g_rpc_server_fd);
        g_rpc_server_fd = -1;
    }

    if (g_rpc_socket_path[0] != '\0') {
        unlink(g_rpc_socket_path);
    }
}

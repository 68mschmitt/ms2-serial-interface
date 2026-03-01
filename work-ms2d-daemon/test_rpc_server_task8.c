#define _POSIX_C_SOURCE 200809L

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "ms2d/include/ms2d.h"

ms2d_error_t ms2d_ini_parse(const char *path, ms2d_state_t *state);
ms2d_error_t ms2d_rpc_init(ms2d_state_t *state);
ms2d_error_t ms2d_rpc_accept(ms2d_state_t *state);
void ms2d_rpc_shutdown(ms2d_state_t *state);

int main(int argc, char **argv)
{
    const char *socket_path = (argc > 1) ? argv[1] : "/tmp/ms2d_test.sock";
    const char *ini_path = (argc > 2)
                               ? argv[2]
                               : "/home/mschmitt/projects/tmp/miata/work-ms2d-daemon/cfg.ini";

    if (setenv("MS2D_RPC_SOCKET_PATH", socket_path, 1) != 0) {
        fprintf(stderr, "failed to set socket path env\n");
        return 1;
    }

    ms2d_state_t state;
    memset(&state, 0, sizeof(state));
    state.serial_fd = -1;
    if (pthread_mutex_init(&state.mutex, NULL) != 0) {
        fprintf(stderr, "failed to init mutex\n");
        return 1;
    }

    ms2d_error_t parse_err = ms2d_ini_parse(ini_path, &state);
    if (parse_err != MS2D_SUCCESS) {
        fprintf(stderr, "ini parse failed: %d\n", parse_err);
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }

    state.outpc_buffer = calloc(state.outpc_size ? state.outpc_size : 256, 1);
    if (!state.outpc_buffer) {
        fprintf(stderr, "failed to allocate outpc buffer\n");
        free(state.fields);
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }

    state.outpc_len = state.outpc_size;
    for (size_t i = 0; i < state.outpc_len; i++) {
        state.outpc_buffer[i] = (uint8_t)(i & 0xFFU);
    }

    ms2d_error_t init_err = ms2d_rpc_init(&state);
    if (init_err != MS2D_SUCCESS) {
        fprintf(stderr, "rpc init failed: %d\n", init_err);
        free(state.outpc_buffer);
        free(state.fields);
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }

    fprintf(stdout, "rpc test server ready: %s\n", socket_path);
    fflush(stdout);

    int handled = 0;
    const int max_requests = 16;
    const uint64_t start_ms = ms2d_timestamp_ms();

    while (handled < max_requests) {
        ms2d_error_t accept_err = ms2d_rpc_accept(&state);
        if (accept_err == MS2D_SUCCESS) {
            handled++;
            continue;
        }

        if (accept_err != MS2D_ERROR_TIMEOUT) {
            fprintf(stderr, "rpc accept failed: %d\n", accept_err);
            break;
        }

        if (ms2d_timestamp_ms() - start_ms > 15000) {
            break;
        }

        struct timespec ts = {.tv_sec = 0, .tv_nsec = 10 * 1000 * 1000};
        nanosleep(&ts, NULL);
    }

    ms2d_rpc_shutdown(&state);
    free(state.outpc_buffer);
    free(state.fields);
    pthread_mutex_destroy(&state.mutex);
    return 0;
}

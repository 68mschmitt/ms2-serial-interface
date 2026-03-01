#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <termios.h>
#include <unistd.h>

#include "../include/ms2d.h"

#define MS2D_SERIAL_TIMEOUT_MS 1000U
#define MS2D_SERIAL_MAX_FRAME 4096U

static ms2d_error_t ms2d_wait_fd(int fd, int want_write, uint32_t timeout_ms)
{
    fd_set fds;
    struct timeval tv;

    FD_ZERO(&fds);
    FD_SET(fd, &fds);

    tv.tv_sec = (time_t)(timeout_ms / 1000U);
    tv.tv_usec = (suseconds_t)((timeout_ms % 1000U) * 1000U);

    int rc = select(fd + 1,
                    want_write ? NULL : &fds,
                    want_write ? &fds : NULL,
                    NULL,
                    &tv);
    if (rc == 0) {
        return MS2D_ERROR_TIMEOUT;
    }
    if (rc < 0) {
        return (errno == EINTR) ? MS2D_ERROR_TIMEOUT : MS2D_ERROR_IO;
    }
    return MS2D_SUCCESS;
}

static ms2d_error_t ms2d_write_exact(int fd, const uint8_t *buf, size_t len, uint32_t timeout_ms)
{
    size_t written = 0;
    while (written < len) {
        ms2d_error_t wait_err = ms2d_wait_fd(fd, 1, timeout_ms);
        if (wait_err != MS2D_SUCCESS) {
            return wait_err;
        }

        ssize_t rc = write(fd, buf + written, len - written);
        if (rc < 0) {
            if (errno == EINTR) {
                continue;
            }
            return MS2D_ERROR_IO;
        }
        if (rc == 0) {
            return MS2D_ERROR_IO;
        }

        written += (size_t)rc;
    }

    return MS2D_SUCCESS;
}

static ms2d_error_t ms2d_read_exact(int fd, uint8_t *buf, size_t len, uint32_t timeout_ms)
{
    size_t read_total = 0;
    while (read_total < len) {
        ms2d_error_t wait_err = ms2d_wait_fd(fd, 0, timeout_ms);
        if (wait_err != MS2D_SUCCESS) {
            return wait_err;
        }

        ssize_t rc = read(fd, buf + read_total, len - read_total);
        if (rc < 0) {
            if (errno == EINTR) {
                continue;
            }
            return MS2D_ERROR_IO;
        }
        if (rc == 0) {
            return MS2D_ERROR_IO;
        }

        read_total += (size_t)rc;
    }

    return MS2D_SUCCESS;
}

static speed_t ms2d_baud_to_speed(uint32_t baud_rate)
{
    switch (baud_rate) {
        case 115200:
            return B115200;
        case 57600:
            return B57600;
        case 38400:
            return B38400;
        case 19200:
            return B19200;
        case 9600:
            return B9600;
        default:
            return 0;
    }
}

ms2d_error_t ms2d_serial_open(ms2d_state_t *state)
{
    if (!state || state->config.serial_port[0] == '\0') {
        return MS2D_ERROR_INVALID_ARG;
    }

    uint32_t baud = state->config.baud_rate ? state->config.baud_rate : 115200U;
    speed_t speed = ms2d_baud_to_speed(baud);
    if (speed == 0) {
        return MS2D_ERROR_CONFIG;
    }

    int fd = open(state->config.serial_port, O_RDWR | O_NOCTTY);
    if (fd < 0) {
        return MS2D_ERROR_SERIAL;
    }

    struct termios tty;
    if (tcgetattr(fd, &tty) != 0) {
        close(fd);
        return MS2D_ERROR_SERIAL;
    }

    cfmakeraw(&tty);
    tty.c_cflag |= (CLOCAL | CREAD);
    tty.c_cflag &= ~CSIZE;
    tty.c_cflag |= CS8;
    tty.c_cflag &= ~PARENB;
    tty.c_cflag &= ~CSTOPB;
#ifdef CRTSCTS
    tty.c_cflag &= ~CRTSCTS;
#endif
    tty.c_iflag &= ~(IXON | IXOFF | IXANY);
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;

    if (cfsetispeed(&tty, speed) != 0 || cfsetospeed(&tty, speed) != 0) {
        close(fd);
        return MS2D_ERROR_SERIAL;
    }

    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        close(fd);
        return MS2D_ERROR_SERIAL;
    }

    tcflush(fd, TCIOFLUSH);
    state->serial_fd = fd;
    return MS2D_SUCCESS;
}

ms2d_error_t ms2d_serial_close(ms2d_state_t *state)
{
    if (!state) {
        return MS2D_ERROR_INVALID_ARG;
    }

    if (state->serial_fd >= 0) {
        if (close(state->serial_fd) != 0) {
            return MS2D_ERROR_SERIAL;
        }
    }

    state->serial_fd = -1;
    return MS2D_SUCCESS;
}

ms2d_error_t ms2d_serial_send(ms2d_state_t *state,
                              const uint8_t *cmd,
                              size_t len,
                              uint8_t *response,
                              size_t *resp_len)
{
    if (!state || !cmd || len == 0 || !response || !resp_len || state->serial_fd < 0) {
        return MS2D_ERROR_INVALID_ARG;
    }

    if (len > 0xFFFFU || *resp_len < 2U) {
        return MS2D_ERROR_INVALID_ARG;
    }

    uint8_t request[2 + MS2D_SERIAL_MAX_FRAME + 4];
    if (len > MS2D_SERIAL_MAX_FRAME) {
        return MS2D_ERROR_INVALID_ARG;
    }

    request[0] = (uint8_t)((len >> 8) & 0xFFU);
    request[1] = (uint8_t)(len & 0xFFU);
    memcpy(request + 2, cmd, len);

    uint32_t req_crc = ms2d_crc32(cmd, len);
    request[2 + len + 0] = (uint8_t)((req_crc >> 24) & 0xFFU);
    request[2 + len + 1] = (uint8_t)((req_crc >> 16) & 0xFFU);
    request[2 + len + 2] = (uint8_t)((req_crc >> 8) & 0xFFU);
    request[2 + len + 3] = (uint8_t)(req_crc & 0xFFU);

    ms2d_error_t err = ms2d_write_exact(state->serial_fd, request, 2 + len + 4, MS2D_SERIAL_TIMEOUT_MS);
    if (err != MS2D_SUCCESS) {
        return err;
    }

    uint8_t header[2];
    err = ms2d_read_exact(state->serial_fd, header, sizeof(header), MS2D_SERIAL_TIMEOUT_MS);
    if (err != MS2D_SUCCESS) {
        return err;
    }

    size_t frame_len = ((size_t)header[0] << 8) | (size_t)header[1];
    if (frame_len == 0 || frame_len > MS2D_SERIAL_MAX_FRAME) {
        return MS2D_ERROR_PARSE;
    }

    uint8_t frame[MS2D_SERIAL_MAX_FRAME];
    err = ms2d_read_exact(state->serial_fd, frame, frame_len, MS2D_SERIAL_TIMEOUT_MS);
    if (err != MS2D_SUCCESS) {
        return err;
    }

    uint8_t crc_bytes[4];
    err = ms2d_read_exact(state->serial_fd, crc_bytes, sizeof(crc_bytes), MS2D_SERIAL_TIMEOUT_MS);
    if (err != MS2D_SUCCESS) {
        return err;
    }

    uint32_t crc_rx = ((uint32_t)crc_bytes[0] << 24)
                    | ((uint32_t)crc_bytes[1] << 16)
                    | ((uint32_t)crc_bytes[2] << 8)
                    | (uint32_t)crc_bytes[3];
    uint32_t crc_calc = ms2d_crc32(frame, frame_len);
    if (crc_rx != crc_calc) {
        return MS2D_ERROR_PARSE;
    }

    if (*resp_len < frame_len) {
        return MS2D_ERROR_MEMORY;
    }

    memcpy(response, frame, frame_len);
    *resp_len = frame_len;
    return MS2D_SUCCESS;
}

ms2d_error_t ms2d_serial_query_signature(ms2d_state_t *state)
{
    uint8_t response[512];
    size_t response_len = sizeof(response);
    const uint8_t cmd = (uint8_t)'Q';

    ms2d_error_t err = ms2d_serial_send(state, &cmd, 1, response, &response_len);
    if (err != MS2D_SUCCESS) {
        return err;
    }

    if (response_len < 2 || response[0] != 0x00U) {
        return MS2D_ERROR_PARSE;
    }

    size_t sig_len = response_len - 1;
    char signature[511];
    if (sig_len >= sizeof(signature)) {
        sig_len = sizeof(signature) - 1;
    }

    memcpy(signature, response + 1, sig_len);
    signature[sig_len] = '\0';

    if (strstr(signature, "MS2Extra") == NULL) {
        return MS2D_ERROR_PARSE;
    }

    return MS2D_SUCCESS;
}

ms2d_error_t ms2d_serial_poll_outpc(ms2d_state_t *state)
{
    if (!state) {
        return MS2D_ERROR_INVALID_ARG;
    }

    uint8_t response[MS2D_SERIAL_MAX_FRAME];
    size_t response_len = sizeof(response);
    const uint8_t cmd = (uint8_t)'A';

    ms2d_error_t err = ms2d_serial_send(state, &cmd, 1, response, &response_len);
    if (err != MS2D_SUCCESS) {
        return err;
    }

    if (response_len < 1 || response[0] != 0x01U) {
        return MS2D_ERROR_PARSE;
    }

    size_t outpc_len = response_len - 1;

    err = pthread_mutex_lock(&state->mutex) == 0 ? MS2D_SUCCESS : MS2D_ERROR_THREAD;
    if (err != MS2D_SUCCESS) {
        return err;
    }

    if (!state->outpc_buffer || state->outpc_size < outpc_len) {
        uint8_t *new_buffer = realloc(state->outpc_buffer, outpc_len);
        if (!new_buffer) {
            pthread_mutex_unlock(&state->mutex);
            return MS2D_ERROR_MEMORY;
        }
        state->outpc_buffer = new_buffer;
        state->outpc_size = outpc_len;
    }

    memcpy(state->outpc_buffer, response + 1, outpc_len);
    state->outpc_len = outpc_len;

    if (pthread_mutex_unlock(&state->mutex) != 0) {
        return MS2D_ERROR_THREAD;
    }

    return MS2D_SUCCESS;
}

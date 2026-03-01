#ifndef MS2D_SERIAL_COMM_H
#define MS2D_SERIAL_COMM_H

#include "ms2d.h"

/**
 * Open serial port connection
 * 
 * @param state Daemon state (config.serial_port and config.baud_rate must be set)
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_serial_open(ms2d_state_t *state);

/**
 * Close serial port connection
 * 
 * @param state Daemon state
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_serial_close(ms2d_state_t *state);

/**
 * Read data from serial port
 * 
 * @param fd File descriptor
 * @param buffer Buffer to read into
 * @param size Maximum bytes to read
 * @param timeout_ms Timeout in milliseconds
 * @return Number of bytes read, negative error code on failure
 */
int ms2d_serial_read(int fd, uint8_t *buffer, size_t size, uint32_t timeout_ms);

/**
 * Write data to serial port
 * 
 * @param fd File descriptor
 * @param buffer Data to write
 * @param size Number of bytes to write
 * @return Number of bytes written, negative error code on failure
 */
int ms2d_serial_write(int fd, const uint8_t *buffer, size_t size);

/**
 * Flush serial port buffers
 * 
 * @param fd File descriptor
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_serial_flush(int fd);

/**
 * Set serial port parameters
 * 
 * @param fd File descriptor
 * @param baud_rate Baud rate
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_serial_set_params(int fd, uint32_t baud_rate);

/**
 * Poll ECU for OUTPC data
 * 
 * @param state Daemon state
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_serial_poll_outpc(ms2d_state_t *state);

#endif /* MS2D_SERIAL_COMM_H */

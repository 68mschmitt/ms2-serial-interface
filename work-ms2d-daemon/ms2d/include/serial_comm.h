#ifndef MS2D_SERIAL_COMM_H
#define MS2D_SERIAL_COMM_H

#include "ms2d.h"

/**
 * Open serial port connection
 * 
 * @param port Serial port path (e.g., /dev/ttyUSB0)
 * @param baud_rate Baud rate (e.g., 115200)
 * @return File descriptor on success, negative error code on failure
 */
int ms2d_serial_open(const char *port, uint32_t baud_rate);

/**
 * Close serial port connection
 * 
 * @param fd File descriptor
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_serial_close(int fd);

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

#endif /* MS2D_SERIAL_COMM_H */

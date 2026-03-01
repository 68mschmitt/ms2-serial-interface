#ifndef MS2_CLIENT_H
#define MS2_CLIENT_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * MS2D C Client Library
 * 
 * This library provides a simple C API for communicating with the ms2d daemon
 * over Unix sockets using JSON-RPC 2.0 protocol.
 */

/**
 * Opaque client handle.
 * Do not access fields directly - use provided API functions.
 */
typedef struct ms2_client ms2_client_t;

/**
 * Connect to ms2d daemon at the specified Unix socket path.
 * 
 * @param socket_path Path to Unix socket (e.g., "/tmp/ms2d.sock")
 * @return Client handle on success, NULL on error
 */
ms2_client_t *ms2_connect(const char *socket_path);

/**
 * Disconnect from daemon and free client resources.
 * 
 * @param client Client handle returned by ms2_connect()
 */
void ms2_disconnect(ms2_client_t *client);

/**
 * Get the current value of a single field.
 * 
 * @param client Client handle
 * @param field Field name (e.g., "rpm", "batteryVoltage")
 * @return Field value, or 0.0 on error
 */
double ms2_get_value(ms2_client_t *client, const char *field);

/**
 * Get values for multiple fields in a single request.
 * 
 * @param client Client handle
 * @param fields Array of field names
 * @param count Number of fields in array
 * @param values Output array to store values (must be allocated by caller)
 * @return 0 on success, -1 on error
 */
int ms2_get_values(ms2_client_t *client, const char **fields, int count, double *values);

/**
 * List all available field names.
 * 
 * @param client Client handle
 * @param count Output parameter to store number of fields
 * @return Array of field name strings (caller must free with ms2_free_fields), NULL on error
 */
char **ms2_list_fields(ms2_client_t *client, int *count);

/**
 * Get daemon status information.
 * 
 * @param client Client handle
 * @param connected Output parameter for connection status (0=disconnected, 1=connected)
 * @param signature Output buffer for ECU signature string
 * @param sig_len Size of signature buffer
 * @return 0 on success, -1 on error
 */
int ms2_get_status(ms2_client_t *client, int *connected, char *signature, size_t sig_len);

/**
 * Free field names array returned by ms2_list_fields().
 * 
 * @param fields Array returned by ms2_list_fields()
 * @param count Number of fields in array
 */
void ms2_free_fields(char **fields, int count);

#ifdef __cplusplus
}
#endif

#endif /* MS2_CLIENT_H */

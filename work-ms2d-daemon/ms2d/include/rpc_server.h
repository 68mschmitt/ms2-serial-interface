#ifndef MS2D_RPC_SERVER_H
#define MS2D_RPC_SERVER_H

#include "ms2d.h"

/**
 * Start RPC server
 * 
 * @param state Daemon state
 * @param port TCP port to listen on
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_start(ms2d_state_t *state, uint16_t port);

/**
 * Stop RPC server
 * 
 * @param state Daemon state
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_stop(ms2d_state_t *state);

/**
 * Handle RPC request
 * 
 * @param state Daemon state
 * @param request Request buffer
 * @param request_len Request length
 * @param response Response buffer (allocated by function)
 * @param response_len Pointer to store response length
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_handle_request(ms2d_state_t *state, const uint8_t *request, 
                                      size_t request_len, uint8_t **response, size_t *response_len);

/**
 * Get field value via RPC
 * 
 * @param state Daemon state
 * @param field_name Field name to retrieve
 * @param value Pointer to store value
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_get_field(ms2d_state_t *state, const char *field_name, ms2d_value_t *value);

/**
 * Get all field values via RPC
 * 
 * @param state Daemon state
 * @param values Pointer to value array (allocated by function)
 * @param num_values Pointer to store number of values
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_get_all_fields(ms2d_state_t *state, ms2d_value_t **values, uint16_t *num_values);

/**
 * Send CAN command via RPC
 * 
 * @param state Daemon state
 * @param can_id CAN ID
 * @param data CAN data bytes
 * @param data_len Length of data
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_send_can_command(ms2d_state_t *state, uint16_t can_id, 
                                        const uint8_t *data, size_t data_len);

/**
 * Initialize RPC server
 * 
 * @param state Daemon state
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_init(ms2d_state_t *state);

/**
 * Accept new RPC client connection (non-blocking)
 * 
 * @param state Daemon state
 * @return MS2D_SUCCESS on success, MS2D_ERROR_TIMEOUT if no client, error code otherwise
 */
ms2d_error_t ms2d_rpc_accept(ms2d_state_t *state);

/**
 * Handle RPC requests from client
 * 
 * @param state Daemon state
 * @param client_fd Client file descriptor
 * @return MS2D_SUCCESS on success, error code otherwise
 */
ms2d_error_t ms2d_rpc_handle(ms2d_state_t *state, int client_fd);

/**
 * Shutdown RPC server and clean up resources
 * 
 * @param state Daemon state
 */
void ms2d_rpc_shutdown(ms2d_state_t *state);

#endif /* MS2D_RPC_SERVER_H */

/**
 * MS2D Client - Node.js client for ms2d daemon
 * 
 * Implements JSON-RPC 2.0 over Unix socket communication with ms2d daemon.
 * No external dependencies - uses only Node.js built-in modules.
 * 
 * Note: The daemon closes the connection after each request, so each RPC call
 * establishes a new connection.
 */

const net = require('net');

/**
 * MS2Client - JSON-RPC client for ms2d daemon
 */
class MS2Client {
  /**
   * Create a new MS2Client instance
   * @param {string} socketPath - Path to Unix socket (default: /tmp/ms2d.sock)
   */
  constructor(socketPath = '/tmp/ms2d.sock') {
    this.socketPath = socketPath;
    this.requestId = 0;
  }

  /**
   * Connect to the ms2d daemon (for compatibility, but not required)
   * @returns {Promise<void>}
   */
  async connect() {
    // Connection is established per-request, so this is a no-op
    return Promise.resolve();
  }

  /**
   * Disconnect from the ms2d daemon (for compatibility, but not required)
   * @returns {Promise<void>}
   */
  async disconnect() {
    // No persistent connection to close
    return Promise.resolve();
  }

  /**
   * Get a single field value
   * @param {string} field - Field name
   * @returns {Promise<Object>} Object with {name, value, units, last_poll_timestamp_ms}
   */
  async getValue(field) {
    const response = await this._rpcCall('get_value', { name: field });
    return response;
  }

  /**
   * Get multiple field values
   * @param {string[]} fields - Array of field names
   * @returns {Promise<Object>} Object with {values: [...], last_poll_timestamp_ms}
   */
  async getValues(fields) {
    const response = await this._rpcCall('get_values', { names: fields });
    return response;
  }

  /**
   * Get all field values
   * @returns {Promise<Object>} Object with {values: [...], last_poll_timestamp_ms}
   */
  async getAll() {
    const response = await this._rpcCall('get_all', {});
    return response;
  }

  /**
   * List all available field names
   * @returns {Promise<string[]>} Array of field names
   */
  async listFields() {
    const response = await this._rpcCall('list_fields', {});
    return response;
  }

  /**
   * Get daemon status
   * @returns {Promise<Object>} Object with {connected, signature, request_count, last_poll_timestamp_ms}
   */
  async getStatus() {
    const response = await this._rpcCall('get_status', {});
    return response;
  }

  /**
   * Internal: Send JSON-RPC request and wait for response
   * Establishes a new connection for each request (daemon closes after each request)
   * @private
   * @param {string} method - RPC method name
   * @param {Object} params - Method parameters
   * @returns {Promise<*>} RPC result
   */
  async _rpcCall(method, params) {
    const id = ++this.requestId;
    const request = {
      jsonrpc: '2.0',
      method: method,
      params: params,
      id: id
    };

    return new Promise((resolve, reject) => {
      // Create new connection for this request
      const socket = net.createConnection(this.socketPath);
      let responseReceived = false;
      let buffer = '';

      // Handle connection errors
      socket.on('error', (err) => {
        if (!responseReceived) {
          reject(err);
        }
      });

      // Handle incoming data
      socket.on('data', (data) => {
        buffer += data.toString();
        
        // Try to parse complete JSON lines
        const lines = buffer.split('\n');
        
        // Keep the last incomplete line in the buffer
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (!line.trim()) continue;
          
          try {
            const response = JSON.parse(line);
            
            // Check if this is a response to our request
            if (response.id === id) {
              responseReceived = true;
              socket.destroy();
              
              // Handle error response
              if (response.error) {
                reject(new Error(`RPC error: ${response.error.message} (code: ${response.error.code})`));
              } else {
                // Return result
                resolve(response.result);
              }
              return;
            }
          } catch (err) {
            // Ignore parse errors
          }
        }
      });

      // Handle socket close
      socket.on('close', () => {
        if (!responseReceived) {
          // Try to parse any remaining buffer content (response might not have newline)
          if (buffer.trim()) {
            try {
              const response = JSON.parse(buffer);
              if (response.id === id) {
                responseReceived = true;
                if (response.error) {
                  reject(new Error(`RPC error: ${response.error.message} (code: ${response.error.code})`));
                } else {
                  resolve(response.result);
                }
                return;
              }
            } catch (err) {
              // Ignore parse errors
            }
          }
          reject(new Error('Socket closed without response'));
        }
      });

      // Set connection timeout
      socket.setTimeout(5000, () => {
        socket.destroy();
        if (!responseReceived) {
          reject(new Error(`RPC timeout for method: ${method}`));
        }
      });

      // Send request when connected
      socket.on('connect', () => {
        const payload = JSON.stringify(request) + '\n';
        socket.write(payload, (err) => {
          if (err && !responseReceived) {
            reject(err);
          }
        });
      });
    });
  }
}

/**
 * Convenience function to create and connect a client
 * @param {string} socketPath - Path to Unix socket
 * @returns {Promise<MS2Client>} Connected client instance
 */
async function connect(socketPath = '/tmp/ms2d.sock') {
  const client = new MS2Client(socketPath);
  await client.connect();
  return client;
}

module.exports = { MS2Client, connect };

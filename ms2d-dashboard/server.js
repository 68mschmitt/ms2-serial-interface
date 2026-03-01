#!/usr/bin/env node
/**
 * MS2D Dashboard Server
 * Bridges the Unix socket client to HTTP for browser access
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

// Import the ms2d client (adjust path as needed)
const MS2_CLIENT_PATH = '../work-ms2d-daemon/ms2d/clients/ms2_client.js';
const { MS2Client } = require(MS2_CLIENT_PATH);

const PORT = 3000;
const SOCKET_PATH = process.argv[2] || '/tmp/ms2d.sock';

let client = null;
let connected = false;

// Connect to daemon
async function connectClient() {
  if (client && connected) return true;
  
  try {
    client = new MS2Client(SOCKET_PATH);
    await client.connect();
    connected = true;
    console.log(`Connected to ms2d daemon at ${SOCKET_PATH}`);
    return true;
  } catch (err) {
    console.error('Failed to connect:', err.message);
    connected = false;
    return false;
  }
}

// MIME types for static files
const MIME_TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
};

// Serve static files from public/
function serveStatic(req, res) {
  let filePath = req.url === '/' ? '/index.html' : req.url;
  filePath = path.join(__dirname, 'public', filePath);
  
  const ext = path.extname(filePath);
  const contentType = MIME_TYPES[ext] || 'text/plain';
  
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not found');
      return;
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(data);
  });
}

// API handlers
async function handleAPI(req, res) {
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');
  
  if (!connected) {
    const ok = await connectClient();
    if (!ok) {
      res.writeHead(503);
      res.end(JSON.stringify({ error: 'Not connected to daemon' }));
      return;
    }
  }
  
  try {
    let result;
    
    if (req.url === '/api/status') {
      result = await client.getStatus();
    } else if (req.url === '/api/all') {
      result = await client.getAll();
    } else if (req.url === '/api/fields') {
      result = await client.listFields();
    } else if (req.url.startsWith('/api/value/')) {
      const field = req.url.split('/api/value/')[1];
      result = await client.getValue(field);
    } else if (req.url.startsWith('/api/values?')) {
      const params = new URLSearchParams(req.url.split('?')[1]);
      const fields = params.get('fields').split(',');
      result = await client.getValues(fields);
    } else {
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'Unknown endpoint' }));
      return;
    }
    
    res.writeHead(200);
    res.end(JSON.stringify(result));
  } catch (err) {
    console.error('API error:', err.message);
    connected = false;
    res.writeHead(500);
    res.end(JSON.stringify({ error: err.message }));
  }
}

// HTTP server
const server = http.createServer(async (req, res) => {
  if (req.url.startsWith('/api/')) {
    await handleAPI(req, res);
  } else {
    serveStatic(req, res);
  }
});

// Start server
server.listen(PORT, async () => {
  console.log(`MS2D Dashboard running at http://localhost:${PORT}`);
  console.log(`Using socket: ${SOCKET_PATH}`);
  await connectClient();
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down...');
  if (client) client.disconnect();
  process.exit(0);
});

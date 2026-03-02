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
let lastErrorLog = 0;  // Rate limit error logging
const ERROR_LOG_INTERVAL = 5000;  // Only log errors every 5 seconds
// Connect to daemon
let wasConnected = false;  // Track for logging
async function connectClient() {
  if (client && connected) return true;
  
  try {
    client = new MS2Client(SOCKET_PATH);
    await client.connect();
    connected = true;
    // Only log on first connection or reconnection
    if (!wasConnected) {
      console.log(`Connected to ms2d daemon at ${SOCKET_PATH}`);
      wasConnected = true;
    }
    return true;
  } catch (err) {
    // Only log connection failures once every 5 seconds
    const now = Date.now();
    if (now - lastErrorLog > ERROR_LOG_INTERVAL) {
      console.error('Waiting for daemon...');
      lastErrorLog = now;
    }
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
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

// Route mapping for dashboard themes
const THEME_ROUTES = {
  '/': 'jdm.html',
  '/jdm': 'jdm.html',
  '/drift': 'drift.html',
  '/drag': 'drag.html',
  '/ricer': 'ricer.html',
  '/fnf': 'fnf.html',
  '/ultimate': 'ultimate.html',
};

// Serve static files from public/
function serveStatic(req, res) {
  let urlPath = req.url.split('?')[0]; // Remove query string
  
  // Check if it's a theme route
  if (THEME_ROUTES[urlPath]) {
    urlPath = '/' + THEME_ROUTES[urlPath];
  }
  
  const filePath = path.join(__dirname, 'public', urlPath);
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
    const url = req.url.split('?')[0];
    
    if (url === '/api/status') {
      result = await client.getStatus();
    } else if (url === '/api/all') {
      result = await client.getAll();
    } else if (url === '/api/fields') {
      result = await client.listFields();
    } else if (url.startsWith('/api/value/')) {
      const field = url.split('/api/value/')[1];
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
    // Rate-limit error logging to reduce spam
    const now = Date.now();
    if (now - lastErrorLog > ERROR_LOG_INTERVAL) {
      console.error('API error:', err.message);
      lastErrorLog = now;
    }
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
  console.log('Available themes:');
  console.log('  /      - JDM Night Racer (default)');
  console.log('  /drift - Drift King');
  console.log('  /drag  - Dragster');
  console.log('  /ricer - Ricer Max');
  console.log('  /fnf   - Fast & Furious');
  await connectClient();
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down...');
  if (client) client.disconnect();
  process.exit(0);
});

#!/usr/bin/env node

/**
 * MS2D Client Example
 * 
 * Demonstrates usage of the MS2Client module to connect to ms2d daemon
 * and retrieve sensor values.
 * 
 * Usage: node ms2_client_example.js [socket_path]
 * Example: node ms2_client_example.js /tmp/ms2d.sock
 */

const { MS2Client } = require('./ms2_client');

async function main() {
  // Get socket path from command line or use default
  const socketPath = process.argv[2] || '/tmp/ms2d.sock';

  console.log(`Connecting to ms2d daemon at: ${socketPath}`);

  const client = new MS2Client(socketPath);

  try {
    // Connect to daemon
    await client.connect();
    console.log('✓ Connected to daemon\n');

    // Get daemon status
    console.log('--- Daemon Status ---');
    const status = await client.getStatus();
    console.log(JSON.stringify(status, null, 2));
    console.log();

    // Get list of available fields
    console.log('--- Available Fields ---');
    const fields = await client.listFields();
    console.log(`Total fields: ${fields.length}`);
    console.log(`First 10 fields: ${fields.slice(0, 10).join(', ')}`);
    console.log();

    // Get a single field value (RPM)
    console.log('--- Single Field Value (RPM) ---');
    const rpm = await client.getValue('rpm');
    console.log(JSON.stringify(rpm, null, 2));
    console.log();

    // Get multiple field values
    console.log('--- Multiple Field Values ---');
    const values = await client.getValues(['rpm', 'batteryVoltage', 'tps']);
    console.log(JSON.stringify(values, null, 2));
    console.log();

    // Get all field values
    console.log('--- All Field Values (first 5) ---');
    const allValues = await client.getAll();
    console.log(`Total values: ${allValues.values.length}`);
    console.log('First 5 values:');
    console.log(JSON.stringify(allValues.values.slice(0, 5), null, 2));
    console.log();

    // Disconnect
    await client.disconnect();
    console.log('✓ Disconnected from daemon');

  } catch (err) {
    console.error('✗ Error:', err.message);
    process.exit(1);
  }
}

main();

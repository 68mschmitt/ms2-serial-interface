/**
 * MS2D Dashboard - Frontend
 */

const POLL_INTERVAL = 33; // ms (30 Hz update rate)

// Fields to fetch
const FIELDS = [
  'rpm', 'map', 'tps', 'afr1', 'advance',
  'coolant', 'mat', 'batteryVoltage',
  'pulseWidth1', 'veCurr1', 'accelEnrich',
  'engine', 'crank', 'startw', 'warmup',
  'tpsaccaen', 'tpsaccden'
];

// Round gauge config
const ROUND_GAUGES = {
  rpm: { min: 0, max: 8500, redline: 7000, decimals: 0 },
  afr1: { min: 10, max: 20, decimals: 1 },
  coolant: { min: 0, max: 250, decimals: 0 },
};

// Bar gauge config
const BAR_GAUGES = {
  map: { max: 250, decimals: 0 },
  tps: { max: 100, decimals: 1 },
  advance: { max: 50, decimals: 1 },
};

// Field display config (for value cards)
const FIELD_CONFIG = {
  mat: { decimals: 0 },
  batteryVoltage: { decimals: 1 },
  pulseWidth1: { decimals: 2 },
  accelEnrich: { id: 'dutyCycle1', decimals: 1 },
  veCurr1: { decimals: 0 },
};

let connected = false;

// Arc length for 270 degree gauge (0.75 of full circle)
const ARC_LENGTH = 2 * Math.PI * 85 * 0.75; // ~401

/**
 * Update round gauge
 */
function updateRoundGauge(name, value) {
  const config = ROUND_GAUGES[name];
  if (!config) return;

  const displayName = name === 'afr1' ? 'afr' : name;
  const valueEl = document.getElementById(`${displayName}-round`);
  const arcEl = document.getElementById(`${displayName}-arc`);
  
  if (!valueEl || !arcEl) return;

  // Update value display
  const decimals = config.decimals ?? 0;
  valueEl.textContent = typeof value === 'number' ? value.toFixed(decimals) : '---';

  // Calculate arc position (0-1 range)
  const range = config.max - config.min;
  const normalized = Math.max(0, Math.min(1, (value - config.min) / range));
  const offset = ARC_LENGTH * (1 - normalized);
  arcEl.style.strokeDashoffset = offset;

  // Update colors based on value
  arcEl.classList.remove('redline', 'cold', 'normal', 'hot', 'danger', 'rich', 'stoich', 'lean');
  
  if (name === 'rpm') {
    if (value >= config.redline) {
      arcEl.classList.add('redline');
    }
  } else if (name === 'afr1') {
    if (value < 12.5) {
      arcEl.classList.add('rich');
    } else if (value >= 12.5 && value <= 15.5) {
      arcEl.classList.add('stoich');
    } else {
      arcEl.classList.add('lean');
    }
  } else if (name === 'coolant') {
    if (value < 100) {
      arcEl.classList.add('cold');
    } else if (value >= 100 && value < 210) {
      arcEl.classList.add('normal');
    } else if (value >= 210 && value < 230) {
      arcEl.classList.add('hot');
    } else {
      arcEl.classList.add('danger');
    }
  }
}

/**
 * Update bar gauge
 */
function updateBarGauge(name, value) {
  const config = BAR_GAUGES[name];
  if (!config) return;

  const valueEl = document.getElementById(name);
  const barEl = document.getElementById(`${name}-bar`);
  
  if (valueEl) {
    const decimals = config.decimals ?? 1;
    valueEl.textContent = typeof value === 'number' ? value.toFixed(decimals) : '---';
  }
  
  if (barEl && config.max) {
    const pct = Math.min(100, Math.max(0, (value / config.max) * 100));
    barEl.style.width = `${pct}%`;
  }
}

/**
 * Update value card
 */
function updateValueCard(name, value) {
  const config = FIELD_CONFIG[name];
  if (!config) return;

  const displayId = config.id || name;
  const el = document.getElementById(displayId);
  
  if (!el) return;

  const decimals = config.decimals ?? 1;
  el.textContent = typeof value === 'number' ? value.toFixed(decimals) : '---';
}

/**
 * Update status flags
 */
function updateFlags(data) {
  // Engine running (rpm > 300)
  const running = (data.rpm || 0) > 300;
  document.getElementById('flag-running')?.classList.toggle('active', running);
  
  // Cranking
  const cranking = data.crank === 1;
  document.getElementById('flag-cranking')?.classList.toggle('active', cranking);
  
  // Warmup
  const warmup = data.warmup === 1 || data.startw === 1;
  document.getElementById('flag-warmup')?.classList.toggle('active', warmup);
  
  // Acceleration enrichment
  const accel = data.tpsaccaen === 1 || (data.accelEnrich || 0) > 0;
  document.getElementById('flag-accel')?.classList.toggle('active', accel);
  
  // Deceleration
  const decel = data.tpsaccden === 1;
  document.getElementById('flag-decel')?.classList.toggle('active', decel);
}

/**
 * Update connection status
 */
function setConnected(isConnected, signature = '') {
  connected = isConnected;
  const statusEl = document.getElementById('status');
  const statusText = document.getElementById('status-text');
  const sigEl = document.getElementById('signature');
  
  statusEl.classList.toggle('connected', isConnected);
  statusText.textContent = isConnected ? 'Connected' : 'Disconnected';
  
  if (signature) {
    sigEl.textContent = signature;
  }
}

/**
 * Fetch and update all data
 */
async function poll() {
  try {
    const url = `/api/values?fields=${FIELDS.join(',')}`;
    const res = await fetch(url);
    
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const data = await res.json();
    
    if (!connected) {
      const statusRes = await fetch('/api/status');
      const status = await statusRes.json();
      setConnected(true, status.signature || 'MS2');
    }
    
    if (data.values) {
      const valueMap = {};
      data.values.forEach(v => {
        valueMap[v.name] = v.value;
        
        // Update round gauges
        if (ROUND_GAUGES[v.name]) {
          updateRoundGauge(v.name, v.value);
        }
        
        // Update bar gauges
        if (BAR_GAUGES[v.name]) {
          updateBarGauge(v.name, v.value);
        }
        
        // Update value cards
        if (FIELD_CONFIG[v.name]) {
          updateValueCard(v.name, v.value);
        }
      });
      
      updateFlags(valueMap);
    }
    
    // Update poll timestamp
    const timeEl = document.getElementById('poll-time');
    const now = new Date().toLocaleTimeString();
    timeEl.textContent = `Last update: ${now}`;
    
  } catch (err) {
    console.error('Poll error:', err);
    setConnected(false);
  }
}

/**
 * Start polling
 */
function start() {
  console.log('MS2D Dashboard starting...');
  poll();
  setInterval(poll, POLL_INTERVAL);
}

// Init
document.addEventListener('DOMContentLoaded', start);

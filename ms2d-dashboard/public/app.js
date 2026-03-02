/**
 * MS2D Dashboard - ULTIMATE Edition
 * Enhanced frontend with all the bells and whistles
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

const CONFIG = {
  pollInterval: 33, // ms (30 Hz)
  
  // Shift light settings
  shiftLight: {
    enabled: true,
    warningRpm: 6000,
    shiftRpm: 7000,
    redlineRpm: 7500,
    beepEnabled: true,
    beepStartRpm: 6500,
    beepMaxRpm: 7500,
  },
  
  // Warning thresholds
  warnings: {
    coolantHigh: 220,
    coolantCritical: 235,
    voltageLow: 12.0,
    voltageCritical: 11.0,
    afrLeanWarn: 16.0,
    afrLeanCritical: 17.0,
    afrRichWarn: 11.5,
    afrRichCritical: 10.5,
  },
  
  // Data logging
  logging: {
    maxSamples: 18000, // 10 minutes at 30Hz
    historyLength: 900, // 30 seconds for strip charts
  },
  
  // G-force meter
  gForce: {
    enabled: true,
    maxG: 1.5,
    historyLength: 60,
  },
  
  // Physics settings for needle gauges
  physics: {
    damping: 0.85,
    stiffness: 0.3,
  },
};

// Fields to fetch from ECU
const FIELDS = [
  'rpm', 'map', 'tps', 'afr1', 'advance',
  'coolant', 'mat', 'batteryVoltage',
  'pulseWidth1', 'veCurr1', 'accelEnrich',
  'engine', 'crank', 'startw', 'warmup',
  'tpsaccaen', 'tpsaccden'
];

// Gauge configurations
const ROUND_GAUGES = {
  rpm: { min: 0, max: 8500, redline: 7000, decimals: 0 },
  afr1: { min: 10, max: 20, decimals: 1 },
  coolant: { min: 0, max: 250, decimals: 0 },
};

const BAR_GAUGES = {
  map: { max: 250, decimals: 0 },
  tps: { max: 100, decimals: 1 },
  advance: { max: 50, decimals: 1 },
};

const FIELD_CONFIG = {
  mat: { decimals: 0 },
  batteryVoltage: { decimals: 1 },
  pulseWidth1: { decimals: 2 },
  accelEnrich: { id: 'dutyCycle1', decimals: 1 },
  veCurr1: { decimals: 0 },
};

// ============================================================================
// STATE
// ============================================================================

const state = {
  connected: false,
  daemonReady: false,  // Set true once daemon responds successfully
  currentData: {},
  
  // Peak hold values
  peaks: {
    rpm: 0,
    map: 0,
    afr1: { min: 20, max: 10 },
    coolant: 0,
    tps: 0,
  },
  
  // Data history for charts
  history: {
    rpm: [],
    afr1: [],
    map: [],
    tps: [],
    coolant: [],
    timestamps: [],
  },
  
  // AFR histogram bins (10-20 AFR, 0.5 increments)
  afrHistogram: new Array(20).fill(0),
  
  // Engine load heatmap (RPM x MAP)
  loadHeatmap: [], // Will be 17x10 grid
  
  // Data logging
  logging: {
    active: false,
    data: [],
    startTime: null,
  },
  
  // Playback
  playback: {
    active: false,
    data: [],
    index: 0,
    speed: 1,
  },
  
  // Drag race
  dragRace: {
    staged: false,
    running: false,
    startTime: null,
    reactionTime: null,
    splits: {},
    lastRun: null,
    bestET: null,
  },
  
  // Lap timer
  lapTimer: {
    running: false,
    startTime: null,
    laps: [],
    bestLap: null,
  },
  
  // G-force
  gForce: {
    x: 0,
    y: 0,
    history: [],
    peak: 0,
  },
  
  // Physics state for needle gauges
  needles: {
    rpm: { value: 0, velocity: 0 },
    afr1: { value: 14.7, velocity: 0 },
    coolant: { value: 0, velocity: 0 },
  },
  
  // Warnings
  activeWarnings: new Set(),
  
  // UI mode
  mode: 'normal', // 'normal', 'hud', 'night', 'dyno'
};

// ============================================================================
// AUDIO SYSTEM
// ============================================================================

const Audio = {
  ctx: null,
  
  init() {
    // Create on first user interaction
    document.addEventListener('click', () => {
      if (!this.ctx) {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      }
    }, { once: true });
  },
  
  beep(frequency = 880, duration = 50, volume = 0.3) {
    if (!this.ctx || !CONFIG.shiftLight.beepEnabled) return;
    
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    
    osc.connect(gain);
    gain.connect(this.ctx.destination);
    
    osc.frequency.value = frequency;
    osc.type = 'square';
    
    gain.gain.setValueAtTime(volume, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + duration / 1000);
    
    osc.start();
    osc.stop(this.ctx.currentTime + duration / 1000);
  },
  
  shiftBeep(rpm) {
    if (!CONFIG.shiftLight.enabled || !CONFIG.shiftLight.beepEnabled) return;
    
    const { beepStartRpm, beepMaxRpm, redlineRpm } = CONFIG.shiftLight;
    
    if (rpm < beepStartRpm) return;
    
    // Progressive beeping - faster as RPM increases
    const progress = (rpm - beepStartRpm) / (beepMaxRpm - beepStartRpm);
    const interval = Math.max(50, 300 - (progress * 250));
    
    // Frequency increases with RPM
    const freq = 600 + (progress * 800);
    
    // Only beep at intervals
    const now = Date.now();
    if (!this._lastBeep || now - this._lastBeep > interval) {
      this.beep(freq, 30, 0.2 + (progress * 0.3));
      this._lastBeep = now;
    }
    
    // Continuous tone at redline
    if (rpm >= redlineRpm) {
      this.beep(1400, 100, 0.5);
    }
  },
  
  warning(type = 'warning') {
    if (!this.ctx) return;
    
    const patterns = {
      warning: [{ freq: 800, dur: 100 }, { freq: 0, dur: 100 }, { freq: 800, dur: 100 }],
      critical: [{ freq: 1000, dur: 50 }, { freq: 0, dur: 50 }, { freq: 1000, dur: 50 }, { freq: 0, dur: 50 }, { freq: 1000, dur: 100 }],
      success: [{ freq: 523, dur: 100 }, { freq: 659, dur: 100 }, { freq: 784, dur: 150 }],
    };
    
    const pattern = patterns[type] || patterns.warning;
    let delay = 0;
    
    pattern.forEach(({ freq, dur }) => {
      setTimeout(() => {
        if (freq > 0) this.beep(freq, dur, 0.3);
      }, delay);
      delay += dur;
    });
  },
  
  stagingBeep() {
    this.beep(440, 200, 0.4);
  },
  
  goBeep() {
    this.beep(880, 500, 0.5);
  },
};

// ============================================================================
// DATA HISTORY & ANALYTICS
// ============================================================================

const History = {
  add(data) {
    const maxLen = CONFIG.logging.historyLength;
    
    Object.keys(state.history).forEach(key => {
      if (key === 'timestamps') {
        state.history.timestamps.push(Date.now());
        if (state.history.timestamps.length > maxLen) {
          state.history.timestamps.shift();
        }
      } else if (data[key] !== undefined) {
        state.history[key].push(data[key]);
        if (state.history[key].length > maxLen) {
          state.history[key].shift();
        }
      }
    });
    
    // Update AFR histogram
    if (data.afr1 !== undefined) {
      const bin = Math.floor((data.afr1 - 10) / 0.5);
      if (bin >= 0 && bin < state.afrHistogram.length) {
        state.afrHistogram[bin]++;
      }
    }
    
    // Update load heatmap
    if (data.rpm !== undefined && data.map !== undefined) {
      this.updateHeatmap(data.rpm, data.map);
    }
  },
  
  updateHeatmap(rpm, map) {
    // 17 RPM bins (0-8000, 500 increments)
    // 10 MAP bins (0-250, 25 increments)
    const rpmBin = Math.min(16, Math.floor(rpm / 500));
    const mapBin = Math.min(9, Math.floor(map / 25));
    
    if (!state.loadHeatmap[rpmBin]) {
      state.loadHeatmap[rpmBin] = new Array(10).fill(0);
    }
    state.loadHeatmap[rpmBin][mapBin]++;
  },
  
  updatePeaks(data) {
    if (data.rpm > state.peaks.rpm) state.peaks.rpm = data.rpm;
    if (data.map > state.peaks.map) state.peaks.map = data.map;
    if (data.tps > state.peaks.tps) state.peaks.tps = data.tps;
    if (data.coolant > state.peaks.coolant) state.peaks.coolant = data.coolant;
    
    if (data.afr1 !== undefined) {
      if (data.afr1 < state.peaks.afr1.min) state.peaks.afr1.min = data.afr1;
      if (data.afr1 > state.peaks.afr1.max) state.peaks.afr1.max = data.afr1;
    }
  },
  
  resetPeaks() {
    state.peaks = {
      rpm: 0,
      map: 0,
      afr1: { min: 20, max: 10 },
      coolant: 0,
      tps: 0,
    };
  },
  
  resetHistogram() {
    state.afrHistogram = new Array(20).fill(0);
  },
  
  resetHeatmap() {
    state.loadHeatmap = [];
  },
};

// ============================================================================
// DATA LOGGING
// ============================================================================

const DataLogger = {
  start() {
    state.logging.active = true;
    state.logging.data = [];
    state.logging.startTime = Date.now();
    console.log('Data logging started');
    
    // Update UI
    const btn = document.getElementById('log-btn');
    if (btn) {
      btn.textContent = '⏹ STOP';
      btn.classList.add('recording');
    }
  },
  
  stop() {
    state.logging.active = false;
    console.log(`Data logging stopped. ${state.logging.data.length} samples captured.`);
    
    const btn = document.getElementById('log-btn');
    if (btn) {
      btn.textContent = '⏺ LOG';
      btn.classList.remove('recording');
    }
    
    return state.logging.data;
  },
  
  toggle() {
    if (state.logging.active) {
      this.stop();
    } else {
      this.start();
    }
  },
  
  record(data) {
    if (!state.logging.active) return;
    if (state.logging.data.length >= CONFIG.logging.maxSamples) {
      this.stop();
      return;
    }
    
    state.logging.data.push({
      timestamp: Date.now() - state.logging.startTime,
      ...data,
    });
  },
  
  exportCSV() {
    if (state.logging.data.length === 0) {
      alert('No data to export. Start logging first.');
      return;
    }
    
    const headers = ['timestamp', ...FIELDS];
    const rows = state.logging.data.map(row => 
      headers.map(h => row[h] ?? '').join(',')
    );
    
    const csv = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `ms2d_log_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.csv`;
    a.click();
    
    URL.revokeObjectURL(url);
  },
  
  saveToLocalStorage() {
    if (state.logging.data.length === 0) return;
    
    const key = `ms2d_log_${Date.now()}`;
    const compressed = JSON.stringify(state.logging.data);
    
    try {
      localStorage.setItem(key, compressed);
      console.log(`Saved ${state.logging.data.length} samples to ${key}`);
    } catch (e) {
      console.error('Failed to save to localStorage:', e);
    }
  },
  
  listSaved() {
    const logs = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key.startsWith('ms2d_log_')) {
        logs.push(key);
      }
    }
    return logs.sort().reverse();
  },
  
  load(key) {
    const data = localStorage.getItem(key);
    if (!data) return null;
    return JSON.parse(data);
  },
};

// ============================================================================
// PLAYBACK SYSTEM
// ============================================================================

const Playback = {
  load(data) {
    state.playback.data = data;
    state.playback.index = 0;
    state.playback.active = false;
    
    console.log(`Loaded ${data.length} samples for playback`);
  },
  
  play() {
    if (state.playback.data.length === 0) return;
    state.playback.active = true;
    this._playbackLoop();
  },
  
  pause() {
    state.playback.active = false;
  },
  
  stop() {
    state.playback.active = false;
    state.playback.index = 0;
  },
  
  seek(index) {
    state.playback.index = Math.max(0, Math.min(index, state.playback.data.length - 1));
  },
  
  setSpeed(speed) {
    state.playback.speed = speed;
  },
  
  _playbackLoop() {
    if (!state.playback.active) return;
    if (state.playback.index >= state.playback.data.length) {
      this.stop();
      return;
    }
    
    const sample = state.playback.data[state.playback.index];
    processData(sample);
    state.playback.index++;
    
    // Calculate delay to next sample
    const nextSample = state.playback.data[state.playback.index];
    const delay = nextSample 
      ? (nextSample.timestamp - sample.timestamp) / state.playback.speed
      : CONFIG.pollInterval;
    
    setTimeout(() => this._playbackLoop(), delay);
  },
};

// ============================================================================
// DRAG RACE MODE
// ============================================================================

const DragRace = {
  stage() {
    state.dragRace.staged = true;
    state.dragRace.running = false;
    state.dragRace.startTime = null;
    state.dragRace.reactionTime = null;
    state.dragRace.splits = {};
    
    Audio.stagingBeep();
    this.updateDisplay();
    
    // Start countdown after staging
    setTimeout(() => this.countdown(), 1000);
  },
  
  countdown() {
    if (!state.dragRace.staged) return;
    
    // Simulate Christmas tree - 3 amber, then green
    const lights = ['amber1', 'amber2', 'amber3', 'green'];
    let i = 0;
    
    const flash = () => {
      if (i < 3) {
        // Amber lights
        this.setLight(lights[i], true);
        Audio.beep(440, 100, 0.3);
        i++;
        setTimeout(flash, 500);
      } else {
        // Green light - GO!
        this.setLight('green', true);
        Audio.goBeep();
        state.dragRace.greenTime = Date.now();
        
        // Wait for launch detection (RPM spike or TPS)
        this.detectLaunch();
      }
    };
    
    flash();
  },
  
  detectLaunch() {
    // Launch detected when RPM drops (clutch dump) or TPS high
    const checkLaunch = () => {
      if (!state.dragRace.staged) return;
      
      const rpm = state.currentData.rpm || 0;
      const tps = state.currentData.tps || 0;
      
      // Launch condition: TPS > 80% or significant RPM change
      if (tps > 80 || state.dragRace._lastRpm && (state.dragRace._lastRpm - rpm) > 500) {
        this.start();
        return;
      }
      
      state.dragRace._lastRpm = rpm;
      requestAnimationFrame(checkLaunch);
    };
    
    checkLaunch();
  },
  
  start() {
    state.dragRace.running = true;
    state.dragRace.startTime = Date.now();
    state.dragRace.reactionTime = state.dragRace.startTime - state.dragRace.greenTime;
    
    // Red light if jumped
    if (state.dragRace.reactionTime < 0) {
      this.setLight('red', true);
      Audio.warning('critical');
    }
    
    this.updateDisplay();
    this.trackSplits();
  },
  
  trackSplits() {
    if (!state.dragRace.running) return;
    
    // Simulated distance based on time (rough approximation)
    const elapsed = (Date.now() - state.dragRace.startTime) / 1000;
    
    // Record split times at distance markers
    const splits = [60, 330, 660, 1000, 1320]; // feet
    const splitNames = ['60ft', '330ft', '1/8mi', '1000ft', '1/4mi'];
    
    // Very rough speed/distance estimation
    // Real implementation would need GPS or wheel speed
    const estimatedDistance = elapsed * elapsed * 15; // feet (rough)
    
    splits.forEach((dist, i) => {
      if (!state.dragRace.splits[splitNames[i]] && estimatedDistance >= dist) {
        state.dragRace.splits[splitNames[i]] = elapsed.toFixed(3);
      }
    });
    
    this.updateDisplay();
    
    if (!state.dragRace.splits['1/4mi']) {
      requestAnimationFrame(() => this.trackSplits());
    } else {
      this.finish();
    }
  },
  
  finish() {
    state.dragRace.running = false;
    state.dragRace.staged = false;
    
    const et = parseFloat(state.dragRace.splits['1/4mi']);
    state.dragRace.lastRun = {
      et,
      reaction: state.dragRace.reactionTime,
      splits: { ...state.dragRace.splits },
      timestamp: Date.now(),
    };
    
    // Check for best ET
    if (!state.dragRace.bestET || et < state.dragRace.bestET) {
      state.dragRace.bestET = et;
      Audio.warning('success');
    }
    
    this.saveRun();
    this.updateDisplay();
  },
  
  reset() {
    state.dragRace.staged = false;
    state.dragRace.running = false;
    state.dragRace.startTime = null;
    this.clearLights();
    this.updateDisplay();
  },
  
  setLight(name, on) {
    const el = document.getElementById(`tree-${name}`);
    if (el) el.classList.toggle('active', on);
  },
  
  clearLights() {
    ['prestage', 'stage', 'amber1', 'amber2', 'amber3', 'green', 'red'].forEach(l => {
      this.setLight(l, false);
    });
  },
  
  updateDisplay() {
    const etEl = document.getElementById('drag-et');
    const rtEl = document.getElementById('drag-reaction');
    const splitsEl = document.getElementById('drag-splits');
    
    if (state.dragRace.running && state.dragRace.startTime) {
      const elapsed = ((Date.now() - state.dragRace.startTime) / 1000).toFixed(3);
      if (etEl) etEl.textContent = elapsed;
    } else if (state.dragRace.lastRun) {
      if (etEl) etEl.textContent = state.dragRace.lastRun.et.toFixed(3);
    }
    
    if (rtEl && state.dragRace.reactionTime !== null) {
      rtEl.textContent = (state.dragRace.reactionTime / 1000).toFixed(3);
    }
    
    if (splitsEl) {
      const splits = state.dragRace.splits;
      splitsEl.innerHTML = Object.entries(splits)
        .map(([name, time]) => `<div>${name}: ${time}s</div>`)
        .join('');
    }
  },
  
  saveRun() {
    const runs = JSON.parse(localStorage.getItem('ms2d_drag_runs') || '[]');
    runs.push(state.dragRace.lastRun);
    localStorage.setItem('ms2d_drag_runs', JSON.stringify(runs.slice(-50)));
  },
  
  getBestRuns() {
    const runs = JSON.parse(localStorage.getItem('ms2d_drag_runs') || '[]');
    return runs.sort((a, b) => a.et - b.et).slice(0, 10);
  },
};

// ============================================================================
// LAP TIMER
// ============================================================================

const LapTimer = {
  start() {
    state.lapTimer.running = true;
    state.lapTimer.startTime = Date.now();
    state.lapTimer.laps = [];
    
    Audio.stagingBeep();
    this.updateDisplay();
  },
  
  lap() {
    if (!state.lapTimer.running) return;
    
    const now = Date.now();
    const lapTime = now - (state.lapTimer.laps.length > 0 
      ? state.lapTimer.laps[state.lapTimer.laps.length - 1].timestamp 
      : state.lapTimer.startTime);
    
    const lap = {
      number: state.lapTimer.laps.length + 1,
      time: lapTime,
      timestamp: now,
      totalTime: now - state.lapTimer.startTime,
    };
    
    state.lapTimer.laps.push(lap);
    
    // Check for best lap
    if (!state.lapTimer.bestLap || lapTime < state.lapTimer.bestLap) {
      state.lapTimer.bestLap = lapTime;
      Audio.warning('success');
    } else {
      Audio.beep(660, 100, 0.2);
    }
    
    this.updateDisplay();
  },
  
  stop() {
    state.lapTimer.running = false;
    this.updateDisplay();
  },
  
  reset() {
    state.lapTimer.running = false;
    state.lapTimer.startTime = null;
    state.lapTimer.laps = [];
    this.updateDisplay();
  },
  
  updateDisplay() {
    const timerEl = document.getElementById('lap-timer');
    const lapsEl = document.getElementById('lap-list');
    const bestEl = document.getElementById('best-lap');
    
    if (timerEl && state.lapTimer.running) {
      const elapsed = Date.now() - state.lapTimer.startTime;
      timerEl.textContent = this.formatTime(elapsed);
    }
    
    if (bestEl && state.lapTimer.bestLap) {
      bestEl.textContent = this.formatTime(state.lapTimer.bestLap);
    }
    
    if (lapsEl) {
      lapsEl.innerHTML = state.lapTimer.laps
        .slice(-5)
        .reverse()
        .map(lap => {
          const isBest = lap.time === state.lapTimer.bestLap;
          return `<div class="${isBest ? 'best' : ''}">
            Lap ${lap.number}: ${this.formatTime(lap.time)}
          </div>`;
        })
        .join('');
    }
  },
  
  formatTime(ms) {
    const totalSec = ms / 1000;
    const min = Math.floor(totalSec / 60);
    const sec = (totalSec % 60).toFixed(3);
    return min > 0 ? `${min}:${sec.padStart(6, '0')}` : sec;
  },
};

// ============================================================================
// G-FORCE METER
// ============================================================================

const GForce = {
  init() {
    if (!CONFIG.gForce.enabled) return;
    
    if (window.DeviceMotionEvent) {
      // Request permission on iOS 13+
      if (typeof DeviceMotionEvent.requestPermission === 'function') {
        document.getElementById('gforce-enable')?.addEventListener('click', async () => {
          const permission = await DeviceMotionEvent.requestPermission();
          if (permission === 'granted') {
            this.startListening();
          }
        });
      } else {
        this.startListening();
      }
    }
  },
  
  startListening() {
    window.addEventListener('devicemotion', (e) => {
      const acc = e.accelerationIncludingGravity;
      if (!acc) return;
      
      // Convert to G (9.81 m/s² = 1G)
      // X = lateral, Y = longitudinal (on phone held landscape)
      state.gForce.x = (acc.x || 0) / 9.81;
      state.gForce.y = (acc.y || 0) / 9.81;
      
      const totalG = Math.sqrt(state.gForce.x ** 2 + state.gForce.y ** 2);
      if (totalG > state.gForce.peak) {
        state.gForce.peak = totalG;
      }
      
      // Add to history
      state.gForce.history.push({ x: state.gForce.x, y: state.gForce.y });
      if (state.gForce.history.length > CONFIG.gForce.historyLength) {
        state.gForce.history.shift();
      }
      
      this.updateDisplay();
    });
  },
  
  updateDisplay() {
    const dotEl = document.getElementById('gforce-dot');
    const xEl = document.getElementById('gforce-x');
    const yEl = document.getElementById('gforce-y');
    const peakEl = document.getElementById('gforce-peak');
    const trailEl = document.getElementById('gforce-trail');
    
    if (dotEl) {
      // Map G to pixel position (assuming 100px radius meter)
      const maxG = CONFIG.gForce.maxG;
      const x = (state.gForce.x / maxG) * 50;
      const y = -(state.gForce.y / maxG) * 50; // Invert Y
      dotEl.style.transform = `translate(${x}px, ${y}px)`;
    }
    
    if (xEl) xEl.textContent = state.gForce.x.toFixed(2);
    if (yEl) yEl.textContent = state.gForce.y.toFixed(2);
    if (peakEl) peakEl.textContent = state.gForce.peak.toFixed(2);
    
    // Draw trail
    if (trailEl && state.gForce.history.length > 1) {
      const maxG = CONFIG.gForce.maxG;
      const points = state.gForce.history.map((g, i) => {
        const x = 50 + (g.x / maxG) * 50;
        const y = 50 - (g.y / maxG) * 50;
        return `${x},${y}`;
      }).join(' ');
      trailEl.setAttribute('points', points);
    }
  },
  
  resetPeak() {
    state.gForce.peak = 0;
  },
};

// ============================================================================
// WARNING SYSTEM
// ============================================================================

const Warnings = {
  check(data) {
    const { warnings } = CONFIG;
    const newWarnings = new Set();
    
    // Coolant temperature
    if (data.coolant >= warnings.coolantCritical) {
      newWarnings.add('coolant-critical');
      this.trigger('COOLANT CRITICAL', 'critical');
    } else if (data.coolant >= warnings.coolantHigh) {
      newWarnings.add('coolant-high');
      this.trigger('COOLANT HIGH', 'warning');
    }
    
    // Voltage
    if (data.batteryVoltage <= warnings.voltageCritical) {
      newWarnings.add('voltage-critical');
      this.trigger('VOLTAGE CRITICAL', 'critical');
    } else if (data.batteryVoltage <= warnings.voltageLow) {
      newWarnings.add('voltage-low');
      this.trigger('LOW VOLTAGE', 'warning');
    }
    
    // AFR
    if (data.afr1 >= warnings.afrLeanCritical) {
      newWarnings.add('afr-lean-critical');
      this.trigger('AFR LEAN!', 'critical');
    } else if (data.afr1 >= warnings.afrLeanWarn) {
      newWarnings.add('afr-lean');
    }
    
    if (data.afr1 <= warnings.afrRichCritical) {
      newWarnings.add('afr-rich-critical');
      this.trigger('AFR RICH!', 'critical');
    } else if (data.afr1 <= warnings.afrRichWarn) {
      newWarnings.add('afr-rich');
    }
    
    // Update UI
    this.updateDisplay(newWarnings);
    state.activeWarnings = newWarnings;
  },
  
  trigger(message, level) {
    // Only alert once per warning
    const key = message.toLowerCase().replace(/\s+/g, '-');
    if (state.activeWarnings.has(key)) return;
    
    // Flash screen edge
    document.body.classList.add(`warning-${level}`);
    setTimeout(() => document.body.classList.remove(`warning-${level}`), 500);
    
    // Audio
    if (level === 'critical') {
      Audio.warning('critical');
    }
    
    // Show toast notification
    this.showToast(message, level);
  },
  
  showToast(message, level) {
    let container = document.getElementById('warning-toasts');
    if (!container) {
      container = document.createElement('div');
      container.id = 'warning-toasts';
      document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    toast.className = `warning-toast ${level}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => toast.remove(), 3000);
  },
  
  updateDisplay(warnings) {
    const el = document.getElementById('warning-panel');
    if (!el) return;
    
    if (warnings.size > 0) {
      el.classList.add('active');
      el.innerHTML = Array.from(warnings)
        .map(w => `<div class="warning-item">${w.replace(/-/g, ' ').toUpperCase()}</div>`)
        .join('');
    } else {
      el.classList.remove('active');
      el.innerHTML = '';
    }
  },
};

// ============================================================================
// PHYSICS-BASED NEEDLE GAUGES
// ============================================================================

const PhysicsNeedles = {
  update(name, targetValue) {
    if (!state.needles[name]) return targetValue;
    
    const needle = state.needles[name];
    const { damping, stiffness } = CONFIG.physics;
    
    // Spring physics
    const force = (targetValue - needle.value) * stiffness;
    needle.velocity += force;
    needle.velocity *= damping;
    needle.value += needle.velocity;
    
    return needle.value;
  },
  
  reset() {
    Object.keys(state.needles).forEach(key => {
      state.needles[key] = { value: 0, velocity: 0 };
    });
  },
};

// ============================================================================
// SHIFT LIGHTS
// ============================================================================

const ShiftLights = {
  update(rpm) {
    if (!CONFIG.shiftLight.enabled) return;
    
    const { warningRpm, shiftRpm, redlineRpm } = CONFIG.shiftLight;
    
    // Update shift light bar elements
    const lights = document.querySelectorAll('.shift-light');
    const numLights = lights.length;
    
    if (numLights === 0) return;
    
    // Calculate how many lights should be lit
    let litCount = 0;
    
    if (rpm >= warningRpm) {
      const progress = (rpm - warningRpm) / (redlineRpm - warningRpm);
      litCount = Math.ceil(progress * numLights);
    }
    
    lights.forEach((light, i) => {
      const isLit = i < litCount;
      light.classList.toggle('active', isLit);
      
      // Color progression: green -> yellow -> red
      const position = i / numLights;
      if (isLit) {
        if (position < 0.4) {
          light.classList.add('green');
          light.classList.remove('yellow', 'red');
        } else if (position < 0.7) {
          light.classList.add('yellow');
          light.classList.remove('green', 'red');
        } else {
          light.classList.add('red');
          light.classList.remove('green', 'yellow');
        }
      } else {
        light.classList.remove('green', 'yellow', 'red');
      }
    });
    
    // Flash at redline
    if (rpm >= redlineRpm) {
      lights.forEach(l => l.classList.toggle('flash', Date.now() % 200 < 100));
    }
    
    // Trigger audio
    Audio.shiftBeep(rpm);
  },
};

// ============================================================================
// REDLINE EFFECTS
// ============================================================================

const RedlineEffects = {
  update(rpm) {
    const { redline } = ROUND_GAUGES.rpm;
    const isRedline = rpm >= redline;
    
    // Screen shake
    if (isRedline) {
      const intensity = Math.min(5, (rpm - redline) / 200);
      const x = (Math.random() - 0.5) * intensity;
      const y = (Math.random() - 0.5) * intensity;
      document.body.style.transform = `translate(${x}px, ${y}px)`;
    } else {
      document.body.style.transform = '';
    }
    
    // Edge glow
    document.body.classList.toggle('redline-active', isRedline);
    
    // Vignette flash
    const vignette = document.getElementById('redline-vignette');
    if (vignette) {
      vignette.classList.toggle('active', isRedline);
    }
  },
};

// ============================================================================
// DISPLAY MODE SWITCHING
// ============================================================================

const DisplayModes = {
  setMode(mode) {
    state.mode = mode;
    document.body.className = document.body.className
      .replace(/mode-\w+/g, '')
      .trim() + ` mode-${mode}`;
    
    // Special handling for HUD mode
    if (mode === 'hud') {
      document.body.style.transform = 'scaleX(-1)';
    } else {
      document.body.style.transform = '';
    }
  },
  
  toggle() {
    const modes = ['normal', 'hud', 'night', 'dyno'];
    const currentIndex = modes.indexOf(state.mode);
    const nextIndex = (currentIndex + 1) % modes.length;
    this.setMode(modes[nextIndex]);
  },
};

// ============================================================================
// CHARTS & VISUALIZATIONS
// ============================================================================

const Charts = {
  drawRpmRibbon(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas;
    const data = state.history.rpm;
    
    if (data.length < 2) return;
    
    ctx.clearRect(0, 0, width, height);
    
    // Draw RPM ribbon
    ctx.beginPath();
    ctx.strokeStyle = '#00ff88';
    ctx.lineWidth = 2;
    
    const step = width / data.length;
    const maxRpm = ROUND_GAUGES.rpm.max;
    
    data.forEach((rpm, i) => {
      const x = i * step;
      const y = height - (rpm / maxRpm) * height;
      
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    
    ctx.stroke();
    
    // Fill below line
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fillStyle = 'rgba(0, 255, 136, 0.1)';
    ctx.fill();
    
    // Draw redline marker
    const redlineY = height - (ROUND_GAUGES.rpm.redline / maxRpm) * height;
    ctx.beginPath();
    ctx.strokeStyle = '#ff004488';
    ctx.setLineDash([5, 5]);
    ctx.moveTo(0, redlineY);
    ctx.lineTo(width, redlineY);
    ctx.stroke();
    ctx.setLineDash([]);
  },
  
  drawAfrHistogram(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas;
    const data = state.afrHistogram;
    
    ctx.clearRect(0, 0, width, height);
    
    const maxCount = Math.max(...data, 1);
    const barWidth = width / data.length;
    
    data.forEach((count, i) => {
      const barHeight = (count / maxCount) * (height - 20);
      const x = i * barWidth;
      const y = height - barHeight - 10;
      
      // Color based on AFR value
      const afr = 10 + (i * 0.5);
      if (afr < 12.5) {
        ctx.fillStyle = '#ff6600'; // Rich
      } else if (afr <= 15.5) {
        ctx.fillStyle = '#00ff88'; // Stoich
      } else {
        ctx.fillStyle = '#00aaff'; // Lean
      }
      
      ctx.fillRect(x + 1, y, barWidth - 2, barHeight);
    });
    
    // Draw stoich line
    const stoichX = ((14.7 - 10) / 0.5) * barWidth;
    ctx.beginPath();
    ctx.strokeStyle = '#ffffff88';
    ctx.setLineDash([3, 3]);
    ctx.moveTo(stoichX, 0);
    ctx.lineTo(stoichX, height);
    ctx.stroke();
    ctx.setLineDash([]);
  },
  
  drawLoadHeatmap(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas;
    
    ctx.clearRect(0, 0, width, height);
    
    const cellWidth = width / 17;
    const cellHeight = height / 10;
    
    // Find max for normalization
    let maxCount = 0;
    state.loadHeatmap.forEach(row => {
      if (row) maxCount = Math.max(maxCount, ...row);
    });
    
    if (maxCount === 0) return;
    
    state.loadHeatmap.forEach((row, rpmBin) => {
      if (!row) return;
      row.forEach((count, mapBin) => {
        const intensity = count / maxCount;
        const x = rpmBin * cellWidth;
        const y = height - (mapBin + 1) * cellHeight;
        
        // Heat color: blue -> green -> yellow -> red
        const hue = (1 - intensity) * 240;
        ctx.fillStyle = `hsla(${hue}, 100%, 50%, ${0.3 + intensity * 0.7})`;
        ctx.fillRect(x, y, cellWidth - 1, cellHeight - 1);
      });
    });
    
    // Labels
    ctx.fillStyle = '#666';
    ctx.font = '10px sans-serif';
    ctx.fillText('RPM →', width - 40, height - 2);
    ctx.save();
    ctx.translate(10, height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('MAP →', 0, 0);
    ctx.restore();
  },
};

// ============================================================================
// GAUGE UPDATES
// ============================================================================

const ARC_LENGTH = 2 * Math.PI * 85 * 0.75;

function updateRoundGauge(name, rawValue) {
  const config = ROUND_GAUGES[name];
  if (!config) return;

  // Apply physics for smooth needle movement
  const value = PhysicsNeedles.update(name, rawValue);

  const displayName = name === 'afr1' ? 'afr' : name;
  const valueEl = document.getElementById(`${displayName}-round`);
  const arcEl = document.getElementById(`${displayName}-arc`);
  
  if (!valueEl || !arcEl) return;

  const decimals = config.decimals ?? 0;
  valueEl.textContent = typeof rawValue === 'number' ? rawValue.toFixed(decimals) : '---';

  const range = config.max - config.min;
  const normalized = Math.max(0, Math.min(1, (value - config.min) / range));
  const offset = ARC_LENGTH * (1 - normalized);
  arcEl.style.strokeDashoffset = offset;

  // Color states
  arcEl.classList.remove('redline', 'cold', 'normal', 'hot', 'danger', 'rich', 'stoich', 'lean');
  
  if (name === 'rpm') {
    if (rawValue >= config.redline) arcEl.classList.add('redline');
  } else if (name === 'afr1') {
    if (rawValue < 12.5) arcEl.classList.add('rich');
    else if (rawValue <= 15.5) arcEl.classList.add('stoich');
    else arcEl.classList.add('lean');
  } else if (name === 'coolant') {
    if (rawValue < 100) arcEl.classList.add('cold');
    else if (rawValue < 210) arcEl.classList.add('normal');
    else if (rawValue < 230) arcEl.classList.add('hot');
    else arcEl.classList.add('danger');
  }
}

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

function updateValueCard(name, value) {
  const config = FIELD_CONFIG[name];
  if (!config) return;

  const displayId = config.id || name;
  const el = document.getElementById(displayId);
  
  if (!el) return;

  const decimals = config.decimals ?? 1;
  el.textContent = typeof value === 'number' ? value.toFixed(decimals) : '---';
}

function updateFlags(data) {
  const running = (data.rpm || 0) > 300;
  document.getElementById('flag-running')?.classList.toggle('active', running);
  
  const cranking = data.crank === 1;
  document.getElementById('flag-cranking')?.classList.toggle('active', cranking);
  
  const warmup = data.warmup === 1 || data.startw === 1;
  document.getElementById('flag-warmup')?.classList.toggle('active', warmup);
  
  const accel = data.tpsaccaen === 1 || (data.accelEnrich || 0) > 0;
  document.getElementById('flag-accel')?.classList.toggle('active', accel);
  
  const decel = data.tpsaccden === 1;
  document.getElementById('flag-decel')?.classList.toggle('active', decel);
}

function updatePeakDisplay() {
  const { peaks } = state;
  
  const peakRpm = document.getElementById('peak-rpm');
  const peakMap = document.getElementById('peak-map');
  const peakAfr = document.getElementById('peak-afr');
  
  if (peakRpm) peakRpm.textContent = peaks.rpm.toFixed(0);
  if (peakMap) peakMap.textContent = peaks.map.toFixed(0);
  if (peakAfr) peakAfr.textContent = `${peaks.afr1.min.toFixed(1)} - ${peaks.afr1.max.toFixed(1)}`;
}

function setConnected(isConnected, signature = '') {
  state.connected = isConnected;
  const statusEl = document.getElementById('status');
  const statusText = document.getElementById('status-text');
  const sigEl = document.getElementById('signature');
  
  if (statusEl) statusEl.classList.toggle('connected', isConnected);
  if (statusText) statusText.textContent = isConnected ? 'Connected' : 'Disconnected';
  if (sigEl && signature) sigEl.textContent = signature;
}

// ============================================================================
// MAIN DATA PROCESSING
// ============================================================================

function processData(data) {
  state.currentData = data;
  
  // Update all gauges
  Object.entries(data).forEach(([name, value]) => {
    if (ROUND_GAUGES[name]) updateRoundGauge(name, value);
    if (BAR_GAUGES[name]) updateBarGauge(name, value);
    if (FIELD_CONFIG[name]) updateValueCard(name, value);
  });
  
  updateFlags(data);
  
  // Update peaks
  History.updatePeaks(data);
  updatePeakDisplay();
  
  // Update history & analytics
  History.add(data);
  
  // Log if active
  DataLogger.record(data);
  
  // Check warnings
  Warnings.check(data);
  
  // Update shift lights
  if (data.rpm !== undefined) {
    ShiftLights.update(data.rpm);
    RedlineEffects.update(data.rpm);
  }
  
  // Update drag race display if active
  if (state.dragRace.running) {
    DragRace.updateDisplay();
  }
  
  // Update lap timer if running
  if (state.lapTimer.running) {
    LapTimer.updateDisplay();
  }
  
  // Update charts
  Charts.drawRpmRibbon('rpm-ribbon');
  Charts.drawAfrHistogram('afr-histogram');
  Charts.drawLoadHeatmap('load-heatmap');
  
  // Update dyno mode if running
  if (DynoMode.running) {
    DynoMode.update(data);
    DynoMode.drawCurves('dyno-curves');
  }
}

// ============================================================================
// POLLING
// ============================================================================

async function poll() {
  // Don't poll if in playback mode or not ready
  if (state.playback.active || !state.daemonReady) return;
  
  try {
    const url = `/api/values?fields=${FIELDS.join(',')}`;
    const res = await fetch(url);
    
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const data = await res.json();
    
    // Check for RPC errors
    if (data.error) {
      throw new Error(data.error);
    }
    
    if (!state.connected) {
      const statusRes = await fetch('/api/status');
      const status = await statusRes.json();
      setConnected(true, status.signature || 'MS2');
    }
    
    if (data.values) {
      const valueMap = {};
      data.values.forEach(v => {
        valueMap[v.name] = v.value;
      });
      
      processData(valueMap);
    }
    
    // Update poll timestamp
    const timeEl = document.getElementById('poll-time');
    if (timeEl) {
      const now = new Date().toLocaleTimeString();
      timeEl.textContent = `Last update: ${now}`;
    }
    
  } catch (err) {
    // Only log if was previously connected (avoid spam during startup)
    if (state.connected) {
      console.error('Poll error:', err);
    }
    setConnected(false);
  }
}

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================

function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Ignore if typing in input
    if (e.target.tagName === 'INPUT') return;
    
    switch (e.key.toLowerCase()) {
      case 'l':
        DataLogger.toggle();
        break;
      case 'e':
        DataLogger.exportCSV();
        break;
      case 'r':
        History.resetPeaks();
        break;
      case 's':
        DragRace.stage();
        break;
      case ' ':
        e.preventDefault();
        LapTimer.running ? LapTimer.lap() : LapTimer.start();
        break;
      case 'escape':
        DragRace.reset();
        LapTimer.stop();
        break;
      case 'm':
        DisplayModes.toggle();
        break;
      case 'f':
        toggleFullscreen();
        break;
      case 'd':
        DynoMode.running ? DynoMode.stop() : DynoMode.start();
        break;
      case 'p':
        DragAndDropLayout.toggle();
        break;
    }
  });
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
}

// ============================================================================
// UI SETUP
// ============================================================================

function setupUI() {
  // Log button
  document.getElementById('log-btn')?.addEventListener('click', () => DataLogger.toggle());
  
  // Export button
  document.getElementById('export-btn')?.addEventListener('click', () => DataLogger.exportCSV());
  
  // Reset peaks button
  document.getElementById('reset-peaks-btn')?.addEventListener('click', () => {
    History.resetPeaks();
    History.resetHistogram();
    History.resetHeatmap();
  });
  
  // Drag race buttons
  document.getElementById('drag-stage-btn')?.addEventListener('click', () => DragRace.stage());
  document.getElementById('drag-reset-btn')?.addEventListener('click', () => DragRace.reset());
  
  // Lap timer buttons
  document.getElementById('lap-start-btn')?.addEventListener('click', () => LapTimer.start());
  document.getElementById('lap-btn')?.addEventListener('click', () => LapTimer.lap());
  document.getElementById('lap-stop-btn')?.addEventListener('click', () => LapTimer.stop());
  document.getElementById('lap-reset-btn')?.addEventListener('click', () => LapTimer.reset());
  
  // Mode switcher
  document.getElementById('mode-btn')?.addEventListener('click', () => DisplayModes.toggle());
  
  // Fullscreen button
  document.getElementById('fullscreen-btn')?.addEventListener('click', toggleFullscreen);
  
  // G-force reset
  document.getElementById('gforce-reset-btn')?.addEventListener('click', () => GForce.resetPeak());
}

// ============================================================================
// DYNO MODE
// ============================================================================

const DynoMode = {
  running: false,
  startTime: null,
  peakHp: 0,
  peakTorque: 0,
  peakRpm: 0,
  hpCurve: [],
  torqueCurve: [],
  
  // Rough HP calculation (very approximate without actual dyno)
  // HP = (Torque × RPM) / 5252
  // We estimate torque from MAP, RPM, and VE
  calculateHP(data) {
    const { rpm, map, veCurr1, mat } = data;
    if (!rpm || rpm < 1000) return { hp: 0, torque: 0 };
    
    // Very rough estimation - real dyno would use measured wheel torque
    // This is just for display purposes
    const displacement = 1.8; // Liters - Miata
    const airDensity = 1.225; // kg/m³
    const ve = (veCurr1 || 80) / 100;
    const volumetricFlow = (rpm / 2) * (displacement / 1000) * ve * (map / 101.325);
    
    // Estimated torque (very rough)
    const estimatedTorque = volumetricFlow * 15; // Arbitrary scaling
    const estimatedHP = (estimatedTorque * rpm) / 5252;
    
    return {
      hp: Math.max(0, estimatedHP),
      torque: Math.max(0, estimatedTorque),
    };
  },
  
  start() {
    this.running = true;
    this.startTime = Date.now();
    this.peakHp = 0;
    this.peakTorque = 0;
    this.peakRpm = 0;
    this.hpCurve = [];
    this.torqueCurve = [];
    
    Audio.stagingBeep();
    console.log('Dyno run started');
  },
  
  stop() {
    this.running = false;
    console.log(`Dyno run complete. Peak HP: ${this.peakHp.toFixed(1)} @ ${this.peakRpm} RPM`);
    Audio.warning('success');
  },
  
  update(data) {
    if (!this.running) return;
    
    const { hp, torque } = this.calculateHP(data);
    const rpm = data.rpm || 0;
    
    // Record curve data
    this.hpCurve.push({ rpm, hp });
    this.torqueCurve.push({ rpm, torque });
    
    // Track peaks
    if (hp > this.peakHp) {
      this.peakHp = hp;
      this.peakRpm = rpm;
    }
    if (torque > this.peakTorque) {
      this.peakTorque = torque;
    }
    
    this.updateDisplay(hp, torque, rpm);
    
    // Auto-stop if RPM drops significantly after peak
    if (rpm < this.peakRpm - 1500 && this.peakRpm > 5000) {
      this.stop();
    }
  },
  
  updateDisplay(hp, torque, rpm) {
    const hpEl = document.getElementById('dyno-hp');
    const torqueEl = document.getElementById('dyno-torque');
    const peakHpEl = document.getElementById('dyno-peak-hp');
    const peakRpmEl = document.getElementById('dyno-peak-rpm');
    
    if (hpEl) hpEl.textContent = hp.toFixed(1);
    if (torqueEl) torqueEl.textContent = torque.toFixed(1);
    if (peakHpEl) peakHpEl.textContent = this.peakHp.toFixed(1);
    if (peakRpmEl) peakRpmEl.textContent = this.peakRpm;
  },
  
  drawCurves(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || this.hpCurve.length < 2) return;
    
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas;
    
    ctx.clearRect(0, 0, width, height);
    
    const maxHp = Math.max(...this.hpCurve.map(p => p.hp), 1);
    const maxTorque = Math.max(...this.torqueCurve.map(p => p.torque), 1);
    const maxRpm = Math.max(...this.hpCurve.map(p => p.rpm), 8000);
    const minRpm = Math.min(...this.hpCurve.map(p => p.rpm));
    
    // Draw HP curve (cyan)
    ctx.beginPath();
    ctx.strokeStyle = '#00ffff';
    ctx.lineWidth = 2;
    
    this.hpCurve.forEach((point, i) => {
      const x = ((point.rpm - minRpm) / (maxRpm - minRpm)) * width;
      const y = height - (point.hp / maxHp) * height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    // Draw Torque curve (pink)
    ctx.beginPath();
    ctx.strokeStyle = '#ff0080';
    ctx.lineWidth = 2;
    
    this.torqueCurve.forEach((point, i) => {
      const x = ((point.rpm - minRpm) / (maxRpm - minRpm)) * width;
      const y = height - (point.torque / maxTorque) * height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    // Labels
    ctx.fillStyle = '#00ffff';
    ctx.font = '10px sans-serif';
    ctx.fillText(`HP: ${maxHp.toFixed(0)}`, 5, 12);
    ctx.fillStyle = '#ff0080';
    ctx.fillText(`TQ: ${maxTorque.toFixed(0)}`, 5, 24);
  },
};

// ============================================================================
// DRAG AND DROP LAYOUT
// ============================================================================

const DragAndDropLayout = {
  enabled: false,
  dragging: null,
  offset: { x: 0, y: 0 },
  layouts: {},
  
  init() {
    document.querySelectorAll('.draggable-panel').forEach(panel => {
      panel.addEventListener('mousedown', (e) => this.startDrag(e, panel));
      panel.addEventListener('touchstart', (e) => this.startDrag(e, panel), { passive: false });
    });
    
    document.addEventListener('mousemove', (e) => this.drag(e));
    document.addEventListener('touchmove', (e) => this.drag(e), { passive: false });
    document.addEventListener('mouseup', () => this.endDrag());
    document.addEventListener('touchend', () => this.endDrag());
    
    // Load saved layout
    this.loadLayout();
  },
  
  toggle() {
    this.enabled = !this.enabled;
    document.body.classList.toggle('layout-edit-mode', this.enabled);
    
    if (this.enabled) {
      console.log('Layout edit mode enabled. Drag panels to reposition.');
    } else {
      this.saveLayout();
      console.log('Layout saved.');
    }
  },
  
  startDrag(e, panel) {
    if (!this.enabled) return;
    e.preventDefault();
    
    this.dragging = panel;
    panel.classList.add('dragging');
    
    const rect = panel.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    this.offset = {
      x: clientX - rect.left,
      y: clientY - rect.top,
    };
  },
  
  drag(e) {
    if (!this.dragging) return;
    e.preventDefault();
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    const x = clientX - this.offset.x;
    const y = clientY - this.offset.y;
    
    this.dragging.style.position = 'fixed';
    this.dragging.style.left = `${x}px`;
    this.dragging.style.top = `${y}px`;
    this.dragging.style.zIndex = '1000';
  },
  
  endDrag() {
    if (this.dragging) {
      this.dragging.classList.remove('dragging');
      this.dragging = null;
    }
  },
  
  saveLayout() {
    const layout = {};
    document.querySelectorAll('.draggable-panel').forEach(panel => {
      const id = panel.id || panel.dataset.panelId;
      if (id) {
        layout[id] = {
          left: panel.style.left,
          top: panel.style.top,
          width: panel.style.width,
          height: panel.style.height,
        };
      }
    });
    
    localStorage.setItem('ms2d_layout', JSON.stringify(layout));
    this.layouts.current = layout;
  },
  
  loadLayout() {
    const saved = localStorage.getItem('ms2d_layout');
    if (!saved) return;
    
    try {
      const layout = JSON.parse(saved);
      this.layouts.current = layout;
      
      Object.entries(layout).forEach(([id, pos]) => {
        const panel = document.getElementById(id) || document.querySelector(`[data-panel-id="${id}"]`);
        if (panel && pos.left) {
          panel.style.position = 'fixed';
          panel.style.left = pos.left;
          panel.style.top = pos.top;
          if (pos.width) panel.style.width = pos.width;
          if (pos.height) panel.style.height = pos.height;
        }
      });
    } catch (e) {
      console.error('Failed to load layout:', e);
    }
  },
  
  resetLayout() {
    localStorage.removeItem('ms2d_layout');
    location.reload();
  },
};

// ============================================================================
// INITIALIZATION
// ============================================================================
// INITIALIZATION
// ============================================================================

async function start() {
  console.log('MS2D Dashboard ULTIMATE starting...');
  
  // Initialize systems
  Audio.init();
  GForce.init();
  setupUI();
  initKeyboardShortcuts();
  
  // Initialize load heatmap
  for (let i = 0; i < 17; i++) {
    state.loadHeatmap[i] = new Array(10).fill(0);
  }
  
  // Wait for daemon to be ready (with visual feedback)
  console.log('Waiting for daemon connection...');
  await waitForDaemon();
  
  // Start polling
  poll();
  setInterval(poll, CONFIG.pollInterval);
  
  // Start animation loop for charts
  function animationLoop() {
    Charts.drawRpmRibbon('rpm-ribbon');
    requestAnimationFrame(animationLoop);
  }
  animationLoop();
  
  console.log('Dashboard ready. Keyboard shortcuts:');
  console.log('  L - Toggle data logging');
  console.log('  E - Export CSV');
  console.log('  R - Reset peaks');
  console.log('  S - Stage drag race');
  console.log('  D - Start/stop dyno run');
  console.log('  P - Toggle layout edit mode');
  console.log('  SPACE - Lap timer');
  console.log('  M - Toggle display mode');
  console.log('  F - Fullscreen');
  
  // Initialize drag-and-drop (if panels exist)
  DragAndDropLayout.init();
}

/**
 * Wait for daemon to be ready by polling status endpoint
 * Retries with exponential backoff
 */
async function waitForDaemon() {
  const maxRetries = 30;  // 30 retries = ~30 seconds max wait
  let delay = 200;  // Start with 200ms
  
  for (let i = 0; i < maxRetries; i++) {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const status = await res.json();
        if (status.connected) {
          console.log(`Daemon connected: ${status.signature || 'MS2'}`);
          state.daemonReady = true;
          setConnected(true, status.signature || 'MS2');
          return;
        }
      }
    } catch (e) {
      // Ignore errors during startup
    }
    
    // Wait before retry with exponential backoff (cap at 2s)
    await new Promise(r => setTimeout(r, delay));
    delay = Math.min(delay * 1.2, 2000);
  }
  
  console.warn('Daemon not responding after retries, starting anyway...');
  state.daemonReady = true;  // Allow polling to start anyway
}

// Init on DOM ready
document.addEventListener('DOMContentLoaded', start);

// Expose for console debugging
window.MS2D = {
  state,
  CONFIG,
  DataLogger,
  Playback,
  DragRace,
  LapTimer,
  GForce,
  History,
  Charts,
  DisplayModes,
  Audio,
  DynoMode,
  DragAndDropLayout,
};

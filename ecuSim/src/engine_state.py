"""
Engine state simulation for MS2Extra ECU.

Simulates realistic engine behavior including:
- RPM, MAP, TPS variations
- Temperature changes over time
- Different driving modes (idle, cruise, acceleration, deceleration)
- Fuel and ignition parameters
"""

from __future__ import annotations
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EngineState:
    """Simulated engine state with realistic behavior."""

    # Core parameters
    rpm: float = 850.0
    target_rpm: float = 850.0
    map_kpa: float = 35.0
    tps: float = 0.0

    # Temperatures (Fahrenheit for MS2Extra default)
    coolant: float = 180.0
    mat: float = 85.0

    # Fuel/ignition
    afr: float = 14.7
    advance: float = 15.0
    pulse_width: float = 2.5
    pulse_width2: float = 2.5
    dwell: float = 3.0

    # Battery
    battery: float = 14.1

    # Barometer
    barometer: float = 101.3

    # Timing
    start_time: float = field(default_factory=time.time)

    # State flags
    running: bool = True
    cranking: bool = False
    warmup: bool = False

    # Simulation mode
    mode: str = "idle"  # idle, cruise, accel, decel
    mode_timer: float = 0.0

    # EGO correction
    ego_correction1: float = 100.0
    ego_correction2: float = 100.0

    # VE values
    ve_curr1: float = 75.0
    ve_curr2: float = 75.0

    # Idle control
    iac_step: int = 30

    # Knock
    knock_voltage: float = 0.0
    knock_retard: float = 0.0

    # Enrichment
    warmup_enrich: float = 100.0
    accel_enrich: float = 0.0
    gamma_enrich: float = 100.0
    air_correction: float = 100.0
    baro_correction: float = 100.0

    # Derivatives
    tps_dot: float = 0.0
    map_dot: float = 0.0
    rpm_dot: float = 0.0

    # Previous values for calculating derivatives
    _prev_tps: float = 0.0
    _prev_map: float = 35.0
    _prev_rpm: float = 850.0

    def update(self, dt: float):
        """Update engine state for one time step."""
        self.mode_timer -= dt

        # Randomly change driving mode
        if self.mode_timer <= 0:
            self._change_mode()

        # Store previous values for derivatives
        self._prev_tps = self.tps
        self._prev_map = self.map_kpa
        self._prev_rpm = self.rpm

        # Update based on mode
        if self.mode == "idle":
            self._update_idle(dt)
        elif self.mode == "cruise":
            self._update_cruise(dt)
        elif self.mode == "accel":
            self._update_accel(dt)
        elif self.mode == "decel":
            self._update_decel(dt)

        # Smooth RPM changes
        rpm_diff = self.target_rpm - self.rpm
        self.rpm += rpm_diff * min(1.0, dt * 5)
        self.rpm = max(0, self.rpm)

        # Calculate derivatives
        if dt > 0:
            self.tps_dot = (self.tps - self._prev_tps) / dt
            self.map_dot = (self.map_kpa - self._prev_map) / dt
            self.rpm_dot = (self.rpm - self._prev_rpm) / dt

        # RPM affects other params
        self._update_fuel_params(dt)
        self._update_temperatures(dt)
        self._update_battery(dt)
        self._update_enrichments(dt)

        # Update state flags
        self.warmup = self.coolant < 160
        self.cranking = False

    def _update_idle(self, dt: float):
        """Update state for idle mode."""
        self.target_rpm = 850 + random.uniform(-20, 20)
        self.tps = max(0, self.tps - dt * 50)
        self.map_kpa = 30 + random.uniform(-2, 2)
        self.afr = 14.7 + random.uniform(-0.3, 0.3)
        self.advance = 18 + random.uniform(-1, 1)
        self.iac_step = 30 + int(random.uniform(-5, 5))

    def _update_cruise(self, dt: float):
        """Update state for cruise mode."""
        self.target_rpm = 2800 + random.uniform(-100, 100)
        self.tps = 25 + random.uniform(-3, 3)
        self.map_kpa = 55 + random.uniform(-5, 5)
        self.afr = 14.5 + random.uniform(-0.2, 0.2)
        self.advance = 28 + random.uniform(-2, 2)
        self.iac_step = 0

    def _update_accel(self, dt: float):
        """Update state for acceleration mode."""
        self.target_rpm = min(6500, self.target_rpm + dt * 2000)
        self.tps = min(95, self.tps + dt * 100)
        self.map_kpa = min(100, 40 + self.tps * 0.6)
        self.afr = 12.5 + random.uniform(-0.3, 0.3)  # Rich under load
        self.advance = max(10, 35 - self.map_kpa * 0.2)
        self.iac_step = 0
        self.accel_enrich = self.tps_dot * 0.1  # Acceleration enrichment

    def _update_decel(self, dt: float):
        """Update state for deceleration mode."""
        self.target_rpm = max(1200, self.target_rpm - dt * 1500)
        self.tps = max(0, self.tps - dt * 80)
        self.map_kpa = max(20, self.map_kpa - dt * 30)
        self.afr = 15.5 + random.uniform(-0.2, 0.2)  # Lean on decel
        self.advance = 25 + random.uniform(-2, 2)
        self.iac_step = 0
        self.accel_enrich = 0.0

    def _update_fuel_params(self, dt: float):
        """Update fuel-related parameters."""
        self.pulse_width = 1.5 + (self.map_kpa / 100) * 8 + random.uniform(-0.1, 0.1)
        self.pulse_width2 = self.pulse_width + random.uniform(-0.05, 0.05)
        self.dwell = 2.5 + random.uniform(-0.1, 0.1)

        # VE based on load
        self.ve_curr1 = 75 + (self.map_kpa / 100) * 50 + random.uniform(-2, 2)
        self.ve_curr2 = self.ve_curr1 + random.uniform(-1, 1)

        # EGO correction
        self.ego_correction1 = 100.0 + random.uniform(-3, 3)
        self.ego_correction2 = 100.0 + random.uniform(-3, 3)

    def _update_temperatures(self, dt: float):
        """Update temperature values."""
        # Coolant slowly approaches operating temp
        target_coolant = 190 if self.rpm > 500 else 70
        self.coolant += (target_coolant - self.coolant) * dt * 0.01
        self.coolant += random.uniform(-0.5, 0.5)

        # MAT based on airflow
        target_mat = 90 + (self.rpm / 6500) * 30
        self.mat += (target_mat - self.mat) * dt * 0.05
        self.mat += random.uniform(-0.2, 0.2)

    def _update_battery(self, dt: float):
        """Update battery voltage."""
        # Slight variation, drops slightly at high RPM
        self.battery = 14.1 - (self.rpm / 6500) * 0.3 + random.uniform(-0.05, 0.05)

    def _update_enrichments(self, dt: float):
        """Update enrichment values."""
        self.warmup_enrich = 100 + (20 if self.warmup else 0)
        self.gamma_enrich = 100 + (10 if self.warmup else 0)
        self.air_correction = 100.0 + random.uniform(-1, 1)
        self.baro_correction = 100.0

    def _change_mode(self):
        """Randomly change driving mode based on current state."""
        modes = ["idle", "cruise", "accel", "decel"]

        # Bias based on current state
        if self.rpm < 1000:
            weights = [0.2, 0.3, 0.4, 0.1]  # More likely to accel from idle
        elif self.rpm > 5000:
            weights = [0.1, 0.2, 0.1, 0.6]  # More likely to decel from high RPM
        else:
            weights = [0.3, 0.35, 0.2, 0.15]

        self.mode = random.choices(modes, weights)[0]
        self.mode_timer = random.uniform(2.0, 8.0)

    @property
    def seconds(self) -> int:
        """ECU uptime in seconds."""
        return int(time.time() - self.start_time)

    @property
    def engine_bits(self) -> int:
        """Get engine status bits."""
        bits = 0
        if self.running:
            bits |= 0x01  # ready
        if self.cranking:
            bits |= 0x02  # crank
        if self.warmup:
            bits |= 0x0C  # startw + warmup
        return bits

    @property
    def squirt_bits(self) -> int:
        """Get squirt status bits."""
        return 0x28 if self.running else 0  # inj1 + sched1

    @property
    def afr_target(self) -> float:
        """Get current AFR target based on conditions."""
        if self.tps > 80:
            return 12.5  # Rich at WOT
        return 14.7  # Stoich

    def set_mode(self, mode: str):
        """Manually set the simulation mode."""
        if mode in ("idle", "cruise", "accel", "decel"):
            self.mode = mode
            self.mode_timer = 999.0  # Long timer to stay in this mode


class ScenarioRunner:
    """Run predefined scenarios for testing."""

    def __init__(self, state: EngineState):
        self.state = state
        self.scenario_name: Optional[str] = None
        self.scenario_step: int = 0
        self.scenario_timer: float = 0.0

    def run_cold_start(self):
        """Simulate a cold start scenario."""
        self.scenario_name = "cold_start"
        self.state.coolant = 70.0
        self.state.mat = 60.0
        self.state.warmup = True
        self.state.cranking = True
        self.state.rpm = 0
        self.scenario_step = 0

    def run_warmup(self):
        """Simulate warmup driving."""
        self.scenario_name = "warmup"
        self.state.coolant = 100.0
        self.state.warmup = True
        self.scenario_step = 0

    def run_highway(self):
        """Simulate highway cruising."""
        self.scenario_name = "highway"
        self.state.set_mode("cruise")
        self.state.target_rpm = 3500
        self.state.tps = 30
        self.state.map_kpa = 70

    def run_track_day(self):
        """Simulate aggressive track driving."""
        self.scenario_name = "track"
        self.scenario_step = 0

    def update(self, dt: float):
        """Update the current scenario."""
        if not self.scenario_name:
            return

        if self.scenario_name == "cold_start":
            self._update_cold_start(dt)
        elif self.scenario_name == "track":
            self._update_track(dt)

    def _update_cold_start(self, dt: float):
        """Update cold start scenario."""
        self.scenario_timer += dt

        if self.scenario_step == 0 and self.scenario_timer > 2.0:
            # Start cranking
            self.state.cranking = True
            self.state.rpm = 250
            self.scenario_step = 1
        elif self.scenario_step == 1 and self.scenario_timer > 4.0:
            # Engine catches
            self.state.cranking = False
            self.state.running = True
            self.state.rpm = 1200
            self.scenario_step = 2
        elif self.scenario_step == 2 and self.scenario_timer > 8.0:
            # Settle to fast idle
            self.state.target_rpm = 1100
            self.scenario_step = 3
        elif self.scenario_step == 3:
            # Gradually warm up
            self.state.coolant += dt * 0.5
            if self.state.coolant > 180:
                self.scenario_name = None

    def _update_track(self, dt: float):
        """Update track scenario with aggressive driving."""
        self.scenario_timer += dt

        # Cycle through hard acceleration and braking
        cycle_time = self.scenario_timer % 20.0

        if cycle_time < 8.0:
            # Hard acceleration
            self.state.set_mode("accel")
            self.state.target_rpm = 6000 + random.uniform(-200, 200)
        elif cycle_time < 12.0:
            # Hard braking
            self.state.set_mode("decel")
        elif cycle_time < 16.0:
            # Corner (medium load)
            self.state.target_rpm = 4000
            self.state.tps = 40
            self.state.map_kpa = 60
        else:
            # Exit corner, accelerate
            self.state.set_mode("accel")

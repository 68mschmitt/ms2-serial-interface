"""
OUTPC data builder for MS2Extra ECU simulator.

Builds the Output Channels (OUTPC) data block that TunerStudio reads
to display realtime engine data.
"""

from __future__ import annotations
import struct
from typing import Optional

try:
    from .ini_parser import INIConfig, FieldDef
    from .engine_state import EngineState
except ImportError:
    from ini_parser import INIConfig, FieldDef
    from engine_state import EngineState


class OUTPCBuilder:
    """Builds OUTPC data block from engine state."""

    def __init__(self, config: INIConfig, state: EngineState):
        self.config = config
        self.state = state

    def build(self) -> bytes:
        """Build the complete OUTPC data block."""
        buffer = bytearray(self.config.och_block_size)

        # Map engine state to field values
        field_values = self._get_field_values()

        # Encode each field
        for name, value in field_values.items():
            if name in self.config.output_channels:
                field = self.config.output_channels[name]
                self._encode_field(buffer, field, value)

        return bytes(buffer)

    def _get_field_values(self) -> dict[str, float]:
        """Get current values for all output channel fields."""
        s = self.state

        return {
            # Timing
            "seconds": float(s.seconds),
            # RPM and timing
            "rpm": s.rpm,
            "advance": s.advance,
            # Pulse widths
            "pulseWidth1": s.pulse_width,
            "pulseWidth2": s.pulse_width2,
            "pulseWidth3": s.pulse_width,
            "pulseWidth4": s.pulse_width2,
            # Status bits
            "squirt": float(s.squirt_bits),
            "engine": float(s.engine_bits),
            # AFR targets
            "afrtgt1": s.afr_target,
            "afrtgt2": s.afr_target,
            # Sensors
            "barometer": s.barometer,
            "map": s.map_kpa,
            "mat": s.mat,
            "coolant": s.coolant,
            "tps": s.tps,
            "batteryVoltage": s.battery,
            # Wideband O2
            "afr1": s.afr,
            "afr2": s.afr + 0.1,
            "wbo2_en1": 1.0,
            "wbo2_en2": 1.0,
            # Knock
            "knock": s.knock_voltage,
            "knockRetard": s.knock_retard,
            # Corrections
            "egoCorrection1": s.ego_correction1,
            "egoCorrection2": s.ego_correction2,
            "airCorrection": s.air_correction,
            "warmupEnrich": s.warmup_enrich,
            "accelEnrich": s.accel_enrich,
            "tpsfuelcut": 100.0,
            "baroCorrection": s.baro_correction,
            "gammaEnrich": s.gamma_enrich,
            # VE
            "veCurr1": s.ve_curr1,
            "veCurr2": s.ve_curr2,
            # Idle
            "iacstep": float(s.iac_step),
            "idleDC": float(s.iac_step) * 0.392,
            # Cold advance
            "coldAdvDeg": 2.0 if s.warmup else 0.0,
            # Derivatives
            "TPSdot": s.tps_dot,
            "MAPdot": s.map_dot,
            "RPMdot": s.rpm_dot,
            # Dwell
            "dwell": s.dwell,
            "dwell_trl": s.dwell * 0.8,
            # Load
            "fuelload": s.map_kpa,
            "fuelload2": s.map_kpa,
            "ignload": s.map_kpa,
            "ignload2": s.map_kpa,
            "mafload": s.map_kpa,
            # Fuel correction
            "fuelCorrection": 100.0,
            # Loop time (typical value)
            "looptime": 15000.0,
            # Sync
            "synccnt": 1.0,
            "syncreason": 0.0,
            # Status bytes
            "status1": 0.0,
            "status2": 0.0,
            "status3": 0.0,
            "status4": 0.0,
            # Timing error
            "timing_err": 0.0,
            # Wall fuel
            "wallfuel1": 0.0,
            "wallfuel2": 0.0,
            # EAE
            "EAEFuelCorr1": 100.0,
            "EAEFuelCorr2": 100.0,
            "eaeload1": s.map_kpa,
            "afrload1": s.map_kpa,
            # Boost
            "boostduty": 0.0,
            "boost_targ": 0.0,
            # GPIO (default zeros)
            "gpioadc0": 512.0,
            "gpioadc1": 512.0,
            "gpioadc2": 512.0,
            "gpioadc3": 512.0,
            "gpioadc4": 512.0,
            "gpioadc5": 512.0,
            "gpioadc6": 512.0,
            "gpioadc7": 512.0,
            # Injection advance
            "inj_adv1": 0.0,
            "inj_adv2": 0.0,
            # VE trim
            "vetrim1curr": 100.0,
            "vetrim2curr": 100.0,
            "vetrim3curr": 100.0,
            "vetrim4curr": 100.0,
            # MAF
            "maf": 0.0,
            "maf_volts": 0.0,
            # Airtemp (same as MAT for non-separate sensor)
            "airtemp": s.mat,
            # Fuel percent
            "fuel_pct": 0.0,
            # Advance breakdown
            "ext_advance": 0.0,
            "base_advance": s.advance,
            "idle_cor_advance": 0.0,
            "mat_retard": 0.0,
            "flex_advance": 0.0,
            "adv1": s.advance,
            "adv2": 0.0,
            "adv3": 0.0,
            "revlim_retard": 0.0,
            "nitrous_retard": 0.0,
            # Deadtime
            "deadtime1": 1.0,
            # Nitrous
            "n2o_addfuel": 0.0,
            # Port status
            "portStatus": 0.0,
            "portbde": 0.0,
            "portam": 0.0,
            "portt": 0.0,
            # TPS ADC
            "tpsADC": s.tps * 10.23,
            # Delta T
            "deltaT": 60000000.0 / max(s.rpm, 1),
            # Idle target
            "cl_idle_targ_rpm": 850.0,
            "idleupcnt": 0.0,
            # User variables
            "user0": 0.0,
            # GPIO ports
            "gpioport0": 0.0,
            "gpioport1": 0.0,
            "gpioport2": 0.0,
            # PWM inputs
            "gpiopwmin0": 0.0,
            "gpiopwmin1": 0.0,
            "gpiopwmin2": 0.0,
            "gpiopwmin3": 0.0,
            # ADC channels
            "adc6": 0.0,
            "adc7": 0.0,
        }

    def _encode_field(self, buffer: bytearray, field: FieldDef, value: float):
        """Encode a value into the buffer at the field's offset."""
        if field.offset + field.size > len(buffer):
            return

        # Skip calculated/virtual fields (no physical offset in OUTPC)
        if field.field_type == "bits" and field.bit_range is None:
            return

        # Reverse the decode formula: msValue = userValue / scale - translate
        if field.scale != 0:
            raw = (value / field.scale) - field.translate
        else:
            raw = value

        # Clamp to type range
        type_ranges = {
            "U08": (0, 255),
            "S08": (-128, 127),
            "U16": (0, 65535),
            "S16": (-32768, 32767),
            "U32": (0, 4294967295),
            "S32": (-2147483648, 2147483647),
        }
        lo, hi = type_ranges.get(field.data_type, (0, 65535))
        raw = max(lo, min(hi, int(raw)))

        # Pack into buffer
        try:
            struct.pack_into(field.struct_format, buffer, field.offset, raw)
        except struct.error:
            pass  # Skip if offset/format issues

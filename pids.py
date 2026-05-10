# ============================================================
# pids.py — XC90 T6 PID Definitions
# 2018 Volvo XC90 T6 Inscription (B4204T23, SPA Platform)
# Mode 01 standard OBD-II PIDs only (no enhanced/UDS)
# Designed for AI-ready single-row-per-cycle output
# ============================================================

from config import (
    SAMPLE_RATE_CRITICAL,
    SAMPLE_RATE_STANDARD,
    SAMPLE_RATE_SLOW,
)


# ---- Critical (1s) — engine vitals ----

CRITICAL_PIDS = {

    "rpm": {
        "cmd":     "010C",
        "bytes":   2,
        "unit":    "rpm",
        "min":     0,
        "max":     7000,
        "tier":    "critical",
        "tier_ms": SAMPLE_RATE_CRITICAL,
        "formula": lambda b: ((b[0] * 256) + b[1]) / 4
    },

    "coolant_temp_c": {
        "cmd":     "0105",
        "bytes":   1,
        "unit":    "degC",
        "min":     -40,
        "max":     215,
        "tier":    "critical",
        "tier_ms": SAMPLE_RATE_CRITICAL,
        "formula": lambda b: b[0] - 40
    },

    "boost_actual_kpa": {
        "cmd":     "010B",
        "bytes":   1,
        "unit":    "kPa",
        "min":     0,
        "max":     255,
        "tier":    "critical",
        "tier_ms": SAMPLE_RATE_CRITICAL,
        "formula": lambda b: b[0]
    },

    "vehicle_speed_kph": {
        "cmd":     "010D",
        "bytes":   1,
        "unit":    "kph",
        "min":     0,
        "max":     300,
        "tier":    "critical",
        "tier_ms": SAMPLE_RATE_CRITICAL,
        "formula": lambda b: b[0]
    },

}


# ---- Standard (2s) — fuel, air, load ----

STANDARD_PIDS = {

    "engine_load_pct": {
        "cmd":     "0104",
        "bytes":   1,
        "unit":    "pct",
        "min":     0,
        "max":     100,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(b[0] / 2.55, 1)
    },

    "throttle_pos_pct": {
        "cmd":     "0111",
        "bytes":   1,
        "unit":    "pct",
        "min":     0,
        "max":     100,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(b[0] / 2.55, 1)
    },

    "stft_pct": {
        "cmd":     "0106",
        "bytes":   1,
        "unit":    "pct",
        "min":     -100,
        "max":     99.2,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round((b[0] / 128.0) * 100 - 100, 2)
    },

    "ltft_pct": {
        "cmd":     "0107",
        "bytes":   1,
        "unit":    "pct",
        "min":     -100,
        "max":     99.2,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round((b[0] / 128.0) * 100 - 100, 2)
    },

    "maf_g_s": {
        "cmd":     "0110",
        "bytes":   2,
        "unit":    "g/s",
        "min":     0,
        "max":     655.35,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(((b[0] * 256) + b[1]) / 100, 2)
    },

    "intake_air_temp_c": {
        "cmd":     "010F",
        "bytes":   1,
        "unit":    "degC",
        "min":     -40,
        "max":     215,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: b[0] - 40
    },

    # --- New PIDs for AI model ---

    "timing_advance_deg": {
        "cmd":     "010E",
        "bytes":   1,
        "unit":    "deg",
        "min":     -64,
        "max":     63.5,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(b[0] / 2.0 - 64, 1)
        # Knock/pinging detection: sudden retarding = trouble
    },

    "fuel_system_status": {
        "cmd":     "0103",
        "bytes":   2,
        "unit":    "code",
        "min":     0,
        "max":     255,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: b[0]
        # 1=open loop, 2=closed loop, 4=open loop drive
        # Stuck open loop = sensor/ECU failure
    },

    "o2_lambda": {
        "cmd":     "0114",
        "bytes":   2,
        "unit":    "ratio",
        "min":     0,
        "max":     2.0,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(((b[0] * 256) + b[1]) / 32768, 3)
        # Wideband O2: actual AFR reading from sensor
        # More precise than fuel trims alone
    },

    "absolute_load_pct": {
        "cmd":     "0143",
        "bytes":   2,
        "unit":    "pct",
        "min":     0,
        "max":     25700,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(((b[0] * 256) + b[1]) * 100 / 255, 1)
        # Better load metric — uses MAF, RPM, displacement
    },

}


# ---- Slow (5s) — health, temperature, battery, DTCs ----

SLOW_PIDS = {

    "oil_temp_c": {
        "cmd":     "015C",
        "bytes":   1,
        "unit":    "degC",
        "min":     -40,
        "max":     215,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: b[0] - 40
    },

    "battery_voltage_v": {
        "cmd":     "0142",
        "bytes":   2,
        "unit":    "V",
        "min":     0,
        "max":     65.535,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: round(((b[0] * 256) + b[1]) / 1000, 2)
    },

    "baro_pressure_kpa": {
        "cmd":     "0133",
        "bytes":   1,
        "unit":    "kPa",
        "min":     0,
        "max":     255,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: b[0]
    },

    # --- New PIDs for AI model ---

    "fuel_pressure_kpa": {
        "cmd":     "010A",
        "bytes":   1,
        "unit":    "kPa",
        "min":     0,
        "max":     765,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: b[0] * 3
        # Fuel pump health — similar failure mode to oil pump
        # Dropping pressure at high RPM = pump weakening
    },

    "ambient_air_temp_c": {
        "cmd":     "0146",
        "bytes":   1,
        "unit":    "degC",
        "min":     -40,
        "max":     215,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: b[0] - 40
        # Compare with intake_air_temp_c for intercooler health
        # Big gap under load = intercooler/heat soak issue
    },

    "engine_run_time_s": {
        "cmd":     "011F",
        "bytes":   2,
        "unit":    "s",
        "min":     0,
        "max":     65535,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: (b[0] * 256) + b[1]
        # Cold start tracking: hard on bearings/oil
        # Pair with coolant temp to measure warmup rate
    },

    "dtc_count": {
        "cmd":     "0101",
        "bytes":   4,
        "unit":    "count",
        "min":     0,
        "max":     127,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: b[0] & 0x7F
        # Byte A bit 7 = MIL status, bits 6-0 = DTC count
        # Mask off MIL bit so count isn't +128 when check-engine is on
        # Non-zero = Volvo already found a problem
        # Catches oil pressure, misfire, sensor failures etc.
    },

    "fuel_rate_l_h": {
        "cmd":     "015E",
        "bytes":   2,
        "unit":    "L/h",
        "min":     0,
        "max":     3276.75,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": lambda b: round(((b[0] * 256) + b[1]) * 0.05, 2)
        # Fuel consumption — efficiency tracking
        # Sudden increase = injector/combustion issue
    },

    # Derived PIDs — calculated locally, not queried from ECU
    "fuel_trim_sum": {
        "cmd":     None,
        "bytes":   None,
        "unit":    "pct",
        "min":     -100,
        "max":     100,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": None
    },

    "iat_ambient_delta_c": {
        "cmd":     None,
        "bytes":   None,
        "unit":    "degC",
        "min":     -50,
        "max":     100,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": None
        # Intake temp minus ambient temp = intercooler efficiency
        # Climbing delta at cruise = intercooler failing
    },

}


# ---- Combined ----

ALL_PIDS = {}
ALL_PIDS.update(CRITICAL_PIDS)
ALL_PIDS.update(STANDARD_PIDS)
ALL_PIDS.update(SLOW_PIDS)

# Only queryable PIDs (excludes derived ones with cmd=None)
QUERYABLE_PIDS = {}
for k, v in ALL_PIDS.items():
    if v["cmd"] is not None:
        QUERYABLE_PIDS[k] = v

# PIDs grouped by tier for the sampler
PIDS_BY_TIER = {
    "critical": {k: v for k, v in ALL_PIDS.items() if v["tier"] == "critical"},
    "standard": {k: v for k, v in ALL_PIDS.items() if v["tier"] == "standard"},
    "slow":     {k: v for k, v in ALL_PIDS.items() if v["tier"] == "slow"},
}
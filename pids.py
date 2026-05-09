# ============================================================
# pids.py — XC90 T6 PID Definitions
# 2018 Volvo XC90 T6 Inscription (B4204T23, SPA Platform)
# Standard OBD-II + Enhanced Volvo PIDs
# ============================================================

from config import (
    SAMPLE_RATE_CRITICAL,
    SAMPLE_RATE_STANDARD,
    SAMPLE_RATE_SLOW,
    SAMPLE_RATE_ENHANCED
)


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
        "unit":    "°C",
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


STANDARD_PIDS = {

    "engine_load_pct": {
        "cmd":     "0104",
        "bytes":   1,
        "unit":    "%",
        "min":     0,
        "max":     100,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(b[0] / 2.55, 1)
    },

    "throttle_pos_pct": {
        "cmd":     "0111",
        "bytes":   1,
        "unit":    "%",
        "min":     0,
        "max":     100,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round(b[0] / 2.55, 1)
    },

    "stft_pct": {
        "cmd":     "0106",
        "bytes":   1,
        "unit":    "%",
        "min":     -100,
        "max":     99.2,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: round((b[0] / 128.0) * 100 - 100, 2)
    },

    "ltft_pct": {
        "cmd":     "0107",
        "bytes":   1,
        "unit":    "%",
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
        "unit":    "°C",
        "min":     -40,
        "max":     215,
        "tier":    "standard",
        "tier_ms": SAMPLE_RATE_STANDARD,
        "formula": lambda b: b[0] - 40
    },

}


SLOW_PIDS = {

    "oil_temp_c": {
        "cmd":     "015C",
        "bytes":   1,
        "unit":    "°C",
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

    "fuel_trim_sum": {
        "cmd":     None,        # derived — calculated not queried
        "bytes":   None,
        "unit":    "%",
        "min":     -100,
        "max":     100,
        "tier":    "slow",
        "tier_ms": SAMPLE_RATE_SLOW,
        "formula": None         # logger.py calculates stft + ltft
    },

}

ENHANCED_PIDS = {

    "boost_target_kpa": {
        "cmd":     "21F40B",    # Volvo enhanced PID
        "bytes":   2,
        "unit":    "kPa",
        "min":     0,
        "max":     400,
        "tier":    "enhanced",
        "tier_ms": SAMPLE_RATE_ENHANCED,
        "formula": lambda b: round(((b[0] * 256) + b[1]) * 0.1, 1)
    },

    "boost_delta_kpa": {
        "cmd":     None,        # derived: boost_actual - boost_target
        "bytes":   None,
        "unit":    "kPa",
        "min":     -400,
        "max":     400,
        "tier":    "enhanced",
        "tier_ms": SAMPLE_RATE_ENHANCED,
        "formula": None         # calculated in logger.py
    },

    "turbo_inlet_pres": {
        "cmd":     "221182",
        "bytes":   2,
        "unit":    "kPa",
        "min":     0,
        "max":     400,
        "tier":    "enhanced",
        "tier_ms": SAMPLE_RATE_ENHANCED,
        "formula": lambda b: round(((b[0] * 256) + b[1]) * 0.1, 1)
    },

    "oil_pressure_kpa": {
        "cmd":     "22F42D",
        "bytes":   2,
        "unit":    "kPa",
        "min":     0,
        "max":     1000,
        "tier":    "enhanced",
        "tier_ms": SAMPLE_RATE_ENHANCED,
        "formula": lambda b: round(((b[0] * 256) + b[1]) * 0.1, 1)
    },

}


# Combined — all PIDs in one flat dict for easy iteration
ALL_PIDS = {}
ALL_PIDS.update(CRITICAL_PIDS)
ALL_PIDS.update(STANDARD_PIDS)
ALL_PIDS.update(SLOW_PIDS)
ALL_PIDS.update(ENHANCED_PIDS)

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
    "enhanced": {k: v for k, v in ALL_PIDS.items() if v["tier"] == "enhanced"},
}
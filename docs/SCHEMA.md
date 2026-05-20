# Schema Evolution Guide

## Overview

The XC90 Logger has **three places** that must agree on column schema:

| Location | File | Role |
|----------|------|------|
| **ESP32 firmware** | `logger.py` → `CSV_COLUMNS` | Defines what columns are written to flash CSV |
| **Google Sheets** | `deploy/code.gs` → `CSV_HEADERS` | Defines what columns the webhook accepts |
| **Google Sheets tab** | Row 1 of `XC90_Logs` | Live data — header row overwritten on every POST |

**Rule**: All three must be identical. If they drift, columns get silently dropped or misaligned.

---

## Current Schema (v0.1.0)

37 columns total. One row per second (AI-ready dense format).

```
1.   timestamp_utc           ISO8601 UTC time
2.   timestamp_local         ISO8601 local time (Toronto = UTC-5)
3.   trip_id                 XC90_20260509_110419
4.   trip_sequence           Incrementing row number per trip
5.   session_odometer        Trip distance in km (derived from speed × time)

6.   engine_state            cold_start | warming | normal | hot
7.   drive_phase             idle | light | moderate | hard | decel

--- Critical PIDs (every 1s) ---
8.   rpm                     Engine RPM
9.   coolant_temp_c          Coolant temperature (°C)
10.  boost_actual_kpa        Manifold absolute pressure (kPa)
11.  vehicle_speed_kph       Vehicle speed (km/h)

--- Standard PIDs (every 2s) ---
12.  engine_load_pct         Calculated engine load (%)
13.  throttle_pos_pct        Throttle position (%)
14.  stft_pct                Short-term fuel trim (%)
15.  ltft_pct                Long-term fuel trim (%)
16.  maf_g_s                 Mass air flow (g/s)
17.  intake_air_temp_c       Intake air temperature (°C)
18.  timing_advance_deg      Ignition timing advance (°)
19.  fuel_system_status      Open/closed loop (1=open, 2=closed)
20.  o2_lambda               Wideband O2 equivalence ratio
21.  absolute_load_pct       Normalized engine load (%)

--- Slow PIDs (every 5s, includes derived) ---
22.  oil_temp_c              Oil temperature (°C) — may return NO DATA on some ECUs
23.  battery_voltage_v       Battery voltage (V)
24.  baro_pressure_kpa       Barometric pressure (kPa)
25.  fuel_pressure_kpa       Fuel rail pressure (kPa)
26.  ambient_air_temp_c      Ambient air temperature (°C)
27.  engine_run_time_s       Engine run time since start (seconds)
28.  dtc_count               Stored diagnostic trouble codes (masked: bits 6-0)
29.  fuel_rate_l_h           Fuel consumption rate (L/h)
30.  fuel_trim_sum           STFT + LTFT combined correction (%) — derived
31.  iat_ambient_delta_c     IAT - Ambient temp (°C) — derived (intercooler health)

--- Metadata ---
32.  raw_pid                 PID command sent ("ALL" for sequential sampler)
33.  raw_response            Raw ELM327 response (sanitized)
34.  decode_status           ok | no_data | error | unsupported
35.  sample_tier             critical | standard | slow | sequential
36.  fw_version              Firmware version
37.  vin_partial             Last 6 of VIN
```

---

## How to Add a Column

### Step 1: Decide what you're adding

- **New OBD PID**: Add to `pids.py` in the appropriate tier (critical/standard/slow), then add column to CSV_COLUMNS.
- **Derived value**: Add formula to `decoder.py` → `calculate_derived()`, then add column to CSV_COLUMNS with a `"cmd": None` entry in `pids.py`.
- **Metadata**: Just add to CSV_COLUMNS and populate in `logger.py` → `build_row()`.

### Step 2: Update all three schema locations

```
1. logger.py   → CSV_COLUMNS list (append new column at logical position)
2. deploy/code.gs → CSV_HEADERS array (append in exact same position)
3. logger.py   → build_row() return dict (add the new key:value)
```

### Step 3: Bump the version

Update `FW_VERSION` in `config.py`. This is logged in every row so you know which firmware wrote which schema.

### Step 4: Deploy

1. Flash updated firmware to ESP32
2. Deploy updated `deploy/code.gs` to Google Apps Script
3. The next POST will overwrite the sheet's header row with the new schema
4. Old rows from previous firwmare will have empty values for new columns (forward-filled by SensorState)

### Step 5: Verify

Check the Google Sheet after the first upload:
- Row 1 should show the new headers
- New column should have values (not all empty)
- No data in wrong columns (schema alignment)

---

## How to Remove a Column

Same process as adding, but:

1. Remove from `CSV_COLUMNS` in `logger.py`
2. Remove from `CSV_HEADERS` in `deploy/code.gs`
3. Remove from `build_row()` in `logger.py`
4. Remove PID definition from `pids.py` if applicable
5. Bump `FW_VERSION`
6. Deploy both firmware and script

**⚠️ Warning**: Removing a column shifts all columns to the right of it one position left. Google Sheets won't automatically adjust charts, pivot tables, or formulas that reference those columns by letter (e.g., `=AVERAGE(J:J)`). Prefer adding new columns at the end if you have existing analysis that depends on column positions.

---

## Schema Alignment Guarantees

### On the ESP32 (`logger.py`)

- `build_row()` returns a dict keyed by `CSV_COLUMNS` names
- `LogBuffer.flush()` writes rows by iterating `CSV_COLUMNS` in order
- `SensorState` forward-fills: if a PID hasn't been queried this cycle, its last known value is used
- All columns always have a value (or empty string if never queried)

### In Google Sheets (`deploy/code.gs`)

- Header row is **overwritten on every POST** with `CSV_HEADERS`
- Row data is mapped column-by-column using `CSV_HEADERS` as the key
- Columns in the payload that aren't in `CSV_HEADERS` → silently dropped
- Columns in `CSV_HEADERS` that aren't in the payload → empty string `""`

### What happens during migration

| Scenario | Result |
|----------|--------|
| New firmware, old script | New columns silently dropped by script |
| Old firmware, new script | New columns show empty strings `""` |
| Both updated together ✅ | Full alignment |

**Always deploy both together.** The order doesn't matter — the script always writes headers on POST, so the first upload after both are deployed will fix the sheet.

---

## Future Considerations

### Schema versioning for AI training

If you train an ML model on data from schema v0.1.0, then add columns in v0.2.0:

- **Old data**: Missing columns → model trained on v0.1.0 won't have those features
- **New data**: Has extra columns → model trained on v0.1.0 ignores them
- **Solution**: Train a new model when you add features. The `fw_version` column lets you filter rows by schema version.

### Column ordering

Column positions are fixed by the order in `CSV_COLUMNS`. Google Sheets references columns by letter (A, B, C...), so:

- **Keep critical PIDs at fixed positions** (first columns) so existing charts don't break
- **Add new columns at the end** of their tier group
- **Never reorder columns** without updating all dependent charts/formulas

### Maximum columns

Google Sheets has a limit of 18,278 columns. You're at 37. Not a concern.

### Data volume

At 1 row/second, active driving:
- 1 hour = 3,600 rows
- Google Sheets limit: 10 million cells (rows × columns)
- With 37 columns: ~270,000 rows max per sheet = ~75 hours of driving
- Google Sheets also has a 200,000 cell limit per `setValues()` call
- The ESP32 uploader should batch in chunks of ≤50 rows to stay well under this

# XC90 OBD Logger — Architecture & Logic Reference

> **Target:** 2018 Volvo XC90 T6 Inscription (B4204T23, SPA Platform)  
> **Hardware:** ESP32-S3-WROOM-1 (LOLIN S3 Pro)  
> **Firmware:** MicroPython v1.28.0 Lolin-specific  
> **Output:** Google Sheets (via HTTPS webhook)
> **Power:** Deep sleep + dual wake (timer / reed GPIO) — see `POWER_MANAGEMENT.md`

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [End-to-End Flowchart](#2-end-to-end-flowchart)
3. [Module Architecture](#3-module-architecture)
4. [Data Flow](#4-data-flow)
5. [Boot Sequence](#5-boot-sequence)
6. [Sampling System](#6-sampling-system)
7. [BLE Auto-Discovery](#7-ble-auto-discovery)
8. [Trip Detection Logic](#8-trip-detection-logic)
9. [Upload Pipeline](#9-upload-pipeline)
10. [Power Management](#10-power-management)
11. [File Map](#11-file-map)

---

## 1. Project Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         XC90 OBD LOGGER                          │
│                                                                  │
│  ┌─────────────┐    BLE 5.0     ┌──────────┐    CAN Bus    ┌───┐ │
│  │  LOLIN S3    │◄─────────────►│ iCar Pro │◄────────────►│ECU│ │
│  │  (ESP32-S3)  │               │ BLE 4.0  │              └───┘ │
│  └──────┬───────┘               └──────────┘                    │
│         │                                                        │
│         │ WiFi 802.11n                                           │
│         ▼                                                        │
│  ┌─────────────┐     HTTPS POST     ┌──────────────┐            │
│  │  WiFi Router │──────────────────►│ Google Sheets │            │
│  └─────────────┘                    │ (Apps Script) │            │
│                                     └──────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

**Purpose:** Log 20+ OBD-II/Enhanced PIDs from the XC90's ECU continuously, buffer to flash, and auto-upload to Google Sheets when WiFi is available.

**Key design decisions:**
- **Async concurrency** — 3 `uasyncio` tasks run simultaneously (sampler + upload + connection watchdog)
- **Single sequential sampler** — Torque Pro method: one PID at a time, no collisions, no ELM327 mode corruption
- **RAM buffer** — 50 rows buffered before flash write (reduces flash wear)
- **Pre-start buffer** — Up to 12 engine-off rows kept in RAM, flushed on engine start (captures off→on transition)
- **Three-tier BLE discovery** — works with any ELM327 BLE adapter, not just iCar Pro
- **Deep sleep + dual wake** — Timer (RTC) or reed switch (GPIO) wake; saves 99%+ battery while parked
- **Offline-first** — logs locally even without WiFi; uploads next time you're home

---

## 2. End-to-End Flowchart

```
                                ┌─────────────────┐
                                │   POWER ON /     │
                                │   BOOT ESP32     │
                                └────────┬────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │  Detect Boot     │
                                │  Cause            │
                                │  (cold/timer/gpio)│
                                └────────┬────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │ timer        │ cold/gpio     │
                          ▼              │               │
                   ┌──────────────┐      │               │
                   │ Quick BLE    │      │               │
                   │ Scan (3s)    │      │               │
                   └──────┬───────┘      │               │
                          │              │               │
              iCar found? │              │               │
              ┌─────NO────┘              │               │
              │ YES                     │               │
              ▼                         ▼               ▼
       ┌──────────────┐          ┌─────────────────────────┐
       │ Deep Sleep   │          │  main.py:boot()         │
       │ (ESP resets) │          └───────────┬─────────────┘
       └──────────────┘                      │
                                  ┌──────────┼──────────┐
                                  ▼          ▼          ▼
                          ┌──────────┐ ┌──────────┐ ┌──────────┐
                          │Init Store│ │Init OBD  │ │Init WiFi │
                          │(logger)  │ │(obd)     │ │(uploader)│
                          └────┬─────┘ └────┬─────┘ └────┬─────┘
                               │            │            │
                               ▼            ▼            ▼
                          ┌──────────┐ ┌──────────┐ ┌──────────┐
                          │ /logs/   │ │ BLE Scan │ │Background│
                          │ CSV rot. │ │ & Connect│ │ Upload   │
                          └──────────┘ └────┬─────┘ └──────────┘
                                            │
                                 ┌──────────┘
                                 ▼
                          ┌──────────────┐
                          │ BLE Connect  │◄── RETRY FOREVER
                          │ (3 Tiers)    │
                          └──────┬───────┘
                                 │
                                 ▼
                ┌────────────────┴────────────────────┐
                │       LAUNCH 3 ASYNC TASKS          │
                │                                      │
                │  ┌──────────────────────────────┐   │
                │  │  Sequential Sampler          │   │
                │  │  (1 row/second)              │   │
                │  │  • Critical PIDs every cycle │   │
                │  │  • Standard PIDs every 2nd   │   │
                │  │  • Slow PIDs every 5th       │   │
                │  │  • Trip detection inline     │   │
                │  │  • Pre-start buffer (RAM)    │   │
                │  │  • Sleep trigger on idle     │   │
                │  └──────────────┬───────────────┘   │
                │                 │                    │
                │                 ▼                    │
                │  ┌──────────────────────────────┐   │
                │  │  SensorState (shared cache)  │   │
                │  │  Forward-filled values       │   │
                │  └──────────────┬───────────────┘   │
                │                 │                    │
                │                 ▼                    │
                │  ┌──────────────────────────────┐   │
                │  │  build_row → LogBuffer       │   │
                │  │  (50-row RAM → flash)        │   │
                │  └──────────────┬───────────────┘   │
                │                 │                    │
                │                 ▼                    │
                │  ┌──────────────────────────────┐   │
                │  │  /logs/xc90_NNN.csv          │   │
                │  └──────────────────────────────┘   │
                │                                      │
                │  ┌──────────┐  ┌──────────┐        │
                │  │ Upload   │  │Connection│        │
                │  │ Task     │  │ Watchdog │        │
                │  │ (5min)   │  │ (5s)     │        │
                │  └──────────┘  └──────────┘        │
                └─────────────────────────────────────┘
                                 │
                                 ▼
                          RUN FOREVER
                          (until power loss / Ctrl+C)
                                 │
                                 ▼
                          ┌──────────────┐
                          │ Flush Buffer │
                          │ Upload Last  │
                          │ Clean Exit   │
                          └──────────────┘
```

---

## 3. Module Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          main.py                                 │
│                    (Orchestrator / Entry Point)                   │
│                                                                  │
│  boot() → detect wake cause → quick scan (if timer) →            │
│           init all modules → BLE connect → 3 async tasks         │
│  main() → boot() → launch tasks → asyncio.gather()              │
└───┬──────┬──────┬────────┬──────────┬──────────┬───────────────┘
    │      │      │        │          │          │
    ▼      ▼      ▼        ▼          ▼          ▼
┌───────┐┌──────┐┌──────┐┌──────┐┌──────────┐┌──────────────┐
│config ││pids  ││decoder││logger││uploader  ││power_manager │
│.py    ││.py   ││.py   ││.py   ││.py       ││.py           │
│       ││      ││      ││      ││          ││              │
│WiFi   ││PID   ││Raw→Val││Trip  ││WiFi Mgr  ││Deep Sleep    │
│BLE    ││defs  ││derived││detect││HTTPS POST││Timer/GPIO    │
│sample ││tiers ││pids   ││CSV   ││cleanup   ││Wake Modes    │
│sleep  ││      ││      ││buf   ││health    ││RTC Memory    │
└───────┘└──────┘└──────┘└──────┘└──────────┘└──────────────┘
                                   │
                                   ▼
                              ┌──────────┐
                              │  obd.py  │
                              │          │
                              │BLE client│
                              │AT init   │
                              │PID query │
                              │quick_scan│
                              │3-tier    │
                              │discovery │
                              └──────────┘
```

### Module Responsibilities

| Module | Role | Key Classes/Functions |
|--------|------|----------------------|
| **`config.py`** | All configuration constants | WiFi, BLE, sampling rates, sleep/wake, storage limits |
| **`pids.py`** | PID definitions (22 PIDs in 3 tiers) | `PIDS_BY_TIER`, `ALL_PIDS` |
| **`decoder.py`** | Raw ELM327 → decoded value + derived PIDs | `decode()`, `calculate_derived()`, `clean_response()` |
| **`obd.py`** | BLE connection + ELM327 protocol + quick scan | `OBDClient` class: `connect()`, `query()`, `quick_scan()` |
| **`logger.py`** | Trip detection + CSV logging + pre-start buffer | `TripManager`, `LogBuffer`, `PreStartBuffer`, `build_row()` |
| **`uploader.py`** | WiFi + Google Sheets HTTPS upload | `WiFiManager`, `upload_pending()`, `_http_post_json()` |
| **`power_manager.py`** | Deep sleep + dual wake (timer / GPIO) | `PowerManager`, `detect_boot_cause()`, `boot_cause_label()` |
| **`main.py`** | Async orchestrator (3 concurrent tasks) | `boot()`, `main()`, `sampler_sequential()`, `SensorState` |

---

## 4. Data Flow

### 4.1 PID Query → CSV Row (per sample)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        SINGLE SAMPLE CYCLE                           │
│                                                                      │
│  1. sampler_task (tier)                                              │
│     │                                                                │
│     │  for pid_name, pid_def in PIDS_BY_TIER[tier]:                  │
│     │                                                                │
│     ▼                                                                │
│  2. obd.query(pid_name)                                              │
│     ├── _send_raw(cmd + "\r")     →  BLE write to iCar Pro          │
│     ├── _wait_response()          →  BLE notify with ">" prompt     │
│     └── decode(pid_name, cmd, raw)                                   │
│         │                                                            │
│         ├── clean_response()      →  strip ">", " ", \r\n           │
│         ├── detect_error()        →  check "NO DATA", "7F xx", etc  │
│         ├── validate_response()   →  check header matches cmd        │
│         ├── extract_bytes()       →  parse hex data bytes            │
│         ├── apply formula         →  e.g. ((A*256)+B)/4 for RPM     │
│         └── validate_range()      →  check min ≤ value ≤ max        │
│                                                                      │
│  3. sensor_state.update(pid_name, result)                            │
│     └── Stores latest value in shared dict (all tiers contribute)    │
│                                                                      │
│  4. build_row(trip_manager, sensor_state.get_all(), ...)             │
│     ├── classify_engine_state(coolant) → cold_start/warming/normal/hot │
│     ├── classify_drive_phase(rpm, throttle, speed) → idle/light/...  │
│     ├── calculate_derived()            → fuel_trim_sum, boost_delta  │
│     └── Assemble 31-column CSV row dict                              │
│                                                                      │
│  5. log_buffer.add(row)                                              │
│     └── Append to RAM buffer; flush to flash when ≥ 50 rows          │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Flash → Google Sheets (upload cycle)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        UPLOAD CYCLE (every 5 min)                    │
│                                                                      │
│  1. upload_task fires every 300s                                     │
│     │                                                                │
│     ▼                                                                │
│  2. upload_pending(wifi_manager, active_log_file)                    │
│     │                                                                │
│     ├── wifi_manager.connect()   →  join "Rogers 77" (10s timeout) │
│     ├── cleanup_old_uploads()    →  delete files > 3 days old       │
│     ├── check_storage_health()   →  warn if > 90% flash used        │
│     ├── _get_pending_files()     →  find CSV files not yet uploaded │
│     │                                                                │
│     └── for each pending file:                                       │
│         │                                                            │
│         ▼                                                            │
│  3. _upload_file(filepath)                                           │
│     ├── Read CSV header + data lines                                 │
│     ├── Batch in groups of 5 rows                                    │
│     │                                                                │
│     └── for each batch:                                              │
│         │                                                            │
│         ▼                                                            │
│  4. _http_post_json(SHEETS_WEBHOOK_URL, payload)                     │
│     ├── Raw socket connect to script.google.com:443                  │
│     ├── SSLContext TLS wrap (PROTOCOL_TLS_CLIENT)                    │
│     ├── POST with JSON body + headers                                │
│     ├── Follow up to 5 redirects (301/302 → GET, 307 → re-POST)     │
│     │                                                                │
│     └── Return (status_code, response_body)                         │
│                                                                      │
│  5. On success (200):                                                │
│     ├── _mark_uploaded(filepath)                                     │
│     └── File kept 3 days then auto-deleted                           │
│                                                                      │
│  6. On failure:                                                      │
│     └── File left for retry next upload cycle                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. Boot Sequence

```
main.py:main()
  │
  └─► main.py:boot()
        │
        ├── 1. init_storage()                  logger.py
        │     ├── Ensure /logs/ exists
        │     └── Pick log file (rotate if > 512KB)
        │
        ├── 2. check_storage_health()          uploader.py
        │     └── Print flash usage %
        │
        ├── 3. cleanup_old_uploads()           uploader.py
        │     └── Delete files uploaded > 3 days ago
        │
        ├── 4. Create instances:
        │     ├── OBDClient()                  obd.py
        │     │     └── BLE init, register IRQ handler
        │     ├── TripManager()                logger.py
        │     ├── LogBuffer(log_file)          logger.py
        │     ├── SensorState()                main.py
        │     └── WiFiManager()                uploader.py
        │
        ├── 5. Launch TWO parallel background tasks:
        │     │
        │     ├── _boot_upload()               ─► Upload previous trips immediately
        │     │     └── upload_pending(wifi_manager, ...)
        │     │
        │     └── _boot_ble()                  ─► Retry BLE connection forever
        │           │
        │           └── while True:
        │                 obd.connect()
        │                 ├── Tier 1: Scan BLE ads for OBD service UUIDs
        │                 ├── Tier 2: Try known MAC addresses
        │                 └── Tier 3: Connect-and-probe all nearby devices
        │                 sleep(3) if failed
        │
        ├── 6. Wait for BLE to connect (ble_connected.wait())
        │
        ├── 7. Wait for upload to finish (upload_done.wait())
        │     (WiFi radio safety — don't collide with BLE)
        │
        ├── 8. If first boot: run_pid_probe()  obd.py
        │     └── Test all enhanced PIDs against ECU
        │         Save results → /logs/pid_probe.json
        │
        └── 9. Return (obd, trip_manager, log_buffer, sensor_state, wifi_manager)

main.py:main() continues:
  │
  ├── Launch 7 concurrent async tasks
  │
  └── await asyncio.gather(*tasks)
        │
        └── RUN FOREVER until KeyboardInterrupt or exception
```

---

## 6. Sampling System

### 6.1 Single Sequential Sampler (Torque Pro Method)

```
┌─────────────────────────────────────────────────────────────────┐
│  CYCLE │ PIDs Queried                                           │
├────────┼────────────────────────────────────────────────────────┤
│  Every │ rpm, coolant_temp_c, boost_actual_kpa,                 │
│  cycle │ vehicle_speed_kph (4 critical PIDs)                    │
├────────┼────────────────────────────────────────────────────────┤
│  Every │ engine_load_pct, throttle_pos_pct, stft_pct,           │
│  2nd   │ ltft_pct, maf_g_s, intake_air_temp_c,                  │
│  cycle │ timing_advance_deg, fuel_system_status,                 │
│        │ o2_lambda, absolute_load_pct (8 standard PIDs)         │
├────────┼────────────────────────────────────────────────────────┤
│  Every │ oil_temp_c, battery_voltage_v, baro_pressure_kpa,      │
│  5th   │ fuel_pressure_kpa, ambient_air_temp_c,                 │
│  cycle │ engine_run_time_s, dtc_count, fuel_rate_l_h,           │
│        │ fuel_trim_sum*, iat_ambient_delta_c* (8+2 PIDs)        │
│        │                                                        │
│        │ * = derived (calculated, not OBD)                      │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Sampler Logic

```
sampler_sequential(obd, trip_manager, log_buffer, sensor_state,
                   pre_start_buffer, power_manager):
  │
  └── while True:
        │
        ├── IDLE MODE (trip NOT active):
        │     ├── Query critical PIDs every IDLE_POLL_INTERVAL (5s)
        │     ├── Build pre-start rows → PreStartBuffer (RAM only)
        │     ├── Run trip detection (check RPM > 100)
        │     │
        │     ├── Track engine-off time
        │     ├── After SLEEP_AFTER_IDLE_MS (30 min) of 0 RPM:
        │     │     └── power_manager.enter_sleep() → ESP resets
        │     │
        │     └── Trip detected? → continue to ACTIVE MODE
        │
        └── ACTIVE MODE (trip active):
              ├── First active cycle: flush PreStartBuffer
              │     └── Rows re-stamped with trip_id + sequence
              │
              ├── Query critical PIDs (every cycle, 1s)
              ├── Query standard PIDs (every 2nd cycle)
              ├── Query slow PIDs (every 5th cycle)
              │
              ├── trip_manager.update(rpm, speed)
              │
              ├── Build ONE dense row with SensorState.get_all()
              │     └── All columns forward-filled → AI-ready
              │
              └── log_buffer.add(row)
                    └── Flush to flash when BUFFER_SIZE reached
```

### 6.3 Pre-Start Buffer

```
ENGINE OFF (hours)                    ENGINE ON (drive)
┌──────────────────────────┐    ┌──────────────────────────────┐
│ Sample every 5s          │    │ Sample every 1s              │
│ Keep last 12 rows in RAM │    │ Write every row to flash     │
│ → PreStartBuffer         │    │                              │
│ → NO flash wear          │    │                              │
│         ↓                │    │                              │
│   [row -60s]             │    │                              │
│   [row -55s]    ← FLUSH →│    │ [row 0s] ← first engine-on   │
│   [row -50s]    at start │    │ [row 1s]                     │
│   ...                    │    │ [row 2s]                     │
│   [row -5s]              │    │ ...                          │
└──────────────────────────┘    └──────────────────────────────┘

Rows tagged engine_state = "pre_start" for easy AI filtering.
```

```
                    ┌─────────────────────┐
                    │    SensorState       │
                    │                     │
    critical ──────►│  rpm: 1726          │
    critical ──────►│  coolant_temp_c: 92 │
    critical ──────►│  boost_actual: 112  │
    critical ──────►│  speed: 87          │
    standard ──────►│  throttle_pos: 22.4 │
    standard ──────►│  stft_pct: -2.3     │
    standard ──────►│  ltft_pct: 3.1      │
    standard ──────►│  maf_g_s: 42.5      │
    standard ──────►│  timing_adv: 12.5   │
    ...              │  ...               │
    slow ──────────►│  oil_temp_c: 98     │
    slow ──────────►│  battery: 14.1      │
    slow ──────────►│  baro: 101          │
    slow ──────────►│  fuel_rate: 5.2     │
    ...              │  ...               │
    derived ───────►│  fuel_trim_sum: 0.8 │
    derived ───────►│  iat_ambient_delta:5│
                    │                     │
                    │  get_all() → dict   │──► build_row() includes ALL values
                    │  get("rpm") → 1726  │     in every row, even if some tiers
                    └─────────────────────┘     haven't sampled yet this cycle
```

**Key insight:** `sensor_state.get_all()` returns the latest value for *every* PID across *all* tiers. This means every CSV row has all 20+ columns populated with their most recent readings, not just the PIDs from the tier that triggered the row.

---

## 7. BLE Auto-Discovery

### 7.1 Three-Tier Strategy

```
obd.connect()
  │
  ├── Tier 1: SCAN ADS FOR OBD SERVICE UUIDs (fast, no connection)
  │     │
  │     ├── gap_scan(5s)
  │     ├── Parse AD types 0x02/0x03 (16-bit service UUID list)
  │     ├── Match against: 0xFFF0, 0xFFE0, 0x18F0
  │     │
  │     ├── Found candidates → try connecting strongest RSSI first
  │     │
  │     └── Connected? → DONE
  │
  ├── Tier 2: KNOWN MAC ADDRESSES (fast, specific)
  │     │
  │     ├── Iterate KNOWN_ICAR_PRO_MACS
  │     ├── gap_connect(addr_type=1, addr) for each
  │     │
  │     └── Connected? → DONE
  │
  └── Tier 3: CONNECT-AND-PROBE ALL DEVICES (slow, universal)
        │
        ├── gap_scan(8s) → all devices sorted by RSSI
        │
        ├── For each device (up to 8, strongest first):
        │     │
        │     ├── gap_connect (5s timeout)
        │     ├── Discover services → look for OBD UUID
        │     ├── Discover characteristics → look for write/notify handles
        │     ├── Enable notifications
        │     ├── Send ATZ\r
        │     ├── Check response for "ELM327" or "OK"
        │     │
        │     ├── OBD confirmed? → DONE (keep connection)
        │     │
        │     └── Not OBD? → gap_disconnect, try next
        │
        └── All exhausted? → FAIL
```

### 7.2 ELM327 UUID Compatibility

```
┌────────────────────┬──────────────────────┬──────────────────────┐
│ Adapter Type       │ Service UUID         │ Write Char UUID      │
├────────────────────┼──────────────────────┼──────────────────────┤
│ iCar Pro           │ 0x18F0              │ 0x2AF1               │
│ Standard ELM327    │ 0xFFF0              │ 0xFFF1               │
│ Some clones        │ 0xFFE0              │ 0xFFF1               │
└────────────────────┴──────────────────────┴──────────────────────┘
```

The IRQ handler matches all three patterns — iCar, standard, and substring matches (`'18f0'`, `'fff0'`, `'2af1'`, `'fff1'`).

---

## 8. Trip Detection Logic

```
TripManager.update(rpm, speed)  ← called by trip_monitor_task every 1s
  │
  ├── TRIP START
  │     Conditions: NOT trip_active AND rpm ≥ 100
  │     Action:
  │       ├── Generate trip_id: XC90_20240315_143022
  │       ├── Reset sequence counter → 1
  │       ├── Reset odometer → 0.0 km
  │       └── Set trip_active = True
  │
  ├── ODOMETER (every cycle when trip active)
  │     ├── elapsed_hours = (now - last_time) / 3600
  │     ├── session_odom += speed_kph × elapsed_hours
  │     └── Update last_time
  │
  └── TRIP END (with 10s debounce)
        │
        ├── rpm ≤ 0 detected:
        │     ├── First time? → record engine_off_at = now
        │     │                 print "Engine off detected, waiting 10s"
        │     │
        │     └── (now - engine_off_at) ≥ 10s? → TRIP END
        │           ├── Print trip summary (rows, distance)
        │           ├── trip_active = False
        │           └── Trip monitor triggers buffer flush
        │
        └── rpm > 0 while waiting:
              └── Cancel end detection (engine_off_at = None)
```

### 8.1 Engine State Classification

```
classify_engine_state(coolant_temp):
  │
  ├── coolant < 70°C    → cold_start
  ├── coolant 70–85°C   → warming
  ├── coolant 85–95°C   → normal
  └── coolant > 95°C    → hot
```

### 8.2 Drive Phase Classification

```
classify_drive_phase(rpm, throttle, speed):
  │
  ├── throttle < 5% AND speed > 20 kph  → decel
  ├── rpm < 900 AND speed == 0          → idle
  ├── throttle < 25%                    → light
  ├── throttle 25–60%                   → moderate
  └── throttle > 60%                    → hard
```

---

## 9. Upload Pipeline

### 9.1 Upload Trigger Points

```
┌──────────────────────────────────────────────────────────────┐
│ TRIGGER                  │ FREQUENCY     │ WHAT HAPPENS      │
├──────────────────────────┼───────────────┼───────────────────┤
│ Boot                     │ Every boot    │ Upload previous   │
│                          │               │ trip files        │
├──────────────────────────┼───────────────┼───────────────────┤
│ upload_task              │ Every 5 min   │ Check + upload all│
│ (background)             │               │ pending files     │
├──────────────────────────┼───────────────┼───────────────────┤
│ Trip end                 │ On trip end   │ Flush buffer to   │
│ (trip_monitor_task)      │               │ flash immediately │
├──────────────────────────┼───────────────┼───────────────────┤
│ Shutdown (Ctrl+C)        │ On exit       │ Flush + upload    │
│                          │               │ last buffer       │
└──────────────────────────┴───────────────┴───────────────────┘
```

### 9.2 Upload Tracker State Machine

```
                    ┌─────────────┐
                    │  CSV file   │
                    │  created    │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  PENDING    │  ← Not in uploaded.json
                    │  UPLOAD     │     Will be attempted next
                    └──────┬──────┘     upload cycle
                           │
                     upload succeeds
                     (HTTP 200)
                           │
                           ▼
                    ┌─────────────┐
                    │  UPLOADED   │  ← In uploaded.json
                    │  (kept 3d)  │     with timestamp
                    └──────┬──────┘
                           │
                     > 3 days since upload
                           │
                           ▼
                    ┌─────────────┐
                    │  DELETED    │  ← os.remove()
                    │  (freed)    │     removed from tracker
                    └─────────────┘
```

### 9.3 HTTPS POST (Raw Socket)

```
_http_post_json(url, body):
  │
  ├── Parse URL → host, path
  │
  ├── Build HTTP request:
  │     POST /macros/s/.../exec HTTP/1.1
  │     Host: script.google.com
  │     User-Agent: MicroPython/1.24
  │     Accept: application/json, */*
  │     Content-Type: application/json
  │     Content-Length: <N>
  │     Connection: close
  │     {JSON body}
  │
  ├── SSLContext(ssl.PROTOCOL_TLS_CLIENT)
  │     ctx.verify_mode = ssl.CERT_NONE
  │
  ├── socket.connect(host, 443)
  ├── ctx.wrap_socket(sock, server_hostname=host)
  ├── sock.write(request)
  ├── sock.read() until done or 8KB limit
  │
  ├── Parse status code from response headers
  │
  └── Redirect loop (up to 5 hops):
        │
        ├── 301/302 → GET (follow with new URL)
        ├── 307     → Re-POST (same body, new URL)
        └── Other   → Return (status, body)
```

---

## 10. Power Management

See the full guide: [`POWER_MANAGEMENT.md`](./POWER_MANAGEMENT.md)

### 10.1 Wake Modes

| Mode | Wake Source | Hardware | Parked Draw |
|------|------------|----------|-------------|
| `"timer"` | RTC alarm every 5 min | None | ~15.5 mAh/day |
| `"reed"` | GPIO ext0 (door reed switch) | $1 reed + magnet | ~0.98 mAh/day |
| `"both"` | GPIO primary + timer fallback | $1 reed + magnet | ~1.0 mAh/day |
| `"none"` | Never sleeps | None | ~1355 mAh/day |

### 10.2 Sleep Entry

```
sampler_sequential idle loop:
  │
  ├── Track engine_off_at timestamp
  ├── After SLEEP_AFTER_IDLE_MS (30 min) of 0 RPM:
  │     └── power_manager.enter_sleep()
  │           ├── Write RTC magic (XC91=timer, XC92=GPIO)
  │           ├── Configure GPIO wake (if reed/both mode)
  │           └── machine.deepsleep(ms)
  │                 ESP32-S3 resets
  │
  └── Next boot: detect_boot_cause() → cold/timer/gpio
```

### 10.3 Boot Cause Detection

```
detect_boot_cause():
  │
  ├── machine.reset_cause() == PWRON_RESET → "cold"
  │
  └── machine.reset_cause() == DEEPSLEEP_RESET:
        ├── RTC memory == XC91 → "timer"
        ├── RTC memory == XC92 → "gpio"
        └── Unknown → "cold"
```

### 10.4 Boot Decision Flow

| Boot Cause | Action |
|-----------|--------|
| `"cold"` | Full boot (power-on) |
| `"gpio"` | Full boot (door opened) |
| `"timer"` | Quick BLE scan → iCar found? → full boot : re-sleep |

### 10.5 Reed Switch Circuit

```
   3.3V ── 100kΩ ──┬── GPIO4 (RTC wake)
                    │
              Reed Switch (NO)
                    │
                   GND

Door CLOSED: magnet holds reed closed → GPIO = LOW
Door OPENS:  reed opens → pull-up pulls HIGH → ESP32 WAKES
```

---

## 11. File Map

```
xc90_logger/
│
├── config.py            All constants (WiFi, BLE, sampling, sleep/wake, storage)
├── decoder.py           ELM327 raw response → decoded value + derived PIDs
├── logger.py            Trip detection, CSV row building, flash buffer, PreStartBuffer
├── main.py              Orchestrator — boot sequence, sequential sampler, 3 async tasks
├── obd.py               BLE client — 3-tier discovery, AT init, PID query, quick_scan
├── pids.py              PID definitions (22 Mode 01 PIDs across 3 tiers + 2 derived)
├── power_manager.py     Deep sleep & dual wake (timer / reed GPIO)
├── uploader.py          WiFi manager, HTTPS POST, cleanup, health checks
│
├── deploy/
│   └── code.gs          Google Apps Script — webhook receiver
│
├── tests/
│   ├── __init__.py
│   ├── mocks.py         Test mocks for MicroPython modules
│   ├── test_decoder.py  Decoder unit tests
│   ├── test_logger.py   Logger unit tests
│   └── test_uploader.py Uploader unit tests
│
├── tools/
│   ├── fix_com_port.py           COM port diagnostic
│   └── troubleshoot_connection.py Connection debugger
│
├── docs/                # Documentation
│   ├── ARCHITECTURE.md
│   ├── POWER_MANAGEMENT.md
│   ├── SCHEMA.md
│   ├── DEPLOYMENT_GUIDE.md
│   └── ...
│
├── hw/                  Hardware reference
│   └── ESP32-S3-WROOM-1_REFERENCE.md
│
└── xc90_001.csv          Sample captured log data
```

### Dependency Graph

```
                    ┌──────────┐
                    │ config   │◄──── All modules import from here
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┬──────────────┐
          │              │              │              │
    ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼──────────┐
    │ pids.py   │  │ logger.py │  │uploader.py│  │power_manager.py│
    └─────┬─────┘  └─────┬─────┘  └───────────┘  └────────────────┘
          │              │
    ┌─────▼─────┐        │
    │ decoder.py│        │
    └─────┬─────┘        │
          │              │
    ┌─────▼──────────────▼──┐
    │       obd.py          │
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │       main.py         │  ← Orchestrates everything
    └───────────────────────┘
```

---

## Quick Reference: Key Numbers

| Parameter | Value | Config Key |
|-----------|-------|-----------|
| Critical sample rate | 1s | `ROW_INTERVAL_MS` |
| Standard sample rate | 2s (every 2nd cycle) | (derived) |
| Slow sample rate | 5s (every 5th cycle) | (derived) |
| RAM buffer flush | 50 rows | `BUFFER_SIZE` |
| Max log file size | 512 KB | `MAX_LOG_SIZE_KB` |
| Trip start threshold | RPM ≥ 100 | `TRIP_START_RPM` |
| Trip end debounce | 10 seconds | `TRIP_END_DELAY` |
| Idle poll interval | 5 seconds | `IDLE_POLL_INTERVAL` |
| Pre-start buffer rows | 12 (~60s) | `PRE_START_BUFFER_ROWS` |
| Sleep after idle | 30 minutes | `SLEEP_AFTER_IDLE_MS` |
| Wake interval (timer) | 5 minutes | `SLEEP_WAKE_INTERVAL_MS` |
| BLE scan on wake | 3 seconds | `WAKE_BLE_SCAN_TIMEOUT` |
| Upload interval | 5 minutes | (hardcoded in upload_task) |
| Uploaded file retention | 3 days | `MAX_UPLOADED_AGE_DAYS` |
| BLE connect timeout | 10 seconds | `BLE_CONNECT_TIMEOUT` |
| WiFi timeout | 10 seconds | `WIFI_TIMEOUT` |
| Total PIDs | 24 (2 derived) | `ALL_PIDS` |
| Concurrent async tasks | 3 | `asyncio.gather()` |
| Wake modes | timer / reed / both / none | `WAKE_MODE` |

---

*Generated for XC90 OBD Logger Firmware v0.1.0 — ESP32-S3 / MicroPython v1.28.0*

**See also:** [POWER_MANAGEMENT.md](./POWER_MANAGEMENT.md) — Deep sleep & wake strategy details
[SCHEMA.md](./SCHEMA.md) — CSV column schema evolution guide

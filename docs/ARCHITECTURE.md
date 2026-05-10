# XC90 OBD Logger — Architecture & Logic Reference

> **Target:** 2018 Volvo XC90 T6 Inscription (B4204T23, SPA Platform)  
> **Hardware:** ESP32-S3-WROOM-1 (LOLIN S3 Pro)  
> **Firmware:** MicroPython v1.28.0 Lolin-specific  
> **Output:** Google Sheets (via HTTPS webhook)

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
10. [File Map](#10-file-map)

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
- **Async concurrency** — 7 `uasyncio` tasks run simultaneously (4 samplers + trip monitor + upload + connection watchdog)
- **RAM buffer** — 50 rows buffered before flash write (reduces flash wear)
- **Three-tier BLE discovery** — works with any ELM327 BLE adapter, not just iCar Pro
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
                                │  main.py:boot() │
                                └────────┬────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
            ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
            │ Init Storage │    │ Init OBD      │    │ Init WiFi    │
            │ (logger.py)  │    │ (obd.py)      │    │ (uploader.py)│
            └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
                   │                   │                   │
                   ▼                   │                   ▼
            ┌──────────────┐           │           ┌──────────────┐
            │ /logs/ dir   │           │           │ Background   │
            │ CSV rotation │           │           │ Upload Task  │
            └──────────────┘           │           │ (prev trips) │
                                       │           └──────────────┘
                                       │
                    ┌──────────────────┘
                    ▼
            ┌──────────────────┐
            │ BLE Connection   │◄──── RETRY FOREVER (3s interval)
            │ 3-Tier Discovery │
            └────────┬─────────┘
                     │
                     ▼ (connected)
            ┌──────────────────┐
            │ PID Probe        │  First boot only — test enhanced PIDs
            │ (engine running) │  Saves → /logs/pid_probe.json
            └────────┬─────────┘
                     │
                     ▼
     ┌───────────────┴───────────────────────────────────────┐
     │              LAUNCH 7 ASYNC TASKS                      │
     │                                                        │
     │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
     │  │ Critical │ │ Standard │ │  Slow    │ │ Enhanced │ │
     │  │ Sampler  │ │ Sampler  │ │ Sampler  │ │ Sampler  │ │
     │  │  (1s)    │ │  (2s)    │ │  (5s)    │ │ (10s)    │ │
     │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
     │       │            │            │            │        │
     │       └────────────┴────────────┴────────────┘        │
     │                         │                              │
     │                         ▼                              │
     │              ┌──────────────────┐                      │
     │              │  SensorState     │   Shared dict        │
     │              │  (shared cache)  │   of latest values   │
     │              └────────┬─────────┘                      │
     │                       │                                │
     │         ┌─────────────┼─────────────┐                  │
     │         ▼             ▼             ▼                  │
     │  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
     │  │ Trip     │  │ build_row│  │ Dispatch │             │
     │  │ Monitor  │  │ (CSV row)│  │ to Tier  │             │
     │  │ (1s)     │  └────┬─────┘  └──────────┘             │
     │  └────┬─────┘       │                                   │
     │       │             ▼                                   │
     │       │      ┌────────────┐                             │
     │       │      │ LogBuffer  │  RAM buffer (50 rows)       │
     │       │      │ .add(row)  │                             │
     │       │      └─────┬──────┘                             │
     │       │            │ (flush when full)                  │
     │       │            ▼                                    │
     │       │      ┌────────────┐                             │
     │       │      │ /logs/     │  CSV on flash               │
     │       │      │ xc90_NNN   │                             │
     │       │      └─────┬──────┘                             │
     │       │            │                                    │
     │       ▼            │                                    │
     │  ┌──────────┐      │                                    │
     │  │ Trip End │      │                                    │
     │  │ Flush    │──────┘                                    │
     │  └──────────┘                                           │
     │                                                         │
     │  ┌──────────┐  ┌──────────┐                             │
     │  │ Upload   │  │Connection│                             │
     │  │ Task     │  │ Watchdog │                             │
     │  │ (5min)   │  │ (5s)     │                             │
     │  └──────────┘  └──────────┘                             │
     │                                                         │
     └─────────────────────────────────────────────────────────┘
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
│  boot() → init all modules → BLE connect → PID probe → tasks    │
│  main() → boot() → launch 7 async tasks → asyncio.gather()      │
└───────┬──────┬────────┬──────────┬──────────┬───────────────────┘
        │      │        │          │          │
        ▼      ▼        ▼          ▼          ▼
┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│config │ │ pids  │ │decoder │ │logger  │ │uploader  │
│.py    │ │.py    │ │.py     │ │.py     │ │.py       │
│       │ │       │ │        │ │        │ │          │
│WiFi   │ │PID    │ │Raw→Val │ │Trip    │ │WiFi Mgr  │
│BLE    │ │defs   │ │pipeline│ │detect  │ │HTTPS POST│
│sample │ │tiers  │ │        │ │CSV row │ │cleanup   │
│rates  │ │       │ │        │ │buffer  │ │health    │
└───────┘ └───────┘ └────────┘ └────────┘ └──────────┘
                                       │
                                       ▼
                                  ┌──────────┐
                                  │  obd.py  │
                                  │          │
                                  │BLE client│
                                  │AT init   │
                                  │PID query │
                                  │3-tier    │
                                  │discovery │
                                  └──────────┘
```

### Module Responsibilities

| Module | Role | Key Classes/Functions |
|--------|------|----------------------|
| **`config.py`** | All configuration constants | WiFi, BLE, sampling rates, storage limits |
| **`pids.py`** | PID definitions (20 PIDs in 4 tiers) | `CRITICAL_PIDS`, `STANDARD_PIDS`, `SLOW_PIDS`, `ENHANCED_PIDS`, `PIDS_BY_TIER` |
| **`decoder.py`** | Raw ELM327 → decoded value pipeline | `decode()`, `clean_response()`, `extract_bytes()`, `validate_range()` |
| **`obd.py`** | BLE connection + ELM327 protocol | `OBDClient` class: `connect()`, `query()`, `_scan_for_obd_by_service()` |
| **`logger.py`** | Trip detection + CSV logging | `TripManager`, `LogBuffer`, `build_row()`, `classify_engine_state()` |
| **`uploader.py`** | WiFi + Google Sheets HTTPS upload | `WiFiManager`, `upload_pending()`, `_http_post_json()` |
| **`main.py`** | Async orchestrator | `boot()`, `main()`, `sampler_task()`, 7 concurrent `uasyncio` tasks |

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

### 6.1 Four Tiers

```
┌─────────────────────────────────────────────────────────────────┐
│  TIER         │ INTERVAL │ PIDs                                │
├───────────────┼──────────┼─────────────────────────────────────┤
│  critical     │   1s     │ rpm, coolant_temp_c, boost_actual,  │
│               │          │ vehicle_speed_kph                    │
├───────────────┼──────────┼─────────────────────────────────────┤
│  standard     │   2s     │ engine_load_pct, throttle_pos_pct,  │
│               │          │ stft_pct, ltft_pct, maf_g_s,        │
│               │          │ intake_air_temp_c                    │
├───────────────┼──────────┼─────────────────────────────────────┤
│  slow         │   5s     │ oil_temp_c, battery_voltage_v,      │
│               │          │ baro_pressure_kpa, fuel_trim_sum*   │
├───────────────┼──────────┼─────────────────────────────────────┤
│  enhanced     │  10s     │ boost_target_kpa, boost_delta_kpa*, │
│               │          │ turbo_inlet_pres, oil_pressure_kpa  │
│               │          │                                     │
│               │          │ * = derived (calculated, not OBD)   │
└───────────────┴──────────┴─────────────────────────────────────┘
```

### 6.2 Sampler Task Logic

```
sampler_task(obd, trip_manager, log_buffer, sensor_state, tier):
  │
  ├── Get PIDs and interval for this tier
  │
  └── while True:
        │
        ├── If not trip_active AND tier != "critical":
        │     sleep(IDLE_POLL_INTERVAL)  ← 5s poll when engine off
        │     continue
        │
        ├── If not obd.is_connected():
        │     sleep(1)
        │     continue
        │
        ├── for each pid_name, pid_def in tier's PIDs:
        │     │
        │     ├── Skip derived PIDs (cmd is None)
        │     │
        │     ├── result = obd.query(pid_name)
        │     │     │
        │     │     └── Switch enhanced/standard CAN mode as needed
        │     │
        │     ├── sensor_state.update(pid_name, result)
        │     │
        │     ├── row = build_row(
        │     │       trip_manager,
        │     │       sensor_state.get_all(),  ← ALL tiers' latest values
        │     │       tier, pid_def["cmd"],
        │     │       result["raw"], result["status"]
        │     │     )
        │     │
        │     └── log_buffer.add(row)
        │
        └── sleep(interval)
```

### 6.3 SensorState — Shared Value Cache

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
    ...              │  ...               │
    slow ──────────►│  oil_temp_c: 98     │
    slow ──────────►│  battery: 14.1      │
    slow ──────────►│  baro: 101          │
    ...              │  ...               │
    enhanced ──────►│  boost_target: 120  │
    enhanced ──────►│  turbo_inlet: 100   │
    enhanced ──────►│  oil_pressure: 340  │
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

## 10. File Map

```
xc90_logger/
│
├── main.py              Orchestrator — boot sequence, 7 async tasks
├── config.py            All constants (WiFi, BLE, sampling, storage)
├── pids.py              PID definitions (20 PIDs across 4 tiers)
├── decoder.py           ELM327 raw response → decoded value pipeline
├── obd.py               BLE client — 3-tier discovery, AT init, PID query
├── logger.py            Trip detection, CSV row building, flash buffer
├── uploader.py          WiFi manager, HTTPS POST, cleanup, health checks
│
├── code.gs              Google Apps Script — webhook receiver
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
├── ESP32-S3-WROOM-1_REFERENCE.md  Hardware reference (pin map, power, BLE specs)
├── ARCHITECTURE.md                ← THIS FILE
├── DEPLOYMENT_GUIDE.md            Step-by-step flashing + deploy
├── QUICK_START.md                 Fast deploy for LOLIN Pro
├── WEBHOOK_SETUP.md               Google Sheets Apps Script setup
├── PID_VALIDATION_GUIDE.md        How to validate enhanced PIDs
├── FIRST_TEST.md                  First test instructions
│
├── diagram.json          Wokwi simulator diagram
├── wokwi.toml            Wokwi config
├── wokwi_test.py         Simulator test script
│
└── xc90_001.csv          Sample captured log data
```

### Dependency Graph

```
                    ┌──────────┐
                    │ config   │◄──── All modules import from here
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
    │ pids.py   │  │ logger.py │  │uploader.py│
    └─────┬─────┘  └─────┬─────┘  └───────────┘
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
| Critical sample rate | 1s | `SAMPLE_RATE_CRITICAL` |
| Standard sample rate | 2s | `SAMPLE_RATE_STANDARD` |
| Slow sample rate | 5s | `SAMPLE_RATE_SLOW` |
| Enhanced sample rate | 10s | `SAMPLE_RATE_ENHANCED` |
| RAM buffer flush | 50 rows | `BUFFER_SIZE` |
| Max log file size | 512 KB | `MAX_LOG_SIZE_KB` |
| Trip start threshold | RPM ≥ 100 | `TRIP_START_RPM` |
| Trip end debounce | 10 seconds | `TRIP_END_DELAY` |
| Upload interval | 5 minutes | `UPLOAD_INTERVAL` |
| Uploaded file retention | 3 days | `MAX_UPLOADED_AGE_DAYS` |
| BLE connect timeout | 10 seconds | `BLE_CONNECT_TIMEOUT` |
| BLE probe per device | 5 seconds | `BLE_PROBE_PER_DEVICE_TIMEOUT` |
| WiFi timeout | 10 seconds | `WIFI_TIMEOUT` |
| HTTPS redirect limit | 5 hops | `MAX_REDIRECTS` |
| Total PIDs | 20 (4 derived) | `ALL_PIDS` |
| Concurrent async tasks | 7 | `asyncio.gather()` |

---

*Generated for XC90 OBD Logger Firmware v0.1.0 — ESP32-S3 / MicroPython v1.28.0*

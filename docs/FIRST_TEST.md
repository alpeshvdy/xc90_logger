# ============================================================
# FIRST TEST — Stationary Engine Test (No Driving)
# XC90 T6 — Engine Start, Idle, Throttle Blips
# ============================================================

---

## Objective

Validate that the ESP32 logger:
- Connects to iCar Pro BLE adapter
- Detects trip start/end from RPM
- Queries all 3 tiers via sequential sampler
- Writes valid CSV rows to flash
- Survives the full session without crashing

**No driving required.** Engine on, throttle in Park/Neutral only.

---

## Step 0 — Before You Go to the Car

### On Your PC

```
# 1. Verify mpremote works
mpremote --version

# 2. List connected devices (plug in LOLIN Pro)
mpremote connect auto

# 3. Copymp boot_test.py and run it
mpremote cp boot_test.py :
mpremote run boot_test.py

# Expected: "All checks passed! Ready to deploy."
```

### In config.py (on device)

```python
WIFI_SSID = "Rogers 77"                        # ✓ Your WiFi
WIFI_PASSWORD = "House@77"                     # ✓ Your password  
SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycb..."   # ✓ Your webhook
ICAR_DEVICE_NAME_IOS = "IOS-VLink"             # ✓ iCar Pro name
ICAR_DEVICE_NAME_ANDROID = "ANDROID-VLink"     # ✓ iCar Pro name
```

### Hardware Checklist

```
☐ iCar Pro plugged into OBD-II port (under dash, driver side)
☐ iCar Pro LED is blinking (means it's advertising BLE)
☐ LOLIN Pro connected to USB power (laptop or power bank)
☐ Laptop ready with mpremote terminal open
☐ Car in Park, parking brake ON
☐ Bonnet open optional (lets you hear engine state)
☐ Phone timer ready (for timing throttle holds)
```

---

## Step 1 — Deploy All Files to Device

```bash
# From your project directory, copy every .py file
mpremote cp main.py :
mpremote cp config.py :
mpremote cp pids.py :
mpremote cp decoder.py :
mpremote cp logger.py :
mpremote cp obd.py :
mpremote cp uploader.py :

# Verify all 7 files are on device
mpremote ls

# Expected output:
#   main.py
#   config.py
#   pids.py
#   decoder.py
#   logger.py
#   obd.py
#   uploader.py
```

---

## Step 2 — Key On, Engine OFF

**Turn key to position II** (ignition ON, dashboard lights on, engine NOT running). This powers up the OBD-II port and lets us test that the ECU responds even with engine off.

```bash
# Start the logger
mpremote run main.py
```

**Expected console output (key on, engine off):**

```
========================================
 XC90 OBD Logger
 Firmware v0.1.0
========================================

[boot] Initialising storage...
[logger] Log file: /logs/xc90_001.csv
[storage] XX.X% used (XXXXKB free)
[boot] Connecting to iCar Pro...
[obd] Scanning for iCar Pro...
[obd] Found: ANDROID-VLink RSSI:-XX
[obd] Connecting...
[obd] Connected handle:X
[obd] Service found: X-X
[obd] Write:X Notify:X
[obd] Notifications enabled
[obd] Running AT init sequence...
[obd] ATZ → ELM327 v1.5
[obd] ATE0 → OK
[obd] ATL0 → OK
[obd] ATS0 → OK
[obd] ATH0 → OK
[obd] ATSP0 → OK
[obd] ATAT1 → OK
[obd] ATST32 → OK
[obd] AT init complete
[obd] Ready for OBD queries
[boot] Checking for pending uploads...
[uploader] No WiFi — skipping upload
[boot] Boot complete

[sampler] Sequential sampler started — 1 row/1s
[sampler] Critical: 4 PIDs every cycle
[sampler] Standard: 10 PIDs every 2nd cycle
[sampler] Slow: 8 PIDs every 5th cycle
[upload] Task started
[conn] Monitor started
[main] 3 tasks running
```

### ⚠️ Critical Check #1 — Trip Detection

With engine OFF, RPM should be 0:

```
Expected: Trip stays IDLE (no "Trip started" message)
```

If you see `[logger] Trip started: XC90_...` with engine off → `TRIP_START_RPM` may be too low or RPM sensor is reading noise. **Note this.**

---

## Step 3 — Start the Engine

**Start the engine.** Let it idle. Watch the console.

### Expected: Trip Detection (within 1-2 seconds)

```
[logger] Trip started: XC90_20260507_183045
```

If this does NOT appear within 3 seconds of engine start, note it — the `TRIP_START_RPM` threshold (100 RPM) may need adjusting.

### Expected: Sampler Output (within 10 seconds)

```
[sampler] Sequential sampler started — 1 row/1s
```

Rows will be written to CSV with all forward-filled columns. Standard PIDs fill in on even cycles, slow PIDs on every 5th cycle.

---

## Step 4 — Cold Idle (2 Minutes)

Let the engine idle for 2 minutes. **Just watch.** Don't touch the throttle.

**Record these values from the console:**

| PID | Expected Range (Cold Idle) | Your Value | OK? |
|-----|---------------------------|------------|-----|
| RPM | 700–1200 | ______ | ☐ |
| Coolant Temp | 15–40 °C (cold start) | ______ | ☐ |
| Boost Actual (MAP) | 90–105 kPa | ______ | ☐ |
| Vehicle Speed | 0 kph | ______ | ☐ |
| Engine Load | 15–35% | ______ | ☐ |
| Throttle Position | 10–20% (idle) | ______ | ☐ |
| STFT | -5 to +5% | ______ | ☐ |
| LTFT | -10 to +10% | ______ | ☐ |
| MAF | 2–8 g/s | ______ | ☐ |
| Intake Air Temp | 15–40 °C | ______ | ☐ |
| Oil Temp | 15–40 °C (cold) | ______ | ☐ |
| Battery Voltage | 13.5–14.5V | ______ | ☐ |
| Baro Pressure | 95–105 kPa | ______ | ☐ |

**Red flags during idle:**
- RPM jumping by >100 between readings → BLE interference
- Coolant temp = exactly 0 or -40 → PID not responding
- Any PID = "NO DATA" repeatedly → PID not supported
- Battery voltage < 12.0V → alternator issue or reading wrong PID

---

## Step 5 — Throttle Blips (10 Minutes)

Now the real test. **Stay in Park.** Blip the throttle and hold at specific RPMs.

### Blip Sequence

| # | Action | Hold Time | Target RPM |
|---|--------|-----------|------------|
| 1 | Idle baseline | 30 sec | ~800 |
| 2 | Gentle blip → hold | 10 sec | ~1500 |
| 3 | Back to idle | 30 sec | ~800 |
| 4 | Medium blip → hold | 10 sec | ~2500 |
| 5 | Back to idle | 30 sec | ~800 |
| 6 | Harder blip → hold | 5 sec | ~3500 |
| 7 | Back to idle | 30 sec | ~800 |
| 8 | Smooth ramp up → down | 15 sec | 800→3500→800 |
| 9 | Idle cooldown | 60 sec | ~800 |

Use your phone timer. Call out each step so you can match it to CSV rows later.

### For Each Blip — Record Console Output

Focus on these PIDs during throttle:

| Blip | RPM | Boost Actual | Throttle % | MAF | STFT |
|------|-----|-------------|------------|-----|------|
| Idle baseline | ______ | ______ | ______ | ______ | ______ |
| ~1500 RPM | ______ | ______ | ______ | ______ | ______ |
| Back to idle | ______ | ______ | ______ | ______ | ______ |
| ~2500 RPM | ______ | ______ | ______ | ______ | ______ |
| Back to idle | ______ | ______ | ______ | ______ | ______ |
| ~3500 RPM | ______ | ______ | ______ | ______ | ______ |
| Back to idle | ______ | ______ | ______ | ______ | ______ |
| Ramp 800→3500 | ______ | ______ | ______ | ______ | ______ |

### Plausibility Checks During Throttle

```
☐ RPM rises when you press throttle
☐ RPM falls when you release throttle
☐ Throttle position rises with your foot
☐ Engine load rises with RPM
☐ MAF (airflow) rises with RPM
☐ Boost actual (MAP) may dip slightly then rise
☐ Vehicle speed stays at 0 (you're in Park!)
☐ Coolant temp slowly rises over the 10 minutes
```

---

## Step 6 — Engine Off

Turn the engine off (key to position I or 0).

### Expected: Trip End Detection

After `TRIP_END_DELAY` seconds (default: 10 seconds of RPM=0):

```
[logger] Engine off detected, waiting 10s
[logger] Trip ended: XC90_20260507_183045 | XX rows | X.X km
[trip] Flushing buffer on trip end
[logger] Flushed XX rows → /logs/xc90_001.csv
```

### ⚠️ Critical Check #2 — Trip End

If you do NOT see "Trip ended" within 15 seconds of engine off:
→ `TRIP_END_RPM` or `TRIP_END_DELAY` may need tuning.

---

## Step 7 — Retrieve the CSV Log

After the test, copy the CSV file from the device:

```bash
mpremote cp /logs/xc90_001.csv .
```

Open it in Excel / Google Sheets / VS Code.

### CSV Validation Checklist

```
☐ File has a header row (37 columns)
☐ At least 600+ data rows (10 minutes × 1 row/sec)
☐ Column "trip_id" is the same throughout
☐ Column "trip_sequence" counts up 1,2,3... without gaps
☐ "rpm" column:
    - Starts at 0 (before engine start)
    - Jumps to ~800 when engine starts
    - Rises to ~1500, ~2500, ~3500 at your blip times
    - Returns to ~800 between blips
    - Drops to 0 after engine off
☐ "vehicle_speed_kph" = 0 for ALL rows (stationary test)
☐ "engine_state" transitions: cold_start → warming → normal
☐ "drive_phase" is mostly "idle" (you're in Park)
☐ "coolant_temp_c" rises slowly throughout the test
☐ "throttle_pos_pct" correlates with your blips
☐ All standard PIDs have values (not empty); slow PIDs fill in every 5th row
☐ No obviously impossible values (negative RPM, speed>0, etc.)
```

---

## Step 8 — Test WiFi Upload (Optional, If Near Your WiFi)

After the trip ends, the upload task runs every 5 minutes. Or you can trigger manually:

```python
# In REPL, after the test:
import uploader
from uploader import WiFiManager
wifi = WiFiManager()
uploader.upload_pending(wifi, "/logs/xc90_001.csv")
```

If WiFi connects, you should see:
```
[wifi] Connected — IP: 192.168.X.X
[uploader] Uploading /logs/xc90_001.csv...
[uploader] ✓ /logs/xc90_001.csv — XXX rows uploaded
```

Then check your Google Sheet for data.

---

## Pass/Fail Criteria

### ✅ PASS — All of these must be true

```
☐ Logger boots without Python traceback
☐ iCar Pro found and connected within 30 seconds
☐ AT init sequence completes (all 8 commands respond)
☐ "Trip started" appears within 3 seconds of engine start
☐ RPM values are plausible (0→~800→blips→0)
☐ All PIDs return values (not "NO DATA") when applicable
☐ "Trip ended" appears within 15 seconds of engine off
☐ CSV file is written to /logs/ with header + 37 data columns
☐ CSV contains at least 600 rows (10 min × 1 row/sec)
☐ Logger doesn't crash or freeze during 10+ minute test
```

### ⚠️ PARTIAL PASS — Note these but can deploy

```
☐ WiFi upload skipped (no WiFi at test location — expected)
☐ Buffer didn't fill to BUFFER_SIZE (test too short — normal)
☐ Some slow PIDs only populated every 5th row (expected — forward-filling)
```

### ❌ FAIL — Must fix before driving test

```
☐ Logger crashes with Python traceback
☐ iCar Pro never found (check BLE auto-discovery settings in config.py)
☐ AT init fails (check iCar Pro firmware version)
☐ Trip never starts (TRIP_START_RPM too high?)
☐ Trip never ends (TRIP_END_DELAY too long?)
☐ RPM = 0 or -40 even with engine running (PID 010C not responding)
☐ CSV file empty or missing (/logs directory not created)
☐ "NO DATA" on ALL PIDs (adapter connected but not communicating with ECU)
```

---

## Quick Troubleshooting

| Symptom | Check |
|---------|-------|
| "iCar Pro not found" | Is iCar Pro plugged in? LED blinking? |
| "Connection timed out" | iCar Pro too far from ESP32? Try closer. |
| "ATZ → NO DATA" | iCar Pro needs power cycle. Unplug/replug. |
| All PIDs "NO DATA" | Engine running? Key at position II? |
| RPM reads 0 when engine on | Wrong protocol? Check ATSP0 result. |
| Trip doesn't start | TRIP_START_RPM may need lowering (try 50). |

---

## Post-Test — Before You Drive

1. **Review CSV** — every column should have data where expected
2. **Check forward-filling** — slow PIDs appear every 5th row, standard PIDs every 2nd row
3. **Commit the CSV** to your repo as a baseline reference
4. **Review `docs/SCHEMA.md`** to understand all 37 columns

---

**Total test time: ~15 minutes**

Print this and take it to the car. ✅

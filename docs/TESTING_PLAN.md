# XC90 Logger — Power Management Testing Plan

## Branch: `power-management`

Tests are **step-by-step**, require **no tools**, and give **yes/no answers** you can run in your car tonight.

---

## Equipment Needed

| Item | Purpose | Cost |
|------|---------|------|
| LOLIN S3 (ESP32-S3) with MicroPython flashed | Device under test | — |
| iCar Pro OBD2 adapter | BLE OBD source | — |
| OBD-II Y-splitter cable | Powers both devices from one port | $8 |
| 12V→5V buck converter (Mini360 or similar) | Steps down for ESP32 | $1 |
| 2× 100kΩ resistors | Reed switch pull-up circuit | $0.10 |
| Reed switch (NC or NO, normally open preferred) | Door-open wake trigger | $2 |
| Small magnet | Door-trigger magnet | $1 |
| Multimeter | Verify voltage levels | — |
| Jumper wires / alligator clips | Temporary connections | — |

---

## Phase 0 — Baseline Verification (Before Any Sleep Code)

### T0.1: Fresh Deploy — Confirm Always-On Works

**Purpose:** Establish a known-good state before touching sleep logic.

```
1. Set config.py: WAKE_MODE = 'none'
2. Deploy all files to ESP32
3. Park car, turn engine off, lock doors
4. Wait 35 minutes (iCar Pro auto-sleeps)
5. Come back, open door (do NOT start engine)
6. Check: Does ESP32 connect to iCar Pro?
   YES → Expected (idle mode active, polling every 5s)
   NO  → Problem — not a sleep issue, a base connectivity issue
7. Start engine
8. Check: Does trip detection work? (RPM > 100 → trip starts)
9. Check: Does data appear in Google Sheets?
```

**Pass criteria:** All three checks YES.

---

### T0.2: Verify iCar Pro Auto-Sleep

**Purpose:** Confirm your iCar Pro actually sleeps, which is the foundation of the timer-wake strategy.

```
1. Park car overnight (or 1+ hour)
2. Walk to car with key fob LEFT AT HOME
3. Stand 5m from car, phone Bluetooth scanning
4. Do you see 'IOS-VLINK' or 'ANDROID-VLINK'?
   YES → iCar Pro does NOT auto-sleep — timer wake strategy won't help
   NO  → Good — iCar Pro sleeps when car is off

5. Now walk to driver door and pull handle (key still home)
6. Scan Bluetooth again immediately
7. Do you see the iCar Pro now?
   YES → iCar Pro wakes on door open (CAN bus activity)
   NO  → Wait 30 sec and scan again
```

**Pass criteria:** Steps 3=NO, 6=YES (confirms auto-sleep works).

---

## Phase 1 — Timer Wake Mode (`WAKE_MODE = 'timer'`)
*Zero hardware — tests the BLE scan detection logic*

### T1.1: Deploy Sleep Code

```
1. Set config.py: WAKE_MODE = 'timer'
2. Deploy all files: main.py, config.py, power_manager.py, obd.py
3. Do a hard reset (press EN button on ESP32)
4. Connect to REPL: mpremote repl
5. Watch boot output for wake cause
```

**Expected output:**
```
[boot] Cold boot — full init
[obd] Scanning for iCar Pro...
...
[sampler:critical] Started
```

### T1.2: Confirm Deep Sleep After 30 Min Idle

**Purpose:** Verify the ESP32 actually enters deep sleep after 30 minutes of engine-off.

```
1. With ESP32 running and connected to iCar Pro (idle mode)
2. Turn engine OFF
3. Watch REPL — ESP32 should continue polling for ~30 min
4. After 30 min: ESP32 should print [pm] Entering deep sleep
5. Confirm ESP32 is no longer visible on BLE or REPL
6. Measure: Does board go warm or cold? (deep sleep = cool)
```

**Pass criteria:** `[pm] Entering deep sleep` appears in REPL after ~30 min.

### T1.3: Timer Wake — iCar Pro Still Asleep

**Purpose:** Confirm that when the timer fires but the car is still off (iCar Pro sleeping), ESP32 goes back to sleep without wasting power.

```
1. From T1.2 — ESP32 is in deep sleep
2. Wait 5 minutes (first timer wake)
3. ESP32 should wake, do a 3-second BLE scan
4. iCar Pro NOT found → ESP32 immediately goes back to sleep
5. Confirm: Did you see [obd] quick_scan: no device found, sleeping?
6. Check car battery — should not be drained

Optional: Add a print in should_full_boot() to log each wake cycle:
   print(f'[pm] Wake cause: timer, BLE found: {found}')
```

**Pass criteria:** `[pm] Wake cause: timer, BLE found: False` → back to sleep within ~5 seconds.

### T1.4: Timer Wake — iCar Pro Awake (Engine Started)

**Purpose:** Confirm that when the timer fires and the car is on (iCar Pro advertising), ESP32 does a full boot and starts logging.

```
1. From T1.3 — ESP32 is back in deep sleep after failed BLE scan
2. Start the car engine (do NOT open door — don't use reed)
3. Wait 5–6 minutes (next timer wake cycle)
4. ESP32 wakes, does 3-second BLE scan
5. iCar Pro found → full boot begins
6. Confirm: Does ESP32 connect to iCar Pro and start sampling?
7. Does a new trip start? Does data flow to Google Sheets?
```

**Pass criteria:** Full boot initiates, connection established, data logged.

### T1.5: Data Gap Measurement — Timer Wake Only

**Purpose:** Quantify how much data is missed between sleep cycles.

```
1. Park car, turn off engine
2. Wait 35 minutes for iCar Pro to sleep
3. Start engine
4. Immediately start driving (don't wait for ESP32 to wake)
5. Drive for 2 minutes, then stop
6. Check Google Sheets — what was the first logged timestamp?
7. Compare to when you started driving

Expected gap: 0–5 minutes (worst case = engine started right before sleep cycle)
```

**Pass criteria:** Gap ≤ 5 min (expected), ideally < 2 min.

---

## Phase 2 — Reed Switch Mode (`WAKE_MODE = 'reed'`)
*Requires reed switch hardware installation*

### T2.1: Wire the Reed Switch

**Circuit:**
```
LOLIN S3 GPIO4 (RTC pin)────┬── 100kΩ ────── 3.3V
                            │
                       REED SWITCH (NO)
                            │
                           GND

Door CLOSED → switch closed → GPIO4 pulled LOW (0V) → no wake
Door OPENS  → switch opens → GPIO4 pulled HIGH (3.3V via 100kΩ) → WAKE
```

**Assembly steps:**
1. Connect GPIO4 to one leg of 100kΩ resistor
2. Connect other leg of 100kΩ to 3.3V (or use 3.3V rail from LOLIN S3)
3. Connect reed switch between GPIO4 and GND
4. Tape magnet to door frame (driver side B-pillar or door jam)
5. Tape reed switch on door, aligned with magnet — gap < 5mm when closed

**Verification:**
```
ESP32 OFF (no power)
Multimeter on GPIO4 pin → GND

Door CLOSED: Multimeter reads ~0V (reed closed, 100kΩ shorted to GND)
Door OPENS:  Multimeter reads ~3.3V (reed open, 100kΩ pulls HIGH)
```

### T2.2: Deploy and Test Reed Wake

```
1. Set config.py: WAKE_MODE = 'reed'
2. Hard reset ESP32 (press EN)
3. Lock car, close all doors — ESP32 should go to deep sleep immediately
4. Wait 2 min (confirm no timer wakes — reed mode = no timer)
5. Open driver door — reed switch opens → GPIO4 HIGH → ESP32 WAKES
6. Check REPL: [boot] GPIO wake → [obd] Scanning...
7. iCar Pro connects, idle mode starts
8. Do NOT start engine yet — stay in idle mode
9. Close door (reed closes) → after 30 min idle → ESP32 sleeps again
10. Open door again → wake again ✓
```

**Pass criteria:** Door open → instant wake (< 100ms). Door closed 30 min → deep sleep.

### T2.3: Door Open → Cranking Data Capture

**Purpose:** The key test — does pre-start buffer capture door-open-to-engine-start?

```
1. ESP32 is deep sleep (reed mode), car parked, all doors closed
2. Walk to car, open driver door → ESP32 wakes
3. ESP32 connects to iCar Pro, starts idle sampling (5s polling)
4. Pre-start buffer starts collecting rows (engine state = pre_start)
5. Sit in car, close door, press START
6. Engine cranks (RPM > 100) → trip starts
7. Pre-start buffer flushes to CSV → all pre-engine rows captured
8. Drive for 5 minutes
9. Check Google Sheets — do you have rows with engine_state = 'pre_start'?
10. What is the timestamp of the first row vs when you opened the door?
```

**Pass criteria:** Rows with `engine_state = 'pre_start'` appear in Google Sheets, timestamp starts from door-open moment (not engine-start).

---

## Phase 3 — Both Mode (`WAKE_MODE = 'both'`)
*Tests GPIO as primary + timer as fallback*

### T3.1: Timer Fallback When Door Stays Closed

```
1. Set config.py: WAKE_MODE = 'both'
2. ESP32 deep sleeps (door closed)
3. Do NOT open any door
4. Wait 5 minutes → timer fires → ESP32 wakes
5. [pm] Wake cause: timer (not gpio) → quick BLE scan
6. iCar Pro sleeping (car still off) → back to sleep
7. Confirm: [pm] Entering deep sleep within ~5 seconds of wake
8. Repeat for 30 min / 1 hour / 2 hours — confirm no battery drain
```

**Pass criteria:** ESP32 returns to deep sleep within ~5 sec on every timer wake.

### T3.2: Door Open Overrides Timer

```
1. ESP32 is deep sleep (both mode)
2. Wait 3 minutes into a 5-min timer cycle
3. Open door → GPIO wake fires immediately
4. ESP32 boots fully (not just BLE scan) — door was opened = reason to wake
5. Confirm: Trip starts immediately when engine starts
6. Pre-start buffer has rows from door-open moment
```

**Pass criteria:** Door open → instant full boot, pre-start data captured.

---

## Phase 4 — Power Measurement

### T4.1: Measure Deep Sleep Current (No Meter Tools Needed)

**Estimate via observation:**
```
1. Fully charge car battery (or measure resting voltage first: should be ~12.7V)
2. Install ESP32 + iCar Pro in car, configure WAKE_MODE = 'reed'
3. Close all doors, lock car, leave parked
4. After 24 hours: measure car battery voltage
   12.7V → Car battery healthy, ESP32 not draining it
   12.4V → Minor drain (~1Ah used), acceptable
   <12.0V → Problem — ESP32 or iCar Pro is drawing too much

Compare with WAKE_MODE = 'none' (always-on) for 24h:
   Expected drop: ~1.4V (always-on = 55mA × 24h = 1320mAh from 70Ah battery)
```

**Pass criteria (reed mode, 24h parked):** Battery voltage ≥ 12.4V.

### T4.2: Measure Active Current (Driving)

**Estimate via voltage delta:**
```
1. Before drive: measure car battery voltage at rest (key off, 5 min wait)
2. Start engine, drive for 1 hour with ESP32 logging
3. After drive: measure battery voltage immediately (engine still running)
   >14V (alternator charging) → normal
4. Turn engine off, wait 30 sec, measure again
   12.7–12.9V → healthy
   <12.5V → something drawing excess power

Run same test with WAKE_MODE = 'none' vs 'reed' and compare.
```

---

## Phase 5 — Long-Term Stability

### T5.1: Multi-Day Parking Test

```
1. Park car Friday evening
2. Set WAKE_MODE = 'reed'
3. Monitor battery voltage each morning (Mon/Wed/Fri)
4. After 2 weeks: battery still starts car?
   YES → Power management working
   NO  → Investigate (iCar Pro not sleeping? Reed stuck?)

Log entry: Record date, time, battery voltage AM each day.
```

### T5.2: Trip Reliability Test

Over 2–4 weeks of daily driving:

```
1. Every trip: note timestamp of first row in Google Sheets
2. Compare against trip start (when you started the engine)
3. Track any gaps > 5 min (timer mode) or > 0 sec (reed mode)
4. After 20+ trips: all should have pre_start rows with reed mode
5. Any trips missing pre_start data = bug to investigate
```

**Pass criteria:** ≥ 95% of trips have complete pre-start buffer data.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| ESP32 won't enter deep sleep | `WAKE_MODE = 'none'` or idle detection not working | Check config, check RPM value being returned |
| Timer never fires | `SLEEP_WAKE_INTERVAL_MS` not set, or deep sleep blocked | Verify config values, check no exception in enter_sleep() |
| Door open doesn't wake ESP32 | Reed switch not aligned, wire disconnected, GPIO wrong | Multimeter check GPIO4 voltage when door open/closed |
| ESP32 wakes but doesn't connect | iCar Pro not awake yet, BLE scan timeout too short | Increase `WAKE_BLE_SCAN_TIMEOUT`, check iCar Pro is powered |
| Pre-start buffer empty | Buffer not flushed before trip started | Check `PreStartBuffer.flush_to()` was called in `sampler_sequential` |
| Always-on drain (no sleep) | `machine.deepsleep()` not being called | Add print before/after deep sleep to confirm execution |
| Battery drain too fast | iCar Pro not auto-sleeping | Test iCar Pro auto-sleep (T0.2), consider OBD switch cable |

---

## Test Log Sheet

Copy this to your phone/notes for field recording:

```
Date       | Mode    | Test # | Car State          | ESP32 State    | Result  | Notes
-----------|---------|--------|--------------------|----------------|---------|------
           |         |        |                    |                |         |
           |         |        |                    |                |         |
           |         |        |                    |                |         |
           |         |        |                    |                |         |
           |         |        |                    |                |         |
```

---

## Test Sequence Summary

| Order | Test | Duration | Hardware Needed |
|-------|------|----------|-----------------|
| T0.1  | Baseline always-on | 40 min | None |
| T0.2  | iCar Pro auto-sleep verify | 1 hour | Phone |
| T1.1  | Deploy sleep code | 10 min | None |
| T1.2  | Deep sleep after 30 min idle | 35 min | None |
| T1.3  | Timer wake — car still off | 6 min | None |
| T1.4  | Timer wake — car on | 6 min | None |
| T1.5  | Data gap measurement | 10 min | None |
| T2.1  | Wire reed switch | 20 min | Reed + magnet + resistors |
| T2.2  | Reed wake test | 10 min | Reed wired |
| T2.3  | Door open → cranking capture | 15 min | Reed wired |
| T3.1  | Both mode — timer fallback | 6 min | Reed wired |
| T3.2  | Both mode — door override | 5 min | Reed wired |
| T4.1  | Park drain (24h) | 24 hours | Reed wired |
| T5.1  | Multi-day parking | 2 weeks | Reed wired |
| T5.2  | Trip reliability | 2–4 weeks | Reed wired |

**Total: ~3 hours active testing + 2-week observation period**

---

*Generated for: `power-management` branch — XC90 Logger Firmware v0.1.0*
# Power Management

> **XC90 OBD Logger — Deep Sleep & Wake Strategies**  
> Target: 2018 Volvo XC90 T6 (B4204T23) | Board: LOLIN S3 (ESP32-S3)  
> iCar Pro BLE: Auto-sleeps after ~30 min of no CAN activity ✅ Confirmed

---

## Overview

The ESP32 draws ~80mA while active (sampling) and ~55mA while idle (BLE connected, polling every 5s). Parked overnight, this would drain a typical car battery in about 28 days. Deep sleep drops this to **under 1-16 mAh/day** — effectively negligible.

### Power States

| State | Current @ 3.3V | When |
|-------|-----------------|------|
| **Active sampling** | ~80 mA | Engine running, querying PIDs every 1s |
| **Active idle** | ~55 mA | Engine off, polling critical PIDs every 5s, building pre-start rows |
| **Deep sleep + timer** | ~8 μA + 15.3 mAh burst/day | RTC timer wakes every 5 min, 2.7s BLE scan each |
| **Deep sleep + reed** | ~41 μA | Reed switch + pull-up resistor, no timer |

---

## Wake Strategies

### Comparison

| | Timer Wake | Reed Switch (GPIO) | Both |
|---|---|---|---|
| **Wake mechanism** | RTC alarm every 5 min | GPIO ext0 on door open | GPIO primary + timer fallback |
| **ESP32 parked draw** | ~15.5 mAh/day | **~0.98 mAh/day** | ~1.0 mAh/day |
| **Wasted wake cycles** | 98.6% (284/288 find iCar asleep) | **0%** | <1% |
| **Data missed on start** | Up to 5 min | **0 sec** | **0 sec** (GPIO wins) |
| **Wake latency** | 0–300 seconds | **<50 ms** | **<50 ms** |
| **Hardware needed** | None | $1 reed switch + magnet | $1 reed switch + magnet |
| **Install difficulty** | None (code only) | Tape magnet to door | Tape magnet to door |
| **Car battery lasts¹** | ~258 days | **~289 days** | ~285 days |

¹ 70Ah AGM battery, 50% usable (35Ah), driving surplus ignored

### Timer Wake Flow

```
Deep Sleep (8 μA)
      │
      ▼  (every 5 min)
RTC Timer Fires → ESP32 boots → Quick BLE scan (3s)
      │                              │
      │                    iCar found? ──YES──→ Full boot → Sample
      │                         │
      │                        NO
      │                         │
      └── Back to deep sleep ←──┘
```

- **288 wakes per 24h**, each ~2.7 sec @ 70mA average = 15.3 mAh/day
- **98.6% of wakes** find the iCar Pro sleeping → wasted energy
- Simple, zero hardware, works today

### Reed Switch Wake Flow

```
Deep Sleep (41 μA)
      │
      ▼  (only when door opens)
Door opens → Reed switch opens → GPIO pulled HIGH → ESP32 boots
      │
Full boot → BLE connect → Start sampling (pre-start buffer already in RAM)
```

- **4–8 wakes per day** (one per trip, plus door opens)
- Every wake is meaningful
- Captures engine-off → on transition with zero latency

### Both Mode Flow

```
Deep Sleep (41 μA)
      │
      ├── Door opens → GPIO wake → Full boot (instant)
      │
      └── Timer fires → Quick BLE scan → iCar found? → Full boot (fallback)
```

- Reed switch is primary (instant door-open detection)
- Timer is backup (catches engine start if reed fails or misaligns)
- Timer finds iCar only if reed already woke the ESP32, so negligible extra drain

---

## Configuration

All settings in `config.py`:

```python
# Wake mode: "timer", "reed", "both", or "none"
WAKE_MODE = "timer"

# Engine must be off this long before sleep
SLEEP_AFTER_IDLE_MS = 30 * 60 * 1000  # 30 minutes

# Timer interval (only used in "timer" and "both" modes)
SLEEP_WAKE_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes

# BLE scan timeout on timer wake
WAKE_BLE_SCAN_TIMEOUT = 3  # seconds

# Reed switch GPIO pin (RTC-capable, must be 0-21)
REED_GPIO_PIN = 4

# Wake level: 1 = HIGH (door open, switch opens, pull-up pulls high)
REED_WAKE_LEVEL = 1
```

### Changing Modes

| From → To | What to change | Hardware |
|-----------|---------------|----------|
| `timer` → `reed` | Set `WAKE_MODE = "reed"`, wire reed switch | Add $1 reed + magnet |
| `timer` → `both` | Set `WAKE_MODE = "both"`, wire reed switch | Add $1 reed + magnet |
| `timer` → `none` | Set `WAKE_MODE = "none"` | None (not recommended) |
| `reed` → `timer` | Set `WAKE_MODE = "timer"` | Remove reed switch |

No code changes needed — just update `WAKE_MODE` in `config.py`.

---

## Reed Switch Hardware

### Parts ($1 total)

| Part | Example | Cost |
|------|---------|------|
| Reed switch (NO) | MC-38 wired door sensor | $0.50 |
| Magnet | Small neodymium, or the magnet that comes with MC-38 | $0.50 |
| 100kΩ resistor | 1/4W through-hole | $0.01 |
| Wire | 2-conductor, ~50cm | Scrap |

### Circuit

```
ESP32 3.3V ── 100kΩ ──┬── GPIO4 (RTC wake pin)
                       │
                 Reed Switch (NO)
                       │
                      GND

Door CLOSED: magnet holds reed contacts closed → GPIO = LOW
Door OPENS:  reed contacts open → pull-up resistor pulls GPIO HIGH → ESP32 WAKES
```

### Installation (Non-invasive)

1. **Tape the magnet** to the driver door (interior edge, near the B-pillar)
2. **Tape the reed switch** to the B-pillar, aligned with the magnet when door is closed
3. **Run the wire** along the door sill trim to the ESP32
4. **Plug into GPIO4 and 3.3V/GND**

Zero damage to the car. Removable in 30 seconds. The MC-38 is a premade door sensor with screw mounting holes and a 50cm cable — just tape it.

### GPIO Pin Constraints

The wake pin **must be RTC-capable**. On ESP32-S3, pins 0-21 are RTC-safe. GPIO4 is used by default. Other options if GPIO4 is occupied: GPIO5, GPIO12, GPIO13, GPIO14.

---

## iCar Pro Auto-Sleep Behavior

| State | iCar Pro | BLE Advertise | ESP32 Can Detect |
|-------|----------|---------------|------------------|
| Engine running | Active | ✅ Yes | ✅ |
| Engine off < 30 min | Active | ✅ Yes | ✅ |
| Engine off > 30 min | **Asleep** | ❌ No | ❌ (this is the signal) |
| Door opened (car wakes) | **Wakes** | ✅ Yes | ✅ (via reed switch) |

**Key insight:** When the iCar Pro is sleeping (no BLE advertisement), the car is definitely off and parked. When it starts advertising again, the car was just woken up. The timer wake exploits this: BLE scan finds nothing → go back to sleep. BLE scan finds iCar → full boot.

---

## Battery Life Calculation

### Daily Energy Budget (Typical Driver: 1.5 hrs/day)

| Mode | Idle (22.5h) | Active (1.5h) | Daily Total |
|------|-------------|---------------|-------------|
| Always-on | 1,238 mAh | 120 mAh | **1,358 mAh** |
| Timer wake | 15.5 mAh | 120 mAh | **135.5 mAh** |
| Reed switch | 0.98 mAh | 120 mAh | **121 mAh** |
| Both | 1.0 mAh | 120 mAh | **121 mAh** |

### Car Battery Longevity (70Ah AGM, 50% usable = 35Ah)

| Mode | Days Until Dead | Practical Limit |
|------|----------------|-----------------|
| Always-on | **28 days** | Park 1 month → dead battery |
| Timer wake | **258 days** | Park 8 months → dead battery |
| Reed switch | **289 days** | Park 9.5 months → dead battery |
| Both | **285 days** | Park 9.3 months → dead battery |

**Note:** The car's own electronics (alarm, clock, keyless receiver) draw ~20-30 mA when parked. This dominates over the ESP32's deep sleep draw. The real battery life limit is the car itself, not the ESP32.

---

## Sleep Entry Logic

The sampler tracks engine-off time in the idle loop:

```
sampler_sequential idle mode:
  │
  ├── RPM == 0 AND trip NOT active:
  │     ├── Record engine_off_at timestamp (if first 0-RPM sample)
  │     ├── Continue polling critical PIDs every 5s
  │     ├── Build pre-start rows in RAM buffer
  │     │
  │     ├── (time.time() - engine_off_at) ≥ SLEEP_AFTER_IDLE_MS?
  │     │     │
  │     │     YES → Flush LogBuffer → enter_sleep() → machine.deepsleep()
  │     │            ESP32 resets. Next boot: detect_boot_cause() = "timer"
  │     │
  │     └── Continue
  │
  └── RPM > 0:
        └── Reset engine_off_at = None (engine restarted)
```

Sleep never triggers while the engine is running. The `SLEEP_AFTER_IDLE_MS` default of 30 minutes prevents sleep during short stops (groceries, coffee).

---

## Boot Sequence with Wake Detection

```
Power-on / Wake
      │
      ▼
detect_boot_cause()
      │
      ├── "cold"  (PWRON_RESET) ──→ Full boot
      │
      ├── "gpio"  (RTC_MAGIC_GPIO) ──→ Door opened → Full boot
      │
      └── "timer" (RTC_MAGIC_TIMER) ──→ Quick BLE scan (3s)
            │                              │
            │                    iCar Pro found? ──YES──→ Full boot
            │                         │
            │                        NO
            │                         │
            └── enter_sleep("timer") ←┘
                 ESP32 resets → wakes again in 5 min
```

The boot cause is stored in RTC memory (survives deep sleep). On wake, `detect_boot_cause()` reads the magic bytes to determine whether the wake was from timer or GPIO.

---

## Module Reference

| File | Role |
|------|------|
| `config.py` | `WAKE_MODE`, `SLEEP_AFTER_IDLE_MS`, `SLEEP_WAKE_INTERVAL_MS`, `REED_GPIO_PIN`, `REED_WAKE_LEVEL` |
| `power_manager.py` | `PowerManager`, `detect_boot_cause()`, `boot_cause_label()` |
| `obd.py` | `OBDClient.quick_scan()` — fast BLE presence check |
| `main.py` | `boot()` — early wake check, `sampler_sequential()` — sleep trigger |

---

## Quick Decision Guide

| Your Situation | Recommended `WAKE_MODE` |
|----------------|------------------------|
| I want to test now, no hardware | `"timer"` |
| I have a reed switch wired up | `"reed"` |
| I want the best of both | `"both"` |
| My car is on a battery tender | `"none"` (always-on) |
| I park for weeks at a time | `"reed"` + unplug iCar Pro |

---

## Appendix: OBD Power Wiring — ESP32 + iCar Pro from One Port

The OBD-II port provides constant 12V on pin 16 (unswitched) and ground on pins 4/5. Both devices can be powered from the same port using a Y-splitter.

### Option A — Y-Splitter with Inline Buck Converter ($12 total)

```
OBD Port (female)
  │
  ├─── OBD Y-Splitter (1 male → 2 female) ──┬─── iCar Pro (12V direct)
  │                                          │
  │                                          └─── 12V → Buck Converter (12V→5V)
  │                                                      │
  │                                                      └─── LOLIN S3 USB-C (5V)
```

| Part | Cost | Notes |
|------|------|-------|
| OBD-II Y-splitter cable | $8 | 1 male to 2 female, 10-15cm long |
| Mini360 buck converter (12V→5V, 2A) | $1 | Screw terminal preferred |
| USB-A to USB-C cable (old charger cable) | $0 | Cut and splice, or use USB-C breakout |

**Assembly:**
1. Plug Y-splitter into OBD port
2. iCar Pro plugs into one female port (it handles its own 12V regulation)
3. Cut a USB-A cable, strip the 5V/GND wires, connect to buck converter output
4. Or use a USB-C breakout board soldered to buck converter output
5. Add a **1A inline fuse** on the 12V line going to the buck converter for safety

### Option B — Bare Pigtail + Two Buck Converters ($10 total)

```
OBD Port pin 16 (12V) ──┬── Buck #1 → iCar Pro
                        │
                        └── Buck #2 → LOLIN S3 (5V USB-C)

OBD Port pin 4/5 (GND) ──┴── Both buck converters GND
```

| Part | Cost | Notes |
|------|------|-------|
| OBD-II pigtail (bare wires) | $3 | Amazon: "OBD2 connector pigtail 16-pin" |
| 2× Mini360 buck converter | $2 | One per device |
| USB-C breakout or cut USB cable | $0 | For ESP32 |
| 2× 1A fuse (inline blade holder) | $1 | One per circuit |

**Wire colors (standard OBD-II pigtail):**
| Pin | Function | Typical Wire Color |
|-----|----------|-------------------|
| 16 | 12V constant (unswitched) | Red or Yellow |
| 4 | Chassis ground | Black |
| 5 | Signal ground | Black/White |

### Option C — Hardwire Kit (with Low-Voltage Cutoff) ($15)

For permanent installation with battery protection:

```
Fuse box (ACC or always-on fuse) ──→ Hardwire kit ──→ 12V→5V buck ──→ ESP32
                                         │
                                         └── Low-voltage cutoff (cuts at 11.8V)
```

Hardwire kits (e.g., for dash cams) include an inline fuse and a low-voltage cutoff that protects your car battery from draining below ~12V. Connect the ESP32 to the kit's USB output.

### GPIO Pin Reference for Reed Switch (LOLIN S3)

| LOLIN S3 Pin | GPIO | Notes |
|-------------|------|-------|
| GPIO4 | RTC (wake-capable) | Used for reed switch ext0 wake |
| 3.3V | — | Pull-up resistor supply |
| GND | — | Reed switch ground |
| EN | — | Press to hard reset (useful during testing) |

### Full Wiring Diagram — Reed Switch + ESP32 + iCar Pro

```
                    OBD PORT (under dash)
                    ╔══════════════════════╗
                 16 │  ●  12V always-on    │  ← Red/Yellow wire
                  4 │  ●  GND (chassis)    │  ← Black wire
                  5 │  ●  GND (signal)     │  ← Black/White wire
                    ╚══════════════════════╝
                          │
          ┌───────────────┴───────────────┐
          │                               │
    ┌─────▼─────┐                  ┌─────▼─────┐
    │  iCar Pro │                  │ Y-Splitter│
    │  (BLE)    │                  │           │
    └─────┬─────┘                  │     ┌─────┼─────┐
          │                         │     │          │
          │                         │  Port A    Port B
    No power regulation            │  (iCar)  (Buck→ESP32)
    inside iCar Pro (12V in)       │           │
          │                         │      ┌────▼────┐
          │                         │      │ Buck    │
          │                         │      │ 12V→5V  │
          │                         │      └───┬────┘
          │                         │          │ 5V
          │                         │     ┌────▼────┐
          │                         │     │ LOLIN S3│
          │                         │     └────┬────┘
          │                         │          │
          │                         │     ┌────▼────┐
          │                         │     │ GPIO4   │
          │                         │     │   │     │
          │                         │     │ 100kΩ   │
          │                         │     │   │     │
          │                         │     │ REED    │
          │                         │     │ SWITCH  │
          │                         │     │   │     │
          │                         │     └────┼────┘
          │                         │          │ GND
          │                         └──────────┘
          │
      iCar Pro BLE
      ↕ (connected to ESP32 via BLE)

    REED SWITCH INSTALLATION:
    ┌─────────────────────────────────────────┐
    │  DOOR FRAME (B-pillar)                   │
    │                                          │
    │  ┌─────────┐        ┌─────────┐         │
    │  │ REED    │  ←5mm→ │ MAGNET  │         │
    │  │ SWITCH  │        │ (tape)  │         │
    │  │ (tape)  │        │         │         │
    │  └────┬────┘        └─────────┘         │
    │       │                                  │
    │    GPIO4 (via 100kΩ)                    │
    │       │                                  │
    │    GND                                   │
    │                                          │
    │  DOOR (opens → magnet moves away →       │
    │       reed opens → GPIO4 HIGH → WAKE)   │
    └─────────────────────────────────────────┘
```

### Parts List Summary

| Component | Quantity | Cost |
|-----------|----------|------|
| OBD-II Y-splitter cable | 1 | $8 |
| Mini360 buck converter (12V→5V) | 1–2 | $1–2 |
| 100kΩ resistor (0805 or through-hole) | 1 | $0.05 |
| Reed switch (NO, e.g. SW-420 or equivalent) | 1 | $2 |
| Small neodymium magnet (钕磁铁) | 1 | $1 |
| 1A inline blade fuse + holder | 1 | $1 |
| USB-C breakout or cut USB cable | 1 | $0 |
| **Total** | | **~$13–15** |

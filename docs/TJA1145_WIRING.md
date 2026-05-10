# TJA1145 Wiring Guide

> **ESP32-S3 + Buck Converter + TJA1145 CAN Transceiver Wiring**
> Target: 2018 Volvo XC90 T6 | Board: LOLIN S3 (ESP32-S3)
> Purpose: Hard-off power architecture — ESP32 is truly off when car is parked

---

## What This Guide Covers

This guide is for the `WAKE_MODE = 'tja1145'` configuration. It shows every wire connection from the OBD-II port to:
- **TJA1145** CAN FD transceiver (monitors CAN bus, controls power)
- **Buck Converter** 12V → 5V (feeds ESP32 via TJA1145 INH control)
- **LOLIN S3** ESP32-S3 board (receives power and TWAI CAN from TJA1145)

---

## Power Architecture

```
OBD Pin 16 (12V always) ──┬── Buck Converter INPUT
                           │         │
                           │    Buck EN ←── TJA1145 INH (open-drain)
                           │         │
                           │    Buck 5V OUTPUT ──→ ESP32 5V pin
                           │         │
                           └─────────┼───────────┬─── TJA1145 VCC
                                     │           │
                                     │           └──→ TJA1145 VIO (3.3V from ESP32)
                                     │
OBD Pin 6 (CAN_H) ────────────────────┴───────────→ TJA1145 CANH
OBD Pin 14 (CAN_L) ─────────────────────────────────→ TJA1145 CANL

TJA1145 INH (open-drain) ──────────→ Buck EN pin
                                        │
                                    10kΩ pull-down to GND (prevents accidental enable on startup)

TJA1145 TXD ─────────────────────────→ ESP32 GPIO1 (TWAI TX)
TJA1145 RXD ─────────────────────────→ ESP32 GPIO2 (TWAI RX)

TJA1145 STBY ────────────────────────→ ESP32 GPIO6 (drive HIGH = normal mode)
TJA1145 INT ─────────────────────────→ ESP32 GPIO5 (optional, diagnostics only)

OBD Pin 4 (GND) ──────────────────────→ Buck GND + TJA1145 GND + ESP32 GND
```

---

## Parts Needed

| Part | Qty | Notes |
|------|-----|-------|
| TJA1145TK/3 | 1 | HVSON-14 package, 3.3V VIO — NXP automotive CAN FD transceiver |
| Mini360 buck converter (12V→5V, 2A) | 1 | Must have EN pin exposed — verify before buying |
| 10kΩ resistor (0805 SMD or through-hole) | 1 | Pull-down on buck EN |
| 100nF capacitor (0805) | 2 | Required — one on TJA1145 VCC pin (datasheet spec), one optional on CAN_H |
| OBD-II Y-splitter cable (1M→2F) | 1 | Powers both iCar Pro and TJA1145 from one port |
| Jumper wire / DuPont wire | ~20 | 22AWG for power, 26AWG for signal |
| 1A inline blade fuse + holder | 1 | On 12V input to buck converter |
| Heat-shrink tubing | 1 | For wire joints |
| Soldering iron + rosin-core solder | — | Required for SMD and wire connections |

---

## Step 1 — TJA1145 Pin Map

The TJA1145TK/3 has 14 pins in HVSON-14 package. View from top (mark dot = pin 1):

```
    ┌─────────────────────────┐
 1  │ ●                       │ 14
    │                         │
 2  │                         │ 13
    │   TJA1145TK/3           │
 3  │   (top view, dot = pin1)│ 12
    │                         │
 4  │                         │ 11
    │                         │
 5  │                         │ 10
    │                         │
 6  │                         │  9
    └─────────────────────────┘

Pin 1: SPLIT   Pin 8: TXD
Pin 2: CANH    Pin 9: RXD
Pin 3: CANL    Pin 10: VCC
Pin 4: GND     Pin 11: INH
Pin 5: STBY    Pin 12: VIO
Pin 6: INT     Pin 13: VBAT
Pin 7: NC      Pin 14: WAKE
```

**Pin functions:**

| Pin | Name | Function | Connect To |
|-----|------|----------|------------|
| 1 | SPLIT | CAN bus split termination | Leave floating or 10kΩ to GND |
| 2 | CANH | CAN high | OBD pin 6 (CAN_H) |
| 3 | CANL | CAN low | OBD pin 14 (CAN_L) |
| 4 | GND | Ground | OBD pin 4 (chassis GND) |
| 5 | STBY | Standby control | ESP32 GPIO6 (drive HIGH for normal mode) |
| 6 | INT | Interrupt output (optional) | ESP32 GPIO5 |
| 7 | NC | No connect | Leave floating |
| 8 | TXD | CAN transmit data out | ESP32 GPIO1 (TWAI TX) |
| 9 | RXD | CAN receive data in | ESP32 GPIO2 (TWAI RX) |
| 10 | VCC | 5V power supply | Buck converter 5V output |
| 11 | INH | Inhibit (open-drain power control) | Buck converter EN pin |
| 12 | VIO | 3.3V I/O voltage | ESP32 3.3V rail |
| 13 | VBAT | Battery sense (internal) | Connect to VCC or leave open |
| 14 | WAKE | Wake pin (not used) | Leave floating |

**Package marking:** The TJA1145TK/3 will have the lot number etched on top. The leads are on the short sides.

---

## Step 2 — Solder TJA1145 to Adapter PCB

The HVSON-14 package has 0.5mm lead pitch. Use a breakout adapter or solder it directly to a prototype PCB.

**Option A — Solder directly to prototype PCB:**
1. Apply flux to TJA1145 pads and prototype PCB
2. Tin the pads with a fine-tip soldering iron
3. Place TJA1145, align under microscope or magnifying glass
4. Reflow each side with hot air gun at 230°C or solder each pad manually with fine tip
5. Inspect under magnification — no bridges, all 14 leads connected

**Option B — Use a SOIC-14 to DIP adapter:**
1. Socket the TJA1145 into the adapter
2. Solder the adapter pins to your PCB/wires
3. Easier to swap if you kill the chip

**Tip:** Buy 2x TJA1145 — one to solder, one spare. HVSON-14 is easy to destroy with static or heat damage.

---

## Step 3 — Wire TJA1145 to OBD Port

```
OBD Port          TJA1145 Pin         Wire Color (typical)
──────────────────────────────────────────────────────────
Pin 4 (GND)   →   Pin 4  (GND)        Black
Pin 6 (CAN_H) →   Pin 2  (CANH)       White/Green twisted pair
Pin 14 (CAN_L)→   Pin 3  (CANL)       White/Brown twisted pair
```

**CAN bus connections:**
- Use twisted pair wire (speaker wire works) for CAN_H/CAN_L
- Keep CAN wires short — maximum 30cm from OBD to TJA1145
- Optional: 100nF capacitor between CANH and GND, close to TJA1145, for EMI filtering

---

## Step 4 — Wire Power (OBD Pin 16 to TJA1145 + Buck Converter)

```
OBD Pin 16 (12V always-on)
     │
     ├──→ iCar Pro Y-splitter port (iCar Pro has internal regulator)
     │
     └──→ Buck Converter INPUT +
           │
           ├──→ 1A inline fuse (hot side)
           │
           └──→ Buck Converter INPUT -

Buck Converter 5V OUTPUT ──→ TJA1145 VCC (Pin 10)
Buck Converter 5V OUTPUT ──→ ESP32 5V pin

ESP32 3.3V pin ────────────→ TJA1145 VIO (Pin 12)
Buck Converter GND ────────→ TJA1145 GND (Pin 4) + ESP32 GND
```

**⚠️ Verify your buck converter EN polarity first (before wiring anything):**

> Some Mini360 modules have **active-low** EN (output is ON when EN is pulled LOW, OFF when EN is HIGH). Others have **active-high** EN (ON when EN is HIGH). This guide assumes **active-high**.
>
> **Test:** Connect 12V to buck input. With EN pin **floating** (nothing connected), measure voltage on the 5V output.
> - **5V present** → active-high EN ✅ (this guide applies)
> - **0V** → active-low EN ❌ (you need a different module, or add an NPN transistor inverter between TJA1145 INH and buck EN)

**Wire gauge:**
- 12V power from OBD pin 16: 22AWG, max 1A
- 5V rails: 22AWG
- CAN signals: 26AWG twisted pair

**Inline fuse placement:**
```
OBD Pin 16 ──[1A fuse]─── Buck Converter INPUT +
                        │
                        Buck Converter INPUT -
                        │
                        GND ← OBD Pin 4
```

---

## Step 5 — Wire TJA1145 INH to Buck Converter ENABLE

This is the critical connection that makes the power architecture work.

```
TJA1145 INH (Pin 11, open-drain output)
     │
     ├──→ Buck Converter EN pin (this enables 5V output when TJA1145 drives HIGH)
     │
     └──→ 10kΩ pull-down resistor to GND
               │
               └────────────────────────────→ Buck GND
```

**Why the 10kΩ pull-down?**
On power-up before TJA1145 takes control, the INH pin is in Hi-Z (floating). The pull-down ensures the buck converter stays **disabled** until TJA1145 actively drives INH HIGH. Without it, the buck might enable accidentally on startup.

**Full EN pin circuit:**
```
Buck EN pin ─── 10kΩ ──┬── GND   (pulls EN LOW when TJA1145 INH is Hi-Z)
                       │
                  TJA1145 INH (open-drain)
                       │
                  (drives HIGH = 5V at EN when CAN activity detected)
                       │
                  (drives LOW or Hi-Z = 0V at EN = buck disabled)
```

**Test:** With everything wired, measure voltage at buck EN pin:
- TJA1145 not initialized yet → should read 0V (pull-down working)
- After `tja1145_init()` in code → should read ~3.3V (TJA1145 driving HIGH)

---

## Step 6 — Wire ESP32 GPIO to TJA1145

```
TJA1145 Pin 8 (TXD) ──────────────→ ESP32 GPIO1  (TWAI TX)
TJA1145 Pin 9 (RXD) ──────────────→ ESP32 GPIO2  (TWAI RX)

TJA1145 Pin 5 (STBY) ─────────────→ ESP32 GPIO6  (output, drive HIGH in code)
TJA1145 Pin 11 (INH) ─────────────→ ESP32 GPIO4  (output/input, controlled by code)
TJA1145 Pin 6 (INT)  ─────────────→ ESP32 GPIO5  (input, optional diagnostics)
```

**In `tja1145_init()` (from `power_manager.py`):**
```python
# STBY HIGH = normal operating mode
stby = machine.Pin(TJA1145_STBY_GPIO, machine.Pin.OUT)  # GPIO6
stby.value(1)

# INH released = TJA1145 takes full control of buck EN
inh = machine.Pin(TJA1145_INH_GPIO, machine.Pin.IN)  # GPIO4
# Buck EN is now controlled by TJA1145 INH pin
```

---

## Step 7 — Wire iCar Pro (from same Y-splitter)

The TJA1145 and iCar Pro share the same CAN bus (OBD pins 6/14). The iCar Pro handles its own 12V regulation internally.

```
OBD Port ── Y-Splitter ──┬── iCar Pro (female port A — 12V direct, no buck)
                         │
                         └─── Buck Converter (12V→5V) ──→ ESP32 5V
                               │
                               └──→ TJA1145 VCC (Pin 10)
```

The iCar Pro and TJA1145 both listen to the same CAN_H/CAN_L bus wires. They do not interfere with each other — CAN is a broadcast bus.

---

## Step 8 — Assemble and Inspect

**Check all connections before powering on:**

```
OBD Pin 16 (12V always) ──┬── Buck INPUT ──→ Buck OUTPUT 5V ──→ ESP32 5V
                          │                                         │
                          └──→ iCar Pro (direct)                    │
                                                                    │
OBD Pin 6 (CAN_H) ───────────────→ TJA1145 CANH ←───────────┤
                                                               │
OBD Pin 14 (CAN_L) ───────────────→ TJA1145 CANL ←───────────┤
                                                               │
OBD Pin 4 (GND) ───────────────────→ Buck GND                 │
                                                               │
TJA1145 VCC (Pin 10) ──────────────→ Buck 5V ─────────────────┤

TJA1145 INH (Pin 11) ──────────────→ Buck EN
TJA1145 STBY (Pin 5) ──────────────→ ESP32 GPIO6
TJA1145 TXD (Pin 8) ───────────────→ ESP32 GPIO1
TJA1145 RXD (Pin 9) ───────────────→ ESP32 GPIO2
TJA1145 INT (Pin 6)  ──────────────→ ESP32 GPIO5 (optional)

10kΩ pull-down ────────────────────→ Buck EN to GND
```

**Continuity check (with multimeter, car off):**
1. OBD Pin 4 (GND) to TJA1145 Pin 4 (GND) → continuity (0Ω)
2. OBD Pin 16 (12V) to Buck INPUT+ → continuity
3. Buck OUTPUT 5V to ESP32 5V pin → continuity
4. TJA1145 INH to Buck EN → continuity
5. TJA1145 CANH to OBD Pin 6 → continuity
6. TJA1145 CANL to OBD Pin 14 → continuity

---

## Full Wiring Diagram

```
╔══════════════════════════════════════════════════════════════╗
║                    OBD-II PORT (under dash)                  ║
║                                                              ║
║   Pin 16 (12V always-on)  ──┐                                ║
║   Pin 4  (GND)              ──┤                                ║
║   Pin 6  (CAN_H)            ──┤                                ║
║   Pin 14 (CAN_L)            ──┤                                ║
║   Pin 5  (Signal GND)       ──┘                                ║
╚══════════════════════════════╪════════════════════════════════╝
                               │
              ┌────────────────┴────────────────┐
              │                                  │
        ┌─────▼─────┐                    ┌──────▼──────┐
        │ iCar Pro  │                    │  Y-Splitter │
        │   (BLE)   │                    │   1M → 2F   │
        └─────┬─────┘                    └──────┬──────┘
              │                                 │
        12V direct                         ┌────┼────┐
        (iCar handles                     Port A    Port B
         own regulation)                   │         │
                                          │    ┌────▼────┐
                                          │    │ Buck    │
                                          │    │ 12V→5V  │
                                          │    │ Mini360 │
                                          │    └────┬────┘
                                          │         │ 5V
                                          │    ┌────▼────┐
                                          │    │ TJA1145 │
                                          │    │ HVSON-14│
                                          │    └──┬──────┘
                                          │       │ VCC (5V)
                                          │       │ CANH/CANL (OBD pins 6/14)
                                          │       │ INH (→ Buck EN)
                                          │       │ STBY (→ GPIO6)
                                          │       │ TXD (→ GPIO1)
                                          │       │ RXD (→ GPIO2)
                                          │       │
                                          │  ESP32 3.3V ──→ TJA1145 VIO
                                          │       │
                                     ┌────▼────▼────┐
                                     │   LOLIN S3   │
                                     │  ESP32-S3    │
                                     │  GPIO1 TXD   │
                                     │  GPIO2 RXD   │
                                     │  GPIO4 INH   │
                                     │  GPIO5 INT   │
                                     │  GPIO6 STBY  │
                                     │  5V in       │
                                     │  GND         │
                                     └──────────────┘

BUCK CONVERTER (detailed):

  INPUT (+):  ────[1A fuse]─── OBD Pin 16 (12V)
  INPUT (-):  ─────────────── OBD Pin 4 (GND)
  
  OUTPUT (+): ─────────────── ESP32 5V pin
                                └──→ TJA1145 VCC (Pin 10)
  OUTPUT (-): ─────────────── OBD Pin 4 (GND)
  
  EN pin:     ──┬── 10kΩ pull-down ── GND
                │
                └──→ TJA1145 INH (Pin 11, open-drain)
                      (TJA1145 drives HIGH = buck enabled)
                      (TJA1145 drives Hi-Z = pull-down pulls EN LOW = buck disabled)
```

---

## ESP32 Pin Assignments (for TJA1145 mode)

| ESP32 GPIO | Direction | TJA1145 Pin | Notes |
|-----------|-----------|-------------|-------|
| GPIO1 | TX (TWAI) | Pin 8 (TXD) | TWAI CAN transmit |
| GPIO2 | RX (TWAI) | Pin 9 (RXD) | TWAI CAN receive |
| GPIO4 | Input/Output | Pin 11 (INH) | INH released after init, TJA1145 takes control |
| GPIO5 | Input | Pin 6 (INT) | Optional diagnostics only |
| GPIO6 | Output | Pin 5 (STBY) | Drive HIGH in `tja1145_init()` to enable normal mode |
| 3.3V | Power | Pin 12 (VIO) | TJA1145 I/O voltage |
| 5V | Power | Pin 10 (VCC) | TJA1145 power supply |
| GND | Ground | Pin 4 (GND) | Common ground with OBD, buck, ESP32 |

---

## Boot Sequence (what the code does on wake)

```
1. ESP32 powers on cold (TJA1145 drove INH HIGH → buck enabled)

2. tja1145_init() runs:
   - GPIO6 (STBY) → OUT, HIGH → TJA1145 in normal mode
   - GPIO4 (INH)  → IN  → TJA1145 now controls buck EN freely

3. detect_boot_cause() → 'tja1145' (always cold, no RTC magic needed)

4. Full boot proceeds — BLE connects to iCar Pro, sampling starts

5. Engine off 30 min → enter_sleep():
   - GPIO4 (INH) → IN → releases INH pin for TJA1145 open-drain control
   - machine.deepsleep() → ESP32 powers off
   - TJA1145 stays awake, monitoring CAN at ~5µA

6. Any CAN activity (door unlock, key proximity, engine start):
   - TJA1145 drives INH HIGH → buck enables → ESP32 powers on cold
   - GOTO step 1
```

---

## Testing the Wiring

**Before deploying to the car:**

1. **Power test (bench):**
   - Connect a lab power supply set to 12V to the buck converter input
   - Measure 5V output from buck — should be stable
   - TJA1145 should show ~5V on VCC

2. **INH control test:**
   - Manually connect TJA1145 INH pin directly to 5V rail
   - Buck should enable, 5V present
   - Disconnect INH from 5V
   - Buck should disable (with 10kΩ pull-down on EN)

3. **STBY test:**
   - Connect GPIO6 (STBY) to 3.3V via ESP32 after flashing
   - TJA1145 should be in normal mode (verify current draw ~5µA)

4. **TWAI test:**
   - Load firmware, check serial output for no TWAI errors
   - `quick_scan()` should find iCar Pro if it's broadcasting

---

## Common Wiring Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Buck EN pull-down missing | ESP32 stays on even when TJA1145 tries to cut power | Add 10kΩ from EN to GND |
| TJA1145 VCC connected to 12V instead of 5V | TJA1145 destroyed | Always connect VCC to buck 5V output |
| CANH/CANL swapped | TJA1145 can't read CAN frames | Swap pins 2 and 3 on TJA1145 |
| STBY left floating | TJA1145 in standby mode, INH doesn't work | Drive STBY HIGH from GPIO6 |
| GND not shared between all devices | Unstable buck output, ESP32 resets | Run dedicated GND wire from OBD pin 4 to buck and TJA1145 |
| Wire gauge too thin for 12V feed | Voltage drop when buck draws 2A | Use 22AWG minimum for 12V power wires |

---

## Bill of Materials Summary

| Item | Qty | Est. Cost |
|------|-----|-----------|
| TJA1145TK/3 | 1 | $2.50 |
| Mini360 buck converter (12V→5V, EN pin exposed) | 1 | $1.00 |
| 10kΩ resistor (0805 or through-hole) | 1 | $0.05 |
| 100nF capacitor (0805) | 1 | $0.05 |
| OBD-II Y-splitter cable | 1 | $8.00 |
| 1A inline blade fuse + holder | 1 | $1.00 |
| Hookup wire (22AWG for power, 26AWG for signals) | 2m | $0.50 |
| Heat-shrink tubing (various sizes) | 1 pack | $1.00 |
| **Total** | | **~$14** |
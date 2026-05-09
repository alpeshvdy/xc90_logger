# ============================================================
# Volvo Enhanced PID Validation Guide
# 2018 XC90 T6 (B4204T23, SPA Platform)
# Validates: 21F40B, 221182, 22F42D
# ============================================================

---

## Overview

These 3 Volvo enhanced PIDs are **community-sourced** — not from official documentation. 
They must be validated before trusting them in production logging.

| PID | Name | Mode | Bytes | Formula | Source Confidence |
|-----|------|------|-------|---------|-------------------|
| `21F40B` | Boost Pressure Target | 21 | 2 | `(A*256+B) * 0.1 kPa` | Medium — cited in Volvo CAN projects |
| `221182` | Turbo Inlet Pressure | 22 | 2 | `(A*256+B) * 0.1 kPa` | Medium — known SPA platform identifier |
| `22F42D` | Oil Pressure | 22 | 2 | `(A*256+B) * 0.1 kPa` | ⚠️ Low — may be binary OK/Not OK signal |

---

## PHASE 1 — Raw Bytes Sanity Check (No Tools Needed)

### How to Run

Use your existing `obd.py` PID probe (the `run_pid_probe()` method already queries all 3).
**Alternatively**, send each PID manually via the ELM327 terminal:

```
ATSH7E0              # Set header to Volvo ECU
ATCAF0               # CAN auto format off
21F40B               # Query boost target
221182               # Query turbo inlet pressure
22F42D               # Query oil pressure
```

### Test Matrix — 3 Engine States

For each PID, collect raw hex responses at **three well-defined engine states**:

| State | Engine Condition | How to Achieve |
|-------|-----------------|----------------|
| **A — Key On / Engine Off** | Ignition ON, engine NOT running | Turn key to position II without starting |
| **B — Warm Idle** | Engine running at idle, coolant > 70°C | Start car, let idle until coolant warm (~5 min) |
| **C — Revving @ 3000 RPM** | Engine at 3000 RPM, parked | Hold throttle at ~3000 RPM for 10 seconds |

Record exactly what the ECU returns:

```
State A:  KEY ON / ENGINE OFF
  21F40B → ________________
  221182 → ________________
  22F42D → ________________

State B:  WARM IDLE (~800 RPM)
  21F40B → ________________
  221182 → ________________
  22F42D → ________________

State C:  REVVING @ 3000 RPM
  21F40B → ________________
  221182 → ________________
  22F42D → ________________
```

---

## PHASE 2 — Red Flag / Green Flag Checklist

### 🔴 RED FLAGS (PID is NOT valid analog data)

Mark if you see ANY of these:

```
☐ Raw bytes are exactly 00 00 across ALL three engine states
☐ Raw bytes are exactly 00 01 or 00 00 (binary toggle behavior)
☐ Response starts with "7F" + any bytes (ECU rejects this PID: 7F 11 = unsupported)
☐ Response is "NO DATA" in State B or C (engine running)
☐ Response is "CAN ERROR" consistently
☐ Bytes don't change between State A and State B (engine off vs running should differ)
☐ Bytes jump randomly by >50% between consecutive queries at the same state
```

### 🟢 GREEN FLAGS (PID is likely valid analog data)

Check for these positive signs:

```
☐ Response header matches expected:
     - Mode 21: "61 F4 0B xx xx" for F40B
     - Mode 22: "62 11 82 xx xx" for 1182
     - Mode 22: "62 F4 2D xx xx" for F42D
☐ Bytes change smoothly between states (not 0→1 only)
☐ Bytes change in a physically plausible direction (see Phase 3 table)
☐ Repeated queries at same state return consistent values (±5%)
☐ Values fall within the expected physical range (see Phase 3 table)
```

---

## PHASE 3 — Physical Plausibility Tables

### 3A: Boost Target (`21F40B`)

| Engine State | Expected Range | Physically Impossible |
|-------------|---------------|----------------------|
| Key On / Engine Off | 0–5 kPa or NO DATA | >20 kPa (turbo doesn't spin when engine is off) |
| Warm Idle (~800 RPM) | 0–20 kPa | >50 kPa (no boost demand at idle) |
| Revving @ 3000 RPM | 20–180 kPa | 0 kPa at 3000 RPM (or >250 kPa on stock T6) |

**Correlation checks:**
- Must rise with throttle / RPM (positive correlation)
- Should roughly track `boost_actual_kpa` (010B) minus `baro_pressure_kpa` (0133)
- Should be 0 or near-0 at idle with no throttle

### 3B: Turbo Inlet Pressure (`221182`)

| Engine State | Expected Range | Physically Impossible |
|-------------|---------------|----------------------|
| Key On / Engine Off | 95–105 kPa | <80 or >110 kPa (should equal barometric pressure) |
| Warm Idle (~800 RPM) | 90–105 kPa | Same — should stay near atmospheric |
| Revving @ 3000 RPM | 90–110 kPa | Still near atmospheric (inlet ≠ boost pressure) |

**Critical identity check — compare with Barometric Pressure (`0133`):**

| Query | `0133` (Baro) | `221182` (Turbo Inlet) | Are they equal (±3 kPa)? |
|-------|---------------|------------------------|--------------------------|
| State A | ___ kPa | ___ kPa | ☐ YES / ☐ NO |
| State B | ___ kPa | ___ kPa | ☐ YES / ☐ NO |
| State C | ___ kPa | ___ kPa | ☐ YES / ☐ NO |

**Interpretation:**
- If `221182` ≈ `0133` (±3 kPa) across all states → **Likely correct** — turbo inlet pressure IS near-atmospheric
- If `221182` tracks boost (rises with RPM far above barometric) → **Wrong PID** — this isn't inlet pressure, it's something on the pressurized side
- If `221182` is always a flat value → **May be a constant / calibration value**, not a sensor

### 3C: Oil Pressure (`22F42D`)

| Engine State | Expected Range | Physically Impossible |
|-------------|---------------|----------------------|
| Key On / Engine Off | 0–30 kPa or NO DATA | >50 kPa (oil pump isn't spinning) |
| Warm Idle (~800 RPM) | 100–250 kPa | <50 kPa on healthy engine |
| Revving @ 3000 RPM | 300–500 kPa | <150 kPa on healthy engine (or >800 kPa on stock) |

**⚠️ Critical test — Binary vs. Analog:**

Query `22F42D` rapidly 10 times at idle. Record all raw byte values:

```
Query 1:  ____    Query 6:  ____
Query 2:  ____    Query 7:  ____
Query 3:  ____    Query 8:  ____
Query 4:  ____    Query 9:  ____
Query 5:  ____    Query 10: ____
```

- If all 10 return **exactly the same** (e.g., all `00 01`) → Binary signal (OK/Not OK), NOT oil pressure. **Discard this PID.**
- If values vary by even 1-2 kPa between queries → Analog signal. **PID is likely valid.**

**Correlation checks:**
- MUST rise with RPM (strong positive correlation). If flat → not oil pressure.
- Hot oil pressure should be lower than cold oil pressure at same RPM
- Should NOT correlate with boost pressure (different systems)

---

## PHASE 4 — Cross-Validation Against a Known Tool

### Tool: Car Scanner ELM OBD2

**Car Scanner** by Stanislav Svistunov has pre-built Volvo SPA platform profiles. Use it as your reference.

**Setup:**
1. Install [Car Scanner ELM OBD2](https://play.google.com/store/apps/details?id=com.ovz.carscanner) on your phone (Android) — or the iOS equivalent
2. Pair your phone with the iCar Pro BLE adapter
3. In Car Scanner, go to **Settings → Connection → ELM327** and select your adapter
4. Go to **Settings → Vehicle profile → Volvo → XC90 → 2018 → T6**
5. Go to **Dashboard → Add sensor → Custom PID**
6. Enter each enhanced PID manually (see below)

### Custom PID Entries for Car Scanner

**Boost Target:**
```
OBD Mode:     21
PID:          F40B
Formula:      (A*256+B)*0.1
Unit:         kPa
Header:       7E0
```

**Turbo Inlet Pressure:**
```
OBD Mode:     22
PID:          1182
Formula:      (A*256+B)*0.1
Unit:         kPa
Header:       7E0
```

**Oil Pressure:**
```
OBD Mode:     22
PID:          F42D
Formula:      (A*256+B)*0.1
Unit:         kPa
Header:       7E0
```

### Comparison Protocol

Run Car Scanner AND your ESP32 logger **side by side** (Car Scanner on phone via BLE, your code also connected).

| Step | Action | Record |
|------|--------|--------|
| 1 | Start both Car Scanner and your logger | Time: ______ |
| 2 | Key ON, engine OFF | Car Scanner `221182`: ___ kPa | Your `221182`: ___ kPa |
| 3 | Start engine, warm idle for 2 min | Car Scanner `21F40B`: ___ kPa | Your `21F40B`: ___ kPa |
| 4 | Rev to 3000 RPM, hold 10 sec | Car Scanner `22F42D`: ___ kPa | Your `22F42D`: ___ kPa |
| 5 | Compare all 3 PIDs at cruise (~2000 RPM) | Record all side-by-side |

**Acceptance criteria:**
- Values should match within ±10% between Car Scanner and your ESP32
- If Car Scanner shows "No Data" or "N/A" for a PID → that PID is NOT available on your ECU
- If Car Scanner shows a value but your ESP32 doesn't → check your header/mode settings

---

## PHASE 5 — Extended Road Test

Once Phase 1-4 checks pass, validate under real driving:

### Test Drive Protocol (~15 minutes)

| Segment | Duration | What to Watch |
|---------|----------|---------------|
| **Cold idle** | 2 min | Oil pressure high, boost target 0, inlet = baro |
| **Light acceleration** (0→60 km/h) | 30 sec | Boost target rises with throttle, oil pressure rises with RPM |
| **Cruise** (80 km/h steady) | 3 min | Boost target low (~10-30 kPa), oil pressure stable |
| **WOT pull** (full throttle, 60→120 km/h) | 10 sec | Boost target peaks (~150-200 kPa), oil pressure at max |
| **Decel** (lift off throttle at speed) | 30 sec | Boost target drops to 0 immediately, oil pressure drops with RPM |
| **Hot idle** | 2 min | Oil pressure lower than cold idle, everything else normal |

### Post-Drive Sanity Check

After the drive, check your CSV log:

```
grep "boost_target" xc90_001.csv | head -20
grep "turbo_inlet" xc90_001.csv | head -20
grep "oil_pressure" xc90_001.csv | head -20
```

Verify:
- No NaN or negative impossible values
- Boost target = 0 at all idle rows
- Oil pressure never = 0 when RPM > 500
- Turbo inlet pressure never deviates from barometric by >10 kPa

---

## PHASE 6 — Decision Matrix

After completing Phases 1-5, fill this out for each PID:

### `21F40B` — Boost Pressure Target

| Test | Result | Pass? |
|------|--------|-------|
| Engine-off returns 0 or NO DATA | ______ | ☐ |
| Value rises with RPM/throttle | ______ | ☐ |
| RPM 3000 > Idle value | ______ | ☐ |
| Matches Car Scanner (±10%) | ______ | ☐ |
| Peaks 150-200 kPa at WOT | ______ | ☐ |
| Drops to 0 on decel | ______ | ☐ |

**Verdict: ☐ VALID  /  ☐ INVALID  /  ☐ NEEDS MORE TESTING**

### `221182` — Turbo Inlet Pressure

| Test | Result | Pass? |
|------|--------|-------|
| Engine-off ≈ barometric (±3 kPa) | ______ | ☐ |
| Does NOT rise with boost | ______ | ☐ |
| Stays 90-110 kPa across all states | ______ | ☐ |
| Matches Car Scanner (±10%) | ______ | ☐ |
| Repeated queries return consistent value | ______ | ☐ |
| Not identical to `0133` with 0 offset always | ______ | ☐ |

**Verdict: ☐ VALID  /  ☐ INVALID  /  ☐ NEEDS MORE TESTING**

### `22F42D` — Oil Pressure

| Test | Result | Pass? |
|------|--------|-------|
| Not a binary signal (varies by >1 unit) | ______ | ☐ |
| Engine-off returns 0 or NO DATA | ______ | ☐ |
| Rises with RPM (strong positive correlation) | ______ | ☐ |
| RPM 3000 > Idle value | ______ | ☐ |
| Matches Car Scanner (±10%) | ______ | ☐ |
| Hot pressure < Cold pressure at same RPM | ______ | ☐ |

**Verdict: ☐ VALID  /  ☐ INVALID  /  ☐ NEEDS MORE TESTING**

---

## ⚡ Quick Reference: What to Expect Visually

```
                    KEY ON    WARM IDLE    3000 RPM     WOT
                    ENGINE    ~800 RPM                (full
                    OFF                                throttle)
                    ───────   ─────────    ───────     ──────
Boost Target         0-5       0-15        20-80      150-200  kPa
Turbo Inlet          ~100      ~100        ~100        ~100     kPa
Oil Pressure         0-30     100-250     300-500     350-600  kPa
```

---

## 🛠️ Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| All 3 return "NO DATA" | Engine not running / ECU asleep | Start engine, wait 5 sec |
| `7F xx 11` response | PID not supported on your ECU variant | Remove from PIDS_BY_TIER |
| `7F xx 22` response | ECU security locked the PID | Try Mode 21 instead of Mode 22 |
| Values fluctuate wildly | Interference on CAN bus | Query less frequently |
| Car Scanner shows value, ESP32 doesn't | Header mismatch | Verify `ATSH7E0` and `ATCAF0` before querying |
| Oil pressure always = same 2-byte value | Binary signal, not analog | **Replace PID** — find a different oil pressure DID |

---

## 📋 Checklist Summary

- [ ] Phase 1: Raw bytes collected at 3 engine states
- [ ] Phase 2: All 3 PIDs pass green flags, no red flags
- [ ] Phase 3: All values fall within plausibility ranges
- [ ] Phase 4: Side-by-side matched with Car Scanner (±10%)
- [ ] Phase 5: 15-min drive log shows plausible behavior
- [ ] Phase 6: Decision matrix filled for each PID

**Only trust a PID after it passes ALL 6 phases.**

---

Generated for: 2018 Volvo XC90 T6 Inscription (B4204T23, SPA Platform)

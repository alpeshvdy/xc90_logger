# XC90 OBD Logger

ESP32-S3 (LOLIN Pro) OBD-II data logger for 2018 Volvo XC90 T6 (B4204T23, SPA Platform).

Logs engine data via BLE ELM327 adapter → Google Sheets in real time.

## Repo Structure

```
xc90_logger/
├── config.py              # WiFi, BLE, sampling, storage settings
├── decoder.py             # ELM327 response decoder + derived calculations
├── logger.py              # Trip detection, CSV builder, flash storage
├── main.py                # Async orchestrator — single sequential sampler
├── obd.py                 # BLE driver + ELM327 protocol handler
├── pids.py                # OBD-II PID definitions (18 Mode 01 PIDs)
├── uploader.py            # WiFi + Google Sheets webhook uploader
├── README.md              # This file
├── .gitignore
│
├── docs/                  # Documentation
│   ├── ARCHITECTURE.md
│   ├── SCHEMA.md          # Column schema evolution guide
│   ├── DEPLOYMENT_GUIDE.md
│   ├── QUICK_START.md
│   └── ...
│
├── deploy/                # Google Sheets integration
│   └── code.gs            # Apps Script webhook receiver
│
├── hw/                    # Hardware config + Wokwi simulator
│   ├── wokwi.toml
│   ├── wokwi_test.py
│   ├── diagram.json
│   ├── ESP32-S3-WROOM-1_REFERENCE.md
│   └── firmware-LOLIN_S3-v1.28.0-212-gbb9e675cf1.bin
│
├── tests/                 # Unit tests (run on PC with pytest)
│   ├── test_decoder.py
│   ├── test_logger.py
│   ├── test_uploader.py
│   └── mocks.py
│
├── tools/                 # PC-side diagnostic utilities
│   ├── test_webhook.py                # Test Google Sheets webhook
│   ├── boot_test.py                   # Pre-flight validation on ESP32
│   ├── fix_com_port.py                # Windows COM port troubleshooter
│   ├── troubleshoot_connection.py     # USB connection diagnostics
│   ├── ble_scan_debug.py              # Raw BLE advertisement scanner
│   └── first_try.py                   # Early BLE exploration script
│
└── data/                  # Sample data
    └── xc90_001.csv       # Sample log output
```

## Quick Start

1. **Flash MicroPython** to LOLIN Pro (see `docs/DEPLOYMENT_GUIDE.md`)
2. **Configure** WiFi credentials in `config.py`
3. **Deploy** Google Apps Script from `deploy/code.gs` → update `SHEETS_WEBHOOK_URL`
4. **Copy files** to ESP32: `config.py`, `pids.py`, `decoder.py`, `logger.py`, `obd.py`, `uploader.py`, `main.py`
5. **Run** `main.py` on the ESP32

## Data Flow

```
XC90 ECU → iCar Pro BLE → ESP32 → CSV on flash → WiFi → Google Sheets
                                                              ↓
                                                         AI Model
```

## Schema

37 columns, one dense row per second. All columns forward-filled for AI readiness.
See `docs/SCHEMA.md` for column details and evolution rules.

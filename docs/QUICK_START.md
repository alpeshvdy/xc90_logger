# ============================================================
# QUICK START: LOLIN PRO DEPLOYMENT
# ============================================================

## Your Setup Status ✅

✅ WiFi: Rogers 77 (configured)
✅ Timezone: Toronto UTC-5
✅ Google Sheets Webhook: LIVE (tested)
✅ Firmware: v0.1.0

---

## 3-Step Deployment

### Step 1: Flash MicroPython (5 min)

**Using esptool:**
```bash
pip install esptool
esptool.py --chip esp32s3 --port COM3 erase_flash
esptool.py --chip esp32s3 --port COM3 write_flash -z 0x0 ESP32_GENERIC_S3-*.bin
```

**Using Thonny (easier):**
- Download: https://thonny.org/
- Tools → Options → MicroPython (ESP32)
- Select your port and click "Install or Update"

---

### Step 2: Copy Project Files (2 min)

**Option A: Thonny Drag & Drop**
1. Open Thonny (LOLIN Pro connected)
2. Drag these files to the device (right panel):
   - config.py
   - pids.py
   - decoder.py
   - logger.py
   - obd.py
   - uploader.py
   - main.py

**Option B: Command Line**
```bash
pip install mpremote

mpremote cp config.py :
mpremote cp pids.py :
mpremote cp decoder.py :
mpremote cp logger.py :
mpremote cp obd.py :
mpremote cp uploader.py :
mpremote cp main.py :

# Verify
mpremote ls
```

---

### Step 3: Run Pre-Flight Check (1 min)

```bash
# Copy and run boot test
mpremote cp boot_test.py :
mpremote run boot_test.py
```

Expected output:
```
✅ config.py
✅ pids.py
✅ decoder.py
✅ logger.py
✅ obd.py
✅ uploader.py
✅ WIFI_SSID configured (Rogers 77)
✅ WIFI_PASSWORD configured
✅ SHEETS_WEBHOOK_URL configured
✅ iCar device name configured
✅ All checks passed! Ready to deploy.
```

---

## Start Logging!

```bash
mpremote run main.py
```

You'll see:
```
========================================
 XC90 OBD Logger
 Firmware v0.1.0
========================================

[boot] Initialising storage...
[boot] Connecting to iCar Pro...
[obd] Scanning for iCar Pro...
[obd] Found device: ANDROID-VLINK
[obd] Connecting...
[obd] Connected successfully
[sampler:critical] Started — interval 1.0s
...
```

---

## Monitor Real-Time Output

```bash
mpremote repl
```

Press Ctrl+C to exit. Output will show:
- Connection status
- Trip detection
- Buffer flushes
- Upload success/failures

---

## Test Trip (First Run)

1. Start logging: `mpremote run main.py`
2. Turn on iCar Pro
3. Start your car (should detect trip immediately)
4. Drive for 5 minutes
5. Park and turn off car
6. Wait 10 seconds (trip end delay)
7. Check Google Sheet for data rows

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Device not found" on flash | Try different USB port, restart LOLIN Pro |
| "Cannot connect to iCar" | Power on iCar Pro, restart Bluetooth |
| "WiFi timeout" | Check SSID/password in config.py |
| "No data in Google Sheet" | Run `python test_webhook.py` to verify |
| "Storage error" | LOLIN Pro needs 4MB flash minimum |

---

## Files Reference

```
ESP32 Project Structure:
├── config.py          - WiFi, webhook, sampling config
├── pids.py            - OBD PID definitions (37 PIDs)
├── decoder.py         - OBD response parser (53 tests)
├── logger.py          - Trip & CSV logging (42 tests)
├── obd.py             - BLE/iCar Pro driver
├── uploader.py        - WiFi & Google Sheets (33 tests)
├── main.py            - Async orchestrator
├── boot_test.py       - Pre-flight validation
├── test_webhook.py    - Webhook tester (local only)
└── wokwi_test.py      - Simulator test (Wokwi)

All code tested: 128/128 tests passing ✅
```

---

## What Happens on Boot

1. **Storage Init** - Creates /logs directory
2. **Component Init** - OBD, Logger, Uploader
3. **BLE Connect** - Finds and connects to iCar Pro
4. **Sampling Start** - 4 concurrent async tasks:
   - Critical (1s) - RPM, speed, coolant
   - Standard (2s) - Fuel trims, MAF, throttle
   - Slow (5s) - Oil temp, battery
   - Enhanced (10s) - Boost, turbo data
5. **Trip Monitor** - Watches for RPM > 100 to start
6. **Upload Task** - Attempts WiFi every 5 min
7. **Connection Monitor** - Detects BLE drops

---

**Status: READY TO DEPLOY** 🚀

Once the files are on your LOLIN Pro, you're logging OBD data straight to Google Sheets!

# ============================================================
# LOLIN PRO DEPLOYMENT GUIDE
# Getting XC90 Logger firmware onto your board
# ============================================================

## Step 1: Flash MicroPython to LOLIN Pro

### Download MicroPython
Visit: https://micropython.org/download/esp32/
Download the **S3** variant (your LOLIN Pro is ESP32-S3)
Example: `ESP32_GENERIC_S3-*.bin`

### Flash the Firmware

**Option A: Using esptool.py (Recommended)**

```bash
# Install esptool
pip install esptool

# Connect LOLIN Pro via USB

# Erase flash
esptool.py --chip esp32s3 --port COM3 erase_flash

# Flash MicroPython (adjust path to your .bin file)
esptool.py --chip esp32s3 --port COM3 \
  write_flash -z 0x0 ESP32_GENERIC_S3-20251209-v1.27.0.bin

# Wait for completion
```

**Option B: Using Thonny IDE (Easier for beginners)**
1. Download Thonny: https://thonny.org/
2. Connect LOLIN Pro via USB
3. Tools → Options → Interpreter → MicroPython (ESP32)
4. Select your board and port
5. Install or Update MicroPython
6. Thonny will handle everything

---

## Step 2: Copy Project Files to LOLIN Pro

Once MicroPython is flashed, you can transfer files using:

**Option A: Thonny (Drag & Drop)**
1. Open Thonny with LOLIN Pro connected
2. Left panel: Your computer files
3. Right panel: Device files
4. Drag these files to the device:
   - config.py
   - pids.py
   - decoder.py
   - logger.py
   - obd.py
   - uploader.py
   - main.py

**Option B: Via MPRemote (Command Line)**
```bash
# Install mpremote
pip install mpremote

# Connect device (auto-detect)
mpremote connect auto

# Copy files to device
mpremote cp config.py :
mpremote cp pids.py :
mpremote cp decoder.py :
mpremote cp logger.py :
mpremote cp obd.py :
mpremote cp uploader.py :
mpremote cp main.py :

# List files on device
mpremote ls
```

---

## Step 3: Configure for Your Setup

Before running main.py, verify config.py has:

```python
# WiFi (update these!)
WIFI_SSID = "Your_WiFi_Network"
WIFI_PASSWORD = "Your_WiFi_Password"

# iCar Pro BLE names
ICAR_DEVICE_NAME_IOS     = "IOS-VLINK"      # Or your device name
ICAR_DEVICE_NAME_ANDROID = "ANDROID-VLINK"

# Google Sheets webhook (already configured)
SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxv7BF0..."

# VIN (optional but recommended)
VIN_PARTIAL = "344148"  # Last 6 chars of your XC90 VIN
```

---

## Step 4: Test Connection (BLE Scan)

Create a quick test script `ble_scan.py`:

```python
import bluetooth

print("Scanning for BLE devices...")
ble = bluetooth.BLE()
ble.active(True)

results = []

def scan_callback(addr, adv_data):
    results.append((addr, adv_data))
    name = None
    # Try to extract device name
    if b'\x09' in adv_data or b'\x08' in adv_data:
        try:
            name = adv_data.split(b'\x09')[1] if b'\x09' in adv_data else adv_data.split(b'\x08')[1]
            name = name.decode().rstrip('\x00')
        except:
            pass
    print(f"  Found: {addr.hex()} - {name or 'Unknown'}")

ble.gap_scan(5000, int(48*1.25), int(48*1.25), callback=scan_callback)

print(f"\nScan complete. Found {len(results)} devices")
for addr, adv_data in results:
    print(f"  {addr.hex()}")
```

**Deploy and run:**
```bash
# Copy to device
mpremote cp ble_scan.py :

# Run it
mpremote run ble_scan.py
```

Look for your iCar Pro device in the output!

---

## Step 5: Start the Logger

**Option A: Run Directly**
```bash
mpremote run main.py
```

**Option B: Boot on Power (Recommended)**

Once tested, copy to device as `main.py` and it will auto-start on boot.

---

## Step 6: Monitor Output

**Watch logs in real-time:**
```bash
mpremote mount .
mpremote repl
```

You'll see output like:
```
========================================
 XC90 OBD Logger
 Firmware v0.1.0
========================================

[boot] Initialising storage...
[storage] 37.5% used (10240KB free)
[boot] Connecting to iCar Pro...
[obd] Scanning for iCar Pro...
[obd] Found device: ANDROID-VLINK
[obd] Connecting...
[obd] Connected to iCar Pro
[sampler] Sequential sampler started — 1 row/1s
[sampler] Critical: 4 PIDs every cycle
[sampler] Standard: 10 PIDs every 2nd cycle
[sampler] Slow: 8 PIDs every 5th cycle
[upload] Task started
[conn] Monitor started
[logger] Trip started: XC90_20260507_180532
[logger] Flushed 50 rows → /logs/xc90_001.csv
[trip] Flushing buffer on trip end
...
```

---

## Troubleshooting

**"Cannot connect to iCar Pro"**
- Verify iCar Pro is powered on and advertising
- Check device name matches ICAR_DEVICE_NAME_* config
- Restart iCar Pro if needed

**"Storage initialization error"**
- Normal on first boot — creates /logs directory
- Check LOLIN Pro has enough flash space (4MB minimum)

**"WiFi connection failed"**
- Verify SSID and password in config.py
- Check WiFi range (LOLIN Pro must be in range)
- Upload only happens on trip end or every 5 minutes

**"Webhook timeout"**
- Internet working on WiFi network?
- Google Sheets webhook deployed? Test with `python test_webhook.py`

---

## Next Steps After Deployment

1. **Idle Test**: Let it run at home for 10 minutes, verify logs appear in Google Sheet
2. **First Trip**: Go for a 5-minute drive, watch logger collect data
3. **Validation**: Compare OBD data with Car Scanner app side-by-side
4. **Tuning**: Adjust BUFFER_SIZE, upload intervals based on real performance

---

## Quick Reference: File Checklist

- ✅ config.py (WiFi credentials updated)
- ✅ pids.py (PID definitions)
- ✅ decoder.py (OBD response parsing)
- ✅ logger.py (Trip & CSV logging)
- ✅ obd.py (BLE communication)
- ✅ uploader.py (WiFi & Google Sheets)
- ✅ main.py (Main entry point)

**Total size:** ~50KB (easily fits in ESP32-S3 flash)

---

Ready to deploy? Follow Steps 1-2, then run main.py!

# ============================================================
# troubleshoot_connection.py
# Diagnose mpremote and LOLIN Pro connection issues
# Run this on your PC (not on the device)
# ============================================================

import os
import sys
import subprocess

print("\n" + "="*60)
print(" LOLIN Pro Connection Troubleshooting")
print("="*60 + "\n")

# Step 1: Check Python and tools
print("[1] Checking Python environment...")
print(f"    Python: {sys.executable}")
print(f"    Version: {sys.version.split()[0]}")

# Step 2: Check installed tools
print("\n[2] Checking required tools...")

tools = {
    'pip': 'pip --version',
    'python': 'python --version',
}

for tool, cmd in tools.items():
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        print(f"    ✅ {tool}: {result.stdout.strip()}")
    except Exception as e:
        print(f"    ❌ {tool}: {e}")

# Step 3: Check mpremote
print("\n[3] Checking mpremote...")
try:
    result = subprocess.run('mpremote --version', shell=True, capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"    ✅ mpremote installed: {result.stdout.strip()}")
    else:
        print(f"    ❌ mpremote error: {result.stderr}")
        print("       Try: pip install mpremote")
except Exception as e:
    print(f"    ❌ mpremote not found: {e}")
    print("       Try: pip install --upgrade mpremote")

# Step 4: Check USB devices
print("\n[4] Checking USB devices...")

if sys.platform == 'win32':
    print("    Windows detected. Checking with wmic...")
    try:
        result = subprocess.run(
            'wmic logicaldisk get name',
            shell=True, capture_output=True, text=True, timeout=5
        )
        print("    Logical disks found - device may be in USB drive mode")
    except:
        pass
    
    try:
        result = subprocess.run(
            'wmic path Win32_SerialPort get Name,Description',
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            print("    COM Ports found:")
            for line in result.stdout.split('\n')[1:]:
                if line.strip():
                    print(f"      {line}")
        else:
            print("    ❌ No COM ports found!")
            print("       - LOLIN Pro not detected or driver issue")
    except:
        pass

elif sys.platform == 'darwin':
    print("    macOS detected. Checking for /dev/tty.* devices...")
    try:
        result = subprocess.run(
            'ls /dev/tty.*',
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            print(f"    Devices: {result.stdout}")
        else:
            print("    ❌ No serial devices found")
    except:
        pass

else:  # Linux
    print("    Linux detected. Checking for /dev/ttyUSB* devices...")
    try:
        result = subprocess.run(
            'ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null',
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            print(f"    Devices: {result.stdout}")
        else:
            print("    ❌ No serial devices found")
    except:
        pass

# Step 5: Try mpremote connection
print("\n[5] Attempting mpremote connection...")
try:
    result = subprocess.run(
        'mpremote connect auto',
        shell=True, capture_output=True, text=True, timeout=5
    )
    if result.returncode == 0:
        print(f"    ✅ Connected! Output: {result.stdout.strip()}")
    else:
        print(f"    ❌ Connection failed: {result.stderr.strip()}")
except subprocess.TimeoutExpired:
    print(f"    ⏱️  Connection timeout - device not responding")
except Exception as e:
    print(f"    ❌ Error: {e}")

# Step 6: Try specific COM ports
print("\n[6] Trying specific ports...")
if sys.platform == 'win32':
    ports = ['COM3', 'COM4', 'COM5', 'COM6']
else:
    ports = ['/dev/ttyUSB0', '/dev/ttyACM0', '/dev/ttyUSB1', '/dev/ttyACM1']

for port in ports:
    try:
        result = subprocess.run(
            f'mpremote connect {port}',
            shell=True, capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            print(f"    ✅ Success on {port}!")
            print(f"       Use: mpremote connect {port}")
        # Don't print failures to reduce clutter
    except:
        pass

print("\n" + "="*60)
print(" Troubleshooting Guide")
print("="*60)

print("""
❌ "No device found" - Try these steps:

1. CHECK USB CONNECTION
   - Try a different USB port
   - Use a different USB cable (data cable, not charge-only)
   - Try USB 2.0 ports (avoid USB 3.0 hubs)

2. CHECK DRIVERS (Windows)
   - Device Manager → Ports (COM & LPT)
   - Look for "USB Serial" or "FTDI" device
   - If missing: Download CH340 drivers
     https://github.com/nodemcu/ch340g-ch341g-isp-tool

3. CHECK IF DEVICE IS RUNNING MICROPYTHON
   - Device must have MicroPython already flashed
   - If flashing incomplete, try again:
     esptool.py --chip esp32s3 --port COM3 erase_flash
     esptool.py --chip esp32s3 --port COM3 write_flash -z 0x0 ESP32_GENERIC_S3-*.bin

4. TRY MANUAL PORT
   mpremote connect /dev/ttyUSB0   # Linux
   mpremote connect /dev/tty.usbserial-*  # macOS  
   mpremote connect COM3           # Windows

5. USE THONNY INSTEAD
   - Download: https://thonny.org/
   - More reliable USB detection
   - Built-in terminal and file manager

6. RESTART EVERYTHING
   - Unplug LOLIN Pro
   - Restart computer
   - Plug in LOLIN Pro
   - Try again

7. CHECK INSTALLATION
   pip install --upgrade mpremote
   pip install --upgrade esptool

If still stuck, check the device is in:
- Boot mode (not download/upload mode)
- USB power sufficient (try powered USB hub)
- Not in power saving mode
""")

print("="*60 + "\n")

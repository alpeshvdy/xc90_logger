# ============================================================
# fix_com_port.py
# Find and release COM10 port on Windows
# ============================================================

import os
import subprocess
import sys

print("\n" + "="*60)
print(" COM Port In-Use Troubleshooting")
print("="*60 + "\n")

# Find process using COM10
print("[1] Checking what's using COM10...")

try:
    # Use netstat-like approach
    result = subprocess.run(
        'wmic process list brief',
        shell=True, capture_output=True, text=True, timeout=5
    )
    
    # Try to find common programs
    suspicious_programs = [
        'putty.exe', 'teraterm.exe', 'arduino.exe',
        'python.exe', 'micropython.exe', 'thonny.exe'
    ]
    
    found_programs = []
    for line in result.stdout.split('\n'):
        for prog in suspicious_programs:
            if prog in line.lower():
                found_programs.append(prog)
    
    if found_programs:
        print(f"   Found potentially blocking programs:")
        for prog in set(found_programs):
            print(f"   - {prog}")
    else:
        print("   No obvious blocking programs found")
        
except Exception as e:
    print(f"   Could not check processes: {e}")

print("\n[2] Solutions to try (in order):")
print("""
   A) CLOSE OTHER PROGRAMS
      - Close PuTTY, Teraterm, or any serial terminal
      - Close Arduino IDE if open
      - Close Thonny if open
      - Close any other IDE/editor with the board connected

   B) RESTART THE DEVICE
      - Unplug LOLIN Pro from USB for 2 seconds
      - Plug it back in
      - Wait 3 seconds for drivers to load
      - Try: mpremote connect COM10

   C) RELEASE PORT USING TASKKILL
      If you know what's using it, kill it:
      taskkill /IM putty.exe
      taskkill /IM arduino.exe
      
   D) USE DIFFERENT APPROACH
      - Try Thonny IDE instead (more reliable)
      - Or use Device Manager to reset the USB device:
        1. Device Manager → Ports (COM & LPT)
        2. Find "USB Serial Device" on COM10
        3. Right-click → Uninstall device
        4. Uncheck "Delete driver software"
        5. Unplug/Replug LOLIN Pro
        6. Try again

   E) TRY ANOTHER COM PORT
      - COM10 might be unstable
      - Try: mpremote connect /list
        to see what ports are available
      - Connect to a different port if available
""")

print("\n[3] Quick checks:")

# Check if COM port even exists
try:
    result = subprocess.run(
        'mode COM10',
        shell=True, capture_output=True, text=True, timeout=5
    )
    if result.returncode == 0:
        print("   ✅ COM10 exists and is configured")
    else:
        print("   ❌ COM10 doesn't exist or not configured")
except:
    pass

# List all ports
print("\n   Checking all available ports:")
try:
    result = subprocess.run(
        'mpremote list',
        shell=True, capture_output=True, text=True, timeout=5
    )
    if result.stdout.strip():
        print("   Available devices:")
        print("   " + result.stdout.replace('\n', '\n   '))
    else:
        print("   ⚠️  mpremote list shows no devices (port might be locked)")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "="*60)
print("\nNext steps:")
print("1. Close all other programs using COM ports")
print("2. Unplug/replug LOLIN Pro")
print("3. Run: mpremote connect COM10")
print("\nIf still stuck, use Thonny IDE instead")
print("="*60 + "\n")

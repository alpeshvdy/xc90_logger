# ============================================================
# boot_test.py — Pre-Flight Validation Script
# Run this on LOLIN Pro to verify everything is configured correctly
# before attempting main.py
# Usage: Copy to ESP32 root alongside config.py etc., then run.
#        Or from repo: cd xc90_logger && python tools/boot_test.py
# ============================================================

import os
import sys

# Allow running from tools/ subdirectory on PC
_p = os.path.join(os.path.dirname(__file__), '..')
if _p not in sys.path:
    sys.path.insert(0, _p)

print("\n" + "="*50)
print(" XC90 Logger — Pre-Flight Validation")
print("="*50 + "\n")

checks_passed = 0
checks_total = 0

def check(name, condition, details=""):
    """Run a validation check."""
    global checks_passed, checks_total
    checks_total += 1
    status = "✅" if condition else "❌"
    print(f"[{checks_total}] {status} {name}")
    if details:
        print(f"    {details}")
    if condition:
        checks_passed += 1
    return condition

# 1. Check imports
print("Checking imports...")
try:
    import config
    check("config.py", True)
except ImportError as e:
    check("config.py", False, str(e))
    
try:
    import pids
    check("pids.py", True, f"  {len(pids.PIDS_BY_TIER)} PID tiers loaded")
except ImportError as e:
    check("pids.py", False, str(e))

try:
    import decoder
    check("decoder.py", True)
except ImportError as e:
    check("decoder.py", False, str(e))

try:
    import logger
    check("logger.py", True)
except ImportError as e:
    check("logger.py", False, str(e))

try:
    import obd
    check("obd.py", True)
except ImportError as e:
    check("obd.py", False, str(e))

try:
    import uploader
    check("uploader.py", True)
except ImportError as e:
    check("uploader.py", False, str(e))

# 2. Check config values
print("\nChecking configuration...")
try:
    from config import (
        WIFI_SSID, WIFI_PASSWORD,
        SHEETS_WEBHOOK_URL,
        ICAR_DEVICE_NAME_IOS,
        FW_VERSION, VIN_PARTIAL,
    )
    
    check("WIFI_SSID configured", 
          WIFI_SSID != "" and "YOUR" not in WIFI_SSID,
          f"  {WIFI_SSID}")
    
    check("WIFI_PASSWORD configured",
          WIFI_PASSWORD != "" and "YOUR" not in WIFI_PASSWORD,
          "  ●●●●●●●● (hidden)")
    
    check("SHEETS_WEBHOOK_URL configured",
          SHEETS_WEBHOOK_URL != "" and "YOUR_SCRIPT_ID" not in SHEETS_WEBHOOK_URL,
          f"  {SHEETS_WEBHOOK_URL[:50]}...")
    
    check("iCar device name configured",
          ICAR_DEVICE_NAME_IOS != "",
          f"  {ICAR_DEVICE_NAME_IOS}")
    
    check("Firmware version set",
          FW_VERSION != "",
          f"  v{FW_VERSION}")
    
    check("VIN partial configured",
          VIN_PARTIAL != "" and len(VIN_PARTIAL) >= 4,
          f"  {VIN_PARTIAL}")
    
except Exception as e:
    check("Config values", False, str(e))

# 3. Check storage
print("\nChecking storage...")
try:
    import os
    try:
        os.listdir("/")
        check("Root filesystem accessible", True)
    except:
        check("Root filesystem accessible", False, "  Cannot read /")
    
    # Check /logs directory (or create it)
    try:
        os.listdir("/logs")
        check("/logs directory exists", True)
    except:
        try:
            os.mkdir("/logs")
            check("/logs directory created", True)
        except Exception as e:
            check("/logs directory", False, str(e))
    
    # Check free space
    try:
        stats = os.statvfs("/")
        total = stats[0] * stats[2]
        free = stats[0] * stats[3]
        used_pct = ((total - free) / total) * 100
        check("Sufficient storage",
              used_pct < 90,
              f"  {used_pct:.1f}% used ({free//1024}KB free)")
    except:
        check("Storage check", False, "  Cannot read filesystem stats")
        
except ImportError:
    check("os module", False, "  Required for storage access")

# 4. Check hardware interfaces
print("\nChecking hardware...")
try:
    import time
    check("time module", True)
except:
    check("time module", False)

try:
    import bluetooth
    check("bluetooth module", True, "  BLE available")
except:
    check("bluetooth module", False, "  Required for iCar Pro connection")

try:
    import network
    check("network module", True, "  WiFi available")
except:
    check("network module", False, "  Required for cloud upload")

# 5. Check async
print("\nChecking async framework...")
try:
    import uasyncio
    check("uasyncio module", True, "  Async available")
except:
    check("uasyncio module", False, "  Required for concurrent sampling")

# 6. Summary
print("\n" + "="*50)
print(f" Results: {checks_passed}/{checks_total} checks passed")
print("="*50)

if checks_passed == checks_total:
    print("\n✅ All checks passed! Ready to deploy.")
    print("\nNext steps:")
    print("  1. Connect to iCar Pro")
    print("  2. Copy main.py to device")
    print("  3. Run: main.py")
    print("  4. Monitor output for trip detection")
    sys.exit(0)
else:
    print(f"\n❌ {checks_total - checks_passed} check(s) failed.")
    print("   Fix the issues above before deploying main.py")
    sys.exit(1)

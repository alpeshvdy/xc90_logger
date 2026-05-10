# --- Time ---
UTC_OFFSET_HOURS = -5  # Toronto is UTC-5 (EST) or UTC-4 (EDT in summer)

# WiFi credentials
WIFI_SSID = "Rogers 77"
WIFI_PASSWORD = "House@77"
WIFI_TIMEOUT = 10  # seconds to wait before giving up

# Google Sheets
SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwIYHoQsp1Y3kt4XaW0kg0tl0T3D6GMdORwxyJ-sSSWVdFjExO4zFJ407dW6dRMKWBQ/exec"
SHEETS_TIMEOUT = 5  # seconds before giving up on upload

# BLE / iCar Pro
ICAR_DEVICE_NAME_IOS     = "IOS-Vlink"
ICAR_DEVICE_NAME_ANDROID = "ANDROID-Vlink"
BLE_SCAN_TIMEOUT = 10      # seconds to scan before giving up
BLE_CONNECT_TIMEOUT = 10   # seconds to wait for connection
BLE_RETRY_LIMIT = 3        # how many times to retry on failure

# OBD auto-discovery — 16-bit service UUIDs to look for in BLE advertisements
# 0xFFF0 = standard ELM327 BLE service
# 0xFFE0 = some clone adapters use this
# 0x18F0 = iCar Pro variant
OBD_SCAN_SERVICE_UUIDS = (0xFFF0, 0xFFE0, 0x18F0)

# Tier 3: brute-force connect-and-probe settings
BLE_PROBE_SCAN_TIME = 8           # seconds to scan for all nearby devices
BLE_PROBE_PER_DEVICE_TIMEOUT = 5  # seconds per device connection attempt
BLE_PROBE_MAX_DEVICES = 8         # max devices to probe (strongest signals first)

# Known iCar Pro MAC addresses (from BLE scans)
# If name-based discovery fails, we try connecting to these directly
KNOWN_ICAR_PRO_MACS = [
    (0xD2, 0xE0, 0x2F, 0x8D, 0x5A, 0x04),  # Primary known MAC
]

# iCar Pro BLE service and characteristic UUIDs
# Discovered via service & characteristic discovery on actual device:
# Service: 0x18F0 (ELM327 OBD service)
# Write Char: 0x2AF1 (handle 14, props: Write + Write Without Response)
# Notify Char: 0x2AF0 (handle 11, props: Notify + Indicate)
ICAR_SERVICE_UUID    = "000018f0-0000-1000-8000-00805f9b34fb"
ICAR_WRITE_CHAR_UUID = "00002af1-0000-1000-8000-00805f9b34fb"
ICAR_NOTIFY_CHAR_UUID= "00002af0-0000-1000-8000-00805f9b34fb"

# Sampling intervals in milliseconds
SAMPLE_RATE_CRITICAL = 1000   # RPM, coolant, boost — every 1 second
SAMPLE_RATE_STANDARD = 2000   # fuel trims, MAF, throttle — every 2 seconds
SAMPLE_RATE_SLOW     = 5000   # oil temp, battery, DTCs — every 5 seconds

# Row output interval — one AI-ready dense row per second
# SensorState forward-fills: every column has a value at every timestamp
ROW_INTERVAL_MS = 1000  # produce 1 row per second (1Hz)

# Trip detection
TRIP_START_RPM = 100        # RPM above this = engine running
TRIP_END_RPM = 0            # RPM at this = engine off
TRIP_END_DELAY = 10         # seconds RPM must stay at 0 before trip ends
                            # prevents false trip end at traffic lights
IDLE_POLL_INTERVAL = 5000   # ms between polls when engine is off


# Storage
LOG_DIR = "./logs"                   # directory on LOLIN flash
MAX_LOG_SIZE_KB = 512                # rotate log file after this size
BUFFER_SIZE = 50                     # rows to buffer in RAM before writing to flash
                                     # reduces flash write cycles

# Firmware
FW_VERSION = "0.1.0"
VIN_PARTIAL = "344148"  # replace with last 6 of your XC90 VIN
                        # find it on dashboard near windscreen


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

# ============================================================
# --- Sleep / Wake ---
# ============================================================

# Wake mode — how the ESP32 wakes from deep sleep:
#
#   "tja1145"  TJA1145 CAN transceiver with INH pin power control.
#              ESP32 is HARD OFF (zero power) when parked.
#              TJA1145 monitors CAN bus, drives INH high on any CAN activity,
#              INH enables buck converter → ESP32 boots cold.
#              Requires TJA1145 transceiver + wiring to OBD CAN bus.
#              Parked draw: ~5 µA (TJA1145 standby) + iCar Pro sleep (~4 mA)
#              Total from car battery: ~96 mAh/day (dominated by iCar Pro)
#              ESP32: ZERO power when parked (truly off, not sleeping)
#
#   "timer"    RTC timer only — wakes every SLEEP_WAKE_INTERVAL_MS,
#              does a 3s BLE scan for iCar Pro, goes back to sleep
#              if car is off. Zero hardware needed.
#              Idle draw: ~15.5 mAh/day (288 wasted wake cycles/day)
#
#   "reed"     GPIO ext0 wake from reed switch on car door.
#              ESP32 sleeps forever until door opens. Instant wake,
#              zero wasted cycles. Requires $1 reed switch + magnet.
#              Idle draw: ~0.98 mAh/day
#
#   "none"     Never sleep. Always-on 24/7 mode (~1355 mAh/day).
#              Not recommended for parked cars.
#
WAKE_MODE = "tja1145"  # TJA1145 INH-based hard-off (recommended)

# After engine has been off this long, enter deep sleep / hard-off.
# The ESP32-S3 draws ~80mA active but <0.1mA in deep sleep.
# For TJA1145 mode: power is cut entirely, so this is only for
# the "sampler_sequential" idle tracking before power-off.
# Set to 0 to disable sleep entirely (always-on 24/7 mode).
SLEEP_AFTER_IDLE_MS = 30 * 60 * 1000  # 30 minutes of 0 RPM

# --- TJA1145 CAN Transceiver (WAKE_MODE = "tja1145") ---
#
# HARDWARE: TJA1145TK/3 (HVSON-14 package, 3.3V VIO)
#
# Wiring to OBD-II port:
#   OBD Pin 16 (12V)  ──→ Buck Converter (12V→5V) ──→ TJA1145 VCC
#   OBD Pin 4 (GND)   ──────────────────────────────────→ TJA1145 GND
#   OBD Pin 6 (CAN_H) ────────────────────────────────→ TJA1145 CANH
#   OBD Pin 14 (CAN_L) ───────────────────────────────→ TJA1145 CANL
#   TJA1145 INH pin   ──→ Buck Converter EN (enable)  ──→ ESP32 powers on
#   TJA1145 INT pin   ──→ ESP32 GPIO (optional, for diagnostics)
#
# Power architecture:
#   Car parked (CAN silent)  → TJA1145 INH = Hi-Z → Buck EN = LOW → ESP32 OFF
#   CAN activity detected    → TJA1145 INH = HIGH → Buck EN = HIGH → ESP32 ON
#   Engine off 30min        → TJA1145 monitors CAN → car fully off → INH goes Hi-Z
#
# ESP32-S3 TWAI (CAN) pins for reading frames after boot:
#   TX = GPIO1 (or any remappable), RX = GPIO2
#   Connect TJA1145 TXD/RXD to ESP32 TX/RX respectively.
#
# Parts list:
#   TJA1145TK/3  (~$2.50 from Mouser/Digikey)
#   2 × 47kΩ resistors (voltage divider for 12V sense, optional)
#   1 × 100nF capacitor (optional, for CAN_H stability)
#   1 × SN65HVD230 or TJA1145 CAN transceiver (this is the TJA1145 itself)
#
TJA1145_INH_GPIO = 4   # GPIO connected to TJA1145 INH pin (ESP32 side)
                       # INH drives buck converter ENABLE to power ESP32
TJA1145_INT_GPIO = 5   # GPIO connected to TJA1145 INT pin (optional diagnostics)
TJA1145_STBY_GPIO = 6  # GPIO connected to TJA1145 STBY pin (control, optional)

# ESP32-S3 TWAI (CAN) peripheral pins — connect to TJA1145 TXD/RXD
TWAI_TX_GPIO = 1       # ESP32 TWAI transmit (TXD)
TWAI_RX_GPIO = 2       # ESP32 TWAI receive  (RXD)

# --- Timer Wake (only used when WAKE_MODE = "timer") ---
# When in deep sleep (timer mode), wake every this many ms to check
# if the car has started. Lower = catches engine start faster,
# higher = saves battery.
# 5 minutes: ~288 wakeups per 24h, ~15.3 mAh/day.
SLEEP_WAKE_INTERVAL_MS = 5 * 60 * 1000  # check every 5 minutes

# Quick BLE scan timeout when waking from timer — how long to look
# for the iCar Pro before giving up and going back to sleep.
# 3 seconds is enough for a BLE advertisement to come through.
WAKE_BLE_SCAN_TIMEOUT = 3  # seconds

# --- Reed Switch GPIO (only used when WAKE_MODE = "reed") ---
# GPIO pin connected to the reed switch.
# Must be an RTC-capable GPIO (0-21 on ESP32-S3).
# GPIO4 is available and RTC-safe.
#
# Wiring:
#   3.3V ── 100kΩ ──┬── GPIO4 (RTC wake)
#                    │
#              Reed Switch (NO)
#                    │
#                   GND
#
# Door CLOSED: magnet near reed → switch closed → GPIO = LOW
# Door OPENS:  magnet away     → switch opens  → GPIO pulled HIGH → WAKE
#
REED_GPIO_PIN = 4

# Active level for reed switch wake-on-ext0.
# 1 = wake when GPIO goes HIGH (door opens, switch opens, pull-up pulls high)
# 0 = wake when GPIO goes LOW  (door closes)
REED_WAKE_LEVEL = 1

# Number of engine-off rows to keep in RAM buffer before engine start.
# These get flushed on engine start so you capture the transition.
PRE_START_BUFFER_ROWS = 12  # ~60 seconds at 5s polling


# Storage
LOG_DIR = "./logs"                   # directory on LOLIN flash
MAX_LOG_SIZE_KB = 512                # rotate log file after this size
BUFFER_SIZE = 50                     # rows to buffer in RAM before writing to flash
                                     # reduces flash write cycles

# Firmware
FW_VERSION = "0.1.0"
VIN_PARTIAL = "344148"  # replace with last 6 of your XC90 VIN
                        # find it on dashboard near windscreen


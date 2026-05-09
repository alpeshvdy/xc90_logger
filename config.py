# --- Time ---
UTC_OFFSET_HOURS = -5  # Toronto is UTC-5 (EST) or UTC-4 (EDT in summer)

# WiFi credentials
WIFI_SSID = "Rogers 77"
WIFI_PASSWORD = "House@77"
WIFI_TIMEOUT = 10  # seconds to wait before giving up

# Google Sheets
SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxv7BF0EBcQeDzTyMwFSVlUZY2sE44MUBTbGaUt_Ziuww7kBAvQhgu4cIuLcoTr23ja/exec"
SHEETS_TIMEOUT = 5  # seconds before giving up on upload

# BLE / iCar Pro
ICAR_DEVICE_NAME_IOS     = "IOS-VLink"
ICAR_DEVICE_NAME_ANDROID = "ANDROID-VLink"
BLE_SCAN_TIMEOUT = 10      # seconds to scan before giving up
BLE_CONNECT_TIMEOUT = 10   # seconds to wait for connection
BLE_RETRY_LIMIT = 3        # how many times to retry on failure

# iCar Pro BLE service and characteristic UUIDs
# These are Vgate's published UUIDs for ELM327 BLE protocol
ICAR_SERVICE_UUID    = "0000fff0-0000-1000-8000-00805f9b34fb"
ICAR_WRITE_CHAR_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
ICAR_NOTIFY_CHAR_UUID= "0000fff1-0000-1000-8000-00805f9b34fb"

# Sampling intervals in milliseconds
SAMPLE_RATE_CRITICAL = 1000   # RPM, coolant, boost — every 1 second
SAMPLE_RATE_STANDARD = 2000   # fuel trims, MAF, throttle — every 2 seconds
SAMPLE_RATE_SLOW     = 5000   # oil temp, battery — every 5 seconds
SAMPLE_RATE_ENHANCED = 10000  # Volvo enhanced PIDs — every 10 seconds

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


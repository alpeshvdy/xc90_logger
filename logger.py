# ============================================================
# logger.py — Trip Detection, Row Building, Flash Storage
# ============================================================

import os
import json
import time
from config import (
    LOG_DIR,
    MAX_LOG_SIZE_KB,
    BUFFER_SIZE,
    TRIP_START_RPM,
    TRIP_END_RPM,
    TRIP_END_DELAY,
    FW_VERSION,
    VIN_PARTIAL,
    UTC_OFFSET_HOURS,
)
from decoder import calculate_derived

# Engine states — logged in every row
STATE_COLD_START = "cold_start"   # coolant < 70°C
STATE_WARMING    = "warming"      # coolant 70–85°C
STATE_NORMAL     = "normal"       # coolant 85–95°C
STATE_HOT        = "hot"          # coolant > 95°C

# Drive phases — logged in every row
PHASE_IDLE       = "idle"         # RPM < 900, speed = 0
PHASE_LIGHT      = "light"        # throttle < 25%
PHASE_MODERATE   = "moderate"     # throttle 25–60%
PHASE_HARD       = "hard"         # throttle > 60%
PHASE_DECEL      = "decel"        # throttle < 5%, speed > 20

def init_storage():
    """
    Create log directory on flash if it doesn't exist.
    Returns path to current log file.
    """
    try:
        os.listdir(LOG_DIR)
    except OSError:
        os.mkdir(LOG_DIR)
        print(f"[logger] Created {LOG_DIR}")

    log_file = _get_log_filename()
    print(f"[logger] Log file: {log_file}")
    return log_file


def _get_log_filename():
    """
    Returns current log filename.
    Rotates to new file if current exceeds MAX_LOG_SIZE_KB.
    Format: /logs/xc90_001.csv, /logs/xc90_002.csv etc.
    """
    index = 1
    while True:
        path = f"{LOG_DIR}/xc90_{index:03d}.csv"
        try:
            size = os.stat(path)[6]  # index 6 = file size in bytes
            if size < MAX_LOG_SIZE_KB * 1024:
                return path
            index += 1
        except OSError:
            return path  # file doesn't exist yet, use this one
        
# Full schema — every column in order
CSV_COLUMNS = [
    "timestamp_utc",
    "timestamp_local",
    "trip_id",
    "trip_sequence",
    "session_odometer",
    "engine_state",
    "drive_phase",
    # Critical PIDs
    "rpm",
    "coolant_temp_c",
    "boost_actual_kpa",
    "vehicle_speed_kph",
    # Standard PIDs
    "engine_load_pct",
    "throttle_pos_pct",
    "stft_pct",
    "ltft_pct",
    "maf_g_s",
    "intake_air_temp_c",
    "intake_manifold_pres",
    # Slow PIDs
    "oil_temp_c",
    "battery_voltage_v",
    "baro_pressure_kpa",
    "fuel_trim_sum",
    # Enhanced PIDs
    "boost_target_kpa",
    "boost_delta_kpa",
    "turbo_inlet_pres",
    "oil_pressure_kpa",
    # Raw + metadata
    "raw_pid",
    "raw_response",
    "decode_status",
    "sample_tier",
    "fw_version",
    "vin_partial",
]


def write_header(log_file):
    """
    Write CSV header row if file is new/empty.
    """
    try:
        size = os.stat(log_file)[6]
        if size == 0:
            raise OSError  # treat empty file same as missing
    except OSError:
        with open(log_file, "w") as f:
            f.write(",".join(CSV_COLUMNS) + "\n")
        print("[logger] Wrote CSV header")

def classify_engine_state(coolant_temp):
    """
    Classify engine thermal state from coolant temperature.
    Returns one of the STATE_ constants.
    """
    if coolant_temp is None:
        return STATE_COLD_START  # assume cold if unknown

    if coolant_temp < 70:
        return STATE_COLD_START
    elif coolant_temp < 85:
        return STATE_WARMING
    elif coolant_temp <= 95:
        return STATE_NORMAL
    else:
        return STATE_HOT
    
def classify_drive_phase(rpm, throttle, speed):
    """
    Classify driving behaviour from RPM, throttle and speed.
    Returns one of the PHASE_ constants.
    """
    # Handle missing values
    if rpm is None:
        return PHASE_IDLE
    throttle = throttle or 0
    speed = speed or 0

    # Deceleration — throttle near zero but moving
    if throttle < 5 and speed > 20:
        return PHASE_DECEL

    # Idle — low RPM, not moving
    if rpm < 900 and speed == 0:
        return PHASE_IDLE

    # Classify by throttle position
    if throttle < 25:
        return PHASE_LIGHT
    elif throttle <= 60:
        return PHASE_MODERATE
    else:
        return PHASE_HARD
    
class TripManager:
    """
    Manages trip detection, row sequencing, and odometer.
    One instance lives for the entire firmware session.
    """

    def __init__(self):
        self.trip_id        = None
        self.trip_sequence  = 0
        self.trip_active    = False
        self.engine_off_at  = None   # timestamp when RPM first hit 0
        self.session_odom   = 0.0    # km accumulated this trip
        self._last_speed    = 0      # for odometer integration
        self._last_time     = None   # for odometer integration

    def update(self, rpm, speed):
        """
        Call every sampling cycle with latest RPM and speed.
        Handles trip start, trip end with delay, odometer.
        Returns True if trip is active, False if not.
        """
        now = time.time()

        # --- Trip start detection ---
        if not self.trip_active and rpm is not None and rpm >= TRIP_START_RPM:
            self._start_trip(now)

        # --- Odometer integration (speed × time = distance) ---
        if self.trip_active and speed is not None:
            self._update_odometer(speed, now)

        # --- Trip end detection with delay ---
        if self.trip_active:
            if rpm is not None and rpm <= TRIP_END_RPM:
                if self.engine_off_at is None:
                    self.engine_off_at = now
                    print(f"[logger] Engine off detected, waiting {TRIP_END_DELAY}s")
                elif (now - self.engine_off_at) >= TRIP_END_DELAY:
                    self._end_trip(now)
            else:
                # RPM came back up — cancel end detection
                self.engine_off_at = None

        return self.trip_active

    def _start_trip(self, now):
        self.trip_id       = self._generate_trip_id(now)
        self.trip_sequence = 0
        self.session_odom  = 0.0
        self.trip_active   = True
        self.engine_off_at = None
        self._last_time    = now
        print(f"[logger] Trip started: {self.trip_id}")

    def _end_trip(self, now):
        print(f"[logger] Trip ended: {self.trip_id} | "
              f"{self.trip_sequence} rows | "
              f"{self.session_odom:.1f} km")
        self.trip_active   = False
        self.engine_off_at = None

    def _update_odometer(self, speed_kph, now):
        if self._last_time is not None:
            elapsed_hours = (now - self._last_time) / 3600
            self.session_odom += speed_kph * elapsed_hours
        self._last_time = now

    def _generate_trip_id(self, timestamp):
        """
        Generate unique trip ID from timestamp.
        Format: XC90_20240315_143022
        Readable and sortable.
        """
        t = time.localtime(timestamp + UTC_OFFSET_HOURS * 3600)
        return (f"XC90_{t[0]:04d}{t[1]:02d}{t[2]:02d}"
                f"_{t[3]:02d}{t[4]:02d}{t[5]:02d}")

    def next_sequence(self):
        self.trip_sequence += 1
        return self.trip_sequence
    
def build_row(trip_manager, decoded_values, sample_tier, raw_pid, raw_response, decode_status):
    """
    Assemble a complete CSV row from all current values.
    
    decoded_values: dict of pid_name → decoded value
                    from the current sampling cycle
    """
    now = time.time()
    local_time = now + UTC_OFFSET_HOURS * 3600

    # Format timestamps
    t_utc   = _format_timestamp(time.localtime(now))
    t_local = _format_timestamp(time.localtime(int(local_time)))

    # Get key values for derived columns
    rpm      = decoded_values.get("rpm")
    speed    = decoded_values.get("vehicle_speed_kph")
    coolant  = decoded_values.get("coolant_temp_c")
    throttle = decoded_values.get("throttle_pos_pct")

    # Calculate derived PIDs
    derived = calculate_derived(decoded_values)
    all_values = {**decoded_values, **derived}

    # Classify states
    engine_state = classify_engine_state(coolant)
    drive_phase  = classify_drive_phase(rpm, throttle, speed)

    # Build row dict
    row = {
        "timestamp_utc":      t_utc,
        "timestamp_local":    t_local,
        "trip_id":            trip_manager.trip_id or "no_trip",
        "trip_sequence":      trip_manager.next_sequence(),
        "session_odometer":   round(trip_manager.session_odom, 3),
        "engine_state":       engine_state,
        "drive_phase":        drive_phase,
        # PID values — None becomes empty string in CSV
        "rpm":                all_values.get("rpm", ""),
        "coolant_temp_c":     all_values.get("coolant_temp_c", ""),
        "boost_actual_kpa":   all_values.get("boost_actual_kpa", ""),
        "vehicle_speed_kph":  all_values.get("vehicle_speed_kph", ""),
        "engine_load_pct":    all_values.get("engine_load_pct", ""),
        "throttle_pos_pct":   all_values.get("throttle_pos_pct", ""),
        "stft_pct":           all_values.get("stft_pct", ""),
        "ltft_pct":           all_values.get("ltft_pct", ""),
        "maf_g_s":            all_values.get("maf_g_s", ""),
        "intake_air_temp_c":  all_values.get("intake_air_temp_c", ""),
        "intake_manifold_pres":all_values.get("intake_manifold_pres", ""),
        "oil_temp_c":         all_values.get("oil_temp_c", ""),
        "battery_voltage_v":  all_values.get("battery_voltage_v", ""),
        "baro_pressure_kpa":  all_values.get("baro_pressure_kpa", ""),
        "fuel_trim_sum":      all_values.get("fuel_trim_sum", ""),
        "boost_target_kpa":   all_values.get("boost_target_kpa", ""),
        "boost_delta_kpa":    all_values.get("boost_delta_kpa", ""),
        "turbo_inlet_pres":   all_values.get("turbo_inlet_pres", ""),
        "oil_pressure_kpa":   all_values.get("oil_pressure_kpa", ""),
        # Raw + metadata
        "raw_pid":            raw_pid,
        "raw_response":       raw_response,
        "decode_status":      decode_status,
        "sample_tier":        sample_tier,
        "fw_version":         FW_VERSION,
        "vin_partial":        VIN_PARTIAL,
    }

    return row


def _format_timestamp(t):
    """Format time.localtime() tuple to ISO8601 string."""
    return (f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"
            f"T{t[3]:02d}:{t[4]:02d}:{t[5]:02d}")

class LogBuffer:
    """
    RAM buffer — accumulates rows then flushes to flash in batches.
    Reduces flash write cycles significantly.
    """

    def __init__(self, log_file):
        self.log_file = log_file
        self._buffer  = []

    def add(self, row):
        """Add a row to buffer. Flush automatically when full."""
        self._buffer.append(row)
        if len(self._buffer) >= BUFFER_SIZE:
            self.flush()

    def flush(self):
        """Write all buffered rows to flash."""
        if not self._buffer:
            return

        # Check if we need to rotate log file
        self.log_file = _get_log_filename()
        write_header(self.log_file)

        try:
            with open(self.log_file, "a") as f:
                for row in self._buffer:
                    line = ",".join(
                        str(row.get(col, ""))
                        for col in CSV_COLUMNS
                    )
                    f.write(line + "\n")

            print(f"[logger] Flushed {len(self._buffer)} rows → {self.log_file}")
            self._buffer.clear()

        except Exception as e:
            print(f"[logger] Flush error: {e}")
            # Keep buffer — will retry next flush cycle

    def pending(self):
        """How many rows are waiting in buffer."""
        return len(self._buffer)
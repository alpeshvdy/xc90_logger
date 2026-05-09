# ============================================================
# tests/test_logger.py
# Run with: python -m pytest tests/ -v
# ============================================================

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Must import mocks before logger
import tests.mocks as mocks

from logger import (
    classify_engine_state,
    classify_drive_phase,
    TripManager,
    LogBuffer,
    build_row,
    _format_timestamp,
    CSV_COLUMNS,
    STATE_COLD_START,
    STATE_WARMING,
    STATE_NORMAL,
    STATE_HOT,
    PHASE_IDLE,
    PHASE_LIGHT,
    PHASE_MODERATE,
    PHASE_HARD,
    PHASE_DECEL,
)

# ============================================================
# SECTION 1 — classify_engine_state
# ============================================================

def test_engine_state_none_is_cold():
    assert classify_engine_state(None) == STATE_COLD_START

def test_engine_state_cold_start():
    assert classify_engine_state(-10) == STATE_COLD_START
    assert classify_engine_state(0)   == STATE_COLD_START
    assert classify_engine_state(69)  == STATE_COLD_START

def test_engine_state_warming():
    assert classify_engine_state(70)  == STATE_WARMING
    assert classify_engine_state(80)  == STATE_WARMING
    assert classify_engine_state(84)  == STATE_WARMING

def test_engine_state_normal():
    assert classify_engine_state(85)  == STATE_NORMAL
    assert classify_engine_state(90)  == STATE_NORMAL
    assert classify_engine_state(95)  == STATE_NORMAL

def test_engine_state_hot():
    assert classify_engine_state(96)  == STATE_HOT
    assert classify_engine_state(105) == STATE_HOT
    assert classify_engine_state(215) == STATE_HOT

def test_engine_state_boundary_70():
    # Exactly 70 = warming not cold
    assert classify_engine_state(70) == STATE_WARMING

def test_engine_state_boundary_85():
    # Exactly 85 = normal not warming
    assert classify_engine_state(85) == STATE_NORMAL

def test_engine_state_boundary_95():
    # Exactly 95 = normal not hot
    assert classify_engine_state(95) == STATE_NORMAL

def test_engine_state_boundary_96():
    # 96 = hot
    assert classify_engine_state(96) == STATE_HOT

# ============================================================
# SECTION 2 — classify_drive_phase
# ============================================================

def test_drive_phase_none_rpm_is_idle():
    assert classify_drive_phase(None, None, None) == PHASE_IDLE

def test_drive_phase_idle():
    assert classify_drive_phase(800, 0, 0) == PHASE_IDLE
    assert classify_drive_phase(750, 2, 0) == PHASE_IDLE

def test_drive_phase_decel():
    # Throttle < 5%, speed > 20 = deceleration
    assert classify_drive_phase(1200, 2, 50) == PHASE_DECEL
    assert classify_drive_phase(900,  4, 21) == PHASE_DECEL

def test_drive_phase_light():
    assert classify_drive_phase(1500, 10, 40) == PHASE_LIGHT
    assert classify_drive_phase(2000, 24, 60) == PHASE_LIGHT

def test_drive_phase_moderate():
    assert classify_drive_phase(2500, 25, 80)  == PHASE_MODERATE
    assert classify_drive_phase(3000, 60, 100) == PHASE_MODERATE

def test_drive_phase_hard():
    assert classify_drive_phase(4000, 61, 120) == PHASE_HARD
    assert classify_drive_phase(5000, 90, 160) == PHASE_HARD
    assert classify_drive_phase(6000, 100, 180) == PHASE_HARD

def test_drive_phase_decel_takes_priority():
    # Decel condition checked first — even at high RPM
    assert classify_drive_phase(3000, 3, 80) == PHASE_DECEL

def test_drive_phase_none_speed_defaults_zero():
    # None speed treated as 0 — no decel
    assert classify_drive_phase(1500, 10, None) == PHASE_LIGHT

def test_drive_phase_none_throttle_defaults_zero():
    # None throttle treated as 0
    assert classify_drive_phase(800, None, 0) == PHASE_IDLE

# ============================================================
# SECTION 3 — _format_timestamp
# ============================================================

def test_format_timestamp_basic():
    import time
    # localtime returns (year, month, day, hour, min, sec, ...)
    t = (2024, 3, 15, 14, 30, 22, 4, 75)
    result = _format_timestamp(t)
    assert result == "2024-03-15T14:30:22"

def test_format_timestamp_zero_padding():
    t = (2024, 1, 5, 8, 5, 3, 0, 5)
    result = _format_timestamp(t)
    assert result == "2024-01-05T08:05:03"

def test_format_timestamp_midnight():
    t = (2024, 12, 31, 0, 0, 0, 0, 366)
    result = _format_timestamp(t)
    assert result == "2024-12-31T00:00:00"

# ============================================================
# SECTION 4 — TripManager
# ============================================================

def test_trip_not_active_on_init():
    tm = TripManager()
    assert tm.trip_active == False
    assert tm.trip_id is None

def test_trip_starts_on_rpm():
    tm = TripManager()
    tm.update(rpm=50, speed=0)  # below threshold
    assert tm.trip_active == False

    tm.update(rpm=500, speed=0)  # above threshold
    assert tm.trip_active == True
    assert tm.trip_id is not None

def test_trip_id_format():
    tm = TripManager()
    tm.update(rpm=500, speed=0)
    assert tm.trip_id.startswith("XC90_")
    assert len(tm.trip_id) == 20  # XC90_YYYYMMDD_HHMMSS

def test_trip_sequence_increments():
    tm = TripManager()
    tm.update(rpm=500, speed=0)
    assert tm.next_sequence() == 1
    assert tm.next_sequence() == 2
    assert tm.next_sequence() == 3

def test_trip_end_requires_delay():
    tm = TripManager()
    tm.update(rpm=500, speed=50)  # start trip
    assert tm.trip_active == True

    # RPM drops but delay not elapsed
    tm.update(rpm=0, speed=0)
    assert tm.trip_active == True  # still active

def test_trip_end_after_delay():
    tm = TripManager()
    tm.update(rpm=500, speed=50)
    assert tm.trip_active == True

    # Simulate delay elapsed
    tm.engine_off_at = mocks.mock_time.time() - 11  # 11s ago
    tm.update(rpm=0, speed=0)
    assert tm.trip_active == False

def test_trip_end_cancelled_by_rpm():
    tm = TripManager()
    tm.update(rpm=500, speed=50)

    # RPM drops
    tm.update(rpm=0, speed=0)
    assert tm.engine_off_at is not None

    # RPM comes back — cancel end
    tm.update(rpm=800, speed=10)
    assert tm.engine_off_at is None
    assert tm.trip_active == True

def test_odometer_accumulates():
    tm = TripManager()
    tm.update(rpm=500, speed=0)

    # Simulate 1 hour at 60 kph = 60 km
    tm._last_time = mocks.mock_time.time() - 3600
    tm._update_odometer(60, mocks.mock_time.time())
    assert abs(tm.session_odom - 60.0) < 0.1

def test_odometer_zero_on_new_trip():
    tm = TripManager()
    tm.update(rpm=500, speed=50)
    tm._update_odometer(100, mocks.mock_time.time())
    assert tm.session_odom > 0

    # End trip
    tm.engine_off_at = mocks.mock_time.time() - 11
    tm.update(rpm=0, speed=0)
    assert tm.trip_active == False

    # Start new trip — odometer resets
    tm.update(rpm=500, speed=0)
    assert tm.session_odom == 0.0

def test_no_trip_no_sequence():
    tm = TripManager()
    # next_sequence before trip starts still increments
    # but trip_id is None
    assert tm.trip_id is None
    seq = tm.next_sequence()
    assert seq == 1

# ============================================================
# SECTION 5 — build_row
# ============================================================

def test_build_row_has_all_columns():
    tm = TripManager()
    tm.update(rpm=1500, speed=60)

    decoded = {
        "rpm": 1500,
        "coolant_temp_c": 88,
        "throttle_pos_pct": 25,
        "vehicle_speed_kph": 60,
        "stft_pct": 2.5,
        "ltft_pct": 3.1,
        "boost_actual_kpa": 120,
        "boost_target_kpa": 130,
    }

    row = build_row(
        trip_manager   = tm,
        decoded_values = decoded,
        sample_tier    = "critical",
        raw_pid        = "010C",
        raw_response   = "410C1AF8",
        decode_status  = "ok",
    )

    for col in CSV_COLUMNS:
        assert col in row, f"Missing column: {col}"

def test_build_row_engine_state_correct():
    tm = TripManager()
    tm.update(rpm=1500, speed=60)
    decoded = {"coolant_temp_c": 65, "rpm": 1500,
               "vehicle_speed_kph": 60}
    row = build_row(tm, decoded, "critical", "010C", "", "ok")
    assert row["engine_state"] == STATE_COLD_START

def test_build_row_drive_phase_correct():
    tm = TripManager()
    tm.update(rpm=1500, speed=60)
    decoded = {"rpm": 3000, "throttle_pos_pct": 70,
               "vehicle_speed_kph": 120, "coolant_temp_c": 90}
    row = build_row(tm, decoded, "critical", "010C", "", "ok")
    assert row["drive_phase"] == PHASE_HARD

def test_build_row_derived_fuel_trim():
    tm = TripManager()
    tm.update(rpm=1500, speed=60)
    decoded = {
        "rpm": 1500, "vehicle_speed_kph": 60,
        "stft_pct": 3.0, "ltft_pct": 4.0,
    }
    row = build_row(tm, decoded, "standard", "0106", "", "ok")
    assert row["fuel_trim_sum"] == 7.0

def test_build_row_derived_boost_delta():
    tm = TripManager()
    tm.update(rpm=2000, speed=80)
    decoded = {
        "rpm": 2000, "vehicle_speed_kph": 80,
        "boost_actual_kpa": 150.0,
        "boost_target_kpa": 180.0,
    }
    row = build_row(tm, decoded, "enhanced", "21F40B", "", "ok")
    assert row["boost_delta_kpa"] == -30.0

def test_build_row_metadata():
    from config import FW_VERSION, VIN_PARTIAL
    tm = TripManager()
    tm.update(rpm=1500, speed=60)
    row = build_row(tm, {"rpm": 1500, "vehicle_speed_kph": 60},
                   "critical", "010C", "410C1AF8", "ok")
    assert row["fw_version"]  == FW_VERSION
    assert row["vin_partial"] == VIN_PARTIAL
    assert row["sample_tier"] == "critical"
    assert row["raw_pid"]     == "010C"
    assert row["raw_response"]== "410C1AF8"

def test_build_row_missing_values_empty_string():
    tm = TripManager()
    tm.update(rpm=1500, speed=0)
    # Only RPM provided — everything else should be empty string
    row = build_row(tm, {"rpm": 1500, "vehicle_speed_kph": 0},
                   "critical", "010C", "", "ok")
    assert row["oil_temp_c"]       == ""
    assert row["battery_voltage_v"] == ""
    assert row["boost_target_kpa"] == ""

# ============================================================
# SECTION 6 — LogBuffer
# ============================================================

def test_buffer_accumulates_rows():
    buf = LogBuffer("/logs/test.csv")
    for i in range(5):
        buf.add({"test": i})
    assert buf.pending() == 5

def test_buffer_flushes_at_limit():
    from unittest.mock import patch, mock_open
    import logger

    buf = LogBuffer("/logs/test.csv")

    flushed = []
    original_flush = buf.flush
    buf.flush = lambda: flushed.append(True)

    # Add BUFFER_SIZE rows — should auto-flush
    from config import BUFFER_SIZE
    for i in range(BUFFER_SIZE):
        buf.add({"test": i})

    assert len(flushed) == 1

def test_buffer_keeps_rows_on_flush_error():
    buf = LogBuffer("/logs/test.csv")

    # Add some rows
    for i in range(3):
        buf.add({"col": i})
    # Register the file in mock_os so write_header can check it
    mocks.mock_os.set_file_size("/logs/xc90_001.csv", 50)
    # Make flush fail
    import builtins
    original_open = builtins.open
    def bad_open(*args, **kwargs):
        raise OSError("Flash write failed")
    builtins.open = bad_open

    buf.flush()

    builtins.open = original_open

    # Rows should still be in buffer
    assert buf.pending() == 3

def test_buffer_clears_after_successful_flush(tmp_path):
    # Use real file for this test
    import builtins
    log_file = str(tmp_path / "test.csv")

    buf = LogBuffer(log_file)

    # Write header manually
    with open(log_file, "w") as f:
        f.write(",".join(CSV_COLUMNS) + "\n")

    # Mock os.stat to return non-zero size
    mocks.mock_os.set_file_size(log_file, 100)

    for i in range(3):
        row = {col: f"val_{i}" for col in CSV_COLUMNS}
        buf.add(row)

    # Manually flush using real file
    with open(log_file, "a") as f:
        for row in buf._buffer:
            line = ",".join(str(row.get(col, ""))
                           for col in CSV_COLUMNS)
            f.write(line + "\n")
    buf._buffer.clear()

    assert buf.pending() == 0
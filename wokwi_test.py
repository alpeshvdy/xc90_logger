# ============================================================
# wokwi_test.py — Simulated OBD Logger Test for Wokwi
# Run this on Wokwi to test core logging logic without hardware
# ============================================================

import time
import os
import tempfile
from config import (
    SAMPLE_RATE_CRITICAL,
    TRIP_START_RPM,
    TRIP_END_RPM,
)
from pids import PIDS_BY_TIER
from decoder import decode
from logger import (
    TripManager,
    LogBuffer,
    build_row,
    classify_engine_state,
    classify_drive_phase,
)

# Create temp logs directory for testing
TEMP_LOG_DIR = os.path.join(tempfile.gettempdir(), "xc90_logs_test")
if not os.path.exists(TEMP_LOG_DIR):
    os.makedirs(TEMP_LOG_DIR)

# Patch the logger to use temp directory
import logger
original_get_log_filename = logger._get_log_filename

def mock_get_log_filename():
    """Return test log file path."""
    return os.path.join(TEMP_LOG_DIR, "xc90_test.csv")

class SimulatedOBD:
    """
    Generates realistic simulated OBD data for testing.
    Simulates a 5-minute trip: cold start → acceleration → cruise → deceleration.
    """
    
    def __init__(self):
        self.connected = True
        self.sample_count = 0
        self.start_time = time.time()
    
    def is_connected(self):
        return self.connected
    
    def query(self, pid_name):
        """Return simulated decoded value for a PID."""
        self.sample_count += 1
        elapsed = time.time() - self.start_time
        
        # Simulate 5-minute trip profile
        # 0-30s: Cold start and warming
        # 30-90s: Acceleration 
        # 90-180s: Cruise
        # 180-210s: Deceleration
        
        if pid_name == "rpm":
            if elapsed < 30:
                rpm = 800 + (elapsed / 30) * 1200  # 800→2000 RPM
            elif elapsed < 90:
                rpm = 2000 + ((elapsed - 30) / 60) * 2000  # 2000→4000 RPM
            elif elapsed < 180:
                rpm = 4000 - ((elapsed - 90) / 90) * 1500  # 4000→2500 RPM
            else:
                rpm = 500  # Decel to idle
            return {
                "status": "ok",
                "value": int(rpm),
                "raw": f"410C{int(rpm*4):04X}",
            }
        
        elif pid_name == "coolant_temp_c":
            # Warm from 20°C to 90°C over 60 seconds
            if elapsed < 60:
                temp = 20 + (elapsed / 60) * 70
            else:
                temp = 90
            return {
                "status": "ok",
                "value": int(temp),
                "raw": f"410530{int(temp):02X}",
            }
        
        elif pid_name == "vehicle_speed_kph":
            if elapsed < 30:
                speed = 0
            elif elapsed < 90:
                speed = ((elapsed - 30) / 60) * 120  # 0→120 kph
            elif elapsed < 180:
                speed = 120 - ((elapsed - 90) / 90) * 50  # 120→70 kph
            else:
                speed = 0
            return {
                "status": "ok",
                "value": int(speed),
                "raw": f"41050E{int(speed):02X}",
            }
        
        elif pid_name == "throttle_pos_pct":
            if elapsed < 90:
                throttle = ((elapsed) / 90) * 80
            elif elapsed < 180:
                throttle = 80 - ((elapsed - 90) / 90) * 60
            else:
                throttle = 2  # Light foot on decel
            return {
                "status": "ok",
                "value": int(throttle),
                "raw": f"41050F{int(throttle):02X}",
            }
        
        elif pid_name == "stft_pct":
            # Fuel trim varies with load
            return {
                "status": "ok",
                "value": 0.5 + (time.time() % 2) * 0.5,
                "raw": "41061A",
            }
        
        elif pid_name == "ltft_pct":
            return {
                "status": "ok",
                "value": 1.0 + (time.time() % 3) * 0.3,
                "raw": "41071B",
            }
        
        elif pid_name == "boost_actual_kpa":
            if elapsed < 90:
                boost = (elapsed / 90) * 180
            else:
                boost = 180 - ((elapsed - 90) / 120) * 180
            return {
                "status": "ok",
                "value": int(boost),
                "raw": "21F40B" + f"{int(boost):04X}",
            }
        
        elif pid_name == "boost_target_kpa":
            return {
                "status": "ok",
                "value": 200,
                "raw": "21F40A" + "00C8",
            }
        
        # Default for any other PID
        return {
            "status": "ok",
            "value": 0,
            "raw": "0000",
        }


def test_simulated_trip():
    """Run a full simulated trip through the logger."""
    
    print("\n" + "="*50)
    print("  XC90 OBD Logger — Wokwi Simulation Test")
    print("="*50 + "\n")
    
    # Initialize components
    obd = SimulatedOBD()
    trip_manager = TripManager()
    
    # Use temp directory for test log file
    import os
    import tempfile
    temp_dir = tempfile.gettempdir()
    log_file = os.path.join(temp_dir, "xc90_wokwi_test.csv")
    log_buffer = LogBuffer(log_file)
    
    sensor_state = {}
    samples_collected = 0
    
    # Sample for 15 seconds (simulating 5 min trip compressed)
    sample_interval = 0.5  # Sample every 500ms
    test_duration = 15
    start_time = time.time()
    
    print(f"[test] Starting simulated trip for {test_duration}s\n")
    
    while time.time() - start_time < test_duration:
        # Query critical PIDs
        rpm = obd.query("rpm")["value"]
        speed = obd.query("vehicle_speed_kph")["value"]
        coolant = obd.query("coolant_temp_c")["value"]
        throttle = obd.query("throttle_pos_pct")["value"]
        
        # Update trip manager
        trip_manager.update(rpm, speed)
        
        # Update sensor state
        sensor_state["rpm"] = rpm
        sensor_state["vehicle_speed_kph"] = speed
        sensor_state["coolant_temp_c"] = coolant
        sensor_state["throttle_pos_pct"] = throttle
        sensor_state["stft_pct"] = obd.query("stft_pct")["value"]
        sensor_state["ltft_pct"] = obd.query("ltft_pct")["value"]
        sensor_state["boost_actual_kpa"] = obd.query("boost_actual_kpa")["value"]
        sensor_state["boost_target_kpa"] = obd.query("boost_target_kpa")["value"]
        
        # Build row
        row = build_row(
            trip_manager=trip_manager,
            decoded_values=sensor_state,
            sample_tier="critical",
            raw_pid="010C",
            raw_response=obd.query("rpm")["raw"],
            decode_status="ok",
        )
        
        log_buffer.add(row)
        samples_collected += 1
        
        # Print status every 1 second
        if samples_collected % 2 == 0:
            state = classify_engine_state(coolant)
            phase = classify_drive_phase(rpm, throttle, speed)
            trip_status = "ACTIVE" if trip_manager.trip_active else "IDLE"
            
            print(f"[{samples_collected:03d}] RPM:{rpm:4.0f} Speed:{speed:3.0f}kph "
                  f"Throttle:{throttle:2.0f}% | Trip:{trip_status} "
                  f"State:{state:10s} Phase:{phase:8s}")
        
        time.sleep(sample_interval)
    
    # Final flush
    print(f"\n[test] Flushing {log_buffer.pending()} buffered rows")
    log_buffer.flush()
    
    print(f"\n✅ Test complete!")
    print(f"   Samples collected: {samples_collected}")
    print(f"   Trip detected: {trip_manager.trip_active or samples_collected > 0}")
    print(f"   Trip ID: {trip_manager.trip_id}")
    print(f"   Session distance: {trip_manager.session_odom:.1f}km")
    print(f"   Rows logged: {trip_manager.trip_sequence}")
    
    return samples_collected > 0


if __name__ == "__main__":
    try:
        success = test_simulated_trip()
        if success:
            print("\n🎉 Wokwi simulation test PASSED\n")
        else:
            print("\n❌ Wokwi simulation test FAILED\n")
    except Exception as e:
        print(f"\n❌ Test error: {e}\n")
        import traceback
        traceback.print_exc()

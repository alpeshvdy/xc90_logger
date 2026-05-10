#!/usr/bin/env python3
# ============================================================
# test_webhook.py
# Quick test to verify Google Apps Script webhook is working
# Run from repo root: python tools/test_webhook.py
# or: cd tools && python test_webhook.py (uses sys.path)
# ============================================================

import json
import os
import sys
import requests

# Allow running from tools/ subdirectory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import SHEETS_WEBHOOK_URL

def test_webhook():
    """Send sample data to verify webhook receives and logs correctly."""
    
    # Sample row data matching CSV_COLUMNS in logger.py
    sample_rows = [
        {
            "timestamp_utc": "2026-05-09T14:30:22",
            "timestamp_local": "2026-05-09T09:30:22",
            "trip_id": "XC90_20260509_143022",
            "trip_sequence": "1",
            "session_odometer": "0.0",
            "engine_state": "cold_start",
            "drive_phase": "idle",
            # Critical PIDs
            "rpm": "1500",
            "coolant_temp_c": "65",
            "boost_actual_kpa": "100",
            "vehicle_speed_kph": "0",
            # Standard PIDs
            "engine_load_pct": "10",
            "throttle_pos_pct": "0",
            "stft_pct": "0.0",
            "ltft_pct": "1.5",
            "maf_g_s": "5.2",
            "intake_air_temp_c": "25",
            "timing_advance_deg": "12",
            "fuel_system_status": "2",
            "o2_lambda": "1.0",
            "absolute_load_pct": "15",
            # Slow PIDs
            "oil_temp_c": "40",
            "battery_voltage_v": "12.6",
            "baro_pressure_kpa": "101.3",
            "fuel_pressure_kpa": "380",
            "ambient_air_temp_c": "20",
            "engine_run_time_s": "45",
            "dtc_count": "0",
            "fuel_rate_l_h": "3.2",
            "fuel_trim_sum": "1.5",
            "iat_ambient_delta_c": "5.0",
            # Metadata
            "raw_pid": "ALL",
            "raw_response": "ok",
            "decode_status": "ok",
            "sample_tier": "sequential",
            "fw_version": "0.1.0",
            "vin_partial": "344148",
        },
        {
            "timestamp_utc": "2026-05-09T14:30:23",
            "timestamp_local": "2026-05-09T09:30:23",
            "trip_id": "XC90_20260509_143022",
            "trip_sequence": "2",
            "session_odometer": "0.1",
            "engine_state": "cold_start",
            "drive_phase": "light",
            # Critical PIDs
            "rpm": "2000",
            "coolant_temp_c": "66",
            "boost_actual_kpa": "105",
            "vehicle_speed_kph": "15",
            # Standard PIDs
            "engine_load_pct": "15",
            "throttle_pos_pct": "10",
            "stft_pct": "0.5",
            "ltft_pct": "1.6",
            "maf_g_s": "6.1",
            "intake_air_temp_c": "26",
            "timing_advance_deg": "18",
            "fuel_system_status": "2",
            "o2_lambda": "0.98",
            "absolute_load_pct": "22",
            # Slow PIDs
            "oil_temp_c": "42",
            "battery_voltage_v": "12.7",
            "baro_pressure_kpa": "101.3",
            "fuel_pressure_kpa": "410",
            "ambient_air_temp_c": "20",
            "engine_run_time_s": "46",
            "dtc_count": "0",
            "fuel_rate_l_h": "4.5",
            "fuel_trim_sum": "2.1",
            "iat_ambient_delta_c": "6.0",
            # Metadata
            "raw_pid": "ALL",
            "raw_response": "ok",
            "decode_status": "ok",
            "sample_tier": "sequential",
            "fw_version": "0.1.0",
            "vin_partial": "344148",
        },
    ]
    
    payload = {"rows": sample_rows}
    
    print(f"[test] Sending {len(sample_rows)} rows to webhook...")
    print(f"[test] URL: {SHEETS_WEBHOOK_URL}")
    print(f"[test] Payload size: {len(json.dumps(payload))} bytes")
    
    try:
        response = requests.post(
            SHEETS_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        
        print(f"\n[test] Status Code: {response.status_code}")
        print(f"[test] Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"\n✅ SUCCESS — {result['rows_received']} rows received by webhook")
                print(f"   Timestamp: {result['timestamp']}")
                return True
            else:
                print(f"\n❌ FAILED — {result.get('message', 'Unknown error')}")
                return False
        else:
            print(f"\n❌ HTTP {response.status_code} — check webhook deployment")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR — {e}")
        return False

if __name__ == "__main__":
    success = test_webhook()
    exit(0 if success else 1)

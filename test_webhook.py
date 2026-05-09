#!/usr/bin/env python3
# ============================================================
# test_webhook.py
# Quick test to verify Google Apps Script webhook is working
# ============================================================

import json
import requests
from config import SHEETS_WEBHOOK_URL

def test_webhook():
    """Send sample data to verify webhook receives and logs correctly."""
    
    # Sample row data matching CSV_COLUMNS
    sample_rows = [
        {
            "timestamp_utc": "2024-03-15T14:30:22",
            "timestamp_local": "2024-03-15T09:30:22",
            "trip_id": "XC90_20240315_143022",
            "trip_sequence": "1",
            "session_odometer": "0.0",
            "engine_state": "cold_start",
            "drive_phase": "idle",
            "rpm": "1500",
            "coolant_temp_c": "65",
            "boost_actual_kpa": "100",
            "vehicle_speed_kph": "0",
            "engine_load_pct": "10",
            "throttle_pos_pct": "0",
            "stft_pct": "0.0",
            "ltft_pct": "1.5",
            "maf_g_s": "5.2",
            "intake_air_temp_c": "25",
            "intake_manifold_pres": "95",
            "oil_temp_c": "40",
            "battery_voltage_v": "12.6",
            "baro_pressure_kpa": "101.3",
            "fuel_trim_sum": "1.5",
            "boost_target_kpa": "120",
            "boost_delta_kpa": "-20.0",
            "turbo_inlet_pres": "98",
            "oil_pressure_kpa": "35",
            "raw_pid": "010C",
            "raw_response": "410C1AF8",
            "decode_status": "ok",
            "sample_tier": "critical",
            "fw_version": "0.1.0",
            "vin_partial": "344148",
        },
        {
            "timestamp_utc": "2024-03-15T14:30:23",
            "timestamp_local": "2024-03-15T09:30:23",
            "trip_id": "XC90_20240315_143022",
            "trip_sequence": "2",
            "session_odometer": "0.1",
            "engine_state": "cold_start",
            "drive_phase": "light",
            "rpm": "2000",
            "coolant_temp_c": "66",
            "boost_actual_kpa": "105",
            "vehicle_speed_kph": "15",
            "engine_load_pct": "15",
            "throttle_pos_pct": "10",
            "stft_pct": "0.5",
            "ltft_pct": "1.6",
            "maf_g_s": "6.1",
            "intake_air_temp_c": "26",
            "intake_manifold_pres": "100",
            "oil_temp_c": "42",
            "battery_voltage_v": "12.7",
            "baro_pressure_kpa": "101.3",
            "fuel_trim_sum": "2.1",
            "boost_target_kpa": "130",
            "boost_delta_kpa": "-25.0",
            "turbo_inlet_pres": "103",
            "oil_pressure_kpa": "38",
            "raw_pid": "010C",
            "raw_response": "410C1F40",
            "decode_status": "ok",
            "sample_tier": "critical",
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

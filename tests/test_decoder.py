# ============================================================
# tests/test_decoder.py
# Run on laptop with: python -m pytest tests/
# Never deployed to ESP32
# ============================================================

import sys
import pytest
sys.path.insert(0, "..")  # find decoder.py in parent folder

from decoder import (
    clean_response,
    detect_error,
    validate_response,
    extract_bytes,
    validate_range,
    decode,
    calculate_derived,
    RESPONSE_OK,
    RESPONSE_ERROR,
    RESPONSE_UNSUPPORTED,
    RESPONSE_NO_DATA,
    RESPONSE_INVALID,
)

# ============================================================
# SECTION 1 — clean_response tests
# ============================================================

def test_clean_strips_prompt():
    assert clean_response("41 0C 1A F8\r\n>") == "410C1AF8"

def test_clean_strips_spaces():
    assert clean_response("41 05 7B") == "41057B"

def test_clean_uppercase():
    assert clean_response("41 0c 1a f8") == "410C1AF8"

def test_clean_none_input():
    assert clean_response(None) == ""

def test_clean_empty_string():
    assert clean_response("") == ""

def test_clean_only_prompt():
    assert clean_response(">") == ""

def test_clean_carriage_return_only():
    assert clean_response("\r\n") == ""

# ============================================================
# SECTION 2 — detect_error tests
# ============================================================

def test_detect_no_data():
    is_err, err_type = detect_error("NODATA")
    assert is_err == True
    assert err_type == RESPONSE_NO_DATA

def test_detect_error_string():
    is_err, err_type = detect_error("ERROR")
    assert is_err == True
    assert err_type == RESPONSE_ERROR

def test_detect_unable_to_connect():
    is_err, err_type = detect_error("UNABLETOCONNECT")
    assert is_err == True
    assert err_type == RESPONSE_ERROR

def test_detect_bus_busy():
    is_err, err_type = detect_error("BUSBUSY")
    assert is_err == True
    assert err_type == RESPONSE_ERROR

def test_detect_7f_unsupported():
    # 7F 0C 11 = PID not supported
    is_err, err_type = detect_error("7F0C11")
    assert is_err == True
    assert err_type == RESPONSE_UNSUPPORTED

def test_detect_7f_conditions_not_met():
    # 7F 0C 22 = conditions not met
    is_err, err_type = detect_error("7F0C22")
    assert is_err == True
    assert err_type == RESPONSE_NO_DATA

def test_detect_7f_unknown_code():
    is_err, err_type = detect_error("7F0C33")
    assert is_err == True
    assert err_type == RESPONSE_ERROR

def test_detect_question_mark():
    is_err, err_type = detect_error("?")
    assert is_err == True
    assert err_type == RESPONSE_ERROR

def test_detect_valid_response_not_error():
    is_err, _ = detect_error("410C1AF8")
    assert is_err == False

def test_detect_stopped():
    is_err, err_type = detect_error("STOPPED")
    assert is_err == True
    assert err_type == RESPONSE_ERROR

# ============================================================
# SECTION 3 — validate_response tests
# ============================================================

def test_validate_standard_pid_correct_header():
    # "010C" → response should start with "410C"
    assert validate_response("410C1AF8", "010C") == True

def test_validate_standard_pid_wrong_header():
    assert validate_response("41051AF8", "010C") == False

def test_validate_enhanced_21_sufficient_length():
    assert validate_response("61F40B0190", "21F40B") == True

def test_validate_enhanced_22_sufficient_length():
    assert validate_response("621182019A", "221182") == True

def test_validate_enhanced_too_short():
    assert validate_response("61F4", "21F40B") == False

def test_validate_empty_string():
    assert validate_response("", "010C") == False

def test_validate_coolant_temp():
    # "0105" → response starts with "4105"
    assert validate_response("41057B", "0105") == True

# ============================================================
# SECTION 4 — extract_bytes tests
# ============================================================

def test_extract_rpm_bytes():
    # "410C1AF8" → data is "1AF8" → [26, 248]
    result = extract_bytes("410C1AF8", "010C")
    assert result == [0x1A, 0xF8]

def test_extract_single_byte():
    # "41057B" → data is "7B" → [123]
    result = extract_bytes("41057B", "0105")
    assert result == [0x7B]

def test_extract_enhanced_bytes():
    # "61F40B0190" → data after 6 chars = "0190" → [1, 144]
    result = extract_bytes("61F40B0190", "21F40B")
    assert result == [0x01, 0x90]

def test_extract_empty_returns_empty():
    result = extract_bytes("", "010C")
    assert result == []

def test_extract_malformed_returns_empty():
    result = extract_bytes("ZZZZ", "010C")
    assert result == []

# ============================================================
# SECTION 5 — Full decode pipeline tests
# ============================================================

def test_decode_rpm_valid():
    # "41 0C 1A F8" → RPM = (26*256 + 248) / 4 = 1726.0
    result = decode("rpm", "010C", "41 0C 1A F8")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == 1726.0
    assert result["valid_range"] == True
    assert result["unit"] == "rpm"

def test_decode_coolant_temp_valid():
    # "41 05 7B" → temp = 123 - 40 = 83°C
    result = decode("coolant_temp_c", "0105", "41 05 7B")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == 83
    assert result["valid_range"] == True

def test_decode_coolant_cold_start():
    # "41 05 00" → temp = 0 - 40 = -40°C (extreme cold)
    result = decode("coolant_temp_c", "0105", "41 05 00")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == -40
    assert result["valid_range"] == True

def test_decode_stft_positive():
    # STFT formula: (b[0] / 128.0) * 100 - 100
    # value 0x80 = 128 → (128/128)*100 - 100 = 0.0%
    result = decode("stft_pct", "0106", "41 06 80")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == 0.0

def test_decode_stft_positive_trim():
    # 0x8A = 138 → (138/128)*100 - 100 = 7.81%
    result = decode("stft_pct", "0106", "41 06 8A")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == pytest.approx(7.81, abs=0.1)

def test_decode_ltft_negative_trim():
    # 0x76 = 118 → (118/128)*100 - 100 = -7.81%
    result = decode("ltft_pct", "0107", "41 07 76")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == pytest.approx(-7.81, abs=0.1)

def test_decode_maf_valid():
    # "41 10 0A F0" → MAF = (10*256 + 240) / 100 = 28.0 g/s
    result = decode("maf_g_s", "0110", "41 10 0A F0")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == pytest.approx(28.0, abs=0.1)

def test_decode_battery_voltage():
    # "01 42 37 00" → voltage = (0x37*256 + 0x00) / 1000 = 14.08V
    result = decode("battery_voltage_v", "0142", "41 42 37 00")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == pytest.approx(14.08, abs=0.01)

def test_decode_no_data():
    result = decode("rpm", "010C", "NO DATA")
    assert result["status"] == RESPONSE_NO_DATA
    assert result["value"] is None

def test_decode_unsupported_pid():
    result = decode("rpm", "010C", "7F 0C 11")
    assert result["status"] == RESPONSE_UNSUPPORTED
    assert result["value"] is None

def test_decode_conditions_not_met():
    result = decode("oil_temp_c", "015C", "7F 5C 22")
    assert result["status"] == RESPONSE_NO_DATA

def test_decode_empty_response():
    result = decode("rpm", "010C", "")
    assert result["status"] == RESPONSE_NO_DATA

def test_decode_none_response():
    result = decode("rpm", "010C", None)
    assert result["status"] == RESPONSE_NO_DATA

def test_decode_wrong_header():
    # Response header doesn't match command
    result = decode("rpm", "010C", "41 05 7B")
    assert result["status"] == RESPONSE_INVALID

def test_decode_enhanced_boost_target():
    # "61 F4 0B 01 90" → boost = (1*256 + 144) * 0.1 = 40.0 kPa
    result = decode("boost_target_kpa", "21F40B", "61 F4 0B 01 90")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == pytest.approx(40.0, abs=0.1)

def test_decode_out_of_range_flagged():
    # RPM of 9000 is above max 7000 — should still decode
    # but valid_range should be False
    # 0x8CA0 = 36000 → 36000/4 = 9000 RPM
    result = decode("rpm", "010C", "41 0C 8C A0")
    assert result["status"] == RESPONSE_OK
    assert result["value"] == 9000.0
    assert result["valid_range"] == False

def test_decode_raw_always_preserved():
    # Raw response always stored regardless of outcome
    raw = "NO DATA"
    result = decode("rpm", "010C", raw)
    assert result["raw"] == raw

# ============================================================
# SECTION 6 — calculate_derived tests
# ============================================================

def test_derived_fuel_trim_sum():
    values = {"stft_pct": 3.5, "ltft_pct": 4.2}
    derived = calculate_derived(values)
    assert derived["fuel_trim_sum"] == pytest.approx(7.7, abs=0.01)

def test_derived_boost_delta():
    values = {"boost_actual_kpa": 180.0, "boost_target_kpa": 190.0}
    derived = calculate_derived(values)
    assert derived["boost_delta_kpa"] == pytest.approx(-10.0, abs=0.1)

def test_derived_missing_stft():
    # If stft missing, fuel_trim_sum should not appear
    values = {"ltft_pct": 4.2}
    derived = calculate_derived(values)
    assert "fuel_trim_sum" not in derived

def test_derived_missing_boost_target():
    values = {"boost_actual_kpa": 180.0}
    derived = calculate_derived(values)
    assert "boost_delta_kpa" not in derived

def test_derived_all_missing():
    derived = calculate_derived({})
    assert derived == {}

def test_derived_zero_values():
    values = {"stft_pct": 0.0, "ltft_pct": 0.0}
    derived = calculate_derived(values)
    assert derived["fuel_trim_sum"] == 0.0

def test_derived_negative_boost_delta():
    # Actual below target = turbo underperforming
    values = {"boost_actual_kpa": 150.0, "boost_target_kpa": 200.0}
    derived = calculate_derived(values)
    assert derived["boost_delta_kpa"] == -50.0
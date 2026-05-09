# ============================================================
# decoder.py — Raw ELM327 Response Decoder
# ============================================================

from pids import ALL_PIDS

RESPONSE_OK          = "ok"
RESPONSE_ERROR       = "error"
RESPONSE_UNSUPPORTED = "unsupported"
RESPONSE_NO_DATA     = "no_data"
RESPONSE_INVALID     = "invalid"


def clean_response(raw):
    """
    Strip whitespace, prompt chars, newlines from raw ELM327 response.
    Returns uppercase string with spaces removed.
    
    Examples:
        "41 0C 1A F8\r\n>"  →  "410C1AF8"
        "NO DATA\r"         →  "NODATA"
        "7F 0C 11\r"        →  "7F0C11"
    """
    if raw is None:
        return ""
    cleaned = raw.replace(">", "").replace("\r", "").replace("\n", "").replace(" ", "")
    return cleaned.upper().strip()


def detect_error(cleaned):
    """
    Check cleaned response for known ELM327 error strings.
    Returns (is_error, error_type).
    """
    error_map = {
        "NODATA":          RESPONSE_NO_DATA,
        "ERROR":           RESPONSE_ERROR,
        "UNABLETOCONNECT": RESPONSE_ERROR,
        "BUSBUSY":         RESPONSE_ERROR,
        "BUSERROR":        RESPONSE_ERROR,
        "CANERROR":        RESPONSE_ERROR,
        "STOPPED":         RESPONSE_ERROR,
        "?":               RESPONSE_ERROR,
    }
    for pattern, error_type in error_map.items():
        if pattern in cleaned:
            return True, error_type
    if cleaned.startswith("7F"):
        if len(cleaned) >= 6:
            service_code = cleaned[4:6]
            if service_code == "11":
                return True, RESPONSE_UNSUPPORTED
            elif service_code == "22":
                return True, RESPONSE_NO_DATA
        return True, RESPONSE_ERROR
    return False, None


def validate_response(cleaned, cmd):
    """
    Verify response header matches the command sent.
    OBD mode 01 responses start with "41" + PID bytes.
    Enhanced responses vary — we just check length.
    
    Returns True if response looks valid.
    """
    if not cleaned:
        return False
    if cmd.startswith("01"):
        expected_header = "4" + cmd[1:4]
        if not cleaned.startswith(expected_header):
            return False
    elif cmd.startswith("21") or cmd.startswith("22"):
        if len(cleaned) < 6:
            return False
    return True


def extract_bytes(cleaned, cmd):
    """
    Strip response header and return list of data bytes as integers.
    
    Standard OBD-II "010C" response "410C1AF8":
        header = "410C" (4 chars = 2 bytes)
        data   = "1AF8" → [0x1A, 0xF8] → [26, 248]
    
    Enhanced "21F40B" response "61F40B0190":
        header = "61F40B" (6 chars = 3 bytes)  
        data   = "0190" → [0x01, 0x90] → [1, 144]
    """
    try:
        if cmd.startswith("01"):
            data_hex = cleaned[4:]
        elif cmd.startswith("21") or cmd.startswith("22"):
            data_hex = cleaned[6:]
        else:
            data_hex = cleaned[4:]
        byte_pairs = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
        return [int(b, 16) for b in byte_pairs if len(b) == 2]
    except Exception:
        return []


def validate_range(pid_name, value):
    """
    Check decoded value is within expected physical range.
    Returns True if valid, False if suspect.
    """
    if pid_name not in ALL_PIDS:
        return True
    pid = ALL_PIDS[pid_name]
    if pid["min"] is None or pid["max"] is None:
        return True
    return pid["min"] <= value <= pid["max"]


def decode(pid_name, cmd, raw_response):
    """
    Full decode pipeline for a single PID response.
    
    Returns dict:
    {
        "pid":          "rpm",
        "raw":          "410C1AF8",
        "value":        1726.0,
        "unit":         "rpm",
        "status":       "ok",
        "valid_range":  True
    }
    """
    result = {
        "pid":         pid_name,
        "raw":         raw_response,
        "value":       None,
        "unit":        ALL_PIDS[pid_name]["unit"] if pid_name in ALL_PIDS else "",
        "status":      RESPONSE_ERROR,
        "valid_range": False
    }
    cleaned = clean_response(raw_response)
    if not cleaned:
        result["status"] = RESPONSE_NO_DATA
        return result
    is_error, error_type = detect_error(cleaned)
    if is_error:
        result["status"] = error_type
        return result
    if not validate_response(cleaned, cmd):
        result["status"] = RESPONSE_INVALID
        return result
    data_bytes = extract_bytes(cleaned, cmd)
    if not data_bytes:
        result["status"] = RESPONSE_INVALID
        return result
    try:
        pid_def = ALL_PIDS.get(pid_name)
        if pid_def and pid_def["formula"]:
            value = pid_def["formula"](data_bytes)
            result["value"] = value
            result["valid_range"] = validate_range(pid_name, value)
            result["status"] = RESPONSE_OK
        else:
            result["status"] = RESPONSE_ERROR
    except Exception as e:
        result["status"] = RESPONSE_ERROR
        result["raw"] = f"{raw_response} | decode_err: {str(e)}"
    return result


def calculate_derived(current_values):
    """
    Calculate derived PIDs from already-decoded values.
    Call this after each sampling cycle with the latest values dict.
    
    Returns dict of derived values to merge into the log row.
    """
    derived = {}
    stft = current_values.get("stft_pct")
    ltft = current_values.get("ltft_pct")
    if stft is not None and ltft is not None:
        derived["fuel_trim_sum"] = round(stft + ltft, 2)
    actual = current_values.get("boost_actual_kpa")
    target = current_values.get("boost_target_kpa")
    if actual is not None and target is not None:
        derived["boost_delta_kpa"] = round(actual - target, 1)
    return derived
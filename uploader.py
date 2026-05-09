# ============================================================
# uploader.py — WiFi Connection + Google Sheets Upload
# Retention: keep uploaded files 3 days then auto-delete
# Storage: warn at 90% usage
# ============================================================

import network
import urequests
import os
import json
import time
from config import (
    WIFI_SSID, WIFI_PASSWORD, WIFI_TIMEOUT,
    SHEETS_WEBHOOK_URL, SHEETS_TIMEOUT, LOG_DIR,
)

UPLOAD_TRACKER        = "/logs/uploaded.json"
MAX_UPLOADED_AGE_DAYS = 3


# ============================================================
# TRACKER HELPERS
# ============================================================

def _load_uploaded():
    """
    Load upload tracker.
    Returns dict of {filepath: upload_timestamp}
    """
    try:
        with open(UPLOAD_TRACKER, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_uploaded(uploaded):
    """Persist upload tracker to flash."""
    try:
        with open(UPLOAD_TRACKER, "w") as f:
            json.dump(uploaded, f)
    except Exception as e:
        print(f"[uploader] Tracker save error: {e}")


def _mark_uploaded(filename):
    """
    Mark a file as successfully uploaded.
    Stores upload timestamp for age-based cleanup.
    """
    uploaded = _load_uploaded()
    uploaded[filename] = time.time()
    _save_uploaded(uploaded)


def _get_pending_files(active_log_file):
    """
    Return list of CSV files not yet uploaded.
    Always excludes the active log file being written to.
    """
    uploaded = _load_uploaded()
    pending  = []

    try:
        all_files = os.listdir(LOG_DIR)
    except Exception:
        return []

    # Normalize active_log_file: strip leading './' if present
    # so "./logs/xc90_001.csv" matches "/logs/xc90_001.csv"
    normalized_active = active_log_file
    if normalized_active.startswith("./"):
        normalized_active = normalized_active[2:]

    print(f"[uploader] Debug — active_file: '{active_log_file}' → normalized: '{normalized_active}'")
    print(f"[uploader] Debug — uploaded tracker: {list(uploaded.keys())}")
    print(f"[uploader] Debug — CSV files in /logs/: {sorted([f for f in all_files if f.endswith('.csv')])}")

    for fname in sorted(all_files):
        if not fname.endswith(".csv"):
            continue
        full_path = f"{LOG_DIR}/{fname}"
        # Strip ./ from full_path too for consistent comparison
        normalized_full = full_path
        if normalized_full.startswith("./"):
            normalized_full = normalized_full[2:]
        if normalized_full == normalized_active:
            print(f"[uploader] Debug — skipping active file: {full_path}")
            continue          # never touch active file
        if full_path in uploaded or normalized_full in uploaded:
            print(f"[uploader] Debug — skipping already uploaded: {full_path}")
            continue          # already uploaded
        pending.append(full_path)
        print(f"[uploader] Debug — added pending: {full_path}")

    print(f"[uploader] Debug — pending count: {len(pending)}")
    return pending


# ============================================================
# STORAGE HEALTH
# ============================================================

def check_storage_health():
    """
    Check flash usage and warn if above 90%.
    Call on every boot and after upload sessions.
    Returns used percentage as float.
    """
    try:
        stats    = os.statvfs("/")
        total    = stats[0] * stats[2]
        free     = stats[0] * stats[3]
        used_pct = ((total - free) / total) * 100

        print(f"[storage] {used_pct:.1f}% used "
              f"({free // 1024}KB free of "
              f"{total // 1024}KB total)")

        if used_pct > 90:
            print("[storage] ⚠ WARNING: Flash above 90% — "
                  "check that uploads are succeeding")
        return used_pct

    except Exception as e:
        print(f"[storage] Check error: {e}")
        return 0


# ============================================================
# CLEANUP
# ============================================================

def cleanup_old_uploads():
    """
    Delete uploaded files older than MAX_UPLOADED_AGE_DAYS.
    Updates tracker to remove cleaned entries.
    Call on every boot and after successful upload session.
    Returns count of deleted files.
    """
    uploaded  = _load_uploaded()
    now       = time.time()
    max_age   = MAX_UPLOADED_AGE_DAYS * 86400
    to_remove = []

    for filepath, upload_time in uploaded.items():
        age = now - upload_time
        if age >= max_age:
            try:
                os.remove(filepath)
                print(f"[uploader] Cleaned {filepath} "
                      f"({age // 86400:.0f}d old)")
            except Exception:
                pass  # file already gone, clean tracker anyway
            to_remove.append(filepath)

    for filepath in to_remove:
        del uploaded[filepath]

    if to_remove:
        _save_uploaded(uploaded)
        print(f"[uploader] Cleaned {len(to_remove)} file(s)")

    return len(to_remove)


# ============================================================
# FILE UPLOADER
# ============================================================

def _upload_file(filepath):
    """
    Read CSV file and POST rows in batches of 10 to webhook.
    Reads header first, then streams data lines in batches
    to minimize peak RAM usage on constrained ESP32.
    Returns (success_count, error_count).
    """
    success = 0
    errors  = 0

    try:
        with open(filepath, "r") as f:
            header_line = f.readline().strip()
            data_lines = []
            for line in f:
                stripped = line.strip()
                if stripped:
                    data_lines.append(stripped)
    except Exception as e:
        print(f"[uploader] Read error {filepath}: {e}")
        return 0, 1

    if not data_lines:
        # Empty or header-only — mark uploaded and skip
        return 0, 0

    headers = header_line.split(",")

    # Upload in small batches to avoid ESP32 memory pressure
    BATCH_SIZE = 5
    for i in range(0, len(data_lines), BATCH_SIZE):
        batch = data_lines[i:i + BATCH_SIZE]
        rows  = []

        for line in batch:
            if not line.strip():
                continue
            values = line.split(",")
            rows.append(dict(zip(headers, values)))

        if not rows:
            continue

        # Debug: print first batch JSON so we can see exactly what's being rejected
        if i == 0:
            payload = json.dumps({"rows": rows})
            print(f"[uploader] Debug — JSON payload ({len(payload)} bytes)")
            # Print in chunks so nothing is truncated
            for start in range(0, len(payload), 200):
                print(f"[uploader]   {payload[start:start+200]}")

        try:
            payload = json.dumps({"rows": rows})
            response = urequests.post(
                SHEETS_WEBHOOK_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=SHEETS_TIMEOUT,
            )
            if response.status_code == 200:
                success += len(rows)
            else:
                print(f"[uploader] HTTP {response.status_code} "
                      f"on batch {i // BATCH_SIZE + 1}")
                errors += len(rows)
            response.close()

        except Exception as e:
            print(f"[uploader] POST error batch "
                  f"{i // BATCH_SIZE + 1}: {e}")
            errors += len(rows)

        time.sleep(0.2)  # breathing room between batches

    return success, errors


# ============================================================
# WIFI MANAGER
# ============================================================

class WiFiManager:
    """
    Handles WiFi connection, reconnection, and disconnect.
    """

    def __init__(self):
        self.wlan      = network.WLAN(network.STA_IF)
        self.connected = False

    def connect(self):
        """
        Connect to configured WiFi network.
        Returns True if connected, False if timed out.
        """
        if self.wlan.isconnected():
            self.connected = True
            return True

        print(f"[wifi] Connecting to {WIFI_SSID}...")
        self.wlan.active(True)
        self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        start = time.time()
        while not self.wlan.isconnected():
            if (time.time() - start) >= WIFI_TIMEOUT:
                print("[wifi] Connection timed out")
                self.connected = False
                return False
            time.sleep(0.5)

        self.connected = True
        print(f"[wifi] Connected — IP: {self.wlan.ifconfig()[0]}")
        return True

    def disconnect(self):
        """Disconnect and power down WiFi radio."""
        self.wlan.disconnect()
        self.wlan.active(False)
        self.connected = False
        print("[wifi] Disconnected")

    def is_connected(self):
        self.connected = self.wlan.isconnected()
        return self.connected


# ============================================================
# MAIN UPLOAD ORCHESTRATOR
# ============================================================

def upload_pending(wifi_manager, active_log_file):
    """
    Main entry point for upload cycle.
    Call this whenever WiFi is available — e.g. on trip end
    or periodically while parked at home.

    wifi_manager:    WiFiManager instance
    active_log_file: path currently being written by LogBuffer
                     — this file is never uploaded or deleted

    Returns total rows successfully uploaded.
    """
    # Attempt WiFi if not already connected
    if not wifi_manager.is_connected():
        if not wifi_manager.connect():
            print("[uploader] No WiFi — skipping upload")
            return 0

    # Run cleanup first — remove stale uploaded files
    cleanup_old_uploads()

    # Check storage health
    check_storage_health()

    # Find files to upload
    pending = _get_pending_files(active_log_file)
    if not pending:
        # Debug: show why no pending files found
        uploaded = _load_uploaded()
        try:
            all_files = os.listdir(LOG_DIR)
        except Exception:
            all_files = []
        csv_files = [f for f in all_files if f.endswith(".csv")]
        print(f"[uploader] Debug — csv files in /logs/: {csv_files}")
        print(f"[uploader] Debug — uploaded tracker: {list(uploaded.keys())}")
        print(f"[uploader] Debug — active file: {active_log_file}")
        print("[uploader] Nothing to upload")
        return 0

    print(f"[uploader] {len(pending)} file(s) to upload")
    total_success = 0

    for filepath in pending:
        print(f"[uploader] Uploading {filepath}...")
        success, errors = _upload_file(filepath)

        if errors == 0:
            # Full success — mark and keep for 3 days then auto-delete
            _mark_uploaded(filepath)
            total_success += success
            print(f"[uploader] ✓ {filepath} — {success} rows uploaded")
        else:
            # Partial or full failure — leave for retry next session
            print(f"[uploader] ✗ {filepath} — "
                  f"{success} ok / {errors} failed — "
                  f"will retry next session")

    print(f"[uploader] Session complete — "
          f"{total_success} total rows uploaded")

    return total_success
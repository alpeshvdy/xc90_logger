# ============================================================
# main.py — XC90 OBD Logger Main Entry Point
# Orchestrates all modules into a single running loop
# ============================================================

import time
import uasyncio as asyncio
from config import (
    ROW_INTERVAL_MS,
    SAMPLE_RATE_CRITICAL,
    SAMPLE_RATE_STANDARD,
    SAMPLE_RATE_SLOW,
    IDLE_POLL_INTERVAL,
    FW_VERSION,
)
from pids import PIDS_BY_TIER, ALL_PIDS
from obd import OBDClient
from decoder import RESPONSE_OK
from logger import (
    init_storage,
    TripManager,
    LogBuffer,
    build_row,
)
from uploader import (
    WiFiManager,
    upload_pending,
    check_storage_health,
    cleanup_old_uploads,
)

class SensorState:
    """
    Holds latest decoded value for every PID.
    Forward-fills: when a PID hasn't been queried this cycle,
    its last known value is used. This ensures every CSV row
    has all columns populated — AI-ready dense rows.
    """

    def __init__(self):
        self._values = {}

    def update(self, pid_name, decode_result):
        """Update state if decode was successful. Keeps last value on failure."""
        if decode_result and decode_result["status"] == RESPONSE_OK:
            self._values[pid_name] = decode_result["value"]

    def get_all(self):
        """Return copy of all current values (forward-filled)."""
        return dict(self._values)

    def get(self, pid_name):
        return self._values.get(pid_name)


async def sampler_sequential(obd, trip_manager, log_buffer, sensor_state):
    """
    Single sequential sampler — Torque Pro method.
    One loop queries all PIDs in sequence at ROW_INTERVAL_MS.

    Each cycle:
      1. Query critical PIDs (every cycle)
      2. Query standard PIDs (every 2nd cycle)
      3. Query slow PIDs (every 5th cycle)
      4. Build ONE dense row with all forward-filled values

    No concurrent queries, no mode switching, no collisions.
    SensorState forward-fills: every column populated every row.
    """
    row_interval = ROW_INTERVAL_MS / 1000  # seconds
    cycle = 0

    critical_pids = PIDS_BY_TIER["critical"]
    standard_pids = PIDS_BY_TIER["standard"]
    slow_pids     = PIDS_BY_TIER["slow"]

    print("[sampler] Sequential sampler started — 1 row/%.0fs" % row_interval)
    print("[sampler] Critical: %d PIDs every cycle" % len(critical_pids))
    print("[sampler] Standard: %d PIDs every 2nd cycle" % len(standard_pids))
    print("[sampler] Slow:     %d PIDs every 5th cycle" % len(slow_pids))

    while True:
        cycle_start = time.time()
        cycle += 1

        # Idle mode: when engine is off, poll slowly
        if not trip_manager.trip_active:
            # Still query critical PIDs to detect trip start
            rpm_cmd = critical_pids.get("rpm", {}).get("cmd")
            if rpm_cmd:
                result = obd.query("rpm")
                if result:
                    sensor_state.update("rpm", result)

            # Run trip detection
            rpm = sensor_state.get("rpm")
            speed = sensor_state.get("vehicle_speed_kph")
            trip_manager.update(rpm, speed)

            await asyncio.sleep(IDLE_POLL_INTERVAL / 1000)
            continue

        # --- Query critical PIDs (every cycle) ---
        for pid_name, pid_def in critical_pids.items():
            if pid_def["cmd"] is None:
                continue
            if not obd.is_connected():
                break
            result = obd.query(pid_name)
            if result:
                sensor_state.update(pid_name, result)

        # --- Query standard PIDs (every 2nd cycle) ---
        if cycle % 2 == 0 and obd.is_connected():
            for pid_name, pid_def in standard_pids.items():
                if pid_def["cmd"] is None:
                    continue
                if not obd.is_connected():
                    break
                result = obd.query(pid_name)
                if result:
                    sensor_state.update(pid_name, result)

        # --- Query slow PIDs (every 5th cycle) ---
        if cycle % 5 == 0 and obd.is_connected():
            for pid_name, pid_def in slow_pids.items():
                if pid_def["cmd"] is None:
                    continue
                if not obd.is_connected():
                    break
                result = obd.query(pid_name)
                if result:
                    sensor_state.update(pid_name, result)

        # --- Run trip detection ---
        rpm = sensor_state.get("rpm")
        speed = sensor_state.get("vehicle_speed_kph")
        was_active = trip_manager.trip_active
        trip_manager.update(rpm, speed)

        # Trip just ended — flush buffer
        if was_active and not trip_manager.trip_active:
            print("[trip] Flushing buffer on trip end")
            log_buffer.flush()

        # --- Build one dense row with all forward-filled values ---
        if trip_manager.trip_active:
            row = build_row(
                trip_manager   = trip_manager,
                decoded_values = sensor_state.get_all(),
                sample_tier    = "sequential",
                raw_pid        = "ALL",
                raw_response   = "",
                decode_status  = "ok",
            )
            log_buffer.add(row)

        # --- Maintain steady pace ---
        elapsed = time.time() - cycle_start
        sleep_time = max(0, row_interval - elapsed)
        if sleep_time < row_interval * 0.5:
            print("[sampler] ⚠ Cycle %d took %.2fs (over half interval)" % (cycle, elapsed))
        await asyncio.sleep(sleep_time)

async def upload_task(wifi_manager, log_buffer):
    """
    Periodically attempts WiFi upload.
    Runs every 5 minutes — succeeds silently when home,
    fails silently when away.
    """
    print("[upload] Task started")
    UPLOAD_INTERVAL = 300  # 5 minutes

    while True:
        await asyncio.sleep(UPLOAD_INTERVAL)

        # Only upload when buffer is not actively flushing
        active_file = log_buffer.log_file
        uploaded = upload_pending(wifi_manager, active_file)

        if uploaded > 0:
            print(f"[upload] Uploaded {uploaded} rows")

async def connection_task(obd, sensor_state):
    """
    Monitors BLE connection health.
    Attempts reconnection if connection drops.
    Resets sensor state on reconnect to avoid
    stale values from previous connection.
    """
    print("[conn] Monitor started")

    while True:
        if not obd.is_connected():
            print("[conn] Connection lost — attempting reconnect")

            # Clear stale sensor values
            sensor_state._values.clear()

            success = obd.reconnect()
            if not success:
                print("[conn] Reconnect failed — waiting 30s")
                await asyncio.sleep(30)
            else:
                print("[conn] Reconnected successfully")

        await asyncio.sleep(5)

async def boot():
    """
    Full boot sequence — upload and BLE run in parallel.
    Upload fires immediately so data reaches Google Sheets
    the moment you bring the ESP32 home.
    BLE retries forever until the iCar Pro is in range.
    Returns (obd, trip_manager, log_buffer, 
             sensor_state, wifi_manager)
    or raises on unrecoverable failure.
    """
    print("\n" + "="*40)
    print(" XC90 OBD Logger")
    print(" Firmware v" + FW_VERSION)
    print("="*40 + "\n")

    # 1. Initialise storage
    print("[boot] Initialising storage...")
    log_file = init_storage()
    check_storage_health()
    cleanup_old_uploads()

    # 2. Initialise components
    obd          = OBDClient()
    trip_manager = TripManager()
    log_buffer   = LogBuffer(log_file)
    sensor_state = SensorState()
    wifi_manager = WiFiManager()

    # 3. Launch upload and BLE connection in parallel
    upload_done   = asyncio.Event()
    ble_connected = asyncio.Event()

    async def _boot_upload():
        """Background: upload any pending CSV files via WiFi."""
        print("[boot:upload] Starting background upload...")
        try:
            uploaded = upload_pending(wifi_manager, log_buffer.log_file)
            if uploaded > 0:
                print(f"[boot:upload] Uploaded {uploaded} rows")
            else:
                print("[boot:upload] Nothing to upload (or WiFi unavailable)")
        except Exception as e:
            print(f"[boot:upload] Error: {e}")
        finally:
            upload_done.set()

    async def _boot_ble():
        """Background: keep trying BLE until connected."""
        print("[boot:ble] Starting BLE connection loop...")
        attempt = 0
        while True:
            attempt += 1
            print(f"[boot:ble] Attempt {attempt}...")
            try:
                if obd.connect():
                    ble_connected.set()
                    print(f"[boot:ble] Connected on attempt {attempt}")
                    return
            except Exception as e:
                print(f"[boot:ble] Error on attempt {attempt}: {e}")
            print(f"[boot:ble] Failed — retrying in 3s...")
            await asyncio.sleep(3)

    asyncio.create_task(_boot_upload())
    asyncio.create_task(_boot_ble())

    # 4. Wait for BLE to connect (never-ending retries; upload runs in background)
    print("[boot] Waiting for BLE (upload runs in background)...")
    await ble_connected.wait()

    # 5. Ensure upload finished before PID probe (WiFi vs BLE radio safety)
    await upload_done.wait()

    # No PID probe needed — all Mode 01 standard PIDs only
    # Enhanced PIDs removed (always returned NO DATA on SPA platform)

    print("[boot] Boot complete\n")
    return obd, trip_manager, log_buffer, sensor_state, wifi_manager

async def main():
    """
    Main async entry point.
    Boots then launches all concurrent tasks.
    """
    try:
        obd, trip_manager, log_buffer, sensor_state, wifi_manager = \
            await boot()
    except Exception as e:
        print(f"[main] Boot failed: {e}")
        return

    # Launch all concurrent tasks
    # Single sequential sampler replaces the 4 old tier-specific samplers
    # Trip monitor removed — sampler_sequential handles trip state inline
    tasks = [
        asyncio.create_task(
            sampler_sequential(obd, trip_manager, log_buffer, sensor_state)
        ),
        asyncio.create_task(
            upload_task(wifi_manager, log_buffer)
        ),
        asyncio.create_task(
            connection_task(obd, sensor_state)
        ),
    ]

    print(f"[main] {len(tasks)} tasks running\n")

    # Run forever — tasks handle their own loops
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("[main] Shutdown requested — flushing buffer...")
        log_buffer.flush()
        print("[main] Attempting upload before exit...")
        upload_pending(wifi_manager, log_buffer.log_file)
        print("[main] Shutdown complete")
    except Exception as e:
        print(f"[main] Task error: {e}")
        # Flush buffer before any crash
        log_buffer.flush()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
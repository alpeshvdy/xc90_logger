# ============================================================
# main.py — XC90 OBD Logger Main Entry Point
# Orchestrates all modules into a single running loop
# ============================================================

import time
import uasyncio as asyncio
from config import (
    SAMPLE_RATE_CRITICAL,
    SAMPLE_RATE_STANDARD,
    SAMPLE_RATE_SLOW,
    SAMPLE_RATE_ENHANCED,
    IDLE_POLL_INTERVAL,
    BLE_RETRY_LIMIT,
    FW_VERSION,
)
from pids import PIDS_BY_TIER
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
    Updated each time a PID is successfully queried.
    Ensures every CSV row has all columns populated
    even when some tiers haven't sampled yet this cycle.
    """

    def __init__(self):
        self._values = {}

    def update(self, pid_name, decode_result):
        """Update state if decode was successful."""
        if decode_result and decode_result["status"] == RESPONSE_OK:
            self._values[pid_name] = decode_result["value"]

    def get_all(self):
        """Return copy of all current values."""
        return dict(self._values)

    def get(self, pid_name):
        return self._values.get(pid_name)
    
async def sampler_task(obd, trip_manager, log_buffer, sensor_state, tier):
    """
    Async task for a single sampling tier.
    Runs independently for each tier — critical, standard, slow, enhanced.

    Each tier loops forever at its own interval,
    querying its PIDs and adding rows to the buffer.
    """
    pids      = PIDS_BY_TIER[tier]
    interval  = {
        "critical": SAMPLE_RATE_CRITICAL,
        "standard": SAMPLE_RATE_STANDARD,
        "slow":     SAMPLE_RATE_SLOW,
        "enhanced": SAMPLE_RATE_ENHANCED,
    }[tier] / 1000  # convert ms to seconds

    print(f"[sampler:{tier}] Started — interval {interval}s")

    while True:
        # Only sample when trip is active
        # Exception: always sample critical for trip detection
        if not trip_manager.trip_active and tier != "critical":
            await asyncio.sleep(IDLE_POLL_INTERVAL / 1000)
            continue

        if not obd.is_connected():
            await asyncio.sleep(1)
            continue

        for pid_name, pid_def in pids.items():
            # Skip derived PIDs — calculated not queried
            if pid_def["cmd"] is None:
                continue

            result = obd.query(pid_name)

            if result:
                # Update shared sensor state
                sensor_state.update(pid_name, result)

                # Build and buffer row
                row = build_row(
                    trip_manager    = trip_manager,
                    decoded_values  = sensor_state.get_all(),
                    sample_tier     = tier,
                    raw_pid         = pid_def["cmd"],
                    raw_response    = result["raw"],
                    decode_status   = result["status"],
                )
                log_buffer.add(row)

        await asyncio.sleep(interval)

async def trip_monitor_task(trip_manager, sensor_state, log_buffer):
    """
    Monitors RPM and speed to manage trip start/end.
    Runs every second regardless of other samplers.
    Also triggers buffer flush on trip end.
    """
    print("[trip] Monitor started")

    while True:
        rpm   = sensor_state.get("rpm")
        speed = sensor_state.get("vehicle_speed_kph")

        was_active = trip_manager.trip_active
        trip_manager.update(rpm, speed)

        # Trip just ended — flush buffer immediately
        if was_active and not trip_manager.trip_active:
            print("[trip] Flushing buffer on trip end")
            log_buffer.flush()

        await asyncio.sleep(1)

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
    Full boot sequence.
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

    # 3. Connect to iCar Pro with retry
    print("[boot] Connecting to iCar Pro...")
    connected = False
    for attempt in range(1, BLE_RETRY_LIMIT + 1):
        print(f"[boot] Attempt {attempt}/{BLE_RETRY_LIMIT}")
        if obd.connect():
            connected = True
            break
        await asyncio.sleep(3)

    if not connected:
        print("[boot] ⚠ Could not connect to iCar Pro")
        print("[boot] Will retry in connection monitor")

    # 4. Run PID probe on first boot
    if connected and obd.probe_needed():
        print("[boot] First boot — running PID probe")
        print("[boot] Engine must be running for probe")
        await asyncio.sleep(2)  # brief pause before probe
        results = obd.run_pid_probe()
        supported = sum(1 for v in results.values() if v == "ok")
        print(f"[boot] Probe complete: "
              f"{supported}/{len(results)} PIDs supported")

    # 5. Attempt initial WiFi upload of any pending files
    print("[boot] Checking for pending uploads...")
    upload_pending(wifi_manager, log_buffer.log_file)

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
    tasks = [
        asyncio.create_task(
            sampler_task(obd, trip_manager, log_buffer,
                        sensor_state, "critical")
        ),
        asyncio.create_task(
            sampler_task(obd, trip_manager, log_buffer,
                        sensor_state, "standard")
        ),
        asyncio.create_task(
            sampler_task(obd, trip_manager, log_buffer,
                        sensor_state, "slow")
        ),
        asyncio.create_task(
            sampler_task(obd, trip_manager, log_buffer,
                        sensor_state, "enhanced")
        ),
        asyncio.create_task(
            trip_monitor_task(trip_manager, sensor_state,
                             log_buffer)
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
    except Exception as e:
        print(f"[main] Task error: {e}")
        # Flush buffer before any crash
        log_buffer.flush()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
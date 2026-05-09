# ============================================================
# obd.py — BLE Communication Layer
# Handles iCar Pro BLE connection and ELM327 protocol
# ============================================================

import bluetooth
import time
import json
from micropython import const
from config import (
    ICAR_DEVICE_NAME_IOS,
    ICAR_DEVICE_NAME_ANDROID,
    BLE_SCAN_TIMEOUT,
    BLE_CONNECT_TIMEOUT,
    BLE_RETRY_LIMIT,
    ICAR_SERVICE_UUID,
    ICAR_WRITE_CHAR_UUID,
    ICAR_NOTIFY_CHAR_UUID,
)
from pids import QUERYABLE_PIDS, ENHANCED_PIDS
from decoder import decode, RESPONSE_UNSUPPORTED

# BLE IRQ event codes
_IRQ_SCAN_RESULT        = const(5)
_IRQ_SCAN_DONE          = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_SERVICE_RESULT  = const(9)
_IRQ_GATTC_SERVICE_DONE    = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE   = const(12)
_IRQ_GATTC_NOTIFY       = const(18)
_IRQ_GATTC_WRITE_DONE   = const(17)

# ELM327 response terminator
ELM_PROMPT = b">"

# PID probe results file
PID_PROBE_FILE = "/logs/pid_probe.json"

# AT commands sent on connection in this exact order
AT_INIT_SEQUENCE = [
    b"ATZ\r",        # reset adapter
    b"ATE0\r",       # echo off — stop adapter echoing commands back
    b"ATL0\r",       # linefeeds off — cleaner responses
    b"ATS0\r",       # spaces off — removes spaces from responses
    b"ATH0\r",       # headers off — removes header bytes from response
    b"ATSP0\r",      # auto protocol — let adapter detect CAN protocol
    b"ATAT1\r",      # adaptive timing mode 1 — better for modern cars
    b"ATST32\r",     # timeout 200ms — enough for XC90 ECU response
]

# Enhanced PID mode commands
AT_ENHANCED_HEADER_VOLVO = b"ATSH7E0\r"  # set header for Volvo ECU
AT_ENHANCED_MODE         = b"ATCAF0\r"   # CAN auto format off for enhanced
AT_STANDARD_MODE         = b"ATCAF1\r"   # CAN auto format on for standard

class OBDClient:
    """
    BLE OBD client for iCar Pro BLE 4.0.
    Manages full connection lifecycle and PID querying.
    """

    def __init__(self):
        self._ble           = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq_handler)

        # Connection state
        self._conn_handle   = None
        self._write_handle  = None
        self._notify_handle = None
        self._connected     = False
        self._connecting    = False

        # Scan state
        self._scan_result   = None
        self._scan_done     = False

        # Response buffer
        self._response_buf  = b""
        self._response_ready = False

        # Service/characteristic discovery
        self._services_done = False
        self._chars_done    = False

        # Supported enhanced PIDs (loaded from probe file)
        self._supported_enhanced = None

        print("[obd] BLE initialised")

    # --------------------------------------------------------
    # IRQ HANDLER — called by BLE stack on all events
    # --------------------------------------------------------

    def _irq_handler(self, event, data):

        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            name = self._parse_adv_name(adv_data)
            if name and (
                ICAR_DEVICE_NAME_IOS in name or
                ICAR_DEVICE_NAME_ANDROID in name
            ):
                self._scan_result = bytes(addr), addr_type
                print(f"[obd] Found: {name} RSSI:{rssi}")

        elif event == _IRQ_SCAN_DONE:
            self._scan_done = True

        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, addr_type, addr = data
            self._conn_handle = conn_handle
            self._connected   = True
            self._connecting  = False
            print(f"[obd] Connected handle:{conn_handle}")

        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            self._connected     = False
            self._conn_handle   = None
            self._write_handle  = None
            self._notify_handle = None
            print("[obd] Disconnected")

        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            if str(uuid) == ICAR_SERVICE_UUID:
                self._service_start = start_handle
                self._service_end   = end_handle

        elif event == _IRQ_GATTC_SERVICE_DONE:
            self._services_done = True

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_handle, value_handle, props, uuid = data
            uuid_str = str(uuid)
            if uuid_str == ICAR_WRITE_CHAR_UUID:
                self._write_handle  = value_handle
            elif uuid_str == ICAR_NOTIFY_CHAR_UUID:
                self._notify_handle = value_handle

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            self._chars_done = True

        elif event == _IRQ_GATTC_NOTIFY:
            conn_handle, value_handle, notify_data = data
            if value_handle == self._notify_handle:
                self._response_buf += bytes(notify_data)
                # ELM327 signals end of response with ">"
                if ELM_PROMPT in self._response_buf:
                    self._response_ready = True

    # --------------------------------------------------------
    # BLE ADVERTISEMENT NAME PARSER
    # --------------------------------------------------------

    def _parse_adv_name(self, adv_data):
        """
        Extract device name from BLE advertisement payload.
        Handles both complete (0x09) and shortened (0x08) name types.
        """
        i = 0
        while i < len(adv_data):
            length = adv_data[i]
            if length == 0:
                break
            ad_type = adv_data[i + 1]
            if ad_type in (0x08, 0x09):  # shortened or complete name
                try:
                    return adv_data[i + 2:i + 1 + length].decode("utf-8")
                except Exception:
                    return None
            i += 1 + length
        return None

    # --------------------------------------------------------
    # SCAN
    # --------------------------------------------------------

    def scan(self):
        """
        Scan for iCar Pro BLE device.
        Returns (addr, addr_type) if found, None if timed out.
        """
        print("[obd] Scanning for iCar Pro...")
        self._scan_result = None
        self._scan_done   = False

        # Scan params: interval=50ms, window=30ms, active scan
        self._ble.gap_scan(
            BLE_SCAN_TIMEOUT * 1000,  # duration ms
            50000,                     # interval us
            30000,                     # window us
            True                       # active scan
        )

        start = time.time()
        while not self._scan_done:
            if self._scan_result:
                self._ble.gap_scan(None)  # stop scan
                return self._scan_result
            if (time.time() - start) > BLE_SCAN_TIMEOUT:
                self._ble.gap_scan(None)
                print("[obd] Scan timed out — iCar Pro not found")
                return None
            time.sleep(0.1)

        if self._scan_result:
            return self._scan_result

        print("[obd] iCar Pro not found in scan")
        return None

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    def connect(self):
        """
        Full connection sequence:
        1. Scan for device
        2. Connect
        3. Discover services and characteristics
        4. Enable notifications
        5. Run AT init sequence
        Returns True if fully connected and ready, False otherwise.
        """
        scan_result = self.scan()
        if not scan_result:
            return False

        addr, addr_type = scan_result
        print("[obd] Connecting...")
        self._connecting = True
        self._ble.gap_connect(addr_type, addr)

        # Wait for connection
        start = time.time()
        while self._connecting:
            if (time.time() - start) > BLE_CONNECT_TIMEOUT:
                print("[obd] Connection timed out")
                return False
            time.sleep(0.1)

        if not self._connected:
            return False

        # Discover services
        if not self._discover_services():
            return False

        # Discover characteristics
        if not self._discover_characteristics():
            return False

        # Enable notifications on notify characteristic
        self._enable_notifications()

        # Run AT init sequence
        if not self._run_init():
            return False

        # Load supported enhanced PIDs
        self._supported_enhanced = self._load_pid_probe()

        print("[obd] Ready for OBD queries")
        return True

    # --------------------------------------------------------
    # SERVICE AND CHARACTERISTIC DISCOVERY
    # --------------------------------------------------------

    def _discover_services(self):
        self._services_done = False
        self._service_start = None
        self._service_end   = None

        self._ble.gattc_discover_services(self._conn_handle)

        start = time.time()
        while not self._services_done:
            if (time.time() - start) > BLE_CONNECT_TIMEOUT:
                print("[obd] Service discovery timed out")
                return False
            time.sleep(0.1)

        if self._service_start is None:
            print("[obd] iCar service UUID not found")
            return False

        print(f"[obd] Service found: "
              f"{self._service_start}-{self._service_end}")
        return True

    def _discover_characteristics(self):
        self._chars_done    = False
        self._write_handle  = None
        self._notify_handle = None

        self._ble.gattc_discover_characteristics(
            self._conn_handle,
            self._service_start,
            self._service_end
        )

        start = time.time()
        while not self._chars_done:
            if (time.time() - start) > BLE_CONNECT_TIMEOUT:
                print("[obd] Characteristic discovery timed out")
                return False
            time.sleep(0.1)

        if self._write_handle is None or self._notify_handle is None:
            print("[obd] Required characteristics not found")
            return False

        print(f"[obd] Write:{self._write_handle} "
              f"Notify:{self._notify_handle}")
        return True

    def _enable_notifications(self):
        """
        Write to CCCD (Client Characteristic Configuration Descriptor)
        to enable notifications from the iCar Pro.
        """
        # CCCD is always at notify_handle + 1
        cccd_handle = self._notify_handle + 1
        self._ble.gattc_write(
            self._conn_handle,
            cccd_handle,
            b"\x01\x00",  # enable notifications
            1             # with response
        )
        time.sleep(0.1)
        print("[obd] Notifications enabled")

    # --------------------------------------------------------
    # AT INITIALISATION
    # --------------------------------------------------------

    def _run_init(self):
        """
        Send AT init sequence to ELM327.
        ATZ (reset) takes longer — handled separately.
        Returns True if all commands acknowledged.
        """
        print("[obd] Running AT init sequence...")

        for cmd in AT_INIT_SEQUENCE:
            response = self._send_at(cmd)
            if response is None:
                print(f"[obd] No response to {cmd}")
                return False
            print(f"[obd] {cmd.strip()} → {response.strip()}")
            # ATZ returns firmware version, others return "OK"
            time.sleep(0.1)

        print("[obd] AT init complete")
        return True

    # --------------------------------------------------------
    # RAW SEND / RECEIVE
    # --------------------------------------------------------

    def _send_raw(self, data):
        """Write bytes to ELM327 write characteristic."""
        if not self._connected or self._write_handle is None:
            return False
        try:
            self._ble.gattc_write(
                self._conn_handle,
                self._write_handle,
                data,
                0  # without response — faster
            )
            return True
        except Exception as e:
            print(f"[obd] Write error: {e}")
            return False

    def _wait_response(self, timeout=2.0):
        """
        Wait for complete ELM327 response (ends with '>').
        Returns decoded string or None on timeout.
        """
        self._response_buf   = b""
        self._response_ready = False

        start = time.time()
        while not self._response_ready:
            if (time.time() - start) > timeout:
                print("[obd] Response timeout")
                return None
            time.sleep(0.02)

        # Strip prompt and decode
        raw = self._response_buf.replace(b">", b"").decode(
            "utf-8", "ignore"
        ).strip()
        return raw

    def _send_at(self, cmd, timeout=3.0):
        """Send AT command and return response string."""
        self._send_raw(cmd)
        return self._wait_response(timeout)

    # --------------------------------------------------------
    # PID QUERY
    # --------------------------------------------------------

    def query(self, pid_name):
        """
        Query a single PID by name.
        Handles enhanced PID mode switching automatically.
        Returns decoded result dict from decoder.py.
        """
        if not self._connected:
            return None

        pid_def = QUERYABLE_PIDS.get(pid_name)
        if not pid_def:
            return None

        cmd = pid_def["cmd"]

        # Switch to enhanced mode for Volvo PIDs
        is_enhanced = pid_name in ENHANCED_PIDS
        if is_enhanced:
            self._send_at(AT_ENHANCED_HEADER_VOLVO)
            self._send_at(AT_ENHANCED_MODE)

        # Send PID command
        self._send_raw((cmd + "\r").encode())
        raw_response = self._wait_response()

        # Switch back to standard mode
        if is_enhanced:
            self._send_at(AT_STANDARD_MODE)

        if raw_response is None:
            raw_response = "NO DATA"

        return decode(pid_name, cmd, raw_response)

    def query_batch(self, pid_names):
        """
        Query multiple PIDs in sequence.
        Returns dict of pid_name → decode result.
        Skips PIDs known to be unsupported on this ECU.
        """
        results = {}
        for pid_name in pid_names:
            # Skip enhanced PIDs known unsupported on this ECU
            if (pid_name in ENHANCED_PIDS and
                    self._supported_enhanced is not None and
                    pid_name not in self._supported_enhanced):
                continue
            result = self.query(pid_name)
            if result:
                results[pid_name] = result
            time.sleep(0.05)  # small gap between queries
        return results

    # --------------------------------------------------------
    # FIRST BOOT PID PROBE
    # --------------------------------------------------------

    def run_pid_probe(self):
        """
        Test all enhanced PIDs against this specific ECU.
        Saves results to PID_PROBE_FILE.
        Should run once on first boot with engine running.
        Returns dict of {pid_name: "ok" | "unsupported" | "error"}
        """
        print("[obd] Running enhanced PID probe...")
        results = {}

        for pid_name, pid_def in ENHANCED_PIDS.items():
            if pid_def["cmd"] is None:
                results[pid_name] = "derived"
                continue

            result = self.query(pid_name)
            if result is None:
                results[pid_name] = "error"
            elif result["status"] == "ok":
                results[pid_name] = "ok"
                print(f"[obd] ✓ {pid_name}: {result['value']}"
                      f" {result['unit']}")
            elif result["status"] == RESPONSE_UNSUPPORTED:
                results[pid_name] = "unsupported"
                print(f"[obd] ✗ {pid_name}: unsupported")
            else:
                results[pid_name] = result["status"]
                print(f"[obd] ? {pid_name}: {result['status']}")

            time.sleep(0.2)

        # Save results
        try:
            with open(PID_PROBE_FILE, "w") as f:
                json.dump(results, f)
            print(f"[obd] Probe saved → {PID_PROBE_FILE}")
        except Exception as e:
            print(f"[obd] Probe save error: {e}")

        self._supported_enhanced = {
            k for k, v in results.items() if v == "ok"
        }
        return results

    def _load_pid_probe(self):
        """
        Load saved PID probe results.
        Returns set of supported enhanced PID names.
        Returns None if probe has never been run.
        """
        try:
            with open(PID_PROBE_FILE, "r") as f:
                results = json.load(f)
            supported = {k for k, v in results.items() if v == "ok"}
            print(f"[obd] Loaded probe: "
                  f"{len(supported)} enhanced PIDs supported")
            return supported
        except Exception:
            print("[obd] No probe file — will run on first boot")
            return None

    def probe_needed(self):
        """Returns True if PID probe has never been run."""
        try:
            open(PID_PROBE_FILE, "r").close()
            return False
        except Exception:
            return True

    # --------------------------------------------------------
    # CONNECTION MANAGEMENT
    # --------------------------------------------------------

    def disconnect(self):
        """Cleanly disconnect from iCar Pro."""
        if self._conn_handle is not None:
            try:
                self._ble.gap_disconnect(self._conn_handle)
            except Exception:
                pass
        self._connected   = False
        self._conn_handle = None
        print("[obd] Disconnected")

    def is_connected(self):
        return self._connected

    def reconnect(self):
        """
        Attempt reconnection up to BLE_RETRY_LIMIT times.
        Returns True if reconnected successfully.
        """
        for attempt in range(1, BLE_RETRY_LIMIT + 1):
            print(f"[obd] Reconnect attempt {attempt}/"
                  f"{BLE_RETRY_LIMIT}...")
            if self.connect():
                return True
            time.sleep(2)
        print("[obd] Reconnection failed")
        return False
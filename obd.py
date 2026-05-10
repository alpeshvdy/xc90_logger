# ============================================================
# obd.py — BLE Communication Layer
# Handles iCar Pro BLE connection and ELM327 protocol
# ============================================================

import bluetooth
import time
from micropython import const
from config import (
    BLE_CONNECT_TIMEOUT,
    BLE_RETRY_LIMIT,
    ICAR_SERVICE_UUID,
    ICAR_WRITE_CHAR_UUID,
    ICAR_NOTIFY_CHAR_UUID,
    KNOWN_ICAR_PRO_MACS,
    OBD_SCAN_SERVICE_UUIDS,
    BLE_PROBE_SCAN_TIME,
    BLE_PROBE_PER_DEVICE_TIMEOUT,
    BLE_PROBE_MAX_DEVICES,
)
from pids import QUERYABLE_PIDS
from decoder import decode

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

# No enhanced PIDs — all Mode 01 standard OBD-II
# Removes the mode-switching that was causing ELM327 corruption

# Standard ELM327 BLE UUIDs (used by most non-iCar OBD adapters)
STD_OBD_SERVICE_UUID    = "0000fff0-0000-1000-8000-00805f9b34fb"
STD_OBD_WRITE_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
STD_OBD_NOTIFY_CHAR_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"

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

        # Response buffer
        self._response_buf  = b""
        self._response_ready = False

        # Service/characteristic discovery
        self._services_done = False
        self._chars_done    = False

        # ELM327 recovery: track consecutive NO DATA responses
        self._nodata_streak = 0
        self._max_nodata_before_reset = 5

        print("[obd] BLE initialised")

    # --------------------------------------------------------
    # IRQ HANDLER — called by BLE stack on all events
    # --------------------------------------------------------

    def _irq_handler(self, event, data):

        if event == _IRQ_PERIPHERAL_CONNECT:
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
            uuid_str = str(uuid)
            print("[obd] Service discovered: %s  handle:%d-%d" % (uuid_str, start_handle, end_handle))
            # Match iCar (0x18F0), standard ELM327 (0xFFF0), and any OBD-like service
            is_obd_service = (
                uuid_str == ICAR_SERVICE_UUID or
                uuid_str == STD_OBD_SERVICE_UUID or
                '18f0' in uuid_str.lower() or
                'fff0' in uuid_str.lower()
            )
            if is_obd_service:
                self._service_start = start_handle
                self._service_end   = end_handle

        elif event == _IRQ_GATTC_SERVICE_DONE:
            self._services_done = True

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_handle, value_handle, props, uuid = data
            uuid_str = str(uuid)
            print("[obd] Char found: %s  handle:%d  props:%d" % (uuid_str, value_handle, props))
            # Match iCar write char (0x2AF1) and standard ELM327 write char (0xFFF1)
            matched = False
            if (uuid_str in (ICAR_WRITE_CHAR_UUID, STD_OBD_WRITE_CHAR_UUID) or
                '2af1' in uuid_str.lower() or 'fff1' in uuid_str.lower()):
                self._write_handle  = value_handle
                print("[obd]   → matched WRITE char")
                matched = True
            elif (uuid_str in (ICAR_NOTIFY_CHAR_UUID, STD_OBD_NOTIFY_CHAR_UUID) or
                  '2af0' in uuid_str.lower() or 'fff2' in uuid_str.lower()):
                self._notify_handle = value_handle
                print("[obd]   → matched NOTIFY char")
                matched = True
            if not matched:
                print("[obd]   (no config match - props:%d)" % props)

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
    # DIRECT MAC CONNECTION
    # --------------------------------------------------------

    def _connect_mac(self):
        """
        Connect directly to iCar Pro using known MAC addresses.
        Iterates KNOWN_ICAR_PRO_MACS, attempting connection to each.
        Returns True if connected, False if all MACs fail.
        """
        print("[obd] Connecting to iCar Pro via known MAC addresses...")

        for idx, known_mac in enumerate(KNOWN_ICAR_PRO_MACS):
            addr = bytes(known_mac)
            addr_str = ':'.join('%02X' % b for b in addr)
            print("[obd] Attempt %d/%d — MAC: %s" % (idx + 1, len(KNOWN_ICAR_PRO_MACS), addr_str))

            self._connecting = True
            self._ble.gap_connect(1, addr)  # addr_type=1 (random — most BLE OBD adapters)

            start = time.time()
            while self._connecting and (time.time() - start) < BLE_CONNECT_TIMEOUT:
                time.sleep(0.1)

            if self._connected:
                print("[obd] Connected via MAC: %s" % addr_str)
                return True
            else:
                print("[obd] MAC %s unreachable" % addr_str)

        print("[obd] All known MAC addresses failed")
        return False

    # --------------------------------------------------------
    # CONNECTION HELPERS
    # --------------------------------------------------------

    def _try_connect_addr(self, addr_bytes, addr_type, timeout=None):
        """Connect to a BLE address. Returns True if connected."""
        if timeout is None:
            timeout = BLE_CONNECT_TIMEOUT

        addr_str = ":".join("%02X" % b for b in addr_bytes)
        self._connecting = True
        self._ble.gap_connect(addr_type, addr_bytes)

        start = time.time()
        while self._connecting and (time.time() - start) < timeout:
            time.sleep(0.1)

        if self._connected:
            print(f"[obd] Connected: {addr_str}")
            return True
        return False

    # --------------------------------------------------------
    # TIER 1 — SERVICE UUID SCAN
    # --------------------------------------------------------

    def _scan_for_obd_by_service(self, scan_time=5):
        """
        Scan BLE advertisements for OBD service UUIDs.
        Parses AD structures for 16-bit service UUIDs matching
        OBD_SCAN_SERVICE_UUIDS (0xFFF0, 0xFFE0, 0x18F0).
        Returns list of (addr_bytes, addr_type, rssi, uuid16)
        sorted by strongest signal first.
        """
        candidates = []
        scan_done = False

        def _scan_cb(event, data):
            nonlocal scan_done
            if event == _IRQ_SCAN_RESULT:
                addr_type, addr, adv_type, rssi, adv_data = data
                if isinstance(adv_data, memoryview):
                    adv_data = bytes(adv_data)
                # Parse AD structures for 16-bit service UUIDs
                i = 0
                while i < len(adv_data) - 1:
                    length = adv_data[i]
                    if length == 0 or i + length >= len(adv_data):
                        break
                    ad_type = adv_data[i + 1]
                    if ad_type in (0x02, 0x03):  # 16-bit UUID list
                        data_start = i + 2
                        for j in range(0, length - 1, 2):
                            pos = data_start + j
                            if pos + 1 < len(adv_data):
                                uuid16 = adv_data[pos] | (adv_data[pos + 1] << 8)
                                if uuid16 in OBD_SCAN_SERVICE_UUIDS:
                                    addr_bytes = bytes(addr)
                                    # Deduplicate by address
                                    if not any(c[0] == addr_bytes for c in candidates):
                                        candidates.append((addr_bytes, addr_type, rssi, uuid16))
                                        addr_str = ":".join("%02X" % b for b in addr_bytes)
                                        print(f"[obd] OBD candidate: 0x{uuid16:04X} at {addr_str} RSSI:{rssi}")
                    i += length + 1
            elif event == _IRQ_SCAN_DONE:
                scan_done = True

        self._ble.irq(_scan_cb)
        self._ble.gap_scan(scan_time * 1000, 30000, 30000)

        start = time.time()
        while not scan_done and (time.time() - start) < scan_time + 3:
            time.sleep(0.1)

        self._ble.irq(self._irq_handler)  # Restore main handler
        candidates.sort(key=lambda c: c[2], reverse=True)  # Strongest RSSI first
        return candidates

    # --------------------------------------------------------
    # TIER 3 HELPERS — CONNECT & PROBE
    # --------------------------------------------------------

    def _scan_all_devices(self, scan_time=8):
        """
        Scan for all BLE devices.
        Returns list of (addr_bytes, addr_type, rssi) sorted by RSSI.
        """
        devices = []
        scan_done = False

        def _scan_cb(event, data):
            nonlocal scan_done
            if event == _IRQ_SCAN_RESULT:
                addr_type, addr, adv_type, rssi, adv_data = data
                addr_bytes = bytes(addr)
                if not any(d[0] == addr_bytes for d in devices):
                    devices.append((addr_bytes, addr_type, rssi))
            elif event == _IRQ_SCAN_DONE:
                scan_done = True

        self._ble.irq(_scan_cb)
        self._ble.gap_scan(scan_time * 1000, 30000, 30000)

        start = time.time()
        while not scan_done and (time.time() - start) < scan_time + 3:
            time.sleep(0.1)

        self._ble.irq(self._irq_handler)
        devices.sort(key=lambda d: d[2], reverse=True)
        return devices

    def _connect_and_probe_device(self, addr_bytes, addr_type):
        """
        Connect to a device, discover services/characteristics,
        send ATZ, and check if it responds like an ELM327.
        If confirmed OBD: returns True (connection stays open).
        If not: cleanly disconnects and returns False.
        """
        addr_str = ":".join("%02X" % b for b in addr_bytes)
        print(f"[obd] Probing {addr_str}...")

        if not self._try_connect_addr(addr_bytes, addr_type,
                                      BLE_PROBE_PER_DEVICE_TIMEOUT):
            return False

        # Discover services
        if not self._discover_services():
            print(f"[obd]   no OBD service — skipping")
            self._ble.gap_disconnect(self._conn_handle)
            time.sleep(0.3)
            return False

        # Discover characteristics
        if not self._discover_characteristics():
            print(f"[obd]   no OBD characteristics — skipping")
            self._ble.gap_disconnect(self._conn_handle)
            time.sleep(0.3)
            return False

        # Enable notifications
        self._enable_notifications()

        # Send ATZ and check for ELM327 response
        self._send_raw(b"ATZ\r")
        response = self._wait_response(timeout=3.0)

        if response and ("ELM327" in response.upper() or
                         "OK" in response.upper()):
            print(f"[obd]   -> Confirmed OBD: {response[:50]}")
            return True

        print(f"[obd]   not an OBD adapter (response: {response[:30] if response else 'none'})")
        self._ble.gap_disconnect(self._conn_handle)
        time.sleep(0.3)
        return False

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    def connect(self):
        """
        Three-tier OBD auto-discovery:
        Tier 1: Scan ads for OBD service UUIDs (fast, no connection needed)
        Tier 2: Try known MAC addresses (reliable fallback)
        Tier 3: Connect-and-probe all nearby devices (slow, universal)
        Returns True if fully connected and ready, False otherwise.
        """
        # Reset discovery state (prevents leak from previous failed connect calls)
        self._services_done = False
        self._chars_done = False

        # Tier 1: Service UUID scan in advertisements
        print("[obd] Tier 1: Scanning for OBD service UUIDs...")
        candidates = self._scan_for_obd_by_service()
        for addr_bytes, addr_type, rssi, uuid16 in candidates:
            if self._try_connect_addr(addr_bytes, addr_type):
                break

        # Tier 2: Known MAC addresses
        if not self._connected:
            print("[obd] Tier 2: Trying known MAC addresses...")
            self._connect_mac()

        # Tier 3: Connect-and-probe all devices
        if not self._connected:
            print("[obd] Tier 3: Scanning all devices and probing each...")
            devices = self._scan_all_devices(BLE_PROBE_SCAN_TIME)
            for addr_bytes, addr_type, rssi in devices[:BLE_PROBE_MAX_DEVICES]:
                if self._connect_and_probe_device(addr_bytes, addr_type):
                    # Tier 3 already did ATZ — run rest of init
                    if not self._run_init_rest():
                        try:
                            self._ble.gap_disconnect(self._conn_handle)
                        except Exception:
                            pass
                        self._connected = False
                        self._conn_handle = None
                        return False
                    break

        if not self._connected:
            print("[obd] All tiers failed — no OBD adapter found")
            return False

        # For Tier 1 and Tier 2: discover services/characteristics and run AT init
        if not self._chars_done:
            if not self._discover_services():
                return False
            if not self._discover_characteristics():
                return False
            self._enable_notifications()
            if not self._run_init():
                return False

        print("[obd] Ready for OBD queries")
        return True

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
            # Handle single-characteristic devices (FFE1 used for both write and notify)
            if self._write_handle is not None and self._notify_handle is None:
                print("[obd] Single char device - using write handle for notify")
                self._notify_handle = self._write_handle
            else:
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

    def _run_init_rest(self):
        """
        Run remaining AT init commands (skipping ATZ which was
        already sent during Tier 3 connect-and-probe).
        Returns True if all commands acknowledged.
        """
        print("[obd] Running remaining AT init...")
        for cmd in AT_INIT_SEQUENCE[1:]:  # Skip ATZ
            response = self._send_at(cmd)
            if response is None:
                print(f"[obd] No response to {cmd}")
                return False
            print(f"[obd] {cmd.strip()} -> {response.strip()}")
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
        Query a single PID by name (Mode 01 only).
        Includes ELM327 recovery: resets adapter if 5 consecutive
        NO DATA responses suggest corrupt adapter state.
        After ATZ reset, re-runs AT init sequence to restore
        echo-off, headers-off, spaces-off state.
        Returns decoded result dict from decoder.py.
        """
        if not self._connected:
            return None

        pid_def = QUERYABLE_PIDS.get(pid_name)
        if not pid_def:
            return None

        cmd = pid_def["cmd"]

        # Send PID command (Mode 01 — no mode switching needed)
        self._send_raw((cmd + "\r").encode())
        raw_response = self._wait_response()

        if raw_response is None:
            raw_response = "NO DATA"

        # Track NO DATA streak for ELM327 recovery
        if "NO DATA" in raw_response.upper():
            self._nodata_streak += 1
            if self._nodata_streak >= self._max_nodata_before_reset:
                print("[obd] %d consecutive NO DATA — resetting ELM327" % self._nodata_streak)
                # _run_init() sends ATZ + all config — single clean reset
                if self._run_init():
                    print("[obd] ELM327 reset + re-init successful")
                else:
                    print("[obd] ELM327 re-init failed — may need disconnect")
                self._nodata_streak = 0
                raw_response = "NO DATA (adapter reset)"
        else:
            self._nodata_streak = 0

        return decode(pid_name, cmd, raw_response)

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
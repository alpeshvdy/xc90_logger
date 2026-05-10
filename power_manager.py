# ============================================================
# power_manager.py -- Deep Sleep & Wake Management
#
# WAKE_MODE = 'tja1145':
#   TJA1145 CAN transceiver INH pin controls ESP32 power.
#   When CAN is silent → INH floats → buck disabled → ESP32 HARD OFF.
#   Any CAN activity → TJA1145 drives INH HIGH → buck enabled → ESP32 boots.
#   ~5µA standby, ESP32 zero power when parked.
#
# WAKE_MODE = 'timer':
#   RTC timer wakes every SLEEP_WAKE_INTERVAL_MS.
#   Quick 3s BLE scan for iCar Pro → full boot if found, back to sleep if not.
#
# WAKE_MODE = 'reed':
#   GPIO ext0 wake from reed switch on door.
#   ESP32 sleeps forever until door opens.
#
# WAKE_MODE = 'none':
#   Never sleep (always-on, ~1355 mAh/day).
#
# ============================================================

import machine
import esp32
from config import (
    WAKE_MODE,
    TJA1145_INH_GPIO,
    TJA1145_STBY_GPIO,
    TJA1145_INT_GPIO,
    SLEEP_AFTER_IDLE_MS,
    SLEEP_WAKE_INTERVAL_MS,
)

# RTC magic bytes for non-TJA1145 wake cause detection
_RTC_MAGIC_TIMER = b'XC91'
_RTC_MAGIC_GPIO   = b'XC92'
_RTC_MAGIC_BOTH   = b'XC93'


# =============================================================================
# Public helpers — import these directly from power_manager
# =============================================================================

def detect_boot_cause():
    pm = PowerManager()
    return pm._detect()


def boot_cause_label(cause):
    labels = {
        'cold':    'Cold boot (power-on)',
        'timer':   'Timer wake (5 min interval)',
        'reed':    'Door reed switch wake',
        'both':    'Timer + reed combined wake',
        'tja1145': 'TJA1145 CAN activity wake',
    }
    return labels.get(cause, 'Unknown ({})'.format(cause))


def tja1145_init():
    pm = PowerManager()
    pm._init_tja1145()


# =============================================================================
# PowerManager
# =============================================================================

class PowerManager:
    def __init__(self):
        self.mode = WAKE_MODE

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def enter_sleep(self):
        if self.mode == 'tja1145':
            # Cut power via TJA1145 (INH → input lets TJA1145 control buck EN).
            # ESP32 then enters deep sleep. TJA1145 monitors CAN independently
            # (~5µA) and drives INH HIGH when CAN activity is detected,
            # re-enabling the buck converter to power the ESP32 back on.
            self._tja1145_power_off()
            # Enter deep sleep while TJA1145 monitors CAN.
            # SLEEP_WAKE_INTERVAL_MS is a fallback wake timer in case
            # TJA1145 INH doesn't wake the ESP32 (e.g. wiring issue).
            print('[power] ESP32 deep sleeping — TJA1145 monitoring CAN')
            machine.deepsleep(SLEEP_WAKE_INTERVAL_MS)
            return  # never reached

        if self.mode == 'reed':
            magic = _RTC_MAGIC_GPIO
        elif self.mode == 'both':
            magic = _RTC_MAGIC_BOTH
        else:
            magic = _RTC_MAGIC_TIMER

        self._write_rtc_memory(magic)

        if self.mode == 'reed':
            print('[power] Deep sleep (reed wake, GPIO ext0)')
            # Configure ext0 wake before sleeping
            import config
            pin = machine.Pin(config.REED_GPIO_PIN, machine.Pin.IN)
            esp32.wake_on_ext0(pin=pin, level=config.REED_WAKE_LEVEL)
            machine.deepsleep(0)
        elif self.mode in ('timer', 'both'):
            print('[power] Deep sleep (timer, {}ms)'.format(SLEEP_WAKE_INTERVAL_MS))
            machine.deepsleep(SLEEP_WAKE_INTERVAL_MS)
        else:
            print('[power] Sleep disabled (WAKE_MODE=none)')

    def should_full_boot(self, wake_cause, obd_client=None):
        if self.mode == 'tja1145':
            return True  # TJA1145 only wakes on real CAN activity
        if wake_cause == 'cold':
            return True
        if wake_cause in ('timer', 'both') and obd_client:
            try:
                print('[power] Wake detected -- quick BLE scan for iCar Pro...')
                found = obd_client.quick_scan(timeout=3)
                if found:
                    print('[power] iCar Pro found -- proceeding with full boot')
                    return True
                else:
                    print('[power] iCar Pro not found -- returning to sleep')
                    return False
            except Exception as e:
                print('[power] BLE scan error: {} -- proceeding with full boot'.format(e))
                return True
        return True

    def should_sleep(self, trip_manager, engine_off_ms):
        if self.mode == 'none':
            return False
        if SLEEP_AFTER_IDLE_MS <= 0:
            return False
        if trip_manager.trip_active:
            return False
        return engine_off_ms >= SLEEP_AFTER_IDLE_MS

    # -------------------------------------------------------------------------
    # Internal: wake cause detection
    # -------------------------------------------------------------------------

    def _detect(self):
        if self.mode == 'tja1145':
            return 'tja1145'
        magic = self._read_rtc_memory()
        if magic == _RTC_MAGIC_TIMER:
            return 'timer'
        elif magic == _RTC_MAGIC_GPIO:
            return 'reed'
        elif magic == _RTC_MAGIC_BOTH:
            return 'both'
        return 'cold'

    # -------------------------------------------------------------------------
    # TJA1145 — INH-based hard power-off
    # -------------------------------------------------------------------------

    def _init_tja1145(self):
        try:
            # Drive STBY HIGH to put TJA1145 in normal operating mode
            stby = machine.Pin(TJA1145_STBY_GPIO, machine.Pin.OUT)
            stby.value(1)
            print('[power] TJA1145 STBY = HIGH (normal mode)')

            # Configure INT pin as input (optional diagnostics)
            try:
                int_pin = machine.Pin(TJA1145_INT_GPIO, machine.Pin.IN)
                print('[power] TJA1145 INT pin configured (GPIO{})'.format(TJA1145_INT_GPIO))
            except Exception:
                pass

            # Release INH pin — let TJA1145 take full control of buck enable.
            # INH is open-drain on TJA1145, so setting ESP32 pin to INPUT
            # allows TJA1145 to drive it LOW (CAN silent) or HIGH (CAN active).
            inh = machine.Pin(TJA1145_INH_GPIO, machine.Pin.IN)
            print('[power] TJA1145 INH released (GPIO{} → INPUT)'.format(TJA1145_INH_GPIO))
        except Exception as e:
            print('[power] TJA1145 init error: {}'.format(e))

    def _tja1145_power_off(self):
        # Prepare INH pin for TJA1145 open-drain control.
        # In normal mode (STBY=HIGH), TJA1145 drives INH HIGH.
        # Setting ESP32 INH pin to INPUT allows TJA1145 to control it.
        # The actual power cut to ESP32 comes from machine.deepsleep()
        # (VCC removed), not from this function. The TJA1145 continues
        # monitoring CAN independently and drives INH HIGH to wake ESP32.
        try:
            inh = machine.Pin(TJA1145_INH_GPIO, machine.Pin.IN)
            print('[power] TJA1145 INH released — ESP32 entering deep sleep')
            print('[power] TJA1145 monitoring CAN (~5µA standby)')
        except Exception as e:
            print('[power] Failed to configure TJA1145 INH: {}'.format(e))
            self._fallback_deepsleep()

    def _fallback_deepsleep(self):
        print('[power] TJA1145 fallback — entering regular deep sleep')
        machine.deepsleep(SLEEP_WAKE_INTERVAL_MS)

    # -------------------------------------------------------------------------
    # RTC Memory Helpers (non-TJA1145 modes only)
    # -------------------------------------------------------------------------

    def _write_rtc_memory(self, magic):
        try:
            rtc_mem = esp32.RTC_SLOW_MEM
            rtc_mem[:len(magic)] = magic
        except Exception as e:
            print('[power] RTC memory write error: {}'.format(e))

    def _read_rtc_memory(self):
        try:
            rtc_mem = esp32.RTC_SLOW_MEM
            return bytes(rtc_mem[:4])
        except Exception:
            return b'\u0000\u0000\u0000\u0000'
# ============================================================
# power_manager.py — Deep Sleep & Wake Management
#
# Handles deep sleep entry and wake-up strategies for the
# XC90 OBD Logger. Supports three wake modes:
#
#   "timer"  — RTC timer wake, quick BLE scan, sleep if car off
#   "reed"   — GPIO ext0 wake from reed switch (door open)
#   "both"   — Reed switch primary + timer fallback
#   "none"   — Never sleep (always-on)
#
# ============================================================

import machine
import esp32
from config import (
    WAKE_MODE,
    REED_GPIO_PIN,
    REED_WAKE_LEVEL,
    SLEEP_WAKE_INTERVAL_MS,
    WAKE_BLE_SCAN_TIMEOUT,
)

# RTC memory layout:
#   [0:4]   Magic bytes identifying last sleep type
#   [4:8]   Sleep counter for diagnostics
_RTC_MAGIC_TIMER = b"XC91"
_RTC_MAGIC_GPIO  = b"XC92"
_RTC_MAGIC_BOTH  = b"XC93"
_RTC_MAGIC_COLD  = b"XC90"


# ============================================================
# Boot Cause Detection
# ============================================================

def detect_boot_cause():
    """
    Determine why the ESP32 just booted.
    Uses a combination of reset_cause() and RTC memory
    to distinguish between cold boot, timer wake, and GPIO wake.

    Returns one of: 'cold', 'timer', 'gpio', 'both'
    """
    cause = machine.reset_cause()

    if cause == machine.PWRON_RESET:
        return "cold"

    if cause == machine.DEEPSLEEP_RESET:
        # Deep sleep wake — check RTC memory for discriminator
        try:
            rtc = machine.RTC()
            mem = rtc.memory()
            if mem[:4] == _RTC_MAGIC_GPIO:
                return "gpio"
            elif mem[:4] == _RTC_MAGIC_BOTH:
                return "both"
            elif mem[:4] == _RTC_MAGIC_TIMER:
                return "timer"
            else:
                return "cold"  # unknown RTC state, treat as cold
        except Exception:
            return "cold"

    # HARD_RESET, WDT_RESET, SOFT_RESET — treat as cold
    return "cold"


def _write_rtc_magic(magic):
    """Write magic bytes + counter to RTC memory before sleep."""
    try:
        rtc = machine.RTC()
        # Preserve counter if present, otherwise start at 0
        old = rtc.memory()
        counter = 0
        if len(old) >= 8:
            try:
                counter = int.from_bytes(old[4:8], "little") + 1
            except Exception:
                counter = 0
        rtc.memory(magic + counter.to_bytes(4, "little"))
    except Exception:
        pass


# ============================================================
# PowerManager
# ============================================================

class PowerManager:
    """
    Manages deep sleep entry based on WAKE_MODE config.

    Usage:
        pm = PowerManager()

        # Check if engine-off timeout has elapsed:
        if pm.should_sleep(trip_manager, engine_off_since):
            pm.enter_sleep()

        # enter_sleep() does not return — the ESP32 resets.
    """

    def __init__(self):
        self.mode = WAKE_MODE

    # ----------------------------------------------------------
    # Sleep decision
    # ----------------------------------------------------------

    def should_sleep(self, trip_manager, engine_off_since_ms):
        """
        Returns True if conditions are met for deep sleep:

        1. WAKE_MODE is not "none"
        2. Engine has been off for >= SLEEP_AFTER_IDLE_MS
        3. Trip is not active
        """
        if self.mode == "none":
            return False

        if trip_manager.trip_active:
            return False

        if engine_off_since_ms < SLEEP_AFTER_IDLE_MS:
            return False

        return True

    # ----------------------------------------------------------
    # Sleep entry
    # ----------------------------------------------------------

    def enter_sleep(self):
        """
        Enter deep sleep with configured wake sources.

        Timer mode:   RTC magic = TIMER, sleep for SLEEP_WAKE_INTERVAL_MS
        Reed mode:    RTC magic = GPIO, sleep forever, wake on GPIO
        Both mode:    RTC magic = GPIO (primary), sleep for interval
                      + GPIO wake on door open

        This method does NOT return — machine.deepsleep()
        resets the ESP32-S3.
        """
        if self.mode == "none":
            return  # Should not reach here, but safety

        # Store magic in RTC memory so next boot knows what to expect.
        if self.mode == "timer":
            _write_rtc_magic(_RTC_MAGIC_TIMER)
        elif self.mode == "reed":
            # Reed-only: sleep forever, GPIO must be the wake source
            _write_rtc_magic(_RTC_MAGIC_GPIO)
        else:
            # "both" mode: can wake from timer OR GPIO —
            # write BOTH magic so next boot knows to BLE-scan first
            _write_rtc_magic(_RTC_MAGIC_BOTH)

        # Configure GPIO wake if using reed switch
        if self.mode in ("reed", "both"):
            self._configure_gpio_wake()

        # Enter deep sleep
        if self.mode == "reed":
            # Sleep forever — wake ONLY on reed switch GPIO
            machine.deepsleep(0)
        else:
            # Timer or both: sleep for configured interval
            machine.deepsleep(SLEEP_WAKE_INTERVAL_MS)

    def _configure_gpio_wake(self):
        """
        Configure the reed switch GPIO as an ext0 wake source.

        ext0 uses a single pin. The ESP32 wakes when the pin
        matches REED_WAKE_LEVEL.

        Reed switch circuit (NO = Normally Open):
            Door CLOSED: magnet holds reed closed → GPIO = LOW
            Door OPENS:  reed opens → pull-up pulls GPIO HIGH → WAKE
        """
        try:
            pin = machine.Pin(
                REED_GPIO_PIN,
                machine.Pin.IN,
                machine.Pin.PULL_UP,
            )
            esp32.wake_on_ext0(pin, REED_WAKE_LEVEL)
        except Exception as e:
            print(f"[power] GPIO wake config failed: {e}")
            # Fall through to timer-only sleep

    # ----------------------------------------------------------
    # Timer-wake BLE scan decision
    # ----------------------------------------------------------

    def should_full_boot(self, wake_cause, obd):
        """
        Called at boot to decide whether to proceed with full boot
        or go straight back to sleep.

        Cold boot   → always full boot
        GPIO wake   → always full boot (door was opened)
        Timer wake  → quick BLE scan → iCar found? → boot : sleep
        Both wake   → quick BLE scan → iCar found? → boot : sleep
                      (can't tell if timer or GPIO, so scan first)
        """
        if wake_cause in ("cold", "gpio"):
            return True

        if wake_cause in ("timer", "both"):
            print("[power] Timer wake — scanning for iCar Pro...")
            found = obd.quick_scan(WAKE_BLE_SCAN_TIMEOUT)
            if found:
                print("[power] iCar Pro found → full boot")
                return True
            else:
                print("[power] iCar Pro not found → back to sleep")
                self.enter_sleep()
                return False  # Never reached (sleep resets)

        return True


# ============================================================
# Module-level convenience
# ============================================================

def boot_cause_label(cause):
    """Human-readable boot cause label."""
    return {
        "cold":  "Cold boot (power-on)","timer":  "Timer wake (RTC alarm)",
        "gpio":   "GPIO wake (reed switch / door open)",
        "both":   "Both-mode wake (timer or GPIO)",
    }.get(cause, f"Unknown ({cause})")

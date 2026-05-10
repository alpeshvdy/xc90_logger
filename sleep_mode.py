# ============================================================
# sleep_mode.py — Deep Sleep & Wake Management
# Survives ESP32 deep sleep via RTC memory (8KB preserved).
# On wake, main.py runs from scratch; this module detects
# sleep-wake vs cold-boot so we can skip full BLE discovery.
# ============================================================

import machine
import time

# RTC memory layout (bytes):
#   [0:7]   Magic bytes: b'XCSLEEP\x00'
#   [8:11]  Idle seconds accumulated (32-bit unsigned, big-endian)
#   [12:15] Last sleep entry timestamp (32-bit unsigned epoch, big-endian)
#   [16]    Flags: bit0 = was_asleep, bit1 = prestart_buffered
RTC_MAGIC = b'XCSLEEP\x00'
RTC_MAGIC_LEN = 8
RTC_OFFSET_IDLE_S  = 8
RTC_OFFSET_SLEEP_TS = 12
RTC_OFFSET_FLAGS    = 16
RTC_TOTAL_LEN       = 17

FLAG_WAS_ASLEEP       = 0x01
FLAG_PRESTART_BUFFERED = 0x02


def _rtc_read():
    """Read RTC memory as bytes. Returns empty bytes if uninitialised."""
    try:
        mem = machine.RTC().memory()
        if isinstance(mem, bytes) and len(mem) >= RTC_TOTAL_LEN:
            return mem
    except Exception:
        pass
    return b''


def _rtc_write(data):
    """Write bytes to RTC memory (survives deep sleep)."""
    try:
        machine.RTC().memory(data)
        return True
    except Exception:
        return False


def _rtc_init():
    """Initialise RTC memory if magic bytes don't match."""
    mem = _rtc_read()
    if mem[:RTC_MAGIC_LEN] != RTC_MAGIC:
        fresh = bytearray(RTC_TOTAL_LEN)
        fresh[:RTC_MAGIC_LEN] = RTC_MAGIC
        fresh[RTC_OFFSET_IDLE_S:RTC_OFFSET_SLEEP_TS] = b'\x00\x00\x00\x00'
        fresh[RTC_OFFSET_SLEEP_TS:RTC_OFFSET_FLAGS] = b'\x00\x00\x00\x00'
        fresh[RTC_OFFSET_FLAGS] = 0
        _rtc_write(bytes(fresh))


# ---- Idle Timer (survives deep sleep) ----


def get_idle_seconds():
    """Return accumulated engine-off seconds from RTC memory."""
    _rtc_init()
    mem = _rtc_read()
    if len(mem) < RTC_OFFSET_SLEEP_TS:
        return 0
    idle = int.from_bytes(mem[RTC_OFFSET_IDLE_S:RTC_OFFSET_SLEEP_TS], 'big')
    return idle


def add_idle_seconds(seconds):
    """Add seconds to the accumulated idle counter in RTC memory."""
    _rtc_init()
    current = get_idle_seconds()
    new_total = current + seconds
    mem = bytearray(_rtc_read())
    mem[RTC_OFFSET_IDLE_S:RTC_OFFSET_SLEEP_TS] = new_total.to_bytes(4, 'big')
    _rtc_write(bytes(mem))
    return new_total


def reset_idle_timer():
    """Reset idle counter to zero (engine started)."""
    _rtc_init()
    mem = bytearray(_rtc_read())
    mem[RTC_OFFSET_IDLE_S:RTC_OFFSET_SLEEP_TS] = b'\x00\x00\x00\x00'
    _rtc_write(bytes(mem))


# ---- Sleep State (flags in RTC) ----


def mark_was_asleep():
    """Set the 'was asleep' flag. Read by boot sequence."""
    _rtc_init()
    mem = bytearray(_rtc_read())
    mem[RTC_OFFSET_FLAGS] |= FLAG_WAS_ASLEEP
    _rtc_write(bytes(mem))


def was_asleep():
    """Check if we woke from a car-sleep cycle."""
    mem = _rtc_read()
    if len(mem) <= RTC_OFFSET_FLAGS:
        return False
    return bool(mem[RTC_OFFSET_FLAGS] & FLAG_WAS_ASLEEP)


def clear_sleep_flags():
    """Clear all sleep flags (normal boot)."""
    _rtc_init()
    mem = bytearray(_rtc_read())
    mem[RTC_OFFSET_FLAGS] = 0
    _rtc_write(bytes(mem))


def mark_prestart_buffered():
    """Set flag that pre-start data was buffered before sleep."""
    _rtc_init()
    mem = bytearray(_rtc_read())
    mem[RTC_OFFSET_FLAGS] |= FLAG_PRESTART_BUFFERED
    _rtc_write(bytes(mem))


def was_prestart_buffered():
    """Check if pre-start data was saved before last sleep."""
    mem = _rtc_read()
    if len(mem) <= RTC_OFFSET_FLAGS:
        return False
    return bool(mem[RTC_OFFSET_FLAGS] & FLAG_PRESTART_BUFFERED)


def set_sleep_timestamp():
    """Record current time as last sleep entry."""
    _rtc_init()
    mem = bytearray(_rtc_read())
    ts = int(time.time())
    mem[RTC_OFFSET_SLEEP_TS:RTC_OFFSET_FLAGS] = ts.to_bytes(4, 'big')
    _rtc_write(bytes(mem))


def get_sleep_timestamp():
    """Get the timestamp when we last entered sleep."""
    mem = _rtc_read()
    if len(mem) < RTC_OFFSET_FLAGS:
        return 0
    return int.from_bytes(mem[RTC_OFFSET_SLEEP_TS:RTC_OFFSET_FLAGS], 'big')


# ---- Deep Sleep Entry ----


def enter_deep_sleep(duration_ms):
    """
    Flush flags to RTC and enter deep sleep for duration_ms.
    Wakes via RTC timer after duration_ms elapses.
    On wake, main.py runs from scratch — boot sequence checks was_asleep().

    Power draw: ~10µA vs ~80mA active (8000x reduction).
    """
    mark_was_asleep()
    set_sleep_timestamp()

    print("[sleep] Entering deep sleep for %d min..." % (duration_ms / 60000))

    # Brief delay so print reaches serial before sleep
    time.sleep(0.3)

    machine.deepsleep(duration_ms)


# ---- Wake Detection ----


def detect_wake_reason():
    """
    Called at boot. Returns (is_sleep_wake, is_cold_boot).
    - is_sleep_wake: woke from a car-sleep cycle
    - is_cold_boot: first power-on (not a sleep wake)

    Also detects if ESP32 reset via watchdog or other reset.
    """
    try:
        reset = machine.reset_cause()
    except Exception:
        reset = 0

    if reset == machine.DEEPSLEEP_RESET:
        # Woke from deep sleep. Check if it was our car-sleep.
        if was_asleep():
            return True, False  # is_sleep_wake=True, cold_boot=False

    # Cold boot or other reset type (power-on, watchdog, etc.)
    return False, True  # is_sleep_wake=False, cold_boot=True

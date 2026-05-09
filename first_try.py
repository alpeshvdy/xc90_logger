# ble_scan_test.py — run this first on real hardware
import bluetooth
import time

ble = bluetooth.BLE()
ble.active(True)

def irq(event, data):
    if event == 5:  # scan result
        addr_type, addr, adv_type, rssi, adv_data = data
        # Print everything we see
        print(f"RSSI:{rssi} addr:{bytes(addr).hex()}")

ble.irq(irq)
ble.gap_scan(10000, 50000, 30000, True)
time.sleep(12)
print("Scan complete")
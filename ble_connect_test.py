# ble_connect_test.py
# Direct connection test to iCar Pro using known MAC address
# Run in Thonny after stopping main.py

import bluetooth
import time

# Known iCar Pro MAC from our scan
TARGET_ADDR = bytes([0xD2, 0xE0, 0x2F, 0x8D, 0x5A, 0x04])

connected = False
conn_handle = None

def irq_handler(event, data):
    global connected, conn_handle
    if event == 7:  # _IRQ_PERIPHERAL_CONNECT
        conn_handle, addr_type, addr = data
        # Build address string manually
        addr_str = ''
        for b in addr:
            if addr_str:
                addr_str = addr_str + ':'
            addr_str = addr_str + '%02X' % b
        print('[connect] Connected! handle=%d addr=%s' % (conn_handle, addr_str))
        connected = True
    elif event == 8:  # _IRQ_PERIPHERAL_DISCONNECT
        print('[connect] Disconnected')

ble = bluetooth.BLE()
ble.active(True)
ble.irq(irq_handler)

# Build address string manually
addr_str = ''
for b in TARGET_ADDR:
    if addr_str:
        addr_str = addr_str + ':'
    addr_str = addr_str + '%02X' % b
print('Attempting direct connect to %s...' % addr_str)

result = ble.gap_connect(0, TARGET_ADDR)
print('gap_connect returned: %s' % str(result))
print('Waiting for connection event (15s timeout)...')

start = time.time()
while time.time() - start < 15:
    if connected:
        elapsed = time.time() - start
        print('Connection confirmed after %.1f s!' % elapsed)
        break
    time.sleep(0.2)
else:
    print('TIMEOUT - no connection event received')

print('Final: connected=%s, handle=%s' % (str(connected), str(conn_handle)))
import bluetooth

def scan_handler(event, data):
    if event == 5:  # _IRQ_SCAN_RESULT
        addr_type, addr, adv_type, rssi, adv_data = data
        addr_str = ':'.join(f'{b:02X}' for b in addr)
        print(f'\n=== Device {addr_str} RSSI:{rssi} ===')
        print(f'Raw ({len(adv_data)} bytes): {adv_data.hex()}')
        i = 0
        while i < len(adv_data):
            length = adv_data[i]
            if length == 0:
                break
            ad_type = adv_data[i + 1]
            payload = adv_data[i + 2:i + 1 + length]
            try:
                decoded = payload.decode('utf-8')
                print(f'  [0x{ad_type:02X}, len={length}] \"{decoded}\"')
            except:
                print(f'  [0x{ad_type:02X}, len={length}] {payload.hex()}')
            i += 1 + length

# Initialise BLE
ble = bluetooth.BLE()
ble.active(True)
ble.irq(scan_handler)

print('Scanning 15s - move ESP32 near iCar Pro...')
print('Press Ctrl+C to stop early\n')

# Start scan: duration=15s, interval=50ms, window=30ms, active=True
ble.gap_scan(15000, 50000, 30000, True)
print('Done')
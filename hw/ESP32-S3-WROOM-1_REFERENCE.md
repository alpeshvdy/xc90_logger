# ESP32-S3-WROOM-1 Reference Sheet
> Extracted from Espressif Datasheet v1.8 — relevant for the XC90 OBD Logger project (LOLIN S3 Pro)

---

## Module at a Glance

| Property | Value |
|----------|-------|
| **SoC** | ESP32-S3, Xtensa dual-core 32-bit LX7 @ up to 240 MHz |
| **WiFi** | 802.11b/g/n (2.4 GHz), up to 150 Mbps |
| **Bluetooth** | BLE 5.0, Bluetooth Mesh, 125 Kbps – 2 Mbps |
| **Flash** | Up to 16 MB Quad SPI (80 MHz max) |
| **PSRAM** | Up to 16 MB (Octal SPI variants available) |
| **GPIOs** | Up to 36 (4 are strapping pins) |
| **Antenna** | PCB antenna (WROOM-1) or external U.FL connector (WROOM-1U) |
| **Dimensions** | 18.0 × 25.5 × 3.1 mm (WROOM-1) / 18.0 × 19.2 × 3.2 mm (WROOM-1U) |
| **Operating Voltage** | 3.0 – 3.6 V DC |
| **Temperature** | –40 ~ 85 °C (standard), up to 105 °C (H4 variant) |

---

## Pins Relevant to OBD Logger

### Power & Control

| Pin | GPIO | Notes |
|-----|------|-------|
| **3V3** (pin 2) | — | Power supply, 3.0–3.6 V. Deliver ≥500 mA. |
| **EN** (pin 3) | — | High = on. Low = chip off. **Do not float.** Add RC delay (R=10kΩ, C=1µF) for stable power-up. |
| **GND** (pins 1, 40, 41) | — | EPAD (pin 41) soldering improves thermal performance. |

### UART (Serial / REPL / Debug)

| Pin | GPIO | Alt Function |
|-----|------|-------------|
| **TXD0** (pin 37) | GPIO43 | U0TXD, CLK_OUT1 |
| **RXD0** (pin 36) | GPIO44 | U0RXD, CLK_OUT2 |

These are the default MicroPython REPL pins. Also used for UART Download Boot.

### ADC Pins (Analog Sensors)

All 12-bit SAR ADC, 2 channels (ADC1, ADC2):

| Pin | GPIO | ADC Channel | Touch |
|-----|------|------------|-------|
| IO1 (39) | GPIO1 | ADC1_CH0 | TOUCH1 |
| IO2 (38) | GPIO2 | ADC1_CH1 | TOUCH2 |
| IO3 (15) | GPIO3 | ADC1_CH2 | TOUCH3 |
| IO4 (4) | GPIO4 | ADC1_CH3 | TOUCH4 |
| IO5 (5) | GPIO5 | ADC1_CH4 | TOUCH5 |
| IO6 (6) | GPIO6 | ADC1_CH5 | TOUCH6 |
| IO7 (7) | GPIO7 | ADC1_CH6 | TOUCH7 |
| IO8 (12) | GPIO8 | ADC1_CH7 | TOUCH8 |
| IO9 (17) | GPIO9 | ADC1_CH8 | TOUCH9 |
| IO10 (18) | GPIO10 | ADC1_CH9 | TOUCH10 |
| IO11 (19) | GPIO11 | ADC2_CH0 | TOUCH11 |
| IO12 (20) | GPIO12 | ADC2_CH1 | TOUCH12 |
| IO13 (21) | GPIO13 | ADC2_CH2 | TOUCH13 |
| IO14 (22) | GPIO14 | ADC2_CH3 | TOUCH14 |

### Strapping Pins (⚠️ Must be at correct level at boot)

| Pin | GPIO | Default | Controls |
|-----|------|---------|----------|
| **IO0** (pin 27) | GPIO0 | Pull-up (1) | Boot mode (0 + IO46=0 → Download Boot) |
| **IO3** (pin 15) | GPIO3 | Floating | JTAG signal source |
| **IO45** (pin 26) | GPIO45 | Pull-down (0) | VDD_SPI voltage selection |
| **IO46** (pin 16) | GPIO46 | Pull-down (0) | Boot mode + ROM log control |

### PSRAM Pins (⚠️ Unavailable on R8/R16V modules)

| Pin | GPIO | Notes |
|-----|------|-------|
| IO35 (28) | GPIO35 | Connected to Octal SPI PSRAM on R8/R16V |
| IO36 (29) | GPIO36 | Connected to Octal SPI PSRAM on R8/R16V |
| IO37 (30) | GPIO37 | Connected to Octal SPI PSRAM on R8/R16V |

---

## Boot Modes

| Mode | GPIO0 | GPIO46 |
|------|-------|--------|
| **SPI Boot** (normal) | 1 (default) | Any |
| **Download Boot** | 0 | 0 |

**Download Boot** enables:
- USB-Serial-JTAG Download Boot
- USB-OTG Download Boot
- UART Download Boot

To enter download mode: hold GPIO0 low, reset, release GPIO0.

---

## Power Consumption (for battery life estimation)

### Active Mode (RF on)

| Mode | Peak Current |
|------|-------------|
| WiFi TX (802.11b, 1 Mbps, @20.5 dBm) | **355 mA** |
| WiFi TX (802.11n, MCS7) | 286 mA |
| WiFi RX | 95 mA |
| BLE TX (@20 dBm) | **344 mA** |
| BLE TX (@0 dBm) | 187 mA |
| BLE RX | 93 mA |

### Modem-Sleep (CPU on, RF clock-gated)

| CPU Freq | Typ (periph clocks off) |
|----------|------------------------|
| 240 MHz (dual core idle) | 32.9 mA |
| 240 MHz (dual core active) | 91.7 mA |
| 80 MHz (dual core idle) | 22.0 mA |

### Low-Power Modes

| Mode | Typ Current |
|------|------------|
| Light-sleep | 240 µA |
| Deep-sleep (RTC memory on) | 8 µA |
| Deep-sleep (ULP sensor pattern) | 18 µA |
| Power off (EN low) | 1 µA |

> **Note for XC90 Logger**: BLE TX at 0 dBm (187 mA) + CPU at 80 MHz (~22 mA) ≈ **~210 mA** during active logging. A standard 2000 mAh USB power bank would last ~9 hours.

---

## BLE RF Characteristics

| Parameter | Value |
|-----------|-------|
| Frequency range | 2402 – 2480 MHz |
| TX power range | –24 to +20 dBm |
| RX sensitivity (1 Mbps) | –96.5 dBm |
| RX sensitivity (125 Kbps) | –103.5 dBm |
| Max RX signal | +8 dBm |

**BLE 5 features supported**: Advertising extensions, multiple ad sets, channel selection #2, 2 Mbps PHY.

---

## Peripheral Quick Reference

| Peripheral | Count | Notes |
|-----------|-------|-------|
| **UART** | 3 | Up to 5 Mbps, hardware flow control |
| **I2C** | 2 | Standard (100 kbps) / Fast (400 kbps) / up to 800 kbps |
| **SPI** | 4 | SPI2/SPI3 are general-purpose, up to 80 MHz |
| **I2S** | 2 | Up to 40 MHz BCK, 8/16/24/32-bit, TDM + PDM |
| **ADC** | 2× 12-bit SAR | 20 channels total |
| **Touch** | 14 capacitive-sensing GPIOs | ⚠️ Not CS-tested, limited scenarios |
| **Temperature Sensor** | 1 | –40 to 125 °C range (internal chip temp) |
| **USB OTG** | 1 | Full-speed USB 2.0 |
| **USB Serial/JTAG** | 1 | CDC-ACM serial + JTAG debug |
| **TWAI (CAN 2.0)** | 1 | 1 Kbps – 1 Mbps, compatible with ISO 11898-1 |
| **LED PWM** | 8 channels | 14-bit duty cycle resolution |
| **SD/MMC Host** | 1 | Up to 80 MHz, 1/4/8-bit bus |

---

## Key Limits

| Parameter | Max |
|-----------|-----|
| Power supply voltage | 3.6 V (absolute max) |
| IO input voltage | VDD + 0.3 V |
| IO source current | 40 mA (VOH ≥ 2.64 V) |
| IO sink current | 28 mA (VOL ≤ 0.495 V) |
| Internal pull-up/down | ~45 kΩ |
| ESD (HBM) | ±2000 V |
| ESD (CDM) | ±500 V |
| Flash erase cycles | 100,000 |
| Flash data retention | 20 years |

---

## Antenna Notes

- **WROOM-1**: Keepout zone required around PCB antenna (see datasheet Fig 11-1)
- **WROOM-1U**: Uses U.FL / MHF I / AMC connector. External antenna must be 2.4 GHz, 50 Ω, max gain ≤ 2.33 dBi.

---

## Datasheet Links

- Full datasheet: [esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf](https://www.espressif.com/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
- ESP32-S3 Series Datasheet: [link](https://www.espressif.com/en/products/socs/esp32-s3)
- ESP32-S3 Technical Reference Manual: [link](https://www.espressif.com/en/support/documents/technical-documents)
- Hardware Design Guidelines: [link](https://www.espressif.com/en/support/documents/technical-documents)

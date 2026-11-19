# Schematic notes — revision A

Status: **first draft, not yet reviewed by a person and not laid out.** KiCad's electrical rules check passes with zero violations and KiCad's exported netlist matches the intended netlist pin for pin (see [Verification](#verification)). That proves the drawing is self-consistent; it does not prove the design is right.

Files: [`hardware/climasense.kicad_sch`](../../hardware/climasense.kicad_sch), project symbols in [`hardware/lib/climasense.kicad_sym`](../../hardware/lib/climasense.kicad_sym).

## Block overview

```
USB-C ──VBUS── fuse F1 ──+5V──┬── buck TPS62A01 ──► +3V3 ──── ESP32-C6, status LED, pull-ups
                              │
                              └── LDO TLV75533 ──► +3V3_SENS ─ SHT45, SCD41, SGP41, BMP580, Qwiic
                                      ▲ EN
                                      └── SENS_EN (pulled high, MCU can pull low)

USB D+/D- ── ESD (USBLC6-2) ── ESP32-C6 native USB (flashing, logs, JTAG)
ESP32-C6 ── I2C (IO6 SDA, IO7 SCL) ── all sensors + Qwiic
```

## Design choices made while drawing

These went beyond what had been decided beforehand; all were accepted on 2026-11-19.

| Choice | Why |
| --- | --- |
| **Two 3.3 V rails**: a buck converter for the MCU, a separate LDO from 5 V for the sensors | The SCD41 datasheet asks for a low-noise supply that moves less than 30 mV, and recommends its own LDO. Wi-Fi transmit bursts on a shared rail would violate that. The buck keeps regulator heat low for the MCU, which draws most of the current. |
| **Sensor rail can be switched off** by the MCU (`SENS_EN`, default on) | Lets firmware power-cycle a hung sensor or I2C bus without anyone touching the device. Costs one resistor and one GPIO. |
| **Discrete RGB LED** on three GPIOs instead of an addressable (WS2812-type) LED | WS2812B-2020 is specified for 3.7–5.3 V supply and its data input is not guaranteed to accept 3.3 V logic when run from 5 V. A plain LED with three resistors has no such issue and is dimmed with PWM. |
| **I2C on IO6/IO7** | These are the ESP32-C6 low-power I2C pins, so the low-power core could read sensors in a future battery variant. |
| **BMP580 interrupt wired** to IO19 | Free to add; allows data-ready interrupts. |
| **Qwiic connector on the sensor rail** | Same I2C voltage domain as the on-board sensors and power-cycled with them. |
| **Resettable fuse on the USB supply** (0.75 A hold, 1.5 A trip) — decided 2026-11-19 | The device runs unattended on arbitrary chargers that can deliver 2–3 A into a board fault. `VBUS` is the raw connector supply, `+5V` the rail behind the fuse; both regulators run from `+5V`. 0.75 A was chosen over 0.5 A so a warm enclosure or a long Wi-Fi transfer cannot trip it. |
| **USB shield tied directly to GND** | Best path for static discharge; no ground loop exists on a wall charger. |
| **No USB series resistors** | The C6 USB pins connect directly; ESD protection is the USBLC6-2. |

## ESP32-C6-WROOM-1 pin assignment

| Module pin | GPIO | Net | Use |
| --- | --- | --- | --- |
| 3 | EN | `EN` | 10 kΩ pull-up, 1 µF to GND, RESET button |
| 15 | IO9 | `BOOT` | 10 kΩ pull-up, BOOT/USER button (strapping pin: low at reset = download mode) |
| 10 | IO8 | `IO8` | 10 kΩ pull-up (strapping pin: must be high for download mode) |
| 13 | IO12 | `USB_DN` | USB D− |
| 14 | IO13 | `USB_DP` | USB D+ |
| 25 | IO16 (TXD0) | `UART_TX` | test pad TP1 |
| 24 | IO17 (RXD0) | `UART_RX` | test pad TP2 |
| 6 | IO6 | `I2C_SDA` | sensors + Qwiic, 4.7 kΩ pull-up to +3V3_SENS |
| 7 | IO7 | `I2C_SCL` | sensors + Qwiic, 4.7 kΩ pull-up to +3V3_SENS |
| 16 | IO18 | `SENS_EN` | sensor LDO enable, 100 kΩ pull-up |
| 17 | IO19 | `BMP_INT` | BMP580 interrupt |
| 19 | IO21 | `LED_R` | red, active low, 1 kΩ |
| 20 | IO22 | `LED_G` | green, active low, 220 Ω |
| 21 | IO23 | `LED_B` | blue, active low, 220 Ω |
| 4, 5, 8, 9, 11, 12, 18, 23, 26, 27 | IO4, IO5, IO0, IO1, IO10, IO11, IO20, IO15, IO3, IO2 | — | unused, marked no-connect |

IO0/IO1 are deliberately left free: they are the 32 kHz crystal pins, useful for a battery variant.

## I2C addresses

| Address | Device |
| --- | --- |
| 0x44 | SHT45 |
| 0x47 | BMP580 (SDO tied high) |
| 0x59 | SGP41 |
| 0x62 | SCD41 |

## Bill of materials

JLCPCB part numbers verified against the JLCPCB parts library on 2026-11-19. "Basic" parts carry no per-type loading fee.

| Ref | Part | Package | JLCPCB | Library |
| --- | --- | --- | --- | --- |
| U4 | ESP32-C6-WROOM-1-N8 | module | C5366877 | extended |
| U5 | SHT45-AD1B-R2 | DFN-4 1.5×1.5 | C5221601 | extended |
| U6 | SCD41-D-R2 | LGA-20 10.1×10.1 | C3659294 | extended |
| U7 | SGP41-D-R4 | DFN-6 2.44×2.44 | C3659325 | extended |
| U8 | BMP580 | LGA-10 2×2 | C22391138 | extended |
| U1 | USBLC6-2SC6 | SOT-23-6 | C7519 | extended |
| U2 | TPS62A01DRLR | SOT-563 | C5157937 | extended |
| U3 | TLV75533PDBVR | SOT-23-5 | C404027 | extended |
| L1 | 1 µH, DFE252012F-1R0M | 2520 | C435392 | extended |
| F1 | Resettable fuse MF-NSMF075-2, 0.75 A, 6 V | 1206 | C89653 | extended |
| D1 | RGB LED 19-337/R6GHBHC-A01/2T | 1.6×1.6 | C264519 | extended |
| J1 | USB-C receptacle TYPE-C-31-M-12 | 16-pin SMD | C165948 | extended |
| J2 | JST SH 4-pin SM04B-SRSS-TB (Qwiic) | 1 mm pitch | C160404 | extended |
| SW1, SW2 | TS-1187A-B-A-B push button | 5.1×5.1 | C318884 | basic |
| R14 | 4.7 Ω | 0402 | C25121 | extended |
| R3 | 68 kΩ | 0402 | C36871 | extended (preferred, no fee) |
| R9 | 1 kΩ | 0402 | C11702 | basic |
| R10, R11 | 220 Ω | 0402 | C25091 | basic |
| R12, R13 | 4.7 kΩ | 0402 | C25900 | basic |
| R1, R2 | 5.1 kΩ | 0402 | C25905 | basic |
| R6, R7, R8 | 10 kΩ | 0402 | C25744 | basic |
| R4 | 15 kΩ | 0402 | C25756 | basic |
| R5 | 100 kΩ | 0402 | C25741 | basic |
| C6, C8, C10, C13, C14 | 100 nF | 0402 | C1525 | basic |
| C3, C4, C7, C11, C12 | 1 µF | 0402 | C52923 | basic |
| C1, C5, C9 | 10 µF | 0805 | C15850 | basic |
| C2 | 22 µF | 0805 | C45783 | basic |
| TP1–TP3 | bare test pads | 1.5 mm | — | not a part |

14 part types carry the extended-part loading fee (about $42), within the range of the earlier cost estimate.

## Open points for the layout phase

- The four footprints missing from KiCad's standard library (ESP32-C6-WROOM-1, SGP41, BMP580, 19-337 RGB LED) have been drawn and assigned; see [`footprints.md`](footprints.md). They are unproven on a real board.
- The inductor uses a generic 2520 footprint; check it against the DFE252012F land pattern.
- Mounting holes and the board outline depend on the enclosure, which is undecided.
- Thermal layout rules from [`../research/hardware-options.md`](../research/hardware-options.md) apply: sensors at a board edge behind milled slots, away from U2, U3, U4 and the SGP41.
- Keep the SCD41's "do not connect" pads on isolated pads, as its datasheet requires.
- LED resistor values are a first guess for brightness balance; expect to tune them (or the PWM duty) on the first board.
- The 4.7 Ω resistor is the only passive with a loading fee. A basic-library value such as 10 Ω would likely work as well for the SGP41 supply filter, but the datasheet specifies 4.7 Ω, so it is kept for now.

## How the schematic is produced

The schematic is generated by [`hardware/tools/gen_schematic.py`](../../hardware/tools/gen_schematic.py), which pulls standard symbols from the installed KiCad library and writes the project symbols, the schematic and the project files.

```bash
python hardware/tools/gen_schematic.py
```

```bash
python hardware/tools/check_schematic.py
```

Editing the schematic in KiCad is fine and expected. **Once you do, do not re-run the generator** — it overwrites `climasense.kicad_sch`. After layout starts, the `.kicad_sch` file is the only source of truth and the generator is history.

## Verification

`check_schematic.py` does four things with KiCad's own command-line tool:

1. runs the electrical rules check and fails on any violation — currently **0 violations**;
2. exports KiCad's netlist and compares every net, pin by pin, against the netlist the generator intended — currently **46 components, 27 nets, all matching**;
3. checks that every part has a footprint and every symbol pin a pad with the same number — currently **all 46 parts pass**;
4. plots the schematic to `hardware/build/climasense.pdf`.

Pin numbers and application circuits were checked against these datasheets: ESP32-C6-WROOM-1 (v1.4, pin table and strapping pins), SGP41 (v1.0, pin assignment and application circuit), BMP580 (BST-BMP580-DS004-02, pin-out and I2C wiring), SCD4x (v1.5, pin assignment and supply requirements), TPS62A01 (SLUSEG9E, pin functions and component values), TLV755P (enable thresholds), Everlight 19-337 (pin polarity). Symbols taken unchanged from KiCad's library (USB-C connector, USBLC6-2SC6, TPS62A01, TLV75533, SHT4x, SCD41) were not re-checked pin by pin.

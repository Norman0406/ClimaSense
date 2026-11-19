# Decisions

Settled design decisions for ClimaSense. Background and alternatives are in [`research/hardware-options.md`](research/hardware-options.md).

## Revision 1.0 hardware (decided 2026-11-19)

| Topic | Decision | Notes |
| --- | --- | --- |
| MCU | **ESP32-C6-WROOM-1-N8** (JLCPCB C5366877) | Wi-Fi 6 (2.4 GHz), BLE 5, Thread/Zigbee. Chosen over the ESP32-C5 "for now" because the C5 modules were out of stock at JLCPCB. 5 GHz stays a wish — revisit if the C5 becomes easy to source. |
| Temperature + humidity | **Sensirion SHT45** (C5221601) | |
| CO2 | **Sensirion SCD41** (C3659294) | |
| VOC + NOx | **Sensirion SGP41** (C3659325) | |
| Barometric pressure | **Bosch BMP580** (C22391138) | |
| Ambient light, microphone | **Not in revision 1.0** | Deferred; no footprints planned for now. |
| Extras | **RGB status LED, Qwiic connector** | The Qwiic connector has its own I2C bus and its own switchable, current-limited supply (decided 2026-11-19): it was either that or removing it, so that nothing plugged in can disturb the on-board sensors. |
| Buttons | **Two**: combined BOOT/user button, and RESET | BOOT/user is reachable from outside the enclosure (long press → Wi-Fi setup portal); RESET is board-only. |
| Programming | **Native USB** of the ESP32-C6 via the USB-C port; OTA over Wi-Fi once deployed | No USB-UART bridge. BOOT + RESET always recovers the board over USB. |
| Debug access | **None beyond USB** | Decided 2026-11-19. Bare UART test pads and a Tag-Connect TC2030-IDC footprint were both considered and dropped; UART0 is not brought out. BOOT + RESET over USB is the recovery path. |
| Power | **USB-C only** | Battery is a possible separate later variant. |
| Quantity | **At least 5 boards** | |
| Assembly | Full PCBA at JLCPCB | No hand soldering. |
| Enclosure | **Deferred**; a 3D-printed case is expected later | The device hangs on a wall in landscape, USB cable down, components facing the room (decided 2026-11-19; an earlier note said it lies flat). |
| Board | **75 × 34 mm, landscape, 2 layers**, routed | ESP32 at the left end with the antenna at the edge, then USB (on the bottom edge) and power, then the sensors at the right end behind a milled slot. See [`hardware/layout.md`](hardware/layout.md). |
| Mounting | **Four M3 holes in the corners** | |
| Routing | **By script**, checked with KiCad's rule check | |
| Revision naming | **Numeric: 1.0** for the first board | Decided 2026-11-19, replacing the letter "A". |
| Sensor arrangement | **SCD41 and SGP41 at the top of the sensor side, SHT45 lowest**, on a tongue at the lower right | On a wall, heat rises: the two warm sensors sit at the top so their heat leaves upwards, and nothing warm is underneath the SHT45. |

The BME680 from the breadboard prototypes is dropped.

Ideas for later revisions — a different microcontroller, deep sleep, separate power control for the SCD41 — are collected in [`hardware/next-revision.md`](hardware/next-revision.md). None of them is decided.

## Schematic-level choices (accepted 2026-11-19)

Made while drawing the first schematic and accepted afterwards; rationale in [`hardware/schematic.md`](hardware/schematic.md).

| Topic | Choice |
| --- | --- |
| Power | Buck converter (TPS62A01) for the MCU rail `+3V3`; separate LDO (TLV75533) from 5 V for the sensor rail `+3V3_SENS`, as the SCD41 datasheet recommends |
| Sensor power control | MCU can switch the sensor rail off via `SENS_EN` (default on) to recover a hung sensor |
| Qwiic | Own I2C bus on IO19/IO20; own regulator (second TLV75533) switched by `QWIIC_EN`, off by default |
| Status LED | Discrete RGB LED on three GPIOs with PWM, not an addressable LED (those are out of spec at 3.3 V) |
| I2C pins | IO6 (SDA) / IO7 (SCL), the ESP32-C6 low-power I2C pins |
| Protection | ESD diodes on USB data; USB shield tied to GND; resettable fuse (0.75 A) on the USB supply |
| BMP580 interrupt | Wired to IO19 |

## Cost estimate for 5 boards (2026-11-19)

Component prices are live JLCPCB quantity-1 prices from 2026-11-19. Fees are taken from JLCPCB's published price list, not from a real quote — the quote at checkout is authoritative.

### Components per board

| Part | Price |
| --- | --- |
| SCD41 | $19.45 |
| SGP41 | $9.02 |
| SHT45 | $5.72 |
| ESP32-C6-WROOM-1-N8 | $4.30 |
| BMP580 | $1.21 |
| USB-C connector, ESD protection, regulators, LED, Qwiic connector, buttons, passives | ~$1.30 |
| **Total per board** | **~$41** |

### Order total

| Item | Low | High | Assumption |
| --- | --- | --- | --- |
| Components, 5 boards | $205 | $205 | |
| Bare PCBs (5 pcs, ~50 × 80 mm) | $5 | $25 | Low: 2-layer, standard finish. High: gold (ENIG) finish, which is advisable for the fine-pitch sensor packages. |
| Assembly setup + stencil | $10 | $34 | Low: "Economic" service. High: "Standard" service, if a part or the board requires it. |
| Per-part-type loading fees | $36 | $45 | ~12 non-basic part types at ~$3 each. |
| Placement | $2 | $3 | |
| **Subtotal** | **~$258** | **~$312** | |
| Shipping | $10 | $35 | Economy vs. express. |
| **Total before import VAT** | **~$270** | **~$350** | **$54–70 per board** |

Import VAT depends on the destination country and comes on top (roughly 8–20 %).

Not included: enclosure, USB power supply and cable.

### Observations

- The sensors are about 85 % of the component cost; the SCD41 alone is $97 of the $205.
- Fixed costs (setup, loading fees, shipping) are roughly $60–110 per order regardless of quantity. Each additional board beyond 5 costs about $41–43.
- JLCPCB can assemble only 2 of the 5 PCBs. For the first, untested revision that limits the sensor spend at risk to ~$82 instead of ~$205; the remaining boards follow once the design is verified (paying the fixed costs a second time).
- Swapping the SHT45 for the footprint-compatible SHT41 would save $12 across 5 boards.

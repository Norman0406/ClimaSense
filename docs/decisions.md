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
| Revision naming | **Numeric: 1.0** for the first board, printed on it as **"Rev 1.0"** | Numeric decided 2026-11-19, replacing the letter "A". "Rev" rather than "v" on the silkscreen (2026-11-20), so that the number is not taken for a firmware version. **The first number** changes when the firmware has to know about the change: a different pin map, a part that needs a different driver or address, anything that needs different code. **The second number** changes for a re-spin the firmware cannot tell apart from its predecessor: layout, routing, silkscreen, a part swapped for an equivalent one. A number is used up once boards carrying it have been ordered; changes before that do not count. File names carry the bare number (`climasense-1.0-…`). |
| Sensor arrangement | **SCD41 and SGP41 at the top of the sensor side, SHT45 below them**, on a tongue at the right edge | On a wall, heat rises: the two warm sensors sit at the top so their heat leaves upwards, and nothing is underneath the SHT45. The BMP580 sits lower still, but 17 mm to the left, and gives off practically no heat. (Corrected 2026-11-20: this row used to call the SHT45 the lowest sensor.) |

The BME680 from the breadboard prototypes is dropped.

Ideas for later revisions — a different microcontroller, deep sleep, separate power control for the SCD41 — are collected in [`hardware/next-revision.md`](hardware/next-revision.md). None of them is decided.

## Firmware (decided 2026-11-19)

| Topic | Decision | Notes |
| --- | --- | --- |
| Framework | **ESP-IDF**, version **6.1** (6.1.1 at the start) | Chosen over ESPHome and Arduino. Sensirion and Bosch publish their drivers and Sensirion's VOC/NOx index algorithm in C, which ESP-IDF builds as-is. ESP-IDF gives direct control over what this board needs: the sensors on the low-power I2C controller and Qwiic on the normal one, releasing the bus pins before switching a rail off, SCD41 single-shot mode, and the low-power core if deep sleep is ever needed. MQTT client, HTTP server and OTA are part of ESP-IDF. |
| Language | **C++** (ESP-IDF 6.1 compiles with `-std=gnu++26`), restricted | No exceptions and no RTTI (ESP-IDF's defaults), no heap-allocating containers in the measurement path. Chosen for classes with a shared interface for the sensors, automatic release of locks and bus handles, and `std::optional`/`std::expected` for readings that may not exist. Vendor drivers stay C files and are called from C++. |
| Build | `idf.py` from the ESP-IDF tools | Project in `firmware/`; `sdkconfig.defaults` is versioned, the generated `sdkconfig` is not. |
| Settings | **Everything the device needs at run time can be set and changed in the captive portal** (decided 2026-11-20) | Wi-Fi network and password, country, time server, time zone now; the MQTT broker and the like later. Build-time values (Kconfig, `sdkconfig.defaults.local`) are only defaults; settings stored by the portal in NVS take precedence. Each group of settings is one record with its own validation rules (`net/settings.h`), which the portal uses to check its form. |
| Captive portal | **Opens only when no Wi-Fi network is configured, or on a 3 s press of the BOOT button; open network `ClimaSense-<id>`; closes after 10 minutes** (decided 2026-11-20) | A lost network does not open it: otherwise anyone nearby could reconfigure the device whenever the router is off. A fixed password for the portal network would be no safer than none, since it would be published. Passwords are never sent back to the browser. |
| Device name and ID | **Fixed ID in the MQTT topics, a name set in the portal as information** (decided 2026-11-20) | The ID is the host name, `climasense-` plus the last three MAC bytes; it never changes, so subscriptions, dashboards and histories never break. The name (UTF-8, up to 32 bytes, empty: the ID is shown) travels in the messages. Names in topics would break on renaming and need escaping. |
| Publishing | **MQTT to the existing Mosquitto, read by mqtt-exporter into Prometheus** (decided 2026-11-20) | Questioned and kept: the device only pushes, needs no inbound reachability, and any number of consumers read the same messages. A `/metrics` endpoint on the device was considered and left out; it remains an option if the device name is wanted as a Prometheus label. |
| MQTT connection | **Plain MQTT on port 1883 with user name and password, no TLS** (decided 2026-11-20) | Local broker. TLS would need the broker's CA certificate on the device and in the portal. |
| MQTT messages | **One flat JSON state message every 60 s to `<base>/<id>/state`; retained `online`/`offline` (last will) on `<base>/<id>/status`** (decided 2026-11-20) | Temperature, humidity and pressure are the means of the interval; VOC and NOx index the latest of the interval; values without data are left out, never 0. CO2 is measured every 5 minutes, so its latest value is repeated in every message for up to 11 minutes, together with its age `co2_age_s`; no other value gets an age, since all others are from the last interval by construction. |
| Diagnostics over MQTT | **Retained boot report per start, WARNING-and-above log lines at most 10 a minute, log level settable over MQTT until restart; the core dump erased once the boot report is acknowledged** (decided 2026-11-20) | `<base>/<id>/boot`, `<base>/<id>/log`, `<base>/<id>/set/log_level`. mqtt-exporter subscribes to everything by default; to keep these out of Prometheus, narrow its topic filter to `climasense/+/state`. |
| Home Assistant | **Discovery as a portal switch, off by default** (decided 2026-11-20) | One retained config message per value; re-sent when Home Assistant announces a restart. The same state message serves Prometheus and Home Assistant. Turning the switch off does not remove the device from Home Assistant; delete it there. |
| MQTT client | **`espressif/mqtt` 1.1.0 from Espressif's component registry**, pinned exactly; `firmware/dependencies.lock` versioned (decided 2026-11-20) | ESP-IDF 6 no longer ships the MQTT client. Our component is named `telemetry`, because `mqtt` is the registry component's name. |
| Step order | **Captive portal (step 7) before MQTT (step 6)** (decided 2026-11-20) | So the MQTT settings go straight into the portal. The steps keep their numbers. |
| Partition table | **Two 3 MB OTA slots and a 128 KB core dump partition** (decided 2026-11-20) | `firmware/partitions.csv`. Laid out before the first board is flashed, because changing it later needs a USB flash of every board. |
| Crash handling | **Core dump to flash, last 2 KB of log kept across resets, task watchdog panics** (decided 2026-11-20) | Reported at the next start and, from step 6, published over MQTT. Details in [`firmware/architecture.md`](firmware/architecture.md#debugging). |

## Schematic-level choices (accepted 2026-11-19)

Made while drawing the first schematic and accepted afterwards; rationale in [`hardware/schematic.md`](hardware/schematic.md).

| Topic | Choice |
| --- | --- |
| Power | Buck converter (TPS62A01) for the MCU rail `+3V3`; separate LDO (TLV75533) from 5 V for the sensor rail `+3V3_SENS`, as the SCD41 datasheet recommends |
| Sensor power control | MCU can switch the sensor rail off via `SENS_EN` (default on) to recover a hung sensor |
| Qwiic | Own I2C bus on IO19/IO20; own regulator (second TLV75533) switched by `QWIIC_EN`, off by default |
| Enable pins | `QWIIC_EN` on IO11, `SENS_EN` on IO18 (swapped 2026-11-19): IO18 has a pull-up while the chip is in reset, which would have switched the Qwiic supply on |
| Status LED | Discrete RGB LED on three GPIOs with PWM, not an addressable LED (those are out of spec at 3.3 V) |
| I2C pins | IO6 (SDA) / IO7 (SCL), the ESP32-C6 low-power I2C pins |
| Protection | ESD diodes on USB data; USB shield tied to GND; resettable fuse (0.75 A) on the USB supply |
| BMP580 interrupt | Wired to IO10 |

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

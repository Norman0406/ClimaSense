# Hardware options research

Date: 2026-11-19 · Status: **research; the resulting choices are recorded in [`../decisions.md`](../decisions.md)** (notably: ESP32-C6 instead of the C5 proposed here, no light sensor or microphone in revision A)

Scope: component selection for the ClimaSense PCB (USB-powered first revision, fully assembled by a PCBA service). Stock and prices are a snapshot of the JLCPCB assembly parts library on 2026-11-19 (unit price at quantity 1, USD) and will move — re-check before ordering.

## TL;DR — proposed configuration

| Function | Proposal | JLCPCB part | Price | Stock |
| --- | --- | --- | --- | --- |
| MCU / radio | **ESP32-C5-WROOM-1** (N8R8 or N16R8) | C51950749 / C54951859 | ~$5.85 | **0** (see sourcing risk) |
| Temperature + humidity | **Sensirion SHT45** (or SHT41 to save $2.50) | C5221601 (SHT41: C7461861) | $5.72 ($3.26) | 6,371 (11,190) |
| CO2 (the key "air quality" number) | **Sensirion SCD41** | C3659294 | $19.45 | 1,107 |
| VOC / NOx | **Sensirion SGP41** | C3659325 | $9.02 | 2,221 |
| Barometric pressure | Bosch BMP580 | C22391138 | $1.21 | 11,219 |
| Ambient light (optional) | Vishay VEML7700 | C1850416 | $1.20 | 6,113 |
| Microphone (optional) | TDK ICS-43434 (I2S) | C5656610 | $4.25 | 458 |
| Power | USB-C, 5 V → 3.3 V | — | < $1 | plenty |

Sensor BOM ≈ $35 without light/mic, ≈ $41 with. Expect very roughly $55–70 per assembled board at 5–10 pieces once PCB, passives, assembly and extended-part fees are included (estimate, not a quote).

The main change versus the breadboard: **replace the BME680 with dedicated sensors** — it is the weakest part of the current setup (details below).

## 1. MCU: ESP32 variant

Requirement: current chip, BLE, ideally 5 GHz.

| Chip | Wi-Fi | BLE | 802.15.4 (Thread/Zigbee) | Notes |
| --- | --- | --- | --- | --- |
| **ESP32-C5** | Wi-Fi 6, **2.4 + 5 GHz** | 5 LE | yes | Only ESP32 with 5 GHz. Single-core RISC-V 240 MHz. Mass production since April 2025. |
| ESP32-C6 | Wi-Fi 6, 2.4 GHz | 5 LE | yes | Mature, cheap (~$4.30), 3,500+ modules in stock at JLCPCB. |
| ESP32-C61 | Wi-Fi 6, 2.4 GHz | 5 LE | no | Low-cost C6 sibling. |
| ESP32-S3 | Wi-Fi 4, 2.4 GHz | 5 LE | no | Dual-core, most mature ecosystem; older radio. |

**Recommendation: ESP32-C5-WROOM-1** (PCB antenna, 27.5 × 18 mm). It is the only option that meets the 5 GHz wish and also brings BLE and Thread/Zigbee for free. Native USB Serial/JTAG means no USB-UART bridge chip is needed for flashing and logs.

Software support is fine by now: ESP-IDF ≥ 5.5, arduino-esp32 3.3.x, and ESPHome (variant `esp32c5`) all support it.

Honest caveats:

- **Sourcing risk.** Every PCB-antenna C5 module variant showed **0 stock** at JLCPCB today; only the U.FL variant (`-1U-N16R8-V1.2`, C54951857, 676 pcs, needs an external antenna) and the bare chip were available. Western distributors do stock the module (Mouser showed ~1,800 in a recent search snapshot). Workable routes: JLCPCB global-sourcing/pre-order of the part, or wait for restock. This needs a fresh check when we are ready to order.
- **5 GHz gives a sensor no functional benefit.** A device sending a few hundred bytes every few minutes does not need the bandwidth, and 5 GHz penetrates walls worse than 2.4 GHz. The real upside is being able to join 5 GHz-only/less congested networks. Dual-band covers both, so nothing is lost.
- If the C5 cannot be sourced, the **ESP32-C6-WROOM-1-N8** (C5366877) is the fallback: same feature set minus 5 GHz, in stock.

## 2. Temperature and humidity

| Part | Accuracy (typ.) | Price | Stock |
| --- | --- | --- | --- |
| SHT40 | ±0.2 °C, ±1.8 %RH | $1.75 | 13,349 |
| SHT41 | ±0.2 °C, ±1.8 %RH | $3.26 | 11,190 |
| **SHT45** | **±0.1 °C, ±1.0 %RH** | $5.72 | 6,371 |

All three are the same 1.5 × 1.5 mm footprint and I2C address (0x44 for the `-AD1B` variants), so the choice can be changed at order time. **Recommendation: SHT45** — on a board this size the $2.50–4 premium is small. In practice, layout matters more than the sensor grade: board self-heating easily adds 1–3 °C, far more than the difference between these parts.

### Thermal design rules (apply to all sensors)

These come from Sensirion's design-in guides and are the single biggest factor for measurement quality:

- Put the T/RH sensor at a board edge, as far as possible from the ESP32 module, the regulator and the SGP41 (its hotplate is a heat source).
- Isolate it with **milled slots** and route only thin traces onto the sensor "island"; no copper pour under or around it.
- Mount orientation: sensors at the **bottom** of the device, heat sources above (warm air rises away).
- Enclosure: large grille aperture near the sensors, minimal dead air volume, no direct sunlight on the sensors.
- Firmware matters too: keep the radio in power-save and avoid running the CPU continuously, even on USB, to limit heat.

## 3. Air quality — is the BME680 the right choice?

Short answer: **no, not for a new design.**

What the BME680 actually measures is the resistance of a heated metal-oxide layer, which reacts to the *sum* of volatile organic compounds. Everything else (IAQ index, "eCO2", "bVOC") is an estimate computed by Bosch's closed-source BSEC library. Specific problems:

- **It does not measure CO2.** The "eCO2" value is a guess derived from VOCs. CO2 is the best single indicator for "the room needs ventilation", and it needs a real CO2 sensor.
- **BSEC is a closed binary blob** with licence terms, per-architecture builds and state that must be persisted. Support for a new RISC-V target like the C5 is not guaranteed.
- The built-in temperature reading is biased by the sensor's own heater.
- The BME680 itself is now listed by distributors as **not recommended for new designs**; its successors are the BME688 and BME690 (pin-compatible, lower power, better condensation robustness), which share the same fundamental limits.

### Options

| Option | Measures | Pros | Cons | Price |
| --- | --- | --- | --- | --- |
| BME690 (C42431867) | VOC-based index, T, RH, pressure | One 3 × 3 mm part; drop-in for existing code | No real CO2; BSEC blob; newest part has thinnest library support | $9.92 |
| **SCD41** (C3659294) | **True CO2** (photoacoustic NDIR), 400–5,000 ppm, ±(50 ppm + 2.5 %) in the 400–1,000 ppm band | Accurate, proven, huge community support, automatic self-calibration | 10 × 10 × 6.5 mm; current pulses up to ~200 mA; ~$19 | $19.45 |
| STCC4 (C49191471) | CO2 via thermal conductivity, ±(100 ppm + 10 %) | 4 × 3 × 1.2 mm, < 1 mA, cheaper | Roughly 2–3× wider error band; new (2025); requires an SHT4x for compensation and regular fresh-air exposure for baseline | $11.32 |
| **SGP41** (C3659325) | VOC index + NOx index | Open-source algorithm (plain C, runs anywhere); NOx catches combustion (gas stove, candles) | Relative indices, not ppm; heater draws ~3 mA continuously | $9.02 |
| SGP40 (C2874215) | VOC index only | $2 cheaper | No NOx | $6.91 |
| ENS160 / ENS161 | VOC-based eCO2/TVOC | Cheap | Not stocked at JLCPCB; again no real CO2 | — |
| SEN66 (module) | PM1/2.5/4/10, T, RH, VOC, NOx, CO2 — everything | One calibrated unit, one driver | roughly $40–50, 55 × 26 × 21 mm box with a fan, cable-connected (not reflowed), not stocked at JLCPCB | — |

### Recommendation

**SHT45 + SCD41 + SGP41 (+ BMP580)**, all on one I2C bus.

- SCD41 gives the real CO2 number — the value that actually tells you to open a window.
- SGP41 gives VOC and NOx trends (cooking, cleaning agents, new furniture, combustion). It replaces what the BME680 gas reading was doing, with an open algorithm.
- BMP580 keeps the barometric pressure channel the BME680 provided and feeds pressure compensation to the SCD41.

Since the device is USB-powered and not size-constrained, the SCD41's higher power draw and size do not hurt, so its accuracy wins over the STCC4. The STCC4 becomes the better choice only if a battery variant is a real goal.

If budget needs trimming, drop the SGP41 first (saves $9); CO2 + T/RH already covers most of the practical value.

## 4. Optional: ambient light

| Part | Range | Notes | Price | Stock |
| --- | --- | --- | --- | --- |
| **VEML7700** | 0–120k lux | Ubiquitous drivers; gain/integration time managed in firmware | $1.20 | 6,113 |
| OPT4001 | ~0.0004–83k lux | Auto-ranging, best human-eye match and IR rejection | $1.99 | 2,835 |
| LTR-303ALS | 0.01–64k lux | Cheapest | $0.55 | 11,739 |
| BH1750 | 1–65k lux | Old classic, coarse resolution | $0.96 | 29,957 |

**Recommendation: VEML7700** (OPT4001 if we want less firmware fiddling). The sensor needs a clear view of the room: top side of the board plus a window or light pipe in the enclosure. Readings depend heavily on where the device sits, so treat them as "relative daylight in this spot", not a calibrated room illuminance.

## 5. Optional: microphone

Goal: detect piano playing outside quiet hours → a sound-level measurement, not audio recording.

| Part | Interface | Notes | Price | Stock |
| --- | --- | --- | --- | --- |
| **ICS-43434** | I2S | De-facto standard for ESP32 sound-level meters; works on any ESP32 | $4.25 | 458 |
| T3902 | PDM | Cheaper; requires PDM receive support on the C5 — **to be verified** | $1.56 | 6,125 |
| T5838 | PDM | Has acoustic wake-up for battery designs | $3.37 | 5 |
| INMP441 / SPH0645 | I2S | Common on breakouts, but end-of-life / not stocked | — | 0 |

**Recommendation: ICS-43434.** It is a bottom-port part, so the PCB needs a small hole under it (no issue for the fab).

Firmware implications worth knowing now:

- Sound monitoring means the MCU samples **continuously** and publishes aggregates (e.g. equivalent level per 10 s or per minute). That rules out deep sleep and is one reason the mic variant cannot run from a battery.
- Loudness alone cannot tell a piano from a vacuum cleaner or a TV. A handful of frequency-band energies would allow a simple "tonal/piano-like" classifier later. The hardware is the same either way.
- Privacy: only levels/features leave the device, never audio.
- Absolute dB(A) values need a one-time calibration against a reference meter; relative levels work out of the box.

**One board or two variants?** Light + mic add about $5.50. Suggestion: design one PCB and decide per order whether to populate them (assembly variants), rather than maintaining two layouts.

## 6. Power

### USB (first revision)

- USB-C receptacle (16-pin, e.g. TYPE-C-31-M-12, C165948) with 5.1 kΩ CC pull-downs and ESD protection (USBLC6-2SC6); data lines go straight to the C5's native USB.
- 5 V → 3.3 V: the C5 draws up to ~380 mA peaks when transmitting on 5 GHz and the SCD41 adds ~200 mA pulses, so the regulator should be rated ≥ 1 A.
  - A **buck converter** (e.g. TPS62A01, C5157937, $0.07) wastes far less heat than an LDO — relevant because regulator heat ends up in the temperature reading.
  - Sensirion recommends a clean LDO-regulated supply for the gas sensors; a small separate LDO from 5 V for the sensor rail is a cheap way to get both. To be settled in the schematic phase.

### Battery — is it sensible?

Rough daily energy budget at a 5-minute reporting interval (estimates):

| Consumer | Avg. draw | Per day |
| --- | --- | --- |
| Wi-Fi wake-up + MQTT publish (~2 s at ~90 mA, 288×/day) | — | ~14 mAh |
| ESP32-C5 deep sleep (~12 µA) | 12 µA | ~0.3 mAh |
| SHT45 | negligible | ~0 |
| SCD41, single-shot every 5 min | ~0.5 mA | ~12 mAh |
| STCC4, single-shot | < 0.1 mA | ~2.4 mAh |
| SGP41 (heater must run continuously) | ~3 mA | ~72 mAh |
| Microphone monitoring (MCU awake) | tens of mA | 500+ mAh |

What that means for a 2,000 mAh LiPo:

- T/RH + CO2 only: **2–4 months**. Feasible.
- Adding the SGP41: **~3 weeks**. Marginal.
- Adding continuous sound monitoring: **a few days**. Not sensible.

**Conclusion:** battery operation is only sensible for a reduced sensor set (T/RH + CO2, no VOC, no mic), and would favour the STCC4 and Thread/Zigbee/BLE over Wi-Fi. That is effectively a different product. Recommendation: build revision A as USB-only, and treat a battery version as a separate later variant rather than compromising this one. Parts for it are readily available when the time comes (BQ24074 power-path charger, MAX17048 fuel gauge — both stocked).

## 7. What else would be interesting to have?

Ranked by value for effort:

**Worth adding now (cheap, no downside)**

- **Barometric pressure** — BMP580, $1.21. Already in the proposal.
- **RGB status LED** (WS2812B-2020, $0.09) — provisioning/connection state, and optionally a CO2 "traffic light". With the light sensor it can auto-dim or switch off at night.
- **User button** — re-enter the captive portal / factory reset without reflashing. Plus the usual BOOT and RESET buttons.
- **Qwiic / STEMMA QT connector** (4-pin JST-SH on the I2C bus) — plug-in expansion for future sensors with zero soldering.
- **Thread / Zigbee / Matter and BLE** — free with the C5. BLE could also serve as an alternative provisioning path or a Bluetooth proxy for Home Assistant.

**Worth providing a connector for, populate later**

- **Particulate matter (PM2.5)** — the one major air-quality metric the proposal lacks; relevant for cooking, candles, wood stoves, or urban/wildfire smoke. PM sensors are fan-based modules connected by cable (Sensirion SPS30 / SEN6x), so the board would only carry a 5 V + I2C connector (JST-GH) and the module plugs in. Adds ~$25–35 and enclosure volume.
- **Presence / occupancy** — a 24 GHz mmWave radar module (HLK-LD2410, ~$5.50) on a UART header. Lets you correlate CO2 with occupancy and is useful for home automation. Changes the enclosure requirements.

**Probably not worth it**

- **Formaldehyde** (SFA40, $23) — only interesting after renovation or with lots of new furniture.
- **Small display** (e-paper/OLED) — nice, but adds heat (OLED), cost and enclosure complexity; the data lives in MQTT anyway. Could ride on an expansion header later.
- **Buzzer, IR blaster** — niche.
- **CO or radon** — these are safety measurements; use certified dedicated devices instead.

## 8. Manufacturing notes

- All proposed parts are SMD and in JLCPCB's assembly library (as "extended" parts, which carry a small one-time loading fee each). The C5 module is the only sourcing risk.
- Gas and humidity sensors are sensitive to flux, cleaning solvents and conformal coating — the assembly order should specify **no board wash**. Sensirion's handling instructions also call for avoiding VOC exposure after soldering.
- The SCD41 and the bottom-port microphone have reflow/handling constraints listed in their datasheets (single reflow pass preferred, on the last-reflowed side).
- An enclosure is not optional for good readings (airflow, sunlight shielding, ESD protection of the sensor openings). Its design should start together with the board outline, not after.

## 9. Open questions

1. **MCU sourcing:** accept the ESP32-C5 with pre-order/global sourcing, or fall back to the in-stock ESP32-C6 (no 5 GHz)?
2. **Air quality set:** agree on SHT45 + SCD41 + SGP41 + BMP580? Or the cheaper STCC4 for CO2 / drop the SGP41?
3. **Light + mic:** one PCB with assembly variants (suggested), or always populated?
4. **Extras:** status LED, user button, Qwiic connector (suggested yes); PM and radar connectors (your call).
5. **Quantity and budget** per board — affects part grades and assembly fees.
6. **Enclosure:** 3D-printed custom case? Wall-mounted or desk-standing? This drives board shape and sensor placement.
7. **Firmware framework** (custom ESP-IDF vs. ESPHome) — affects nothing in hardware except confirming driver availability; can wait.

## Sources

- Espressif: [ESP32-C5 mass production announcement](https://www.espressif.com/en/news/ESP32-C5_Mass_Production), [product page](https://www.espressif.com/en/products/socs/esp32-c5), [ESP-IDF current consumption guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c5/api-guides/current-consumption-measurement-modules.html)
- [CNX Software: ESP32-C5 mass production](https://www.cnx-software.com/2025/04/30/esp32-c5-mass-production-esp32-c5-devkitc-1-board/), [XIAO ESP32-C5](https://www.cnx-software.com/2026/01/16/xiao-esp32-c5-a-tiny-usb-c-iot-board-with-dual-band-wifi-6-bluetooth-5-0-le-zigbee-and-thread-connectivity/)
- [ESPHome on ESP32-C5 (Home Assistant community)](https://community.home-assistant.io/t/esp32-c5-and-esphome/920704), [Seeed: XIAO ESP32-C5 with Home Assistant](https://wiki.seeedstudio.com/xiao_esp32c5_homeassistant/)
- Sensirion: [STCC4 product page](https://sensirion.com/products/catalog/STCC4), [STCC4 design-in guide](https://sensirion.com/media/documents/4B786C73/68E5EE93/CD_AN_STCC4_Design-In_Guide_D1_1.pdf), [STCC4 datasheet](https://cdn.soselectronic.com/productdata/dd/9f/50d5ffc9/stcc4-d-r3.pdf), [SCD4x datasheet](https://sensirion.com/resource/datasheet/scd40/scd41), [CO2 sensor flyer](https://sensirion.com/resource/flyer-co2), [humidity/temperature design guide](https://mouser.com/pdfDocs/sensirion-ht-design-guide.pdf)
- [Rutronik: CO2 sensors for indoor monitoring](https://www.rutronik.com/article/co2-sensors-for-interior-space-monitoring-precise-measurements-for-better-air-quality)
- [Adafruit STCC4 + SHT41 guide](https://learn.adafruit.com/adafruit-stcc4-and-sht41-co2-temperature-humidity-sensor?view=all), [SparkFun STCC4 breakout](https://www.sparkfun.com/sparkfun-co2-sensor-stcc4-sht40-qwiic.html), [ESPHome STCC4 component](https://esphome.io/components/sensor/stcc4/)
- Bosch Sensortec: [BME690 announcement](https://www.bosch-sensortec.com/en/news/bosch-unveils-robust-power-efficient-4-in-1-mems-air-quality-sensor-for-indoors.html); [BME688 vs BME690 comparison](https://esp32.co.uk/bme688-vs-bme690-what-changed/)
- [SGP40 vs SGP41 comparison](https://esp32.co.uk/sgp40-vs-sgp41-voc-nox-esp32-home-assistant/), [Sensirion IAQ solutions overview (DigiKey)](https://www.digikey.com/en/product-highlight/s/sensirion/indoor-air-quality-sensing-solutions)
- [TI: temperature sensor PCB layout guidelines](https://ti.com/lit/pdf/snoaa01)
- [ESP32 I2S sound level meter project](https://hackaday.io/project/166867-esp32-i2s-slm)
- JLCPCB assembly parts library, queried 2026-11-19 (stock and prices in the tables above)

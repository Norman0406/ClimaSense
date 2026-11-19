# ClimaSense

ESP32-based indoor environment sensor. Measures ambient data periodically and publishes it via MQTT to a broker. Wi-Fi credentials are configured through a captive portal served by the device.

The repository contains both the **hardware** (KiCad PCB) and the **firmware**.

## Language

- Everything in this repository is written in **English**: code, comments, commit messages, docs, schematic labels.
- Reply to the user in English, even if they write in German.

## Repository layout

```
hardware/   KiCad project (schematic, PCB, libraries, fabrication outputs)
firmware/   ESP32 firmware
docs/       Design notes, research, decisions
```

## Hardware ground rules

- EDA tool: **KiCad** (all design files live in `hardware/`, versioned as text).
- The board is **fully manufactured and assembled by a fab** (PCBA, e.g. JLCPCB / PCBWay). The user does not hand-solder.
  - Prefer parts that are stocked by the assembler's parts library (LCSC for JLCPCB). Record the LCSC / manufacturer part number for every BOM line.
  - SMD only where possible; avoid parts that need manual or through-hole assembly unless the fab offers it.
  - Keep fab outputs (Gerbers, BOM, CPL/position files) reproducible from the KiCad project.
- Power: **USB-C** first. Battery operation with charging is a possible later revision — don't block it in the layout, don't build it yet unless decided.
- Temperature/humidity accuracy matters: keep T/RH sensors thermally isolated from the ESP32, regulator and other heat sources (board edge, milled slots, no copper pour under them).

## Revision A configuration (decided — see `docs/decisions.md`)

- MCU: **ESP32-C6-WROOM-1-N8** (chosen for now; ESP32-C5 with 5 GHz was preferred but not sourceable at the fab).
- Sensors on I2C: **SHT45** (T/RH), **SCD41** (CO2), **SGP41** (VOC/NOx), **BMP580** (pressure).
- Extras: RGB status LED, Qwiic connector, two buttons (combined BOOT/user, and RESET), three bare UART test pads (TX, RX, GND).
- Programming: native USB of the C6 through the USB-C port, OTA when deployed. No USB-UART bridge, no pogo/Tag-Connect footprint.
- Not in revision A: ambient light sensor and microphone (deferred idea: detect piano playing outside quiet hours, log daylight), battery operation.
- The BME680 used on the breadboard prototypes is dropped.
- Quantity: at least 5 boards, assembled at JLCPCB.

## Working on the schematic

- KiCad 10 is installed at `C:\Program Files\KiCad\10.0` (`bin\kicad-cli.exe` for rule checks, netlist and PDF export).
- `python hardware/tools/check_schematic.py` — runs ERC, compares KiCad's netlist with the intended one, plots `hardware/build/climasense.pdf`. Run it after any schematic change.
- `python hardware/tools/gen_schematic.py` — regenerates and **overwrites** `hardware/climasense.kicad_sch`. Only use it while the schematic has not been edited by hand in KiCad; check `git log`/diff first. After layout starts, the `.kicad_sch` is the source of truth.
- Pin map, BOM with JLCPCB numbers and open layout points: `docs/hardware/schematic.md`.
- Footprints for ESP32-C6-WROOM-1, SGP41, BMP580 and the RGB LED are not in KiCad's library and still have to be created.

## Firmware ground rules

- Periodic measurement → publish via MQTT.
- Captive portal (SoftAP) for Wi-Fi provisioning.
- Framework not decided yet (see `docs/`).

## Decisions

Settled decisions live in `docs/decisions.md`; research and alternatives in `docs/research/`. Check there before re-opening a settled question, and update the relevant doc when a decision changes.

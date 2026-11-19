# ClimaSense

An ESP32-based indoor environment sensor. It periodically measures temperature, humidity and air quality (optionally also ambient light and sound level) and publishes the readings via MQTT. Wi-Fi is configured through a captive portal.

## Contents

| Folder | What |
| --- | --- |
| [`hardware/`](hardware/) | KiCad project for the PCB (designed for full fab assembly) |
| [`firmware/`](firmware/) | ESP32 firmware |
| [`docs/`](docs/) | Research and design decisions |

## Status

Early concept phase. See [`docs/research/hardware-options.md`](docs/research/hardware-options.md) for the component research.

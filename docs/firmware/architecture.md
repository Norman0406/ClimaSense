# Firmware architecture

Status: **agreed 2026-11-19**, before any sensor code exists. Framework and language are in [`../decisions.md`](../decisions.md).

## Reading the sensors

The sensors are read **continuously in the background**; publishing takes a snapshot of the latest values. Reading them only when publishing does not work, because of two of the four sensors:

| Sensor | Needs | Schedule |
| --- | --- | --- |
| **SGP41** (VOC/NOx) | A reading every second, each one compensated with the current T/RH. Sensirion's index algorithm assumes that 1 s rhythm and learns the room's baseline over hours. | Every 1 s tick |
| **SCD41** (CO2) | Single shot: command, wait 5 s, read. Accepts the ambient pressure for compensation. | Started every 5 minutes, collected 5 ticks later; pressure from the BMP580 |
| **SHT45** (T/RH) | On demand, about 8 ms. | Every tick (the SGP41 needs it); the publisher averages |
| **BMP580** (pressure) | On demand, a few ms. | Every tick, or every few ticks |

## Tasks

ESP-IDF already runs Wi-Fi, the network stack, the MQTT client and the HTTP server in tasks of their own. The firmware adds:

- **Sensor task.** The only code that touches the sensor I2C bus, so the sensors need no locking among themselves and network delays cannot disturb the SGP41's timing. Runs on a fixed 1 s tick (`vTaskDelayUntil`, no drift). Also owns recovery: when a sensor stops answering, it releases the bus pins, switches the sensor rail off and on (`SENS_EN`) and initialises the sensors again.
- **App task** (`app_main`). Wi-Fi, MQTT, captive portal, OTA, LED status, button events. Publishes on its own interval (decided with the MQTT step).
- **Handover:** one "latest readings" snapshot. The sensor task overwrites it, the app task copies it when it publishes (a FreeRTOS queue of length 1 with `xQueueOverwrite`/`xQueuePeek`, or a struct behind a mutex). No other shared state.
- **LED and button** run on the LEDC peripheral and a timer, not on tasks of their own.

## Components

```
firmware/
  main/                    app_main and top-level wiring
  components/
    board/                 pin map, supply rails, status LED, button
    sensors/               (step 3/4) bus access and the four drivers
    net/                   (step 5+) Wi-Fi, MQTT, portal, OTA
  test/host/               tests that run on the PC
```

Each component has its public headers in `include/<component>/` (included as `"board/led.h"`) and its sources and private headers in `src/`. Dependencies between components are declared in their `CMakeLists.txt`, so the build enforces the layering.

## Testing without hardware

Logic that does not touch hardware lives in headers and sources without ESP-IDF includes (for example `button_logic.h`, `led_logic.h`). `firmware/test/host/` compiles those for the PC and checks them with GoogleTest unit tests: press detection, LED colour balance, and later the sensor CRCs, conversions and command/response parsing, against the examples in the datasheets. The sensor drivers are written against a small I2C interface of our own, so the unit tests can check the bytes a driver sends and replay datasheet responses through a GoogleMock mock of that interface. GitHub Actions runs the unit tests and the ESP-IDF build on every push that touches `firmware/`.

Code that does touch hardware (LEDC duty on the pins, timers, the I2C driver against real sensors) can only be tested on a board; ESP-IDF's on-target test framework (Unity, run with `pytest-embedded`) is the tool for that once a board is at hand.

The host tests need a C++ compiler for the PC; on this machine that is g++ in WSL (`sudo apt install g++ cmake ninja-build`). Steps are in `firmware/README.md`.

Until the boards arrive there are no sensors to test against (no breakouts for these parts), and the dev board's model is not known yet; a board variant for it will be added once it is.

## Status LED and button

- **LED:** three LEDC PWM channels at 4 kHz, 10 bit, output inverted in the peripheral (the LED is active low, so duty 0 = off). Colours are gamma-corrected and each channel is scaled so that equal values look about equally bright. The scale factors come from the datasheet estimate in `docs/hardware/schematic.md` (green ~21 mcd, red ~13 mcd, blue ~8 mcd at full current, ±30 %) and are to be checked by eye on the real board.
- **Button** (BOOT/user, IO9, low when pressed): polled every 10 ms, debounced over 30 ms. A press released before 3 s is a **short press**; holding it for 3 s gives a **long press** at that moment (the release afterwards gives nothing), so the LED can confirm while the button is still held. Long press opens the Wi-Fi setup portal (step 7). Holding BOOT while pressing RESET still enters USB download mode; that happens in the chip's ROM, before the firmware runs.

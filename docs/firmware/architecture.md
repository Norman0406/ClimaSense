# Firmware architecture

Status: **agreed 2026-11-19**, before any sensor code exists. Framework and language are in [`../decisions.md`](../decisions.md).

## Reading the sensors

The sensors are read **continuously in the background**; publishing takes a snapshot of the latest values. Reading them only when publishing does not work, because of two of the four sensors:

| Sensor | Needs | Schedule |
| --- | --- | --- |
| **SGP41** (VOC/NOx) | A reading every second, each one compensated with the current T/RH. Sensirion's index algorithm assumes that 1 s rhythm and learns the room's baseline over hours. Conditioning command for the first 10 s after power-up (no longer: it can damage the sensor). | Every 1 s tick, after the SHT45 of the same tick; conditioning for the first 10 ticks after boot |
| **SCD41** (CO2) | Single shot: command, wait 5 s, read. Accepts the ambient pressure for compensation. | Started every 5 minutes, collected 6 ticks later (`SingleShotSchedule`); pressure from the BMP580 |
| **SHT45** (T/RH) | On demand, about 8 ms. | Every tick (the SGP41 needs it); the publisher averages |
| **BMP580** (pressure) | On demand, a few ms. | Every tick, or every few ticks |

**CO2 every 5 minutes, kept on 2026-11-20 after asking whether it could be faster.** The SCD41 can measure every 5 s (periodic, ~15 mA), every 30 s (low-power periodic, ~3.2 mA) or in single shots as often as every 5 s. Single shot every 5 minutes (~0.45 mA) was chosen for accuracy rather than energy: the SCD41 is the largest heat source next to the SHT45, and its automatic self-calibration is tuned for exactly this interval in single-shot mode, so nothing has to be written to its EEPROM. The cost is a slow reaction (an opened window shows up to 5 minutes late). Revisit after step 10 has measured the SHT45's self-heating: 30 s low-power periodic mode is the alternative if faster CO2 values are wanted (about 8 mW more, self-calibration unchanged).

## Tasks

ESP-IDF already runs Wi-Fi, the network stack, the MQTT client and the HTTP server in tasks of their own. The firmware adds:

- **Sensor task.** The only code that touches the sensor I2C bus, so the sensors need no locking among themselves and network delays cannot disturb the SGP41's timing. Runs on a fixed 1 s tick (`vTaskDelayUntil`, no drift). Also owns recovery: when a sensor stops answering, it releases the bus pins, switches the sensor rail off and on (`SENS_EN`) and initialises the sensors again.
- **App task** (`app_main`). Wi-Fi, MQTT, captive portal, OTA, LED status, button events. Publishes on its own interval (decided with the MQTT step).
- **Sensor bus:** on the ESP32-C6's low-power I2C controller (`LP_I2C_NUM_0`), which ESP-IDF's normal I2C master driver supports and which is wired only to IO6/IO7, the sensor pins. 100 kHz, the SCD41's maximum. The task addresses nothing on the bus until 1 s after the rail came on (SCD41 start-up). The drivers see the bus only through `sensors::I2cBus` (probe, write, read, write-then-read), implemented by `EspI2cBus` on the chip and mocked in the unit tests. The normal I2C controller stays free for the Qwiic bus.
- **Sensor drivers** (`Sht45`, `Bmp580`, `Scd41`, `Sgp41`) are plain classes on top of `I2cBus`, without ESP-IDF calls and without waiting: each measurement is split into "start" and "read", and the sensor task does the waiting between them (`vTaskDelay`). That keeps them fully testable with the mock and lets the task decide how to overlap waits. Values are integers in milli-units (milli-degrees, milli-percent), so there is no floating point in the drivers and test values are exact. The three Sensirion sensors share one framing helper (`sensirion.h`: 16-bit words, each with a CRC-8). Short command waits of the SCD41 (1 ms) go through a delay function passed in; everything longer stays with the task.
- **Vendored code:** Sensirion's Gas Index Algorithm (release 3.2.2, the fixed-point variant because the ESP32-C6 has no FPU, BSD-3) is copied unchanged into `components/sensors/vendor/gas_index_algorithm/`, with its licence and a note of version, commit and file hashes, and wrapped for C++ by `gas_index.h`. Its learned state is lost at every reboot; the VOC part can save and restore it (`GasIndexAlgorithm_get_states`/`set_states`), planned for step 9.
- **Handover:** one "latest readings" snapshot. The sensor task overwrites it, the app task copies it when it publishes (a FreeRTOS queue of length 1 with `xQueueOverwrite`/`xQueuePeek`, or a struct behind a mutex). No other shared state.
- **LED and button** run on the LEDC peripheral and a timer, not on tasks of their own.

## Components

```
firmware/
  main/                    app_main and top-level wiring
  components/
    board/                 pin map, supply rails, status LED, button
    diagnostics/           build fingerprint, last log lines across resets, crash dump report
    settings/              settings store: NVS over build defaults, device name
    portal/                setup portal: DNS answers, form, pages, access point and web server
    sensors/               (step 3/4) bus access and the four drivers
    net/                   Wi-Fi, network time, settings record (step 5); MQTT, portal, OTA later
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

## Network and settings

- **Settings are records, the build only provides defaults.** The Wi-Fi code gets a `net::NetSettings` (network name, password, country, time server, time zone; fixed-size, no heap) and never reads build settings itself. `net::default_settings()` fills it from the Kconfig menu "ClimaSense network", whose values come from the git-ignored `firmware/sdkconfig.defaults.local`. From step 7 on, the captive portal stores settings in NVS, which take precedence; it checks them with `net::validate()` first. The MQTT settings in step 6 follow the same pattern.
- **Settings store** (`components/settings`): each settings record is loaded at start from NVS (namespace `settings`, one entry per field, so fields can be added without migration) over the build defaults. A stored field wins even when empty; a stored set that fails validation, or a value too long for its field, is ignored as a whole and the build defaults are used, with a log line saying so. Saving validates first and writes nothing if anything is invalid. Load and save are plain logic against a small `KvStore` interface, tested with an in-memory store; `NvsStore` is the chip's implementation. Records so far: `net::NetSettings` and `settings::DeviceSettings` (the device name).
- **Captive portal** (`components/portal`, step 7): opens on first boot (no network configured) or on a 3 s button press; a short press closes it, and so does a 10-minute timer. The station keeps running next to an open access point `ClimaSense-<id>` (APSTA, on the station's channel), and its reconnect attempts pause meanwhile so it does not leave that channel. A DNS task answers every A query with the device's address (other types get an empty answer, so clients use IPv4; TTL 60 s), DHCP announces the portal address (option 114, RFC 8910), and the web server redirects every unknown path, including the portal checks of Android, iOS and Windows, to the page with a `303` and a body (iOS needs the body). The page lists nearby networks (scanned when setup opens and on request), and the device name, country, time server and time zone; saving checks the form with the same rules (`apply_form`), stores it through the settings store and restarts. An empty password field keeps the stored password for the same network; a new network needs its password or "open network" ticked. Passwords are never written into a page; everything from outside (scanned names, the user's input) is HTML-escaped. DNS answers, form parsing and checks, pages and the network list are pure and unit-tested; the access point, sockets and web server are not testable without a board. The LED blinks blue while setup is open.
- **Wi-Fi station** (`net/wifi.h`): starts in the background from `app_main` after NVS is initialised; with no network configured it stays off and says so. Country `CH` (channels 1-13), not taken over from the access point. WPA2, and WPA3 where the router offers it; all channels scanned, the strongest access point chosen. Reconnects with pauses of 1, 2, 4 ... 60 s (`net/backoff.h`), back to 1 s once connected. Power save stays at ESP-IDF's default (modem sleep) for less heat. Host name `climasense-` plus the last three MAC bytes (`net/hostname.h`).
- **Network time:** SNTP from `ch.pool.ntp.org`, started at the first connection and resyncing on its own; time zone Europe/Zurich with daylight saving time. The log keeps its milliseconds-since-boot timestamps; real time is for the MQTT messages.

## Debugging

Decided 2026-11-20. The device hangs on a USB charger, so nothing reads its USB console; what happened before a reset has to survive the reset.

- **Logging:** ESP-IDF's `ESP_LOGx` with one tag per module, INFO and above, milliseconds since boot. Output goes to the native USB console (`idf.py monitor`).
- **Last log lines across a reset:** every log line also goes into a 2 KB ring buffer in RTC memory (`RTC_NOINIT_ATTR`), which keeps its content across a software reset, panic or watchdog reset, but not a power cut. At the next start the firmware prints them as "last ... bytes of log before the reset" and keeps a copy for publishing. After a power-on or brownout the buffer is discarded. The log hook only formats the line and copies it in a critical section; it never sends anything, so it cannot deadlock inside Wi-Fi or MQTT code. Lines longer than 160 characters are kept shortened.
- **Crash dumps:** a panic (exception, failed assert or `ESP_ERROR_CHECK`, interrupt watchdog, task watchdog, which is set to panic) writes a core dump to the `coredump` partition (128 KB) and reboots. At the next start the firmware logs a summary: panic reason, task, PC, RISC-V cause registers, and the fingerprint of the build that crashed. The dump stays in flash until it has been reported (step 6 erases it after publishing); a later crash overwrites it.
- **Build fingerprint:** 16 hex characters of the app's ELF SHA-256, in the start-up banner and in every core dump. A backtrace or core dump decodes only with the `.elf` of exactly that build: the local `firmware/build/climasense.elf` for a build flashed from the PC, or the `firmware-<commit>` artifact that CI keeps for 90 days.
- **Partition table** (`firmware/partitions.csv`): NVS 24 KB, OTA data, PHY data, two 3 MB OTA app slots, core dump 128 KB, 1.75 MB free. Changing it on a deployed board needs a USB flash, so it already has what OTA (step 8) needs.

With MQTT (step 6): publish a boot report (reset reason, build, crash summary, the last log lines), send log lines of WARNING and above to a log topic with the level adjustable remotely, then erase the reported core dump. Optional later: upload the full core dump over HTTP, or forward the log topic to a log service from the broker side.

On the desk, the C6's USB port is also a JTAG debugger: `idf.py openocd` and `idf.py gdb` give breakpoints and single-stepping over the same cable.

# Firmware

ESP32-C6 firmware for ClimaSense: periodic measurements, MQTT publishing, captive-portal Wi-Fi provisioning.

Framework: **ESP-IDF 6.1, in C++** (see [`docs/decisions.md`](../docs/decisions.md)).

## Status

Step 5 of the plan below: all four sensors are read (into the log only; publishing comes with MQTT in step 6), and the device joins Wi-Fi and gets network time. Builds with ESP-IDF 6.1.1; **not yet run on hardware**. The unit tests run in GitHub Actions (all 111 passing at commit `3d04482`, 2026-11-20); they have not been run on this PC (no PC compiler installed here, see below).

What the firmware does now:

- prints a banner (version, chip, flash size, build fingerprint, reset reason) and a heartbeat every 5 s on the native USB console;
- after a reset that kept them, prints the last log lines from before the reset; after a crash, prints the core dump summary (see "After a crash");
- switches the sensor rail on and the Qwiic rail off, puts a pull-down on `BMP_INT`;
- shows red, green, blue and white on the status LED in turn at start (to check the LED and its colour balance by eye);
- BOOT button: a short press cycles the LED through off/red/green/blue/white, a long press (3 s) turns it blue and logs where the Wi-Fi setup portal will go;
- starts the sensor task: it waits until 1 s after power-up (the SCD41's start-up time), opens the sensor bus on the low-power I2C controller at 100 kHz, probes 0x08–0x77 and logs which of the four sensors answered, any unexpected device, and a bus fault (scan stopped on a timeout). Then, once a second, it starts a measurement on the SHT45 (high precision, CRC-checked) and the BMP580 (forced mode, pressure oversampling 16x), waits 40 ms for both, reads both, and logs temperature, humidity and pressure every 10 s at INFO (every second at DEBUG). The BMP580 is reset and its chip ID and calibration memory checked at start; if that fails, it is retried every 10 s. The SCD41 takes a single-shot CO2 measurement every 5 minutes, compensated with the BMP580's pressure: the shot is started at the end of a tick, its result read 6 s later (up to 10 s), without holding up the other sensors; each CO2 value is logged at INFO. The SGP41 is conditioned for its first 10 s, then measured every second with the SHT45's humidity and temperature of the same tick for compensation; Sensirion's Gas Index Algorithm turns its raw signals into the VOC index (100 = the room's usual) and the NOx index (1 = the usual). Both indices are 0 for the algorithm's first 46 samples and keep learning the room's baseline for hours; they start again at every reboot (saving the learned state is planned for step 9). At start the task stops a periodic measurement the SCD41 may still be running after an ESP32 reset, and logs its serial number and whether its automatic self-calibration is on. A failing sensor is logged when it starts failing and when it works again, not every second.

- loads its settings (network, device name) from NVS over the build defaults and logs where each came from; nothing writes them yet (the captive portal, next, will);
- joins the Wi-Fi network from those settings (see "Wi-Fi settings"), reconnects with pauses of up to 60 s when the connection is lost, and logs its IP, channel and signal strength; then sets the clock from `ch.pool.ntp.org` (time zone Europe/Zurich). With no network configured it says so and runs without Wi-Fi.

How the firmware is structured, and why: [`docs/firmware/architecture.md`](../docs/firmware/architecture.md).

## Layout

```
CMakeLists.txt         project file
sdkconfig.defaults     settings that differ from ESP-IDF's defaults (versioned; sdkconfig is generated)
partitions.csv         flash layout: NVS, two OTA slots, core dump
main/main.cpp          entry point
components/board/      pin map (include/board/pins.h, mirrored from docs/hardware/schematic.md),
                       supply rails, status LED, button
components/sensors/    I2C interface (i2c_bus.h) and its ESP-IDF implementation, device list
                       and bus parameters (devices.h), address scan, the sensor task,
                       Sensirion framing and CRC (sensirion.h), SHT45, BMP580, SCD41 and
                       SGP41 drivers, the SCD41's single-shot schedule (single_shot.h),
                       the gas index wrapper (gas_index.h)
components/sensors/vendor/gas_index_algorithm/
                       Sensirion's Gas Index Algorithm 3.2.2, fixed-point, unchanged (BSD-3)
components/diagnostics/ build fingerprint, log ring buffer kept across resets, crash dump report
components/settings/   settings store: load from NVS over build defaults, validate, save;
                       device name record
components/net/        settings record and its rules (settings.h), Wi-Fi station, reconnect
                       pauses, host name, network time; Kconfig menu "ClimaSense network"
sdkconfig.defaults.local.example
                       template for the git-ignored file with the Wi-Fi credentials
test/host/             unit tests of the hardware-independent logic (GoogleTest), built for the PC;
                       data/ holds Sensirion's VOC test data
```

## Build and flash

ESP-IDF 6.1.1 is installed in `C:\Espressif` by Espressif's installation manager (EIM). Open an ESP-IDF shell: the PowerShell shortcut the installer put on the desktop, or in any PowerShell:

```powershell
. C:\Espressif\tools\Microsoft.v6.1.1.PowerShell_profile.ps1
```

Then:

```powershell
cd firmware
idf.py build
idf.py -p COM5 flash monitor
```

Replace `COM5` with the port Windows assigns to the board (Device Manager → Ports, "USB Serial Device"). Leave the monitor with `Ctrl+]`.

If the board does not show up or flashing fails: hold BOOT, press and release RESET, release BOOT. The chip then waits in download mode; flash again and press RESET afterwards.

## Wi-Fi settings

The network the device joins is a build setting until the captive portal (step 7) can set it on the device. The password must not go into the repository, so it goes in a git-ignored file:

1. Copy `firmware/sdkconfig.defaults.local.example` to `firmware/sdkconfig.defaults.local` and enter the network name and password.
2. Delete `firmware/sdkconfig` (or run `idf.py fullclean`): the settings are read when it is generated.
3. Build and flash as above. The log shows `connecting to "..."`, then `connected as climasense-xxxxxx, IP ...`.

`idf.py menuconfig` → "ClimaSense network" also works, but is lost when `sdkconfig` is regenerated. The same menu holds the country (CH), time server and time zone. Once the portal exists, values entered there take precedence over all of these.

## After a crash

A crash (exception, failed `ESP_ERROR_CHECK`, watchdog) writes a core dump to flash and reboots. At the next start the firmware logs, in the console:

- the last log lines before the reset;
- `core dump in flash ...` with the panic reason, task, PC, RISC-V cause registers and the `crashed build` fingerprint.

The banner shows the fingerprint of the running build (`build ...`). For the full backtrace and the state of every task, read the dump from the board over USB with the `.elf` of **the build that crashed**:

- built and flashed from this PC, and not rebuilt since: in `firmware/`, run
  ```powershell
  idf.py -p COM5 coredump-info
  ```
- a CI build: download the `firmware-<commit>` artifact from the workflow run on GitHub, then
  ```powershell
  esp-coredump --chip esp32c6 -p COM5 info_corefile path\to\climasense.elf
  ```

The dump stays in flash until the firmware erases it after reporting it (from step 6, after publishing it over MQTT); the next crash overwrites it.

For live debugging, the USB port is also a JTAG adapter: `idf.py openocd` in one ESP-IDF shell, `idf.py gdb` in another.

## Tests on the PC

`test/host/` holds unit tests for the logic that does not touch hardware (button press detection, LED colour balance; later sensor CRCs, conversions and command/response parsing). They use **GoogleTest** and **GoogleMock** (1.18.0, downloaded by CMake on the first configure and pinned by hash) and are built with the PC's own compiler, not ESP-IDF. The mocks are meant for the sensor drivers: a mock of the I2C interface checks the bytes a driver sends and replays responses from the datasheets.

On this machine that means g++ in WSL; install it once:

```powershell
wsl -d Ubuntu -- sudo apt install -y g++ cmake ninja-build
```

Then, from the repository root:

```powershell
wsl -d Ubuntu -- bash -c "cmake -S firmware/test/host -B firmware/build/host -G Ninja && cmake --build firmware/build/host && ctest --test-dir firmware/build/host --output-on-failure"
```

## Continuous integration

`.github/workflows/firmware.yml` runs on every push and pull request that touches `firmware/`:

- **Unit tests (PC):** configures, builds and runs `test/host` on Ubuntu.
- **Build (ESP-IDF 6.1.1):** `idf.py build` in Espressif's `espressif/idf:v6.1.1` Docker image, the same ESP-IDF version as on this PC. It keeps the build as the artifact `firmware-<commit>` for 90 days: the `.elf` (to decode crashes of that build), the flash images and `flash_args`.

When ESP-IDF is updated here, update the image tag there too.

## Plan

1. Skeleton: builds, flashes over native USB, logs over USB, pin map in code.
2. Board basics: rail enables, `BMP_INT` pull-down, RGB LED with PWM, BOOT button with short and long press.
3. I2C bus on the low-power controller, address scan.
4. Sensors one at a time: SHT45, BMP580, SCD41 (single shot every 5 min), SGP41 (1 Hz, index algorithm).
5. Wi-Fi with fixed credentials from a git-ignored file (done), network time; settings store (done).
6. MQTT publishing: 6a sensor values, 6b diagnostics (boot report, crash summary, log lines). **Comes after step 7** (decided 2026-11-20), so its settings go straight into the portal.
7. Captive portal for all settings (Wi-Fi, device name, later MQTT). **Next.**
8. OTA updates.
9. Hardening: watchdog, reconnects, sensor recovery by switching the sensor rail, LED status patterns.
10. Measure self-heating against a reference thermometer; only then consider sleep modes.

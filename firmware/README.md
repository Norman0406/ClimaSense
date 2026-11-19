# Firmware

ESP32-C6 firmware for ClimaSense: periodic measurements, MQTT publishing, captive-portal Wi-Fi provisioning.

Framework: **ESP-IDF 6.1, in C++** (see [`docs/decisions.md`](../docs/decisions.md)).

## Status

Step 2 of the plan below. Builds with ESP-IDF 6.1.1; **not yet run on hardware**. The unit tests compile but have not been run yet (no PC compiler installed here; GitHub Actions runs them once the workflow is pushed, see below).

What the firmware does now:

- prints a banner (version, chip, flash size, reset reason) and a heartbeat every 5 s on the native USB console;
- switches the sensor rail on and the Qwiic rail off, puts a pull-down on `BMP_INT`;
- shows red, green, blue and white on the status LED in turn at start (to check the LED and its colour balance by eye);
- BOOT button: a short press cycles the LED through off/red/green/blue/white, a long press (3 s) turns it blue and logs where the Wi-Fi setup portal will go.

How the firmware is structured, and why: [`docs/firmware/architecture.md`](../docs/firmware/architecture.md).

## Layout

```
CMakeLists.txt         project file
sdkconfig.defaults     settings that differ from ESP-IDF's defaults (versioned; sdkconfig is generated)
main/main.cpp          entry point
components/board/      pin map (include/board/pins.h, mirrored from docs/hardware/schematic.md),
                       supply rails, status LED, button
test/host/             unit tests of the hardware-independent logic (GoogleTest), built for the PC
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
- **Build (ESP-IDF 6.1.1):** `idf.py build` in Espressif's `espressif/idf:v6.1.1` Docker image, the same ESP-IDF version as on this PC.

When ESP-IDF is updated here, update the image tag there too.

## Plan

1. Skeleton: builds, flashes over native USB, logs over USB, pin map in code.
2. Board basics: rail enables, `BMP_INT` pull-down, RGB LED with PWM, BOOT button with short and long press.
3. I2C bus on the low-power controller, address scan.
4. Sensors one at a time: SHT45, BMP580, SCD41 (single shot every 5 min), SGP41 (1 Hz, index algorithm).
5. Wi-Fi with fixed credentials from a git-ignored file.
6. MQTT publishing.
7. Captive portal for Wi-Fi setup.
8. OTA updates.
9. Hardening: watchdog, reconnects, sensor recovery by switching the sensor rail, LED status patterns.
10. Measure self-heating against a reference thermometer; only then consider sleep modes.

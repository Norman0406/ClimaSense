# Firmware

ESP32-C6 firmware for ClimaSense: periodic measurements, MQTT publishing, captive-portal Wi-Fi provisioning.

Framework: **ESP-IDF 6.1, in C++** (see [`docs/decisions.md`](../docs/decisions.md)).

## Status

Step 1 of the plan below: a skeleton that builds (checked with ESP-IDF 6.1.1), starts, prints a banner (version, chip, flash size, reset reason) and a heartbeat every 5 s over the native USB console.

## Layout

```
CMakeLists.txt       project file
sdkconfig.defaults   settings that differ from ESP-IDF's defaults (versioned; sdkconfig is generated)
main/main.cpp        entry point
main/board.h         pin map and I2C addresses, mirrored from docs/hardware/schematic.md
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

## Plan

1. Skeleton: builds, flashes over native USB, logs over USB, pin map in `board.h`.
2. Board basics: rail enables, `BMP_INT` pull-down, RGB LED with PWM, BOOT button with short and long press.
3. I2C bus on the low-power controller, address scan.
4. Sensors one at a time: SHT45, BMP580, SCD41 (single shot every 5 min), SGP41 (1 Hz, index algorithm).
5. Wi-Fi with fixed credentials from a git-ignored file.
6. MQTT publishing.
7. Captive portal for Wi-Fi setup.
8. OTA updates.
9. Hardening: watchdog, reconnects, sensor recovery by switching the sensor rail, LED status patterns.
10. Measure self-heating against a reference thermometer; only then consider sleep modes.

# Firmware

ESP32-C6 firmware for ClimaSense: periodic measurements, MQTT publishing, captive-portal Wi-Fi provisioning.

Framework: **ESP-IDF 6.1, in C++** (see [`docs/decisions.md`](../docs/decisions.md)).

## Status

Steps 1-8 of the plan below: all four sensors are read and published over MQTT every 60 s together with a boot report and log lines, the device joins Wi-Fi and gets network time, and every setting can be changed in the setup portal. Builds with ESP-IDF 6.1.1; **not yet run on hardware**. The unit tests run in GitHub Actions (all 185 passing at commit `44cf4d1`, 2026-11-20); they have not been run on this PC (no PC compiler installed here, see below).

What the firmware does now:

- prints a banner (version, chip, flash size, build fingerprint, reset reason) and a heartbeat every 5 s on the native USB console;
- after a reset that kept them, prints the last log lines from before the reset; after a crash, prints the core dump summary (see "After a crash");
- switches the sensor rail on and the Qwiic rail off, puts a pull-down on `BMP_INT`;
- shows red, green, blue and white on the status LED in turn at start (to check the LED and its colour balance by eye);
- BOOT button: a short press cycles the LED through off/red/green/blue/white, a long press (3 s) turns it blue and logs where the Wi-Fi setup portal will go;
- starts the sensor task: it waits until 1 s after power-up (the SCD41's start-up time), opens the sensor bus on the low-power I2C controller at 100 kHz, probes 0x08–0x77 and logs which of the four sensors answered, any unexpected device, and a bus fault (scan stopped on a timeout). Then, once a second, it starts a measurement on the SHT45 (high precision, CRC-checked) and the BMP580 (forced mode, pressure oversampling 16x), waits 40 ms for both, reads both, and logs temperature, humidity and pressure every 10 s at INFO (every second at DEBUG). The BMP580 is reset and its chip ID and calibration memory checked at start; if that fails, it is retried every 10 s. The SCD41 takes a single-shot CO2 measurement every 5 minutes, compensated with the BMP580's pressure: the shot is started at the end of a tick, its result read 6 s later (up to 10 s), without holding up the other sensors; each CO2 value is logged at INFO. The SGP41 is conditioned for its first 10 s, then measured every second with the SHT45's humidity and temperature of the same tick for compensation; Sensirion's Gas Index Algorithm turns its raw signals into the VOC index (100 = the room's usual) and the NOx index (1 = the usual). Both indices are 0 for the algorithm's first 46 samples and keep learning the room's baseline for hours; they start again at every reboot (saving the learned state is planned for step 9). At start the task stops a periodic measurement the SCD41 may still be running after an ESP32 reset, and logs its serial number and whether its automatic self-calibration is on. A failing sensor is logged when it starts failing and when it works again, not every second.

- loads its settings (network, device name) from NVS over the build defaults and logs where each came from;
- publishes the sensor values over MQTT every 60 s (see "MQTT"), with Home Assistant discovery if switched on; at each start a boot report (with the crash summary after a crash), and WARNING-and-above log lines;
- installs updates over the air, from a URL sent over MQTT or uploaded in the setup portal; only signed images, with rollback (see "Updating");
- opens the setup portal on first boot (no network configured) or on a 3 s press of the BOOT button; see "Setting up a device";
- joins the Wi-Fi network from those settings (see "Wi-Fi settings"), reconnects with pauses of up to 60 s when the connection is lost, and logs its IP, channel and signal strength; then sets the clock from `ch.pool.ntp.org` (time zone Europe/Zurich). With no network configured it says so and runs without Wi-Fi.

How the firmware is structured, and why: [`docs/firmware/architecture.md`](../docs/firmware/architecture.md).

## Layout

```
CMakeLists.txt         project file
version.txt            firmware version (x.y.z); raise it for every release
sdkconfig.ci           added in CI: unsigned images (CI has no signing key)
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
components/portal/     setup portal: DNS answers, form parsing and checks, HTML pages (pure,
                       tested), and the access point / DNS / web server around them
components/telemetry/  MQTT: settings record and rules, state message and Home Assistant
                       discovery (pure, tested), the client on espressif/mqtt
components/ota/        updates: version and command logic, trial guard (pure), download, upload
components/net/        settings record and its rules (settings.h), Wi-Fi station, reconnect
                       pauses, host name, network time; Kconfig menu "ClimaSense network"
dependencies.lock      registry components ESP-IDF resolved (espressif/mqtt), versioned
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

## Signing key

Firmware images are signed; devices only install updates signed with the same key. Local builds sign with the private key at `C:\Users\<you>\Documents\climasense-keys\ota_signing_key.pem` (the folder next to the repository; `CONFIG_SECURE_BOOT_SIGNING_KEY` in `sdkconfig.defaults`, changeable in `sdkconfig.defaults.local`). It is not in git and must never be.

**Back the key up** (a password manager or an offline copy). Without it, devices accept no further updates over the air, only over USB. On a new PC, put the backup back in that place; without the key a local build stops with an error naming the missing file.

The key was created with ESP-IDF's tool (only ever needed once):

```powershell
espsecure generate-signing-key --version 2 --scheme rsa3072 ..\..\climasense-keys\ota_signing_key.pem
```

The first firmware on a board must itself be signed (a normal local build is), since updates are checked against the key in the running firmware. CI's builds are unsigned: fine for decoding crashes, refused as updates.

## Updating

Raise `version.txt` (for example to `0.2.0`), build, then either:

- **over MQTT:** serve `firmware/build/climasense.bin` over HTTP somewhere on the network, e.g. from the build folder:
  ```powershell
  python -m http.server 8000 --directory build
  ```
  and send the device its URL:
  ```powershell
  mosquitto_pub -h <broker> -u <user> -P <password> -t climasense/climasense-a1b2c3/set/ota -m http://<pc>:8000/climasense.bin
  ```
  Progress appears on `climasense/<id>/ota` (`mosquitto_sub -t 'climasense/+/ota' -v`). Append ` force` to the URL to install an older version.
- **in the setup portal:** open it (3 s on the BOOT button), section "Firmware", choose `climasense.bin`, "Update firmware".

The device restarts into the new firmware, which runs **on trial**: it is kept once it has been connected (to the broker, or to Wi-Fi without a broker) for at least 3 minutes, and the device returns to the previous firmware by itself if that has not happened after 10 minutes, or if it crashes. The boot report shows `"on_trial":true` meanwhile. Only signed images with the same or a newer version are installed.

## Setting up a device

A new board (no network configured) opens its setup portal by itself; any board opens it on a **3 s press of the BOOT button**. The LED then blinks blue.

1. On a phone or laptop, join the open Wi-Fi network **`ClimaSense-xxxxxx`** (the last six characters of the device ID).
2. The setup page usually opens by itself; otherwise open `http://192.168.4.1/`.
3. Pick the network from the list (or type it), enter its password, optionally a device name (e.g. "Living room"). Country, time server and time zone are under the fold-out at the bottom.
4. **Save and restart.** The device restarts and joins the network; the setup network disappears.

Leaving the password empty keeps the stored one, but only for the same network: a new network needs its password, or "Open network" ticked. Passwords are never shown. The portal closes after 10 minutes, or on a short press of the button; a lost network does not open it (decided, see `docs/decisions.md`).

## MQTT

Set the broker in the setup portal (section "MQTT broker"): host name or IPv4 address, port (1883), user name and password; under the fold-out the base topic (`climasense`) and the Home Assistant switch (off by default). With no broker set, nothing is sent.

Every 60 s the device publishes one JSON message to `<base>/<id>/state`, for example

```json
{"id":"climasense-a1b2c3","name":"Living room","time":"2026-11-20T14:05:00+01:00",
 "temperature_c":22.41,"humidity_pct":45.20,"pressure_hpa":963.12,"co2_ppm":812,"co2_age_s":140,
 "voc_index":104,"nox_index":1,"rssi_dbm":-58,"uptime_s":3600}
```

Temperature, humidity and pressure are the means of the last minute; VOC and NOx index the latest of that minute. CO2 is measured every 5 minutes: its latest value is repeated with its age `co2_age_s`, and dropped once older than 11 minutes. A value without data is left out, never sent as 0. `<base>/<id>/status` holds `online`, or `offline` once the device has gone (retained; MQTT last will).

mqtt-exporter turns every number into a Prometheus metric, labelled with the topic (so with the device ID). Home Assistant, with the switch on, finds the device with all values and units by itself.

**Diagnostics** on the same broker:

- `<base>/<id>/boot` (retained): the latest start: firmware, build, reset reason, the log lines from before the reset, and after a crash its summary. Read it with e.g. `mosquitto_sub -t 'climasense/+/boot' -v`.
- `<base>/<id>/log`: WARNING and above, at most 10 lines a minute, e.g. `{"level":"W","tag":"wifi","t_ms":81234,"msg":"disconnected (reason 201)"}`.
- `<base>/<id>/set/log_level`: publish `info` or `debug` (or `warn`, `error`, `none`) to change which lines are sent, until the next restart: `mosquitto_pub -t 'climasense/climasense-a1b2c3/set/log_level' -m info`.

mqtt-exporter subscribes to all topics by default; to keep these out of Prometheus, set its topic filter to `climasense/+/state`.

## Wi-Fi settings at build time

Build settings are only defaults; whatever was saved in the portal takes precedence. For development, a network can be built in so that a freshly flashed board joins it without the portal. The password must not go into the repository, so it goes in a git-ignored file:

1. Copy `firmware/sdkconfig.defaults.local.example` to `firmware/sdkconfig.defaults.local` and enter the network name and password.
2. Delete `firmware/sdkconfig` (or run `idf.py fullclean`): the settings are read when it is generated.
3. Build and flash as above. The log shows `connecting to "..."`, then `connected as climasense-xxxxxx, IP ...`.

`idf.py menuconfig` → "ClimaSense network" also works, but is lost when `sdkconfig` is regenerated. The same menu holds the country (CH), time server and time zone. Values saved in the portal take precedence over all of these; to get back to the build defaults, erase the flash (`idf.py erase-flash`) or the NVS partition.

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

With a broker configured, the crash summary also goes out in the boot report (`<base>/<id>/boot`), and the dump is erased once the broker has acknowledged it; without a broker it stays in flash until the next crash overwrites it. Read it over USB before it is reported, or keep the summary from the boot report.

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
6. MQTT publishing: 6a sensor values, 6b diagnostics (boot report, crash summary, log lines). Done.
7. Captive portal for all settings (Wi-Fi, device name, later MQTT). Done; MQTT fields come with step 6.
8. OTA updates. Done.
9. Hardening: watchdog, reconnects, sensor recovery by switching the sensor rail, LED status patterns.
10. Measure self-heating against a reference thermometer; only then consider sleep modes.

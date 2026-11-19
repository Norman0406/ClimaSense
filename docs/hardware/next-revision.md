# Ideas for the next iteration

Status: **ideas, not decisions.** Collected on 2026-11-19 after revision 1.0 was routed. Nothing here is implemented. Settled choices are in [`../decisions.md`](../decisions.md).

Most of these should wait for measurements on the first 1.0 boards; what to measure is listed [at the end](#what-to-measure-on-the-10-boards-first).

## 1. Is the ESP32-C6 the right microcontroller?

**Short answer: yes, for a USB-powered Wi-Fi device. Keep it.** A different microcontroller only becomes interesting if the device should run from a battery, and then the radio protocol changes with it, not just the chip.

What the device has to do — join Wi-Fi, publish over MQTT, serve a setup page, update itself over the air — needs a Wi-Fi radio with a mature software stack. In that class the ESP32-C6 module is hard to beat: about $4, antenna and radio certification included, stocked at JLCPCB, programmed and debugged over its own USB port.

| Alternative | What it would bring | Why not now |
| --- | --- | --- |
| **ESP32-C5** | Wi-Fi on 5 GHz as well as 2.4 GHz | The original preference; was out of stock at JLCPCB. Check stock again before each order. Footprint and pin assignment would need checking, it is not assumed to be a drop-in. |
| ESP32-C3 | Slightly cheaper | Older, no Thread/Zigbee radio, no low-power core. No benefit. |
| ESP32-S3 | More computing power, more pins | Needed for neither; draws more. Only relevant if the microphone idea returns with on-device audio analysis. |
| Nordic nRF52840 / nRF54L15 | Far lower power: microamps asleep, a few milliamps on air | **No Wi-Fi.** Talks Bluetooth, Thread or Zigbee, so it needs a gateway in the house, and MQTT happens on the gateway. The right choice for a coin-cell sensor, a different product from this one. |
| Raspberry Pi Pico W (RP2040) | Popular, easy | Worse sleep current, no advantage here. |

Two properties of the C6 keep later options open, which is the main reason to stay with it:

- It also has a **Thread/Zigbee radio**. A battery variant could switch protocol without changing the chip.
- It has a **second, low-power processor core** that can read I2C sensors on IO6/IO7 — the pins the sensors are already on — while the main core and the Wi-Fi radio sleep.

The microcontroller is also not what dominates this board's power use. Continuously measuring, the SCD41 averages 15 mA and the SGP41 3 mA; a sleeping ESP32 with a Wi-Fi publish every five minutes averages well under 1 mA.

## 2. Deep sleep, powering things up only when needed

**Short answer: possible, and mostly a firmware decision that revision 1.0 already supports. The reason to do it on a USB-powered device is accuracy, not energy:** every milliwatt not spent on the board is a milliwatt that does not warm the temperature and humidity sensor.

What each part allows:

| Part | Continuous | Reduced | Notes |
| --- | --- | --- | --- |
| **SCD41** (CO2) | 15 mA average, about 50 mW | 3.2 mA measuring every 30 s; **0.45 mA measuring once every 5 minutes** (single shot) | The largest heat source on the sensor side, and the easiest win: three commands, no hardware. Single-shot readings are a little noisier. Its automatic baseline correction is tuned for a 5-minute interval and is **not available** if the sensor is fully powered down between readings. |
| **SGP41** (VOC/NOx) | 3 mA, about 10 mW | Heater off: 34 µA, but see note | **The part that does not fit deep sleep.** Its heater has to stay on and it has to be read about once a second for Sensirion's index algorithm to work. After every power-off it must be conditioned again and the algorithm needs time to settle. Either it runs continuously or the VOC/NOx values are given up. |
| **SHT45** (T/RH) | — | Measures only when asked, idles below a microamp | Nothing to do. |
| **BMP580** (pressure) | — | Measures only when asked, idles around a microamp | Nothing to do. |
| **ESP32-C6** | Wi-Fi connected: roughly 20–30 mA average, 70–100 mW | Deep sleep with a 2 s wake-up every 5 minutes: under 1 mA average | The module is at the far end of the board from the sensors, so its heat matters less than the SCD41's. |

What deep sleep of the ESP32 costs:

- **No reaction between wake-ups.** Over-the-air updates, MQTT commands and the BOOT button's long press only work while it is awake.
- **USB logging and debugging drop out** whenever the chip sleeps, because the USB port is part of the chip.
- **The SGP41 still needs reading every second.** That is what the low-power core is for: it can keep sampling the sensors while the main core sleeps, and wake it to publish. This works on the 1.0 hardware because the sensors are on the low-power I2C pins, but it is the most involved piece of firmware in this list.

A sensible order for the 1.0 firmware:

1. Stay connected to Wi-Fi (simple, responsive), read the SHT45 and BMP580 on demand, run the SGP41 at 1 Hz, and run the **SCD41 in single-shot mode every 5 minutes**. That alone takes the sensor side from about 60 mW to about 12 mW.
2. Measure how far the SHT45 reads above a reference thermometer.
3. Only if that offset is still too large: sleep the ESP32 between publishes, with the low-power core doing the sampling.

Hardware that would matter for a battery variant but not on USB: the buck converter's 20 µA idle current, the 100 kΩ pull-up on `SENS_EN` (33 µA while the sensor rail is held off), and the sensor regulator's idle current.

## 3. Separate power control per sensor, or for a subset

**Short answer: not for every sensor. If anything is split off, it is the SCD41 alone — and only once measurements or a battery variant call for it.**

Revision 1.0 has one switch, `SENS_EN`, for the whole sensor rail. Its purpose is to recover a hung sensor, not to save power.

Why a switch per sensor does not pay off:

- **SHT45 and BMP580** idle at about a microamp and produce no heat when idle. A switch would save nothing.
- **SGP41** should not be switched off at all (see above). Today it loses its settled state whenever `SENS_EN` is used; a split would let it stay on while something else is power-cycled.
- **SCD41** is the only sensor where a hard switch has a case: it is the largest consumer, it draws pulses of up to 205 mA that the other sensors' supply and ground see, and powering it down fully is Sensirion's recommended mode for very long measurement intervals. But it also has a `power_down` command that gets most of the way with no hardware, and a hard power cycle disables its automatic baseline correction.

The catch with any partial power-down: **a chip without supply still hangs on the shared I2C bus.** Its inputs conduct into its dead supply pin and pull the bus down for everyone. A switched sensor therefore needs its own bus (or an isolator chip), not just a switch.

If it is done, the clean version is:

- two sensor rails: **SCD41 alone on a switched rail** with its own small regulator or load switch; SHT45, BMP580 and SGP41 on a rail that stays on;
- the SCD41 on **its own I2C pins** (two of the twelve unused GPIOs, two more pull-ups), so that powering it down cannot disturb the other sensors;
- keep one overall switch for recovering a hung bus.

Cost: one small regulator or load switch, two resistors, a capacitor, two GPIOs — well under a dollar, and one more part type with a loading fee. Benefit on USB power: independent recovery of the SCD41 and a quieter supply for the others. Benefit on battery: large.

## Smaller items noticed along the way

- **Status LED on 3.3 V.** The calculation in [`schematic.md`](schematic.md) covers a typical LED. A green or blue LED at the top of its forward-voltage range would be dim or dark on 3.3 V. If that shows up on the first boards, feed the green and blue LEDs from 5 V (their anodes are separate pads) or choose an LED specified with a lower maximum forward voltage.
- **Capacitance on the USB supply** is 12 µF nominal (10 + 1 + 1); the USB specification asks for at most 10 µF. Under voltage the real value is below that. A 4.7 µF buck input capacitor would settle it.
- **USB data lines** have no footprints for series resistors, which Espressif suggests reserving; their own development board leaves them out too.
- **USB D− reaches its ESD protection through a side branch.** On the 1.0 board the D− track runs from the ESP32 to the connector pads and then on for about 17 mm, round under the connector, to the protection part U1. D+ has U1 about 3 mm off the direct path. Both are protected and programming is unaffected (checked 2026-11-19), but the extra track makes the protection of D− slower against a fast static discharge. Route D− so that it passes U1 on the way between connector and ESP32, as D+ does; drawing both data lines by hand in `PREROUTED` in `gen_pcb.py` would also bring their lengths together (19 mm and 32 mm now, which does not matter at this USB speed).
- **Thermal tracks could be thinner.** The tracks across the slot and into the SHT45 tongue are 0.2 mm; 0.15 mm is allowed and would remove a quarter of the copper that carries heat. See the review in [`layout.md`](layout.md).
- Still deferred from before: ambient light sensor, microphone, battery operation, 5 GHz Wi-Fi.

## What to measure on the 1.0 boards first

1. SHT45 reading against a reference thermometer, with the SCD41 in continuous mode and in 5-minute single-shot mode. This decides how much of section 2 is needed.
2. The same with Wi-Fi permanently connected and with the ESP32 sleeping.
3. Sensor rail voltage at the SCD41 during a measurement pulse (oscilloscope).
4. Whether `SENS_EN` is ever needed in practice to recover a sensor.
5. LED brightness per colour.

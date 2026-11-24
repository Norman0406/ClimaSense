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

## 4. More sensors

Collected on 2026-11-20, after revision 1.0 was ordered. **Short answer: a light sensor on the board is cheap and harmless; everything else of value is a plug-in module, so the real question is a connector for it.** Stock and prices at JLCPCB were not checked for any of these.

| Sensor | What it adds | Fit for this board |
| --- | --- | --- |
| **Ambient light** (for example VEML7700, OPT3004) | Illuminance in lux: daylight log, lights on or off, blinds | Easy: a small I2C chip for about a dollar, no heat. Already deferred from 1.0. |
| **Particulates, PM2.5** (for example Sensirion SPS30 or SEN5x) | Fine dust from cooking, candles, smoke, outdoor air | The largest gap in what 1.0 measures. These are fan modules on a cable, need 5 V and cannot be reflowed: a connector, not a chip. |
| **Presence** (PIR, or a 24 GHz radar module) | Whether someone is in the room | Useful for automations and for reading the CO2 curve. Radar modules are plug-in parts with a serial port and their own supply. |
| **Microphone** (I2S MEMS) | Sound level; the idea of noticing piano playing outside quiet hours | Simple hardware, most of the work is firmware. It puts a microphone in a room, which guests may mind. |
| **Carbon monoxide** (electrochemical cell or a module such as Winsen ZE07-CO) | CO level as information, for a room with a fireplace | Roughly 5 to 25 USD plus a small amplifier. The cells hold liquid electrolyte and cannot be reflowed, so only as a plug-in module. See the warning below. |
| **Formaldehyde** (Sensirion SFA30) | Off-gassing from new furniture and flooring | Niche; a cable-connected module. |
| **Light colour** (for example AS7341) | Colour temperature, for lighting that follows the day | Niche. |

- **A CO reading on this board is information, never the alarm.** A certified CO alarm (EN 50291) has its own battery and sounder, an end-of-life warning, and works without Wi-Fi, broker or firmware. A room with a fireplace gets one of those regardless. The cheap heated type (MQ-7) is ruled out: inaccurate, and its heater draws about 150 mA next to the temperature sensor.
- **Left out:** radon (no chip-sized sensor), and anything with a heater near the SHT45.
- **Try before designing in.** Light and presence breakouts can be tried on revision 1.0 through the Qwiic connector. It supplies 3.3 V only, so the 5 V modules (particulates, radar, CO) need a second connector: 5 V behind the fuse, switched, with I2C or a serial port.
- **Wait for the measurements below.** How much the board warms the SHT45 decides how much power the sensor side can still take.

## 5. Should the board be more modular?

Discussed on 2026-11-20. **Not decided.** Two routes came out of it; the second is the direction preferred in that discussion, and whether it is worth its cost depends on how many devices and how many different rooms there will be.

### Route A: one board, modular at the edges

Keep the microcontroller, the supply and the four sensors on one board, and add connectors for what cannot be soldered on anyway: a second expansion connector with 5 V next to the Qwiic connector, and the light sensor on the board itself. Cheapest, and right for a handful of identical devices. Different rooms can still get different boards by leaving sensors off when ordering: a board with only temperature, humidity and pressure is about 28 USD cheaper, at no design cost, but it cannot be changed after assembly.

### Route B: a controller board with swappable sensor boards

One controller board (microcontroller, USB, supply) and sensor boards chosen by use, so that a room only gets the sensors it needs and a new sensor type does not touch the controller board.

**Side by side, not stacked.** The boards join edge to edge in one plane, through a right-angle plug on one board and a right-angle socket on the other, so that they sit flush. A stack was considered and dropped for the core sensors: it puts the controller's heat under the temperature sensor, traps air between the boards where the gas sensors need exchange, and brings copper over the antenna. Stacking stays an option for add-ons that mind none of that (a display, a radar module).

**The connector replaces the Qwiic connector** and carries:

| Pins | Purpose |
| --- | --- |
| Ground, twice | One return for the sensors, one for the 5 V loads |
| 3.3 V, switched | The quiet sensor supply. Its regulator stays on the controller board, away from the temperature sensor |
| 5 V, switched and current-limited | For particulate, radar and CO modules; it comes from behind the fuse |
| I2C bus 1 (IO6/IO7) | The core sensors, alone on their bus; the only pins the low-power core can use |
| I2C bus 2 | Add-ons, so that a misbehaving or unpowered part cannot pull the core sensors' bus down, and two parts with one address can coexist |
| Interrupt | Shared, open-drain, so several boards can use it |
| Serial TX and RX | Most 5 V modules talk serial. Point to point: one board in a chain can use it |

Pull-ups sit on the controller board only. Buying a Qwiic breakout and plugging it in stays possible through a sensor board that carries a Qwiic socket on bus 2; the simplest such board has nothing else on it.

**Daisy chain.** A sensor board can carry the plug on one edge and the socket on the opposite one and pass every line through, so boards line up in a row. What that needs:

- **No board-ID pin:** one pin cannot name several boards. The firmware finds out what is attached by asking the known I2C addresses, which it has to do anyway; the state message already leaves out values it does not have.
- **A supply budget.** Everything on the 3.3 V pin shares one regulator (500 mA; the SCD41 alone pulses to 205 mA), everything on 5 V shares the 0.75 A fuse.
- **An order.** Warm boards (anything on 5 V) go next to the controller, the board with the temperature and humidity sensor goes at the far end, and on the wall the row runs sideways so that no board sits above another's heat.
- **Mounting of its own for every board.** The connectors carry signals, not weight: a common board height, a common hole pattern, or a rail in the case.
- **No plugging in under power.**

**Open points:** which connector (surface-mount, right-angle, stocked at JLCPCB; pitch and pin count against the 34 mm board edge), the outline and hole pattern every board has to follow, and whether the first sensor board simply carries what revision 1.0 has.

**What it costs.** Every board design at JLCPCB repeats the fixed fees: in the order of 2026-11-20, setup and stencil alone were about 34 USD, plus loading fees for its parts and a minimum of five boards. Every connector is also one more place for a fault on a device meant to hang on a wall for years. Rough guide: Route B pays off from about three different room types or fifteen devices; below that, Route A with boards ordered partly populated is cheaper.

**What the 1.0 boards will tell:** if the SHT45 still reads too warm despite the slots (measurement 1 below), a separate sensor board is justified on accuracy alone, whatever the number of devices.

## 6. A display

Researched on 2026-11-22. **Not decided.** **Short answer: a 2.13" black-and-white e-paper panel with the SSD1680 controller (for example Good Display GDEY0213B74). It is the only kind that can show values without warming the SHT45. The runner-up is a Sharp memory LCD.** Either one needs board space that revision 1.0 does not have, and a new pin map, so the board that has it is revision 2.0 by the numbering rule in [`../decisions.md`](../decisions.md).

The deciding factor is heat. Section 2 aims to bring the sensor side down to about 12 mW, so a display that draws tens of milliwatts would cancel that work.

| Type | Heat | Readability | Verdict |
| --- | --- | --- | --- |
| Small TFT (for example ST7789) | Backlight alone roughly 50–150 mW (estimate) | Good, also in the dark | **No.** Several times the whole sensor budget, and its light is near the SGP41, which must not sit in bright light. |
| OLED (SSD1306, 0.91", 128 × 32) | Roughly 30–50 mW while lit (estimate, not from a datasheet) | Very good, but glows in a dark room | Only with a screen-off timeout. It burns in when it shows the same values for years. |
| Sharp memory LCD | 12 µW typical when static, 50 µW at one update a second (LS013B7DH03 datasheet) | Reflective, lower contrast, no light | Fine for heat, but small and hard to source. |
| **E-paper, 2.13"** | 10.5 mW for about 3 s per refresh: about 0.1 mW averaged with one refresh every 5 minutes. 3 µW in standby (Good Display) | Best in daylight, keeps the image without power, unlit at night | **Recommended.** |

### E-paper: GDEY0213B74 or similar

- 250 × 122 pixels, outline 59.2 × 29.2 × 1.0 mm, active area 48.6 × 23.7 mm. It fits the 34 mm board height.
- 3.3 V, SPI, 24-pin FPC with 0.5 mm pitch, SSD1680Z controller, rated for 0 to 50 °C.
- Full refresh 3 s, fast 1.5 s, partial 0.3 s (at 25 °C). CO2 and temperature change slowly, so an update every 1 to 5 minutes is enough. A full refresh about once an hour clears the ghosting that partial refreshes leave.
- The bare panel needs a boost circuit on the board for its driving voltages: an inductor, a MOSFET, three Schottky diodes, a sense resistor and about eight capacitors, some rated for 25 V. That list comes from Good Display's usual reference design and has not been checked against this panel's datasheet.
- Driver: ESP-IDF has no built-in e-paper driver. Espressif's registry component `espressif/esp_lcd_ssd1681` (version 0.1.0, about two years old) is written for the SSD1681 used in 1.54" 200 × 200 panels, not for the SSD1680. Community SSD1680 drivers exist; one of them (`cleishm/idfxx_epaper_ssd1680`) is C++23 and needs ESP-IDF 5.5 or later. The command set is short, so a driver of our own is a small job.
- A 1.54" 200 × 200 SSD1681 panel (for example GDEY0154D67, about 32 × 37 mm, from memory) would use Espressif's own component and needs less board, at the cost of a smaller picture.

### Memory LCD as the alternative

- LS013B7DH03: 1.28", 128 × 128, outline 26.6 × 30.3 mm, 2.7–3.3 V, 10-pin FPC into a connector (Sharp recommends SMK CFP-4610-0150F or Molex 51441-1093), -20 to +70 °C. LS011B7DH03: 1.1", 160 × 72, about 31.8 × 13.4 mm; its full datasheet was not read.
- Needs 3 or 4 pins (clock, data, chip select, plus COM toggle). The display has to be inverted at 54–65 Hz, either on its `EXTCOMIN` pin from a PWM output or by a bit in the serial data.
- Can redraw every second, for example as a clock. It is small and dimmer than e-paper.
- Out of stock at LCSC on 2026-11-22 (price from about 3.92 USD). It would come from DigiKey or Mouser and be sent to JLCPCB as a consigned part.

### What it changes on the board

- **Space.** The display needs about 60 × 30 mm of the top face that is neither the sensor island nor the antenna end. Revision 1.0 has none. Two ways: the controller side grows (the board ends up roughly 110 to 120 mm long), or the display goes on a board of its own, next to the controller or stacked on it ([section 5](#5-should-the-board-be-more-modular) allows a stack for a display). **Never over the sensor island**: a panel there blocks the air the sensors need and holds their heat.
- **Assembly.** JLCPCB fits the FPC connector (for example a 24-pin 0.5 mm part, extended, about 3 USD loading fee) and the boost circuit. The panel itself cannot be reflowed, so it is plugged into the connector by hand, with no soldering. The case has to hold the panel (it is glass) and needs a window for it.
- **Pins.** E-paper needs six: clock, data, chip select, data/command, reset and busy. Reset cannot be left out, because the SSD1680 only wakes from deep sleep through it. Only five are free: IO2 to IO5 and IO15. The sixth would come from the fallback serial port (IO16/IO17), if revision 1.0 shows that USB works, or from IO0/IO1, which gives up the crystal kept for a battery variant. **Busy goes on IO2 or IO3**: the panel drives that line, and IO4, IO5 and IO15 are start-up configuration pins. Keep `pins.h` and [`schematic.md`](schematic.md) in step.
- **Firmware.** An SPI driver, a display task with a refresh policy (partial updates, a full one every hour, none while the values have not changed) and a screen layout. The values are already in the state message.

### Try first

A 0.91" OLED breakout with a Qwiic connector (for example SparkFun's 128 × 32) plugs into revision 1.0's Qwiic connector without any hardware change, and ESP-IDF has a built-in SSD1306 driver. That is a cheap way to try out the screen layout and see whether a display is worth having. It also shows how much the OLED warms the SHT45, if it sits close by.

### Not checked yet

- LCSC prices with stock for the e-paper panels. Both listings seen were out of stock, among them a Waveshare 2.13" at 6.71 USD.
- The boost circuit against the panel datasheet, and the full LS011B7DH03 datasheet.
- The OLED and TFT heat figures are estimates, not datasheet values.

## 7. Parts on the room side of the board

Raised on 2026-11-24 (Norman). **Not decided.** On revision 2.0 every part faces the wall and only the panel faces the room ([`rev-2.0.md`](rev-2.0.md)). The idea: put the buttons and the LED, and perhaps the sensors, on the room side as well. **Short answer: for buttons and LED the gain is small and the board has to grow; for the sensors the gain may be real but is not measured, and it ends assembly on a hot plate. Measure on a 1.0 board first** (measurement 7 below).

What holds for any part on the room side:

- **Assembly at home.** The hot plate needs a bare, flat back. With parts on both sides, the second side is done with hot air or an iron, or the board goes into a small reflow oven. A second stencil is needed.
- **Assembly at JLCPCB.** Two-sided assembly repeats the fixed fees for the second side and, as far as known, needs the standard service instead of the economic one. **Not checked** against JLCPCB's current terms.
- **Scripts.** `gen_pcb.py` places every part on one side; `gen_fab.py` has no placement corrections for parts on the bottom side (JLCPCB counts their rotation differently); `check_pcb.py` renders the top only. The router already reads pads per layer.
- **Nothing under the panel.** The panel lies flat on the room side from x 10.8 to 70.0 and y 2.4 to 31.6.

### Buttons and LED

- **There is no room for them.** The panel leaves 2.4 mm above and below it. Left of it is the antenna, right of it the FPC slot, the strip for the sensor bus and the sensor island. So the board grows by about 5 to 6 mm in height for a strip above the panel, or in length; or the panel becomes the 1.54" one.
- **Gain:** a simpler case. A flexible tab and a window in its front, instead of a plunger from the top onto the side-push buttons and a light pipe for the LED.
- **Soldering:** both part types can be soldered by hand after the hot-plate pass, so this alone keeps home assembly possible.
- The top-edge arrangement of 2.0 already works without any of this, and the display takes over most of the LED's job.

### Sensors

- **What it might gain.** The sensors would see room air directly, not the air in the gap between board and wall, which follows the wall's temperature on an outside wall. The board would also stand between them and the warm air that rises from the ESP32 and the regulators. How much the wall side costs is not known.
- **The SCD41 allows one reflow pass, no hand soldering and no added flux** ([`ordering.md`](ordering.md)). On a hot plate the sensor side would have to be the side soldered on the plate, which leaves the ESP32, the USB connector and the regulators for hot air. In practice: a reflow oven, or boards assembled at JLCPCB with the sensor side soldered last.
- **The island is laid out again.** A part moved to the other side is mirrored. The hand-drawn copper of the island (the SCD41's supply link past its vent hole, the order of the tracks on the bridge and in the tongue's neck) has to be redone, and the 1.0 boards no longer prove the island's layout, only its circuit.
- **Light.** The SGP41 must not sit in bright light. Facing the wall it is shaded for free; facing the room the case needs a front grille that lets air through and no light.
- **Depth.** The SCD41 is 6.5 mm high, the panel 1.0 mm. The case's front is stepped, or the display sits about 5 mm behind it.
- **Route B of [section 5](#5-should-the-board-be-more-modular)** gets to the same place another way: a separate sensor board can face the room whatever the controller board does.

## Smaller items noticed along the way

- **Status LED on 3.3 V.** The calculation in [`schematic.md`](schematic.md) covers a typical LED. A green or blue LED at the top of its forward-voltage range would be dim or dark on 3.3 V. If that shows up on the first boards, feed the green and blue LEDs from 5 V (their anodes are separate pads) or choose an LED specified with a lower maximum forward voltage.
- **Capacitance on the USB supply** is 12 µF nominal (10 + 1 + 1); the USB specification asks for at most 10 µF. Under voltage the real value is below that. A 4.7 µF buck input capacitor would settle it.
- **USB data lines** have no footprints for series resistors, which Espressif suggests reserving; their own development board leaves them out too.
- **Input voltage of the two linear regulators.** The TLV75533 is rated for 5.5 V in operation and 6.0 V at most, and both sit directly behind the fuse. Plugging in a live USB-A-to-C cable makes the supply ring against the ceramic capacitors; with the fuse's resistance in the path the estimate is a peak of 5.8 to 5.9 V for a few microseconds. If the measurement on the first boards (below) shows more, use a pin-compatible regulator with a higher input rating; the Torex XC6227C in the next item is rated for 6.0 V in operation.
- **A regulator that blocks reverse current** would remove two warnings at once: no self-powered device on the Qwiic connector, and no feeding the sensor header's 3.3 V pin while the sensor side is joined. Checked on 2026-11-20 against its datasheet: Torex XC6227C331MR-G (JLCPCB C216640) has the TLV75533's pinout, blocks whenever the output is above the input (1.5 µA maximum), limits at 720 mA or more, and has a pull-down of 160–340 kΩ on its enable pin, which our 100 kΩ pull-up on `SENS_EN` overrides. It needs 2.2 µF of real output capacitance, so the Qwiic regulator's capacitor C16 would have to grow, and it has no fast output discharge. No noise figure was found in the datasheet. TI's TPS73633 also fits but blocks only while its enable pin is low; Richtek's RT9080 does not block at all. Not done for 1.0: a new part on both regulated sensor-side rails is a bigger risk to the first boards than what it guards against.
- **The BMP580 interrupt cannot wake the ESP32 from deep sleep.** It is on IO10; only IO0 to IO7 can wake the chip from deep sleep or be read by the low-power core. On revision 1.0 the interrupt therefore works while the chip is awake or in light sleep, and the low-power core has to poll the BMP580 instead. This only matters once deep sleep is used (section 2), and most for a battery variant. To change it, move `BMP_INT` to IO5 or IO4: same side of the module, 8 to 9 mm further from the sensors. Both are start-up configuration pins, which set a timing option of an interface this board does not use; confirm that in the ESP32-C6 datasheet before moving the signal. IO0 and IO1 are nearer but are the 32 kHz crystal pins kept free for a battery variant; IO2 and IO3 are at the far corner of the module. Considered on 2026-11-20 and left for later, because it needs the whole board routed again. By the numbering rule in [`../decisions.md`](../decisions.md) this changes the pin map, so the board that has it is revision 2.0.
- **Thermal tracks could be thinner.** The tracks across the slot and into the SHT45 tongue are 0.2 mm; 0.15 mm is allowed and would remove a quarter of the copper that carries heat. See the review in [`layout.md`](layout.md).
- Still deferred from before: battery operation, 5 GHz Wi-Fi. The ambient light sensor and the microphone are in [section 4](#4-more-sensors).

## What to measure on the 1.0 boards first

1. SHT45 reading against a reference thermometer, with the SCD41 in continuous mode and in 5-minute single-shot mode. This decides how much of section 2 is needed.
2. The same with Wi-Fi permanently connected and with the ESP32 sleeping.
3. Sensor rail voltage at the SCD41 during a measurement pulse (oscilloscope).
4. Whether `SENS_EN` is ever needed in practice to recover a sensor.
5. LED brightness per colour.
6. The 5 V rail at the regulators while a live USB-A-to-C cable is plugged in (oscilloscope, single shot): the peak must stay below 6.0 V.
7. The same board hung both ways on the same wall: parts facing the room, and parts facing the wall on spacers of about a centimetre. Compare the SHT45 against the reference thermometer, how fast temperature, humidity and CO2 follow a change in the room (a window opened), and the Wi-Fi signal strength. This decides [section 7](#7-parts-on-the-room-side-of-the-board) for the sensors and answers revision 2.0's open question about the antenna facing the wall.

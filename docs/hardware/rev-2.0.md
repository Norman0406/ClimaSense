# Revision 2.0 — e-paper display

Revision 1.0 plus a 2.13" e-paper panel. **Designed, reviewed, not ordered, not built.** This page describes the board as it is in [`hardware/rev-2.0/`](../../hardware/rev-2.0/). How it got here, including two earlier arrangements that no longer exist (panel on the back with its tail through a slot), is in [`rev-2.0-history.md`](rev-2.0-history.md). The design review of 2026-11-24 with its findings and their status is [`../../REVIEW.md`](../../REVIEW.md).

Revision 1.0's documents ([`schematic.md`](schematic.md), [`layout.md`](layout.md), [`footprints.md`](footprints.md), [`ordering.md`](ordering.md)) still hold for everything this page does not mention: supply, USB, sensors, the sensor island.

## State

As of 2026-11-25:

- Schematic: no ERC violation, the netlist as intended (93 parts with the 22 test pads; 71 are placed, 36 part types).
- Board: placed and routed by `gen_pcb.py` with `ROUTE_SEED` 2; five of twelve seeds route it completely. `check_pcb.py --require-routed`: no DRC violation, no difference to the schematic, no open connection. `audit_pcb.py` passed: no net crosses itself or has a loop, no track meets a pad off its centre lines; seven right-angle corners and eight jogs are listed. 241 vias.
- A plain run from scratch gives the same tracks as the batch of twelve seeds did (one to three of the ground patch vias land a few tenths of a millimetre elsewhere). The board in the repository is that plain run, with two silkscreen details changed afterwards with `--keep`, which leaves the copper alone.
- The pictures in [`../images/rev-2.0/`](../images/rev-2.0/) are of this board.
- Reviewed on 2026-11-24 ([`../../REVIEW.md`](../../REVIEW.md)): no error that stops the board from working. Of its findings, 1, 5, 7, 11, 13, 15 and most of 9, 16 and 17 are in this board; what is open is listed [below](#open-points).

Not done:

- **Revision 1.0 has not been powered yet.** Revision 2.0 reuses its USB circuit, both supplies, the module and the whole sensor island unchanged. Ordering 2.0 before 1.0 has run means ordering it with all of 1.0's open questions (review, finding 3).
- **Firmware:** `pins.h` is still the revision 1.0 pin map; there is no display driver and no way to tell the board revisions apart. **Revision 1.0 firmware must not be flashed onto a 2.0 board:** it would make IO10, which is `SENS_EN` here, an input with pull-down and hold the sensor regulator's enable pin at its threshold.
- **The frame and the case** are not designed; the frame's height is not settled (see [Panel, tail and frame](#panel-tail-and-frame)).
- **Order files:** `tools/gen_fab.py` is ready and writes them when they are needed; nothing is in `fab/` yet.

## Decisions

| Topic | Choice | Decided |
| --- | --- | --- |
| Display | Good Display GDEY0213B74: 2.13", 250 × 122, black and white, SSD1680, SPI, 24-pin tail at 0.5 mm pitch; 59.2 × 29.2 × 1.0 mm, 0 to 50 °C | 2026-11-22 |
| Driving voltages | Made on the board with the panel maker's boost circuit and charge pump; no extra chip | 2026-11-22 |
| Orientation | Component side faces the room, as on 1.0: sensors, antenna and display all face the room | 2026-11-24 |
| Panel | On the component side, on a printed frame that stands on the board, above the parts of the controller side | 2026-11-24 |
| Tail | Folds back under the panel in a half circle into J5. No slot through the board | 2026-11-24 |
| Pin order at J5 | Panel pin N on connector pin N | 2026-11-24 |
| Buttons | Two Alps SKRTLAE010 side-push switches on the top edge, pressed by plungers in the case | 2026-11-22 |
| Status LED | The LED of 1.0, 1.4 mm from the top edge; the case carries its light | 2026-11-22 |
| 32 kHz crystal | Dropped (no battery variant of this board): IO0 and IO1 are free for signals | 2026-11-22 |
| Sensor header J4, serial header J3 | Gone; test pads take over | 2026-11-22 |
| Test pads | All on the back, bare 1.0 mm pads with their names on the back silkscreen | 2026-11-24 |
| Assembly | **By JLCPCB**, as revision 1.0 (Norman, 2026-11-25). The earlier plan to assemble test revisions at home on a hot plate is dropped | 2026-11-25 |
| Case | Flat front, display behind a shallow bezel, a wall round the sensor area. Concept only: [`next-revision.md`](next-revision.md), section 7 | 2026-11-24 |

## Board

103 × 34 mm, two layers, 1.6 mm, all parts on one side. Seen from the component side as it hangs on the wall:

| Zone (x, mm) | Contents |
| --- | --- |
| 0 – 26 | ESP32-C6 module, antenna at the left edge; UART pads on the back |
| 26 – 48 | USB-C on the bottom edge, protection, fuse, buck converter, Qwiic connector and its regulator; the two buttons and the LED on the top edge; the I2C pull-ups at the start of the sensor bus |
| 48 – 62 | Display supply: seven capacitors in a row along the top, the six display lines in the middle, the boost circuit below them |
| 62 – 67 | Display connector J5, opening to the right |
| 67 – 76 | Room for the tail's fold; below it the sensor regulator U3 |
| 76 – 77.5 | Milled slot to the sensor island, with three bridges |
| 77.5 – 103 | Sensor island and SHT45 tongue, exactly as on 1.0 |

- The panel lies over x 10.8 to 70.0, y 2.0 to 31.2, its back `FRAME_HEIGHT` above the board. It starts 3.9 mm behind the antenna keep-out (x 6.9).
- Four M3 holes in the corners; two 2.2 mm holes (FH1 at 15.5 / 30.8, FH2 at 66.5 / 4.0) and seven spots free of parts for the frame (`FRAME_HOLES`, `FRAME_FEET` in `gen_pcb.py`). The spots and holes are a proposal until the frame is designed.
- The board name, the revision and the "Up" arrow are on the sensor island.

## Panel, tail and frame

From Good Display's specification ([`../datasheets/`](../datasheets/README.md), pages 7, 8, 28, 35) and their usage guidelines:

- The tail leaves the middle of a short edge, 12.5 mm wide (14.3 mm at its shoulder near the glass), 14.30 ± 0.30 mm long; its last 6.00 ± 0.5 mm are stiffened. Contacts are on the display side, the stiffener behind them.
- **Pin order.** The panel lies display up with its tail to the right, towards the sensors. That is the drawing's main view turned by 180°, so pin 1 is at the bottom. The fold runs parallel to the board's short edge and keeps each contact's height; J5, with its opening to the right, has its pin 1 at the bottom too. Panel pin N is connector pin N. After the fold the contacts face the board; J5 has contacts on both sides. Checked three times independently in the review.
- **J5** (Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF) sits with its front edge 3.0 mm inside the glass edge, 0.05 mm off the tail's centre line so that its pads fall on the 0.1 mm grid. Its flip lock is under the panel: the tail is plugged in and locked with the panel swung open, and the panel folded down onto the frame afterwards. Swinging it open again is also the only way to reach the parts under it.
- **Room for the fold** (`FOLD_ROOM`): from the glass edge to 4.3 mm beyond it, 1.5 mm wider than the tail's shoulder at both ends. Only tracks lie there; in front of J5, under the tail's stiff end, nothing stands higher than the board.
- **Frame height: not settled** (review, finding 4). The scripts draw the panel's back 4.75 mm above the board. With the tail entering J5 1.15 mm above the board and leaving the glass 0.5 mm above the panel's back (assumed; not dimensioned), the half circle has a radius of 2.05 mm and uses 6.44 mm of tail: nominally 0.48 mm of flexible tail are left before the stiffener, and with the tail at its shortest and the stiffener at its longest there are −0.17 mm, so the fold is tighter than a half circle. At about 4.3 mm there are 0.83 mm nominally and 0.18 mm at worst. The tallest parts under the panel are 3.3 mm (the switches). The height changes nothing on the board. **Decide before a frame is printed, with a real panel in hand.**
- **The fold bends once.** Plug in, close the lock, fold the panel down, leave it. Unplug USB first: the panel is always powered, and Good Display forbids plugging it in with power on.

## Circuit

### Panel connector J5

| Pin | Name | Connection |
| --- | --- | --- |
| 1, 4 | NC | open |
| 2 | GDR | gate of Q1, R18 (1 MΩ) to ground |
| 3 | RESE | source of Q1, R19 (2.2 Ω) to ground |
| 5 | VSH2 | C20 |
| 6, 7 | TSCL, TSDA | open, as in the reference circuit |
| 8 | BS1 | ground: 4-wire SPI |
| 9 | BUSY | `EPD_BUSY` |
| 10 | RES# | `EPD_RST`, R21 (100 kΩ) to +3V3 |
| 11 | D/C# | `EPD_DC` |
| 12 | CS# | `EPD_CS`, R20 (100 kΩ) to +3V3 |
| 13 | SCL | `EPD_SCK` |
| 14 | SDA | `EPD_MOSI` (also read back on this line) |
| 15, 16 | VDDIO, VCI | +3V3, C17 |
| 17 | VSS | ground |
| 18 | VDD | C18 |
| 19 | VPP | open |
| 20 | VSH1 | C19 |
| 21 | VGH | boost output, C22 at J5 and C27 at the diode |
| 22 | VSL | C21 |
| 23 | VGL | charge pump output, C23 at J5 and C28 at the diode |
| 24 | VCOM | C24 |

Boost and charge pump, as the specification's reference circuit (page 29): L2 from +3V3 (C25 at its input) to the switch node; Q1 from the switch node to `RESE`; D2 from the switch node to VGH; C26 from the switch node to the pump node; D3 from the pump node to ground; D4 from VGL to the pump node.

| Ref | Part | LCSC | Notes |
| --- | --- | --- | --- |
| J5 | Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, contacts on both sides, 2.0 mm high | C3249999 | 981 in stock on 2026-11-24; one maker |
| Q1 | Vishay SI1308EDL-T1-GE3, SOT-323 | C469327 | 1 gate, 2 source, 3 drain |
| D2–D4 | onsemi MBR0530T1G, SOD-123 | C82046 | pad 1 is the cathode |
| L2 | Sunlord SWPA4030S470MT, 47 µH, 4 × 4 mm, 0.72 A (saturation 0.95 A) | C54731 | |
| R18 | 1 MΩ, 0402 | C26083 | |
| R19 | 2.2 Ω, 0402 | C226973 | |
| R20, R21 | 100 kΩ, 0402 | C25741 | not in the reference circuit |
| C17–C24, C27, C28, and C3, C15 | Samsung CL10A105KB8NNNC, 1 µF, 50 V, X5R, 0603 | C15849 | keeps about 0.15 µF at 20 V, 0.21 µF at 15 V, 0.66 µF at 5 V |
| C25, C26 | Samsung CL21A475KAQNNNE, 4.7 µF, 25 V, X5R, 0805 | C1779 | C26 keeps about 0.75 µF at 20 V |

- **C27 and C28 (2026-11-25):** a second capacitor on VGH and on VGL, at the diodes (review, finding 11). The first ones stand at J5, 16 and 26 mm from the diodes, where the panel uses the voltages; the reference circuit draws the one on VGH at its diode.
- **Not done: 0805 capacitors for the driving voltages** (review, finding 10). They would keep 0.7 µF at 20 V, but the row along the top stands at 1.6 mm pitch and 0.8 mm parts are the widest that fit; it would mean laying out J5's upper pins again. The design equals Good Display's reference as it is.
- **C3 and C15 (2026-11-25):** the input capacitors of the two linear regulators are this 0603 part too (review, finding 5).
- **Buttons (2026-11-25):** the two lands of each switch's metal frame are on ground (pad SH), so a discharge from a finger or a plunger onto the frame goes to ground (review, finding 9). The terminals are as before: signal on the two outer ones, ground in the middle. The review's full proposal, signal on the middle terminal and ground on the outer ones, was tried and dropped: the signal then has to leave the middle pad on the bottom layer right below the switch, where the lines from the module's lower pin row pass, and one of them stayed open in every seed of three runs.

### Pin map

| Module pin | GPIO | Net | Use | In reset |
| --- | --- | --- | --- | --- |
| 3 | EN | `EN` | R6 10 kΩ up, C7 1 µF, RESET button | |
| 4 | IO4 | `EPD_DC` | panel data/command | floats; the panel ignores it while CS is high |
| 5 | IO5 | `EPD_RST` | panel reset, active low | high by R21 |
| 6 | IO6 | `I2C_SDA` | sensors, 4.7 kΩ to +3V3_SENS | |
| 7 | IO7 | `I2C_SCL` | sensors, 4.7 kΩ to +3V3_SENS | |
| 8 | IO0 | `BMP_INT` | BMP580 interrupt; can wake the chip from deep sleep | floats: internal pull needed |
| 9 | IO1 | `EPD_BUSY` | panel busy, driven by the panel, active high | floats without a panel |
| 10 | IO8 | `IO8` | R8 10 kΩ up (needed for download mode) | high |
| 11 | IO10 | `SENS_EN` | sensor regulator enable | high by R5: sensors on |
| 12 | IO11 | `QWIIC_EN` | Qwiic regulator enable | low by R15: Qwiic off |
| 13 | IO12 | `USB_DN` | USB D− | |
| 14 | IO13 | `USB_DP` | USB D+ | |
| 15 | IO9 | `BOOT` | R7 10 kΩ up, BOOT/USER button | high |
| 16 | IO18 | `EPD_SCK` | panel clock | pulled up by the chip |
| 17 | IO19 | `QWIIC_SDA` | Qwiic, 4.7 kΩ to +3V3_QWIIC | |
| 18 | IO20 | `QWIIC_SCL` | Qwiic, 4.7 kΩ to +3V3_QWIIC | |
| 19 | IO21 | `LED_G` | green, active low, 100 Ω | off |
| 20 | IO22 | `LED_R` | red, active low, 330 Ω | off |
| 21 | IO23 | `LED_B` | blue, active low, 100 Ω | off |
| 23 | IO15 | `EPD_CS` | panel chip select, active low | high by R20 |
| 24 | IO17 | `UART_RX` | UART0, the ESP32's input, pad RX | |
| 25 | IO16 | `UART_TX` | UART0, the ESP32's output, pad TX | |
| 26 | IO3 | `EPD_MOSI` | panel data | floats |
| 27 | IO2 | — | spare, open: enable an internal pull | |
| 22 | NC | — | | |

Changed against revision 1.0: `SENS_EN` IO18 → IO10, `BMP_INT` IO10 → IO0, and the six display lines. IO4, IO5 and IO15 are start-up configuration pins; with what hangs on them here they change nothing (IO4 and IO5 only set an SDIO timing option; IO15 high selects the USB JTAG the board uses). Confirmed against the ESP32-C6 datasheet in the review.

For the firmware:

- SPI goes through the GPIO matrix; write at 10 MHz or less in mode 0, read back over `EPD_MOSI` at 2.5 MHz at most.
- The display lines have no series resistors. Lower the pins' drive strength (`gpio_set_drive_capability`, start with setting 1) and look at SCK on its pad.
- Pulse `EPD_RST` at start. Give `EPD_BUSY` a timeout: it floats when no panel is plugged in.
- Turn the picture by 180°.
- Set the BMP580's interrupt pin to push-pull; it resets to disabled and open-drain.

### Test pads

All on the back, named on the back silkscreen.

| Pad | Name | Net | Where |
| --- | --- | --- | --- |
| TP1 | 5V | +5V | beside the fuse |
| TP2 | 3V3 | +3V3 | at the boost circuit's input |
| TP3 | 3VS | +3V3_SENS | at the sensor regulator |
| TP4, TP13 | GND | ground | middle of the board; by the display supply |
| TP5, TP6, TP7 | SCK, SDI, CS | display SPI | on their lines |
| TP8, TP11 | BSY, DC | `EPD_BUSY`, `EPD_DC` | on their lines |
| TP22 | RST | `EPD_RST` | on a via of its line, below the display lines at 52.5 / 18.9 (2026-11-25) |
| TP9, TP10, TP12 | SDA, SCL, INT | sensor bus | at the start of the bus |
| TP14, TP15, TP16 | GND, TX, RX | UART0 | under the module, 2.54 mm apart |
| TP17, TP19, TP21 | SH1, VSL, COM | VSH1, VSL, VCOM | below their capacitors, upper row (2026-11-25) |
| TP18, TP20 | VGH, VGL | VGH, VGL | below their capacitors, lower row (2026-11-25) |

**VGH and VGL carry about ±20 V**, and their pads stand 2.3 mm from their neighbours: use a fine probe. VDD (1.8 V) and VSH2 (5 V) have no pad. There is none on VBUS and on the Qwiic supply either, and no rail can be isolated without removing a part (the fuse, L1, R5).

## Layout

Generated by `tools/gen_pcb.py`; the rules of revision 1.0 ([`layout.md`](layout.md)) hold. What is particular to 2.0:

- **Drawn by hand** (`PREROUTED`): the six display lines from the module to J5 with their pads in line (`EPD_LINES`); the boost circuit (`BOOST`: input link, switch node 0.3 mm wide, sense and gate lines side by side into J5's pins 3 and 2); the sensor bus along the bottom edge and up to the bridge (`SENSOR_BUS`); J5's pins 17 and 18 (`J5_UPPER`); the stubs and vias of the back pads (`BACK_PAD_STUBS`, `DRIVE_PADS`); the buck converter's ground vias (`BUCK_GND`); the links of C27 and C28 to their diodes.
- **Nothing lies under the buck inductor L1 on the top layer** (2026-11-25; review, finding 1): no track, no via, no pour (`L1_UNDER`). Murata's specification for the DFE252012F forbids copper under the coil. `QWIIC_EN`, which ran there, passes L1 on the bottom layer through a hand-drawn hop (`L1_HOP`: vias at 34.2 / 13.1 and 37.7 / 12.5). With the strip closed and no hop, none of twelve seeds routed the board. The price is a slit 0.6 mm wide and 3.5 mm long in the bottom ground under the inductor, 5 mm from the converter's input loop.
- **Kept as ground on the bottom layer** (`DISPLAY_GROUND_AREAS`, `BUCK_AREA`, `USB_GROUND_AREAS`): in front of and behind J5, under the boost circuit's switching loop (x 52.0–59.3, y 23.0–26.3), under the buck converter apart from the hop, behind the USB connector. **Outside that area, bottom tracks do cross under the boost circuit's inductor and capacitors** (review, finding 12, open).
- **Kept as ground on the top layer** (`EPD_POCKETS`, `BOOST_KEEP_TOP`): between the display lines, under the MOSFET, and between the boost inductor's pads, where VGL (−20 V) used to run 0.25 mm from the switch node's pad (2026-11-25; review, finding 13).
- **Ground stitching and patches:** one stitching via per 5 mm cell where one fits, under the module too; pieces of pour that tracks close off are tied to ground with a via where one fits (`tie_patches`).
- **SCD41 paste** (2026-11-25; review, finding 7): the paste openings of its twenty outer pads are pulled in by 0.15 mm all round, 1.6 × 0.55 mm instead of the whole 1.9 × 0.85 mm land. That is 1.28 times the volume of Sensirion's aperture instead of 2.35 times, and 0.46 mm from the vent hole's centre instead of 0.31 mm. The copper is unchanged, so revision 1.0 still proves the island's layout.
- **Silkscreen** (2026-11-25; review, finding 15): letters 1.0 mm high, lines 0.15 mm wide, JLCPCB's stated minimums. Two outlines stay 0.12 mm wide, those of the SGP41 and of the capacitor C11 beside it: at 0.15 mm they come within 0.08 mm of each other.

How the router is driven (`--keep`, `--seeds`, the audit): [`layout.md`](layout.md) and `CLAUDE.md`.

## Open points

From the review, in its numbering; everything not listed here is done or was a note.

| | What | When |
| --- | --- | --- |
| 2 | JLCPCB's assembly rails at the parts that overhang the long edges (buttons, USB connector): a remark on the order, and a look at the production file | at ordering, see [`ordering.md`](ordering.md#revision-20) |
| 3 | Revision 1.0 brought up; a 2.0 pin map in the firmware | before ordering |
| 4 | Frame height | before the frame is printed |
| 6 | Voltage peak on +5V when a cable is plugged in (calculated: up to 6.6 V in the middle case; the regulators' limit is 6.0 V) | measure on a 1.0 board |
| 8 | Reverse current through the sensor regulator at unplug | judge after 1.0 |
| 10 | 0805 driving-voltage capacitors | not planned |
| 12 | Bottom tracks under the boost circuit outside the reserved area | open |
| 14 | Antenna: panel 6 mm away, M3 screws 3 mm away | nylon screws; measure on the first board |
| 9 | Buttons: the frame is on ground; the signal is still on the outer terminals beside it, and `BOOT` has no capacitor | judge on the first board |
| 17 | No pad on VBUS and the Qwiic supply; no way to isolate a rail | open |
| 18 | Green and blue LED may be dim on 3.3 V | see on a 1.0 board |
| 19 | BMP580 land size (Bosch's two documents disagree) | see on a 1.0 board |
| 20 | Switch boss holes 0.20 mm from the switch's own pads; USB shell slots with a 0.20 mm ring | known, at JLCPCB's limit |
| 21 | C2's part number is not recommended for new designs; J5 has one maker and low stock | at the next order |

Only real parts can show: the J5 and switch footprints, the antenna behind the panel, the temperature under the panel (rated to 50 °C), and how the case presses the buttons, which reach only 0.2 mm past the edge.

## Next steps

1. Bring up a revision 1.0 board and make the measurements above.
2. Firmware: board revision mechanism, 2.0 pin map, display driver.
3. Decide the frame height; design frame and case.
4. Order as described in [`ordering.md`](ordering.md#revision-20), only after Norman's go-ahead.

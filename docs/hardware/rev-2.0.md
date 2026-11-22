# Revision 2.0 — e-paper display (draft)

Status: **schematic and board generated and checked with KiCad (2026-11-22): fully routed, no rule violations, display lines drawn by hand with their probe pads in line; footprints of the display connector and the side-push buttons drawn from the makers' land patterns. Not yet built; the FPC distance still has to be checked with a paper print.** Started 2026-11-22. Every point marked **Assumption** or **Open** still needs a decision or a check against a datasheet. Revision 1.0 stays as ordered on 2026-11-20 (commit `8c89155` is the design that was sent to JLCPCB); its documents ([`schematic.md`](schematic.md), [`layout.md`](layout.md)) describe 1.0 until the 2.0 board is drawn.

Background: section 6 of [`next-revision.md`](next-revision.md).

## What is already settled

From the display research of 2026-11-22, agreed with Norman:

| Topic | Choice |
| --- | --- |
| Display | **Good Display GDEY0213B74**: 2.13", 250 × 122, black and white e-paper, SSD1680 controller, SPI, 24-pin FPC with 0.5 mm pitch. Outline 59.2 × 29.2 × 1.0 mm, active area 48.55 × 23.70 mm, 0 to 50 °C. Fallback if the board gets too long: a 1.54" 200 × 200 SSD1681 panel. |
| Driving voltages | Made on the board from the panel's own gate driver (`GDR`) and current sense (`RESE`) pins with the maker's boost circuit; no extra chip. |
| Board orientation | **Flipped.** All parts stay on one side, which now faces the wall; the panel is stuck to the bare back side, which faces the room. |
| Panel position | **Over the controller side only**: never over the sensor island or the SHT45 tongue (it would hold their heat and block air), and clear of the antenna. |
| FPC | Through a **milled slot in the controller side** to a connector on the component side, not round a board edge. |
| Assembly of test revisions | **At home**: bare boards and a stencil from JLCPCB, tin-bismuth low-temperature paste on a hot plate. Populated boards are ordered only once a revision works. The panel is plugged in by hand. |
| Cost | Hobby project: one-sided, hand-placeable parts, common LCSC parts, no part that is not needed. |

What the flip means elsewhere:

- **The sensors face the wall.** The case needs a gap to the wall and vents at its top and bottom edges, so that air rises past the sensors like in a chimney. The SGP41 is then also out of direct light, which its datasheet asks for.
- **The antenna faces the wall too.** A wall a centimetre away costs some Wi-Fi range; a brick or concrete wall more than plasterboard. To be measured on the first board.
- **BOOT/USER and the status LED have to be reachable from the room**: see [Buttons and LED](#buttons-and-led).
- **The one-sided board suits a hot plate**: the bare back side lies flat on the plate.

## Board

Seen from the component side (the side that faces the wall), with the same left-to-right order as 1.0:

| Zone (x, mm) | Contents |
| --- | --- |
| 0 – 26 | ESP32-C6 module, antenna at the left edge (unchanged) |
| 26 – 48 | USB-C, protection, fuse, buck converter, Qwiic, as in 1.0; the two side-push buttons on the top edge; the I2C pull-ups at the start of the sensor bus |
| 48 – 67 | **New**: boost circuit (top), FPC connector J5 (opening towards the slot), the eight 1 µF capacitors (bottom). The panel lies on the other side of 10.8 – 70.0 |
| 64 – 72, below the slot | The sensor regulator U3 with C3, C4, its pull-up R5 and its test pad TP3 ("3VS"), where the sensor bus turns up into the strip |
| 71.8 – 73.0 | FPC slot, 13.5 mm long, y = 10.05 – 23.55, 1.8 mm beyond the panel's edge |
| 73.0 – 76.0 | Strip where the sensor bus runs round the end of the FPC slot to the bridge |
| 76.0 – 77.5 | Milled slot to the sensor island (as 1.0) |
| 77.5 – 103 | Sensor island and SHT45 tongue, exactly as in 1.0, moved right by 28 mm |

- **Size: 103 × 34 mm** (1.0: 75 × 34). The height stays: the panel is 29.2 mm high. It came out 2 mm longer than first estimated: the FPC slot lies right in front of the bridge that carries the sensor bus across the sensor slot, so the bus has to run round the slot's end, and that needs a strip of about 3 mm between the two slots.
- **Assumption**: the panel's left edge keeps a gap from the end of the antenna keep-out (x = 6.9 mm in 1.0). Espressif asks for no metal near the antenna; the panel has thin metal tracks on glass. Less gap gives a shorter board. First 5 mm (x = 11.8 to 71.0); **since 2026-11-22 the panel sits 1 mm further left, x = 10.8 to 70.0, 3.9 mm from the keep-out** (Norman's observation: the glass edge was only 0.8 mm from the FPC slot; it now keeps 1.8 mm). It stays 5.7 mm clear of the left mounting holes' edge, and no back-side pad lies in the added strip. `PANEL_X0` in `gen_pcb.py`; to be verified with the real panel and a 1:1 print.
- The generator (`hardware/rev-2.0/tools/gen_pcb.py`) builds this from the 1.0 placement: everything from x = 48 rightwards moves by 28 mm, nothing else of 1.0 moves, and the new parts go into the gap. The panel's outline is printed on the back silkscreen.
- The component side under the panel is free for parts, since the panel is on the other side. Only the FPC slot has to lie beyond the panel's edge.
- Seen from the room the board is mirrored: the antenna end is on the right, the sensors on the left. Up stays up, so the arrangement of the sensors for rising heat is unchanged.
- **Mounting holes**: the two at the antenna end are outside the panel; the two on the sensor island stay where they are.
- **Under the panel** (on the back side): no parts, as everywhere on the back. Vias are covered by solder mask. The panel is held by the case or by double-sided tape; the tape must not cover the FPC slot.
- **The serial port** (1.0's header J3) lies under the panel. **Decided 2026-11-22 (Norman): three of KiCad's standard 1.0 mm test pads on the component side instead of the holes** (TP14–TP16: UART0 GND, TX, RX, in a row 2.54 mm apart, so a 3-pin pogo adapter still fits); nothing reaches the panel side.

## FPC slot and connector

From Good Display's drawing (GDEY0213B74 specification, page 7, initial version 2021-03-17):

- The tail leaves the middle of a short edge: 12.50 mm wide, its edge 8.15 ± 0.3 mm from the panel's long edge, so it is centred to within 0.2 mm.
- It reaches 14.30 ± 0.3 mm beyond the glass. The last 6.00 mm carry a stiffener; contacts are 0.30 mm thick, 24 at 0.5 mm pitch over 11.5 mm.
- The contacts are drawn on the display side of the tail; the stiffener is behind them. **Assumption** from the drawing: it shows the contacts in the front view. To be confirmed on the real panel.

The tail leaves towards the sensor side, so that the FPC and the boost circuit stay away from the antenna. Two ways through the board:

| | Route | Contacts on the component side face | Connector | Board |
| --- | --- | --- | --- | --- |
| **A (chosen)** | Through the slot, then **back** under the panel's edge (a U-turn round the slot's edge) | up, away from the board | **dual-contact**: Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, LCSC **C3249999**, flip lock, 2.0 mm high | 103 mm |
| B | Through the slot and **onwards**, away from the panel (an S-bend) | down, onto the board | bottom-contact: BOOMELE 0.5-24P FG, LCSC **C20688**, flip lock, 2.0 mm high, the common one, about 0.08 USD | longer: the connector has to sit beyond the slot |

- In route A the connector sits under the panel's edge, with its opening facing the slot. A dual-contact connector also works if the assumption about the contact side above is wrong.
- **The U-turn reverses the pin order.** The panel's pin 1 is at the top of the tail (drawing, front view; it stays at the top seen from the component side). The connector, turned to face the slot, has its pin 1 at the bottom. So panel pin N lands on connector pin 25 − N, and the schematic wires J5 that way (`FPC_REVERSED` in `gen_schematic.py`). **Check this with the real panel before ordering**: if pin 1 turns out to be at the other end, set `FPC_REVERSED = False`.
- **The connector's front edge is 6.8 mm from the slot (2026-11-22, Norman: J5 1 mm closer to the slot, together with the panel 1 mm further from it; before that 7.8 mm, decided the same day: some slack in the tail is fine, too short would be fatal).** Kinghelm's drawing gives an FPC insertion depth of 2.1 mm, not the 3.7 mm first assumed. With bends of 0.4 mm radius the tail needs about 12.2 mm from the glass edge to full insertion and has 14.3 mm, so about 2 mm of slack remain for real bend radii and tolerances (5.8 mm, the first value, left 4 mm). With the panel and J5 both moved by 1 mm the tail runs 1.8 mm on the back to the slot and 5.0 mm from the glass edge's line to J5's front on the component side; the slack stays at 2.15 mm (`gen_models.py` prints it; with the panel moved alone it would have dropped to about 1.2 mm). **To be confirmed with a 1:1 paper print and the real panel** (`J5_FRONT_TO_SLOT` in `gen_pcb.py`). The 3D view draws the tail along that path, with its spare length as a bow (`board-fpc.png`).
- **How pin 1 was placed:** in Kinghelm's top view (tails at the back, opening towards the viewer) the "refer pin" triangle marks the left end, so that is pin 1; JLCPCB's own footprint of C3249999 agrees. Turned by 90° so that the opening faces the slot, pin 1 is at the bottom. The fold of the U-turn runs parallel to the slot and keeps each contact's height on the board, so the panel's pin 1 (top of the tail) arrives at connector pin 24. The connector has contacts on both sides, so the face of the tail does not matter. Still unverified is only the panel side: whether its pin 1 is really at the top of the tail seen from the component side.
- **The tail is short.** Of its 14.3 mm, 6 mm are stiff, which leaves about 8 mm to reach the slot, pass through the 1.6 mm board in two bends and come out on top. Feasible, but **check with a 1:1 paper print of the board edge and the real panel** before ordering.
- Both connectors are extended parts at JLCPCB; for a board assembled at home that costs nothing extra.
- Footprint: `gen_footprints.py`, from Kinghelm drawing 8.01A0-C rev L; notes in [`footprints.md`](footprints.md).
- Hand assembly: 0.5 mm pitch is fine with a stencil and a hot plate. Bridges are cleared with the rework station and flux.

## Schematic additions

### Panel connector and boost circuit

From the reference circuit in the GDEY0213B74 specification (page 29). The panel makes its driving voltages itself from the two pins `GDR` (gate drive) and `RESE` (current sense); the board adds a boost converter and a charge pump.

| FPC pin | Name | Connection |
| --- | --- | --- |
| 1, 4 | NC | open |
| 2 | GDR | MOSFET gate, 1 MΩ to ground |
| 3 | RESE | MOSFET source, 2.2 Ω to ground |
| 5 | VSH2 | 1 µF to ground |
| 6, 7 | TSCL, TSDA | open (an external temperature sensor; not used) |
| 8 | BS1 | ground: 4-wire SPI |
| 9 | BUSY | `EPD_BUSY` |
| 10 | RES# | `EPD_RST` |
| 11 | D/C# | `EPD_DC` |
| 12 | CS# | `EPD_CS` |
| 13 | SCL | `EPD_SCK` |
| 14 | SDA | `EPD_MOSI` |
| 15, 16 | VDDIO, VCI | +3V3, 1 µF to ground |
| 17 | VSS | ground |
| 18 | VDD | 1 µF to ground (internal regulator) |
| 19 | VPP | open (no capacitor drawn in the reference circuit) |
| 20 | VSH1 | 1 µF to ground |
| 21 | VGH | `PREVGH`: boost output, 1 µF to ground |
| 22 | VSL | 1 µF to ground |
| 23 | VGL | `PREVGL`: charge pump output, 1 µF to ground |
| 24 | VCOM | 1 µF to ground |

Boost and charge pump: 47 µH from +3V3 (4.7 µF at its input) to the switch node; the MOSFET from the switch node to `RESE`; a Schottky diode from the switch node to `PREVGH`; 4.7 µF from the switch node to a junction with two Schottky diodes, one from the junction to ground, one from `PREVGL` to the junction, so that `PREVGL` is pumped negative.

| Ref (Good Display) | Ref (ours) | Part | Good Display's requirement | Chosen | LCSC |
| --- | --- | --- | --- | --- | --- |
| P1 | J5 | FPC connector | 24 pins, 0.5 mm | Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, double-sided contacts | C3249999 (980 in stock, from 0.13 USD) |
| Q1 | Q1 | N-MOSFET | Si1308EDL, or: ≥ 30 V, Vgs(th) ≤ 1.5 V, Rds(on) ≤ 400 mΩ | Vishay SI1308EDL-T1-GE3, SOT-323 | C469327 (39,000 in stock, from 0.12 USD). Fallback AO3400A, C20917, SOT-23 |
| D1–D3 | D2–D4 | Schottky diodes | MBR0530, or: ≥ 30 V, ≥ 500 mA, Vf ≤ 430 mV | onsemi MBR0530T1G, SOD-123 | C232832 (**not confirmed**). JSCJ's MBR0530, C77336, specifies 550 mV at 0.5 A |
| L1 | L2 | Inductor | 47 µH, "refer to NR3015: Io = 500 mA (max)" | APV APSWPA4030S470MTF, 4 × 4 mm, 720 mA, 0.58 Ω | C5363795. NR3015-size parts (3 × 3 mm) carry only 300 mA |
| R1 | R18 | 1 MΩ | 0603/0805, 1 %, ≥ 0.05 W | UNI-ROYAL 0402WGF1004TCE, 0402 | C26083 |
| R2 | R19 | 2.2 Ω | as above | YAGEO AC0402FR-072R2L, 0402 | C226973 |
| C2, C5–C7, C9–C12 | C17–C24 | 8 × 1 µF | 0603/0805, X5R/X7R, ≥ 25 V | Samsung CL10A105KB8NNNC, 0603, **50 V** | C15849 (basic) |
| C3, C4 | C25, C26 | 2 × 4.7 µF | as above | Samsung CL21A475KAQNNNE, 0805, 25 V | C1779 |
| – | R20 | Pull-up on `EPD_CS` (not in the reference circuit) | – | 100 kΩ, UNI-ROYAL 0402WGF1003TCE, 0402, the part type of R5 and R15 | C25741 |

Checked at LCSC on 2026-11-22 unless marked. The 1 MΩ and 2.2 Ω resistors are 0402 at 0.0625 W, above the 0.05 W asked for.

- **The 25 V capacitors go to 0603 and 0805, as Good Display asks**, even though the rest of the board is 0402. A 1 µF 0402 ceramic keeps only a small part of its capacitance at 20 V; the larger case keeps more.
- The panel's voltages are about ±20 V on `VGH`/`VGL`, so 25 V capacitors and 30 V diodes and MOSFET.

### Pins

The panel needs six GPIOs. IO2, IO3, IO4, IO5 and IO15 were free. **Decided 2026-11-22 (Norman): the 32 kHz crystal option is dropped**, because the device is not battery powered; that frees IO0 and IO1, which revision 1.0 kept unconnected for it. The sixth display pin is IO1, and the BMP580 interrupt stays.

| GPIO | Net | Why this pin |
| --- | --- | --- |
| IO3 | `EPD_BUSY` | Driven by the panel, so not on a start-up configuration pin (IO4, IO5, IO15 are) |
| IO18 | `EPD_RST` | **Decided 2026-11-22 (Norman)**: first moved from IO2 to IO10, then swapped with `SENS_EN` onto IO18 (upper pin row, beside `EPD_CS` and `EPD_BUSY`), because the lower row's lines no longer all fitted through the corridor below the module. IO18 is pulled up while the chip is in reset, so the panel is simply not held in reset then; the firmware pulses `EPD_RST` at start. IO2 is the spare. |
| IO10 | `SENS_EN` | **Decided 2026-11-22 (Norman)**, swapped with `EPD_RST` (IO18 on 1.0). IO10 floats in reset; R5's 100 kΩ pull-up keeps the sensor regulator on, as before. R5 now sits next to the regulator U3. |
| IO4 | `EPD_SCK` | Start-up configuration pin; fine as an output that the ESP32 drives only after start |
| IO5 | `EPD_MOSI` | as IO4 |
| IO15 | `EPD_CS` | as IO4 |
| IO1 | `EPD_DC` | |
| IO0 | `BMP_INT` | **Decided 2026-11-22 (Norman)**: the BMP580 interrupt moves here from IO10. IO0 is one of the pins that can wake the chip from deep sleep and be read by the low-power core, which IO10 cannot (see the BMP580 item in [`next-revision.md`](next-revision.md)); it is not a start-up configuration pin. Costs nothing, since 2.0 changes the pin map anyway. |

- SPI goes through the GPIO matrix to these pins; fine at the panel's clock (a few MHz to 20 MHz).
- **`EPD_CS` has a 100 kΩ pull-up to +3V3 (R20, added 2026-11-22)**, so that the panel's chip select is inactive while the ESP32 is in reset or before IO15 is configured. IO15 floats in reset: it has no internal pull resistor (ESP32-C6 datasheet v1.6, table 3-1 and section 3.4). It is a strapping pin, but only for the JTAG signal source, and only when `EFUSE_JTAG_SEL_ENABLE` is burned; with the default eFuses (all three JTAG eFuses 0) IO15 is ignored and JTAG goes to the USB Serial/JTAG controller (table 3-7). Even with that eFuse burned, a high IO15 selects the USB Serial/JTAG controller, which is what the board uses. So the pull-up is harmless at start. The other display lines have no pull resistors: `EPD_RST` sits on IO18, which the chip pulls up in reset, and SCK/SDI/DC do nothing while CS is high.
- The final order on the module pins is chosen during layout, so that the six tracks reach the connector without crossing.
- `pins.h` and [`schematic.md`](schematic.md) describe 1.0 and change with the 2.0 firmware (see [Firmware](#firmware)).

## Buttons and LED

The component side faces the wall, so a normal push button and a top-facing LED cannot be seen or pressed from the room.

- **BOOT/USER**: a **side-press button on the top edge** of the board, so a finger or a plunger in the case reaches it from above. The first proposal, Kinghelm KH-3635-CAJ (C530670), was dropped: its drawing and JLCPCB's footprint disagree on which side of the pads the plunger is.
- **Decided 2026-11-22 (Norman): Alps SKRTLAE010** (LCSC C110293, about 70,000 in stock, 0.14 USD) **for both buttons, as Alps draws it**: 4.5 × 3.4 × 3.3 mm, round button Ø2 mm, two guide bosses in Ø0.9 mm holes. On the top edge, button up, 8 mm apart (BOOT/USER at x 28, RESET at x 36), labels below them. Its holding pads reach 0.3 mm beyond the front of the body, so with the 0.3 mm copper-to-edge rule the body stays 0.6 mm inside the edge and **the button reaches only about 0.2 mm past the edge: the case needs a button of its own that presses on it.** Checked 2026-11-22: JLCPCB's capabilities page gives 0.2 mm copper clearance from a routed edge (0.4 mm from a V-cut), so the switches could sit 0.1 mm further out (0.3 mm past the edge) with a board rule of 0.2 mm for their pads. Not changed: the routed edge's tolerance is ±0.2 mm, so at 0.2 mm the edge may touch the holding pads' copper, and 0.1 mm does not remove the need for a plunger in the case. Two changes from Alps' land pattern, so that the boss holes keep JLCPCB's 0.2 mm to copper (as drawn: 0.08 and 0.15 mm): the outer terminal pads are 0.125 mm narrower on the outside, the holding pads start 0.05 mm further forward. The board's own hole clearance is 0.25 mm; `climasense.kicad_dru` allows 0.2 mm between a switch's holes and its own pads.
- **RESET**: **decided 2026-11-22 (Norman)**: buttons and LED line up along the top edge so that a case can have them pressed from the top. RESET becomes the same side-press part next to BOOT, about 8–10 mm apart. The case should recess it against accidental presses.
- **Status LED**: keep the 1.0 LED at the top edge, now as close to it as the copper-to-edge rule allows (centre 1.4 mm from the edge), and let the case carry the light to the room with a light pipe or a thin wall (decided, see below). With a display, the LED matters less: it is mainly for the moments when the display cannot show anything (start, firmware update, crash).
- Side-view RGB LEDs with a common anode at LCSC (2026-11-22): Amicc A-SP1103R6GHB1C-A01-2C (C5160691, 235 in stock, 0.12 USD; datasheet read: pin 1 common anode, 2 blue, 3 green, 4 red; 3.0 × 1.0 mm with a dome of 1.0 mm radius that emits away from its row of pads, so it can sit at the top edge with the pads on the board and light over the edge). Everlight 12-23C/R6GHBHC-A01/2C (C311716, 17,000 in stock, 0.10 USD) is very likely the same design, but LCSC links Amicc's datasheet for it and Everlight's was not available.
- **Decided 2026-11-22 (Norman): the side-emitting LED is not used.** It is a niche part with low stock. D1 stays the Everlight 19-337 of 1.0, 1.4 mm from the top edge; the case gets a thin window or a light pipe above it.

## What stays as in 1.0

Supply (USB-C, fuse, buck converter, Qwiic regulator), sensors and their island and tongue, Qwiic connector, the 0402 passives. Changed against 1.0: the sensor regulator U3 (with C3, C4, R5, TP3) and the I2C pull-ups R12/R13 moved (see [Layout as generated](#layout-as-generated)), the buttons, the serial port and the test pads (see above), and **the sensor header J4 is gone (decided 2026-11-22, Norman)**: the sensor side is electrically unchanged, so the 1.0 boards show whether it works; probe pads take over its job for a logic analyser.

**Assumption**: 0402 stays. It can be placed by hand with tweezers and a stencil, and the layout of 1.0 can be reused. 0603 would be easier for a first hand assembly but would need the whole board placed again.

## Firmware

- An SPI display driver for the SSD1680 (no ESP-IDF component fits; a short driver of our own), a display task, and a screen layout. Refresh: partial updates when values change, a full refresh about once an hour.
- **Pin map**: `pins.h` still describes 1.0. 2.0 needs the display pins of the table above and `SENS_EN` on IO10 (was IO18), `BMP_INT` on IO0 (was IO10); a separate step.
- **Board revision**: 2.0 changes the pin map, so the firmware has to know which board it runs on. **Open**: a build option per board, or detection at run time (for example by reading `EPD_BUSY` with a pull-down: the panel holds it low when present). Not decided.

## Layout as generated

State of 2026-11-22: `gen_pcb.py` gives a fully routed board, 103 × 34 mm; KiCad counts no open connection, DRC has no violation, the board matches the schematic, and the ground pours are one connected piece. Pictures: [`../images/rev-2.0/`](../images/rev-2.0/), including the back with the panel in place (`board-bottom.png`) and the FPC tail running into J5 (`board-fpc.png`). What differs from revision 1.0's layout ([`layout.md`](layout.md)):

- **Sensor bus drawn by hand** (`SENSOR_BUS` in `gen_pcb.py`): `+3V3_SENS`, `I2C_SCL`, `I2C_SDA` and `BMP_INT` run on the top layer along the bottom edge (y 31.9–33.2, below C17–C24), then up the strip right of the FPC slot into the bridge tracks. Left to the router, the bus crossed the display area diagonally, cut pockets out of the pours and left `BMP_INT` without a route. `SENS_EN` runs with it on the bottom layer to R5 (`SENS_EN_FEED`).
- **Sensor regulator by the bridge**: U3 with C3, C4, R5 and TP3 sits below the FPC slot, where the bus turns up to the bridge; its output joins the bus's supply run directly. The 5 V feed and `SENS_EN` travel instead.
- **I2C pull-ups at the start of the bus** (decided 2026-11-22, Norman): R12/R13 sit above the free ends of the SDA and SCL runs at the bottom edge, with the SDA/SCL/INT probe pads beside them. The "Up" arrow moved right to make room.
- **Buttons on the top edge**: the hand-drawn Qwiic lines and `SENS_EN`'s old run, which went under 1.0's BOOT button, moved below the new switches.
- **USB supply**: the link from the connector's farther supply pad to the fuse is drawn by hand as the router drew it on 1.0 (19 mm, 24 mΩ; 73 mm when left to the router on 2.0).
- **J5 and the charge pump**: J5 now 6.8 mm from the slot (moved 1 mm right on 2026-11-22; only J5 moved, the display lines' ends follow it and DC's probe pad TP11 moved 1 mm right with DC's run down beside the pad row). Earlier, with J5 7.8 mm from the slot, the boost parts moved 0.7 mm left and the diodes D2–D4 0.8 mm up, so that the lines to J5's pins 14–16 reach them straight from the left.
- **Bottom layer kept as ground** (`DISPLAY_GROUND_AREAS`): the FPC landing area and the strip between the two slots over the full height (the sensor island's ground return), behind J5, under the boost converter's switching loop, under the RESET switch's ground pad, and a patch round C7's ground via below the module.
- **Router**: it counts a cut-off pocket of the ground pours as a failure; its start order can be jittered (`ROUTE_SEED`, 4 on this board since the display lines are drawn by hand, found in one batch of eight; 6 of the 8 routed completely); tracks ending on the middle of another track are split there so KiCad sees both ends joined.
- **Ground stitching vias** (`STITCH_PITCH`, `STITCH_EXTRA`), added after routing so they never block a track: a uniform 5 mm grid over the pours, plus single rows along the strip between the slots, across both ends of the FPC slot, along the antenna keep-out and round the boost converter's grounds (thinned on 2026-11-22, Norman); each with room for the pour all round, 0.5 mm from every pad, none under the USB connector or in the antenna keep-out, and (2026-11-22, Norman) none under a silkscreen label or within 1 mm of a test pad (`stitch_avoid()` in `gen_pcb.py`; the label's size is estimated). 31 vias on the current board.
- **Top layer kept as ground between the display lines** (`EPD_POCKETS`, `reserve_top` in `route_board.py`): the pocket that RST closes in above CS's run down at x 40, and the gaps between RST, CS, SCK and SDI along the staircase, round the probe pads. In the first runs with the hand-drawn lines the router threaded a 0.4 mm +3V3 track through such a gap between two vias, squeezed between two display lines; on the board before the staircase a +5V track ran 9.5 mm between the SCK and SDI dips. Now no supply track runs between the display lines.
- **Ground test pads and R15 with their via drawn by hand** (`GND_PAD_VIAS`, 2026-11-22, Norman): the router puts a ground pad's via right beside the pad. TP4 (GND, middle) moved 0.8 mm down to y 24.2, its via 1 mm above its edge at (44.6, 22.4), label below at y 25.9; TP13 (GND, top) stays at (60.0, 2.4), its via 1 mm to its right at (61.8, 2.4); TP14 (UART GND) has its via midway to the TX pad at (10.3, 4.0), clear of the labels above (it was under the GND label; that was the pad's own via, not a stitching via). R15's ground pad has its via below it at (42.3, 13.5): with the SPI lines in the staircase the router had put it on the left, where I2C_SDA and the RST and CS vias cut it off from the pours.
- **Test and probe pads, all KiCad's 1.0 mm pad (decided 2026-11-22, Norman)**: 5V, 3V3, 3VS and GND (TP1–TP4), a second GND by the boost converter (TP13), UART0 GND/TX/RX (TP14–TP16), SDA, SCL and INT at the bus start (TP9, TP10, TP12), and the display's SCK, SDI, CS, BSY and DC (TP5–TP8, TP11, see the next point). The display's driving voltages are measured on the pads of C18–C23, which carry silkscreen names (VDD, VSH1, VSH2, VSL, VGH, VGL; VCOM's does not fit beside J5).
- **Display lines drawn by hand** (`EPD_LINES` in `gen_pcb.py`, 2026-11-22): all six, from the module to J5, on the paths the router had found for the clean board of commit `e8b8ee3`, with the probe pads placed **in line** on top-layer sections, so that a pad adds no branch (a row of pads beside the lines had forced every line into a detour). **Left of J5 the three SPI lines run as a staircase (2026-11-22, Norman)**: CS straight at y 16.5 from x 40.5 into its pin (54.1 mm instead of 55.4 mm with its former U), SCK 1.2 mm below it at y 17.7, SDI (MOSI) another 1.2 mm below at y 18.9, each rising to its pin after its pad; the bundle sits 1.5 mm higher than with the former nested U shapes, which leaves more ground below it. Their probe pads sit on the lines 4.4 mm apart (`SPI_PAD_X`): CS (45.4, 16.5), SCK (49.8, 17.7), SDI (54.2, 18.9). BSY's pad sits above the bundle on its run down past C26, DC's on its run down the right of J5's pad row, now at y 6.6 with its label 0.5 mm clear of the ground via below it (the stitching via that was above it went with the rule below); RST has none. **Labels beside the pads**: CS, SCK, SDI and DC to the right of their pads, each ending before the next pad begins; BSY's left of its pad (below it sat on a via). **Every test pad's label is placed by one rule** (`TP_LABELS`, `pad_label_position()` in `gen_pcb.py`, 2026-11-22, Norman): 0.4 mm (`TP_LABEL_GAP`) between the outer edge of the pad's silkscreen circle and the nearest edge of the letters as KiCad draws them, the letters centred on the pad across that direction. 5V's label is below its pad (beside it, it touched a +3V3 via), 3VS's to the right of its pad (above it, it touched U3's outline). R20, the pull-up on CS, sits in line on CS's run down from its via at x 40, its +3V3 pad towards the feedback divider.
- The rules of 1.0 hold unchanged: nothing under the USB connector on either layer (checked on the generated board), ground behind it, the SCD41 supply link clear of the vent hole.
- From `audit_pcb.py` (2.0 / 1.0): sensor regulator to the SCD41's supply pin 35.9 mm, 51 mΩ / 22.8 mm, 34 mΩ; to its emitter supply 51.8 mm, 72 mΩ / 38.6 mm, 55 mΩ; to the SHT45 57.7 mm, 100 mΩ / 49.8 mm, 94 mΩ; fuse to sensor regulator 38.4 mm, 55 mΩ (a few tens of mA); buck output capacitor to the ESP32's supply pin 45.5 mm, 37 mΩ. No net crosses itself or has a loop; 9 right-angle corners remain, none on one of the six display lines. Figures of the board with the SPI staircase (2026-11-22): fuse to sensor regulator now 37.9 mm, 54 mΩ, the rest unchanged. This board was made with `gen_pcb.py --keep` on top of a full run with seed 4: only the nets around the change were routed again (seed batch 4–11, all clean on the last step).
- The panel's outline is on the back silkscreen (broken where it would cross a through-hole pad), with two ticks and "FPC" at the edge the tail leaves from. Simple models of the panel and its tail exist for the 3D view only.

## Not checked yet

- The GDEY0213B74 specification was read on 2026-11-22 (37 pages, revision 1.0 of 2021-03-17): pin table, drawing, reference circuit. Not yet read: its DC characteristics (an image in the PDF) for current in deep sleep and the SPI clock limit.
- On a real panel and a 1:1 paper print: where pin 1 is after the U-turn (`FPC_REVERSED`), and whether 6.8 mm from the slot (panel at x 70.0) leaves the tail the right slack (the face of the tail does not matter with the dual-contact connector).
- The J5 and switch footprints on a real board (JLCPCB's placement preview, then the first assembly); the switch's narrowed pads.
- How the case presses the buttons (they reach only about 0.2 mm past the edge).
- LCSC numbers, stock and prices of the remaining new parts (see the table above; the Schottky diode is not confirmed).
- Whether the panel can be bought as a single piece at a sensible price outside Good Display's own shop (LCSC listings were out of stock on 2026-11-22).

## Next steps

1. A 1:1 paper print and the real panel: tail reach round the slot, contact side, and pin 1's position after the U-turn (`FPC_REVERSED`).
2. Firmware: board revision mechanism, 2.0 pin map, display driver.
3. Order bare boards and a stencil only after Norman's go-ahead.

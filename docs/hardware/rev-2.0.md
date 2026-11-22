# Revision 2.0 — e-paper display (draft)

Status: **concept drafted; schematic generator updated, not yet checked with KiCad; board not started.** Started 2026-11-22. Every point marked **Assumption** or **Open** still needs a decision or a check against a datasheet. Revision 1.0 stays as ordered on 2026-11-20 (commit `8c89155` is the design that was sent to JLCPCB); its documents ([`schematic.md`](schematic.md), [`layout.md`](layout.md)) describe 1.0 until the 2.0 board is drawn.

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
| 26 – 48 | USB-C, protection, fuse, regulators, buttons, Qwiic, exactly as in 1.0 |
| 48 – 67 | **New**: boost circuit (top), FPC connector J5 (middle, opening towards the slot), the eight 1 µF capacitors (bottom). The panel lies on the other side of 11.8 – 71.0 |
| 71.8 – 73.0 | FPC slot, 13.5 mm long, y = 10.05 – 23.55, 0.8 mm beyond the panel's edge |
| 73.0 – 76.0 | Strip where the sensor bus runs round the end of the FPC slot to the bridge |
| 76.0 – 77.5 | Milled slot to the sensor island (as 1.0) |
| 77.5 – 103 | Sensor island and SHT45 tongue, exactly as in 1.0, moved right by 28 mm |

- **Size: 103 × 34 mm** (1.0: 75 × 34). The height stays: the panel is 29.2 mm high. It came out 2 mm longer than first estimated: the FPC slot lies right in front of the bridge that carries the sensor bus across the sensor slot, so the bus has to run round the slot's end, and that needs a strip of about 3 mm between the two slots.
- **Assumption**: the panel's left edge keeps 5 mm from the end of the antenna keep-out (x = 6.9 mm in 1.0), so it spans x = 11.8 to 71.0. Espressif asks for no metal near the antenna; the panel has thin metal tracks on glass. Less gap gives a shorter board.
- The generator (`hardware/rev-2.0/tools/gen_pcb.py`) builds this from the 1.0 placement: everything from x = 48 rightwards moves by 28 mm, nothing else of 1.0 moves, and the new parts go into the gap. The panel's outline is printed on the back silkscreen.
- The component side under the panel is free for parts, since the panel is on the other side. Only the FPC slot has to lie beyond the panel's edge.
- Seen from the room the board is mirrored: the antenna end is on the right, the sensors on the left. Up stays up, so the arrangement of the sensors for rising heat is unchanged.
- **Mounting holes**: the two at the antenna end are outside the panel; the two on the sensor island stay where they are.
- **Under the panel** (on the back side): no parts, as everywhere on the back. Vias are covered by solder mask. The panel is held by the case or by double-sided tape; the tape must not cover the FPC slot.
- **J3 (the serial header)** lies under the panel. Its holes stay; a pin header would have to be soldered in from the component side and cut flush on the back, or the panel taken off first.

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
- The connector's front edge is about 5.8 mm from the slot: of the tail's 14.3 mm, about 5 mm of the flexible part go into the slot and the U-turn, the rest and 2.3 mm of the stiffener lie flat on the board, and 3.7 mm go into the connector.
- **The tail is short.** Of its 14.3 mm, 6 mm are stiff, which leaves about 8 mm to reach the slot, pass through the 1.6 mm board in two bends and come out on top. Feasible, but **check with a 1:1 paper print of the board edge and the real panel** before ordering.
- Both connectors are extended parts at JLCPCB; for a board assembled at home that costs nothing extra. Price and stock of C3249999 have not been seen yet.
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

Checked at LCSC on 2026-11-22 unless marked. The 1 MΩ and 2.2 Ω resistors are 0402 at 0.0625 W, above the 0.05 W asked for.

- **The 25 V capacitors go to 0603 and 0805, as Good Display asks**, even though the rest of the board is 0402. A 1 µF 0402 ceramic keeps only a small part of its capacitance at 20 V; the larger case keeps more.
- The panel's voltages are about ±20 V on `VGH`/`VGL`, so 25 V capacitors and 30 V diodes and MOSFET.

### Pins

The panel needs six GPIOs. IO2, IO3, IO4, IO5 and IO15 were free. **Decided 2026-11-22 (Norman): the 32 kHz crystal option is dropped**, because the device is not battery powered; that frees IO0 and IO1, which revision 1.0 kept unconnected for it. The sixth display pin is IO1, and the BMP580 interrupt stays.

| GPIO | Net | Why this pin |
| --- | --- | --- |
| IO3 | `EPD_BUSY` | Driven by the panel, so not on a start-up configuration pin (IO4, IO5, IO15 are) |
| IO10 | `EPD_RST` | **Decided 2026-11-22 (Norman)**: moved from IO2 after the first routing run, which could not route it from the module's antenna end; IO10 is at the end nearest the connector. It floats while the chip is in reset, which is harmless for the panel's reset line. IO2 is now the spare. |
| IO4 | `EPD_SCK` | Start-up configuration pin; fine as an output that the ESP32 drives only after start |
| IO5 | `EPD_MOSI` | as IO4 |
| IO15 | `EPD_CS` | as IO4 |
| IO1 | `EPD_DC` | |
| IO0 | `BMP_INT` | **Decided 2026-11-22 (Norman)**: the BMP580 interrupt moves here from IO10. IO0 is one of the pins that can wake the chip from deep sleep and be read by the low-power core, which IO10 cannot (see the BMP580 item in [`next-revision.md`](next-revision.md)); it is not a start-up configuration pin. Costs nothing, since 2.0 changes the pin map anyway. |

- SPI goes through the GPIO matrix to these pins; fine at the panel's clock (a few MHz to 20 MHz).
- No pull-ups: while the ESP32 is in reset the panel is in deep sleep and ignores the bus until it is reset. **Assumption**; a 100 kΩ pull-up on `EPD_CS` would cost one resistor of a type already on the board.
- The final order on the module pins is chosen during layout, so that the six tracks reach the connector without crossing.
- `pins.h` and [`schematic.md`](schematic.md) change together; the firmware gets a board revision check (see [Firmware](#firmware)).

## Buttons and LED

The component side faces the wall, so a normal push button and a top-facing LED cannot be seen or pressed from the room.

- **BOOT/USER**: a **side-press button on the top edge** of the board, so a finger or a plunger in the case reaches it from above. Proposed: Kinghelm KH-3635-CAJ, LCSC C530670, 6 × 3 mm, 3.5 mm high, right-angle, about 0.03 USD, 63,000 in stock. Its footprint still has to be drawn from its datasheet.
- **RESET** stays a top-actuated button: it is only for bring-up.
- **Status LED**: keep the 1.0 LED at the top edge (it already sits there), and let the case carry the light to the room with a light pipe or a thin wall. **Assumption**; the alternative is a side-view LED. With a display, the LED matters less: it is mainly for the moments when the display cannot show anything (start, firmware update, crash).

## What stays as in 1.0

Supply (USB-C, fuse, buck converter, sensor and Qwiic regulators), sensors and their island and tongue, Qwiic connector, serial header J3, sensor header J4, test pads, the 0402 passives.

**Assumption**: 0402 stays. It can be placed by hand with tweezers and a stencil, and the layout of 1.0 can be reused. 0603 would be easier for a first hand assembly but would need the whole board placed again.

## Firmware

- An SPI display driver for the SSD1680 (no ESP-IDF component fits; a short driver of our own), a display task, and a screen layout. Refresh: partial updates when values change, a full refresh about once an hour.
- **Board revision**: 2.0 changes the pin map, so the firmware has to know which board it runs on. **Open**: a build option per board, or detection at run time (for example by reading `EPD_BUSY` with a pull-down: the panel holds it low when present). Not decided.

## Layout as generated

State of 2026-11-22: `gen_pcb.py` gives a fully routed board, 103 × 34 mm; KiCad counts no open connection, DRC has no violation, the board matches the schematic, and the ground pours are one connected piece. Pictures: [`../images/rev-2.0/`](../images/rev-2.0/). What differs from revision 1.0's layout ([`layout.md`](layout.md)):

- **Sensor bus drawn by hand** (`SENSOR_BUS` in `gen_pcb.py`): `+3V3_SENS`, `I2C_SCL`, `I2C_SDA` and `BMP_INT` run on the top layer along the bottom edge (y 31.9–33.2, below C17–C24), then up the strip right of the FPC slot (x 73.6–74.9) into the bridge tracks. Left to the router, the bus crossed the display area diagonally on both layers, cut pockets out of the pours and left `BMP_INT` without a route. Its left ends are staggered like steps so that the router reaches each run from above. It starts at x 39.2, right of the USB connector's shell.
- **Bottom layer kept as ground** (`DISPLAY_GROUND_AREAS`): the FPC landing area and the strip between the two slots over the full height (this is the sensor island's ground return), behind J5, under the boost converter's switching loop, and along the bottom edge below the module (tracks from the module's corner pins closed in the ground via of the EN capacitor there).
- The router counts a cut-off pocket of the ground pours as a failure, so an attempt with one is never kept.
- The rules of 1.0 hold unchanged: nothing under the USB connector on either layer (checked on the generated board), ground behind it, the SCD41 supply link clear of the vent hole.
- Costs of the bus route, from `audit_pcb.py`: sensor supply to the SHT45 107.6 mm (166 mΩ); `BMP_INT` runs beside `I2C_SDA` for 58 mm. The 5 V path from the connector's farther supply pad to the fuse was 73 mm in this run and gets a hand-drawn link.
- The panel's outline is on the back silkscreen (broken where it would cross a through-hole pad), with two ticks and "FPC" at the edge the tail leaves from.

## Not checked yet

- The GDEY0213B74 specification was read on 2026-11-22 (37 pages, revision 1.0 of 2021-03-17): pin table, drawing, reference circuit. Not yet read: its DC characteristics (an image in the PDF) for current in deep sleep and the SPI clock limit.
- Which side of the FPC tail carries the contacts, on a real panel.
- LCSC numbers, stock and prices of every new part (see the table above).
- Whether the panel can be bought as a single piece at a sensible price outside Good Display's own shop (LCSC listings were out of stock on 2026-11-22).
- The side-press button part.

## Next steps

1. Footprints from the makers' land patterns: FPC connector (Kinghelm, replaces the Hirose FH12 stand-in) and the side-press BOOT button, in `gen_footprints.py`.
2. A 1:1 paper print and the real panel: tail reach round the slot, contact side, and pin 1's position after the U-turn (`FPC_REVERSED`).
3. Firmware: board revision mechanism, 2.0 pin map, display driver.
4. Order bare boards and a stencil only after Norman's go-ahead.

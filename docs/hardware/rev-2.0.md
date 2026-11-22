# Revision 2.0 — e-paper display (draft)

Status: **first draft of the concept, nothing drawn yet.** Started 2026-11-22. Every point marked **Assumption** or **Open** still needs a decision or a check against a datasheet. Revision 1.0 stays as ordered on 2026-11-20 (commit `8c89155` is the design that was sent to JLCPCB); its documents ([`schematic.md`](schematic.md), [`layout.md`](layout.md)) describe 1.0 until the 2.0 board is drawn.

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
| 26 – ~71 | USB-C, protection, fuse, regulators, buttons, Qwiic as in 1.0, plus the FPC connector and the boost circuit for the panel. The panel lies on the other side of this zone, from x ≈ 12 to 71 |
| ~72.5 – 73.7 | FPC slot (about 13.5 × 1.2 mm), just beyond the panel's edge |
| ~75 – 76.5 | Milled slot to the sensor island (as 1.0) |
| ~76.5 – ~101 | Sensor island and SHT45 tongue (as 1.0, moved right) |

- **Size: about 101 × 34 mm** (1.0: 75 × 34). The height stays: the panel is 29.2 mm high. **Assumption**: the panel's left edge keeps 5 mm from the end of the antenna keep-out (x = 6.9 mm in 1.0), so it spans about x = 12 to 71. Espressif asks for no metal near the antenna; the panel has thin metal tracks on glass. Less gap gives a shorter board.
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
| **A (proposed)** | Through the slot, then **back** under the panel's edge (a U-turn round the slot's edge) | up, away from the board | **dual-contact**: Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, LCSC **C3249999**, flip lock, 2.0 mm high | about 101 mm |
| B | Through the slot and **onwards**, away from the panel (an S-bend) | down, onto the board | bottom-contact: BOOMELE 0.5-24P FG, LCSC **C20688**, flip lock, 2.0 mm high, the common one, about 0.08 USD | about 7 mm longer: the connector has to sit beyond the slot |

- In route A the connector sits under the panel's edge, with its opening facing the slot. A dual-contact connector also works if the assumption about the contact side above is wrong.
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

| Ref (Good Display) | Part | Good Display's requirement | Proposed | LCSC |
| --- | --- | --- | --- | --- |
| P1 | FPC connector | 24 pins, 0.5 mm | see above | C3249999 or C20688 |
| Q1 | N-MOSFET | Si1308EDL, or: ≥ 30 V, Vgs(th) ≤ 1.5 V, Rds(on) ≤ 400 mΩ | Si1308EDL (SOT-323) as drawn; AO3400A (SOT-23, 30 V, Vgs(th) ≤ 1.45 V) meets the same figures and is a basic part | to look up; AO3400A C20917 |
| D1–D3 | Schottky diodes | MBR0530, or: ≥ 30 V, ≥ 500 mA, Vf ≤ 430 mV | MBR0530 (SOD-123) | to look up |
| L1 | Inductor | 47 µH, 500 mA, "refer to NR3015" (Taiyo Yuden, 3 × 3 mm) | NR3015T470M or equivalent | to look up |
| R1, R2 | 1 MΩ, 2.2 Ω | 0603/0805, 1 %, ≥ 0.05 W | 0402, 1 %, 0.0625 W: meets the rating, smaller than drawn | to look up |
| C2, C5–C7, C9–C12 | 8 × 1 µF | 0603/0805, X5R/X7R, ≥ 25 V | 1 µF 25 V **0603** | to look up |
| C3, C4 | 2 × 4.7 µF | as above | 4.7 µF 25 V 0805 | to look up |

- **The 25 V capacitors go to 0603 and 0805, as Good Display asks**, even though the rest of the board is 0402. A 1 µF 0402 ceramic keeps only a small part of its capacitance at 20 V; the larger case keeps more.
- The panel's voltages are about ±20 V on `VGH`/`VGL`, so 25 V capacitors and 30 V diodes and MOSFET.
- LCSC numbers marked "to look up" are not chosen yet; the AO3400A number is from memory.

### Pins

The panel needs six GPIOs. IO2, IO3, IO4, IO5 and IO15 were free. **Decided 2026-11-22 (Norman): the 32 kHz crystal option is dropped**, because the device is not battery powered; that frees IO0 and IO1, which revision 1.0 kept unconnected for it. The sixth display pin is IO1, and the BMP580 interrupt stays.

| GPIO | Net | Why this pin |
| --- | --- | --- |
| IO3 | `EPD_BUSY` | Driven by the panel, so not on a start-up configuration pin (IO4, IO5, IO15 are) |
| IO2 | `EPD_RST` | |
| IO4 | `EPD_SCK` | Start-up configuration pin; fine as an output that the ESP32 drives only after start |
| IO5 | `EPD_MOSI` | as IO4 |
| IO15 | `EPD_CS` | as IO4 |
| IO1 | `EPD_DC` | |
| IO0 | spare, or `BMP_INT` | **Proposed**: move the BMP580 interrupt here from IO10. IO0 is one of the pins that can wake the chip from deep sleep and be read by the low-power core, which IO10 cannot (see the BMP580 item in [`next-revision.md`](next-revision.md)); it is not a start-up configuration pin. Costs nothing, since 2.0 changes the pin map anyway. IO10 would then be the spare. |

- SPI goes through the GPIO matrix to these pins; fine at the panel's clock (a few MHz to 20 MHz).
- No pull-ups: while the ESP32 is in reset the panel is in deep sleep and ignores the bus until it is reset. **Assumption**; a 100 kΩ pull-up on `EPD_CS` would cost one resistor of a type already on the board.
- The final order on the module pins is chosen during layout, so that the six tracks reach the connector without crossing.
- `pins.h` and [`schematic.md`](schematic.md) change together; the firmware gets a board revision check (see [Firmware](#firmware)).

## Buttons and LED

The component side faces the wall, so a normal push button and a top-facing LED cannot be seen or pressed from the room.

- **BOOT/USER**: a **side-press button on the top edge** of the board, so a finger or a plunger in the case reaches it from above. **Open**: part (a common SMD side-actuated tactile switch at LCSC; not looked up yet).
- **RESET** stays a top-actuated button: it is only for bring-up.
- **Status LED**: keep the 1.0 LED at the top edge (it already sits there), and let the case carry the light to the room with a light pipe or a thin wall. **Assumption**; the alternative is a side-view LED. With a display, the LED matters less: it is mainly for the moments when the display cannot show anything (start, firmware update, crash).

## What stays as in 1.0

Supply (USB-C, fuse, buck converter, sensor and Qwiic regulators), sensors and their island and tongue, Qwiic connector, serial header J3, sensor header J4, test pads, the 0402 passives.

**Assumption**: 0402 stays. It can be placed by hand with tweezers and a stencil, and the layout of 1.0 can be reused. 0603 would be easier for a first hand assembly but would need the whole board placed again.

## Firmware

- An SPI display driver for the SSD1680 (no ESP-IDF component fits; a short driver of our own), a display task, and a screen layout. Refresh: partial updates when values change, a full refresh about once an hour.
- **Board revision**: 2.0 changes the pin map, so the firmware has to know which board it runs on. **Open**: a build option per board, or detection at run time (for example by reading `EPD_BUSY` with a pull-down: the panel holds it low when present). Not decided.

## Not checked yet

- The GDEY0213B74 specification was read on 2026-11-22 (37 pages, revision 1.0 of 2021-03-17): pin table, drawing, reference circuit. Not yet read: its DC characteristics (an image in the PDF) for current in deep sleep and the SPI clock limit.
- Which side of the FPC tail carries the contacts, on a real panel.
- LCSC numbers, stock and prices of every new part (see the table above).
- Whether the panel can be bought as a single piece at a sensible price outside Good Display's own shop (LCSC listings were out of stock on 2026-11-22).
- The side-press button part.

## Next steps

1. Norman: confirm moving the BMP580 interrupt to IO0, the board length (about 101 mm) and FPC route A with the dual-contact connector.
2. Schematic: add the panel block and the new pins in `gen_schematic.py`, run `check_schematic.py`.
3. Footprints: FPC connector and side button in `gen_footprints.py` if KiCad's library has none that fit.
4. Board: new outline, FPC slot and placement in `gen_pcb.py`, route, `check_pcb.py`, `audit_pcb.py`. These need KiCad on Norman's computer.
5. Order bare boards and a stencil only after Norman's go-ahead.

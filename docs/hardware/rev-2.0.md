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
| 26 – 48 | USB-C, protection, fuse, regulators, buttons, Qwiic (as 1.0, rearranged where the new parts need room) |
| 48 – ~70 | **New**: FPC slot, FPC connector, boost circuit for the panel |
| ~71.5 – 73 | Milled slot to the sensor island (as 1.0) |
| ~73 – ~99 | Sensor island and SHT45 tongue (as 1.0, moved right) |

- **Size: about 99 × 34 mm** (1.0: 75 × 34). The height stays: the panel is 29.2 mm high. **Assumption**: the panel's left edge keeps 5 mm from the end of the antenna keep-out (x = 6.9 mm in 1.0), so it spans about x = 12 to 71. Espressif asks for no metal near the antenna; the panel has thin metal tracks on glass. Less gap gives a shorter board.
- Seen from the room the board is mirrored: the antenna end is on the right, the sensors on the left. Up stays up, so the arrangement of the sensors for rising heat is unchanged.
- **Mounting holes**: the two at the antenna end are outside the panel; the two on the sensor island stay where they are. Nothing changes there.
- **Under the panel** (on the back side): no parts, as everywhere on the back. Vias are covered by solder mask. The panel is held by the case or by double-sided tape; the tape must not cover the FPC slot.
- **J3 (the serial header)** lies under the panel. Its holes stay; a pin header would have to be soldered in from the component side and cut flush on the back, or the panel taken off first.

**Open**: the exact panel position depends on where its FPC leaves the glass (centred on a short edge or offset) and how long the tail is. Good Display's drawing has it; the text of the specification could not be read here (see [Not checked yet](#not-checked-yet)).

## FPC slot and connector

- The tail leaves the panel at its short edge towards the sensor side, so that the FPC and the boost circuit stay away from the antenna. It goes through a slot about 14 × 1.2 mm (the tail is about 12.5 mm wide for 24 contacts, **to be confirmed**) just beyond the panel's edge and into a connector on the component side next to the slot.
- **Which side of the tail carries the contacts decides the connector.** A tail that goes through the slot and carries on in the same direction arrives with the face that was against the board facing away from it; one that turns back arrives the other way round. Two ways to settle it:
  - **Dual-contact connector** (contacts top and bottom): works either way. Candidate: Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, LCSC **C3249999**, flip lock, 2.0 mm high, extended part. Price and stock not seen yet.
  - **Bottom-contact connector** once the drawing shows the contact side: BOOMELE 0.5-24P FG, LCSC **C20688**, flip lock, 2.0 mm high, extended part, 1,100 in stock at LCSC, from about 0.08 USD. This is the common one.
  - **Recommendation**: C20688 if the drawing settles the contact side, otherwise C3249999.
- Hand assembly: 0.5 mm pitch is the finest pitch on the board after the sensors; with a stencil and a hot plate it is fine. Bridges are cleared with the rework station and flux.

## Schematic additions

### Panel connector and boost circuit

**Assumption**: Good Display's usual reference circuit for its 24-pin SSD16xx panels; its values have **not** been checked against the GDEY0213B74 specification yet. Pin numbers below are from the specification of the front-lit variant GDEY0213B74-FL01, which uses the same 24-pin layout (its pins 6 and 7 go to a temperature sensor of the front light).

| FPC pin | Name | Connection |
| --- | --- | --- |
| 1, 4 | NC | open |
| 2 | GDR | gate of the boost MOSFET |
| 3 | RESE | MOSFET source, sense resistor to ground |
| 5 | VSH2 | 1 µF to ground |
| 6, 7 | TSCL, TSDA | open (temperature sensor of the front-lit variant) |
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
| 19 | VPP | 1 µF to ground (test pin) |
| 20 | VSH1 | 1 µF to ground |
| 21 | VGH | 1 µF to ground, fed by the boost |
| 22 | VSL | 1 µF to ground |
| 23 | VGL | 1 µF to ground, fed by the charge pump |
| 24 | VCOM | 1 µF to ground |

Boost circuit: inductor from +3V3 to the switch node, N-MOSFET from the switch node to `RESE`, sense resistor from `RESE` to ground, one Schottky diode from the switch node to `VGH`, and a capacitor plus two Schottky diodes from the switch node as a charge pump down to `VGL`. The capacitors on `VGH`, `VGL`, `VSH1`, `VSH2`, `VSL`, `VCOM` see up to about ±20 V and need a 25 V rating.

| Part | Proposed | LCSC | Note |
| --- | --- | --- | --- |
| FPC connector | see above | C20688 or C3249999 | extended |
| N-MOSFET | AO3400A, SOT-23, 30 V | C20917 | basic; Good Display uses a Si1308EDL. **To check**: rating, gate threshold at the panel's gate drive |
| 3 Schottky diodes | B5819W, SOD-123, 40 V 1 A | C8598 | basic; Good Display uses MBR0530 (30 V). |
| Inductor | 10 µH, small SMD | open | **To check**: value against the specification |
| Sense resistor | about 2.2 Ω, 0402 | open | **To check**: value against the specification |
| Capacitors | 1 µF 25 V, 0402 (CL05A105KA5NQNC) | C52923 | already on the board, about 11 more |

The LCSC numbers in this table were written from memory, not looked up: **all to be verified** before the BOM is final.

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

- **The GDEY0213B74 specification itself**: the reference circuit (component values), the FPC drawing (tail width, position, length, contact side). The PDF is on Good Display's site (product page 391, "Specification") but could not be downloaded from the tools used here; it needs to be read before the schematic is final.
- LCSC numbers, stock and prices of every new part (see the table above).
- Whether the panel can be bought as a single piece at a sensible price outside Good Display's own shop (LCSC listings were out of stock on 2026-11-22).
- The side-press button part.

## Next steps

1. Norman: confirm moving the BMP580 interrupt to IO0, and the board length, and get the specification PDF into the project.
2. Schematic: add the panel block and the new pins in `gen_schematic.py`, run `check_schematic.py`.
3. Footprints: FPC connector and side button in `gen_footprints.py` if KiCad's library has none that fit.
4. Board: new outline, FPC slot and placement in `gen_pcb.py`, route, `check_pcb.py`, `audit_pcb.py`. These need KiCad on Norman's computer.
5. Order bare boards and a stencil only after Norman's go-ahead.

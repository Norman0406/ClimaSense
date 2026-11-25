# Design review before ordering — ClimaSense revision 2.0

Reviewed on 2026-11-24, at commit `8b32dfd`. Subject: `hardware/rev-2.0/` (schematic and board; no manufacturing files exist yet). Revision 1.0 is frozen and already ordered; it was not re-reviewed, but everything revision 2.0 takes over from it was checked again here.

**Verdict in one line: conditional go. No error was found that makes the board non-functional. Two things should be fixed or decided before the order (findings 1 and 2), and the board should not be ordered before revision 1.0 has been powered up (finding 3).** Details in [section 6](#6-verdict).

## Status since the review (last updated 2026-11-25)

The review below describes the design as it was at commit `8b32dfd` and is left as written. This table says what has happened to each finding since. Not committed yet at the time of writing: the changes are in the working tree.

| Finding | Status | What was done |
| --- | --- | --- |
| 1. `QWIIC_EN` under the buck inductor L1 | **Fixed 2026-11-25** | The top layer under L1 is a keep-out for tracks, vias and pour (`L1_UNDER` in `gen_pcb.py`). Closing the strip alone did not route (none of twelve seeds), so `QWIIC_EN` now passes L1 on the bottom layer, drawn by hand (`L1_HOP`: vias at (34.2, 13.1) and (37.7, 12.5), 3.5 mm between them). Price: a 0.6 mm slit in the bottom ground under the inductor, 5 mm from the buck converter's input loop. Seven of twelve seeds route the board; KiCad's check and the audit pass. The note in `rev-2.0.md` that named `BMP_INT` is corrected. |
| 5. Regulator input capacitors C3, C15 | **Fixed 2026-11-25** | Both are now CL10A105KB8NNNC (0603, C15849, 0.66 µF at 5 V). C15 moved to (44.775, 14.45), C3 to (68.775, 25.5). `+5V` now carries the same 12 µF nominal as before (note 27 unchanged). |
| 16. Documents against the design | **Partly** | Corrected: the net under L1; the schematic value of C17–C24 ("1uF/50V"); `rev-2.0.md` has a dated section on the two fixes and now gives 228 vias. Still open: the stale lower sections of `rev-2.0.md`, `hardware/rev-2.0/README.md`, the 2.0 pin table, `schematic.md`, `ordering.md`, fab or home assembly. |
| 2. Assembly rails at the overhanging parts | Open | Order remark, at ordering time |
| 3. Revision 1.0 not powered yet; no 2.0 firmware | Open | |
| 4. Fold margin at a frame height of 4.75 mm | Open | Decision before the frame is printed |
| 6 to 15, 17 to 22 | Open | None of them was a condition for ordering |

Of the five conditions in the verdict, 1 and 4 are met by these changes; 2, 3 and 5 remain.

How the review was done: the project was copied to a temporary folder outside the repository and all tools ran there; nothing in the repository was changed except this file. Six independent passes were made: five by scope (microcontroller, power and USB, sensors and small parts, display, manufacturing and parts), each reading the manufacturers' datasheets, and a sixth that re-checked every Major finding and every pinout marked "verified" from the primary sources without seeing the first passes' reasoning. Where the passes disagreed on severity, this report says so.

---

## 1. Context

### What the board does

An indoor air sensor that hangs on a wall in landscape, USB cable down, components facing the room. An ESP32-C6 module reads four sensors over I2C and publishes over Wi-Fi (MQTT); Wi-Fi is set up through a captive portal. New in revision 2.0: a 2.13" black-and-white e-paper panel that lies above the components of the controller side on a printed frame, with its flexible tail folded back under it into a connector.

| | |
| --- | --- |
| Microcontroller | ESP32-C6-WROOM-1-N8 (U4), native USB for flashing, UART0 on test pads as fallback |
| Sensors (I2C on IO6/IO7, own rail) | SHT45 0x44 (U5), SCD41 0x62 (U6), SGP41 0x59 (U7), BMP580 0x47 (U8) |
| Display | Good Display GDEY0213B74 (SSD1680), 24-pin 0.5 mm FPC connector J5, maker's discrete boost and charge pump (L2, Q1, D2–D4, R18, R19, C17–C26) |
| Other | RGB status LED D1, Qwiic connector J2 on its own bus and switched rail, two side-push buttons on the top edge (SW1 RESET, SW2 BOOT/USER), 16 test pads on the back |
| Board | 103 × 34 mm, 2 layers, 1.6 mm, 69 placed parts, all on the top side; 229 vias; milled slots round the sensor island and the SHT45 tongue |

### Power: sources, rails, load

Single source: USB-C, 5 V, as a sink with 5.1 kΩ on each CC pin. No battery.

| Rail | Made by | Loads | Peak | Average | Capacity |
| --- | --- | --- | --- | --- | --- |
| VBUS → `+5V` | J1 → fuse F1 (0.75 A hold at 20 °C, 0.54 A at 60 °C) | buck converter, both linear regulators | 0.49 A (0.59 A with the SHT45 heater) | about 0.10 A | fuse and tracks adequate |
| `+3V3` | TPS62A01 (U2), 1 µH, 68 k / 15 k → 3.32 V (3.22–3.43 V over tolerance) | ESP32-C6 (354 mA transmit peak), LED (13 mA), panel logic and boost (3.5 mA typical in a refresh), pull-ups | 0.38 A | about 0.1 A | 1 A converter; current limit ≥ 1.3 A; inductor saturates at 4.7 A |
| `+3V3_SENS` | TLV75533 (U3) from `+5V`, enable `SENS_EN` (IO10, pulled up) | SCD41 (205 mA peak, 18 mA average), SGP41 (4.8 mA), SHT45 (0.5 mA; 100 mA if its heater is used), BMP580 | 211 mA (311 mA with heater) | about 24 mA | 500 mA regulator; 47 mW average, 11 °C rise |
| `+3V3_QWIIC` | TLV75533 (U9) from `+5V`, enable `QWIIC_EN` (IO11, pulled down) | whatever is plugged in | current limit 0.56–0.87 A | 0 (off by default) | about 150 mA continuous in a warm case (finding 16) |
| Panel driving voltages | panel's own controller with L2/Q1/D2–D4 | VGH/VGL about ±20 V, VSH1/VSL about ±15 V | not published (assumption A3) | — | 30 V switch and diodes, 50 V and 25 V capacitors |

Calculations behind these figures are with the findings and in [section 3](#3-coverage).

### Environment and enclosure

- Indoor, wall-mounted; no temperature range is documented. **Assumption A1:** 0 to 40 °C room air, up to about 50 °C inside the case. The panel is rated 0 to 50 °C and is the narrowest part.
- The case is not designed. What exists is a concept (`docs/hardware/next-revision.md`, section 7): a printed frame 4.75 mm above the board carrying the panel, a flat front with a bezel, a wall round the sensor area, plungers for the two buttons, a light pipe for the LED. The board reserves seven free spots and two 2.2 mm holes (FH1, FH2) for the frame, and four M3 holes (H1–H4).
- Sensor placement follows rising heat: SCD41 and SGP41 at the top, SHT45 below on a tongue cut free on three sides, everything else behind a milled slot.

### Fab, stackup, order parameters

- Fab and assembler: JLCPCB. 2 layers, 1.6 mm FR4, 1 oz, ENIG, no impedance control. Assembly: Standard PCBA, top side only.
- Documented order parameters exist only for revision 1.0 (`docs/hardware/ordering.md`): 5 boards, 2 assembled, "confirm parts placement" on, no washing. **The documents contradict each other for 2.0:** `CLAUDE.md` says the board is fully assembled by the fab; `docs/hardware/rev-2.0.md` says test revisions are assembled at home on a hot plate from bare boards and a stencil. This review checked the design for both paths (finding 22).

### Where things are

| | |
| --- | --- |
| EDA tool | KiCad 10.0.8 (`C:\Program Files\KiCad\10.0`) |
| Schematic | `hardware/rev-2.0/climasense.kicad_sch`, written by `tools/gen_schematic.py` (re-run here: reproduces the committed file byte for byte) |
| Board | `hardware/rev-2.0/climasense.kicad_pcb`, written by `tools/gen_pcb.py` (re-run here from scratch, 6.5 minutes: identical copper, 1,039 tracks and vias, identical placement) |
| Libraries | `hardware/rev-2.0/lib/` (project symbols and footprints), KiCad's standard libraries for the rest |
| BOM | fields `LCSC` and `MPN` on every schematic symbol; no BOM file exists yet (`tools/gen_fab.py` would write it) |
| Firmware | `firmware/` (ESP-IDF 6.1, C++). Pin map: `firmware/components/board/include/board/pins.h`, **still revision 1.0** |
| Datasheets | only the panel's is in the repo (`docs/datasheets/`); all others were fetched for this review |

### Pin map: netlist against firmware

| Signal | Revision 2.0 netlist | `pins.h` (revision 1.0) |
| --- | --- | --- |
| I2C SDA / SCL (sensors) | IO6 / IO7 | same |
| Qwiic SDA / SCL | IO19 / IO20 | same |
| `QWIIC_EN` | IO11 | same |
| LED green / red / blue | IO21 / IO22 / IO23 | same |
| BOOT button | IO9 | same |
| `SENS_EN` | **IO10** | **IO18** |
| `BMP_INT` | **IO0** | **IO10** |
| `EPD_MOSI` / `EPD_SCK` / `EPD_CS` | IO3 / IO18 / IO15 | missing |
| `EPD_DC` / `EPD_RST` / `EPD_BUSY` | IO4 / IO5 / IO1 | missing |
| UART0 TX / RX | IO16 / IO17 (TP15 / TP16) | not needed |

All assigned functions exist on these pins (ESP32-C6 datasheet v1.6, table 2-7; module datasheet v1.4, table 3-1).

---

## 2. Findings

Severity: **Blocker** (will not work or will be damaged), **Major** (likely failure or marginal), **Minor**, **Note**. Coordinates are board coordinates in millimetres from the top-left corner, y downwards, as in the project's documents (KiCad's are 100 / 60 larger).

**No Blocker was found.**

### Major

#### 1. `QWIIC_EN` runs under the buck inductor L1, between its pads — Major (marginal; the passes disagree)

- **Where:** top layer, 0.2 mm track of `/QWIIC_EN` from (34.8, 12.4) to (42.1, 12.4), under the body of L1 (Murata DFE252012F-1R0M, at (36.0, 12.5)). Measured: 0.45 mm from L1's switch-node pad, 0.25 mm from its `+3V3` pad; the diagonal that feeds it passes 0.36 mm from the switch-node pad.
- **What is wrong:**
  - Murata forbids it for this part. Reference specification J(E)TE243A-0017D-01 (covers DFE252012F-1R0M=P2), page 7, notice 2: "This product employs a core with low insulation resistance … Do not make any through holes and copper pattern under the coil, except a copper pattern to the electrode."
  - It is the worst net for that lane: `QWIIC_EN` is held low only by R15 (100 kΩ) while IO11 is high-impedance in reset (ESP32-C6 datasheet v1.6, table 2-1), and it is the enable input of U9, which reads low only below 0.3 V (TLV755P, SBVS320D, table 5.5). The node next to it swings 5 V at 2.4 MHz.
  - `docs/hardware/rev-2.0.md` (line 271) says the track there is `BMP_INT`, 0.35 mm from the pad. It is not.
- **How bad:** the coupling was estimated three times: 60 mV, "tens of millivolts", and 32 to 290 mV depending on how closely the inductor body sits on the solder mask. So a false turn-on of the Qwiic supply in reset is unlikely but not excluded, and the manufacturer's notice is broken either way. Two passes rated this Minor, one Major; it is listed as Major because the fix is cheap and the rule is the manufacturer's own.
- **Fix (one of):**
  - Route `QWIIC_EN` round L1 on the top layer and give the lane to nothing.
  - If the board does not route without the lane: put a low-impedance net there, or add 100 nF from `QWIIC_EN` to ground at U9 pin 3 (C1525, already on the BOM) and make R15 10 kΩ (C25744, already on the BOM). The second variant still has copper under the coil.

#### 2. Assembly rails: the buttons and the USB connector overhang both long edges — Major for the order, no layout change

- **Where:** SW1 and SW2 (Alps SKRTLAE010): button tip 0.22 mm beyond the top edge (0.12 to 0.32 mm with Alps' tolerance; the travel is 0.2 mm). J1: shell 0.45 to 0.5 mm beyond the bottom edge, as its maker intends.
- **What is wrong:** JLCPCB's Standard PCBA needs edge rails, and on a 103 × 34 mm board they go on the two long edges, where these three parts overhang. Revision 1.0 had only J1 over an edge, and the order remark in `docs/hardware/ordering.md` names only J1. A rail joined flush to the top edge sits inside the buttons' travel: the switches cannot be placed, or are soldered pressed.
- **Evidence (JLCPCB pages read 2026-11-24):** assembly capabilities (rails "Necessary" for Standard PCBA); panelization (V-cut needs 70 × 70 mm at least); terms of the assembly service (for boards under 70 × 70 mm JLCPCB "will select a suitable production method for edge rail, for instance, mouse bite"; component bodies 2.5 mm from the edge); assembly fixtures ("when the SMT components exceed the PCB board … the carrier needs to be used"). No page gives a rule for how far a part may overhang, so how JLCPCB will handle it is **not verified**.
- **Also:** copper is 0.30 mm from the edge (LED pad, ground pours) and 0.33 mm (switch holding pads). That is fine for a routed edge (0.2 mm) and too little for a V-cut edge (0.4 mm).
- **Fix:** a new order remark, "Confirm production file" ticked, and a look at the rails in the production file before it is released. Wording in [section 5](#5-pre-order-checklist). Does not apply to bare boards for home assembly.

#### 3. Everything carried over from revision 1.0 is unproven, and there is no firmware for 2.0 — Major (risk, not a defect)

- Revision 1.0 was ordered on 2026-11-20 and has not been powered. Revision 2.0 reuses its USB circuit, both supplies, the module footprint, all four sensor footprints and the sensor island unchanged. `docs/hardware/rev-2.0.md` says it itself: ordering 2.0 before 1.0 has run means ordering it with all of 1.0's open questions. Several findings below (5, 6, 7, 8, 9, 18) can be settled on a 1.0 board with a multimeter and an oscilloscope.
- The firmware has no display driver, no 2.0 pin map and no way to tell the board revisions apart. **Revision 1.0 firmware must not be flashed onto a 2.0 board:** it would configure IO10 as an input with pull-down for the BMP580 interrupt, and IO10 is `SENS_EN` on 2.0. The internal 45 kΩ against R5 (100 kΩ) gives 3.32 V × 45 / 145 = 1.03 V at the sensor regulator's enable pin, exactly at its 1.0 V threshold.
- **Fix:** bring up a 1.0 board first; write the 2.0 pin map before the first 2.0 board is flashed.

### Minor

#### 4. The tail's fold has no margin at a frame height of 4.75 mm — Minor for the board, to settle before the frame is printed

- **Arithmetic** (specification page 7: tail 14.30 ± 0.30 mm, the last 6.00 ± 0.5 mm stiffened; Kinghelm drawing: tail enters J5 about 1.15 mm above the board, 2.1 mm deep; `gen_pcb.py`: frame 4.75 mm, J5's front 3.0 mm inside the glass edge; tail assumed to leave the glass 0.5 mm above the panel's back): drop 4.75 + 0.5 − 1.15 = 4.10 mm, half circle of radius 2.05 mm, arc 6.44 mm. Nominal: the fold begins 1.38 mm from the glass and leaves 0.48 mm of flexible tail before the stiffener. With the tail 0.3 mm short and the stiffener 0.5 mm long: −0.17 mm, so the half circle no longer fits and the fold becomes tighter and lopsided.
- **How bad:** the tail still reaches J5 in every case, and a tighter fold is allowed (Good Display's guideline: radius above 0.5 mm, 1.0 to 1.5 mm from the glass, never towards the front). The cost is a permanent push on the panel's edge. Two inputs are not from any drawing: the 0.5 mm exit height and the smallest bend radius in `gen_models.py`.
- **Fix:** no board change. Print the frame at about 4.3 mm (nominal 0.83 mm of flexible run, 0.18 mm worst case; the tallest parts under the panel are 3.3 mm) or decide with a real panel in hand.

#### 5. Input capacitors of both linear regulators are at the datasheet minimum — C3, C15 (`+5V`)

- CL05A105KA5NQNC (1 µF, 25 V, X5R, 0402) keeps 0.55 µF at 5 V (Samsung's DC-bias curve, −44.8 %), 0.50 µF with −10 % tolerance, less when warm and aged. TLV755P (SBVS320D, table 4-1, note 1): "Make sure the effective capacitance at the pin is greater than 0.47 µF". U3 is 39 mm from the fuse and feeds 205 mA pulses.
- **Fix:** C3 and C15 → CL10A105KB8NNNC (0603, C15849, already on the BOM for the display: 0.66 µF at 5 V), or a 2.2 µF 0402 rated 10 V or more. Outputs are fine (C4: 0.73 µF at the pin plus 9.5 µF on the rail; C16: 0.90 µF).

#### 6. Hot-plug overshoot on `+5V` may pass the regulators' 6.0 V limit — U3, U9

- Only ceramics on `+5V` (about 6.1 µF effective). With 0.3 to 1 µH of cable: Z₀ = √(1 µH / 6 µF) = 0.41 Ω; series resistance 0.2 to 0.6 Ω (cable, contacts, fuse 0.09–0.29 Ω) gives damping 0.24 to 0.7 and an overshoot of 46 % to 4 %: 6.6 V in the middle case, 7.7 V in the worst, from 5.25 V. Absolute maximum: TLV755P 6.0 V, TPS62A01 6.5 V. The protection part U1 sits before the fuse and clamps from 6 V upwards, so it does not protect a 6.0 V part.
- Calculated, not measured; already suspected in `next-revision.md`.
- **Fix:** measure on TP1 of a 1.0 board with a short thick cable. For 2.0, consider an unpopulated SOD-323 footprint for a clamp diode on `+5V`.

#### 7. SCD41 footprint (KiCad's standard one): 2.35 times the solder paste Sensirion asks for — U6

- Pads 1–20 are 1.9 × 0.85 mm with full paste (1.615 mm² each). Sensirion SCD4x datasheet v1.7, figure 4: lands 1.5 × 0.8 mm, paste 1.25 × 0.55 mm (0.688 mm²), and a 0.6 mm circle round the vent hole at (+2.94, +2.94) to be kept "free from solder and flux". Paste on pads 10 and 11 comes within 0.312 mm of the hole's centre. Sensirion's own land is equally close; the difference is the volume.
- Unchanged from revision 1.0, so the 1.0 boards will show whether it matters.
- **Fix:** a project footprint with Sensirion's lands and apertures.

#### 8. Reverse current through the sensor regulator at every unplug — U3

- TLV755P section 7.1.4 names a large output capacitor with a collapsing input as a damaging condition and limits the output to the input plus 0.3 V. `+3V3_SENS` holds about 9.5 µF effective against 0.55 µF at U3's input; on unplug the buck converter empties `+5V` within about 100 µs and 52 µJ flow back through U3. Common practice and probably harmless; TI gives no allowed value.
- **Fix (optional):** a Schottky diode from output to input (TI's figure 7-3), or the reverse-blocking regulator already noted in `next-revision.md`.

#### 9. Buttons: frame pads unconnected, signal on the outer terminals — SW1 (`EN`), SW2 (`BOOT`)

- The switch's metal frame pads carry no net, and the signal is on the two outer terminals next to the frame; the centre terminal is ground. `BOOT` (IO9) has only R7 (10 kΩ) and no capacitor. A discharge from a finger or a plunger lands on the frame beside the signal.
- **Fix:** tie the frame pads to ground and swap the roles (outer terminals ground, centre signal); optionally 100 nF on `BOOT`. With a plastic plunger in the case the risk is small.

#### 10. Display driving-voltage capacitors keep 15 to 20 % of their value — C19, C21, C22, C23, C26

- CL10A105KB8NNNC (1 µF, 50 V, X5R, 0603): −85 % at 20 V → 0.15 µF on VGH and VGL; −79 % at 15 V → 0.21 µF on VSH1 and VSL. C26 (4.7 µF, 25 V, 0805): 0.75 µF at 20 V. Samsung's typical curves.
- This is what Good Display's reference circuit asks for ("0603/0805; X5R/X7R; ≥ 25 V"), so the design equals the reference; a 25 V 0603 part would be worse. Voltage ratings are adequate everywhere.
- **Fix (optional, needs room in the capacitor row):** C19, C21, C22, C23 → CL21B105KBFNNNE (0805, 50 V, X7R, C28323): 0.70 µF at 20 V.

#### 11. VGH and VGL capacitors are 16 to 26 mm from their diodes — C22, C23, D2, D4

- `EPD_VGH`: D2 to C22 16.9 mm routed, 0.2 mm, two vias. `EPD_VGL`: D4 to C23 about 31 mm, two vias. The reference circuit (specification page 29) draws the VGH capacitor at the diode. The switching loop Q1–D2–C22–ground–R19 is about 20 × 5 mm: more ringing on a 30 V switch that works at about 20.5 V, and more noise during a refresh. It will work. The project decided on 2026-11-23 to leave it; that decision was made for the previous board.
- **Fix (optional):** a second capacitor at D2's cathode and at D4's anode.

#### 12. Bottom layer under the boost converter is not the unbroken ground the notes describe

- Bottom-layer tracks crossing x 48–61, y 20–30: `+5V` (0.4 mm) from (42.5, 17.3) via (51.6, 26.4) to (60.7, 26.4), under L2, C26, Q1 and D3; `+3V3` (0.2 mm) from (59.0, 17.0) via (53.4, 22.6) to (49.6, 22.6), between the ground vias of R19 and C25. The area reserved in `gen_pcb.py` is only x 52.0–59.3, y 23.0–26.3, and both tracks run just outside it, so the script's rule is kept and the notes' wording ("under the boost converter's switching loop") is not.
- **Fix:** widen the reserved area to cover L2 to R19 and re-route, or correct the notes.

#### 13. ±20 V nets at the board's minimum spacing, one under the boost inductor

- `EPD_VGL` (−20 V) runs on the top layer between L2's pads, 0.250 mm from the switch-node pad (40 V between them), and 0.200 mm from D2's cathode pad and the VGH via (40 V). Other minima: 0.154 mm to `EPD_VSL`, 0.166 mm VGH to VSH1 (5 V each). No breakdown risk under solder mask, and J5 itself puts these pins 0.25 mm apart; it is a margin against flux residue and humidity on uncleaned boards.
- **Fix:** lead `EPD_VGL` away from L2 and D2 with 0.4 mm or more.

#### 14. Antenna: panel, screws and board are inside Espressif's recommended clearance — U4, H1, H2

- Hardware Design Guidelines 1.4.7 ask for the antenna beyond the board edge and 15 mm of clearance in all directions. Here: antenna on bare board (as on 1.0), M3 holes 2.9 mm from it (as on 1.0), and new in 2.0 the panel glass starting 4.5 mm behind the antenna, about 4 mm above it (about 6 mm away). The copper keep-out itself is correct: nothing but two unplated holes left of x = 7.6.
- Effect: range, not function. Cannot be calculated.
- **Fix:** nylon screws or printed pegs at H1 and H2; compare signal strength with and without the panel on the first board.

#### 15. Silkscreen below JLCPCB's stated minimums

- All 26 texts are 0.8 mm high (JLCPCB: 1.0 mm); footprint outlines are 0.12 mm wide and one graphic 0.10 mm (JLCPCB: 0.15 mm). The project's own rule is 0.8 / 0.08 mm, so KiCad does not report it. Cosmetic; pin-1 triangles are filled shapes. J1's outline runs past the board edge (the two DRC warnings) and is cut off.
- **Fix at the next regeneration:** text 1.0 mm, lines 0.15 mm.

#### 16. Documents that contradict the design files

| Document | Says | Design files |
| --- | --- | --- |
| `docs/hardware/rev-2.0.md`, from "What is already settled" on | panel on the back, slot through the board, panel pin N on connector pin 25 − N, `EPD_RST` on IO18, test pads on the component side | the top section of the same file is right; the rest describes the board of 2026-11-23 |
| same, line 271 | `BMP_INT` under L1 | `QWIIC_EN` (finding 1) |
| same, line 11 | 210 vias | 229 (210 from the router plus 19 patch vias) |
| `hardware/rev-2.0/README.md` | display "on the back of the board", status 2026-11-23 | panel above the components |
| `docs/hardware/schematic.md` | `SENS_EN` IO18, `BMP_INT` IO10, IO0/IO1 kept free; "Qwiic supply good for about 200 mA continuously" | 2.0 pin map above; 200 mA gives 115 °C junction at 25 °C and 130 °C at 40 °C (0.39 W × 231 °C/W): document 150 mA |
| schematic value of C17–C24 | "1uF/25V" | the part is 50 V |
| `docs/hardware/ordering.md` | 75 × 34 mm, 28 BOM lines, six corrected parts | no 2.0 section: 103 × 34 mm, 36 lines, 69 parts |
| `CLAUDE.md` against `rev-2.0.md` | assembled by the fab / assembled at home | undecided for 2.0 |
| no document | — | a complete 2.0 pin table does not exist anywhere |

#### 17. Debug access with the panel mounted

- With the panel in place, J5's lock, the boost circuit, all eight driving-voltage capacitors, the fuse, L1 and both converters are covered. Of the driving voltages only VGH and VGL reach the back at all, as masked vias; `EPD_RST` has no pad; VBUS and `+3V3_QWIIC` have none; no rail can be isolated or its current measured without removing a part (F1, L1, R5).
- What works: swing the panel open about its tail, which is also the only way to plug the tail in. That needs a panel that is not taped down.
- **Fix (no BOM cost):** back-side pads for VGH, VGL, VSH1, VSL, VCOM and `EPD_RST`; a VBUS pad at F1.

#### 18. Status LED: green and blue may be dim — D1

- Forward voltage 2.7–3.8 V from a 3.3 V supply through 100 Ω: typically 3.6 mA (green) and 4.5 mA (blue), about 0.4 mA for a part at the top of the range. Red: 3.9 mA through 330 Ω. Carried over from 1.0 and known (`next-revision.md`); the 1.0 boards will show it.

#### 19. BMP580 land pattern follows one Bosch document and not the other — U8

- Pads are 0.25 × 0.275 mm, the package pad size, as the datasheet (BST-BMP580-DS004-02, section 8.2) says. Bosch's handling instruction (BST-BMP5xy-HS000-00, section 3.2) says package pad plus 25 µm on each side and no traces under the sensor. A bottom-layer `+3V3_SENS` track crosses under one corner of the package, (82.9, 26.3)–(81.7, 25.1). Carried over from 1.0.

#### 20. Dimensions exactly on JLCPCB's limits (known, no change proposed)

- Switch boss holes (unplated, 0.9 mm) to the switch's own pads: 0.200 and 0.204 mm against a rule of 0.2 mm with ±0.075 mm hole tolerance. Risk: a little bare copper at the hole wall.
- USB-C shell slots: 0.20 mm ring (JLCPCB: 0.20 minimum, 0.25 recommended); the 0.6 × 1.2 mm slot is at "length ≥ 2 × width". KiCad's library footprint, as on 1.0.
- J1's footprint differs slightly from HRO's current drawing (2020-12-08) in pad length and outer pad position (0.05 mm); all leads land on their pads. L1's pads (1.25 × 2.2 mm, 0.9 mm gap) are larger than Murata's (0.8 × 2.0 mm, 1.2 mm gap).

#### 21. Parts: one capacitor not recommended for new designs, one connector with low stock

- C2, CL21A226MAQNNNE (C45783): Samsung lists it as not recommended for new designs. 4.6 million in stock at JLCPCB; fine for this order. Later: CL21A226MAYNNNE (C602037).
- J5, C3249999: 981 in stock, one maker. Shou Han C6364666 and Jushuo C262683 have the same 24 × 0.5 mm pad row but holding pads about 0.35 mm further in: not drop-in without a footprint check.
- SCD41 (C3659294): 411 in stock on 2026-11-24, 1,070 the day before. Check on the day.
- MBR0530T1G: Digi-Key lists it active, onsemi's page for the base number shows "Last Shipments". Unresolved. 164,666 at JLCPCB.

#### 22. Home assembly path, if that is the plan

- Stencil 0.10 mm rather than the 0.12 mm default (BMP580 aperture area ratio 0.65 against 0.55); Sensirion asks for 0.125–0.150 mm, so this is a compromise.
- The four USB-C shell legs have no paste and are soldered by hand. Tin-bismuth joints are brittle, which matters most at the USB connector. The SCD41 allows one reflow pass, no flux, no cleaning.
- The paste layer is correct for this path (277 apertures, none on test pads).

### Notes

- **23. Floating inputs until the firmware runs.** `EPD_DC`, `EPD_MOSI` and (after reset) `EPD_SCK` float; harmless, because R20 and R21 hold CS and reset high. `BMP_INT` floats until the BMP580 is configured (its interrupt pin resets to disabled, open-drain) and runs 74 mm beside SDA: keep an internal pull on IO0 and set the pin push-pull. IO2 is open: enable a pull. `EPD_BUSY` floats without a panel: the driver needs a timeout.
- **24. No series resistors on the display lines** (44 to 82 mm) or on USB D+/D−. Espressif's guidelines recommend both; Espressif's own development board leaves the USB ones out. Planned instead: reduced drive strength in firmware. `EPD_MOSI` leaves the module 4 mm from the antenna: check Wi-Fi during a refresh.
- **25. The panel is always powered** (`+3V3` straight to J5 pins 15 and 16) and Good Display forbids plugging it in with power on. Unplug USB first.
- **26. TSCL and TSDA (J5 pins 6, 7) are open**, as in Good Display's reference circuit; the SSD1680 datasheet (rev 1.4) lists them as "VSS" when unused. Either is defensible.
- **27. `+5V` carries 12 µF nominal** (USB asks for 10 µF at most); about 6 µF effective. Keep the sum in view when fixing finding 5.
- **28. No over-voltage protection:** a faulty charger that delivers 9 V or more destroys all three regulators. Compliant sources stay at 5 V.
- **29. Vias beside the ESP32's ground squares** have their holes 0.075 mm from the paste: some solder may run in. Soldering that pad is optional per Espressif. As on 1.0.
- **30. The four M3 screws over-determine the board,** and two are on the sensor island: mount without forcing the board flat (BMP580 stress).
- **31. SHT45 heater** (up to 100 mA) shares the rail with the SCD41: do not fire it during a CO2 measurement.
- **32. The router's own log reports one ground pocket as "not routed"** on the committed board; KiCad counts no open connection, because a patch via ties the pocket afterwards. Consistent with the project's rule to trust KiCad's count.
- **33. No reference designators and no fiducials on the board.** JLCPCB adds fiducials on the rails.
- **34. The feed-forward capacitor position at R3 does not exist;** the buck converter runs in power-save mode almost always (below 0.23 A), so output ripple cannot be tuned without rework.

---

## 3. Coverage

V = verified against the named source in this review; F = failed (finding number); C = could not verify, with the reason. Every V for a pinout or footprint was checked by two independent passes.

### Components

| Ref | Part | Symbol pins | Footprint and pad numbering | Orientation on board | Application circuit | Source |
| --- | --- | --- | --- | --- | --- | --- |
| U4 | ESP32-C6-WROOM-1-N8 | V (29 pins) | V (land pattern fig. 11-1; not mirrored) | V (antenna at the left edge) | V (EN 10 k / 1 µF; 10 µF + 100 nF) | module datasheet v1.4; chip datasheet v1.6; Hardware Design Guidelines; DevKitC-1 schematic v1.4 |
| U1 | USBLC6-2SC6 | V | V | V | V (3.7 mm from J1, before the fuse) | ST Doc ID 11265 rev 5 |
| U2 | TPS62A01DRLR | V | V (mask web 0.15 mm) | V | V; F for the track under L1 (1) | TI SLUSEG9E |
| U3, U9 | TLV75533PDBVR | V | V | V | F for C3/C15 (5); V otherwise | TI SBVS320D |
| L1 | DFE252012F-1R0M | — | V, pads larger than Murata's (20) | — | F (1) | Murata J(E)TE243A-0017D-01 |
| F1 | 1206L075/16WR | — | V | — | V (hold 0.54 A at 60 °C against 0.10 A average) | Littelfuse 1206L series |
| J1 | TYPE-C-31-M-12 | V (CC1/CC2 separate, both D+ and both D− joined) | V with small differences (20) | V (opening at the bottom edge, edge at HRO's 5.79 mm) | V | HRO drawing 2020-12-08; C for the 2018 drawing KiCad cites |
| U5 | SHT45-AD1B-R2 | V | V | V | V | Sensirion SHT4x v7.3 |
| U6 | SCD41-D-R2 | V (unused pads isolated) | F for paste and land size (7); pin order V | V | V (supply link 20 mΩ; 0.38 mm from the vent hole's centre) | Sensirion SCD4x v1.7 |
| U7 | SGP41-D-R4 | V | V | V | V (4.7 Ω + 1 µF on VDD, 1 µF on VDDH: Sensirion's own circuit) | Sensirion SGP41 v1.0 |
| U8 | BMP580 | V | V, not mirrored (bottom view fig. 25 against top view fig. 18); pad size see (19) | V | V (I2C mode, 0x47) | BST-BMP580-DS004-02 rev 1.2 (mirror copy), BMP581 rev 1.13, BST-BMP5xy-HS000-00 |
| D1 | 19-337/R6GHBHC-A01/2T | V | V | V | V; brightness see (18) | Everlight DSE-0002657 rev 4 |
| J2 | SM04B-SRSS-TB | V (1 GND, 2 3V3, 3 SDA, 4 SCL) | V for pad order against SparkFun's footprint; C for JST's own land drawing (the catalogue has none) | V (opening at the top edge, not mirrored) | V | SparkFun Qwiic board files |
| SW1, SW2 | SKRTLAE010 | V (1 and 3 common, 2 other pole) | V (two documented changes for hole clearance) | V (button over the top edge) | F for ESD (9) | Alps SKRT sheet, update 2510 |
| J5 | KH-FPC0.5-H2.0SMT-24P-QCHF | V (24 pins against specification page 8) | V (24 × 0.25 × 1.30 mm at 0.5 mm; holding pads; pin 1 end; dual contact) | V (opening towards the sensors, pad 1 at the bottom) | V (panel pin N on pad N after the fold, derived three times independently) | Kinghelm 8.01A0-C rev L; EasyEDA footprint; panel specification pages 7, 8, 28 |
| Q1 | SI1308EDL-T1-GE3 | V (1 G, 2 S, 3 D) | V | V (drain towards L2) | V (30 V; RDS(on) ≤ 0.185 Ω at 2.5 V) | Vishay 63399 rev C |
| D2–D4 | MBR0530T1G | V (pad 1 cathode) | V | V | V (each direction against the reference circuit) | onsemi MBR0530T1/D rev 9 |
| L2 | SWPA4030S470MT | — | V | — | V (0.95 A saturation, 0.72 A rated, against "500 mA") | Sunlord SWPA series, 2016 |
| R18, R19, C17–C26 | boost passives | — | V | — | V against specification page 29; capacitance under bias see (10) | panel specification; Samsung DC-bias data |
| R20, R21 | pull-ups on CS and reset | — | V | — | V (additions to the reference; harmless on IO15 and IO5) | ESP32-C6 datasheet |
| R1–R17, C1–C16 | other passives | — | V (standard 0402 / 0805) | — | V; C3/C15 see (5) | TI and Samsung data |
| TP1–TP16 | test pads | — | V (back side, mask open, no paste, not in BOM or placement) | — | see (17) | trial Gerbers |
| Panel | GDEY0213B74 | V | — | V (fold direction, pin order, contact side) | fold margin see (4) | specification 2021-03-17; Good Display guidelines |

### Schematic checks

| Check | Result |
| --- | --- |
| ERC (KiCad 10.0.8, all severities) | V: 0 violations |
| Netlist hygiene: single-pin nets, split or shorted labels | V: 60 nets; the only single-pin nets are the 12 intended no-connects |
| Power and ground pins all connected; decoupling on every supply pin | V |
| Unused pins terminated as required | V; TSCL/TSDA see (26) |
| Reset, enable, boot, strapping pins defined at power-up | V (IO8, IO9 high by 10 k; IO15 high by R20; IO4/IO5 only matter for SDIO; `SENS_EN` high, `QWIIC_EN` low) |
| MCU functions available on their pins | V |
| Firmware pin map matches | F (3): `pins.h` is revision 1.0 |
| Regulator input range, dropout, output current, dissipation | V (buck needs 3.42 V in, has 3.85 V at worst; junction rises 16 °C and 11 °C) |
| Capacitor values, DC bias | F (5); (10) |
| Feedback divider | V: 3.320 V nominal |
| Inductor saturation | V for L1 (peak 0.89 A against 4.7 A); L2 rated above the reference's 500 mA; C for the boost's real peak current (not published) |
| Sequencing, back-powering | V: `+3V3_SENS` cannot be up without `+3V3`; at most 66 µA into a switched-off rail |
| Inrush, hot-plug | C (6): calculated only |
| Reverse polarity, overcurrent, ESD | V for fuse and USB protection; reverse polarity not applicable to USB-C; (8), (9), (28) |
| Logic levels and absolute maximum ratings | V: everything is 3.3 V; C for an absolute maximum on ESP32 pins (Espressif gives none) |
| I2C pull-ups and addresses | V: 4 addresses, no clash; about 50 pF, rise time 0.85 × 4.7 kΩ × 50 pF = 0.20 µs (0.28 µs at 70 pF) against 0.3 µs; sink 0.7 mA |
| UART TX/RX | V: TP15 is the ESP32's output, TP16 its input, labels match |
| SPI chip select | V: one device, CS pulled up |
| USB D+/D−, CC resistors | V |
| Crystal load capacitors, ADC inputs | not applicable: none on the board |
| Transistor and diode pinouts, gate default state | V; C for the gate-drive level of the panel's GDR pin (not published) |
| LED currents, resistor power | V: all far below ratings; R19 about 7 mW in a 62.5 mW part (estimate) |
| Connector pin order against the mating part | V for J1, J2, J5 |
| Each subcircuit against the maker's reference | V: buck (TI), regulators (TI), module (Espressif), SGP41 and SCD41 (Sensirion), display (Good Display page 29). Deviations: findings 1, 11, 24, 26 |

### Parts and BOM

| Check | Result |
| --- | --- |
| Full MPN on every line, package suffix matches footprint | V: 36 lines |
| JLCPCB's part for each number is the schematic's MPN | V: 36 of 36 (parts API, 2026-11-24) |
| Value, tolerance, voltage, dielectric | V; (5), (10) |
| Stock | V: all in stock; lowest J5 981, SCD41 411 (21) |
| Lifecycle | V for 21 lines; F for C2 (21); C for BMP580, the USB connector, L2, J5, the UNI-ROYAL resistors (no source states it) and MBR0530T1G (sources conflict) |
| Alternates | C for J5 (candidates not drop-in) |
| BOM, schematic, board agree | V: 85 schematic parts, 69 placed, 16 test pads excluded; 8 board-only footprints (holes, panel models) excluded |

### Layout

| Check | Result |
| --- | --- |
| Board in sync with schematic, nothing unrouted | V: KiCad counts 0 differences, 0 open connections; a from-scratch run reproduces the board |
| DRC with the project's rules | V: 0 errors; 2 warnings (J1 silkscreen over the edge) |
| DRC against JLCPCB's rules, by measurement | V: table below; on the limit see (20); silkscreen F (15) |
| Track and via current capacity | V: worst case 0.6 A in 0.4 mm (1.2 A capacity at 10 °C rise); supply drops 4 to 16 mV |
| High-voltage clearances | V with reservations (13) |
| Decoupling at the pins, return paths | V for U2 (1.5 mm), U4 (3.7 mm), regulators (1.5–1.8 mm), sensors; C2's ground returns over 7 mm of bottom pour (deviation from TI, works) |
| Ground under fast signals | V for USB and the buck converter; F in wording for the boost converter (12) |
| Buck layout against TI's example | V for hot loop, switch node, feedback; F (1) |
| Boost layout | V for the input loop and switch node; (11), (12), (13) |
| Differential pair | V: USB D+ 23.2 mm, D− 23.9 mm; not a 90 Ω pair, irrelevant at 12 Mbit/s over 24 mm |
| Antenna keep-out | V for copper; F against the clearance recommendation (14) |
| ESD parts at the connector | V |
| Thermal | V by distance (regulator U3 33 mm from the SHT45, behind the slot; no pour on the island); C for the temperature under the panel (no case) |
| Assembly spacing | V: smallest pad-to-pad between parts 0.39 mm |
| Fiducials, designators | none on the board (33) |
| Polarity and pin-1 marks, board name and revision | V: present at U1–U9, J5, Q1, D1–D4; "ClimaSense Rev 2.0" and the Up arrow |
| Component heights under the panel | V: 3.3 mm at most (switches), J5 3.1 mm with its lock up, against 4.75 mm |
| Mounting and frame holes | V: no collisions; a `+3V3` track passes 0.30 mm from FH1's edge on the top layer, so no metal washer there |

Measured on the board against JLCPCB's capability pages (read 2026-11-24; 2 layers, 1 oz):

| Rule | JLCPCB | Project rule | Measured |
| --- | --- | --- | --- |
| Track width | 0.10 mm | 0.15 | 0.20 smallest |
| Copper spacing | 0.10 (pad to pad 0.15) | 0.15 | 0.150 smallest |
| Via hole / pad | ≥ 0.15 / 0.25 | 0.3 / 0.5 | all 229: 0.3 / 0.6, ring 0.15 |
| Plated-hole ring | ≥ 0.20 (0.25 recommended) | — | 0.20 (J1 shell slots) |
| Hole to hole | 0.2 (vias), 0.45 (pads) | 0.5 | 0.56 / 0.50 |
| Via hole to track | 0.2 | 0.25 | 0.30 |
| Unplated hole to copper | 0.2 | 0.25; 0.2 at the switches | 0.200, 0.204, 0.25 |
| Milled slot | ≥ 1.0 wide | — | 1.5 |
| Copper to routed edge | ≥ 0.2 (V-cut 0.4) | 0.3 | 0.30 |
| Solder mask bridge | 0.10 (green), 0.13 (black, white) | 0 | 0.15 smallest (U2); 0.25 at J5, U7, U8 |
| Smallest pad | 0.25 × 0.25 | — | 0.25 × 0.275 (U8) |
| Silkscreen | line 0.15, text 1.0 | 0.08 / 0.8 | 0.10–0.12 / 0.8 (finding 15) |
| Part to part | 0.15 (0402), 0.2–0.4 (SOT) | courtyards | 0.39 smallest |

### Manufacturing readiness (on trial exports, kept outside the repository)

| Check | Result |
| --- | --- |
| Outline | V: three closed loops (outer outline with the tongue's cuts, two closed slots), no stray segments |
| Plated and non-plated holes | V: 229 plated 0.3 mm; 4 plated slots (J1); 12 non-plated (2 × 0.65, 4 × 0.9, 2 × 2.2, 4 × 3.2) |
| Layers present, extents | V: 9 Gerbers and 2 drill files; 103 × 34 mm; bottom paste empty, as it should be |
| Drills aligned with pads | V: every hit on a pad or via |
| Mask | V: opening on every pad, none on a via on the front; 11 back test pads stand on a via that is open inside the pad |
| Paste | V: 277 apertures, only on placed parts; none on test pads or shell slots |
| Silkscreen clear of pads | V |
| Placement file: side, origin, rotation | V: 69 parts, all top; every correction in `gen_fab.py` confirmed against JLCPCB's footprints; C for which drawing production uses for Q1, U3, U9 (only an order shows) |
| Fits the order parameters | V; F for the rails remark (2) |

### Debuggability

| Check | Result |
| --- | --- |
| Test pads on rails | V for `+5V`, `+3V3`, `+3V3_SENS`, ground (three); none on VBUS and `+3V3_QWIIC` (17) |
| Key signals | V for SDA, SCL, INT, five display lines, UART; none for `EPD_RST` and the driving voltages (17) |
| Programming and debug | V: USB, UART0 pads, both buttons |
| Isolating a rail, measuring its current | F (17) |
| Rework | possible with the panel swung away |

---

## 4. Open questions and assumptions

**Assumptions made**

- **A1.** Ambient 0 to 40 °C, up to 50 °C inside the case. Not documented.
- **A2.** Fab parameters as for revision 1.0 (2 layers, 1.6 mm, 1 oz, ENIG, Standard PCBA, top side). Not documented for 2.0.
- **A3.** The boost converter's peak current stays below 500 mA, because both the panel's specification and the SSD1680 datasheet ask for a 500 mA inductor. The current-sense threshold on `RESE` and the drive level on `GDR` are not published.
- **A4.** The tail leaves the glass 0.5 mm above the panel's back. Not dimensioned in the drawing.
- **A5.** Murata's notice applies as written to a signal track under solder mask.

**Questions only the owner can answer**

1. Assembled at JLCPCB or at home? It decides whether finding 2 applies and which stencil to order.
2. Is the frame height of 4.75 mm fixed, or may it drop to about 4.3 mm (finding 4)?
3. May parts move for findings 10 and 11 (0805 capacitors, capacitors at the diodes)? Both change the placement in the display area.

**Questions only hardware can answer**

1. Does revision 1.0 enumerate on USB, regulate, and read all four sensors?
2. Peak voltage on `+5V` at hot-plug (TP1).
3. How JLCPCB attaches the rails at the overhanging parts.
4. Which footprint drawing JLCPCB places Q1 by (visible in the placement review of an order).
5. Wi-Fi range with the panel in place; temperature under the panel.
6. The tail's real exit height and stiffener position on a panel in hand.

**Could not be obtained**

- Good Display's adapter-board schematic (their site refused connections); the SSD1680's sense threshold; JST's land pattern for SM04B-SRSS-TB; HRO's 2018 drawing; the USB-IF specification text (figures taken from TI's datasheets quoting it); JLCPCB's actual reflow profile beyond the 240 ± 5 °C recorded in `ordering.md`.

---

## 5. Pre-order checklist

### Before exporting

1. Decide findings 1 and 5 (and 9 to 13 if wanted); regenerate with a full run of `gen_pcb.py` without `--keep`; `check_pcb.py --require-routed` and `audit_pcb.py` must pass. The committed board does pass both today.
2. Update `tools/gen_fab.py` for 2.0 if not yet done (its own notes say the back-side pads and R21 are pending) and add `--check-zones` to its Gerber export; JLCPCB's KiCad guide ticks "check zone fills". Its other settings match the guide; `--no-x2 --no-netlist` is accepted (revision 1.0 was ordered that way).
3. Check stock on the day for C3249999 (J5), C3659294 (SCD41), C3659325 (SGP41), C5366877 (module), C5157937 (buck converter).

### Export settings (JLCPCB's KiCad guide; what `gen_fab.py` does)

```
kicad-cli pcb export gerbers -o fab/gerbers/ -l F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask --check-zones climasense.kicad_pcb
kicad-cli pcb export drill -o fab/gerbers/ --format excellon --drill-origin absolute --excellon-units mm --excellon-zeros-format decimal --excellon-oval-format alternate --excellon-separate-th climasense.kicad_pcb
kicad-cli pcb export pos -o pos.csv --format csv --units mm --side front --smd-only --exclude-dnp climasense.kicad_pcb
kicad-cli sch export bom -o bom.csv --fields "MPN,Reference,Footprint,LCSC" --labels "Comment,Designator,Footprint,LCSC Part #" --group-by LCSC --ref-range-delimiter "" --exclude-dnp climasense.kicad_sch
```

- Protel file extensions and the 4.6 mm format are kicad-cli's defaults. Zip the nine Gerbers and the two drill files.
- Placement columns: Designator, Mid X, Mid Y, Layer, Rotation. Gerbers and placement share KiCad's page origin.
- Expected counts: 229 plated holes of 0.3 mm, 4 plated slots, 12 non-plated holes; 36 BOM lines; 69 placements, all Top.

### Rotation and centre corrections (all confirmed against JLCPCB's footprints; all present in `gen_fab.py`)

| Part | LCSC | Add to KiCad's rotation | JLCPCB's centre, in the footprint's frame (x right, y down) |
| --- | --- | --- | --- |
| U1 SOT-23-6 | C7519 | +270° | — |
| U3, U9 SOT-23-5 | C404027 | +270° (the engineer's value from the revision 1.0 order; JLCPCB's published drawing says +180°) | — |
| Q1 SOT-323 | C469327 | +180° (against the published drawing; may come back changed by 90°) | — |
| J1 USB-C | C165948 | 0 | 0, −1.507 mm |
| J2 Qwiic | C160404 | 0 | 0, −0.062 mm |
| U4 module | C5366877 | 0 | 0, +2.995 mm |
| J5 display connector | C3249999 | 0 | 0, −1.125 mm |
| SW1, SW2 | C110293 | 0 | 0, +0.075 mm |

No correction: D1, D2–D4 (pad 1 is the cathode in both), U2, U5, U6, U7, U8, L1, L2, F1, all resistors and capacitors.

### Order form

- **Board:** 2 layers, 103 × 34 mm, 5 pieces, 1.6 mm, 1 oz, ENIG, via covering **Tented** (not plugged: eleven test pads stand on a via that must stay open on the back), any mask colour, "Confirm production file" yes.
- **Board remark:** "J1 overhangs the bottom edge by 0.5 mm and the buttons SW1/SW2 overhang the top edge by 0.25 mm (board x 25–39 mm). Please attach the edge rails with routed gaps and mouse bites (no V-cut), or cut the rails back at these parts. Copper is 0.3 mm from the board edge. The milled slots inside the board are intentional."
- **Assembly:** Standard, top side, 2 of 5, tooling holes and fiducials by JLCPCB, "Confirm parts placement" yes with "do not confirm automatically", no board cleaning, no conformal coating, no substitutes for sensors, regulators, the module or J5.
- **Assembly remark:** "Do not wash or clean the boards after soldering: humidity and gas sensors on board. Do not open the lid of FPC connector J5."
- Expect the hold for the SCD41's reflow temperature again (`ordering.md`).
- **Home assembly instead:** bare ENIG boards, no rails, no remark; stencil top side only, 0.10 mm, electropolished.

### In the Gerber viewer, before paying

- Outline 103 × 34 mm with two closed slots and the cut round the SHT45 tongue.
- Exactly 16 round pads open on the back, plus holes; no via exposed on the front; no paste on test pads.
- The four J1 shell slots plated; pegs, switch bosses, 2.2 mm and 3.2 mm holes not plated.

### In the placement preview, and again under "Confirm Parts Placement"

- 69 parts, none unticked, none with quantity 0 (the SHT45 came up unticked on revision 1.0).
- U4: antenna at the left end. J1: opening at the bottom edge. J2: opening at the top edge.
- J5: opening towards the sensors, pin 1 at the triangle at the lower end of the pad row.
- SW1, SW2: buttons over the top edge.
- Pin-1 dots of U1, U2, U3, U9, U5, U6, U7, U8 and D1 at the triangles. U2 turned by 180° swaps ground and input.
- Q1: the single pin (drain) towards L2. D2–D4: cathode at the bar.
- No test pads, holes or panel in the list.
- Under "Show Revised Items": a 90° change of Q1, U3 or U9 that leaves the pin-1 dot on the triangle is JLCPCB's other drawing of the same part; anything else is an error.
- In the production file: rails clear of J1, SW1 and SW2.

---

## 6. Verdict

**Conditional go.**

What speaks for go: every pinout, every footprint's pad numbering and every polarised part's orientation was checked against the manufacturer's datasheet by two independent passes and found right, including the three things a mistake would have been fatal for on this revision: the display connector's pin order through the fold, the side of the tail that carries the contacts, and the connector's pin-1 end. The display circuit matches the panel maker's reference net by net. ERC and DRC are clean, the board measures inside JLCPCB's current rules, the trial manufacturing files are complete and consistent, all parts are in stock, and both generators reproduce the committed files.

Conditions for go:

1. **Finding 1:** move `QWIIC_EN` out from under L1, or add the capacitor and the smaller pull-down. Then a full regeneration and both checks.
2. **Finding 2:** if JLCPCB assembles the boards, the new remark goes on the order and the rails are checked in the production file.
3. **Finding 3:** a revision 1.0 board has been powered and shows USB, both supplies and the four sensors working; `+5V` at hot-plug measured (finding 6). And no revision 1.0 firmware on a 2.0 board.
4. **Finding 5:** C3 and C15 changed to the 0603 part. A value change in the same re-route as condition 1.
5. **Finding 4:** the frame height decided before a frame is printed. This does not hold up the board.

Recommended in the same re-route, not conditions: back-side pads for the driving voltages and `EPD_RST` (17), the switch pad roles (9), the SCD41 footprint (7), silkscreen sizes (15), and the documents brought in line with the board (16).

Not covered by any of this: whether the antenna still reaches with the panel in front of it, how warm the panel gets above the module, and whether the case can be built round the fold. Those need the first board.

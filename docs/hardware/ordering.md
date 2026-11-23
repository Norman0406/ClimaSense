# Ordering revision 1.0 at JLCPCB

The three files JLCPCB asks for are written by one script:

```
python hardware/rev-1.0/tools/gen_fab.py
```

It runs the board check first and writes nothing if the board does not pass. Output, in `hardware/rev-1.0/fab/`:

| File | What it is | Where it goes on the order page |
| --- | --- | --- |
| `climasense-1.0-gerbers.zip` | The board itself: copper, solder mask, paste, silkscreen, outline, drill files | "Add gerber file", the first upload |
| `climasense-1.0-bom.csv` | Parts list: one line per part type with JLCPCB's part number | PCB Assembly → "Add BOM File" |
| `climasense-1.0-cpl.csv` | Placement: position and rotation of every part | PCB Assembly → "Add CPL File" |

`hardware/rev-1.0/fab/gerbers/` holds the same files as the zip, unpacked. They are kept in the repository as the record of what was ordered; KiCad writes them in a different order on every run, so a diff of them says little.

Stock changes daily. Check the parts list on the order page: every one of the 28 lines must be ticked and have a quantity. On 2026-11-20 the SHT45 line came up unticked with quantity 0; ticking it by hand was enough, and it was then priced like the others. If JLCPCB reports a part as short, do not let it pick a substitute for a sensor, a regulator or the module; ask first.

## Board options

Leave everything at its default except:

- **Layers 2, size 75 × 34 mm, thickness 1.6 mm** — read from the files; just confirm.
- **Surface finish: ENIG** rather than the default HASL. The BMP580 and SHT45 have pads a quarter of a millimetre wide with no leads; the flat gold finish solders them more reliably than the slightly domed tin of HASL. This costs extra; lead-free HASL usually works too, with a higher risk on those two parts.
- **Quantity 5** (the minimum for boards). Assembly is ordered for **2 of the 5** in the first run (decided 2026-11-20): a design fault would be on every board, so more assembled boards add cost at risk and no information. The other three stay bare.
- **PCB remark:** "USB-C connector J1 overhangs the bottom board edge by 0.45 mm. Please make sure the added edge rails do not interfere with it. The milled slots inside the board are intentional." JLCPCB adds edge rails for the assembly (see below), and the connector sticks out over the edge they attach to.

## Assembly options

- Assembly side: **top**. Everything is on the top.
- PCBA type: **Standard**. The page starts with Economic; the SCD41, SGP41 and BMP580 are marked "Standard Only" in the parts list, and the link there switches the order over. Standard costs a 25 USD setup fee, and JLCPCB adds edge rails that bring the panel to 75 × 70 mm.
- PCBA quantity: **2**.
- Tooling holes: added by JLCPCB.
- **Confirm parts placement: yes**, with **"Do not confirm automatically"** ticked in the dialog that follows. An engineer then checks the placement before production; without the tick the order goes into production by itself after 72 hours.
- Remark for the assembly: **"Do not wash or clean the boards after soldering: humidity and gas sensors on board."** Sensirion's handling instructions forbid cleaning agents on the SHT45, SGP41 and SCD41.
- **Board cleaning: no. Conformal coating: no.** Both are offered as extras on the order page; either would ruin the sensors.

The SCD41 can read slightly off after soldering; its datasheet says full accuracy is back after at most five days, whether it is powered or not. Do not judge the CO2 readings on the day the boards arrive.

### The SCD41 and the reflow temperature

After its review JLCPCB puts the assembly on hold and asks what to do with the SCD41 (C3659294): it calls the part "not fully resistant" to its standard reflow profile, which peaks at 240 ± 5 °C. It offers three ways out: medium-temperature solder paste (about 210 °C peak, 32.12 USD per order, mechanically weaker joints), another part, or leaving the part off. Loose parts are not shipped along.

Sensirion's SCD4x datasheet (version 1.7, April 2025, section 4.5) allows a peak of 245 °C for up to 30 seconds, so the standard profile is inside the limit, but at its edge, and the datasheet warns that the sensor's cap can get hotter than its pads. The limit was 235 °C in older datasheet versions.

**First order (decided 2026-11-22):** soldered with the standard paste and profile at our own risk, with no claim on the part. JLCPCB confirmed this. The reply also asked for the peak at the lower end of their range and repeated that the boards must not be washed.

What follows from it:

- **When the boards arrive,** wait the five days above, then compare the CO2 readings of the two boards with each other and with outdoor air (about 420 ppm). Two sensors that agree and read outdoor air correctly came through the oven unharmed.
- **Later orders:** expect the same hold. The paste fee is per order, not per board (about 6.40 USD a board at five), so the medium-temperature paste is the easy choice there unless the first two sensors show that the standard profile does no harm.
- Do not solder or rework the SCD41 by hand: the datasheet allows one reflow pass and no added flux.

## The placement preview: check this before paying

After the BOM and placement files are read, the page draws every part on the board. This is the one place where a mistake in rotation is visible before it is soldered. A part turned by 180° usually destroys it or the board.

The silkscreen marks pin 1 of every chip with a small triangle or a missing corner. In the preview, the pin-1 dot of each part must sit at that mark. Go through all of these:

| Part | What to look for |
| --- | --- |
| U4, ESP32 module | Antenna (the end without pads) at the **left** end of the board, pads on the footprint's pads on all three sides |
| J1, USB-C | Opening at the **bottom** edge, the row of small pads towards the inside of the board |
| J2, Qwiic | Opening at the **top** edge |
| U1, ESD protection (6 pins) | Pin-1 dot at the silkscreen mark |
| U2, buck converter (6 pins, tiny) | Pin-1 dot at the silkscreen mark |
| U3 and U9, regulators (5 pins) | The side with three pins on the three pads, pin-1 dot at the mark |
| U5 SHT45, U7 SGP41, U8 BMP580 | Pin-1 dot at the silkscreen mark. A wrong turn here swaps supply and bus pins |
| U6, SCD41 | Pin-1 corner at the silkscreen mark (the part is square, so it fits in four ways) |
| D1, LED | Pin-1 mark at the silkscreen mark |
| L1, F1, capacitors, resistors, buttons | Sitting on their pads; direction does not matter |
| J3, J4, TP1–TP4 | **Empty.** The two rows of holes (top left, bottom right) and the four round pads are not populated and must not appear in the parts list |

The rotation and centre of J1, J2, U1, U3, U4 and U9 are corrected in the placement file, because JLCPCB draws those parts differently from KiCad (table `CORRECTIONS` in `gen_fab.py`, measured against JLCPCB's own footprints). The preview is the confirmation that the corrections are right; if one of these six looks turned or shifted, fix the table rather than the order page, and tell JLCPCB's engineer in the remark what you saw.

If anything looks wrong and you cannot tell why, stop there. Nothing is charged until the order is placed.

## After the review: confirming the placement

After its review JLCPCB places the parts again itself and asks for the result to be confirmed: order history → "Confirm Parts Placement". The page shows the parts as the engineer placed them, with a magenta dot on pin 1 of each; "Show Revised Items" under the picture lists the parts whose rotation the engineer changed. Go through the table above once more there. On 2026-11-23 the order page showed a countdown ("please confirm parts placement within 2d19h, or your order will be produced directly"), so do not count on the order waiting.

**First order (checked 2026-11-23):** 49 parts placed, none left out; J3, J4 and the test pads are not in the list. The engineer changed two things, and both are right:

- **U3 and U9 (regulators): rotation 270° → 0°.** The parts are not turned on the board. JLCPCB has two drawings of this part (C404027): the EasyEDA data of the part number has pins 1-2-3 up the right side ("…-BR"), the data the part is placed by has them along the bottom ("…-BL"), a quarter turn apart. `CORRECTIONS` was measured against the first. In the second, 0° is exactly how U3 and U9 sit on the board, pin 1 at the bottom left.
- **J1 (USB-C): moved 0.064 mm** towards the board edge.

The other 46 parts were left exactly as in the placement file. This was checked in the picture and in the numbers: the page loads the engineer's position and rotation of every part, and JLCPCB's footprints laid over the board's pads at those values match pin for pin.

Another order of revision 1.0 from the same files will come back with the same two changes; that is expected. Revision 2.0's `gen_fab.py` has both values taken over (SOT-23-5: 270 instead of 180; USB-C centre −1.507 instead of −1.571 mm), so its placement should come back unchanged.

## Cost and import (Switzerland)

**Ordered on 2026-11-20** with the settings on this page: 187.64 USD paid, which is the quote below plus shipping, less a 30 USD coupon. The order then waits for JLCPCB's file review and for the placement drawing to be approved in the order history.

Quote of 2026-11-20 for 5 boards with ENIG, 2 of them assembled: boards 21.20 USD (17.20 of it the ENIG finish), assembly 173.04 USD (parts 86.42, feeder loading 43.40, setup 25.75, stencil 8.27, X-ray 6.60, the rest small), together 194.24 USD; DHL Express about 23.40 USD on top, before any coupon, Swiss VAT (8.1 %) and the carrier's clearance fee. JLCPCB may add a charge after its review for the assembly remark and for the four sensors, which it marks as difficult to process. The customs description chosen on the order page is "Temperature Sensor" (HS code 902590).

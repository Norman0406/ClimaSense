# Ordering revision 1.0 at JLCPCB

The three files JLCPCB asks for are written by one script:

```
python hardware/tools/gen_fab.py
```

It runs the board check first and writes nothing if the board does not pass. Output, in `hardware/fab/`:

| File | What it is | Where it goes on the order page |
| --- | --- | --- |
| `climasense-1.0-gerbers.zip` | The board itself: copper, solder mask, paste, silkscreen, outline, drill files | "Add gerber file", the first upload |
| `climasense-1.0-bom.csv` | Parts list: one line per part type with JLCPCB's part number | PCB Assembly → "Add BOM File" |
| `climasense-1.0-cpl.csv` | Placement: position and rotation of every part | PCB Assembly → "Add CPL File" |

`hardware/fab/gerbers/` holds the same files as the zip, unpacked. They are kept in the repository as the record of what was ordered; KiCad writes them in a different order on every run, so a diff of them says little.

Stock changes daily. Check the parts list on the order page: if JLCPCB reports a part as short, do not let it pick a substitute for a sensor, a regulator or the module; ask first.

## Board options

Leave everything at its default except:

- **Layers 2, size 75 × 34 mm, thickness 1.6 mm** — read from the files; just confirm.
- **Surface finish: ENIG** rather than the default HASL. The BMP580 and SHT45 have pads a quarter of a millimetre wide with no leads; the flat gold finish solders them more reliably than the slightly domed tin of HASL. This costs extra; lead-free HASL usually works too, with a higher risk on those two parts.
- **Quantity 5** (the minimum for boards). Assembly can be ordered for 2 of the 5.

## Assembly options

- Assembly side: **top**. Everything is on the top.
- Tooling holes: added by JLCPCB.
- **Confirm parts placement: yes.** An engineer then checks the placement before production, and you get the preview described below.
- Remark for the assembly: **"Do not wash or clean the boards after soldering: humidity and gas sensors on board."** Sensirion's handling instructions forbid cleaning agents on the SHT45, SGP41 and SCD41.
- **Board cleaning: no. Conformal coating: no.** Both are offered as extras on the order page; either would ruin the sensors.

The SCD41 can read slightly off after soldering; its datasheet says full accuracy is back after at most five days, whether it is powered or not. Do not judge the CO2 readings on the day the boards arrive.

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

## Cost and import (Switzerland)

Estimate of 2026-11-19, to be replaced by the order page's own figures: about 41 USD of parts per assembled board; the smallest order (5 boards, 2 of them assembled) roughly 145–225 USD before Swiss VAT (8.1 %) and the carrier's clearance fee. The sensors are most of the cost, so assembling 2 instead of 5 saves the most.

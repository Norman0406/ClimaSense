# Project footprints

Four parts have no footprint in KiCad's standard library. They live in [`hardware/lib/climasense.pretty`](../../hardware/lib/climasense.pretty) and are produced by [`hardware/tools/gen_footprints.py`](../../hardware/tools/gen_footprints.py), where every dimension sits next to the name of the datasheet drawing it came from.

Status: **drawn from the manufacturers' land-pattern drawings and checked against the schematic, but not yet proven on a real board.**

## The footprints

| Footprint | Part | Source drawing | Key dimensions |
| --- | --- | --- | --- |
| `ESP32-C6-WROOM-1` | U4 | Espressif module datasheet v1.4, figure 11-1 | 18 × 25.5 mm; 2 × 14 pads of 1.5 × 0.9 mm on 1.27 mm pitch, columns 17.5 mm apart; pad 1 is 7.49 mm below the top edge; 3.3 mm ground pad |
| `Sensirion_DFN-6-1EP_2.44x2.44mm_P0.8mm_EP1.25x1.7mm` | U7 (SGP41) | Sensirion SGP41 datasheet v1.0, figure 18 | 6 pads of 0.55 × 0.4 mm on 0.8 mm pitch, pad centres 2.3 mm apart; centre pad 1.25 × 1.7 mm with a 1.05 × 1.5 mm stencil opening |
| `Bosch_LGA-10_2x2mm_P0.5mm_BMP580` | U8 | Bosch BST-BMP580-DS004-02, figure 25 | 10 pads of 0.25 × 0.275 mm on 0.5 mm pitch, rows 1.525 mm apart |
| `LED_RGB_Everlight_19-337_1.6x1.6mm` | D1 | Everlight 19-337/R6GHBHC-A01/2T, page 9 | corner pads 0.55 × 0.4 mm, middle pads 0.7 × 0.5 mm |

## Notes per footprint

**ESP32-C6-WROOM-1**

- The pad positions come out identical to KiCad's own footprint for the sibling ESP32-S3-WROOM-1 (same outline, same pad size and pitch, same first-pad position). That is an independent confirmation of the reading of the drawing.
- The antenna end (top 6 mm) carries a keep-out area on all copper layers: no tracks, vias or copper fill underneath. For best range the antenna should also sit at or beyond the board edge.
- The ground pad is drawn exactly as figure 11-1 and Espressif's own KiCad footprint show it: nine copper squares of 0.8 mm with 0.45 mm gaps, each with its own solder mask opening and paste. The figure's twelve thermal vias are placed by the board generator in the middle of every gap between two neighbouring squares; their copper rings overlap the squares and join them. The vias are the board's normal ones (0.3 mm hole), the smallest JLCPCB makes on a two-layer board at the standard price; their holes end 0.075 mm from the squares, so some solder may run into them. Espressif notes that soldering this pad is not required and only helps heat removal. Until 2026-11-19 this was one solid 3.3 mm pad, bare all over, with four vias.
- The 3D model is the ESP32-S3-WROOM-1 model as a visual stand-in. The outline is the same; details of the shield can differ.

**SGP41**

- The centre pad has its pin-1 chamfer at the top left, matching the datasheet.
- Sensirion asks for non-solder-mask-defined pads and a 125–150 µm stencil.

**BMP580**

- Bosch dimensions the pads in a bottom view (figure 25) and recommends using the package pads themselves as the landing pattern. The footprint follows that exactly, mirrored into the top view; the datasheet's own top views (figures 18 and 24) agree with it. Pin numbers run counter-clockwise from the top-left corner: 1–2 down the left, 3–5 along the bottom, 6–7 up the right, 8–10 along the top.
- The area inside the ring of pads is a keep-out on both copper layers: Bosch's mounting instruction (BST-BMP5xy-HS000-00, section 3.2) advises against tracks or vias under the sensor. The four supply-side pads are therefore joined outside the package.
- These are the smallest pads on the board (0.25 × 0.275 mm). They are within JLCPCB's capability but leave the least margin.

**RGB LED**

- Pins 1, 2, 3 (left side) are the cathodes for blue, red and green; pins 4, 5, 6 the matching anodes.

## What was checked

- KiCad loads and re-saves all four files without complaint.
- Each footprint was rendered and compared by eye with its datasheet drawing (pad positions and numbering).
- `check_schematic.py` confirms that all 43 parts have a footprint and that every symbol pin has a pad with the same number. The only pads without a pin are the SCD41's "do not connect" pads, which must stay unconnected.

## Correction (2026-11-19)

The first version of the SGP41 footprint was wrong: the 2.3 mm in Sensirion's drawing is the distance between pad centres, and it had been read as the outer width, which left the side pads touching the centre pad. KiCad's design rule check on the board caught it; the comparison by eye above had not. It is fixed, the generator now asserts the gap, and the other three footprints were re-read for the same kind of mistake (the LED and BMP580 dimensions are confirmed by a second dimension in their drawings, the ESP32 by KiCad's sibling footprint).

## What was not checked

- Nothing has been compared against a physical part. Before ordering, a 1:1 print of the board with the parts laid on it is not possible here (no parts in hand), so the fab's own design-for-manufacturing review and assembling only a couple of boards first are the practical safeguards.
- The inductor L1 still uses KiCad's generic 2520 footprint rather than Murata's recommended pattern for the DFE252012F.

## Regenerating

```bash
python hardware/tools/gen_footprints.py
```

Rewrites the four files. Once the PCB layout uses them, change dimensions here and re-run rather than editing the files by hand, so the datasheet references stay next to the numbers.

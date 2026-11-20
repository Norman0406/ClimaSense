# Hardware

KiCad 10 project for the ClimaSense PCB. The board is intended to be fully manufactured and assembled by a PCBA service (JLCPCB).

| File | What |
| --- | --- |
| `climasense.kicad_pro` | KiCad project — open this |
| `climasense.kicad_sch` | Schematic, revision 1.0 |
| `climasense.kicad_pcb` | Board, revision 1.0: placed and routed by script, not yet reviewed by a person (see [`../docs/hardware/layout.md`](../docs/hardware/layout.md)) |
| `lib/climasense.kicad_sym` | Project symbols: ESP32-C6-WROOM-1, SGP41, BMP580, RGB LED, sensor-rail power symbol |
| `lib/climasense.pretty/` | Project footprints for the same four parts (see [`../docs/hardware/footprints.md`](../docs/hardware/footprints.md)) |
| `lib/climasense.3dshapes/` | Simple 3D models for the parts KiCad has none for, written by `tools/gen_models.py` |
| `sym-lib-table`, `fp-lib-table` | Tell KiCad where the project libraries are |
| `tools/` | Scripts that generate and verify the schematic, the footprints and the board |
| `build/` | Generated outputs (plots, renders, netlist, rule-check reports); not committed |

Status: the schematic passes KiCad's electrical rules check, every part has a footprint, and the board is placed and fully routed and passes KiCad's design rule check. A measurement of the routing found four weaknesses, which have been fixed; see [`../docs/hardware/layout.md`](../docs/hardware/layout.md). Nothing has been reviewed by a person or manufactured yet. Design notes, pin map and bill of materials are in [`../docs/hardware/schematic.md`](../docs/hardware/schematic.md).

## Verify the schematic

```bash
python hardware/tools/check_schematic.py
```

Runs KiCad's rule check, compares KiCad's netlist with the intended one, checks that every symbol pin has a matching footprint pad, and plots `build/climasense.pdf`.

## Verify the board

```bash
python hardware/tools/check_pcb.py --require-routed
```

Runs KiCad's design rule check, compares the board with the schematic, fails on any open connection, and renders `build/pcb_3d_top.png`.

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" hardware/tools/audit_pcb.py
```

Measures what the rule check does not: track lengths against the shortest possible connection, track widths, supply-path resistance and parallel runs. Writes `build/audit.txt`. Fails if a net crosses itself or has a loop in it.

## Order files

```bash
python hardware/tools/gen_fab.py
```

Runs the board check, then writes the Gerber archive, the parts list and the placement file for JLCPCB into `fab/`. How to order with them, and what to check in JLCPCB's placement preview: [`../docs/hardware/ordering.md`](../docs/hardware/ordering.md).

## Pictures

```bash
python hardware/tools/gen_images.py
```

Writes the 3D views and copper plots shown in the README and the layout notes into `../docs/images/`. Run it by hand after the board has changed. It first runs `gen_models.py`, which writes the 3D models in `lib/climasense.3dshapes/`.

## Regenerating

```bash
python hardware/tools/gen_schematic.py
```

This **overwrites** `climasense.kicad_sch`. It is only meant for the period before the schematic is edited by hand in KiCad; after that, the `.kicad_sch` file is the source of truth.

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" hardware/tools/gen_pcb.py
```

This **overwrites** `climasense.kicad_pcb`: it places the parts, routes the board and fills the ground pours. It needs KiCad's own Python and takes about a minute. Do not run it once the board has been edited by hand in KiCad.

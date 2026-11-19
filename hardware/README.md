# Hardware

KiCad 10 project for the ClimaSense PCB. The board is intended to be fully manufactured and assembled by a PCBA service (JLCPCB).

| File | What |
| --- | --- |
| `climasense.kicad_pro` | KiCad project — open this |
| `climasense.kicad_sch` | Schematic, revision A (first draft) |
| `lib/climasense.kicad_sym` | Project symbols: ESP32-C6-WROOM-1, SGP41, BMP580, RGB LED, sensor-rail power symbol |
| `lib/climasense.pretty/` | Project footprints for the same four parts (see [`../docs/hardware/footprints.md`](../docs/hardware/footprints.md)) |
| `sym-lib-table`, `fp-lib-table` | Tell KiCad where the project libraries are |
| `tools/` | Scripts that generated and verify the schematic and footprints |
| `build/` | Generated outputs (PDF plot, netlist, rule-check report); not committed |

Status: schematic drafted and passing KiCad's electrical rules check, every part has a footprint; PCB layout not started. Design notes, pin map and bill of materials are in [`../docs/hardware/schematic.md`](../docs/hardware/schematic.md).

## Verify the schematic

```bash
python hardware/tools/check_schematic.py
```

Runs KiCad's rule check, compares KiCad's netlist with the intended one, checks that every symbol pin has a matching footprint pad, and plots `build/climasense.pdf`.

## Regenerating

```bash
python hardware/tools/gen_schematic.py
```

This **overwrites** `climasense.kicad_sch`. It is only meant for the period before the schematic is edited by hand in KiCad; after that, the `.kicad_sch` file is the source of truth.

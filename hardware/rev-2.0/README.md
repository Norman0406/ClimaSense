# Hardware — revision 2.0 (in progress)

KiCad 10 project for ClimaSense revision 2.0: revision 1.0 plus a 2.13" e-paper display (Good Display GDEY0213B74) on the back of the board. Concept, pin map and parts: [`../../docs/hardware/rev-2.0.md`](../../docs/hardware/rev-2.0.md). Revision 1.0, as ordered on 2026-11-20, is in [`../rev-1.0`](../rev-1.0) and is not changed.

Status (2026-11-22): this folder started as a copy of revision 1.0. `tools/gen_schematic.py` draws the 2.0 schematic; **`climasense.kicad_sch` and `climasense.kicad_pcb` here are still the 1.0 files until the generators have been run** with KiCad. The board generator (`tools/gen_pcb.py`) has not been adapted yet.

The files and the scripts work as in revision 1.0 (see [`../rev-1.0/README.md`](../rev-1.0/README.md)); run them from the repository root with `hardware/rev-2.0/tools/...`. Outputs go to `build/` and `fab/` in this folder; `fab/` files are named `climasense-2.0-…`, and `tools/gen_images.py` writes to `docs/images/rev-2.0/`.

# Hardware — revision 2.0 (designed, not ordered)

KiCad 10 project for ClimaSense revision 2.0: revision 1.0 plus a 2.13" e-paper display (Good Display GDEY0213B74) that lies above the components on a printed frame, its tail folded back under it into the connector J5. What the board is, its pin map, parts and open points: [`../../docs/hardware/rev-2.0.md`](../../docs/hardware/rev-2.0.md). The design review and what has been done about its findings: [`../../REVIEW.md`](../../REVIEW.md). Revision 1.0, as ordered on 2026-11-20, is in [`../rev-1.0`](../rev-1.0) and is not changed.

`climasense.kicad_sch` and `climasense.kicad_pcb` are written by `tools/gen_schematic.py` and `tools/gen_pcb.py` and have not been edited by hand in KiCad: both generators reproduce the files here. Nothing has been ordered; `fab/` is written only when the order files are needed (`tools/gen_fab.py`, steps in [`../../docs/hardware/ordering.md`](../../docs/hardware/ordering.md#revision-20)).

The files and the scripts work as in revision 1.0 (see [`../rev-1.0/README.md`](../rev-1.0/README.md)); run them from the repository root with `hardware/rev-2.0/tools/...`. Outputs go to `build/` and `fab/` in this folder; `fab/` files are named `climasense-2.0-…`, and `tools/gen_images.py` writes to `docs/images/rev-2.0/`.

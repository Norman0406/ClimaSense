# Hardware — revision 2.0 (in progress)

KiCad 10 project for ClimaSense revision 2.0: revision 1.0 plus a 2.13" e-paper display (Good Display GDEY0213B74) on the back of the board. Concept, pin map and parts: [`../../docs/hardware/rev-2.0.md`](../../docs/hardware/rev-2.0.md). Revision 1.0, as ordered on 2026-11-20, is in [`../rev-1.0`](../rev-1.0) and is not changed.

Status (2026-11-23): `climasense.kicad_sch` and `climasense.kicad_pcb` are the revision 2.0 schematic and board, written by `tools/gen_schematic.py` and `tools/gen_pcb.py` and not edited by hand in KiCad: both generators reproduce the files here exactly. The board is fully routed and passes KiCad's rule check, the comparison with the schematic and `tools/audit_pcb.py`. Nothing has been ordered; `fab/` is written only when the order files are needed (`tools/gen_fab.py`). What was checked before ordering and what still needs the real panel: "Check before ordering" in [`../../docs/hardware/rev-2.0.md`](../../docs/hardware/rev-2.0.md).

The files and the scripts work as in revision 1.0 (see [`../rev-1.0/README.md`](../rev-1.0/README.md)); run them from the repository root with `hardware/rev-2.0/tools/...`. Outputs go to `build/` and `fab/` in this folder; `fab/` files are named `climasense-2.0-…`, and `tools/gen_images.py` writes to `docs/images/rev-2.0/`.

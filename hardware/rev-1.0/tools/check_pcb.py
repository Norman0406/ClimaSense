#!/usr/bin/env python3
"""Check the ClimaSense board with KiCad's own tools.

1. Runs KiCad's design rule check (DRC), including the comparison of the board
   against the schematic, and fails on any error or mismatch.
2. Reports how many connections are still unrouted. That only counts as a
   failure with --require-routed.
3. Renders the board to build/pcb_3d_top.png and build/pcb_top.svg.

Usage:  python hardware/rev-1.0/tools/check_pcb.py [--require-routed]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

HW = Path(__file__).resolve().parent.parent
PCB = HW / "climasense.kicad_pcb"
BUILD = HW / "build"
KICAD_CLI = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

# Expected and harmless: the USB connector overhangs the board edge on purpose.
ACCEPTED = {("silk_edge_clearance", "J1")}


def cli(*args):
    subprocess.run([KICAD_CLI, *args], check=True, capture_output=True, cwd=HW)


def main() -> int:
    require_routed = "--require-routed" in sys.argv[1:]
    BUILD.mkdir(exist_ok=True)
    cli("pcb", "drc", "--format", "json", "--schematic-parity", "--severity-all",
        "-o", str(BUILD / "drc.json"), str(PCB))
    drc = json.loads((BUILD / "drc.json").read_text(encoding="utf-8"))

    failed = False
    violations = []
    for v in drc.get("violations", []):
        items = "; ".join(i.get("description", "") for i in v.get("items", []))
        if any(v["type"] == kind and ref in items for kind, ref in ACCEPTED):
            continue
        violations.append((v, items))
    counts = Counter((v["severity"], v["type"]) for v, _ in violations)
    print(f"DRC: {len(violations)} violation(s)" + (f" {dict(counts)}" if counts else ""))
    for v, items in violations[:40]:
        failed = failed or v["severity"] == "error"
        print(f"  [{v['severity']}] {v['type']}: {v['description']} ({items[:160]})")

    parity = drc.get("schematic_parity", [])
    print(f"Board vs schematic: {len(parity)} difference(s)")
    for v in parity[:40]:
        failed = True
        items = "; ".join(i.get("description", "") for i in v.get("items", []))
        print(f"  {v['type']}: {v['description']} ({items[:160]})")

    unrouted = len(drc.get("unconnected_items", []))
    print(f"Unrouted connections: {unrouted}" + ("" if unrouted == 0 else " (board is not fully routed)"))
    if unrouted and require_routed:
        failed = True

    cli("pcb", "render", "--side", "top", "--width", "2300", "--height", "1100", "--zoom", "2.05", "--background", "opaque",
        "-o", str(BUILD / "pcb_3d_top.png"), str(PCB))
    cli("pcb", "export", "svg", "--mode-single", "--fit-page-to-board", "--exclude-drawing-sheet",
        "--layers", "F.Cu,B.Cu,F.SilkS,F.Fab,F.CrtYd,Cmts.User,Edge.Cuts",
        "-o", str(BUILD / "pcb_top.svg"), str(PCB))
    print(f"Renders: {BUILD / 'pcb_3d_top.png'}, {BUILD / 'pcb_top.svg'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

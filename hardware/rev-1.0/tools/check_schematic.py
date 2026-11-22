#!/usr/bin/env python3
"""Verify the ClimaSense schematic with KiCad's own tools.

1. Runs KiCad's electrical rules check (ERC) and fails on any violation.
2. Exports KiCad's netlist and compares it, pin by pin, with the netlist the
   generator intended (build/expected_netlist.json).
3. Checks that every part has a footprint and that every symbol pin has a pad
   with the same number in that footprint.
4. Plots the schematic to build/climasense.pdf.

Usage:  python hardware/rev-1.0/tools/check_schematic.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kisch import find, first, parse  # noqa: E402

HW = Path(__file__).resolve().parent.parent
SCH = HW / "climasense.kicad_sch"
BUILD = HW / "build"
KICAD_CLI = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


KICAD_FOOTPRINT_DIR = Path(os.environ.get("KICAD_FOOTPRINT_DIR", r"C:\Program Files\KiCad\10.0\share\kicad\footprints"))
PROJECT_FOOTPRINTS = {"climasense": HW / "lib" / "climasense.pretty"}


def cli(*args):
    subprocess.run([KICAD_CLI, *args], check=True, capture_output=True, cwd=HW)


def footprint_pads(lib_id: str) -> set[str] | None:
    """Pad numbers of a footprint given as "Library:Name"; None if the file is missing."""
    lib, name = lib_id.split(":", 1)
    folder = PROJECT_FOOTPRINTS.get(lib, KICAD_FOOTPRINT_DIR / f"{lib}.pretty")
    path = folder / f"{name}.kicad_mod"
    if not path.exists():
        return None
    return {p[1] for p in find(parse(path.read_text(encoding="utf-8")), "pad") if p[1]}


def check_footprints(net) -> bool:
    """Return True if a part lacks a footprint or a symbol pin lacks a pad."""
    pins = {}
    for part in find(first(net, "libparts"), "libpart"):
        pin_list = first(part, "pins")
        pins[(first(part, "lib")[1], first(part, "part")[1])] = \
            {first(p, "num")[1] for p in find(pin_list, "pin")} if pin_list else set()
    failed, checked = False, 0
    for comp in find(first(net, "components"), "comp"):
        ref = first(comp, "ref")[1]
        fp = first(comp, "footprint")
        src = first(comp, "libsource")
        symbol_pins = pins.get((first(src, "lib")[1], first(src, "part")[1]), set())
        if fp is None or not fp[1]:
            failed = True
            print(f"  {ref}: no footprint assigned")
            continue
        pads = footprint_pads(fp[1])
        if pads is None:
            failed = True
            print(f"  {ref}: footprint {fp[1]} not found")
            continue
        checked += 1
        missing = sorted(symbol_pins - pads)
        if missing:
            failed = True
            print(f"  {ref}: symbol pins without a pad in {fp[1]}: {missing}")
        extra = sorted(pads - symbol_pins)
        if extra:
            print(f"  note: {ref} has pads without a symbol pin (they stay unconnected): {extra}")
    print(f"Footprints: {checked} parts checked - "
          f"{'PROBLEMS FOUND' if failed else 'every part has a footprint and every pin a pad'}")
    return failed


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    failed = False

    cli("sch", "erc", "--format", "json", "--severity-all", "-o", str(BUILD / "erc.json"), str(SCH))
    erc = json.loads((BUILD / "erc.json").read_text(encoding="utf-8"))
    violations = [v for s in erc.get("sheets", []) for v in s.get("violations", [])]
    print(f"ERC: {len(violations)} violation(s)")
    for v in violations:
        failed = True
        items = "; ".join(i.get("description", "") for i in v.get("items", []))
        print(f"  [{v['severity']}] {v['type']}: {v['description']} ({items})")

    cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(BUILD / "netlist.net"), str(SCH))
    net = parse((BUILD / "netlist.net").read_text(encoding="utf-8"))
    got = {}
    for n in find(first(net, "nets"), "net"):
        name = first(n, "name")[1]
        if name.startswith("unconnected-"):
            continue  # pins deliberately marked no-connect
        got[name] = frozenset((first(x, "ref")[1], first(x, "pin")[1]) for x in find(n, "node"))
    expected_path = BUILD / "expected_netlist.json"
    if not expected_path.exists():
        print("Netlist: build/expected_netlist.json missing - run gen_schematic.py first")
        return 1
    exp = {k: frozenset(tuple(m) for m in v) for k, v in json.loads(expected_path.read_text()).items()}
    by_pins_got = {v: k for k, v in got.items()}
    by_pins_exp = {v: k for k, v in exp.items()}
    for pins, name in by_pins_exp.items():
        if pins not in by_pins_got:
            failed = True
            print(f"  net {name}: KiCad does not have a net with exactly these pins: {sorted(pins)}")
        elif not name.startswith("<") and by_pins_got[pins].lstrip("/") != name:
            failed = True
            print(f"  net {name}: KiCad calls it {by_pins_got[pins]}")
    for pins, name in by_pins_got.items():
        if pins not in by_pins_exp:
            failed = True
            print(f"  unexpected net {name}: {sorted(pins)}")
    comps = len(find(first(net, "components"), "comp"))
    print(f"Netlist: {comps} components, {len(got)} nets - {'MISMATCH' if failed else 'matches the intended netlist'}")

    failed = check_footprints(net) or failed

    cli("sch", "export", "pdf", "-o", str(BUILD / "climasense.pdf"), str(SCH))
    print(f"Plot: {BUILD / 'climasense.pdf'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

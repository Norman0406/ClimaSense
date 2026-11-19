#!/usr/bin/env python3
"""Verify the ClimaSense schematic with KiCad's own tools.

1. Runs KiCad's electrical rules check (ERC) and fails on any violation.
2. Exports KiCad's netlist and compares it, pin by pin, with the netlist the
   generator intended (build/expected_netlist.json).
3. Plots the schematic to build/climasense.pdf.

Usage:  python hardware/tools/check_schematic.py
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


def cli(*args):
    subprocess.run([KICAD_CLI, *args], check=True, capture_output=True, cwd=HW)


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

    cli("sch", "export", "pdf", "-o", str(BUILD / "climasense.pdf"), str(SCH))
    print(f"Plot: {BUILD / 'climasense.pdf'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

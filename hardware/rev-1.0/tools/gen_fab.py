"""Write the files JLCPCB needs to make and assemble the board, into hardware/rev-1.0/fab/:

  climasense-<rev>-gerbers.zip   copper, mask, paste, silkscreen, outline and drill files
  climasense-<rev>-bom.csv       one line per part type, with the JLCPCB (LCSC) part number
  climasense-<rev>-cpl.csv       where each part goes and how it is turned

Run it with the normal Python:  python hardware/rev-1.0/tools/gen_fab.py
It first runs check_pcb.py and refuses to write anything if the board does not pass
(--no-check skips that).

The placement file is not KiCad's position file as it is. JLCPCB turns and centres each part
as its own footprint for that part number is drawn, and for a few parts that differs from
KiCad's footprint. CORRECTIONS holds those differences. They were measured on 2026-11-19 by
laying the pads of JLCPCB's footprint (EasyEDA data of the part number) over ours; all other
parts on the board agreed without correction. JLCPCB's order page shows the parts placed on
the board before you pay: check there that pin 1 of every chip is where the silkscreen
shows it (see docs/hardware/ordering.md).
"""
import csv
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HW = Path(__file__).resolve().parent.parent
KICAD_CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
PCB = HW / "climasense.kicad_pcb"
SCH = HW / "climasense.kicad_sch"
OUT = HW / "fab"
NAME = "climasense-1.0"
LAYERS = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"

# KiCad footprint -> (degrees to add to the rotation, where JLCPCB's part centre lies in the
# footprint's own frame: x to the right, y down, in mm, footprint not rotated)
CORRECTIONS = {
    "SOT-23-6": (270, (0.0, 0.0)),                                      # U1  (C7519)
    "SOT-23-5": (180, (0.0, 0.0)),                                      # U3, U9  (C404027)
    # KiCad's origin is between the locating pegs, JLCPCB's in the middle of the pads
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12": (0, (0.0, -1.571)),          # J1  (C165948)
    "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal": (0, (0.0, -0.062)),   # J2  (C160404)
    # our origin is the middle of the module, JLCPCB's the middle of its pads (no antenna)
    "ESP32-C6-WROOM-1": (0, (0.0, 2.995)),                              # U4  (C5366877)
}


def cli(*args):
    r = subprocess.run([KICAD_CLI, *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"kicad-cli {' '.join(map(str, args[:3]))} failed:\n{r.stdout}\n{r.stderr}")


def turn(p, deg):
    """Rotate counter-clockwise as seen on screen (KiCad's sense), with y pointing down."""
    a = math.radians(deg)
    return (p[0] * math.cos(a) + p[1] * math.sin(a), -p[0] * math.sin(a) + p[1] * math.cos(a))


def main():
    if "--no-check" not in sys.argv:
        r = subprocess.run([sys.executable, str(HW / "tools" / "check_pcb.py"), "--require-routed"])
        if r.returncode != 0:
            raise SystemExit("The board does not pass check_pcb.py - no order files written.")

    if OUT.exists():
        shutil.rmtree(OUT)
    gerbers = OUT / "gerbers"
    gerbers.mkdir(parents=True)

    # --- board: Gerbers and drill files, zipped ------------------------------
    cli("pcb", "export", "gerbers", "--output", str(gerbers) + "/", "--layers", LAYERS,
        "--subtract-soldermask", "--no-x2", "--no-netlist", PCB)
    cli("pcb", "export", "drill", "--output", str(gerbers) + "/", "--format", "excellon", "--drill-origin", "absolute",
        "--excellon-units", "mm", "--excellon-zeros-format", "decimal", "--excellon-oval-format", "alternate",
        "--excellon-separate-th", PCB)
    for junk in gerbers.glob("*.gbrjob"):
        junk.unlink()
    files = sorted(gerbers.iterdir())
    archive = OUT / f"{NAME}-gerbers.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)

    # --- parts list ----------------------------------------------------------
    bom = OUT / f"{NAME}-bom.csv"
    # one line per JLCPCB part number; the comment is the manufacturer's part number
    cli("sch", "export", "bom", "--output", bom, "--fields", "MPN,Reference,Footprint,LCSC",
        "--labels", "Comment,Designator,Footprint,LCSC Part #", "--group-by", "LCSC",
        "--ref-range-delimiter", "", "--exclude-dnp", SCH)
    with open(bom, newline="", encoding="utf-8") as f:
        lines = list(csv.DictReader(f))
    missing = [row["Designator"] for row in lines if not row["LCSC Part #"].strip()]
    if missing:
        raise SystemExit(f"parts without a JLCPCB number: {missing}")
    in_bom = {ref for row in lines for ref in row["Designator"].split(",")}

    # --- placement -----------------------------------------------------------
    raw = OUT / "kicad-pos.csv"
    cli("pcb", "export", "pos", "--output", raw, "--format", "csv", "--units", "mm", "--side", "both", "--exclude-dnp", PCB)
    with open(raw, newline="", encoding="utf-8") as f:
        placed = list(csv.DictReader(f))
    raw.unlink()
    cpl = OUT / f"{NAME}-cpl.csv"
    corrected, seen = [], set()
    with open(cpl, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in sorted(placed, key=lambda r: (r["Ref"].rstrip("0123456789"), int("0" + "".join(c for c in r["Ref"] if c.isdigit())))):
            ref = row["Ref"]
            if ref not in in_bom:
                continue                      # mounting holes and the like
            x, y, angle = float(row["PosX"]), float(row["PosY"]), float(row["Rot"])
            add, (ox, oy) = CORRECTIONS.get(row["Package"], (0, (0.0, 0.0)))
            dx, dy_down = turn((ox, oy), angle)          # KiCad's position file has y pointing up
            if row["Package"] in CORRECTIONS:
                corrected.append(ref)
            seen.add(ref)
            w.writerow([ref, f"{x + dx:.3f}mm", f"{y - dy_down:.3f}mm", "Top" if row["Side"].lower() == "top" else "Bottom",
                        f"{(angle + add) % 360:g}"])
    if seen != in_bom:
        raise SystemExit(f"parts list and placement disagree: only in parts list {sorted(in_bom - seen)}")

    print(f"Gerbers: {archive}  ({len(files)} files: {', '.join(f.name.split('-')[-1] if f.suffix != '.drl' else f.name for f in files)})")
    print(f"Parts list: {bom}  ({len(lines)} part types, {len(in_bom)} parts)")
    print(f"Placement: {cpl}  ({len(seen)} parts, corrected for JLCPCB's footprints: {', '.join(corrected)})")


if __name__ == "__main__":
    main()

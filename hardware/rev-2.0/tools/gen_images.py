"""Write the pictures of the board that the README and the layout notes show, into docs/images/:

  board-angle.png     3D view from the front left
  board-top.png       3D view straight from above
  copper-top.svg      top copper layer with the board outline
  copper-bottom.svg   bottom copper layer, seen from above through the board (not mirrored)

Run it with the normal Python:  python hardware/rev-2.0/tools/gen_images.py
Run it by hand after the board or a 3D model has changed; it is not part of the board check,
so that the repository does not collect a new set of pictures with every run.

The parts KiCad has no 3D model for get theirs from gen_models.py, which this script runs first.
"""
import re
import subprocess
import sys
from pathlib import Path

HW = Path(__file__).resolve().parent.parent
KICAD_CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
PCB = HW / "climasense.kicad_pcb"
OUT = HW.parent.parent / "docs" / "images" / "rev-2.0"
BACKGROUND = "#0d1117"          # behind the copper plots, so they read the same on light and dark pages


def cli(*args):
    r = subprocess.run([KICAD_CLI, *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"kicad-cli {' '.join(map(str, args[:3]))} failed:\n{r.stdout}\n{r.stderr}")


def render(name, width, height, *view):
    # Basic quality on purpose: the high setting adds a floor with shadows, which come out as
    # a pale halo around the board once the background is transparent.
    cli("pcb", "render", "--width", width, "--height", height, "--quality", "basic", "--background", "transparent",
        *view, "-o", OUT / name, PCB)


def copper(name, layer):
    path = OUT / name
    cli("pcb", "export", "svg", "--mode-single", "--fit-page-to-board", "--exclude-drawing-sheet",
        "--drill-shape-opt", "2", "--layers", f"{layer},Edge.Cuts", "-o", path, PCB)
    svg = path.read_text(encoding="utf-8")
    svg, n = re.subn(r"(<svg\b[^>]*>)", rf'\1\n<rect width="100%" height="100%" fill="{BACKGROUND}"/>', svg, count=1)
    if n != 1:
        raise SystemExit(f"{name}: no <svg> element to put the background into")
    path.write_text(svg, encoding="utf-8", newline="\n")


def main():
    r = subprocess.run([sys.executable, str(HW / "tools" / "gen_models.py")])
    if r.returncode != 0:
        raise SystemExit("gen_models.py failed - no pictures written.")
    OUT.mkdir(parents=True, exist_ok=True)
    # The angled view is lit from the camera only: KiCad's side lights, on by default, put bright
    # patches of glare on the solder mask there. Seen straight from above it is the other way
    # round (a camera light washes the whole board out), so that view keeps the default lights.
    render("board-angle.png", 1600, 800, "--perspective", "--rotate", "-35,0,-20", "--zoom", "1.3", "--pan", "-0.3,0.3,0",
           "--light-side", "0", "--light-camera", "1")
    render("board-top.png", 1600, 760, "--side", "top", "--zoom", "1.8")
    copper("copper-top.svg", "F.Cu")
    copper("copper-bottom.svg", "B.Cu")
    for f in sorted(OUT.iterdir()):
        print(f"{f.relative_to(HW.parent.parent)}  {f.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()

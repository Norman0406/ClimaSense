"""Write the pictures of the board that the README and the layout notes show, into docs/images/:

  board-angle.png     3D view from the front left
  board-top.png       3D view straight from above
  board-bottom.png    3D view of the back, with the display panel in place
  board-fpc.png       close-up of the panel's FPC tail running into its connector
  copper-top.svg      top copper layer with the board outline
  copper-bottom.svg   bottom copper layer, seen from above through the board (not mirrored)

Run it with the normal Python:  python hardware/rev-2.0/tools/gen_images.py
With --fast it writes only a top view, to hardware/rev-2.0/build/preview-top.png, without
rebuilding the 3D models: a quick look at an intermediate board that leaves docs/ alone.
Run it by hand after the board or a 3D model has changed; it is not part of the board check,
so that the repository does not collect a new set of pictures with every run.

The parts KiCad has no 3D model for get theirs from gen_models.py, which this script runs first.

Revision 1.0's top view in the README (docs/images/board-top.png) has the same opaque grey background
(2026-11-22, Norman). Revision 1.0's own gen_images.py is frozen and renders it transparent, so it was
made directly with: kicad-cli pcb render --width 1600 --height 760 --quality basic --background opaque
--side top --zoom 1.8 -o docs/images/board-top.png hardware/rev-1.0/climasense.kicad_pcb
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
# Width of the copper plots in pixels: that of the 3D views as KiCad writes them (1600 asked for),
# so that a page shows plots and views at the same size (2026-11-23, Norman). KiCad gives a plot the
# board's own size in millimetres, which a browser shows 390 pixels wide.
PLOT_WIDTH = 1568


def cli(*args):
    r = subprocess.run([KICAD_CLI, *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"kicad-cli {' '.join(map(str, args[:3]))} failed:\n{r.stdout}\n{r.stderr}")


def render(name, width, height, *view, out=None):
    # Basic quality on purpose: the high setting adds a floor with shadows.
    # An opaque background: with a transparent one, holes and slots show whatever the page
    # behind the picture has (white or dark), which looked like parts or copper.
    cli("pcb", "render", "--width", width, "--height", height, "--quality", "basic", "--background", "opaque",
        *view, "-o", out or OUT / name, PCB)


def copper(name, layer):
    path = OUT / name
    cli("pcb", "export", "svg", "--mode-single", "--fit-page-to-board", "--exclude-drawing-sheet",
        "--drill-shape-opt", "2", "--layers", f"{layer},Edge.Cuts", "-o", path, PCB)
    svg = path.read_text(encoding="utf-8")
    svg, n = re.subn(r"(<svg\b[^>]*>)", rf'\1\n<rect width="100%" height="100%" fill="{BACKGROUND}"/>', svg, count=1)
    if n != 1:
        raise SystemExit(f"{name}: no <svg> element to put the background into")
    size = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm"', svg)
    if not size:
        raise SystemExit(f"{name}: no size in millimetres to replace")
    width, height = float(size.group(1)), float(size.group(2))
    svg = svg.replace(size.group(0), f'width="{PLOT_WIDTH}" height="{round(PLOT_WIDTH * height / width)}"', 1)
    path.write_text(svg, encoding="utf-8", newline="\n")


def main():
    if "--fast" in sys.argv[1:]:
        out = HW / "build" / "preview-top.png"
        out.parent.mkdir(exist_ok=True)
        render("", 1600, 760, "--side", "top", "--zoom", "1.8", out=out)
        print(f"{out.relative_to(HW.parent.parent)}  {out.stat().st_size / 1024:.0f} kB")
        return
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
    # close-up of the FPC tail entering J5, from the component side
    render("board-fpc.png", 1600, 900, "--perspective", "--rotate", "-65,0,-30", "--zoom", "3.5",
           "--pan", "-1.2,0.4,0", "--light-side", "0", "--light-camera", "1")
    # the back, with the display panel where it will be stuck (its model is only for this view)
    render("board-bottom.png", 1600, 760, "--side", "bottom", "--zoom", "1.8")
    copper("copper-top.svg", "F.Cu")
    copper("copper-bottom.svg", "B.Cu")
    for f in sorted(OUT.iterdir()):
        print(f"{f.relative_to(HW.parent.parent)}  {f.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()

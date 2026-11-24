"""Write simple 3D models for the parts KiCad has no model for, into hardware/rev-2.0/lib/climasense.3dshapes/.

Run it with the normal Python:  python hardware/rev-2.0/tools/gen_models.py

The models exist so that the 3D view and the renders in the README show every part. They are
drawn from each datasheet's package drawing: outline and height are the datasheet's, the detail
on top (openings, membranes, the button) is positioned as drawn there but simplified. They are
for looking at, not for checking mechanical fit.

All coordinates below are in millimetres in the footprint's own frame as KiCad's footprint
editor shows it: x to the right, y down, z up from the board, origin at the footprint origin.
The file format is VRML, which KiCad reads in units of 0.1 inch with y pointing up.
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "lib" / "climasense.3dshapes"
UNIT = 2.54

# name: (colour, specular, shininess, transparency)
MATERIALS = {
    "metal": ((0.56, 0.56, 0.55), 0.3, 0.7, 0.0),
    "black": ((0.10, 0.10, 0.10), 0.1, 0.2, 0.0),
    "substrate": ((0.07, 0.16, 0.10), 0.1, 0.1, 0.0),
    "white": ((0.93, 0.93, 0.90), 0.1, 0.1, 0.0),
    "die": ((0.45, 0.47, 0.50), 0.3, 0.5, 0.0),
    "hole": ((0.02, 0.02, 0.02), 0.0, 0.0, 0.0),
    "lens": ((0.96, 0.95, 0.80), 0.3, 0.4, 0.35),
    "kapton": ((0.85, 0.50, 0.10), 0.3, 0.4, 0.0),
}


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def square(side, cx=0.0, cy=0.0):
    return rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)


def rounded(w, h, r, cx=0.0, cy=0.0, steps=6):
    """Rectangle w x h with corner radius r."""
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        for i in range(steps + 1):
            a = math.pi / 2 * (k + i / steps)
            pts.append((cx + sx * (w / 2 - r) + r * math.cos(a), cy + sy * (h / 2 - r) + r * math.sin(a)))
    return pts


def circle(r, cx=0.0, cy=0.0, steps=32):
    return [(cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps))
            for i in range(steps)]


def ring_like(outline, r, cx=0.0, cy=0.0):
    """A circle with as many points as `outline`, each in the direction of the matching outline
    point, so that the two can be joined into a body with a round opening."""
    pts = []
    for x, y in outline:
        d = math.hypot(x - cx, y - cy)
        pts.append((cx + r * (x - cx) / d, cy + r * (y - cy) / d))
    return pts


def area(pts):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1])) / 2


class Model:
    def __init__(self, name):
        self.name, self.shapes = name, []

    def _extrude(self, material, base, w0, w1, hole, top, place):
        """Solid between the outline `base` at w0 and `top` (default: the same outline) at w1,
        optionally with an opening `hole` (same number of points as the outline) all the way
        through. The outlines must be convex. `place` turns (u, v, w) into model coordinates."""
        top = top or base
        if area(base) < 0:                                  # counter-clockwise seen from +w
            base, top, hole = base[::-1], top[::-1], hole and hole[::-1]
        n = len(base)
        pts = [(u, v, w0) for u, v in base] + [(u, v, w1) for u, v in top]
        faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        if hole:
            pts += [(u, v, w0) for u, v in hole] + [(u, v, w1) for u, v in hole]
            for i in range(n):
                j = (i + 1) % n
                faces.append((2 * n + j, 2 * n + i, 3 * n + i, 3 * n + j))        # wall of the opening
                faces.append((n + i, n + j, 3 * n + j, 3 * n + i))                # top
                faces.append((j, i, 2 * n + i, 2 * n + j))                        # bottom
        else:
            faces += [(n, n + i, n + i + 1) for i in range(1, n - 1)]             # top
            faces += [(0, i + 1, i) for i in range(1, n - 1)]                     # bottom
        self.shapes.append((material, [place(p) for p in pts], faces))

    def prism(self, material, outline, z0, z1, hole=None, top=None):
        """Upright solid: `outline` in the footprint's x/y, from height z0 to z1."""
        # y is turned over before the solid is built, not after: turning it over afterwards
        # would turn every face inside out, and KiCad renders such a part black.
        def up(pts):
            return pts and [(x, -y) for x, y in pts]
        self._extrude(material, up(outline), z0, z1, up(hole), up(top), lambda p: p)

    def box(self, material, x0, y0, x1, y1, z0, z1):
        self.prism(material, rect(x0, y0, x1, y1), z0, z1)

    def lying(self, material, section, y0, y1, hole=None):
        """Lying solid: `section` in x/z, running from footprint y0 to y1."""
        self._extrude(material, section, y0, y1, hole, None, lambda p: (p[0], -p[2], p[1]))

    def write(self):
        # Laid out like the models in KiCad's own library: each material defined once under a
        # name, then every shape refers to its material by that name.
        out = ["#VRML V2.0 utf8", f"# {self.name} - written by hardware/rev-2.0/tools/gen_models.py, do not edit"]
        for material in dict.fromkeys(m for m, _, _ in self.shapes):
            (r, g, b), specular, shininess, transparency = MATERIALS[material]
            out.append(
                f"Shape {{ appearance Appearance {{ material DEF {material.upper()} Material {{ ambientIntensity 0.27 "
                f"diffuseColor {r} {g} {b} specularColor {specular} {specular} {specular} emissiveColor 0 0 0 "
                f"shininess {shininess} transparency {transparency} }} }} }}")
        for material, pts, faces in self.shapes:
            out.append(
                "Shape { geometry IndexedFaceSet { creaseAngle 0.5\n"
                "    coordIndex [ " + ", ".join(",".join(map(str, f)) + ",-1" for f in faces) + " ]\n"
                "    coord Coordinate { point [ "
                + ", ".join(" ".join(f"{c / UNIT:.5f}" for c in p) for p in pts) + " ] } }\n"
                f"  appearance Appearance {{ material USE {material.upper()} }} }}")
        (OUT / f"{self.name}.wrl").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# SHT45 - Sensirion SHT4x datasheet: DFN 1.5 x 1.5 x 0.5 mm, sensor opening in the middle.
# --------------------------------------------------------------------------
def sht4x():
    m = Model("Sensirion_SHT4x")
    body = square(1.5)
    m.prism("black", body, 0, 0.35)
    m.prism("black", body, 0.35, 0.5, hole=ring_like(body, 0.35))
    m.prism("die", circle(0.35), 0.35, 0.37)
    return m


# --------------------------------------------------------------------------
# SGP41 - Sensirion datasheet v1.0, section 5 and figure 17: 2.44 x 2.44 x 0.85 mm, black
# mould, opening of 0.8 mm diameter offset towards the bottom right, pin-1 dot top left.
# --------------------------------------------------------------------------
def sgp41():
    m = Model("Sensirion_SGP41")
    body = square(2.44)
    ox = oy = 0.3
    m.prism("black", body, 0, 0.6)
    m.prism("black", body, 0.6, 0.85, hole=ring_like(body, 0.4, ox, oy))
    m.prism("white", circle(0.4, ox, oy), 0.6, 0.7)
    m.prism("white", circle(0.12, -0.85, -0.85, steps=16), 0.85, 0.855)
    return m


# --------------------------------------------------------------------------
# BMP580 - Bosch BST-BMP580-DS004-02, figure 24 and table on page 10: 2.0 x 2.0 x 0.75 mm,
# metal lid 1.85 mm square, port hole of 0.25 mm diameter 0.6 mm in from the top and the
# right edge (pin 1 is the top left corner).
# --------------------------------------------------------------------------
def bmp580():
    m = Model("Bosch_BMP580")
    m.prism("substrate", square(2.0), 0, 0.2)
    m.prism("metal", rounded(1.85, 1.85, 0.15), 0.2, 0.75)
    m.prism("hole", circle(0.125, 0.4, -0.4, steps=16), 0.75, 0.755)
    return m


# --------------------------------------------------------------------------
# SCD41 - Sensirion SCD4x datasheet v1.5, figure 3: 10.1 x 10.1 x 6.5 mm; base board 0.8 mm
# thick, metal cap 8.5 mm square at the bottom and 7.8 mm at the top, white protection
# membrane on top whose notched corner marks pin 1 (top left).
# --------------------------------------------------------------------------
def scd4x():
    m = Model("Sensirion_SCD4x")
    m.prism("substrate", square(10.1), 0, 0.8)
    m.prism("metal", rounded(8.5, 8.5, 1.2), 0.8, 6.3, top=rounded(7.8, 7.8, 1.2))
    h, notch = 2.7, 1.3
    m.prism("white", [(-h + notch, -h), (h, -h), (h, h), (-h, h), (-h, -h + notch)], 6.3, 6.5)
    return m


# --------------------------------------------------------------------------
# RGB LED - Everlight 19-337/R6GHBHC-A01/2T datasheet, page 9: base 1.6 x 1.6 x 0.2 mm, clear
# resin 1.1 mm wide (1.0 mm at the top) over the full length, 0.35 mm over all.
# --------------------------------------------------------------------------
def led_19_337():
    m = Model("LED_RGB_Everlight_19-337")
    m.prism("white", square(1.6), 0, 0.2)
    m.prism("lens", rect(-0.55, -0.8, 0.55, 0.8), 0.2, 0.35, top=rect(-0.5, -0.8, 0.5, 0.8))
    return m


# --------------------------------------------------------------------------
# Push button - XKB TS-1187A: 5.1 x 5.1 mm body, 1.5 mm high with the button, four terminals
# on the pads of KiCad's footprint. The body and height are the part's; the button diameter
# and the split between base and cover are estimated from photographs.
# --------------------------------------------------------------------------
def ts_1187a():
    m = Model("SW_Push_XKB_TS-1187A")
    m.prism("black", square(5.1), 0, 0.45)
    m.prism("metal", rounded(5.1, 5.1, 0.4), 0.45, 1.0)
    m.prism("black", circle(1.3), 1.0, 1.5)
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.box("metal", min(sx * 2.5, sx * 3.3), sy * 1.875 - 0.3, max(sx * 2.5, sx * 3.3), sy * 1.875 + 0.3, 0, 0.25)
    return m


# --------------------------------------------------------------------------
# USB-C receptacle - HRO TYPE-C-31-M-12 drawing: shell 8.34 x 2.56 mm with its top 3.26 mm
# above the board, 7.35 mm long, 8.94 mm wide over the mounting legs. In KiCad's footprint the
# shell runs from y = -3.7 (back) to y = 3.65 (opening); the legs stand in the four slots.
# --------------------------------------------------------------------------
def usb_c_hro():
    m = Model("USB_C_Receptacle_HRO_TYPE-C-31-M-12")
    back, front, mid = -3.7, 3.65, 3.26 - 2.56 / 2
    outer = rounded(8.34, 2.56, 1.2, cy=mid, steps=10)
    inner = rounded(8.34 - 0.5, 2.56 - 0.5, 0.95, cy=mid, steps=10)
    m.lying("metal", outer, back, front, hole=inner)
    m.lying("metal", outer, back, back + 0.3)                                   # closed at the back
    m.lying("black", rect(-3.35, mid - 0.35, 3.35, mid + 0.35), back + 0.3, 2.7)     # contact tongue
    m.box("black", -3.9, back, 3.9, 3.0, 0, 0.75)                               # housing under the shell
    for sx in (-1, 1):
        for y, half in ((-3.13, 0.75), (1.05, 0.55)):
            m.box("metal", min(sx * 4.1, sx * 4.47), y - half, max(sx * 4.1, sx * 4.47), y + half, 0, mid)
    return m


# --------------------------------------------------------------------------
# FPC connector - Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, drawing 8.01A0-C rev L: natural housing
# 15.50 x 4.90 mm, 2.00 mm high, black flip lock over the back half, solder tails reaching
# 5.32 mm behind the front edge, metal holding tabs at the ends. Footprint origin in the middle
# of the housing, opening at y = +2.45.
# --------------------------------------------------------------------------
def kinghelm_fpc_24():
    m = Model("Kinghelm_KH-FPC0.5-H2.0SMT-24P")
    m.box("white", -7.75, -2.45, 7.75, 2.45, 0, 1.6)
    m.box("black", -7.1, -2.45, 7.1, 0.2, 1.6, 2.0)            # flip lock, closed
    m.box("hole", -6.3, 1.2, 6.3, 2.46, 0.5, 1.1)              # the opening the FPC goes into
    for i in range(24):
        x = (i - 11.5) * 0.5
        m.box("metal", x - 0.075, -2.87, x + 0.075, -2.45, 0, 0.12)
    for sx in (-1, 1):
        m.box("metal", min(sx * 7.75, sx * 8.05), -1.6, max(sx * 7.75, sx * 8.05), 0.0, 0, 1.2)
    return m


# --------------------------------------------------------------------------
# E-paper panel - Good Display GDEY0213B74, specification page 7: glass 59.2 x 29.2 mm, about
# 1.0 mm thick. The active area is drawn 48.6 x 23.8 mm in the middle (250 x 122 pixels at
# about 0.194 mm); its exact position on the glass is approximate. For the 3D view only: the
# board generator puts it above the parts, where its frame will carry it.
# --------------------------------------------------------------------------
def gdey0213b74():
    m = Model("GDEY0213B74")
    m.box("white", -29.6, -14.6, 29.6, 14.6, 0, 1.0)
    m.box("die", -24.3, -11.9, 24.3, 11.9, 1.0, 1.02)
    return m


# --------------------------------------------------------------------------
# Side-push switch - Alps SKRT catalogue, drawing No. 1: body 4.5 wide, 2.56 deep behind the
# button, 3.3 high; round button 2.0 across, 0.84 proud of the body, its centre 1.7 above the
# board. Footprint frame: guide bosses on y = 0, button towards +y.
# --------------------------------------------------------------------------
def alps_skrt():
    m = Model("Alps_SKRTLAE010")
    front, back = 2.05 - 0.84, -(3.4 - 2.05)
    m.box("metal", -2.25, back, 2.25, front, 0, 3.3)
    m.box("black", -2.0, back + 0.2, 2.0, front - 0.05, 0.2, 3.2)
    m.box("white", -1.0, front, 1.0, 2.05, 0.7, 2.7)
    return m


# --------------------------------------------------------------------------
# The panel's FPC tail, for the 3D view and for the length check. GDEY0213B74 specification
# page 7: 14.30 mm from the glass to its end, the last 6.00 mm stiffened (0.3 mm thick over all,
# the flexible part about 0.1 mm), 12.50 mm wide at the contacts. Where it leaves the glass it is
# wider: a shoulder 14.3 mm wide in all, 1.38 mm outside the tail's edge on the pin 1 side
# (dimensioned) and about 0.4 mm on the other (measured off the drawing), which runs 4.1 mm out
# from the glass and narrows to the tail's width at 4.9 mm.
#
# Since 2026-11-24 the panel lies on the component side, on a frame FRAME_HEIGHT above the board
# (gen_pcb.py), display up, and the tail folds back under it. Its path, in the frame of the
# board-only footprint that carries it (origin on the board's top surface below the glass edge,
# x to the right, z up): the tail leaves the glass on top of the panel's back glass, `ledge`
# above the panel's back; it runs straight out for `a`, turns down in a half circle and runs back
# to the left into J5, which takes it `zj` above the board (measured off Kinghelm's side view),
# its stiffened end `insert` deep in the connector. The half circle hangs free, so a tail that is
# longer or shorter moves the fold: `a` is what the tail's length leaves, and it must not be less
# than `glue` (silicone glue on the tail's back, specification page 35, item 12: rigid, no bend).
# `spare` is how much shorter the tail could be before the fold begins on the glue.
# (Until 2026-11-24 the panel lay on the back and the tail came round both edges of a slot in the
# board in bends of 0.5 mm; that path needed 13.1 mm of the 14.3 mm.)
# --------------------------------------------------------------------------
TAIL = dict(length=14.30, stiff=6.00, width=12.50, flex_t=0.1, stiff_t=0.3,
            bend_r=0.5,          # smallest bend, inside radius (Good Display's usage guidelines)
            ledge=0.5,           # how far above the panel's back the tail leaves the glass
            glue=1.0,            # silicone glue may reach this far onto the tail's back: no bend there
            frame=4.75,          # the panel's back above the board (FRAME_HEIGHT in gen_pcb.py)
            zj=1.15,             # where J5 takes the tail, above the board (Kinghelm drawing 8.01A0-C, side view)
            j5_front=-3.0,       # J5's front edge, 3.0 mm inside the glass edge (J5_FRONT_INSIDE_GLASS in gen_pcb.py)
            insert=2.1,
            # the shoulder: edges across the tail from its centre line (pin 24 side, pin 1 side; pin 1 is at
            # the bottom of the board), how far it runs from the glass at full width, and where it has
            # narrowed to the tail's width
            shoulder=(-(6.25 + 0.4), 6.25 + 8.15 - 6.77), shoulder_run=4.06, shoulder_end=4.87)


def tail_path():
    """Centre line of the tail as a list of (x, z) points, the stiffener's start index, and the
    lengths: (points, stiff_from, a, spare)."""
    t = TAIL
    za = t["frame"] + t["ledge"]                                 # height at which the tail leaves the glass
    rho = (za - t["zj"]) / 2                                     # the half circle's radius, centre line
    arc = math.pi * rho
    flex = t["length"] - t["stiff"]
    stiff_start = t["j5_front"] - t["insert"] + t["stiff"]       # x where the stiffener begins
    a = (flex - arc + stiff_start) / 2                           # straight run on top; below it is a - stiff_start
    b = a - stiff_start
    assert rho - t["flex_t"] / 2 >= t["bend_r"], "the fold is tighter than the smallest bend"
    assert a >= t["glue"], "the fold begins where the glue on the tail's back may still be"
    assert b >= 0, "the fold reaches into the stiffened end"
    pts = [(0.0, za), (a, za)]
    for i in range(1, 25):                                       # the half circle, out and down
        ang = math.pi * i / 24
        pts.append((a + rho * math.sin(ang), za - rho + rho * math.cos(ang)))
    pts.append((stiff_start, t["zj"]))
    stiff_from = len(pts) - 1
    pts.append((t["j5_front"] - t["insert"], t["zj"]))           # the stiffened end, into J5
    spare = flex - arc - t["glue"] - max(0.0, t["glue"] - stiff_start)
    return pts, stiff_from, a, spare


def fpc_tail():
    m = Model("GDEY0213B74_FPC_tail")
    pts, stiff_from, _, _ = tail_path()
    w = TAIL["width"] / 2
    along = 0.0                                                  # distance from the glass along the tail
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        t = TAIL["stiff_t"] if i >= stiff_from else TAIL["flex_t"]
        dx, dz = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dz)
        if n < 1e-9:
            continue
        mid, along = along + n / 2, along + n
        # the shoulder: full width near the glass, narrowing to the tail's width
        k = min(1.0, max(0.0, (TAIL["shoulder_end"] - mid) / (TAIL["shoulder_end"] - TAIL["shoulder_run"])))
        y0, y1 = -w + k * (TAIL["shoulder"][0] + w), w + k * (TAIL["shoulder"][1] - w)
        nx, nz = -dz / n * t / 2, dx / n * t / 2
        section = [(a[0] + nx, a[1] + nz), (b[0] + nx, b[1] + nz), (b[0] - nx, b[1] - nz), (a[0] - nx, a[1] - nz)]
        m.lying("kapton", section, y0, y1)
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.wrl"):
        old.unlink()
    models = [sht4x(), sgp41(), bmp580(), scd4x(), led_19_337(), ts_1187a(), usb_c_hro(), kinghelm_fpc_24(), gdey0213b74(), alps_skrt(), fpc_tail()]
    for m in models:
        m.write()
    print(f"{len(models)} models written to {OUT}: {', '.join(m.name for m in models)}")
    _, _, a, spare = tail_path()
    t = TAIL
    drop = t["frame"] + t["ledge"] - t["zj"]
    print(f"FPC tail: {t['length']:.2f} mm long, {t['stiff']:.2f} mm of it stiff; panel {t['frame']:g} mm above the board, "
          f"drop {drop:.2f} mm, half circle of {math.pi * drop / 2:.2f} mm with an inside radius of {drop / 2 - t['flex_t'] / 2:.2f} mm; "
          f"the fold begins {a:.2f} mm from the glass (glue up to {t['glue']:.1f} mm, specification page 35) and stands "
          f"{a + drop / 2:.2f} mm beyond it; {spare:+.2f} mm spare")

if __name__ == "__main__":
    main()

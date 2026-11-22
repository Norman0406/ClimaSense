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
# board generator puts it on the back, where the panel will be stuck.
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
# The panel's FPC tail, for the 3D view only. GDEY0213B74 specification page 7: 12.50 mm wide,
# 14.30 mm from the glass to its end, the last 6.00 mm stiffened (0.3 mm thick over all, the
# flexible part about 0.1 mm). Its path, in the frame of the board-only footprint that carries it
# (origin on the top surface above the glass edge, x to the right, z up; the back of the board is
# at z = -1.6): from the glass edge along the back to the FPC slot, up through the slot near its
# left wall, round the slot's edge in a bend of 0.4 mm radius on each side, back to the left on
# the component side, and with its stiffened end 2.1 mm into J5 (Kinghelm drawing). What length is
# left over between the bend and the stiffener is drawn as a loop standing up from the board, so
# the picture shows the slack honestly. The numbers are returned for the documentation.
# --------------------------------------------------------------------------
TAIL = dict(length=14.30, stiff=6.00, width=12.50, flex_t=0.1, stiff_t=0.3, bend_r=0.4,
            slot_x=0.8 + 0.05,   # centre line of the tail in the slot: 0.05 mm right of its left wall (x 71.8)
            j5_front=-7.0,       # J5's front edge, 7.0 mm left of the glass edge (x 64.0; J5_FRONT_TO_SLOT in gen_pcb.py)
            insert=2.1)


def tail_path():
    """Centre line of the tail as a list of (x, z) points, the stiffener's start index, and the
    lengths: (points, stiff_from, needed, slack)."""
    t = TAIL
    r, zb, zt = t["bend_r"], -1.6 - t["flex_t"] / 2, t["flex_t"] / 2
    xs = t["slot_x"]
    pts = [(0.0, zb), (xs - r, zb)]
    for i in range(1, 9):                                        # lower bend, up into the slot
        a = math.pi / 2 * i / 8
        pts.append((xs - r + r * math.sin(a), zb + r - r * math.cos(a)))
    pts.append((xs, zt - r))
    for i in range(1, 9):                                        # upper bend, over to the left
        a = math.pi / 2 * i / 8
        pts.append((xs - r + r * math.cos(a), zt - r + r * math.sin(a)))
    run = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    end = t["j5_front"] - t["insert"]
    stiff_start = end + t["stiff"]
    a, b = pts[-1], (stiff_start, zt)
    flex_left = t["length"] - t["stiff"] - run
    chord = math.dist(a, b)
    needed = run + chord + t["stiff"]
    slack = t["length"] - needed
    if slack > 0.05:                                             # the spare length stands up as a loop
        lo, hi = math.pi + 1e-6, 2 * math.pi - 1e-6              # central angle of an arc longer than a half circle
        if flex_left / chord < math.pi / 2:
            lo, hi = 1e-6, math.pi
        for _ in range(60):
            phi = (lo + hi) / 2
            R = chord / (2 * math.sin(phi / 2))
            lo, hi = (phi, hi) if R * phi < flex_left else (lo, phi)
        d = R * math.cos(phi / 2)                                # centre's height above the chord (negative: below)
        cx, cz = (a[0] + b[0]) / 2, zt + d
        a0 = math.atan2(a[1] - cz, a[0] - cx)
        for i in range(1, 25):
            ang = a0 + phi * i / 24
            pts.append((cx + R * math.cos(ang), cz + R * math.sin(ang)))
        pts[-1] = b
    else:
        pts.append(b)
    stiff_from = len(pts) - 1
    zs = t["stiff_t"] / 2
    pts[-1] = (stiff_start, zs)
    pts += [(t["j5_front"] + 0.6, zs), (t["j5_front"], 0.8), (end, 0.8)]   # into J5's opening (0.5-1.1 mm up)
    return pts, stiff_from, needed, slack


def fpc_tail():
    m = Model("GDEY0213B74_FPC_tail")
    pts, stiff_from, _, _ = tail_path()
    w = TAIL["width"] / 2
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        t = TAIL["stiff_t"] if i >= stiff_from else TAIL["flex_t"]
        dx, dz = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dz)
        if n < 1e-9:
            continue
        nx, nz = -dz / n * t / 2, dx / n * t / 2
        section = [(a[0] + nx, a[1] + nz), (b[0] + nx, b[1] + nz), (b[0] - nx, b[1] - nz), (a[0] - nx, a[1] - nz)]
        m.lying("kapton", section, -w, w)
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.wrl"):
        old.unlink()
    models = [sht4x(), sgp41(), bmp580(), scd4x(), led_19_337(), ts_1187a(), usb_c_hro(), kinghelm_fpc_24(), gdey0213b74(), alps_skrt(), fpc_tail()]
    for m in models:
        m.write()
    print(f"{len(models)} models written to {OUT}: {', '.join(m.name for m in models)}")
    _, _, needed, slack = tail_path()
    print(f"FPC tail: {TAIL['length']:.2f} mm long, {needed:.2f} mm needed from the glass edge to full insertion "
          f"with J5's front {-TAIL['j5_front'] + 0.8:.1f} mm from the slot: {slack:+.2f} mm spare")


if __name__ == "__main__":
    main()

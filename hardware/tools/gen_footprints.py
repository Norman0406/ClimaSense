#!/usr/bin/env python3
"""Generate the ClimaSense project footprints.

Writes hardware/lib/climasense.pretty/*.kicad_mod and hardware/fp-lib-table.
Every dimension below is taken from the manufacturer's land-pattern drawing
named next to it; see docs/hardware/footprints.md for the references.

Coordinates are KiCad footprint coordinates: millimetres, origin at the part
centre, x to the right, y DOWN, seen from the top of the board.

Usage:  python hardware/tools/gen_footprints.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kisch import S, Sym, dump, uid  # noqa: E402

HW = Path(__file__).resolve().parent.parent
PRETTY = HW / "lib" / "climasense.pretty"
KICAD_CLI = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
FP_VERSION = 20260206

SILK_W, FAB_W, CRTYD_W = 0.12, 0.1, 0.05


class Footprint:
    def __init__(self, name: str, descr: str, tags: str, ref_at, value_at):
        self.name = name
        self._n = 0
        self.items: list = []
        self.pad_numbers: list[str] = []
        self.head = [
            Sym("footprint"), name, S("version", FP_VERSION), S("generator", "climasense_gen"),
            S("generator_version", "10.0"), S("layer", "F.Cu"), S("descr", descr), S("tags", tags),
            self._prop("Reference", "REF**", ref_at, "F.SilkS"),
            self._prop("Value", name, value_at, "F.Fab"),
            self._prop("Datasheet", "", (0, 0), "F.Fab", hide=True),
            self._prop("Description", "", (0, 0), "F.Fab", hide=True),
            S("attr", Sym("smd")),
            S("duplicate_pad_numbers_are_jumpers", Sym("no")),
        ]
        self.tail: list = []

    def _uid(self):
        self._n += 1
        return uid(f"fp/{self.name}/{self._n}")

    @staticmethod
    def _font(size=1.0, thickness=0.15):
        return S("effects", S("font", S("size", size, size), S("thickness", thickness)))

    def _prop(self, key, value, at, layer, hide=False):
        p = S("property", key, value, S("at", at[0], at[1], at[2] if len(at) > 2 else 0),
              S("unlocked", Sym("yes")), S("layer", layer))
        if hide:
            p.append(S("hide", Sym("yes")))
        p += [S("uuid", self._uid()), self._font()]
        return p

    # -- graphics ---------------------------------------------------------
    def line(self, a, b, layer, width):
        self.items.append(S("fp_line", S("start", *a), S("end", *b),
                            S("stroke", S("width", width), S("type", Sym("solid"))),
                            S("layer", layer), S("uuid", self._uid())))

    def polyline(self, pts, layer, width, closed=False):
        pts = list(pts) + ([pts[0]] if closed else [])
        for a, b in zip(pts, pts[1:]):
            self.line(a, b, layer, width)

    def rect(self, x1, y1, x2, y2, layer, width):
        self.polyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], layer, width, closed=True)

    def poly(self, pts, layer):
        self.items.append(S("fp_poly", S("pts", *[S("xy", *p) for p in pts]),
                            S("stroke", S("width", SILK_W), S("type", Sym("solid"))),
                            S("fill", Sym("yes")), S("layer", layer), S("uuid", self._uid())))

    def text(self, s, at, layer, size=1.0, thickness=0.15):
        self.items.append(S("fp_text", Sym("user"), s, S("at", at[0], at[1], 0), S("unlocked", Sym("yes")),
                            S("layer", layer), S("uuid", self._uid()), self._font(size, thickness)))

    def pin1_triangle(self, x, y):
        """Small filled silkscreen triangle pointing right, tip at x,y."""
        self.poly([(x, y), (x - 0.4, y - 0.3), (x - 0.4, y + 0.3)], "F.SilkS")

    def body(self, w, h, chamfer=0.0):
        """Fabrication-layer outline with an optional pin-1 chamfer (top left) and the reference text."""
        x, y = w / 2, h / 2
        pts = [(-x + chamfer, -y), (x, -y), (x, y), (-x, y), (-x, -y + chamfer)]
        self.polyline(pts, "F.Fab", FAB_W, closed=True)
        self.text("${REFERENCE}", (0, 0), "F.Fab", size=min(1.0, round(w / 4, 2)), thickness=min(0.15, round(w / 26, 2)))

    def courtyard(self, x, y):
        self.rect(-x, -y, x, y, "F.CrtYd", CRTYD_W)

    # -- pads -------------------------------------------------------------
    def pad(self, number, x, y, w, h, paste=True, chamfer_top_left=0.0, heatsink=False):
        self.pad_numbers.append(str(number))
        layers = ["F.Cu", "F.Mask"] + (["F.Paste"] if paste else [])
        shape = "roundrect" if chamfer_top_left else "rect"
        p = S("pad", str(number), Sym("smd"), Sym(shape), S("at", x, y), S("size", w, h))
        if heatsink:
            p.append(S("property", Sym("pad_prop_heatsink")))
        p.append(S("layers", *layers))
        if chamfer_top_left:
            p += [S("roundrect_rratio", 0), S("chamfer_ratio", round(chamfer_top_left / min(w, h), 6)),
                  S("chamfer", Sym("top_left"))]
        p.append(S("uuid", self._uid()))
        self.items.append(p)

    def paste(self, x, y, w, h):
        """Stencil aperture without copper (used under exposed pads)."""
        self.items.append(S("pad", "", Sym("smd"), Sym("rect"), S("at", x, y), S("size", w, h),
                            S("layers", "F.Paste"), S("uuid", self._uid())))

    def keepout(self, name, pts):
        self.items.append(S(
            "zone", S("layers", "*.Cu"), S("uuid", self._uid()), S("name", name),
            S("hatch", Sym("full"), 0.5), S("connect_pads", S("clearance", 0)), S("min_thickness", 0.25),
            S("keepout", S("tracks", Sym("not_allowed")), S("vias", Sym("not_allowed")),
              S("pads", Sym("not_allowed")), S("copperpour", Sym("not_allowed")), S("footprints", Sym("allowed"))),
            S("placement", S("enabled", Sym("no")), S("sheetname", "")),
            S("fill", S("thermal_gap", 0.5), S("thermal_bridge_width", 0.5), S("island_removal_mode", 0)),
            S("polygon", S("pts", *[S("xy", *p) for p in pts]))))

    def model(self, path):
        self.tail.append(S("model", path, S("offset", S("xyz", 0, 0, 0)), S("scale", S("xyz", 1, 1, 1)),
                           S("rotate", S("xyz", 0, 0, 0))))

    def write(self):
        node = [*self.head, *self.items, S("embedded_fonts", Sym("no")), *self.tail]
        (PRETTY / f"{self.name}.kicad_mod").write_text(dump(node) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# ESP32-C6-WROOM-1
# Espressif "ESP32-C6-WROOM-1 & WROOM-1U Datasheet" v1.4, Figure 11-1.
# --------------------------------------------------------------------------
def esp32_c6_wroom_1() -> Footprint:
    W, H = 18.0, 25.5                 # module outline
    PAD_W, PAD_H, PITCH = 1.5, 0.9, 1.27
    COL_X = 17.5 / 2                  # pad columns are 17.5 mm apart, so pads overhang the edge by 0.5 mm
    Y_PAD1 = -H / 2 + 7.49            # pad 1 centre is 7.49 mm below the top edge
    ANT = 6.0                         # antenna area: top 6 mm
    EP = 3.3                          # ground pad 3.3 x 3.3 mm
    EP_X = -W / 2 + 7.495             # 7.495 mm from the left module edge
    EP_Y = H / 2 - 12.29              # 12.29 mm above the bottom module edge

    fp = Footprint(
        "ESP32-C6-WROOM-1",
        "Espressif ESP32-C6-WROOM-1, Wi-Fi 6 / Bluetooth 5 LE / 802.15.4 module, 18x25.5 mm, PCB antenna "
        "(https://documentation.espressif.com/esp32-c6-wroom-1_wroom-1u_datasheet_en.pdf, figure 11-1)",
        "ESP32 ESP32-C6 WiFi BLE Thread Zigbee module",
        ref_at=(-10.6, 11.2, 90), value_at=(0, 14.6))

    for i in range(14):
        fp.pad(1 + i, -COL_X, round(Y_PAD1 + i * PITCH, 4), PAD_W, PAD_H)
        fp.pad(28 - i, COL_X, round(Y_PAD1 + i * PITCH, 4), PAD_W, PAD_H)
    assert abs((Y_PAD1 + 13 * PITCH) - (H / 2 - 1.5)) < 1e-6  # pad 14 sits 1.5 mm above the bottom edge

    # ground pad: solid copper, paste split into a 3 x 3 grid of 0.8 mm squares (0.45 mm gaps)
    fp.pad(29, EP_X, EP_Y, EP, EP, paste=False, heatsink=True)
    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            fp.paste(round(EP_X + ix * 1.25, 4), round(EP_Y + iy * 1.25, 4), 0.8, 0.8)

    fp.body(W, H)
    fp.line((-W / 2, -H / 2 + ANT), (W / 2, -H / 2 + ANT), "F.Fab", FAB_W)

    # silkscreen: around the antenna end and the bottom end, clear of the pads
    s = 0.12
    top, bot, edge = -H / 2 - s, H / 2 + s, W / 2 + s
    y_stop_top = Y_PAD1 - PAD_H / 2 - 0.3
    y_stop_bot = H / 2 - 1.5 + PAD_H / 2 + 0.3
    fp.polyline([(-edge, y_stop_top), (-edge, top), (edge, top), (edge, y_stop_top)], "F.SilkS", SILK_W)
    fp.polyline([(-edge, y_stop_bot), (-edge, bot), (edge, bot), (edge, y_stop_bot)], "F.SilkS", SILK_W)
    fp.pin1_triangle(-COL_X - PAD_W / 2 - 0.3, Y_PAD1)

    fp.courtyard(COL_X + PAD_W / 2 + 0.25, H / 2 + 0.25)

    # antenna: no copper on any layer underneath
    ant = [(-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, -H / 2 + ANT), (-W / 2, -H / 2 + ANT)]
    fp.polyline(ant, "Cmts.User", 0.1, closed=True)
    fp.text("Antenna - no copper", (0, -H / 2 + ANT / 2), "Cmts.User")
    fp.keepout("Antenna keep-out", ant)

    # same 18 x 25.5 mm outline as the S3 module; used as a visual stand-in only
    fp.model("${KICAD10_3DMODEL_DIR}/RF_Module.3dshapes/ESP32-S3-WROOM-1.step")
    return fp


# --------------------------------------------------------------------------
# Sensirion SGP41, DFN-6 2.44 x 2.44 mm
# Sensirion "SGP41 Datasheet" v1.0, Figure 18 (land pattern), Figure 17 (package).
# --------------------------------------------------------------------------
def sgp41() -> Footprint:
    BODY = 2.44
    PAD_W, PAD_H, PITCH = 0.55, 0.4, 0.8
    X = 2.3 / 2                       # pad CENTRES are 2.3 mm apart (figure 18); pads reach 0.2 mm past the package
    EP_W, EP_H, EP_CHAMFER = 1.25, 1.7, 0.3
    PASTE_W, PASTE_H = 1.05, 1.5

    fp = Footprint(
        "Sensirion_DFN-6-1EP_2.44x2.44mm_P0.8mm_EP1.25x1.7mm",
        "Sensirion SGP41 / SGP40, DFN, 6 pin, 0.8 mm pitch, exposed pad "
        "(https://sensirion.com/media/documents/5FE8673C/61E96F50/Sensirion_Gas_Sensors_Datasheet_SGP41.pdf, figure 18)",
        "Sensirion SGP41 SGP40 DFN NoLead gas sensor",
        ref_at=(0, -2.3), value_at=(0, 2.3))

    for i in range(3):                # 1-3 down the left side, 4-6 up the right side
        fp.pad(1 + i, -X, (i - 1) * PITCH, PAD_W, PAD_H)
        fp.pad(6 - i, X, (i - 1) * PITCH, PAD_W, PAD_H)
    fp.pad(7, 0, 0, EP_W, EP_H, paste=False, chamfer_top_left=EP_CHAMFER)
    assert (X - PAD_W / 2) - EP_W / 2 >= 0.2   # side pads must clear the centre pad
    fp.paste(0, 0, PASTE_W, PASTE_H)

    fp.body(BODY, BODY, chamfer=0.6)
    y = BODY / 2 + 0.11
    fp.line((-BODY / 2, -y), (BODY / 2, -y), "F.SilkS", SILK_W)
    fp.line((-BODY / 2, y), (BODY / 2, y), "F.SilkS", SILK_W)
    fp.pin1_triangle(-X - PAD_W / 2 - 0.3, -PITCH)
    fp.courtyard(X + PAD_W / 2 + 0.25, BODY / 2 + 0.25)
    return fp


# --------------------------------------------------------------------------
# Bosch BMP580, LGA-10 2 x 2 mm
# Bosch "BST-BMP580-DS004-02", Figure 25 (bottom view) - Bosch recommends the
# package pad dimensions as the landing pattern (section 8.2). The figure is a
# BOTTOM view; positions below are mirrored into the top view.
# --------------------------------------------------------------------------
def bmp580() -> Footprint:
    BODY = 2.0
    R = 1.525 / 2                     # pad rows / columns are 1.525 mm apart centre to centre
    LONG, SHORT = 0.275, 0.25         # pad 0.25 x 0.275, long side pointing outwards

    fp = Footprint(
        "Bosch_LGA-10_2x2mm_P0.5mm_BMP580",
        "Bosch BMP580 / BMP581, LGA, 10 pin, 2x2 mm, 0.5 mm pitch "
        "(https://www.bosch-sensortec.com/products/environmental-sensors/pressure-sensors/bmp580/, BST-BMP580-DS004 figure 25)",
        "Bosch BMP580 BMP581 LGA pressure sensor",
        ref_at=(0, -2.1), value_at=(0, 2.1))

    # counter-clockwise from the pin-1 corner (top left), seen from the top
    fp.pad(1, -R, -0.25, LONG, SHORT)
    fp.pad(2, -R, 0.25, LONG, SHORT)
    fp.pad(3, -0.5, R, SHORT, LONG)
    fp.pad(4, 0.0, R, SHORT, LONG)
    fp.pad(5, 0.5, R, SHORT, LONG)
    fp.pad(6, R, 0.25, LONG, SHORT)
    fp.pad(7, R, -0.25, LONG, SHORT)
    fp.pad(8, 0.5, -R, SHORT, LONG)
    fp.pad(9, 0.0, -R, SHORT, LONG)
    fp.pad(10, -0.5, -R, SHORT, LONG)

    fp.body(BODY, BODY, chamfer=0.5)
    # pads on all four sides: silkscreen corner marks only, none at the pin-1 corner
    o, n = BODY / 2 + 0.11, 0.35
    for sx, sy in ((1, -1), (1, 1), (-1, 1)):
        fp.polyline([(sx * (o - n), sy * o), (sx * o, sy * o), (sx * o, sy * (o - n))], "F.SilkS", SILK_W)
    fp.pin1_triangle(-BODY / 2 - 0.25, -0.25)
    fp.courtyard(BODY / 2 + 0.25, BODY / 2 + 0.25)
    return fp


# --------------------------------------------------------------------------
# Everlight 19-337 RGB LED, 1.6 x 1.6 mm, six pads
# Everlight "19-337/R6GHBHC-A01/2T" DSE-0002657 rev 4, page 9
# ("Recommend soldering pad", top view).
# --------------------------------------------------------------------------
def led_19_337() -> Footprint:
    BODY = 1.6
    CORNER_W, CORNER_H = 0.55, 0.4    # pads 1, 3, 4, 6
    MID_W, MID_H = 0.7, 0.5           # pads 2, 5
    CORNER_X = (1.9 - CORNER_W) / 2   # corner pads span 1.9 mm outer edge to outer edge
    MID_X = (2.2 - MID_W) / 2         # middle pads span 2.2 mm
    CORNER_Y = 0.725

    fp = Footprint(
        "LED_RGB_Everlight_19-337_1.6x1.6mm",
        "Everlight 19-337 RGB LED, 1.6x1.6 mm, 6 pads; cathodes 1 (blue), 2 (red), 3 (green), anodes 4, 5, 6 "
        "(https://en.everlight.com/wp-content/plugins/ItemRelationship/product_files/pdf/19-337-R6GHBHC-A01-2T.pdf)",
        "LED RGB Everlight 19-337",
        ref_at=(0, -2.0), value_at=(0, 2.0))

    fp.pad(1, -CORNER_X, -CORNER_Y, CORNER_W, CORNER_H)
    fp.pad(2, -MID_X, 0, MID_W, MID_H)
    fp.pad(3, -CORNER_X, CORNER_Y, CORNER_W, CORNER_H)
    fp.pad(4, CORNER_X, -CORNER_Y, CORNER_W, CORNER_H)
    fp.pad(5, MID_X, 0, MID_W, MID_H)
    fp.pad(6, CORNER_X, CORNER_Y, CORNER_W, CORNER_H)
    assert abs((CORNER_X - CORNER_W / 2) - 0.4) < 1e-9 and abs((MID_X - MID_W / 2) - 0.4) < 1e-9  # 0.8 mm gap

    fp.body(BODY, BODY, chamfer=0.3)
    y = CORNER_Y + CORNER_H / 2 + 0.26
    fp.line((-BODY / 2, -y), (BODY / 2, -y), "F.SilkS", SILK_W)
    fp.line((-BODY / 2, y), (BODY / 2, y), "F.SilkS", SILK_W)
    fp.pin1_triangle(-CORNER_X - CORNER_W / 2 - 0.45, -CORNER_Y)
    fp.courtyard(MID_X + MID_W / 2 + 0.25, y + 0.2)
    return fp


FOOTPRINTS = (esp32_c6_wroom_1, sgp41, bmp580, led_19_337)


def main():
    PRETTY.mkdir(parents=True, exist_ok=True)
    for build in FOOTPRINTS:
        fp = build()
        fp.write()
        print(f"{fp.name}: {len(fp.pad_numbers)} pads ({', '.join(sorted(set(fp.pad_numbers), key=lambda s: int(s)))})")
    (HW / "fp-lib-table").write_text(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "climasense") (type "KiCad") '
        '(uri "${KIPRJMOD}/lib/climasense.pretty") (options "") (descr "ClimaSense project footprints"))\n)\n',
        encoding="utf-8", newline="\n")
    # let KiCad re-save the library so the files are in its own formatting
    if Path(KICAD_CLI).exists():
        subprocess.run([KICAD_CLI, "fp", "upgrade", "--force", str(PRETTY)], check=True, capture_output=True)
    else:
        print(f"note: kicad-cli not found at {KICAD_CLI}; footprints left in generator formatting")


if __name__ == "__main__":
    main()

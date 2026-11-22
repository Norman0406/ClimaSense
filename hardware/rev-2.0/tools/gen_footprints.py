#!/usr/bin/env python3
"""Generate the ClimaSense project footprints.

Writes hardware/rev-2.0/lib/climasense.pretty/*.kicad_mod and hardware/rev-2.0/fp-lib-table.
Every dimension below is taken from the manufacturer's land-pattern drawing
named next to it; see docs/hardware/footprints.md for the references.

Coordinates are KiCad footprint coordinates: millimetres, origin at the part
centre, x to the right, y DOWN, seen from the top of the board.

Usage:  python hardware/rev-2.0/tools/gen_footprints.py
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
# 3D models written by gen_models.py; KiCad has none for these parts
MODELS = "${KIPRJMOD}/lib/climasense.3dshapes"
KICAD_CLI = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
FP_VERSION = 20260206

SILK_W, FAB_W, CRTYD_W = 0.12, 0.1, 0.05


class Footprint:
    def __init__(self, name: str, descr: str, tags: str, ref_at, value_at, attr=("smd",)):
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
            S("attr", *[Sym(a) for a in attr]),
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

    def hole(self, number, x, y, pad, drill):
        """Plated through hole with a round pad on both sides."""
        self.pad_numbers.append(str(number))
        self.items.append(S("pad", str(number), Sym("thru_hole"), Sym("circle"), S("at", x, y), S("size", pad, pad),
                            S("drill", drill), S("layers", "*.Cu", "*.Mask"),
                            S("remove_unused_layers", Sym("no")), S("uuid", self._uid())))

    def npth(self, x, y, drill):
        """Unplated hole (no copper), e.g. for a part's locating pegs."""
        self.items.append(S("pad", "", Sym("np_thru_hole"), Sym("circle"), S("at", x, y), S("size", drill, drill),
                            S("drill", drill), S("layers", "*.Cu", "*.Mask"), S("uuid", self._uid())))

    def round_pad(self, number, x, y, d):
        """Round SMD pad on the top side (a test or probe pad)."""
        self.pad_numbers.append(str(number))
        self.items.append(S("pad", str(number), Sym("smd"), Sym("circle"), S("at", x, y), S("size", d, d),
                            S("layers", "F.Cu", "F.Mask"), S("uuid", self._uid())))

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
    EP = 3.3                          # ground pad 3.3 x 3.3 mm over all,
    EP_SQUARE, EP_GAP = 0.8, 0.45     # made of 3 x 3 squares of 0.8 mm with 0.45 mm gaps
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

    # Ground pad, exactly as figure 11-1 and Espressif's own KiCad footprint draw it: nine
    # copper squares of 0.8 mm with 0.45 mm gaps (3.3 mm over all), each with its own solder
    # mask opening and paste. The figure's twelve thermal vias sit in the gaps between the
    # squares and join them; they are placed by the board generator (route_board.py).
    assert abs(3 * EP_SQUARE + 2 * EP_GAP - EP) < 1e-9
    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            fp.pad(29, round(EP_X + ix * (EP_SQUARE + EP_GAP), 4), round(EP_Y + iy * (EP_SQUARE + EP_GAP), 4),
                   EP_SQUARE, EP_SQUARE, heatsink=True)

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
    fp.model(f"{MODELS}/Sensirion_SGP41.wrl")
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

    # Bosch "BST-BMP5xy-HS000-00" (handling, soldering and mounting), section 3.2: "not
    # recommended to have vias or traces under the BMP580". The area inside the ring of
    # pads is closed on both layers; tracks reach the pads from outside.
    k = R - LONG / 2 - 0.05
    fp.keepout("No tracks under the pressure sensor", [(-k, -k), (k, -k), (k, k), (-k, k)])
    fp.model(f"{MODELS}/Bosch_BMP580.wrl")
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
    fp.model(f"{MODELS}/LED_RGB_Everlight_19-337.wrl")
    return fp


# --------------------------------------------------------------------------
# Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, 0.5 mm FFC/FPC connector, 24 pins, dual contact,
# 2.0 mm high, flip lock at the back (LCSC C3249999)
# Kinghelm customer drawing 8.01A0-C rev L (2019-01-16), single page: "RECOMMENDED PCB LAYOUT",
# top view, bottom view and side view; the table gives DIM A to G for 24 pins.
# Origin: middle of the housing (15.50 x 4.90 mm). Seen from the top, with the solder tails at
# the top (y < 0) and the FPC opening at the bottom (y > 0), pin 1 is on the LEFT: the top view
# marks it with the "refer pin" triangle at the left end, the pin count "XX" stands at the right.
# JLCPCB's own footprint of C3249999 (EasyEDA) agrees: pin 1 at the left, same pad sizes.
# --------------------------------------------------------------------------
def kinghelm_fpc_24() -> Footprint:
    PINS, PITCH = 24, 0.50
    DIM_A, DIM_C, DIM_F, DIM_G = 15.50, 11.50, 13.90, 17.10    # table, 24-pin row
    assert abs((PINS - 1) * PITCH - DIM_C) < 1e-9               # C: pin 1 to pin 24, centre to centre
    DEPTH = 4.90                      # bottom view: front edge to the back of the housing
    TAIL_TIP = 5.32                   # bottom view: front edge to the ends of the solder tails
    TAB_FRONT, TAB_BACK = 2.85 - 1.60, 2.85   # bottom view: metal holding tab, from the front edge
    PAD_W, PAD_L = 0.25, 1.30         # layout: signal pad 0.25 wide, 1.30 long
    PAD_BEYOND_TAIL = 0.45            # layout: "0.45 Ref" from the pad's outer end to the tail's end
    GAP = 1.03                        # layout: signal pads' inner end to the holding pads
    MP_L = 2.80                       # layout: holding pads 2.80 long
    MP_W = (DIM_G - DIM_F) / 2        # layout: DIM F (inner) and DIM G (outer) span the holding pads
    MP_X = (DIM_F + DIM_G) / 4
    FRONT = DEPTH / 2                 # front edge (the FPC opening) at y = +2.45

    pad_outer = FRONT - TAIL_TIP - PAD_BEYOND_TAIL     # -3.32
    pad_y = round(pad_outer + PAD_L / 2, 4)
    mp_top = pad_outer + PAD_L + GAP                   # holding pads begin 1.03 below the signal pads
    mp_y = round(mp_top + MP_L / 2, 4)
    # the metal tab (bottom view: 1.25 to 2.85 mm behind the front edge) sits inside its pad
    assert mp_top < FRONT - TAB_BACK and mp_top + MP_L > FRONT - TAB_FRONT

    fp = Footprint(
        "Kinghelm_KH-FPC0.5-H2.0SMT-24P-QCHF_1x24-1MP_P0.50mm",
        "Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF, FFC/FPC connector, 24 pins, 0.5 mm pitch, dual contact, "
        "2.0 mm high, flip lock (LCSC C3249999; Kinghelm drawing 8.01A0-C rev L, recommended PCB layout)",
        "FPC FFC connector 0.5mm 24 pin dual contact Kinghelm",
        ref_at=(0, -4.5), value_at=(0, 4.0))
    for i in range(PINS):
        fp.pad(1 + i, round((i - (PINS - 1) / 2) * PITCH, 4), pad_y, PAD_W, PAD_L)
    for x in (-MP_X, MP_X):
        fp.pad("MP", round(x, 4), mp_y, MP_W, MP_L)

    x, y0, y1 = DIM_A / 2, -DEPTH / 2, FRONT
    fp.polyline([(-x, y0), (x, y0), (x, y1), (-x, y1)], "F.Fab", FAB_W, closed=True)
    fp.text("${REFERENCE}", (0, 0), "F.Fab", size=1.0, thickness=0.15)
    # silkscreen: the two ends of the housing between the pads, and the pin-1 mark
    s = x + 0.15
    for sx in (-1, 1):
        fp.line((sx * s, round(mp_y + MP_L / 2 + 0.3, 3)), (sx * s, FRONT), "F.SilkS", SILK_W)
    fp.line((-x, FRONT + 0.15), (x, FRONT + 0.15), "F.SilkS", SILK_W)
    fp.pin1_triangle(-DIM_C / 2 - 0.45, round(pad_y, 3))
    # courtyard: pads, housing, and the flip lock, which opens backwards over the tails
    # (side view: 5.9 mm from the front edge when open)
    cx = MP_X + MP_W / 2 + 0.25
    fp.rect(-cx, round(FRONT - 5.9 - 0.25, 3), cx, round(FRONT + 0.25, 3), "F.CrtYd", CRTYD_W)
    fp.model(f"{MODELS}/Kinghelm_KH-FPC0.5-H2.0SMT-24P.wrl")
    return fp


# --------------------------------------------------------------------------
# Alps Alpine SKRTLAE010, side-push tact switch, 4.5 x 3.4 x 3.3 mm, with guide bosses
# (LCSC C110293). Alps catalogue sheet "SKRT Series" (Update 2510), drawing No. 1: dimensions and
# "Land Dimensions, viewed from switch mounting face". Measured from the drawing where it gives no
# number; those values are marked "drawing".
# Origin: the line through the two guide bosses, midway between them. Seen from the mounting
# face, the three terminal pads lie behind that line (y < 0) and the two holding pads in front of
# it (y > 0); the button pushes from the front (+y), between the holding pads.
# Terminals 1 and 3 are joined inside the switch (circuit diagram), so both carry pad number 1.
# --------------------------------------------------------------------------
def alps_skrtlae010() -> Footprint:
    BOSS_PITCH, HOLE = 4.25, 0.9          # land: 2 x 0.9 mm holes, 4.25 apart
    TERM_SPAN, TERM_W, MID_W = 3.2, 0.75, 0.6   # land: terminal pads 3.2 over all, 0.75 and 0.6 wide
    TERM_BACK, TERM_FRONT = -1.8, -0.07   # land: 1.8 behind the boss line; front end 0.07 (drawing)
    HOLD_W, HOLD_FRONT = 1.3, 1.5        # land: holding pads 1.3 wide, 0.9 long, ending 1.5 in front
    HOLD_BACK = 0.65                      # drawn from 0.6 (0.62 measured); 0.65 keeps 0.2 mm from the boss holes
    HOLD_SPAN = 5.0                       # land: 5 over all (inner edges 2.4 apart)
    KEEP_FRONT, KEEP_BACK, KEEP_W = 1.5, 0.3, 2.0   # land: "prohibited area of copper tracks"
    BODY_W, BODY_FRONT, BODY_BACK = 4.5, 2.05 - 0.84, -(3.4 - 2.05)   # dimensions: 2.05 boss to button tip, 0.84 button
    BUTTON_D, BUTTON_TIP = 2.0, 2.05
    # JLCPCB keeps 0.2 mm between an unplated hole and copper. As drawn, the outer terminal pads
    # come within about 0.08 mm of the boss holes and the holding pads within 0.15 mm: the outer
    # terminal pads' outer edge is pulled in by 0.125 mm (0.625 instead of 0.75 wide; the terminal
    # itself is 0.65 wide) and the holding pads start 0.05 mm further forward, so that all keep
    # 0.2 mm. The board's own rule is 0.25 mm; gen_pcb.py writes an exception of 0.2 mm for the
    # switches' own pads (climasense.kicad_dru).
    outer_edge = BOSS_PITCH / 2 - HOLE / 2 - 0.2
    term_inner = TERM_SPAN / 2 - TERM_W
    outer_w = round(outer_edge - term_inner, 4)
    outer_x = round((outer_edge + term_inner) / 2, 4)

    fp = Footprint(
        "Alps_SKRTLAE010_SidePush",
        "Alps Alpine SKRTLAE010 side-push tact switch, 4.5x3.4x3.3 mm, guide bosses (LCSC C110293; Alps SKRT "
        "catalogue drawing No. 1, land dimensions; outer terminal pads narrowed to keep 0.2 mm from the boss holes)",
        "switch tact side push Alps SKRT",
        ref_at=(0, -2.6), value_at=(0, 3.2))
    ty, tl = round((TERM_BACK + TERM_FRONT) / 2, 4), round(TERM_FRONT - TERM_BACK, 4)
    fp.pad(1, -outer_x, ty, outer_w, tl)
    fp.pad(2, 0, ty, MID_W, tl)
    fp.pad(1, outer_x, ty, outer_w, tl)
    hx = (HOLD_SPAN - HOLD_W) / 2
    hy, hl = round((HOLD_FRONT + HOLD_BACK) / 2, 4), round(HOLD_FRONT - HOLD_BACK, 4)
    for sx in (-1, 1):
        fp.items.append(S("pad", "", Sym("smd"), Sym("rect"), S("at", round(sx * hx, 4), hy), S("size", HOLD_W, hl),
                          S("layers", "F.Cu", "F.Mask", "F.Paste"), S("uuid", fp._uid())))
        fp.npth(round(sx * BOSS_PITCH / 2, 4), 0, HOLE)
    k = KEEP_W / 2
    fp.keepout("No tracks under the button", [(-k, KEEP_BACK), (k, KEEP_BACK), (k, KEEP_FRONT), (-k, KEEP_FRONT)])
    x = BODY_W / 2
    fp.polyline([(-x, BODY_BACK), (x, BODY_BACK), (x, BODY_FRONT), (-x, BODY_FRONT)], "F.Fab", FAB_W, closed=True)
    b = BUTTON_D / 2
    fp.polyline([(-b, BODY_FRONT), (-b, BUTTON_TIP), (b, BUTTON_TIP), (b, BODY_FRONT)], "F.Fab", FAB_W)
    fp.text("${REFERENCE}", (0, -0.6), "F.Fab", size=0.8, thickness=0.12)
    fp.courtyard(HOLD_SPAN / 2 + 0.25, max(-TERM_BACK, BUTTON_TIP) + 0.25)
    fp.model(f"{MODELS}/Alps_SKRTLAE010.wrl")
    return fp


# --------------------------------------------------------------------------
# Unpopulated pin headers: a straight row of holes for a 2.54 mm pin header
# Hole and pad as in KiCad's PinHeader_1xNN_P2.54mm_Vertical: 1.0 mm hole, 1.7 mm pad.
# (Revision 2.0 uses none: the serial port is on standard test pads, and the sensor-side header is gone.)
# --------------------------------------------------------------------------
def header(pins: int) -> Footprint:
    PITCH, HOLE, PAD = 2.54, 1.0, 1.7
    fp = Footprint(
        f"PinHeader_1x{pins:02d}_P2.54mm_NotFitted",
        f"{pins} holes for a 2.54 mm pin header, not populated",
        f"pin header 1x{pins:02d} 2.54mm",
        ref_at=(0, -2.3), value_at=(0, 2.4),
        attr=("through_hole", "exclude_from_pos_files", "exclude_from_bom", "dnp"))
    half = (pins - 1) / 2 * PITCH
    for i in range(pins):
        fp.hole(i + 1, round(i * PITCH - half, 3), 0, PAD, HOLE)
    fp.rect(-half - PITCH / 2, -PITCH / 2, half + PITCH / 2, PITCH / 2, "F.Fab", FAB_W)
    fp.text("${REFERENCE}", (0, 0), "F.Fab", size=0.8, thickness=0.12)
    # The courtyard is the envelope of the pads, not of a fitted header: the board is made
    # with the holes empty.
    fp.courtyard(half + PAD / 2 + 0.1, PAD / 2 + 0.1)
    return fp


FOOTPRINTS = (esp32_c6_wroom_1, sgp41, bmp580, led_19_337, kinghelm_fpc_24, alps_skrtlae010)


def main():
    PRETTY.mkdir(parents=True, exist_ok=True)
    for build in FOOTPRINTS:
        fp = build()
        fp.write()
        print(f"{fp.name}: {len(fp.pad_numbers)} pads ({', '.join(sorted(set(fp.pad_numbers), key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else 0, s)))})")
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

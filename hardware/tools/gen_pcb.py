#!/usr/bin/env python3
"""Create the ClimaSense revision 1.0 board: outline, slots, part placement, nets.

This must run with the Python that ships with KiCad (it needs the `pcbnew`
module):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/gen_pcb.py

It reads build/netlist.net (written by check_schematic.py), loads every
footprint, assigns the nets to the pads, places the parts and routes the board
(route_board.py; pass --no-route to skip that). It overwrites
hardware/climasense.kicad_pcb, so do not re-run it once the board has been
edited by hand in KiCad.

Board coordinates below are millimetres from the top-left board corner,
x to the right, y down, seen from the component side, with the board in
landscape (antenna on the left, sensors on the right).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:  # keep KiCad's debug alerts from popping up as dialogs
    import wx
    wx.DisableAsserts()
except Exception:
    pass

import pcbnew
from pcbnew import FromMM, VECTOR2I

HW = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kisch import find, first, parse  # noqa: E402

KICAD_FOOTPRINTS = Path(r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
PROJECT_FOOTPRINTS = {"climasense": HW / "lib" / "climasense.pretty"}
# KiCad's footprints for these parts name a 3D model that KiCad does not ship. They get the
# project's own model instead (written by gen_models.py), so that the 3D view shows every part.
PROJECT_MODELS = {
    "SW_Push_1P1T_XKB_TS-1187A": "SW_Push_XKB_TS-1187A",
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12": "USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    "Sensirion_SCD4x-1EP_10.1x10.1mm_P1.25mm_EP4.8x4.8mm": "Sensirion_SCD4x",
    "Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad": "Sensirion_SHT4x",
}
BOARD_FILE = HW / "climasense.kicad_pcb"
NETLIST = HW / "build" / "netlist.net"
KICAD_CLI = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"

# --------------------------------------------------------------------------
# Board geometry
# --------------------------------------------------------------------------
ORIGIN = (100.0, 60.0)        # where the board's top-left corner sits on the KiCad sheet
W, H = 75.0, 34.0             # board size, landscape

# The board hangs on a wall in landscape: antenna to the left, USB cable down, so the top
# edge of this drawing is up. Zones, left to right:
#   0.0 - 26.0   ESP32 module turned 90 degrees, antenna at the left edge
#   26.5 - 48.0  USB-C on the bottom edge, power, buttons, Qwiic on the top edge
#   48.0 - 49.5  milled slot (three bridges)
#   49.5 - 75.0  sensor island. The two warm sensors (SCD41, SGP41) sit at the top, so
#                 their heat rises away; the SHT45 sits below them, on a tongue at the right
#                 edge, with nothing underneath it. The BMP580 is lower still, but far to
#                 the left, and gives off practically no heat
SLOT_X = (48.0, 49.5)
SLOTS_Y = ((3.0, 14.5), (19.5, 31.0))            # bridges remain at 0-3, 14.5-19.5 and 31-34

# SHT45 tongue: x 66-75, y 15.5-25.5. An L-shaped notch above and to its left and a
# straight notch below cut it free; a 4 mm neck at its lower-left corner (the side away
# from the CO2 sensor) holds it and carries its four tracks. Board outline along the
# right edge, top to bottom:
TONGUE_OUTLINE = ((W, 14.0), (64.5, 14.0), (64.5, 21.5), (66.0, 21.5), (66.0, 15.5), (W, 15.5),
                  (W, 25.5), (66.0, 25.5), (66.0, 27.0), (W, 27.0))
TONGUE_CUTOUTS = ((64.5, 14.0, W + 9, 15.5), (64.5, 14.0, 66.0, 21.5), (66.0, 25.5, W + 9, 27.0))
TONGUE_AREA = (63.2, 13.0, W, 28.0)              # only thin tracks in here
TONGUE_NECK_X = (64.5, 66.0)
# top to bottom in the order the tracks reach the sensor: ground goes round above it,
# the two I2C lines straight in, the supply round below it - so nothing has to cross
TONGUE_NECK_TRACKS = (("GND", 22.4), ("/I2C_SDA", 23.0), ("/I2C_SCL", 23.6), ("+3V3_SENS", 24.2))

MOUNTING_HOLES = ((3.5, 3.5), (3.5, 30.5), (71.5, 3.5), (71.5, 30.5))   # M3, in the corners

MODULE = (13.05, 17.0)         # ESP32 module centre; its antenna end is 0.3 mm inside the left edge
ROW_BOTTOM, ROW_TOP = 25.75, 8.25   # y of the two pad rows of the turned module


def pin_x(pin: int) -> float:
    """Board x of an ESP32 module pad. Pins 1-14 run left to right along the
    bottom row, pins 28 down to 15 run left to right along the top row."""
    col = pin - 1 if pin <= 14 else 28 - pin
    return round(MODULE[0] - 5.26 + col * 1.27, 3)


# ref: (x, y, rotation in degrees counter-clockwise)
PLACEMENT = {
    # --- MCU ---------------------------------------------------------------
    "U4": (*MODULE, 90),                     # module, antenna at the left edge
    # The two capacitors hang below the 3V3 pin with their supply pads on one vertical
    # line; the supply pad of the 10 uF is level with those of R6 and R8, so the supply
    # trunk runs through all three pad centres in one straight line.
    "C5": (8.95, 29.2, 180),                 # 10 uF at the 3V3 pin
    "C6": (9.42, 31.6, 180),                 # 100 nF
    "R6": (pin_x(3) + 1.2, 28.7, 90),        # EN pull-up
    "C7": (pin_x(3) + 1.2, 31.1, 90),        # EN capacitor
    "R8": (pin_x(10), 28.7, 90),             # IO8 pull-up
    # The three LED resistors stand in the order of the LED's cathode pads above them
    # (blue, red, green), each between its pad and its module pin.
    "R9": (pin_x(20), 5.4, 90),              # LED red
    "R10": (pin_x(19), 5.4, 90),             # LED green
    "R11": (pin_x(21), 5.4, 90),             # LED blue
    "D1": (pin_x(20), 2.1, 90),              # status LED
    "R7": (pin_x(15), 5.4, 270),             # BOOT pull-up, its signal pad towards the pin
    "SW2": (29.6, 4.5, 90),                  # BOOT / USER
    "SW1": (29.6, 13.5, 90),                 # RESET
    # --- USB input ---------------------------------------------------------
    # x ends in .05 so that the connector's pads, which sit on quarter millimetres, fall
    # on the 0.1 mm routing grid and their tracks leave them exactly centred
    "J1": (33.05, 30.8, 0),      # USB-C, opening to the bottom edge
    # The CC resistors sit straight above their connector pads and the ESD part straight
    # above the data pads, so every USB track can leave the connector without crossing.
    "U1": (32.5, 21.2, 90),      # ESD protection
    "R1": (31.8, 24.5, 90),      # CC1, centred over pad A5
    "R2": (34.8, 24.5, 90),      # CC2, centred over pad B5
    "F1": (38.9, 21.95, 90),     # fuse
    # --- regulators --------------------------------------------------------
    # The buck converter is turned so that its switch pin faces the inductor above it.
    # The input capacitor sits on its left as in TI's layout example: its supply pad
    # level with the converter's input pin, its ground pad below (see PREROUTED).
    "C1": (33.9, 16.4, 270),     # buck input
    "U2": (36.0, 16.4, 270),     # buck converter
    "L1": (36.0, 12.5, 90),      # inductor, centred over the switch pin
    "C2": (35.05, 9.0, 180),     # buck output, its supply pad centred over the inductor
    "R3": (38.0, 14.9, 270),     # feedback top
    "R4": (38.0, 17.3, 270),     # feedback bottom
    # SENS_EN pull-up: its supply pad on the 3.3 V line that runs down to the feedback
    # divider, its signal pad on the SENS_EN track that comes down beside it.
    "R5": (38.48, 13.2, 0),
    # The regulator's capacitors stand in line with its pins: input below the input and
    # ground pins, output above the output pin.
    "C3": (40.68, 18.6, 0),      # LDO input
    "U3": (41.2, 15.7, 90),      # sensor LDO
    "C4": (40.68, 12.8, 0),      # LDO output
    # --- I2C / Qwiic -------------------------------------------------------
    # --- Qwiic: connector, its own regulator, its pull-ups ------------------
    # Everything hangs on one vertical line below the connector's supply pin (x = 44.0):
    # pull-up, output capacitor, regulator output. The pull-ups lie directly below the
    # connector pads they serve.
    "J2": (43.5, 3.3, 180),      # Qwiic, opening to the top edge; pads SCL, SDA, 3V3, GND from the left
    "R17": (41.49, 7.3, 0),      # SCL pull-up: signal pad below the SCL pad
    "R16": (43.5, 7.3, 180),     # SDA pull-up: between the SDA pad and the supply pad
    "C16": (44.48, 8.6, 0),      # regulator output, on the supply line
    "U9": (44.95, 11.5, 90),     # Qwiic regulator, output pin on the supply line
    "C15": (44.48, 14.45, 0),    # regulator input, below the input and ground pins
    "R15": (42.3, 12.01, 270),   # enable pull-down, left of the regulator, its signal pad on the enable track
    # Both pull-ups hang from the sensor supply where it runs to the bridge (y = 16.1):
    # supply pad on that line, signal pad below it.
    "R12": (43.5, 16.61, 270),   # SDA pull-up
    "R13": (44.7, 16.61, 270),   # SCL pull-up
    # --- sensor island -----------------------------------------------------
    "U6": (57.0, 7.5, 0),        # SCD41, at the top
    # Both capacitors are centred on the pair of pins they serve (ground 6 / supply 7 at
    # the bottom, ground 20 / emitter supply 19 at the top).
    "C9": (55.125, 14.6, 180),   # 10 uF below pins 6 and 7
    "C10": (55.125, 1.4, 180),   # 100 nF above pins 20 and 19
    "U7": (66.0, 10.0, 0),       # SGP41, next to the SCD41
    # Heater supply capacitor and filter resistor on the right, one above the other, so that
    # their 3.3 V pads are neighbours.
    "C12": (69.6, 8.6, 0),       # heater supply capacitor
    "R14": (69.6, 10.0, 0),      # filter resistor
    # The filter capacitor stands on the other side, in the gap towards the SCD41, right
    # beside the supply pin (1) and the ground pin (2) it works for.
    "C11": (63.3, 9.68, 270),
    "U8": (55.05, 25.0, 0),      # BMP580; .05 for the same reason as the USB connector
    "C13": (58.0, 25.7, 0),
    "C14": (58.0, 24.3, 0),
    "U5": (71.8, 19.0, 0),       # SHT45 on its tongue, below the two warm sensors
    "C8": (74.0, 19.0, 90),      # beyond the sensor, level with its supply and ground pads
}

# The board hangs with the USB cable down. Arrow on the silkscreen, right of the USB connector:
# x, y of the tip, length of the head, y of the tail. "UP" is printed below the tail, in the
# size and on the line of the board name.
UP_ARROW = (43.5, 28.0, 0.9, 30.4)

# text, x, y, height - each button label sits directly below its button
SILK_LABELS = (
    ("ClimaSense Rev 1.0", 59.5, 31.6, 1.0),   # numbering: see "Revision naming" in docs/decisions.md
    ("BOOT", 29.6, 9.0, 0.8),
    ("RESET", 29.6, 17.95, 0.8),
    ("QWIIC", 37.3, 3.3, 0.8),
    # sensor names: below the part, like the button labels. The SCD41's stands right of its
    # 10 uF capacitor. The SGP41's is above: below it there is a via and then the cut-out.
    ("SCD41", 59.4, 13.9, 0.8),
    ("SGP41", 66.0, 7.6, 0.8),
    ("BMP580", 55.05, 27.1, 0.8),
    ("SHT45", 71.8, 21.1, 0.8),
)

POWER_NETS = ("GND", "VBUS", "+5V", "+3V3", "+3V3_SENS", "+3V3_QWIIC")
# Push buttons have two legs per terminal, joined inside the part. KiCad is told so, and
# the router does not draw a track between them: that track would wall off the space
# under the button, which other tracks need.
INTERNALLY_JOINED = ("SW1", "SW2")

# --------------------------------------------------------------------------
# Tracks drawn by hand
# --------------------------------------------------------------------------
# The router finds legal paths, not good ones. These few connections matter too much
# to leave to it. Each group joins the listed pads of one net on the top layer; the
# tracks are (width, points), points on the 0.1 mm grid, segments at 0/45/90 degrees.
# KiCad's rule check verifies clearances and that the pads really end up connected.
PREROUTED = (
    # Buck converter, following TI's layout example for the TPS62A01 (datasheet fig. 8-24).
    # Top row of U2 from the left: input, switch, ground. Bottom row: enable, feedback, n.c.
    dict(net="+5V", pads=("F1.2", "C1.1", "U2.3", "U2.4"), tracks=(
        (0.4, ((33.9, 15.7), (35.4, 15.7))),                     # input capacitor straight into the input pin
        (0.4, ((38.9, 20.5), (36.8, 18.4), (32.9, 18.4), (32.5, 18.0), (32.5, 15.9), (32.9, 15.5),
               (33.9, 15.5))),                                   # feed from the fuse, round the capacitor
        (0.2, ((35.5, 17.1), (35.5, 18.4))),                     # enable pin onto the feed (no current)
    )),
    dict(net="GND", pads=("U2.1", "C1.2"), tracks=(
        # ground pin to the capacitor: between the pad rows, then into the middle of the pad's edge
        (0.3, ((36.5, 15.7), (36.5, 16.2), (36.3, 16.4), (35.2, 16.4), (35.0, 16.6), (35.0, 16.9), (34.6, 17.3),
               (33.9, 17.3))),
    )),
    # feedback: out below the pin, round the unused pin 6, into the divider from its left;
    # short, and on the far side of the converter from the switch node
    dict(net="Net-(U2-FB)", pads=("U2.5", "R4.1", "R3.2"), tracks=(
        (0.2, ((36.0, 17.1), (36.0, 17.6), (36.2, 17.8), (37.0, 17.8), (37.3, 17.5), (37.3, 17.1), (37.6, 16.8),
               (38.0, 16.8))),
        (0.2, ((38.0, 16.8), (38.0, 15.4))),
    )),
    # switch pin, inductor and output capacitor stand in one line above the converter
    dict(net="Net-(U2-SW)", pads=("U2.2", "L1.1"), tracks=(
        (0.3, ((36.0, 15.7), (36.0, 13.6))),                     # switch node, as wide as the pin allows
    )),
    dict(net="+3V3", pads=("L1.2", "C2.1"), tracks=(
        (0.6, ((36.0, 11.4), (36.0, 9.0))),                      # inductor straight into the output capacitor
    )),
    # SCD41: its datasheet wants the two supply pins joined close to the sensor. One track
    # runs from the 10 uF capacitor up through the supply pin, on under the package between
    # the centre pad and the unused pads on the right, to the emitter supply pin and its
    # 100 nF capacitor. It follows the pins' centre lines, which are off the grid.
    dict(net="+3V3_SENS", pads=("C9.1", "U6.7", "U6.19", "C10.1"), tracks=(
        (0.4, ((55.75, 14.6), (55.75, 10.5), (55.95, 10.3), (59.6, 10.3), (59.8, 10.1), (59.8, 4.9), (59.6, 4.7),
               (55.95, 4.7), (55.75, 4.5), (55.75, 3.3))),
        (0.3, ((55.75, 3.3), (55.75, 1.4))),
    )),
    dict(net="GND", pads=("U6.6", "C9.2"), tracks=(
        (0.4, ((54.5, 11.7), (54.5, 14.6))),                     # ground pin straight down into the 10 uF
    )),
    dict(net="GND", pads=("U6.20", "C10.2"), tracks=(
        (0.3, ((54.5, 3.3), (54.5, 1.4))),                       # ground pin straight up into the 100 nF
    )),
    # SGP41 filter capacitor: straight across into the supply pin and the ground pin
    dict(net="SGP_VDD", pads=("C11.1", "U7.1"), tracks=(
        (0.3, ((63.3, 9.2), (64.8, 9.2))),
    )),
    dict(net="GND", pads=("C11.2", "U7.2"), tracks=(
        (0.3, ((63.3, 10.2), (63.9, 10.2), (64.1, 10.0), (64.8, 10.0))),
    )),
    # SHT45: its capacitor sits beyond the sensor, level with the two supply pads. The
    # links start at the outer end of the pads, clear of the no-track area under the part.
    dict(net="+3V3_SENS", pads=("U5.3", "C8.1"), tracks=(
        (0.2, ((72.7, 19.4), (74.0, 19.4))),
    )),
    dict(net="GND", pads=("U5.4", "C8.2"), tracks=(
        (0.2, ((72.7, 18.6), (74.0, 18.6))),
    )),
    # Qwiic: the supply runs in one line from the regulator's output up through the output
    # capacitor and the SDA pull-up into the connector's supply pad, and on over the top of
    # the connector's pads to the SCL pull-up. Each signal pad is joined straight down to
    # its pull-up; the module's tracks arrive from below.
    dict(net="+3V3_QWIIC", pads=("U9.5", "C16.1", "R16.1", "J2.2", "R17.1"), tracks=(
        (0.4, ((44.0, 10.4), (44.0, 5.3))),
        (0.2, ((44.0, 5.3), (44.0, 3.9), (43.8, 3.7), (41.2, 3.7), (41.0, 3.9), (41.0, 7.3))),
    )),
    # The three Qwiic signals run side by side from the module's corner pins to the
    # connector block without changing layer: up past the BOOT pull-up, under the BOOT
    # button between its pad rows, down in front of the connector, and into the pull-ups
    # from below. Left to the router they dived under the 3.3 V branch and the BOOT track.
    dict(net="QWIIC_SCL", pads=("U4.18", "R17.2", "J2.4"), tracks=(
        (0.2, ((20.5, 8.2), (20.5, 3.7), (21.0, 3.2), (39.2, 3.2), (40.2, 4.2), (40.2, 7.6), (40.6, 8.0), (42.0, 8.0),
               (42.0, 7.3))),
        (0.2, ((42.0, 7.3), (42.0, 5.3))),
    )),
    dict(net="QWIIC_SDA", pads=("U4.17", "R16.2", "J2.3"), tracks=(
        (0.2, ((21.8, 8.2), (21.8, 4.2), (22.3, 3.7), (38.2, 3.7), (39.7, 5.2), (39.7, 8.1), (40.1, 8.5), (43.0, 8.5),
               (43.0, 7.3))),
        (0.2, ((43.0, 7.3), (43.0, 5.3))),
    )),
    # SENS_EN shares that run (it comes from the fourth corner pin) and then drops down
    # between the buck converter and the sensor regulator to its pull-up.
    dict(net="SENS_EN", pads=("U4.16", "R5.2"), tracks=(
        (0.2, ((23.0, 8.2), (23.0, 4.7), (23.5, 4.2), (37.0, 4.2), (39.0, 6.2), (39.0, 13.2))),
    )),
    dict(net="+3V3", pads=("R5.1", "R3.1"), tracks=(
        (0.2, ((38.0, 13.2), (38.0, 14.4))),
    )),
    # Qwiic enable: pull-down and regulator pin joined above the regulator; the track from
    # the module (pin 12, on the far side) is left to the router.
    dict(net="QWIIC_EN", pads=("R15.1", "U9.3"), tracks=(
        (0.2, ((42.3, 11.5), (45.9, 11.5), (45.9, 12.6))),
    )),
    # ESP32 supply pin to its two capacitors, as wide as the pin
    dict(net="+3V3", pads=("U4.2", "C5.1", "C6.1"), tracks=(
        (0.6, ((9.1, 25.8), (9.1, 28.4), (9.9, 29.2))),
        (0.4, ((9.9, 29.2), (9.9, 31.6))),
    )),
)
# The supply from the buck converter's output capacitor to the ESP32's capacitor is
# routed before any signal, 0.6 mm wide where that fits.
# It passes through the centres of two pull-up resistors' supply pads on its way.
# It starts at the inductor's output pad, where the output capacitor is attached too.
TRUNKS = (("L1.2", "R8.1"), ("R8.1", "R6.1"), ("R6.1", "C5.1"))
# No tracks on the bottom layer under the buck converter: its ground stays unbroken.
BUCK_AREA = (33.0, 8.2, 38.6, 18.2)


def P(x, y):
    return VECTOR2I(FromMM(ORIGIN[0] + x), FromMM(ORIGIN[1] + y))


def edge(board, pts, closed=True):
    pts = list(pts) + ([pts[0]] if closed else [])
    for a, b in zip(pts, pts[1:]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(*a))
        s.SetEnd(P(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(FromMM(0.1))
        board.Add(s)


def load_footprint(lib_id):
    lib, name = lib_id.split(":", 1)
    folder = PROJECT_FOOTPRINTS.get(lib, KICAD_FOOTPRINTS / f"{lib}.pretty")
    fp = pcbnew.FootprintLoad(str(folder), name)
    if fp is None:
        raise SystemExit(f"footprint {lib_id} not found in {folder}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    if name in PROJECT_MODELS:
        model = pcbnew.FP_3DMODEL()
        model.m_Filename = "${KIPRJMOD}/lib/climasense.3dshapes/" + PROJECT_MODELS[name] + ".wrl"
        fp.Models().clear()
        fp.Add3DModel(model)
    return fp


def main():
    if not NETLIST.exists():
        raise SystemExit("build/netlist.net missing - run check_schematic.py first")
    net = parse(NETLIST.read_text(encoding="utf-8"))

    if BOARD_FILE.exists():
        BOARD_FILE.unlink()
    board = pcbnew.NewBoard(str(BOARD_FILE))
    board.SetCopperLayerCount(2)

    # --- design rules: JLCPCB standard 2-layer capabilities with margin -----
    ds = board.GetDesignSettings()
    ds.m_MinClearance = FromMM(0.15)
    ds.m_TrackMinWidth = FromMM(0.15)
    ds.m_ViasMinSize = FromMM(0.5)
    ds.m_ViasMinAnnularWidth = FromMM(0.1)
    ds.m_MinThroughDrill = FromMM(0.3)
    ds.m_HoleClearance = FromMM(0.25)
    ds.m_HoleToHoleMin = FromMM(0.5)
    ds.m_CopperEdgeClearance = FromMM(0.3)
    ds.m_SilkClearance = FromMM(0.1)
    ds.SetBoardThickness(FromMM(1.6))
    ds.m_TentViasFront = True       # vias covered by solder mask
    ds.m_TentViasBack = True

    net_settings = ds.m_NetSettings
    default = net_settings.GetDefaultNetclass()
    default.SetClearance(FromMM(0.15))
    default.SetTrackWidth(FromMM(0.2))
    default.SetViaDiameter(FromMM(0.6))
    default.SetViaDrill(FromMM(0.3))
    power = pcbnew.NETCLASS("Power")
    power.SetClearance(FromMM(0.15))
    power.SetTrackWidth(FromMM(0.4))
    power.SetViaDiameter(FromMM(0.6))
    power.SetViaDrill(FromMM(0.3))
    net_settings.SetNetclass("Power", power)
    for name in POWER_NETS:
        net_settings.SetNetclassPatternAssignment(name, "Power")

    # --- outline, with the two notches that free the SHT45 tongue -----------
    edge(board, [(0, 0), (W, 0), *TONGUE_OUTLINE, (W, H), (0, H)])
    for y1, y2 in SLOTS_Y:
        edge(board, [(SLOT_X[0], y1), (SLOT_X[1], y1), (SLOT_X[1], y2), (SLOT_X[0], y2)])

    # --- nets --------------------------------------------------------------
    nets = {}
    pad_net = {}
    for n in find(first(net, "nets"), "net"):
        name = first(n, "name")[1]
        item = pcbnew.NETINFO_ITEM(board, name)
        board.Add(item)
        nets[name] = item
        for node in find(n, "node"):
            pad_net[(first(node, "ref")[1], first(node, "pin")[1])] = item

    # --- footprints --------------------------------------------------------
    placed = 0
    for comp in find(first(net, "components"), "comp"):
        ref = first(comp, "ref")[1]
        if ref not in PLACEMENT:
            raise SystemExit(f"no placement for {ref}")
        x, y, rot = PLACEMENT[ref]
        fp = load_footprint(first(comp, "footprint")[1])
        fp.SetReference(ref)
        fp.SetValue(first(comp, "value")[1])
        fp.SetPosition(P(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetPath(pcbnew.KIID_PATH("/" + first(comp, "tstamps")[1]))
        fp.SetSheetname("/")
        fp.SetSheetfile("climasense.kicad_sch")
        fields = first(comp, "fields")
        for f in (find(fields, "field") if fields else []):
            name = first(f, "name")[1]
            if name != "Footprint" and len(f) > 2:
                fp.SetField(name, f[2].replace('\\"', '"'))
        # reference designators stay on the fabrication layer; the silkscreen gets a few labels later
        for fld in fp.GetFields():
            if not fld.IsValue():
                fld.SetVisible(False)
        for pad in fp.Pads():
            item = pad_net.get((ref, pad.GetNumber()))
            if item is not None:
                pad.SetNet(item)
        if ref in INTERNALLY_JOINED:
            fp.SetDuplicatePadNumbersAreJumpers(True)
        board.Add(fp)
        placed += 1
    missing = set(PLACEMENT) - {first(c, "ref")[1] for c in find(first(net, "components"), "comp")}
    if missing:
        raise SystemExit(f"placement lists parts that are not in the schematic: {sorted(missing)}")

    # --- mounting holes (board only, not in the schematic) ------------------
    for i, (x, y) in enumerate(MOUNTING_HOLES, 1):
        fp = load_footprint("MountingHole:MountingHole_3.2mm_M3")
        fp.SetReference(f"H{i}")
        fp.SetValue("M3")
        fp.SetPosition(P(x, y))
        fp.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        fp.Reference().SetVisible(False)
        board.Add(fp)

    # --- silkscreen labels ---------------------------------------------------
    # Reference designators are not printed (see above); these few labels are.
    for text, x, y, size in SILK_LABELS:
        label = pcbnew.PCB_TEXT(board)
        label.SetText(text)
        label.SetPosition(P(x, y))
        label.SetLayer(pcbnew.F_SilkS)
        label.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
        label.SetTextThickness(FromMM(0.15))
        board.Add(label)

    # Which way up the board hangs: an arrow towards the top edge with "UP" under it.
    x, tip, head, tail = UP_ARROW
    shaft = pcbnew.PCB_SHAPE(board)
    shaft.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shaft.SetStart(P(x, tip + head))
    shaft.SetEnd(P(x, tail))
    shaft.SetLayer(pcbnew.F_SilkS)
    shaft.SetWidth(FromMM(0.25))
    board.Add(shaft)
    arrowhead = pcbnew.PCB_SHAPE(board)
    arrowhead.SetShape(pcbnew.SHAPE_T_POLY)
    arrowhead.SetPolyPoints([P(x, tip), P(x - 0.6 * head, tip + head), P(x + 0.6 * head, tip + head)])
    arrowhead.SetFilled(True)
    arrowhead.SetLayer(pcbnew.F_SilkS)
    arrowhead.SetWidth(FromMM(0.1))
    board.Add(arrowhead)
    up = pcbnew.PCB_TEXT(board)
    up.SetText("UP")
    up.SetPosition(P(x, tail + 1.2))
    up.SetLayer(pcbnew.F_SilkS)
    up.SetTextSize(VECTOR2I(FromMM(1.0), FromMM(1.0)))
    up.SetTextThickness(FromMM(0.15))
    board.Add(up)

    failures = []
    if "--no-route" not in sys.argv[1:]:
        import route_board
        # Order on the bridge, top to bottom, and how far each track runs on into the island.
        # Ground and supply come first because they turn up towards the SCD41 and its
        # capacitor; the signals pass below them. The ends are staggered so that each track
        # can leave at 45 degrees without having to cross its neighbour.
        bridge = (("GND", 15.3, 1.1), ("+3V3_SENS", 16.1, 1.7), ("/I2C_SCL", 16.9, 2.3), ("/I2C_SDA", 17.7, 1.7),
                  ("/BMP_INT", 18.5, 1.1))
        failures = route_board.run(board, ORIGIN, dict(
            W=W, H=H,
            cutouts=[(SLOT_X[0], y1, SLOT_X[1], y2) for y1, y2 in SLOTS_Y] + list(TONGUE_CUTOUTS),
            antenna_x=6.9,
            module_inner=(MODULE[0] - 12.75, ROW_TOP + 1.05, MODULE[0] + 12.75, ROW_BOTTOM - 1.05),
            module_ref="U4", module_epad="29",
            holes=MOUNTING_HOLES, hole_keepout=3.3,
            bridge_x=SLOT_X, bridge_y={name: y for name, y, _ in bridge},
            fixed_tracks=[(name, SLOT_X[0] - 1.8, SLOT_X[1] + reach, y) for name, y, reach in bridge] + [
                # staggered on the sensor's side for the same reason
                (name, TONGUE_NECK_X[0] - 0.9, TONGUE_NECK_X[1] + 0.9 + 0.6 * k, y)
                for k, (name, y) in enumerate(TONGUE_NECK_TRACKS)],
            usb_body=(PLACEMENT["J1"][0] - 4.6, PLACEMENT["J1"][1] - 3.1, PLACEMENT["J1"][0] + 4.6, H),
            thin_only=TONGUE_AREA,
            fixed_only=[(SLOT_X[0] - 0.3, 0, SLOT_X[1] + 0.3, H), (TONGUE_NECK_X[0], 21.5, TONGUE_NECK_X[1], 25.5)],
            fanout={"U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9", "J1", "J2", "D1"},
            prerouted=[{**g, "net": "/" + g["net"] if "/" + g["net"] in nets else g["net"]} for g in PREROUTED],
            trunks=TRUNKS, reserve_bottom=[("GND", BUCK_AREA)], internally_joined=INTERNALLY_JOINED,
            # the strip below the module's bottom pad row is where its pins escape; the trunk stays out of it
            no_trunk=[(6.9, ROW_BOTTOM + 0.75, MODULE[0] + 14.2, ROW_BOTTOM + 2.55)],
            solid_pour_pads={"J1", "J2", "U1", "U2", "U3", "U9"},
            debug="--debug" in sys.argv[1:],
            attempts=next((int(x.split("=")[1]) for x in sys.argv[1:] if x.startswith("--attempts=")), 12),
        ))

    pcbnew.SaveBoard(str(BOARD_FILE), board)
    if "--no-route" not in sys.argv[1:]:
        # fill the ground pours with KiCad's own filler and store the result in the board
        subprocess.run([KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json",
                        "-o", str(HW / "build" / "drc.json"), str(BOARD_FILE)], check=True, capture_output=True)
    print(f"{placed} parts placed, {len(nets)} nets, board {W} x {H} mm -> {BOARD_FILE.name}")


if __name__ == "__main__":
    main()

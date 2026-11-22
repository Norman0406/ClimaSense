#!/usr/bin/env python3
"""Create the ClimaSense revision 2.0 board: outline, slots, part placement, nets.

Revision 2.0 is revision 1.0 with the sensor island moved right by DX and an e-paper
display added on the back (see the block "Revision 2.0" below and docs/hardware/rev-2.0.md).

This must run with the Python that ships with KiCad (it needs the `pcbnew`
module):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/rev-2.0/tools/gen_pcb.py

It reads build/netlist.net (written by check_schematic.py), loads every
footprint, assigns the nets to the pads, places the parts and routes the board
(route_board.py; pass --no-route to skip that). It overwrites
hardware/rev-2.0/climasense.kicad_pcb, so do not re-run it once the board has been
edited by hand in KiCad.

Options:
  --keep[=board]     reuse the copper of the previous board (default: the one about to be
                     overwritten) for every net whose pads did not move and whose hand-drawn
                     copper did not change; only the rest is routed. Ground is judged per pad.
  --reroute=A,B      with --keep: route these nets anew all the same.
  --seed=N           start order of the router (default ROUTE_SEED).
  --seeds=A-B        route with each of these seeds in parallel processes and keep the best
                     clean result (no open connection, audit_pcb.py passed, then no +3V3 track in the display
                     bundle, then fewest vias, then shortest tracks).
  --attempts=N       routing retries per seed.   --no-route: stop after placement.
  --out=file, --summary=file, --no-fill: used by --seeds for its worker processes.

Board coordinates below are millimetres from the top-left board corner,
x to the right, y down, seen from the component side, with the board in
landscape (antenna on the left, sensors on the right).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
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
    "SW_Push_1P1T_XKB_TS-1187A": "SW_Push_XKB_TS-1187A",     # (1.0's buttons)
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
    # Fallback serial port: three holes in the corner above the module's serial pins (TXD0 is
    # pin 25, RXD0 pin 24), clear of the antenna keep-out on the left and the LED on the right.
    # From the left: GND, TX, RX; TX stands straight above its module pin.
    "J3": (pin_x(25), 4.0, 0),
    # Test pads for a multimeter, each next to its supply: 5 V below the buck converter (label beside it); the others have theirs below:
    # 3.3 V between the module and the USB connector, sensor 3.3 V at the I2C pull-ups, and ground.
    "TP1": (36.0, 19.1, 0), "TP2": (27.6, 24.2, 0), "TP3": (44.6, 19.0, 0), "TP4": (44.6, 23.4, 0),
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
    # supply pad on that line, signal pad below it. (Revision 2.0 moves them, see below.)
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
# x, y of the tip, length of the head, y of the tail. "Up" is printed below the tail, in the
# size and on the line of the board name.
UP_ARROW = (43.5, 28.0, 0.9, 30.4)

# the board name and the "Up" under the arrow stand on one line, in one size
NAME_Y, NAME_SIZE = 32.2, 0.8
# text, x, y, height - each button label sits directly below its button
SILK_LABELS = (
    # numbering: see "Revision naming" in docs/decisions.md. In the strip below the module.
    ("ClimaSense Rev 2.0", 19.8, NAME_Y, NAME_SIZE),
    # (1.0's sensor header J4 and its labels are gone in revision 2.0)
    ("BOOT", 29.6, 9.0, 0.8),
    ("RESET", 29.6, 17.95, 0.8),
    ("QWIIC", 37.3, 3.3, 0.8),
    # the pins of the fallback serial port, each above its hole
    ("GND", 9.06, 2.3, 0.8),
    ("TX", 11.6, 2.3, 0.8),
    ("RX", 14.14, 2.3, 0.8),
    # the test pads, each below its pad (3VS: the sensors' 3.3 V)
    ("5V", 37.7, 19.1, 0.8),
    ("3V3", 27.6, 22.6, 0.8),
    ("3VS", 44.6, 20.7, 0.8),      # moved with TP3 in revision 2.0 (below)
    ("GND", 44.6, 25.1, 0.8),
    # sensor names: below the part, like the button labels. The SCD41's stands right of its
    # 10 uF capacitor. The SGP41's is above: below it there is a via and then the cut-out.
    ("SCD41", 59.4, 13.9, 0.8),
    ("SGP41", 66.0, 7.6, 0.8),
    ("BMP580", 55.05, 22.9, 0.8),
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
# to leave to it. Each group joins the listed pads of one net; the tracks are
# (width, points) on the top layer, points on the 0.1 mm grid, segments at 0/45/90
# degrees. (width, points, "bottom") puts a track on the bottom layer, and `vias` lists
# the vias such tracks end on. KiCad's rule check verifies clearances and that the pads
# really end up connected.
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
    # At the lower right corner of the centre pad it passes the sensor's vent ("thermal
    # relief hole", 0.25 mm, at 59.94 / 10.44). The datasheet keeps a circle of 0.6 mm round
    # that hole free (SCD4x datasheet v1.7, figure 4). The track is therefore thin there
    # and cuts the corner: its copper stays 0.38 mm from the centre of the hole.
    dict(net="+3V3_SENS", pads=("C9.1", "U6.7", "U6.19", "C10.1"), tracks=(
        (0.4, ((55.75, 14.6), (55.75, 10.5), (55.95, 10.3), (59.3, 10.3))),
        (0.2, ((59.3, 10.3), (59.4, 10.3), (59.8, 9.9), (59.8, 9.8))),
        (0.4, ((59.8, 9.8), (59.8, 4.9), (59.6, 4.7), (55.95, 4.7), (55.75, 4.5), (55.75, 3.3))),
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
    # USB data lines at the connector. It has two pads for each line, in the order D-, D+,
    # D-, D+ from the left, so one line has to change layer to join its pair, and nothing
    # may run on the top layer under the connector's metal shell. Both pairs are therefore
    # joined above the pads. D- stays on the top layer: a loop round the inner D+ pad, and
    # from the loop straight up into the protection part U1. D+ leaves that loop through a
    # via inside it. On the bottom layer one short link takes it to a second via, where the
    # track from the outer D+ pad ends, and another to a third via next to U1's D+ pin.
    # The router connects the ESP32 to this copper.
    dict(net="USB_DN", pads=("J1.B7", "J1.A7", "U1.3"), tracks=(
        (0.2, ((32.3, 26.8), (32.3, 25.8), (32.4, 25.7), (32.4, 24.7), (32.5, 24.6), (33.5, 24.6), (33.6, 24.7),
               (33.6, 25.6), (33.3, 25.9), (33.3, 26.8))),
        (0.2, ((33.4, 24.6), (33.4, 22.3))),
    )),
    dict(net="USB_DP", pads=("J1.A6", "J1.B6", "U1.1"), vias=((33.0, 25.3), (34.0, 23.8), (30.8, 22.8)), tracks=(
        (0.2, ((32.8, 26.8), (32.8, 25.6), (33.0, 25.4), (33.0, 25.3))),
        (0.2, ((33.8, 26.8), (33.8, 26.0), (34.0, 25.8), (34.0, 23.8))),
        (0.2, ((30.8, 22.8), (30.8, 22.7), (31.2, 22.3), (31.6, 22.3))),
        (0.2, ((33.0, 25.3), (33.0, 24.8), (34.0, 23.8)), "bottom"),
        (0.2, ((33.0, 24.8), (31.0, 22.8), (30.8, 22.8)), "bottom"),
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
# The same behind the USB connector. The ground vias of the protection part U1 and of the
# two configuration resistors sit in a pocket walled in by USB and supply tracks on the top
# layer. On the bottom layer the strip from those vias down past the connector's pads to its
# two rear shield legs stays ground (apart from the hand-drawn D+ link), so that pocket
# cannot be cut off from the rest of the ground. Without this the router has done exactly
# that: it reported the board as routed while KiCad counted two open ground connections.
USB_GROUND_AREAS = ((31.0, 22.6, 35.4, 26.0), (28.3, 26.0, 37.8, 28.8))
# (1.0 kept the bottom layer below the sensor regulator U3 ground as well; in revision 2.0 the
# regulator sits on the ground kept in the FPC area, see DISPLAY_GROUND_AREAS.)


# --------------------------------------------------------------------------
# Revision 2.0: a longer board with an e-paper panel on the back
# --------------------------------------------------------------------------
# Everything above is the 1.0 geometry. Revision 2.0 keeps the controller side as it was,
# moves the sensor island (everything from the 1.0 slot at x = 48 rightwards) by DX, and
# puts the display electronics into the gap. Seen from the component side (which faces the
# wall), the panel lies on the back over x = PANEL[0]..PANEL[2]; its FPC tail leaves the glass
# towards the sensor side, passes through FPC_SLOT, makes a U-turn back over the slot's edge
# and enters the connector J5 from the right. The sensor bus runs round the top or bottom end
# of FPC_SLOT and down to the bridge between FPC_SLOT and the sensor slot.
DX = 28.0
ISLAND_X = 48.0               # 1.0 coordinates at or right of this belong to the sensor island


def _sx(x: float) -> float:
    return round(x + DX, 3) if x >= ISLAND_X else x


def _shift_pts(pts):
    return tuple((_sx(x), y) for x, y in pts)


W = W + DX
SLOT_X = tuple(_sx(x) for x in SLOT_X)
TONGUE_OUTLINE = _shift_pts(TONGUE_OUTLINE)
TONGUE_CUTOUTS = tuple((_sx(a), b, _sx(c), d) for a, b, c, d in TONGUE_CUTOUTS)
TONGUE_AREA = (_sx(TONGUE_AREA[0]), TONGUE_AREA[1], _sx(TONGUE_AREA[2]), TONGUE_AREA[3])
TONGUE_NECK_X = tuple(_sx(x) for x in TONGUE_NECK_X)
MOUNTING_HOLES = _shift_pts(MOUNTING_HOLES)
PLACEMENT = {ref: (_sx(x), y, rot) for ref, (x, y, rot) in PLACEMENT.items()}
SILK_LABELS = tuple((text, _sx(x), y, *rest) for text, x, y, *rest in SILK_LABELS)


def _shift_group(g):
    if not all(x >= ISLAND_X for t in g["tracks"] for x, _ in t[1]):
        return g
    out = dict(g)
    out["tracks"] = tuple((t[0], _shift_pts(t[1]), *t[2:]) for t in g["tracks"])
    if "vias" in g:
        out["vias"] = _shift_pts(g["vias"])
    return out


PREROUTED = tuple(_shift_group(g) for g in PREROUTED)

# The panel (GDEY0213B74, 59.2 x 29.2 mm; specification page 7), on the back: x0, y0, x1, y1.
# Its left edge keeps 3.9 mm from the antenna keep-out (x = 6.9). Its tail is centred on the short
# edge (to 0.2 mm), 12.5 mm wide, 14.3 mm long, the last 6 mm stiffened.
# PANEL_X0 moved from 11.8 to 10.8 (2026-11-22, Norman): the glass edge sat only 0.8 mm from the
# FPC slot; it now keeps 1.8 mm, and J5 moved 1 mm towards the slot, so the tail's slack stays.
PANEL_X0 = 10.8
PANEL = (PANEL_X0, 2.4, PANEL_X0 + 59.2, 31.6)
PANEL_TAIL_Y = 2.4 + 8.15 + 12.5 / 2          # centre line of the tail
# Slot for the tail: 1.2 mm wide, 0.5 mm wider than the tail at each end, 1.8 mm from the glass.
FPC_SLOT = (71.8, PANEL_TAIL_Y - 6.75, 73.0, PANEL_TAIL_Y + 6.75)

# Display parts. J5 (24-pin, 0.5 mm, dual contact) turned so that its opening faces the slot.
# With the U-turn, the tail's pin 1 arrives at the connector's pin 24: the schematic maps the
# pins accordingly (gen_schematic.py, FPC_REVERSED). The connector's front edge sits about
# 5.8 mm from the slot, so that the 8 mm of flexible tail reach round the slot's edge and the
# stiffened end lies flat into the connector. To be checked with a paper print and a real panel.
# Footprint: Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF (gen_footprints.py), origin in the middle of
# its 4.90 mm deep housing, opening 2.45 mm in front of it; turned by 90 degrees the opening
# faces right, towards the slot, and pin 1 is at the bottom.
# 7.8 mm (decided 2026-11-22): with Kinghelm's insertion depth of 2.1 mm the tail needs about
# 10.2 mm from the glass edge to full insertion at 5.8 mm and had 4 mm to spare; at 7.8 mm about
# 2 mm remain for real bend radii and tolerances (too short would be fatal, some slack is fine).
# 6.8 mm (2026-11-22, Norman), together with the panel 1 mm further from the slot: the same
# slack, with the tail's run split more evenly between the back and the component side.
# To be confirmed with a 1:1 paper print and the real panel.
J5_FRONT_TO_SLOT = 6.8
J5_X = round(FPC_SLOT[0] - J5_FRONT_TO_SLOT - 4.90 / 2, 3)
PLACEMENT.update({
    "J5": (J5_X, PANEL_TAIL_Y, 90),
    # After the U-turn the panel's pin 1 is at the top: the boost pins (GDR, RESE) face the
    # upper half, the supply and driving-voltage pins (15-24) the lower half.
    # Boost converter and charge pump above, left of the connector, away from the antenna
    # (moved 0.7 mm left with J5 on 2026-11-22; the diodes also 0.8 mm up, so that the lines to
    # J5's pins 14-16 reach them straight from the left, clear of D4).
    "L2": (50.3, 4.0, 0),         # 47 uH, 4 x 4 mm
    "C25": (50.3, 7.6, 0),        # 4.7 uF at the inductor's input
    "Q1": (54.7, 4.6, 0),         # MOSFET: drain to the switch node, source to the sense resistor
    "R19": (56.9, 4.6, 90),       # 2.2 ohm sense resistor
    "R18": (54.7, 7.0, 0),        # 1 Mohm gate pull-down
    "C26": (50.3, 11.0, 0),       # 4.7 uF charge pump capacitor
    "D2": (55.1, 8.8, 0),         # switch node to VGH
    "D3": (55.1, 11.2, 0),        # charge pump to ground
    "D4": (55.1, 13.6, 0),        # VGL to the charge pump
    # the eight 1 uF capacitors of the supply and driving voltages in a row below the connector
    **{f"C{n}": (50.4 + 1.6 * i, 29.4, 270) for i, n in enumerate(range(17, 25))},
    # The sensor regulator moves to where the sensor bus turns up into the strip to the bridge,
    # below the FPC slot (1.0 had it next to the buck converter, about 30 mm further left): the
    # sensors' supply current then runs a few millimetres to the strip instead of the length of
    # the display area. The 5 V feed and SENS_EN travel instead. Turned by 270 degrees: input,
    # ground and enable along the top, output at the bottom right above the bus's supply run.
    # Its capacitors stand in line with its pins as before: input above, output below.
    "U3": (68.0, 28.4, 270),
    "C3": (68.475, 25.6, 180),    # LDO input: supply pad over the input pin, ground pad over the ground pin
    "C4": (68.475, 31.0, 180),    # LDO output: supply pad under the output pin
    "TP3": (71.0, 29.0, 0),       # test pad for the sensors' 3.3 V, right of the regulator
    "R5": (65.3, 28.4, 90),       # SENS_EN pull-up, next to the regulator's enable pin (1.0: by the buck converter)
})
POWER_NETS = POWER_NETS + ("/EPD_SW", "/EPD_RESE")
# Bottom-layer ground that no signal may cut. The sensor island's ground reaches the main pours
# only through the strip between the FPC slot and the sensor slot; the bottom layer of that
# strip, and of the FPC landing area between J5 and the slot round both ends of the slot, stays
# ground, so the sensor bus crosses there on the top layer. In the first generated board the bus
# ran on the bottom layer there and walled off pockets of the pours. The boost converter gets
# an unbroken ground under it, like the buck converter.
DISPLAY_GROUND_AREAS = ((66.7, 0.3, 75.9, 33.7),       # FPC landing area and the strip, full height
                        (57.8, 7.5, 66.7, 26.0),       # behind J5: its ground pins' vias land here
                        (48.0, 1.6, 57.6, 8.7),        # under the boost converter's switching loop
                        # Along the bottom edge below the module, to under the USB connector: tracks
                        # from the module's corner pins ran round the ESP32's capacitors on both layers
                        # and closed in the ground via of the EN capacitor C7.
                        (9.6, 29.8, 12.6, 33.7),        # (shrunk to a patch round C7's ground via)
                        # below the RESET switch's middle (ground) pad down to the buck converter's
                        # ground: its via was closed in on both layers in the first run with the switches
                        (35.2, 3.7, 36.8, 8.2))
# The sensor bus to the bridge, drawn by hand on the top layer: along the bottom edge below the
# display capacitors (nothing else runs there), then up the strip right of the FPC slot to the
# fixed tracks across the bridge. Left to the router, it crossed the display area diagonally and
# walled off pockets of the ground pours, and BMP_INT found no way through at all.
# name, x where it starts (left), x of the run up the strip, y along the bottom edge. The run
# that ends highest on the bridge turns up first, so that no two cross; 0.2 mm gaps, the supply
# 0.4 mm wide. The left ends are staggered like steps, the lowest run the longest, so that the
# router can reach each run's end from above (between parallel runs there is no room for a via).
SENSOR_BUS = (("+3V3_SENS", 44.0, 73.6, 31.9), ("/I2C_SCL", 42.4, 74.1, 32.4), ("/I2C_SDA", 40.8, 74.5, 32.8),
              ("/BMP_INT", 38.4, 74.9, 33.2))
SENSOR_BUS_BRIDGE_Y = {"+3V3_SENS": 16.1, "/I2C_SCL": 16.9, "/I2C_SDA": 17.7, "/BMP_INT": 18.5}   # as `bridge` below
SENSOR_BUS_FEEDS = tuple(
    dict(net=name, tracks=((0.4 if name == "+3V3_SENS" else 0.2,
                            ((x0, y), (x - 1.0, y), (x, y - 1.0), (x, SENSOR_BUS_BRIDGE_Y[name]))),))
    for name, x0, x, y in SENSOR_BUS)
# --- Buttons and LED along the top edge (decided 2026-11-22) ---------------------------------
# Both buttons become Alps SKRTLAE010 side-push switches with the button pointing up past the
# top edge, 8 mm apart, BOOT/USER nearer the module; the status LED moves up to the edge too.
# The switch's holding pads reach 0.3 mm beyond its body, so with the 0.3 mm copper-to-edge
# rule the guide-boss line sits 1.83 mm from the edge: the body stays 0.6 mm inside the edge and
# the button reaches about 0.2 mm past it. The case presses on it with a button of its own.
SWITCH_Y = 1.83
PLACEMENT.update({
    "SW2": (28.0, SWITCH_Y, 180),     # BOOT / USER
    "SW1": (36.0, SWITCH_Y, 180),     # RESET
    "D1": (PLACEMENT["D1"][0], 1.4, 90),   # its pads keep the 0.3 mm edge clearance
})
# The Qwiic lines and SENS_EN ran along y = 3.2-4.2 under 1.0's BOOT button; the new switches'
# terminal pads reach down to y = 3.6 there, and each switch's middle (ground) pad needs room
# below it for its via. SCL and SDA pass above the BOOT pull-up R7 as before, then drop below the
# switches; SENS_EN goes along y = 6.9, below R7.
_MOVED = {
    "QWIIC_SCL": dict(net="QWIIC_SCL", pads=("U4.18", "R17.2", "J2.4"), tracks=(
        (0.2, ((20.5, 8.2), (20.5, 4.4), (21.0, 3.9), (25.45, 3.9), (26.95, 5.4), (38.9, 5.4), (40.2, 6.7),
               (40.2, 7.6), (40.6, 8.0), (42.0, 8.0), (42.0, 7.3))),
        (0.2, ((42.0, 7.3), (42.0, 5.3))),
    )),
    "QWIIC_SDA": dict(net="QWIIC_SDA", pads=("U4.17", "R16.2", "J2.3"), tracks=(
        (0.2, ((21.8, 8.2), (21.8, 4.85), (22.3, 4.35), (25.0, 4.35), (26.5, 5.85), (38.2, 5.85), (39.7, 7.35),
               (39.7, 8.1), (40.1, 8.5), (43.0, 8.5), (43.0, 7.3))),
        (0.2, ((43.0, 7.3), (43.0, 5.3))),
    )),
    "SENS_EN": dict(net="SENS_EN", pads=("U4.16", "R5.2"), tracks=(
        (0.2, ((23.0, 8.2), (23.0, 7.4), (23.5, 6.9), (38.3, 6.9), (39.0, 7.6), (39.0, 13.2))),
    )),
}
PREROUTED = tuple(_MOVED.get(g["net"], g) for g in PREROUTED)
# Revision 2.0 (decided 2026-11-22): SENS_EN moved to IO10 on the module's lower row and its pull-up R5
# next to the regulator, so 1.0's hand-drawn SENS_EN run and R5's link to the feedback divider go.
PREROUTED = tuple(g for g in PREROUTED if g["net"] != "SENS_EN" and not (g["net"] == "+3V3" and "R5.1" in g["pads"]))
SILK_LABELS = tuple(lab for lab in SILK_LABELS if lab[0] not in ("BOOT", "RESET", "QWIIC")) + (
    ("BOOT", 28.0, 5.6, 0.8), ("RESET", 36.0, 5.6, 0.8), ("QWIIC", 39.5, 2.6, 0.8, 90))   # upright, between RESET and the Qwiic connector

SILK_LABELS = tuple(lab for lab in SILK_LABELS if lab[0] != "3VS") + (
    ("DISPLAY", J5_X + 5.5, 20.0, 0.8, 90), ("3VS", 71.2, 27.4, 0.8))
# The regulator's output joins the bus's supply run straight below it; the router does the rest.
PREROUTED = PREROUTED + (
    dict(net="+3V3_SENS", pads=("U3.5", "C4.1"), tracks=((0.4, ((68.95, 29.5), (68.95, 31.0))),)),
    # USB supply, as the router drew it on revision 1.0 (25 mOhm from the farther pad): the
    # farther supply pad (A4/B9, left) up past the CC resistor to the protection part's VBUS pin,
    # under the ESD part on the bottom layer to beside the fuse, and the nearer pad (A9/B4)
    # straight up into the same point. Nothing runs under the connector's shell (it starts at
    # y = 27.5); the bottom-layer link stays above the ground kept behind the connector. Left to
    # the router on revision 2.0 the farther pad took a 73 mm detour round the Qwiic connector.
    dict(net="VBUS", pads=("J1.A4", "J1.B9", "U1.5", "J1.A9", "J1.B4", "F1.1"), vias=((32.6, 19.0), (35.4, 22.1)),
         tracks=(
             (0.4, ((30.6, 26.75), (30.6, 24.7), (30.1, 24.2), (30.1, 19.6), (31.3, 18.4), (32.0, 18.4), (32.5, 18.9),
                    (32.5, 20.05))),
             (0.4, ((32.5, 19.0), (32.6, 19.0))),
             (0.4, ((32.6, 19.0), (32.9, 19.0), (35.4, 21.5), (35.4, 22.1)), "bottom"),
             (0.4, ((35.4, 22.1), (36.6, 23.3), (38.9, 23.3))),
             (0.4, ((35.5, 26.75), (35.5, 24.4), (36.6, 23.3))),
         )),
)

# The six display lines, drawn by hand from the module to J5 (revision 2.0). Their paths are the
# ones the router found for the clean board of 2026-11-22 (commit e8b8ee3, ROUTE_SEED 5), with the
# probe pads (1.0 mm, copper only) placed in line on top-layer sections, so that a pad adds no
# branch. Left to the router, a row of probe pads forced every display line into a detour and the
# board no longer routed. Left of J5 the three SPI lines run as a staircase (2026-11-22, Norman):
# CS straight at y 16.5 into its pin, SCK 1.2 mm below it (y 17.7) and SDI (MOSI) 1.2 mm below that
# (y 18.9), each rising to its pin after its pad; the pads sit on the lines 4.4 mm apart in x
# (SPI_PAD_X), so that each label fits to the right of its pad before the next pad begins, and SDI's
# label ends before J5's ground via. (Before, the three lines dipped
# in nested U shapes 1.5 mm lower, CS with a detour.) BUSY has its pad above the bundle, on its run down
# past C26; DC on its run down the right of J5's pad row, between two ground vias. RST has no pad. The
# pull-up R20 on CS sits on CS's run down from its via at x 40, its +3V3 pad towards the feedback divider
# (the router joins it).
# The CS, SCK and SDI labels are printed to the right of their pads, centred on the pad's height, in
# a staircase like the pads; DC's on its right too, BSY's below its pad (the diodes are close on its
# right).
SPI_PAD_X = (45.4, 49.8, 54.2)   # CS, SCK, SDI: 4.4 mm apart (2026-11-22, Norman), each label fits before the next pad
EPD_PADS = {"TP7": (SPI_PAD_X[0], 16.5), "TP5": (SPI_PAD_X[1], 17.7), "TP6": (SPI_PAD_X[2], 18.9), "TP8": (50.2, 13.3),
            "TP11": (60.9, 6.6)}
R20_AT = (39.49, 15.0)        # EPD_CS pull-up, horizontal: +3V3 pad at x 38.98, CS pad at x 40.0
EPD_LINES = (
    dict(net="EPD_SCK", pads=("U4.4", "TP5.1", "J5.12"), vias=((11.6, 26.9), (43.7, 17.1)), tracks=(
        (0.2, ((11.6, 25.8), (11.6, 26.9))),
        # under the module on the bottom layer, round the switches' boss holes, down to J5's row
        (0.2, ((11.6, 26.9), (15.4, 23.1), (15.4, 14.7), (26.7, 3.4), (29.8, 3.4), (32.3, 0.9), (34.3, 0.9),
               (34.8, 1.4), (34.8, 1.7), (34.9, 1.8), (37.1, 1.8), (37.2, 1.7), (37.2, 1.4), (37.7, 0.9),
               (38.5, 0.9), (38.9, 1.3), (38.9, 1.5), (43.7, 6.3), (43.7, 17.1)), "bottom"),
        (0.2, ((43.7, 17.1), (44.3, 17.7), (51.2, 17.7), (51.9, 17.0), (59.9, 17.0))),
    )),
    dict(net="EPD_MOSI", pads=("U4.5", "TP6.1", "J5.11"), vias=((22.4, 27.8), (33.8, 21.2)), tracks=(
        (0.2, ((12.9, 25.8), (12.9, 27.8), (13.3, 28.2), (18.2, 28.2), (18.4, 28.0), (18.4, 27.8), (18.6, 27.6),
               (19.8, 27.6), (19.9, 27.7), (19.9, 27.8), (20.3, 28.2), (22.0, 28.2), (22.4, 27.8))),
        (0.2, ((22.4, 27.8), (30.5, 19.7), (32.3, 19.7), (33.8, 21.2)), "bottom"),
        (0.2, ((33.8, 21.2), (33.9, 21.2), (34.2, 21.5), (40.1, 21.5), (42.7, 18.9), (54.8, 18.9), (56.2, 17.5),
               (59.9, 17.5))),
    )),
    dict(net="EPD_CS", pads=("U4.23", "R20.2", "TP7.1", "J5.13"),
         vias=((16.1, 6.8), (22.4, 6.8), (40.0, 10.4), (40.0, 13.0)), tracks=(
        (0.2, ((14.1, 8.2), (14.1, 7.4), (14.7, 6.8), (16.1, 6.8))),
        (0.2, ((16.1, 6.8), (22.4, 6.8)), "bottom"),
        (0.2, ((22.4, 6.8), (36.4, 6.8), (40.0, 10.4))),
        (0.2, ((40.0, 10.4), (40.0, 13.0)), "bottom"),
        (0.2, ((40.0, 13.0), (40.0, 16.0), (40.5, 16.5), (59.9, 16.5))),
    )),
    dict(net="EPD_RST", pads=("U4.16", "J5.15"), vias=((40.6, 11.8), (40.9, 13.0)), tracks=(
        (0.2, ((23.0, 8.2), (23.0, 7.4), (23.2, 7.2), (36.0, 7.2), (40.6, 11.8))),
        (0.2, ((40.6, 11.8), (40.9, 12.1), (40.9, 13.0)), "bottom"),
        (0.2, ((40.9, 13.0), (43.4, 15.5), (59.9, 15.5))),
    )),
    dict(net="EPD_BUSY", pads=("U4.26", "TP8.1", "J5.16"), tracks=(
        (0.2, ((10.3, 8.2), (10.3, 6.9), (11.4, 5.8), (14.0, 5.8), (16.3, 3.5), (25.7, 3.5), (26.8, 4.6), (37.1, 4.6),
               (38.4, 3.3), (44.7, 3.3), (45.6, 4.2), (45.6, 5.7), (48.5, 8.6), (48.8, 8.6), (50.2, 10.0), (50.2, 13.4),
               (51.8, 15.0), (59.9, 15.0))),
    )),
    dict(net="EPD_DC", pads=("U4.9", "TP11.1", "J5.14"), vias=((16.7, 27.6), (26.2, 17.3), (32.0, 7.8), (38.8, 2.7)),
         tracks=(
        (0.2, ((18.0, 25.8), (18.0, 27.2), (17.6, 27.6), (16.7, 27.6))),
        (0.2, ((16.7, 27.6), (16.7, 26.8), (26.2, 17.3)), "bottom"),
        (0.2, ((26.2, 17.3), (32.0, 11.5), (32.0, 7.8))),
        (0.2, ((32.0, 7.8), (32.0, 5.4), (34.8, 2.6), (37.1, 2.6), (37.2, 2.7), (38.8, 2.7)), "bottom"),
        # along the top edge over the boost converter, then down the right of J5's pad row into pin 14
        (0.2, ((38.8, 2.7), (47.1, 2.7), (47.2, 2.6), (47.2, 2.5), (47.9, 1.8), (57.8, 1.8), (60.9, 4.9), (60.9, 15.9),
               (60.8, 16.0), (59.9, 16.0))),
    )),
)
# The pocket closed in by RST above and CS below (its run down at x 40, its horizontal and its U) is
# kept ground on the top layer. Otherwise the router threads +3V3 through it between two vias,
# sandwiched between the two display lines.
EPD_POCKETS = ((40.25, 13.4, 41.0, 16.3), (41.0, 14.2, 41.8, 16.3), (41.8, 15.0, 42.6, 16.3),
               # between RST and CS, either side of CS's pad
               (42.6, 15.7, SPI_PAD_X[0] - 0.8, 16.3), (SPI_PAD_X[0] + 0.8, 15.7, 58.0, 16.3),
               # between CS and SCK, round the pads
               (44.4, 16.7, SPI_PAD_X[0] - 0.8, 17.5), (SPI_PAD_X[0] - 0.8, 17.3, SPI_PAD_X[0] + 0.8, 17.5),
               (SPI_PAD_X[0] + 0.8, 16.7, SPI_PAD_X[1] - 0.8, 17.5),
               # between SCK and SDI (MOSI), round the pads
               (43.2, 17.9, SPI_PAD_X[1] - 0.8, 18.7), (SPI_PAD_X[1] + 0.8, 17.9, SPI_PAD_X[2] - 0.8, 18.7),
               (52.1, 17.2, SPI_PAD_X[2] + 1.2, 18.1))
PREROUTED = PREROUTED + EPD_LINES
# Three ground test pads get their way into the pours drawn by hand, so that their via does not sit
# against the pad or under its label (2026-11-22, Norman): the router puts it right beside the pad.
# TP4 (middle) moves 0.8 mm down, its via 1 mm above its edge; TP13 (top, by the boost converter)
# keeps its place, its via 1 mm to its right; TP14 (UART GND) has its via midway to the TX pad.
# R15's ground pad (the Qwiic switch's gate pull-down) gets its via below it: with the SPI lines
# in their staircase the router put it to the left, where I2C_SDA and the RST and CS vias closed it in.
GND_PAD_VIAS = {"TP4.1": ((44.6, 24.2), (44.6, 22.4)), "TP13.1": ((60.0, 2.4), (61.8, 2.4)),
                "TP14.1": ((9.06, 4.0), (10.3, 4.0)), "R15.2": ((42.3, 12.52), (42.3, 13.5))}
PREROUTED = PREROUTED + tuple(dict(net="GND", pads=(pad_name,), vias=(via,), tracks=((0.4, (pad, via)),))
                              for pad_name, (pad, via) in GND_PAD_VIAS.items())
PLACEMENT.update({ref: (x, y, 0) for ref, (x, y) in EPD_PADS.items()})
PLACEMENT["R20"] = (*R20_AT, 0)
PLACEMENT["TP4"] = (*GND_PAD_VIAS["TP4.1"][0], 0)
SILK_LABELS = tuple(lab for lab in SILK_LABELS if lab[:3] != ("GND", 44.6, 25.1)) + (("GND", 44.6, 25.9, 0.8),)
# The I2C pull-ups move to where the hand-drawn bus starts at the bottom edge (in 1.0 they sat
# on the bus's straight run to the bridge, which revision 2.0 no longer passes): each signal pad
# drops straight onto its bus run's free end, the supply pads join the supply run to the right.
# The two probe pads sit beside them, each on its line (decided 2026-11-22).
PLACEMENT.pop("J3")
PLACEMENT.update({
    "R12": (41.6, 29.6, 270),    # SDA pull-up: above the free end of the SDA run (x 40.8-42.4)
    "R13": (43.2, 29.6, 270),    # SCL pull-up: above the free end of the SCL run (x 42.4-44.0)
    "TP9": (39.9, 30.4, 0),      # SDA probe, left of its pull-up
    "TP10": (44.7, 30.4, 0),     # SCL probe, right of its pull-up
    "TP12": (39.6, 27.6, 0),     # BMP_INT probe, above the SDA probe; its track drops past it to the free end of the BMP_INT run
    # a second ground pad for a scope's ground clip, by the boost converter
    "TP13": (60.0, 2.4, 0),
    # the fallback serial port on three standard test pads where 1.0's header J3 was: GND, TX, RX
    # from the left, TX straight above its module pin, labels above them as before
    **{ref: (round(pin_x(25) + dx, 3), 4.0, 0) for ref, dx in (("TP14", -2.54), ("TP15", 0.0), ("TP16", 2.54))},
})
# the "Up" arrow and its text make room for them, further right on the same line
UP_ARROW = (47.6, UP_ARROW[1], UP_ARROW[2], UP_ARROW[3])
# The board name and the "Up" arrow move to the sensor island, on one line (2026-11-22, Norman):
# arrow, "Up", then the name, the whole line centred in the free area below the BMP580. That area,
# measured on the board: from the island's slot (x 77.5, +0.5) to the lower mounting hole's keep-out
# (x 96.0), and from the lowest copper of the BMP580 group (y 28.1, +0.3) to the bottom edge (-0.3).
# Nothing else is there since 1.0's header J4 went.
NAME_AREA = (78.0, 28.4, 96.0, 33.7)
# Across, the whole line (from the arrow's left edge to the name's last letter) is centred between the
# island slot's right edge and the edge of the lower mounting hole itself (2026-11-22, Norman), so the
# visible gaps either side are equal.
NAME_X_SPAN = (SLOT_X[1], MOUNTING_HOLES[3][0] - 1.6)
SILK_LABELS = tuple(lab for lab in SILK_LABELS if lab[0] != "ClimaSense Rev 2.0")
# Every test pad's label, and on which side of the pad it stands. Its position is worked out when the
# board is drawn (pad_label_position): the gap between the outer edge of the pad's silkscreen circle
# and the nearest edge of the letters, as KiCad draws them, is TP_LABEL_GAP, and the letters are
# centred on the pad across that direction (2026-11-22, Norman: the labels sat at different
# distances, SCK almost on its circle).
TP_LABEL_GAP = 0.4
TP_LABELS = {
    "TP1": ("5V", "below"), "TP2": ("3V3", "above"), "TP3": ("3VS", "right"), "TP4": ("GND", "below"),
    "TP5": ("SCK", "right"), "TP6": ("SDI", "right"), "TP7": ("CS", "right"), "TP8": ("BSY", "left"),
    "TP9": ("SDA", "below"), "TP10": ("SCL", "below"), "TP11": ("DC", "right"), "TP12": ("INT", "right"),
    "TP13": ("GND", "below"), "TP14": ("GND", "above"), "TP15": ("TX", "above"), "TP16": ("RX", "above"),
}
# their hand-placed labels from before go
SILK_LABELS = tuple(lab for lab in SILK_LABELS
                    if not any(lab[0] == text and abs(lab[1] - PLACEMENT[ref][0]) < 2.6 and abs(lab[2] - PLACEMENT[ref][1]) < 2.6
                               for ref, (text, _) in TP_LABELS.items() if ref in PLACEMENT))
# The display's driving voltages are measured on their capacitors' pads: a name above each,
# turned upright so that it fits the 1.6 mm pitch.
SILK_LABELS = SILK_LABELS + tuple((name, round(50.4 + 1.6 * i, 2), 26.62, 0.8, 90) for i, name in enumerate(
    ("", "VDD", "VSH1", "VSH2", "VSL", "VGH", "VGL", "")) if name)   # VCOM: no room between C24 and J5

# SENS_EN (IO10, lower pin row) runs with the sensor bus to the regulator's pull-up R5 by U3:
# drawn by hand on the bottom layer under the bus along the bottom edge, from right of the USB
# connector to below R5; the router joins its ends. Left to the router it found no way through.
SENS_EN_FEED = (dict(net="/SENS_EN", tracks=((0.2, ((38.6, 32.6), (64.6, 32.6)), "bottom"),)),)

# Ground stitching vias (route_board.py adds them after routing): a uniform 5 mm grid over the
# pours, plus single rows where the ground return matters (x0, y0, x1, y1, pitch): the strip
# between the slots, across both ends of the FPC slot, along the antenna keep-out, and round the
# boost converter's grounds. (A first version was denser round the display connector too; that
# was more than needed, decided 2026-11-22.)
STITCH_PITCH = 5.0
# Start order of the router (route_board.py, `seed`): 0 = shortest connection first. Found by
# trying several with --seed=N; the one kept routes this board completely.
ROUTE_SEED = 7
STITCH_EXTRA = (
    (75.35, 0.8, 75.35, 33.2, 1.5),     # the strip between the FPC slot and the sensor slot
    (66.5, 9.2, 75.5, 9.2, 1.5),        # across the top end of the FPC slot
    (66.5, 24.4, 75.5, 24.4, 1.5),      # across the bottom end
    (7.7, 1.0, 7.7, 33.0, 2.0),         # along the antenna keep-out
    (47.6, 1.0, 58.3, 16.0, 2.5),       # round the boost converter's grounds
)


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


def add_fpc_tail(board):
    """The panel's FPC tail, for the 3D view only (gen_models.py draws its path): a board-only
    footprint without pads on the component side above the glass edge. It changes nothing for the
    router, so it can also be added to an already routed board (see the end of main)."""
    tail = pcbnew.FOOTPRINT(board)
    tail.SetReference("PNL2")
    tail.SetValue("FPC tail")
    tail.Reference().SetVisible(False)
    tail.Value().SetVisible(False)
    tail.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    model = pcbnew.FP_3DMODEL()
    model.m_Filename = "${KIPRJMOD}/lib/climasense.3dshapes/GDEY0213B74_FPC_tail.wrl"
    tail.Add3DModel(model)
    tail.SetPosition(P(PANEL[2], PANEL_TAIL_Y))
    board.Add(tail)


LABEL_BOXES = []      # the letters of every silkscreen label drawn, as KiCad draws them (mm, board frame)


def text_box(label):
    """Box round the letters of a PCB_TEXT as KiCad draws them (strokes included), in board mm."""
    bb = label.GetEffectiveTextShape().BBox()
    return (pcbnew.ToMM(bb.GetLeft()) - ORIGIN[0], pcbnew.ToMM(bb.GetTop()) - ORIGIN[1],
            pcbnew.ToMM(bb.GetRight()) - ORIGIN[0], pcbnew.ToMM(bb.GetBottom()) - ORIGIN[1])


def pad_label_position(board, ref, label, side):
    """Move `label` beside test pad `ref`: TP_LABEL_GAP between the pad's silkscreen circle and the
    nearest edge of the letters, the letters centred on the pad across that direction."""
    fp = board.FindFootprintByReference(ref)
    cx, cy = (pcbnew.ToMM(v) - o for v, o in ((fp.GetPosition().x, ORIGIN[0]), (fp.GetPosition().y, ORIGIN[1])))
    ring = max(pcbnew.ToMM(g.GetRadius()) + pcbnew.ToMM(g.GetWidth()) / 2 for g in fp.GraphicalItems()
               if g.GetClass() == "PCB_SHAPE" and g.GetLayer() == pcbnew.F_SilkS and g.GetShape() == pcbnew.SHAPE_T_CIRCLE)
    label.SetPosition(P(cx, cy))
    x0, y0, x1, y1 = text_box(label)
    reach = ring + TP_LABEL_GAP
    dx, dy = cx - (x0 + x1) / 2, cy - (y0 + y1) / 2              # centre the letters on the pad first
    if side == "right":
        dx = cx + reach - x0
    elif side == "left":
        dx = cx - reach - x1
    elif side == "below":
        dy = cy + reach - y0
    else:
        dy = cy - reach - y1
    label.SetPosition(P(cx + dx, cy + dy))


def stitch_avoid():
    """Where no ground stitching via may go: under a silkscreen label (0.3 mm round its letters) and
    within 1 mm of a test pad's edge (2026-11-22, Norman)."""
    out = [(x0 - 0.3, y0 - 0.3, x1 + 0.3, y1 + 0.3) for x0, y0, x1, y1 in LABEL_BOXES]
    for ref, (x, y, _) in PLACEMENT.items():
        if ref.startswith("TP"):
            out.append((x - 1.5, y - 1.5, x + 1.5, y + 1.5))
    return out


def option(name):
    """Value of --name=value, "" for a bare --name, None if absent."""
    for x in sys.argv[1:]:
        if x == name:
            return ""
        if x.startswith(name + "="):
            return x.split("=", 1)[1]
    return None


def state_file(board_file):
    """Where the fingerprints of a board's hand-drawn copper are kept (for --keep)."""
    return HW / "build" / (Path(board_file).stem + ".route.json")


def bundle_supply_length(board):
    """Length (mm) of +3V3 track on the top layer inside the display bundle: the strip that the
    hand-drawn SPI and reset lines span on the top layer from x 41 to where SDI rises to its pin
    (beyond it +3V3 leaves J5's supply pins below the lines)."""
    x0, x1 = 41.0, SPI_PAD_X[2] + 0.6
    pts = [pt for g in EPD_LINES if g["net"] in ("EPD_SCK", "EPD_MOSI", "EPD_CS", "EPD_RST")
           for width, line, *side in g["tracks"] if not side for pt in line if x0 <= pt[0] <= x1]
    y0, y1 = min(y for _, y in pts), max(y for _, y in pts)
    total = 0.0
    for t in board.GetTracks():
        if (t.GetClass() != "PCB_TRACK" or t.GetLayer() != pcbnew.F_Cu
                or t.GetNetname() != "+3V3"):
            continue
        a = (pcbnew.ToMM(t.GetStart().x) - ORIGIN[0], pcbnew.ToMM(t.GetStart().y) - ORIGIN[1])
        b = (pcbnew.ToMM(t.GetEnd().x) - ORIGIN[0], pcbnew.ToMM(t.GetEnd().y) - ORIGIN[1])
        length = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        steps = max(1, int(length / 0.05))
        inside = sum(1 for k in range(steps) if x0 <= a[0] + (b[0] - a[0]) * (k + 0.5) / steps <= x1
                     and y0 <= a[1] + (b[1] - a[1]) * (k + 0.5) / steps <= y1)
        total += length * inside / steps
    return round(total, 2)


def seed_batch(spec):
    """--seeds=A-B: one worker process per seed, then keep the best clean board."""
    a, b = (int(v) for v in spec.split("-")) if "-" in spec else (int(spec), int(spec))
    seeds = list(range(a, b + 1))
    skip = ("--seeds", "--seed=", "--out=", "--summary=", "--keep", "--no-fill")
    passed = [x for x in sys.argv[1:] if not x.startswith(skip)]
    (HW / "build").mkdir(exist_ok=True)
    keep = option("--keep")
    if keep is not None:
        keep_file = Path(keep).resolve() if keep else BOARD_FILE
        if keep_file.exists():
            snapshot = HW / "build" / "previous.kicad_pcb"           # the workers all read this one
            shutil.copy(keep_file, snapshot)
            if state_file(keep_file).exists():
                shutil.copy(state_file(keep_file), state_file(snapshot))
            passed.append(f"--keep={snapshot}")
    t0 = time.time()
    width = max(1, min(len(seeds), (os.cpu_count() or 2) - 1))
    print(f"routing seeds {a}-{b} in {width} parallel processes ...", flush=True)
    running, results = [], []
    queue = list(seeds)
    while queue or running:
        while queue and len(running) < width:
            n = queue.pop(0)
            out, summary, log = (HW / "build" / f"seed_{n}{ext}" for ext in (".kicad_pcb", ".json", ".log"))
            summary.unlink(missing_ok=True)
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *passed, f"--seed={n}",
                                     f"--out={out}", f"--summary={summary}", "--no-fill"],
                                    stdout=log.open("w"), stderr=subprocess.STDOUT)
            running.append((n, proc, out, summary))
        time.sleep(1)
        for item in list(running):
            n, proc, out, summary = item
            if proc.poll() is None:
                continue
            running.remove(item)
            if proc.returncode == 0 and summary.exists():
                r = json.loads(summary.read_text())
                results.append(r)
                print(f"  seed {n}: {r['open']} open, {r['bundle_supply_mm']} mm of +3V3 in the display bundle, "
                      f"{r['vias']} vias, {r['track_mm']} mm of track, {r['seconds']} s", flush=True)
            else:
                print(f"  seed {n}: failed (see build/seed_{n}.log)", flush=True)
    if not results:
        raise SystemExit("no seed produced a board")
    # the clean ones must also pass audit_pcb.py (a net crossing itself or with a loop fails it)
    for r in results:
        r["audit_ok"] = r["open"] == 0 and subprocess.run(
            [sys.executable, str(HW / "tools" / "audit_pcb.py"), r["out"]], capture_output=True).returncode == 0
        if r["open"] == 0:
            print(f"  seed {r['seed']}: audit {'passed' if r['audit_ok'] else 'FAILED'}", flush=True)
    best = min(results, key=lambda r: (r["open"], not r["audit_ok"], r["bundle_supply_mm"] > 0.05, r["vias"], r["track_mm"]))
    shutil.copy(best["out"], BOARD_FILE)
    shutil.copy(state_file(best["out"]), state_file(BOARD_FILE))
    for r in results:
        for ext in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            Path(r["out"]).with_suffix(ext).unlink(missing_ok=True)
    t_fill = time.time()
    subprocess.run([KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json",
                    "-o", str(HW / "build" / "drc.json"), str(BOARD_FILE)], check=True, capture_output=True)
    print(f"kept seed {best['seed']} ({best['open']} open, {best['vias']} vias, {best['track_mm']} mm) -> "
          f"{BOARD_FILE.name}; pours filled in {time.time() - t_fill:.0f} s; {time.time() - t0:.0f} s in total"
          + ("" if best["seed"] == ROUTE_SEED or keep is not None
             else f"; set ROUTE_SEED = {best['seed']} to get it from a single run"))
    if best["open"]:
        raise SystemExit(f"no seed routed the board completely (best: {best['open']} open)")


def main():
    if option("--seeds"):
        return seed_batch(option("--seeds"))
    if "--add-tail-only" in sys.argv[1:]:
        board = pcbnew.LoadBoard(str(BOARD_FILE))
        if not any(fp.GetReference() == "PNL2" for fp in board.GetFootprints()):
            add_fpc_tail(board)
            pcbnew.SaveBoard(str(BOARD_FILE), board)
        print("FPC tail model added")
        return
    if not NETLIST.exists():
        raise SystemExit("build/netlist.net missing - run check_schematic.py first")
    net = parse(NETLIST.read_text(encoding="utf-8"))
    t0 = time.time()
    timing = {}
    out_file = Path(option("--out")) if option("--out") else BOARD_FILE

    # --keep: read the copper of the previous board before it is overwritten
    keep = None
    if option("--keep") is not None and "--no-route" not in sys.argv[1:]:
        import route_board
        keep_file = Path(option("--keep")) if option("--keep") else BOARD_FILE
        if keep_file.exists():
            keep = route_board.read_previous(keep_file, ORIGIN)
            state = state_file(keep_file)
            record = json.loads(state.read_text()) if state.exists() else {}
            keep["hand"], keep["reserved"] = record.get("hand"), record.get("reserved")
            names = [x for x in (option("--reroute") or "").split(",") if x]
            keep["reroute"] = set(names) | {"/" + x for x in names if not x.startswith("/")}
        else:
            print(f"--keep: {keep_file.name} does not exist, routing everything")
        timing["read previous board"] = time.time() - t0

    if out_file.exists():
        out_file.unlink()
    board = pcbnew.NewBoard(str(out_file))
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
    fx0, fy0, fx1, fy1 = FPC_SLOT
    edge(board, [(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)])
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

    # --- the panel itself, for the 3D view only (board only: no BOM, no placement) ---------
    panel = pcbnew.FOOTPRINT(board)
    panel.SetReference("PNL1")
    panel.SetValue("GDEY0213B74")
    panel.Reference().SetVisible(False)
    panel.Value().SetVisible(False)
    panel.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    model = pcbnew.FP_3DMODEL()
    model.m_Filename = "${KIPRJMOD}/lib/climasense.3dshapes/GDEY0213B74.wrl"
    panel.Add3DModel(model)
    panel.SetPosition(P((PANEL[0] + PANEL[2]) / 2, (PANEL[1] + PANEL[3]) / 2))
    board.Add(panel)
    panel.Flip(panel.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    add_fpc_tail(board)

    # --- where the panel goes, on the back ------------------------------------
    # Outline on the back fabrication layer, and on the back silkscreen with gaps where it
    # would run over a through-hole pad (the fab leaves silkscreen off copper anyway; the gaps
    # keep DRC quiet). Two ticks and "FPC" mark the edge the tail leaves from, so that the
    # panel cannot be stuck on the wrong way round.
    px0, py0, px1, py1 = PANEL
    sides = (((px0, py0), (px1, py0)), ((px1, py0), (px1, py1)), ((px0, py1), (px1, py1)),
             ((px0, py0), (px0, py1)))
    tail_y = (PANEL_TAIL_Y - 6.25, PANEL_TAIL_Y + 6.25)
    ticks = tuple(((px1 - 1.2, y), (px1, y)) for y in tail_y)
    back_pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.IsOnLayer(pcbnew.B_Cu):
                bb = pad.GetBoundingBox()
                back_pads.append(tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())))

    def segment(layer, a, b):
        line = pcbnew.PCB_SHAPE(board)
        line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetStart(P(*a))
        line.SetEnd(P(*b))
        line.SetLayer(layer)
        line.SetWidth(FromMM(0.15))
        board.Add(line)

    def clear_of_pads(a, b, margin=0.25):
        """Pieces of the axis-parallel line a-b that keep `margin` from every back pad."""
        horizontal = a[1] == b[1]
        lo, hi = (a[0], b[0]) if horizontal else (a[1], b[1])
        cuts = []
        for x0, y0, x1, y1 in back_pads:
            x0, y0, x1, y1 = (x0 - ORIGIN[0] - margin, y0 - ORIGIN[1] - margin,
                              x1 - ORIGIN[0] + margin, y1 - ORIGIN[1] + margin)
            if horizontal and y0 <= a[1] <= y1:
                cuts.append((x0, x1))
            elif not horizontal and x0 <= a[0] <= x1:
                cuts.append((y0, y1))
        pieces, start = [], lo
        for c0, c1 in sorted(cuts):
            if c1 < start or c0 > hi:
                continue
            if c0 > start:
                pieces.append((start, c0))
            start = max(start, c1)
        if start < hi:
            pieces.append((start, hi))
        return [((u, a[1]), (v, a[1])) if horizontal else ((a[0], u), (a[0], v))
                for u, v in pieces if v - u > 0.3]

    for a, b in sides + ticks:
        segment(pcbnew.B_Fab, a, b)
        for piece in clear_of_pads(a, b):
            segment(pcbnew.B_SilkS, *piece)
    for text, x, y, angle in (("DISPLAY", (px0 + px1) / 2, (py0 + py1) / 2, 0),
                              ("FPC", px1 - 2.2, PANEL_TAIL_Y, 90)):
        label = pcbnew.PCB_TEXT(board)
        label.SetText(text)
        label.SetLayer(pcbnew.B_SilkS)
        label.SetMirrored(True)
        label.SetTextAngleDegrees(angle)
        label.SetPosition(P(x, y))
        label.SetTextSize(VECTOR2I(FromMM(1.0), FromMM(1.0)))
        label.SetTextThickness(FromMM(0.15))
        board.Add(label)

    # --- silkscreen labels ---------------------------------------------------
    # Reference designators are not printed (see above); these few labels are.
    for text, x, y, size, *angle in SILK_LABELS:
        label = pcbnew.PCB_TEXT(board)
        label.SetText(text)
        if angle:
            label.SetTextAngleDegrees(angle[0])
        label.SetPosition(P(x, y))
        label.SetLayer(pcbnew.F_SilkS)
        label.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
        label.SetTextThickness(FromMM(0.15))
        board.Add(label)
        LABEL_BOXES.append(text_box(label))
    for ref, (text, side) in TP_LABELS.items():
        label = pcbnew.PCB_TEXT(board)
        label.SetText(text)
        label.SetLayer(pcbnew.F_SilkS)
        label.SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        label.SetTextThickness(FromMM(0.15))
        board.Add(label)
        pad_label_position(board, ref, label, side)
        LABEL_BOXES.append(text_box(label))

    # Which way up the board hangs: an arrow towards the top edge, "Up" beside it and the board
    # name after that, on one line centred in NAME_AREA (the letters measured as KiCad draws them).
    texts = []
    for text in ("Up", "ClimaSense Rev 2.0"):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(VECTOR2I(FromMM(NAME_SIZE), FromMM(NAME_SIZE)))
        t.SetTextThickness(FromMM(0.15))
        t.SetPosition(P(0, 0))
        board.Add(t)
        texts.append(t)
    head = UP_ARROW[2]
    arrow_w, gap_up, gap_name, arrow_h = 2 * 0.6 * head + 0.1, 0.5, 1.5, 2.4   # head width with its outline
    boxes = [text_box(t) for t in texts]
    widths = [b[2] - b[0] for b in boxes]
    ax0, ay0, ax1, ay1 = NAME_AREA
    cx, cy = sum(NAME_X_SPAN) / 2, (ay0 + ay1) / 2
    left = cx - (arrow_w + gap_up + widths[0] + gap_name + widths[1]) / 2
    x = left + arrow_w / 2
    # the arrow starts at the foot of the letters and rises above them (2026-11-22, Norman); arrow and
    # text together are centred on cy
    text_h = max(b[3] - b[1] for b in boxes)
    tail = cy + arrow_h / 2
    tip = tail - arrow_h
    text_cy = tail - text_h / 2
    starts = (left + arrow_w + gap_up, left + arrow_w + gap_up + widths[0] + gap_name)
    for t, b, start in zip(texts, boxes, starts):
        t.SetPosition(P(start - b[0], text_cy - (b[1] + b[3]) / 2))   # the letters' left edge at `start`
        LABEL_BOXES.append(text_box(t))
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

    failures = []
    if "--no-route" not in sys.argv[1:]:
        import route_board
        # Order on the bridge, top to bottom, and how far each track runs on into the island.
        # Ground and supply come first because they turn up towards the SCD41 and its
        # capacitor; the signals pass below them. The ends are staggered so that each track
        # can leave at 45 degrees without having to cross its neighbour.
        bridge = (("GND", 15.3, 1.1), ("+3V3_SENS", 16.1, 1.7), ("/I2C_SCL", 16.9, 2.3), ("/I2C_SDA", 17.7, 1.7),
                  ("/BMP_INT", 18.5, 1.1))
        # Revision 2.0: the bus reaches the bridge from below, up the strip between the FPC
        # slot and the sensor slot, so each fixed track starts where its feed comes up.
        start_x = {name: x for name, _, x, _ in SENSOR_BUS}
        timing["placement"] = time.time() - t0 - timing.get("read previous board", 0.0)
        geo = dict(
            W=W, H=H,
            cutouts=[(SLOT_X[0], y1, SLOT_X[1], y2) for y1, y2 in SLOTS_Y] + list(TONGUE_CUTOUTS) + [FPC_SLOT],
            antenna_x=6.9,
            module_inner=(MODULE[0] - 12.75, ROW_TOP + 1.05, MODULE[0] + 12.75, ROW_BOTTOM - 1.05),
            module_ref="U4", module_epad="29",
            holes=MOUNTING_HOLES, hole_keepout=3.3,
            bridge_x=SLOT_X, bridge_y={name: y for name, y, _ in bridge},
            fixed_tracks=[(name, start_x.get(name, SLOT_X[0] - 1.8), SLOT_X[1] + reach, y)
                          for name, y, reach in bridge] + [
                # staggered on the sensor's side for the same reason
                (name, TONGUE_NECK_X[0] - 0.9, TONGUE_NECK_X[1] + 0.9 + 0.6 * k, y)
                for k, (name, y) in enumerate(TONGUE_NECK_TRACKS)],
            # the connector's shell, from just behind its row of pads to the board edge
            usb_body=(PLACEMENT["J1"][0] - 4.6, PLACEMENT["J1"][1] - 3.3, PLACEMENT["J1"][0] + 4.6, H),
            fixed_feeds=SENSOR_BUS_FEEDS,
            free_feeds=SENS_EN_FEED,
            thin_only=TONGUE_AREA,
            fixed_only=[(SLOT_X[0] - 0.3, 0, SLOT_X[1] + 0.3, H), (TONGUE_NECK_X[0], 21.5, TONGUE_NECK_X[1], 25.5)],
            fanout={"U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9", "J1", "J2", "D1", "J5", "Q1"},
            prerouted=[{**g, "net": "/" + g["net"] if "/" + g["net"] in nets else g["net"]} for g in PREROUTED],
            reserve_top=[("GND", area) for area in EPD_POCKETS],
            trunks=TRUNKS, reserve_bottom=[("GND", area) for area in (BUCK_AREA, *USB_GROUND_AREAS,
                                                                               *DISPLAY_GROUND_AREAS)],
            internally_joined=INTERNALLY_JOINED,
            # the strip below the module's bottom pad row is where its pins escape; the trunk stays out of it
            no_trunk=[(6.9, ROW_BOTTOM + 0.75, MODULE[0] + 14.2, ROW_BOTTOM + 2.55)],
            solid_pour_pads={"J1", "J2", "U1", "U2", "U3", "U9"},
            stitch_pitch=STITCH_PITCH, stitch_extra=STITCH_EXTRA, stitch_avoid=stitch_avoid(),
            via_avoid=list(LABEL_BOXES),      # no routed via under a label either (2026-11-22, Norman)
            via_cost=float(next((x.split('=')[1] for x in sys.argv[1:] if x.startswith('--via-cost=')), 30)),
            debug="--debug" in sys.argv[1:],
            attempts=next((int(x.split("=")[1]) for x in sys.argv[1:] if x.startswith("--attempts=")), 12),
            seed=next((int(x.split("=")[1]) for x in sys.argv[1:] if x.startswith("--seed=")), ROUTE_SEED),
            keep=keep,
        )
        failures = route_board.run(board, ORIGIN, geo)
        timing.update(geo.get("timing", {}))
        (HW / "build").mkdir(exist_ok=True)
        state_file(out_file).write_text(json.dumps(dict(hand=route_board.hand_drawn_hashes(geo), seed=geo["seed"],
                                                        reserved=route_board.reserved_areas(geo)), indent=1))

    t_save = time.time()
    pcbnew.SaveBoard(str(out_file), board)
    timing["save"] = time.time() - t_save
    # One exception to the board's 0.25 mm hole clearance: the side switches' guide-boss holes keep
    # 0.2 mm (JLCPCB's limit for an unplated hole to copper) from the switch's own pads.
    (HW / "climasense.kicad_dru").write_text(
        '(version 1)\n'
        '(rule "Side switch: boss holes to its own pads"\n'
        '\t(condition "A.memberOfFootprint(\'SW*\') && B.memberOfFootprint(\'SW*\')")\n'
        '\t(constraint hole_clearance (min 0.2mm)))\n', encoding="utf-8", newline="\n")
    if "--no-route" not in sys.argv[1:] and "--no-fill" not in sys.argv[1:]:
        # fill the ground pours with KiCad's own filler and store the result in the board
        t_fill = time.time()
        subprocess.run([KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json",
                        "-o", str(HW / "build" / "drc.json"), str(out_file)], check=True, capture_output=True)
        timing["pour fill"] = time.time() - t_fill
    timing["total"] = time.time() - t0
    print(f"{placed} parts placed, {len(nets)} nets, board {W} x {H} mm -> {out_file.name}")
    print("time: " + ", ".join(f"{k} {v:.1f} s" for k, v in timing.items()))
    if option("--summary"):
        tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
        Path(option("--summary")).write_text(json.dumps(dict(
            seed=geo["seed"], out=str(out_file), open=len(failures), seconds=round(timing["total"]),
            vias=sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA"),
            track_mm=round(sum(pcbnew.ToMM(t.GetLength()) for t in tracks), 1),
            bundle_supply_mm=bundle_supply_length(board))))


if __name__ == "__main__":
    main()

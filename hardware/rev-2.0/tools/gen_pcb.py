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
    "C15": (44.775, 14.45, 0),   # regulator input (0603 since 2026-11-24): supply pad below the input pin
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
# The top layer under the buck inductor L1, between its two pads, carries no copper at all
# (2026-11-24): no track, no via, no pour. Murata's specification for the DFE252012F
# (J(E)TE243A-0017D-01, notice 2) forbids copper under the coil other than the pattern to its
# electrodes, because the core has a low insulation resistance. Until then the router took one
# signal through there (QWIIC_EN on the board of 2026-11-24, held only by its 100 k pull-down,
# 0.45 mm from the pad of the switch node). Keeping the strip free had been tried on the board
# of 2026-11-23 and no seed routed; see docs/hardware/rev-2.0.md for how it went this time.
L1_UNDER = (34.9, 12.05, 37.1, 12.95)
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
# Revision 2.0: a longer board with an e-paper panel above the parts
# --------------------------------------------------------------------------
# Everything above is the 1.0 geometry. Revision 2.0 keeps the controller side as it was,
# moves the sensor island (everything from the 1.0 slot at x = 48 rightwards) by DX, and
# puts the display electronics into the gap.
# Since 2026-11-24 (Norman) the component side faces the room again, as on 1.0, and the panel
# lies on that side too: on a printed frame that stands on the board, FRAME_HEIGHT above it, over
# x = PANEL[0]..PANEL[2]. Its FPC tail leaves the glass towards the sensor side, folds back in a
# half circle under the panel and enters the connector J5 from the right. No slot goes through
# the board for it any more. The sensor bus runs along the bottom edge and up the strip in front
# of the sensor slot to the bridge, as before. (Until then the board was turned round: the parts
# faced the wall, the panel was stuck to the bare back, and the tail came through a slot,
# FPC_SLOT, at x 71.8 to 73.0. docs/hardware/rev-2.0.md has both.)
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

# The panel (GDEY0213B74, 59.2 x 29.2 mm; specification page 7), above the parts: x0, y0, x1, y1.
# Its left edge keeps 3.9 mm from the antenna keep-out (x = 6.9). Its tail is centred on the short
# edge (to 0.2 mm), 12.5 mm wide, 14.3 mm long, the last 6 mm stiffened.
# The display faces the room and the tail leaves to the right, so the panel is turned by 180
# degrees against the drawing's main view: its pin 1, and the 8.15 mm from the long edge to the
# tail, are at the bottom. The panel sits 0.4 mm higher on the board than it did on the back
# (y 2.0 to 31.2; before 2.4 to 31.6), so that the tail's centre line stays on y 16.8, J5's.
PANEL_X0 = 10.8
PANEL = (PANEL_X0, 2.0, PANEL_X0 + 59.2, 31.2)
PANEL_TAIL_Y = round(PANEL[3] - 8.15 - 12.5 / 2, 2)   # centre line of the tail: 16.8
# How high the frame carries the panel: the panel's back, above the board. The parts under it are
# 3.3 mm at most (the side switches); the tail's fold allows 4.75 mm at most
# (docs/hardware/next-revision.md, "The tail's fold"). 4.75 mm since 2026-11-24 (Norman: raise
# the panel a bit, for a shallower bezel; 4.6 mm before): 0.9 mm of tail are spare, 0.1 mm with
# every tolerance against it. The fold hangs free, so the height changes nothing on the board.
FRAME_HEIGHT = 4.75
# Where it leaves the glass the tail is wider than the 12.5 mm of its contact end (specification
# page 7): a shoulder that starts 6.77 mm from the panel's long edge on the pin 1 side
# (dimensioned; 1.38 mm outside the tail's edge) and ends about 0.4 mm outside the tail's other
# edge (measured off the drawing), 14.3 mm in all. It runs 4.1 mm out from the glass at that width
# and has narrowed to 12.5 mm at 4.9 mm. Board y of its two edges (pin 1 side at the bottom):
FPC_SHOULDER = (round(PANEL[3] - (8.15 + 12.5 + 0.4), 2), round(PANEL[3] - 6.77, 2))     # 10.15 to 24.43
# Room the tail's fold needs above the board: from the glass edge to 4.3 mm beyond it (where the
# half circle stands with every tolerance at its worst), 1.5 mm wider than the shoulder at both
# ends, from the board up to the panel. Nothing higher than the tracks may stand there; in front
# of J5, under the tail's stiff end, nothing higher than about 0.5 mm. Drawn on the fabrication
# layer; the frame is open on this side.
FOLD_ROOM = (PANEL[2], round(FPC_SHOULDER[0] - 1.5, 2), round(PANEL[2] + 4.3, 2), round(FPC_SHOULDER[1] + 1.5, 2))
# Centre line of the 3 mm strip in front of the island's slots (it lay between the FPC slot and
# those slots while the board had one). The two ground vias in that strip stand on it, one above
# the other (2026-11-23, Norman): the via of the ground track that crosses the bridge, and the
# strip's stitching via (STITCH_PREFER).
STRIP_X = 74.5

# Display parts. J5 (24-pin, 0.5 mm, dual contact) with its opening to the right, towards the
# tail's fold; pin 1 is then at the bottom, like the panel's pin 1, and the fold keeps each
# contact's height: panel pin N on connector pin N (gen_schematic.py, FPC_REVERSED false).
# Footprint: Kinghelm KH-FPC0.5-H2.0SMT-24P-QCHF (gen_footprints.py), origin in the middle of
# its 4.90 mm deep housing, opening 2.45 mm in front of it.
# Its front edge lies 3.0 mm inside the glass edge (2026-11-24). The tail leaves the glass 0.5 mm
# above the panel's back and J5 takes it 1.15 mm above the board (measured off Kinghelm's side
# view): a drop of 4.10 mm, a half circle of 6.4 mm, which begins 1.4 mm from the glass (the glue
# on the tail's back may reach 1.0 mm) and leaves 0.5 mm of flexible tail before the stiff 6 mm,
# 2.1 mm of which are in J5. A longer or shorter tail moves the fold, not the connector.
# (With the panel on the back, J5's front edge was 6.8 mm from the FPC slot, 5.0 mm inside the
# glass edge.)
J5_FRONT_INSIDE_GLASS = 3.0
J5_X = round(PANEL[2] - J5_FRONT_INSIDE_GLASS - 4.90 / 2, 3)        # 64.55
# Across, J5 sits 0.05 mm above the tail's centre line (2026-11-24, Norman: the tracks entered the
# pads beside their middle). Its pads are 0.5 mm apart with the connector's middle between two of
# them, so on the centre line (y 16.8) they lie on quarter millimetres, 0.05 mm off the 0.1 mm grid
# all tracks are on; at y 16.75 pin p lies on y = 23.0 - 0.5 p, on the grid. The tail has more play
# in the connector than that. (The USB connector and the BMP580 are placed like this too.)
J5_Y = round(PANEL_TAIL_Y - 0.05, 2)
PLACEMENT.update({
    "J5": (J5_X, J5_Y, 90),
    # The panel's pin 1 is at the bottom now: the gate-drive pins (GDR, RESE: 2, 3) are at the
    # lower end of J5, the supply and driving-voltage pins (15-24) at its upper end. So the two
    # groups of parts changed places (2026-11-24, Norman), the mirror image of the board of
    # 2026-11-23: the boost converter and the charge pump below the display lines, next to pins 2
    # and 3, the capacitors of the supply and driving voltages in a row along the top, with the
    # open area between them and J5's upper pins for their lines. (Tried first, the same day: the
    # boost converter left at the top and the capacitors beside it. Their lines did not fit into
    # the 3.8 mm between the diodes and J5's pad row; none of eight router seeds finished.)
    #
    # Boost converter, drawn again for its new place (see BOOST): everything on one line, y 25.0.
    # The inductor on the left, the switch node straight to the right into the MOSFET's drain,
    # 4.3 mm; the diode to VGH above that line and the charge pump capacitor below it, each a stub
    # of half a millimetre. The MOSFET is turned by 180 degrees: drain towards the inductor, source
    # and gate towards J5, the source (to pin 3) above the gate (to pin 2), as the pins lie.
    "L2": (51.1, 25.0, 0),        # 47 uH, 4 x 4 mm: +3V3 on the left, switch node on the right
    "C25": (51.1, 21.4, 0),       # 4.7 uF at the inductor's input, above it: supply pad over the inductor's
    "D2": (54.9, 22.4, 270),      # switch node to VGH, upright: anode down on the switch node, cathode up
    "C26": (54.9, 27.0, 270),     # 4.7 uF charge pump capacitor, upright: switch node up, pump node down
    "Q1": (57.8, 25.0, 180),      # MOSFET: drain left, source top right, gate bottom right
    # 2.2 ohm sense resistor, upright, right of the source pin: sense pad level with that pin,
    # ground pad and its via above.
    "R19": (59.9, 23.84, 90),
    # 1 Mohm gate pull-down, upright, on the gate line below R19: gate pad on the line, ground pad
    # and its via below. It only holds the gate low while the panel does not drive it.
    "R18": (59.9, 26.16, 270),
    "D4": (51.2, 29.0, 180),      # VGL to the charge pump, under the inductor: pump node right, VGL left
    "D3": (57.2, 28.9, 90),       # charge pump to ground, upright under the MOSFET: pump node up, ground down
    # The seven 1 uF capacitors of J5's upper pins in a row along the top, 1.6 mm apart, the pad
    # that carries the voltage towards the pins. From the left in the order of their pins from the
    # bottom, so that their lines need not cross: +3V3 (pins 15, 16), VDD (18), VSH1 (20), VGH (21),
    # VSL (22), VGL (23), VCOM (24).
    **{f"C{n}": (50.4 + 1.6 * i, 4.1, 90) for i, n in enumerate((17, 18, 19, 22, 21, 23, 24))},
    # VSH2 is the panel's pin 5, among the lower pins: its capacitor lies left of that pin, the
    # voltage pad towards it.
    "C20": (59.2, 20.0, 180),
    # The sensor regulator moves to where the sensor bus turns up into the strip to the bridge,
    # below the FPC slot (1.0 had it next to the buck converter, about 30 mm further left): the
    # sensors' supply current then runs a few millimetres to the strip instead of the length of
    # the display area. The 5 V feed and SENS_EN travel instead. Turned by 270 degrees: input,
    # ground and enable along the top, output at the bottom right above the bus's supply run.
    # Its capacitors stand in line with its pins as before: input above, output below.
    "U3": (68.0, 28.4, 270),
    "C3": (68.775, 25.5, 180),    # LDO input (0603 since 2026-11-24): ground pad over the ground pin, clear of J5
    "C4": (68.475, 31.0, 180),    # LDO output: supply pad under the output pin
    "TP3": (70.6, 30.6, 0),       # test pad for the sensors' 3.3 V, on the back, on a via beside the output capacitor
    "R5": (65.3, 28.4, 90),       # SENS_EN pull-up, next to the regulator's enable pin (1.0: by the buck converter)
})
# Everything that is probed goes to the back (2026-11-24, Norman): the panel on its frame covers
# the component side. All sixteen test and probe pads are bare copper pads on the bottom layer,
# with their labels on the back silkscreen. A pad on a hand-drawn line stands on a via of that
# line (EPD_LINES); the others are reached by the router on the bottom layer; the ground pads lie
# in the bottom pour.
BACK_SIDE = {f"TP{n}" for n in range(1, 17)}
# Where the frame that carries the panel stands on the board (x0, y0, x1, y1): spots kept free of
# parts (tracks and vias may run under them; the feet stand on the solder mask), drawn on the
# comments layer. Proposed 2026-11-24, not yet agreed: one under each corner of the panel, as far
# as the parts allow, one in the open area between the module and the buck converter, one below
# the display lines, and a small one on the top edge between the LED and the BOOT switch.
FRAME_FEET = ((8.8, 0.6, 14.6, 5.6),       # top left, beside the antenna end's mounting hole
              (12.6, 28.6, 18.2, 33.4),    # bottom left
              (63.8, 0.6, 69.6, 7.4),      # top right, above J5
              (60.7, 26.4, 64.4, 31.4),    # bottom right, below J5 (the sensor regulator has the corner)
              (27.0, 9.0, 32.4, 17.0),     # middle, between the module and the buck converter
              (44.6, 21.2, 48.4, 27.4),    # below the display lines, left of the boost converter
              (19.8, 0.6, 23.4, 3.9))      # top edge, between the LED and the BOOT switch
# Two 2.2 mm holes locate the frame, one in the bottom left foot and one in the top right one,
# far apart and on a diagonal; an M2 screw from the back can also hold the frame down there.
FRAME_HOLES = ((15.5, 30.8), (66.5, 4.0))
POWER_NETS = POWER_NETS + ("/EPD_SW", "/EPD_RESE")
# Bottom-layer ground that no signal may cut. The sensor island's ground reaches the main pours
# only through the strip between the FPC slot and the sensor slot; the bottom layer of that
# strip, and of the FPC landing area between J5 and the slot round both ends of the slot, stays
# ground, so the sensor bus crosses there on the top layer. In the first generated board the bus
# ran on the bottom layer there and walled off pockets of the pours. The boost converter gets
# an unbroken ground under it, like the buck converter.
DISPLAY_GROUND_AREAS = ((66.7, 0.3, 75.9, 33.7),       # in front of J5 and the strip, full height
                        (59.8, 7.5, 66.7, 26.0),       # behind J5: its ground pins' vias land here
                        (52.0, 23.0, 59.3, 26.3),      # under the boost converter's switching loop
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
    ("DISPLAY", J5_X + 4.0, 16.8, 0.8, 90),)
# The regulator's output joins the bus's supply run straight below it; the router does the rest.
PREROUTED = PREROUTED + (
    dict(net="+3V3_SENS", pads=("U3.5", "C4.1"), tracks=((0.4, ((68.95, 29.5), (68.95, 31.0))),)),
    # the sensors' 3.3 V test pad, on the back: a stub from the output capacitor to a via in the pad
    # (the bottom layer there is kept for ground, so the router cannot reach the pad)
    dict(net="+3V3_SENS", pads=("TP3.1",), vias=((70.6, 30.6),),
         tracks=((0.4, ((68.95, 31.0), (70.2, 31.0), (70.6, 30.6))),)),
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
# ones the router found for the clean board of 2026-11-22 (commit e8b8ee3, ROUTE_SEED 5). Left of
# J5 three of them run as a staircase (2026-11-22, Norman), 1.2 mm apart.
# 2026-11-24: the panel moved to the component side, which reverses the pin order at J5. The six
# tracks stayed where they were and changed their signals instead (gen_schematic.py): from the
# top, the track from the module's pin 26 (IO3) is MOSI, pin 16 (IO18) SCK, pin 23 (IO15) CS,
# pin 4 (IO4) DC, pin 5 (IO5) RST; they enter J5's pins 14 to 10 from the left, each stepping
# down to its pin in the last 5 mm. The track from pin 9 (IO1), BUSY, comes along the top edge
# and down the right of J5's pad row, between the pads and the upper holding pad, into pin 9.
# The probe pads are on the back, each on a via of its line (a bare 1.0 mm pad with the via in
# its middle, so that a pad still adds no branch): CS, SCK, DC in the staircase, MOSI on its run
# down past C26, BUSY above J5. RST has no pad. The pull-up R20 on CS sits on CS's run down from
# its via at x 40, R21 on RST's run at y 18.9; the router joins their +3V3 pads.
EPD_PADS = {"TP7": (45.4, 16.5), "TP5": (47.6, 15.5), "TP11": (49.8, 17.7), "TP6": (50.2, 13.3),
            "TP8": (round(J5_X - 1.65, 2), 6.6)}
R20_AT = (39.49, 15.0)        # EPD_CS pull-up, horizontal: +3V3 pad at x 38.98, CS pad at x 40.0
R21_AT = (46.0, 19.41)        # EPD_RST pull-up, upright: RST pad on the line at y 18.9, +3V3 pad below
_J5 = round(J5_X - 2.65, 2)   # where a line ends on J5's pads: 61.9
_UP = round(J5_X - 1.65, 2)   # the lane between J5's pad row and its upper holding pad: 62.9
EPD_LINES = (
    dict(net="EPD_DC", pads=("U4.4", "TP11.1", "J5.11"), vias=((11.6, 26.9), (43.7, 17.1), EPD_PADS["TP11"]), tracks=(
        (0.2, ((11.6, 25.8), (11.6, 26.9))),
        # under the module on the bottom layer, round the switches' boss holes, down to J5's row
        (0.2, ((11.6, 26.9), (15.4, 23.1), (15.4, 14.7), (26.7, 3.4), (29.8, 3.4), (32.3, 0.9), (34.3, 0.9),
               (34.8, 1.4), (34.8, 1.7), (34.9, 1.8), (37.1, 1.8), (37.2, 1.7), (37.2, 1.4), (37.7, 0.9),
               (38.5, 0.9), (38.9, 1.3), (38.9, 1.5), (43.7, 6.3), (43.7, 17.1)), "bottom"),
        (0.2, ((43.7, 17.1), (44.3, 17.7), EPD_PADS["TP11"])),
        (0.2, (EPD_PADS["TP11"], (51.2, 17.7), (51.4, 17.5), (_J5, 17.5))),
    )),
    dict(net="EPD_RST", pads=("U4.5", "R21.2", "J5.10"), vias=((22.4, 27.8), (33.8, 21.2)), tracks=(
        # (The step up between x 18.2 and 20.3 goes round a resistor's pad, with a wiggle of 0.1 mm
        # on either side, as the router found it. Drawn as two straight diagonals on 2026-11-24, it
        # cost the module's lower pin row its way out: with it, and with the BUSY line's bottom run
        # 0.1 mm lower, none of twelve seeds routed I2C_SDA, I2C_SCL, BMP_INT and QWIIC_EN all at
        # once; without, five of twelve did. So it stays as it was.)
        (0.2, ((12.9, 25.8), (12.9, 27.8), (13.3, 28.2), (18.2, 28.2), (18.4, 28.0), (18.4, 27.8), (18.6, 27.6),
               (19.8, 27.6), (19.9, 27.7), (19.9, 27.8), (20.3, 28.2), (22.0, 28.2), (22.4, 27.8))),
        (0.2, ((22.4, 27.8), (30.5, 19.7), (32.3, 19.7), (33.8, 21.2)), "bottom"),
        (0.2, ((33.8, 21.2), (33.9, 21.2), (34.2, 21.5), (40.1, 21.5), (42.7, 18.9), (54.8, 18.9), (55.7, 18.0),
               (_J5, 18.0))),
    )),
    dict(net="EPD_CS", pads=("U4.23", "R20.2", "TP7.1", "J5.12"),
         vias=((16.1, 6.8), (22.4, 6.8), (40.0, 10.4), (40.0, 13.0), EPD_PADS["TP7"]), tracks=(
        (0.2, ((14.1, 8.2), (14.1, 7.4), (14.7, 6.8), (16.1, 6.8))),
        (0.2, ((16.1, 6.8), (22.4, 6.8)), "bottom"),
        (0.2, ((22.4, 6.8), (36.4, 6.8), (40.0, 10.4))),
        (0.2, ((40.0, 10.4), (40.0, 13.0)), "bottom"),
        (0.2, ((40.0, 13.0), (40.0, 16.0), (40.5, 16.5), EPD_PADS["TP7"])),
        (0.2, (EPD_PADS["TP7"], (56.9, 16.5), (57.4, 17.0), (_J5, 17.0))),
    )),
    dict(net="EPD_SCK", pads=("U4.16", "TP5.1", "J5.13"), vias=((40.6, 11.8), (40.9, 13.0), EPD_PADS["TP5"]), tracks=(
        (0.2, ((23.0, 8.2), (23.0, 7.4), (23.2, 7.2), (36.0, 7.2), (40.6, 11.8))),
        (0.2, ((40.6, 11.8), (40.9, 12.1), (40.9, 13.0)), "bottom"),
        (0.2, ((40.9, 13.0), (43.4, 15.5), EPD_PADS["TP5"])),
        (0.2, (EPD_PADS["TP5"], (57.9, 15.5), (58.9, 16.5), (_J5, 16.5))),
    )),
    dict(net="EPD_MOSI", pads=("U4.26", "TP6.1", "J5.14"), vias=(EPD_PADS["TP6"],), tracks=(
        (0.2, ((10.3, 8.2), (10.3, 6.9), (11.4, 5.8), (14.0, 5.8), (16.3, 3.5), (25.7, 3.5), (26.8, 4.6), (37.1, 4.6),
               (38.4, 3.3), (44.7, 3.3), (45.6, 4.2), (45.6, 5.7), (48.5, 8.6), (48.8, 8.6), (50.2, 10.0),
               EPD_PADS["TP6"])),
        (0.2, (EPD_PADS["TP6"], (50.2, 13.4), (51.8, 15.0), (58.4, 15.0), (59.4, 16.0), (_J5, 16.0))),
    )),
    dict(net="EPD_BUSY", pads=("U4.9", "TP8.1", "J5.9"),
         vias=((16.7, 27.6), (26.2, 17.3), (32.0, 7.8), (38.8, 2.7), EPD_PADS["TP8"]), tracks=(
        (0.2, ((18.0, 25.8), (18.0, 27.2), (17.6, 27.6), (16.7, 27.6))),
        (0.2, ((16.7, 27.6), (16.7, 26.8), (26.2, 17.3)), "bottom"),
        (0.2, ((26.2, 17.3), (32.0, 11.5), (32.0, 7.8))),
        (0.2, ((32.0, 7.8), (32.0, 5.4), (34.8, 2.6), (37.1, 2.6), (37.2, 2.7), (38.8, 2.7)), "bottom"),
        # along the top edge over the boost converter and the capacitors, then down the right of
        # J5's pad row into pin 9
        (0.2, ((38.8, 2.7), (47.0, 2.7), (47.9, 1.8), (round(_UP - 1.0, 2), 1.8), (_UP, 2.8),
               EPD_PADS["TP8"])),
        (0.2, (EPD_PADS["TP8"], (_UP, 18.4), (round(_UP - 0.1, 2), 18.5), (_J5, 18.5))),
    )),
)
# The pocket closed in by the SCK line above and the CS line below (their runs down at x 40 and
# 41) is kept ground on the top layer, and so are the gaps between the lines of the staircase,
# clear of the probe pads' vias. Otherwise the router threads +3V3 through there between two
# vias, sandwiched between two display lines.
EPD_POCKETS = ((40.25, 13.4, 41.0, 16.3), (41.0, 14.2, 41.8, 16.3), (41.8, 15.0, 42.6, 16.3),
               # between SCK (y 15.5) and CS (16.5)
               (42.6, 15.7, 44.7, 16.3), (46.1, 15.7, 46.9, 16.3), (48.3, 15.7, 56.7, 16.3),
               # between CS (16.5) and DC (17.7, then 17.5)
               (46.1, 16.7, 49.1, 17.5), (51.6, 16.7, 56.7, 17.3),
               # between DC and RST (18.9)
               (44.5, 17.9, 45.3, 18.7), (46.7, 17.9, 49.1, 18.7), (51.6, 17.7, 54.6, 18.7))
PREROUTED = PREROUTED + EPD_LINES
# The boost converter, drawn by hand like the buck converter (first 2026-11-23, at the top of the
# board; drawn again on 2026-11-24 for its place below the display lines).
# Input: C25's supply pad drops straight into the inductor's. Switch node: 0.3 mm wide, straight
# from the inductor into the MOSFET's drain along y 25.0, with a stub of 0.95 mm up into the
# diode D2 and one of 1.05 mm down into the charge pump capacitor C26. Source: 1.2 mm into the
# sense resistor R19, whose ground pad has its via right above it; C25's ground pad has its via
# beside it. The bottom layer under the switch node, the MOSFET and R19 stays ground
# (DISPLAY_GROUND_AREAS).
# Sense line (no current) and gate line run from R19 and from the gate pin to the right, then up
# side by side, 0.4 mm apart, between R19 and J5's pad row into pins 3 and 2: the sense line on
# the left, since its pin is the upper one. Nothing crosses them. The gate pull-down R18 sits on
# the gate line.
# Charge pump: from C26's lower pad 2.3 mm to the right into D3 and 2.1 mm to the left into D4.
# VGH (from D2's upper pad) and VGL (from D4's left pad) have their pins and capacitors at the top
# of J5, beyond the display lines: the router takes them there on the bottom layer, as it did on
# the board of 2026-11-23.
BOOST = (
    # with the 3V3 test pad on the back, on a via of this link
    # (Every point the router may attach to is on the 0.1 mm grid: it attaches on the grid, and its
    # tidy-up cuts off as a dead end whatever does not end exactly on a track. A diagonal from the
    # capacitor's pad centre, which is off the grid, cost the board its +3V3 feed here at first.)
    dict(net="+3V3", pads=("C25.1", "L2.1", "TP2.1"), vias=((49.6, 22.6),), tracks=(
        (0.4, ((50.15, 21.4), (49.6, 21.4), (49.6, 22.6))),
        (0.4, ((49.6, 22.6), (49.6, 25.0))),
    )),
    dict(net="GND", pads=("C25.2",), vias=((53.0, 21.4),), tracks=((0.4, ((52.05, 21.4), (53.0, 21.4))),)),
    dict(net="EPD_SW", pads=("L2.2", "Q1.3", "D2.2", "C26.1"), tracks=(
        (0.3, ((52.6, 25.0), (54.9, 25.0))),
        (0.3, ((54.9, 25.0), (56.91, 25.0))),
        (0.3, ((54.9, 25.0), (54.9, 24.05))),
        (0.3, ((54.9, 25.0), (54.9, 26.05))),
    )),
    dict(net="EPD_RESE", pads=("Q1.2", "R19.1", "J5.3"), tracks=(
        (0.3, ((58.69, 24.35), (59.9, 24.35))),
        (0.2, ((59.9, 24.35), (60.3, 24.35), (60.5, 24.15), (60.5, 21.8), (60.8, 21.5), (_J5, 21.5))),
    )),
    dict(net="GND", pads=("R19.2",), vias=((59.9, 22.5),), tracks=((0.3, ((59.9, 23.33), (59.9, 22.5))),)),
    dict(net="EPD_GDR", pads=("Q1.1", "R18.1", "J5.2"), tracks=(
        (0.2, ((58.69, 25.65), (59.9, 25.65))),
        (0.2, ((59.9, 25.65), (60.6, 25.65), (60.9, 25.35), (60.9, 22.3), (61.2, 22.0), (_J5, 22.0))),
    )),
    dict(net="GND", pads=("R18.2",), vias=((59.9, 27.6),), tracks=((0.3, ((59.9, 26.67), (59.9, 27.6))),)),
    dict(net="EPD_PUMP", pads=("C26.2", "D3.2", "D4.1"), tracks=(
        (0.3, ((54.9, 27.95), (56.2, 27.95), (56.9, 27.25), (57.2, 27.25))),
        (0.3, ((54.9, 27.95), (54.5, 28.6), (54.1, 29.0), (52.85, 29.0))),
    )),
    dict(net="GND", pads=("D3.1",), vias=((58.4, 30.55),), tracks=((0.4, ((57.2, 30.55), (58.4, 30.55))),)),
)
PREROUTED = PREROUTED + BOOST
# The top layer between the MOSFET's drain pad and its source and gate pads is kept for ground:
# it is the one gap through the converter that the switch node does not close, and the router
# took a +3V3 track through it, under the MOSFET, on its way to the sensor regulator's pull-up.
BOOST_KEEP_TOP = ((57.5, 23.6, 58.1, 26.4),)
# J5's pins 17 (VSS) and 18 (VDD), drawn by hand (2026-11-24). Left to the router, pin 17's
# ground via stood right beside the pads, 0.4 mm below pin 18's line: pin 18 could not get out
# in any of sixteen runs. Now both leave to the left side by side, and pin 17's via stands
# 2.7 mm from the pads, where the lines above have fanned out; the router takes VDD on from
# the end of its stub.
J5_UPPER = (
    dict(net="EPD_VDD", pads=("J5.18",), tracks=((0.2, ((_J5, 14.0), (round(_J5 - 2.0, 2), 14.0))),)),
    dict(net="GND", pads=("J5.17",), vias=((round(_J5 - 2.7, 2), 14.5),),
         tracks=((0.2, ((_J5, 14.5), (round(_J5 - 2.7, 2), 14.5))),)),
)
PREROUTED = PREROUTED + J5_UPPER
# Five pads on the back that stood in the bottom layer's busiest stretch, between the USB
# connector and the buck converter and at the start of the sensor bus, get a short stub on the
# top layer to a via in the pad instead (2026-11-24): the router no longer has to reach them on
# the bottom layer, and three of them move to where that layer is quiet.
#   5V: from the fuse's output pad to the right, clear of the RST line.
#   3V3: on the link from the boost converter's input capacitor to its inductor (in BOOST).
#   SDA, SCL: beside their pull-ups, each from its pull-up's signal pad.
#   INT: straight up from the free end of the BMP_INT run of the sensor bus.
BACK_PAD_STUBS = (
    dict(net="+5V", pads=("TP1.1",), vias=((40.0, 19.6),),
         tracks=((0.4, ((38.9, 20.5), (39.8, 19.6), (40.0, 19.6))),)),
    dict(net="I2C_SDA", pads=("TP9.1", "R12.2"), vias=((40.3, 29.4),),
         tracks=((0.2, ((41.6, 30.1), (41.2, 30.1), (40.5, 29.4), (40.3, 29.4))),)),
    dict(net="I2C_SCL", pads=("TP10.1", "R13.2"), vias=((44.6, 30.5),),
         tracks=((0.2, ((43.2, 30.1), (43.5, 30.1), (43.9, 30.5), (44.6, 30.5))),)),
    # (1.2 mm clear of the USB connector's shell leg, a plated hole at x 37.4)
    dict(net="BMP_INT", pads=("TP12.1",), vias=((39.1, 31.6),),
         tracks=((0.2, ((38.4, 33.2), (38.4, 32.3), (39.1, 31.6))),)),
)
PREROUTED = PREROUTED + BACK_PAD_STUBS
PLACEMENT.update({"TP1": (40.0, 19.6, 0), "TP2": (49.6, 22.6, 0)})
# The buck converter's two ground connections get two vias each, drawn by hand (2026-11-23): the
# converter's ground pin with the input capacitor C1, and the output capacitor C2. On revision
# 1.0 each of the two patches of top pour they sit in had two vias; on revision 2.0's denser
# board the router's single via per patch was all that was left, a single point of failure for
# the 3.3 V supply. The link from the ground pin to C1 is the one from PREROUTED above.
BUCK_GND = (
    dict(net="GND", pads=("U2.1", "C1.2"), vias=((37.1, 15.2), (37.1, 16.3)), tracks=(
        (0.3, ((36.5, 15.7), (36.5, 16.2), (36.3, 16.4), (35.2, 16.4), (35.0, 16.6), (35.0, 16.9), (34.6, 17.3),
               (33.9, 17.3))),
        (0.3, ((36.5, 15.7), (36.5, 15.3), (36.6, 15.2), (37.1, 15.2))),
        (0.3, ((36.5, 16.2), (36.6, 16.3), (37.1, 16.3))),
    )),
    dict(net="GND", pads=("C2.2",), vias=((33.2, 9.0), (33.4, 10.2)), tracks=(
        (0.4, ((34.1, 9.0), (33.2, 9.0))),
        (0.4, ((34.1, 9.0), (34.1, 9.9), (33.8, 10.2), (33.4, 10.2))),
    )),
)
PREROUTED = tuple(g for g in PREROUTED if not (g["net"] == "GND" and g["pads"] == ("U2.1", "C1.2"))) + BUCK_GND
# R15, the pull-down on QWIIC_EN, stands right of the Qwiic regulator U9, beside the enable pin it
# holds low (2026-11-24; it stood left of U9 at 42.3 / 12.0). Its ground pad has its via drawn by
# hand, to the right, in the open bottom pour. Where it stood, its via was in the channel between
# the CS and SCK lines' vias and the DC line's run on the bottom layer, down which the router
# takes I2C_SDA and I2C_SCL: in ten of twelve seeds those two closed the via in on both layers,
# and R15 had no ground. A strip of the bottom layer kept for ground beside the via cured that
# and cost the two bus lines their way. (The ground test pads TP4, TP13 and TP14 had hand-drawn
# stubs while they were on the component side; on the back they lie in the bottom pour.)
PLACEMENT["R15"] = (47.6, 13.4, 270)       # QWIIC_EN pad up, level with U9's enable pin; ground pad down
# The enable line still comes through under U9, between its pads, as on 1.0, and now runs on from
# the enable pin to R15 on the right; its free end on the left is where the router joins it.
# Left of U9 the line passes the buck inductor L1 on the bottom layer (2026-11-24, Norman): a via
# on either side of L1, 3.5 mm on the bottom between them, under the gap between L1's pads. On the
# top layer nothing may lie under the coil (L1_UNDER), and with that strip simply closed no seed
# routed the board: the line needs this way through. It costs the bottom ground under the buck
# converter (BUCK_AREA) a slit under the inductor, 5 mm from the input loop at C1 and U2. The
# left via's place is fixed by the 3.3 V trunk that runs down beside it and by L1's pad; from
# there the router takes the line on to the module.
L1_HOP = ((34.2, 13.1), (37.7, 12.5))
PREROUTED = tuple(
    dict(net="QWIIC_EN", pads=("R15.1", "U9.3"), vias=L1_HOP, tracks=(
        (0.2, (L1_HOP[0], (34.8, 12.5), L1_HOP[1]), "bottom"),
        (0.2, (L1_HOP[1], (37.8, 12.4), (42.1, 12.4), (43.0, 11.5), (45.9, 11.5), (45.9, 12.6))),
        (0.2, ((45.9, 12.6), (46.6, 12.6), (46.9, 12.9), (47.6, 12.9))),
    )) if g["net"] == "QWIIC_EN" and "R15.1" in g["pads"] else g for g in PREROUTED)
GND_PAD_VIAS = {"R15.2": ((47.6, 13.9), (48.4, 13.9))}
PREROUTED = PREROUTED + tuple(dict(net="GND", pads=(pad_name,), vias=(via,), tracks=((0.4, (pad, via)),))
                              for pad_name, (pad, via) in GND_PAD_VIAS.items())
PLACEMENT.update({ref: (x, y, 0) for ref, (x, y) in EPD_PADS.items()})
PLACEMENT["R20"] = (*R20_AT, 0)
PLACEMENT["R21"] = (*R21_AT, 90)
PLACEMENT["TP4"] = (44.6, 24.2, 0)
SILK_LABELS = tuple(lab for lab in SILK_LABELS if lab[:3] != ("GND", 44.6, 25.1)) + (("GND", 44.6, 25.9, 0.8),)
# The I2C pull-ups move to where the hand-drawn bus starts at the bottom edge (in 1.0 they sat
# on the bus's straight run to the bridge, which revision 2.0 no longer passes): each signal pad
# drops straight onto its bus run's free end, the supply pads join the supply run to the right.
# The two probe pads sit beside them, each on its line (decided 2026-11-22).
PLACEMENT.pop("J3")
PLACEMENT.update({
    "R12": (41.6, 29.6, 270),    # SDA pull-up: above the free end of the SDA run (x 40.8-42.4)
    "R13": (43.2, 29.6, 270),    # SCL pull-up: above the free end of the SCL run (x 42.4-44.0)
    "TP9": (40.3, 29.4, 0),      # SDA probe, left of its pull-up (on the back, see BACK_PAD_STUBS)
    "TP10": (44.6, 30.5, 0),     # SCL probe, right of its pull-up
    "TP12": (39.1, 31.6, 0),     # BMP_INT probe, above the free end of the BMP_INT run
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
    # (SCK's label below its pad: above it, it lay over the ground via of R15)
    "TP5": ("SCK", "below"), "TP6": ("SDI", "right"), "TP7": ("CS", "below"), "TP8": ("BSY", "right"),
    "TP9": ("SDA", "above"), "TP10": ("SCL", "below"), "TP11": ("DC", "below"), "TP12": ("INT", "right"),
    "TP13": ("GND", "below"), "TP14": ("GND", "above"), "TP15": ("TX", "above"), "TP16": ("RX", "above"),
}
# their hand-placed labels from before go: every test pad is on the back now, so no label on the
# component side names one (the 3V3 and 5V pads moved, and their old labels had stayed behind)
SILK_LABELS = tuple(lab for lab in SILK_LABELS if lab[0] not in {text for text, _ in TP_LABELS.values()})
# SENS_EN (IO10, lower pin row) runs with the sensor bus to the regulator's pull-up R5 by U3:
# drawn by hand on the bottom layer under the bus along the bottom edge, from right of the USB
# connector to below R5; the router joins its ends. Left to the router it found no way through.
SENS_EN_FEED = (dict(net="/SENS_EN", tracks=((0.2, ((38.6, 32.6), (64.6, 32.6)), "bottom"),)),)

# Ground stitching vias (route_board.py adds them after routing, so they never block a track):
# one per 5 mm cell over the pours, at the cell's grid point if a via fits there, otherwise at the
# free spot nearest to it in that cell, looked for on a 0.5 mm raster (2026-11-23, Norman: a
# stitching pass over the whole board). Before that only the 5 mm grid points were tried, with
# extra rows at 1.5 to 2.5 mm pitch in four places; a crowded board left 77 of 98 grid points
# empty, so the vias stood in a block in the empty area left of the FPC slot and hardly anywhere
# else. Tried on the routed board: falling back to a 2.5 mm grid only gave 30 vias, with 1.25 mm
# added 35, the nearest free spot on a 0.5 mm raster 48 (0.25 mm: 53, not worth the odd positions).
# No stitching via stands within 2 mm of another ground via, and none off its grid point within
# 3.5 mm of another stitching via. The cells that stay empty lie under the ESP32 module and the
# USB connector, where no via may go, and where both layers are full of tracks. The strip between
# the slots, which carries the sensor island's ground return, gets its vias by the same rule.
STITCH_PITCH = 5.0
STITCH_SUBGRID = 0.5          # raster on which a blocked grid point's nearest free spot is looked for
STITCH_CLEAR = 2.0            # from every other ground via
STITCH_APART = 3.5            # between a via off its grid point and any other stitching via
STITCH_EXTRA = ()             # no extra rows any more
# Spots tried first for the cell they lie in when the cell's own grid point is blocked. One: the
# strip's stitching via, on the strip's centre line above the bridge's ground via.
STITCH_PREFER = ((STRIP_X, 11.0),)
# Stitching vias also stand under the ESP32 module, between its pad rows (2026-11-23, Norman):
# the router keeps tracks and its own vias out from under the module, but the top layer there
# is ground pour throughout and until now only the twelve vias of the module's ground pad tied
# it to the bottom layer, all in one spot. The antenna keep-out stays as it is.
STITCH_UNDER_MODULE = True
# Patches of pour that tracks close off and that hold no ground copper are left out of the pour by
# KiCad (island removal): 78 on the top layer and 15 on the bottom of the board of 2026-11-23,
# 206 mm2 together, among them the strips kept for ground between the display lines. After
# KiCad's fill, tie_patches() gives every such patch of at least PATCH_MIN_AREA (mm2) one via
# where it lies over connected pour of the other layer, so the copper stays (2026-11-23, Norman:
# connect them instead of dropping them). 0 switches that off. Patches where no via fits stay
# left out: those narrower than a via, and those with no connected ground on the other layer.
# A long patch tied at one spot only is a stub of ground. So a patch then gets further vias until
# no spot of it where a via fits lies more than PATCH_REACH from one of its vias (0: one via per
# patch only).
PATCH_MIN_AREA = 1.0
PATCH_REACH = 5.0
PATCH_VIA_EDGE = 0.3          # from the via's centre to the edge of the copper it stands in, both layers: the via lies wholly in ground copper
PATCH_VIA_SPACING = 0.9       # between the centres of a patch via and any other via
PATCH_VIA_PAD = 0.5           # from the via's edge to any pad, as for the stitching vias
# Start order of the router (route_board.py, `seed`): 0 = shortest connection first. Found by
# trying several with --seed=N; the one kept routes this board completely.
ROUTE_SEED = 1


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
               if g.GetClass() == "PCB_SHAPE" and g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)
               and g.GetShape() == pcbnew.SHAPE_T_CIRCLE)
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


def usb_body():
    """The USB connector's shell, from just behind its row of pads to the board edge: no track and
    no via under it, on either layer."""
    x, y = PLACEMENT["J1"][:2]
    return (x - 4.6, y - 3.3, x + 4.6, H)


def _pour_pieces(board_file):
    """The ground pours' filled copper as KiCad stored it: {layer name: [piece]}. A piece is one
    connected area of copper: dict(area in mm2, box, rows), `rows` holding the edge segments of its
    outline and of its holes by the millimetre rows of y they pass through, in board millimetres."""
    board = pcbnew.LoadBoard(str(board_file))
    out = {}
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        for layer in zone.GetLayerSet().Seq():
            polys = zone.GetFilledPolysList(layer)
            pieces = out.setdefault(board.GetLayerName(layer), [])
            for i in range(polys.OutlineCount()):
                chains = [polys.Outline(i)] + [polys.Hole(i, h) for h in range(polys.HoleCount(i))]
                area = abs(chains[0].Area()) - sum(abs(c.Area()) for c in chains[1:])
                rows = {}
                x0 = y0 = float("inf")
                x1 = y1 = -float("inf")
                for n, chain in enumerate(chains):
                    ring = [(pcbnew.ToMM(chain.CPoint(k).x) - ORIGIN[0], pcbnew.ToMM(chain.CPoint(k).y) - ORIGIN[1])
                            for k in range(chain.PointCount())]
                    if n == 0:
                        x0, y0 = min(q[0] for q in ring), min(q[1] for q in ring)
                        x1, y1 = max(q[0] for q in ring), max(q[1] for q in ring)
                    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
                        for row in range(int(min(ay, by) // 1), int(max(ay, by) // 1) + 1):
                            rows.setdefault(row, []).append((ax, ay, bx, by))
                pieces.append(dict(area=area / 1e12, box=(x0, y0, x1, y1), rows=rows))
    return out


def _edge_distance(pt, piece, near):
    """Distance from pt to the nearest edge of the piece's copper, or `near` if none is that close."""
    x, y = pt
    best = near
    for row in range(int((y - near) // 1), int((y + near) // 1) + 1):
        for ax, ay, bx, by in piece["rows"].get(row, ()):
            if min(ax, bx) - best > x or max(ax, bx) + best < x or min(ay, by) - best > y or max(ay, by) + best < y:
                continue
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
            best = min(best, ((x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2) ** 0.5)
    return best


def _in_piece(pt, piece, margin):
    """Does pt lie in the piece's copper, at least `margin` from the copper's edge?"""
    x, y = pt
    x0, y0, x1, y1 = piece["box"]
    if not (x0 + margin <= x <= x1 - margin and y0 + margin <= y <= y1 - margin):
        return False
    inside = False                              # even-odd over outline and holes together
    for ax, ay, bx, by in piece["rows"].get(int(y // 1), ()):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside and _edge_distance(pt, piece, margin) >= margin


def tie_patches(board_file, report):
    """Tie the patches of ground pour that KiCad leaves out for want of a connection to ground;
    see PATCH_MIN_AREA and PATCH_REACH. This works on KiCad's own fill: the patches are what a
    fill that keeps every piece has more than the board's.

    A via stands where both layers have copper round it (PATCH_VIA_EDGE from its centre to the
    copper's edge; that edge keeps the pour's clearance from every other net), the other layer's
    copper being joined to ground already, PATCH_VIA_SPACING from every other via, PATCH_VIA_PAD
    from every pad, not under the USB connector or a silkscreen label and not within 1 mm of a
    test pad. Spots are looked for every 0.1 mm, in strips hardly wider than a via every 0.05 mm.

    A patch gets its first via at the fitting spot deepest inside it, then further ones, each at
    the fitting spot furthest from those it has, until none is further than PATCH_REACH from one
    of them. A patch tied in one round can carry the via of a patch of the other layer in the next.

    Returns (patches tied, further vias, patches still left out, their area in mm2)."""
    from route_board import VIA_DIAMETER, VIA_DRILL
    record_file = state_file(board_file)
    avoid = stitch_avoid() + [usb_body()]
    step = 0.1
    scratch = HW / "build" / (Path(board_file).stem + ".allpour.kicad_pcb")
    tied = further = 0
    left = []

    def key(q):
        return (round(q["area"], 3), tuple(round(v, 2) for v in q["box"]))

    for round_ in range(7):
        kept = _pour_pieces(board_file)
        board = pcbnew.LoadBoard(str(board_file))
        for zone in board.Zones():
            if not zone.GetIsRuleArea():
                zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        pcbnew.SaveBoard(str(scratch), board)
        subprocess.run([KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json",
                        "-o", str(scratch.with_suffix(".json")), str(scratch)], check=True, capture_output=True)
        every = _pour_pieces(scratch)
        left = []
        for layer, other in (("F.Cu", "B.Cu"), ("B.Cu", "F.Cu")):
            have = {key(q) for q in kept.get(layer, [])}
            left += [(q, other) for q in every.get(layer, []) if key(q) not in have]
        if round_ == 6:
            break
        # the board itself, as it is on disk (the copy above only served to find the patches)
        board = pcbnew.LoadBoard(str(board_file))
        vias = [(pcbnew.ToMM(t.GetPosition().x) - ORIGIN[0], pcbnew.ToMM(t.GetPosition().y) - ORIGIN[1])
                for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
        pads = []
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                pads.append((pcbnew.ToMM(bb.GetLeft()) - ORIGIN[0], pcbnew.ToMM(bb.GetTop()) - ORIGIN[1],
                             pcbnew.ToMM(bb.GetRight()) - ORIGIN[0], pcbnew.ToMM(bb.GetBottom()) - ORIGIN[1]))
        new = []
        for patch, other in sorted(left, key=lambda q: (-q[0]["area"], q[0]["box"])):
            if patch["area"] < PATCH_MIN_AREA:
                continue
            x0, y0, x1, y1 = patch["box"]
            # where the via lies wholly in the patch's copper: every 0.1 mm, and where that just
            # misses (the middle of a strip hardly wider than a via) 0.05 mm beside it
            room = set()
            for j in range(int(y0 / step), int(y1 / step) + 2):
                for i in range(int(x0 / step), int(x1 / step) + 2):
                    pt = (round(i * step, 3), round(j * step, 3))
                    if not _in_piece(pt, patch, 0.0):
                        continue
                    depth = _edge_distance(pt, patch, PATCH_VIA_EDGE)
                    if depth >= PATCH_VIA_EDGE:
                        room.add(pt)
                    elif depth >= PATCH_VIA_EDGE - 0.75 * step:
                        room.update(q for q in ((round(pt[0] + dx * step / 2, 3), round(pt[1] + dy * step / 2, 3))
                                                for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
                                    if _in_piece(q, patch, PATCH_VIA_EDGE))
            spots = []
            for pt in sorted(room, key=lambda q: (q[1], q[0])):
                if any(a[0] - VIA_DIAMETER / 2 < pt[0] < a[2] + VIA_DIAMETER / 2 and a[1] - VIA_DIAMETER / 2 < pt[1] < a[3] + VIA_DIAMETER / 2 for a in avoid):
                    continue
                if any((pt[0] - v[0]) ** 2 + (pt[1] - v[1]) ** 2 < PATCH_VIA_SPACING ** 2 for v in vias + new):
                    continue
                if any(max(q[0] - pt[0], 0, pt[0] - q[2]) ** 2 + max(q[1] - pt[1], 0, pt[1] - q[3]) ** 2 < (VIA_DIAMETER / 2 + PATCH_VIA_PAD) ** 2 for q in pads):
                    continue
                if not any(_in_piece(pt, q, PATCH_VIA_EDGE) for q in kept.get(other, [])):
                    continue
                spots.append(pt)
            if not spots:
                continue
            own = [max(spots, key=lambda q: (round(_edge_distance(q, patch, 3.0), 3), -q[1], -q[0]))]
            tied += 1
            while PATCH_REACH:
                free = [q for q in spots if all((q[0] - v[0]) ** 2 + (q[1] - v[1]) ** 2 >= PATCH_VIA_SPACING ** 2 for v in own)]
                pt = max(free, key=lambda q: (round(min((q[0] - v[0]) ** 2 + (q[1] - v[1]) ** 2 for v in own), 4), -q[1], -q[0]), default=None)
                if pt is None or min((pt[0] - v[0]) ** 2 + (pt[1] - v[1]) ** 2 for v in own) <= PATCH_REACH ** 2:
                    break
                own.append(pt)
                further += 1
            new += own
        if not new:
            break
        gnd = board.FindNet("GND")
        for x, y in new:
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetPosition(P(x, y))
            via.SetDrill(FromMM(VIA_DRILL))
            try:
                via.SetWidth(pcbnew.F_Cu, FromMM(VIA_DIAMETER))
            except TypeError:
                via.SetWidth(FromMM(VIA_DIAMETER))
            via.SetNet(gnd)
            board.Add(via)
        pcbnew.SaveBoard(str(board_file), board)
        record = json.loads(record_file.read_text()) if record_file.exists() else {}
        record["stitched"] = [list(v) for v in record.get("stitched", [])] + [list(v) for v in new]
        record["patched"] = [list(v) for v in record.get("patched", [])] + [list(v) for v in new]
        record_file.write_text(json.dumps(record, indent=1))
        subprocess.run([KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", "--severity-all", "--format", "json",
                        "-o", str(report), str(board_file)], check=True, capture_output=True)
    for junk in (scratch, scratch.with_suffix(".json"), scratch.with_suffix(".kicad_pro"), scratch.with_suffix(".kicad_prl")):
        junk.unlink(missing_ok=True)
    return tied, further, len(left), sum(q["area"] for q, _ in left)


def fill_pours(board_file):
    """Fill the ground pours with KiCad's own filler and store the result in the board, then tie
    the patches of pour that nothing connects to ground (tie_patches). The stitching vias are
    placed on the router's estimate of the pours, the patch vias on the fill itself; where KiCad's
    fill then does not reach one of them on both layers (it reports the via as dangling or
    unconnected), that via is taken out again and the pours are filled once more. Only these vias
    are ever removed: a part's ground via left hanging stays in the board for check_pcb.py to
    report. Returns the number of vias taken out."""
    # (one report per board: several seeds are filled at the same time)
    report = HW / "build" / (Path(board_file).stem + ".fill.json")
    record = state_file(board_file)

    def fill():
        subprocess.run([KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", "--severity-all", "--format", "json",
                        "-o", str(report), str(board_file)], check=True, capture_output=True)

    def prune():
        removed = 0
        for _ in range(5):
            stitched = {(round(x, 3), round(y, 3)) for x, y in (json.loads(record.read_text()).get("stitched", []) if record.exists() else [])}
            drc = json.loads(report.read_text(encoding="utf-8"))
            loose = set()
            for v in [v for v in drc.get("violations", []) if v.get("type") == "via_dangling"] + drc.get("unconnected_items", []):
                for item in v.get("items", []):
                    pos = item.get("pos")
                    if pos and "Via" in item.get("description", ""):
                        at = (round(pos["x"] - ORIGIN[0], 3), round(pos["y"] - ORIGIN[1], 3))
                        if at in stitched:
                            loose.add(at)
            if not loose:
                break
            board = pcbnew.LoadBoard(str(board_file))
            for t in list(board.GetTracks()):
                if t.GetClass() == "PCB_VIA" and (round(pcbnew.ToMM(t.GetPosition().x) - ORIGIN[0], 3),
                                                  round(pcbnew.ToMM(t.GetPosition().y) - ORIGIN[1], 3)) in loose:
                    board.Remove(t)
                    removed += 1
            pcbnew.SaveBoard(str(board_file), board)
            fill()
        return removed

    fill()
    removed = prune()
    if PATCH_MIN_AREA:
        tied, further, left, left_area = tie_patches(board_file, report)
        removed += prune()
        print(f"{tied} patch(es) of pour tied to ground with a via, {further} further via(s) in patches reaching more than "
              f"{PATCH_REACH:g} mm from their first; {left} patch(es) still left out of the pours, {left_area:.1f} mm2")
    if removed:
        print(f"{removed} stitching or patch via(s) taken out again: KiCad's fill does not reach them on both layers")
    return removed


def kicad_open(board_file):
    """Open connections of a filled board as KiCad counts them. The router's own count has been
    wrong in both directions: it reports a pocket of pour that tie_patches() ties afterwards, and
    it has missed connections that its tidy-up cut off."""
    report = HW / "build" / (Path(board_file).stem + ".open.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--severity-all", "--format", "json", "-o", str(report), str(board_file)],
                   check=True, capture_output=True)
    return len(json.loads(report.read_text(encoding="utf-8")).get("unconnected_items", []))


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
    hand-drawn lines of the staircase (SCK, CS, DC, RST) span on the top layer from x 41 to where
    the RST line steps up to its pin."""
    x0, x1 = 41.0, 54.8
    pts = [pt for g in EPD_LINES if g["net"] in ("EPD_SCK", "EPD_CS", "EPD_DC", "EPD_RST")
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
    # KiCad has the last word on what is open (2026-11-24): the eight boards the router rates best
    # get their pours filled and are counted by KiCad. The clean ones must also pass audit_pcb.py
    # (a net crossing itself or with a loop fails it).
    t_fill = time.time()
    for r in results:
        r["kicad_open"], r["audit_ok"] = 999, False
    for r in sorted(results, key=lambda r: (r["open"], r["vias"]))[:8]:
        fill_pours(r["out"])
        r["kicad_open"] = kicad_open(r["out"])
        r["audit_ok"] = r["kicad_open"] == 0 and subprocess.run(
            [sys.executable, str(HW / "tools" / "audit_pcb.py"), r["out"]], capture_output=True).returncode == 0
        print(f"  seed {r['seed']}: KiCad counts {r['kicad_open']} open (the router {r['open']})"
              + (f", audit {'passed' if r['audit_ok'] else 'FAILED'}" if r["kicad_open"] == 0 else ""), flush=True)
    best = min(results, key=lambda r: (r["kicad_open"], not r["audit_ok"], r["bundle_supply_mm"] > 0.05, r["vias"], r["track_mm"]))
    shutil.copy(best["out"], BOARD_FILE)
    shutil.copy(state_file(best["out"]), state_file(BOARD_FILE))
    for r in results:
        for ext in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            Path(r["out"]).with_suffix(ext).unlink(missing_ok=True)
    print(f"kept seed {best['seed']} ({best['kicad_open']} open, {best['vias']} vias, {best['track_mm']} mm) -> "
          f"{BOARD_FILE.name}; pours filled and counted in {time.time() - t_fill:.0f} s; {time.time() - t0:.0f} s in total"
          + ("" if best["seed"] == ROUTE_SEED or keep is not None
             else f"; set ROUTE_SEED = {best['seed']} to get it from a single run"))
    if best["kicad_open"]:
        raise SystemExit(f"no seed routed the board completely (best: {best['kicad_open']} open)")


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
    if option("--without-panel"):
        # a copy of the board without the panel and its tail, for a picture of the parts under them
        board = pcbnew.LoadBoard(str(BOARD_FILE))
        for fp in list(board.GetFootprints()):
            if fp.GetReference() in ("PNL1", "PNL2"):
                board.Remove(fp)
        pcbnew.SaveBoard(option("--without-panel"), board)
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
        if ref in BACK_SIDE:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
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

    # --- the frame's locating holes (board only) ------------------------------------------------
    for i, (x, y) in enumerate(FRAME_HOLES, 1):
        fp = load_footprint("MountingHole:MountingHole_2.2mm_M2")
        fp.SetReference(f"FH{i}")
        fp.SetValue("frame")
        fp.SetPosition(P(x, y))
        fp.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        fp.Reference().SetVisible(False)
        board.Add(fp)

    # --- the panel itself, for the 3D view only (board only: no BOM, no placement) ---------
    # On the component side, FRAME_HEIGHT above the board, where its frame carries it.
    # --no-panel leaves it and its tail out, for a picture of the parts under it.
    show_panel = "--no-panel" not in sys.argv[1:]
    panel = pcbnew.FOOTPRINT(board)
    panel.SetReference("PNL1")
    panel.SetValue("GDEY0213B74")
    panel.Reference().SetVisible(False)
    panel.Value().SetVisible(False)
    panel.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    model = pcbnew.FP_3DMODEL()
    model.m_Filename = "${KIPRJMOD}/lib/climasense.3dshapes/GDEY0213B74.wrl"
    model.m_Offset.z = FRAME_HEIGHT
    panel.Add3DModel(model)
    panel.SetPosition(P((PANEL[0] + PANEL[2]) / 2, (PANEL[1] + PANEL[3]) / 2))
    if show_panel:
        board.Add(panel)
        add_fpc_tail(board)

    # --- where the panel goes, above the parts -----------------------------------
    # Its outline, with two ticks at the edge the tail leaves from, the room the tail's fold needs
    # and the frame's feet, all on the comments layer. Nothing of this is printed on the board:
    # the frame positions the panel.
    px0, py0, px1, py1 = PANEL
    sides = (((px0, py0), (px1, py0)), ((px1, py0), (px1, py1)), ((px0, py1), (px1, py1)),
             ((px0, py0), (px0, py1)))
    ticks = tuple(((px1 - 1.2, y), (px1, y)) for y in FPC_SHOULDER)   # the tail's edges where it leaves the glass

    def segment(layer, a, b):
        line = pcbnew.PCB_SHAPE(board)
        line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetStart(P(*a))
        line.SetEnd(P(*b))
        line.SetLayer(layer)
        line.SetWidth(FromMM(0.15))
        board.Add(line)

    def box(layer, x0, y0, x1, y1):
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            segment(layer, a, b)

    for a, b in sides + ticks:
        segment(pcbnew.Cmts_User, a, b)
    box(pcbnew.Cmts_User, *FOLD_ROOM)
    for x0, y0, x1, y1 in FRAME_FEET:
        box(pcbnew.Cmts_User, x0, y0, x1, y1)

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
        # the pads are on the back: their labels too, mirrored so that they read from there
        label.SetLayer(pcbnew.B_SilkS if ref in BACK_SIDE else pcbnew.F_SilkS)
        label.SetMirrored(ref in BACK_SIDE)
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
        start_x["GND"] = STRIP_X      # ground has no feed: its track starts, with its via, on the strip's centre line
        timing["placement"] = time.time() - t0 - timing.get("read previous board", 0.0)
        geo = dict(
            W=W, H=H,
            cutouts=[(SLOT_X[0], y1, SLOT_X[1], y2) for y1, y2 in SLOTS_Y] + list(TONGUE_CUTOUTS),
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
            usb_body=usb_body(),
            fixed_feeds=SENSOR_BUS_FEEDS,
            free_feeds=SENS_EN_FEED,
            thin_only=TONGUE_AREA,
            fixed_only=[(SLOT_X[0] - 0.3, 0, SLOT_X[1] + 0.3, H), (TONGUE_NECK_X[0], 21.5, TONGUE_NECK_X[1], 25.5)],
            fanout={"U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9", "J1", "J2", "D1", "J5", "Q1"},
            prerouted=[{**g, "net": "/" + g["net"] if "/" + g["net"] in nets else g["net"]} for g in PREROUTED],
            reserve_top=[("GND", area) for area in (*EPD_POCKETS, *BOOST_KEEP_TOP)],
            copper_free_top=[L1_UNDER],
            trunks=TRUNKS, reserve_bottom=[("GND", area) for area in (BUCK_AREA, *USB_GROUND_AREAS,
                                                                               *DISPLAY_GROUND_AREAS)],
            internally_joined=INTERNALLY_JOINED,
            # the strip below the module's bottom pad row is where its pins escape; the trunk stays out of it
            no_trunk=[(6.9, ROW_BOTTOM + 0.75, MODULE[0] + 14.2, ROW_BOTTOM + 2.55)],
            solid_pour_pads={"J1", "J2", "U1", "U2", "U3", "U9"},
            stitch_pitch=STITCH_PITCH, stitch_subgrid=STITCH_SUBGRID, stitch_clear=STITCH_CLEAR, stitch_apart=STITCH_APART,
            stitch_extra=STITCH_EXTRA, stitch_avoid=stitch_avoid(), stitch_prefer=STITCH_PREFER,
            stitch_under=(MODULE[0] - 12.75, ROW_TOP + 1.05, MODULE[0] + 12.75, ROW_BOTTOM - 1.05) if STITCH_UNDER_MODULE else None,
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
                                                        reserved=route_board.reserved_areas(geo),
                                                        stitched=geo.get("stitched", [])), indent=1))

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
        fill_pours(out_file)
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

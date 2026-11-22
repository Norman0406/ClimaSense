#!/usr/bin/env python3
"""Generate the ClimaSense revision 2.0 schematic.

Writes, relative to hardware/:
    lib/climasense.kicad_sym   project symbols (ESP32-C6-WROOM-1, SGP41, BMP580, ...)
    climasense.kicad_sch       the schematic
    climasense.kicad_pro       minimal project file (only if missing)
    sym-lib-table              project library table
    build/expected_netlist.json  nets as drawn, for check_schematic.py

This script bootstraps the design. Once PCB layout has started, the
.kicad_sch file is the source of truth and this script must not be re-run
without care - it overwrites the schematic.

Usage:  python hardware/rev-2.0/tools/gen_schematic.py
        KICAD_SYMBOL_DIR can point at a non-default KiCad symbol directory.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kisch import Library, Schematic, box_symbol, find, first, write_symbol_lib  # noqa: E402

HW = Path(__file__).resolve().parent.parent
PROJECT = "climasense"
KICAD_SYMBOL_DIR = os.environ.get("KICAD_SYMBOL_DIR", r"C:\Program Files\KiCad\10.0\share\kicad\symbols")
KICAD_CLI = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

# Passive footprints and JLCPCB part numbers (verified against the JLCPCB
# parts library on 2026-11-19).
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
RES = {  # value -> (LCSC, MPN)
    "4.7R": ("C25121", "0402WGF470KTCE"),
    "100R": ("C25076", "0402WGF1000TCE"),
    "330R": ("C25104", "0402WGF3300TCE"),
    "4.7k": ("C25900", "0402WGF4701TCE"),
    "5.1k": ("C25905", "0402WGF5101TCE"),
    "10k": ("C25744", "0402WGF1002TCE"),
    "15k": ("C25756", "0402WGF1502TCE"),
    "68k": ("C36871", "0402WGF6802TCE"),
    "100k": ("C25741", "0402WGF1003TCE"),
    # revision 2.0, display boost circuit (checked at LCSC on 2026-11-22)
    "2.2R": ("C226973", "AC0402FR-072R2L"),
    "1M": ("C26083", "0402WGF1004TCE"),
}
C0603 = "Capacitor_SMD:C_0603_1608Metric"
CAP = {  # value -> (footprint, LCSC, MPN)
    "100nF": (C0402, "C1525", "CL05B104KO5NNNC"),
    "1uF": (C0402, "C52923", "CL05A105KA5NQNC"),
    "2.2uF": (C0402, "C12530", "CL05A225MQ5NSNC"),
    "10uF": (C0805, "C15850", "CL21A106KAYNNNE"),
    "22uF": (C0805, "C45783", "CL21A226MAQNNNE"),
    # Display supply (revision 2.0). The panel's driving voltages reach about +/-20 V, and
    # Good Display asks for 0603/0805, X5R/X7R, >= 25 V: a 0402 part keeps too little of its
    # capacitance at that voltage. LCSC numbers checked at LCSC on 2026-11-22; the 1 uF part is
    # rated 50 V (the 25 V version was not found there).
    "1uF/25V": (C0603, "C15849", "CL10A105KB8NNNC"),
    "4.7uF/25V": (C0805, "C1779", "CL21A475KAQNNNE"),
}


# --------------------------------------------------------------------------
# Project symbol library
# --------------------------------------------------------------------------
def project_symbols(lib: Library) -> list[list]:
    io, pwr, pas = "bidirectional", "power_in", "passive"

    esp = box_symbol(
        "ESP32-C6-WROOM-1", "U", width=30.48, vpad=2,
        left=[("3", "EN", "input"), None,
              ("15", "IO9/BOOT", io), ("10", "IO8", io), ("23", "IO15", io), None,
              ("13", "IO12/USB_D-", io), ("14", "IO13/USB_D+", io), None,
              ("25", "TXD0/IO16", io), ("24", "RXD0/IO17", io), None,
              ("4", "IO4/MTMS", io), ("5", "IO5/MTDI", io),
              ("6", "IO6/LP_SDA", io), ("7", "IO7/LP_SCL", io)],
        right=[("8", "IO0", io), ("9", "IO1", io), ("27", "IO2", io), ("26", "IO3", io), None,
               ("11", "IO10", io), ("12", "IO11", io), None,
               ("16", "IO18", io), ("17", "IO19", io), ("18", "IO20", io),
               ("19", "IO21", io), ("20", "IO22", io), ("21", "IO23", io), None,
               ("22", "NC", "no_connect")],
        top=[("2", "3V3", pwr)],
        bottom=[("1", "GND", pwr), ("28", "GND", pwr), ("29", "EPAD", pwr)],
        footprint="climasense:ESP32-C6-WROOM-1",
        datasheet="https://documentation.espressif.com/esp32-c6-wroom-1_wroom-1u_datasheet_en.pdf",
        description="ESP32-C6 module, Wi-Fi 6 (2.4 GHz), Bluetooth 5 LE, 802.15.4, PCB antenna",
        keywords="ESP32 C6 RISC-V WiFi BLE Thread Zigbee module",
    )

    sgp41 = box_symbol(
        "SGP41", "U", width=20.32, vpad=1,
        left=[("3", "SDA", io), None, ("6", "SCL", "input")],
        top=[("1", "VDD", pwr), None, ("5", "VDDH", pwr)],
        bottom=[("2", "VSS", pwr), ("4", "NA", pas), ("7", "EP", pas)],
        footprint="climasense:Sensirion_DFN-6-1EP_2.44x2.44mm_P0.8mm_EP1.25x1.7mm",
        datasheet="https://sensirion.com/media/documents/5FE8673C/61E96F50/Sensirion_Gas_Sensors_Datasheet_SGP41.pdf",
        description="VOC and NOx sensor, I2C (0x59), 1.7-3.6 V, DFN-6 2.44x2.44 mm",
        keywords="Sensirion gas VOC NOx air quality",
    )

    bmp580 = box_symbol(
        "BMP580", "U", width=25.4, vpad=1,
        left=[("4", "SDI/SDA", io), ("2", "SCK/SCL", "input"), None, None, None],
        right=[("7", "INT", "output"), None, None, ("6", "CSB", "input"), ("5", "SDO/ADDR", "input")],
        top=[("10", "VDD", pwr), None, ("1", "VDDIO", pwr)],
        bottom=[("3", "VSS", pwr), ("8", "VSS", pwr), ("9", "VSS", pwr)],
        footprint="climasense:Bosch_LGA-10_2x2mm_P0.5mm_BMP580",
        datasheet="https://www.bosch-sensortec.com/products/environmental-sensors/pressure-sensors/bmp580/",
        description="Barometric pressure sensor, I2C (0x46/0x47), 1.71-3.6 V, LGA-10 2x2 mm",
        keywords="Bosch pressure barometer",
    )

    # RGB LED with the Everlight 19-337 pin numbering (anode/cathode pairs 4/1, 5/2, 6/3)
    led = copy.deepcopy(lib.raw("Device", "LED_RGB"))
    led[1] = "LED_RGB_19-337"
    # the KiCad graphic labels its rows R, G, B from top to bottom
    rename = {(-5.08, 5.08): ("2", "RK"), (5.08, 5.08): ("5", "RA"),
              (-5.08, 0.0): ("3", "GK"), (5.08, 0.0): ("6", "GA"),
              (-5.08, -5.08): ("1", "BK"), (5.08, -5.08): ("4", "BA")}
    for unit in find(led, "symbol"):
        unit[1] = unit[1].replace("LED_RGB", "LED_RGB_19-337", 1)
        for pin in find(unit, "pin"):
            at = first(pin, "at")
            number, name = rename[(float(str(at[1])), float(str(at[2])))]
            first(pin, "number")[1] = number
            first(pin, "name")[1] = name
    for p in find(led, "property"):
        if p[1] == "Value":
            p[2] = "LED_RGB_19-337"
        if p[1] == "Footprint":
            p[2] = "climasense:LED_RGB_Everlight_19-337_1.6x1.6mm"
        if p[1] == "Description":
            p[2] = "RGB LED, six pins, separate anodes and cathodes, Everlight 19-337 pinout"

    # Power symbols for the two switched 3.3 V rails
    rails = []
    for name, what in (("+3V3_SENS", "sensor rail"), ("+3V3_QWIIC", "Qwiic rail")):
        rail = copy.deepcopy(lib.raw("power", "+3V3"))
        rail[1] = name
        for unit in find(rail, "symbol"):
            unit[1] = unit[1].replace("+3V3", name, 1)
        for p in find(rail, "property"):
            if p[1] == "Value":
                p[2] = name
            if p[1] == "Description":
                p[2] = f'Power symbol creates a global label with name \\"{name}\\" ({what})'
        rails.append(rail)

    return [esp, sgp41, bmp580, led, *rails]


# --------------------------------------------------------------------------
# Schematic
# --------------------------------------------------------------------------
def build(lib: Library) -> Schematic:
    sch = Schematic(lib, PROJECT, "ClimaSense", "2.0", "2026-11-22", paper="A2")
    sch.power_libs["+3V3_SENS"] = "climasense:+3V3_SENS"
    sch.power_libs["+3V3_QWIIC"] = "climasense:+3V3_QWIIC"
    sch.power_libs["+5V"] = "power:+5V"
    counters = {"R": 0, "C": 0}

    def res(value, x, y, horizontal=False):
        counters["R"] += 1
        lcsc, mpn = RES[value]
        kw = dict(ref_at=(-3.81, -2.54, "left"), value_at=(2.54, -2.54, "left")) if horizontal else \
            dict(ref_at=(2.54, -2.54, "left"), value_at=(2.54, 0, "left"))
        return sch.add("Device:R", f"R{counters['R']}", value, x, y, 90 if horizontal else 0,
                       footprint=R0402, fields={"LCSC": lcsc, "MPN": mpn}, **kw)

    def cap(value, x, y):
        counters["C"] += 1
        fp, lcsc, mpn = CAP[value]
        return sch.add("Device:C", f"C{counters['C']}", value, x, y, footprint=fp,
                       fields={"LCSC": lcsc, "MPN": mpn},
                       ref_at=(3.81, -1.27, "left"), value_at=(3.81, 1.27, "left"))

    def cap_between(value, x, y, top_net, bottom_net="GND"):
        """Vertical capacitor centred at x,y with power symbols on both pins."""
        c = cap(value, x, y)
        sch.power_at(*c.pos(1), top_net, (0, -1))
        sch.power_at(*c.pos(2), bottom_net, (0, 1))
        return c

    def pullup(value, x, y, rail, net):
        r = res(value, x, y)
        sch.power_at(*r.pos(1), rail, (0, -1))
        px, py = r.pos(2)
        sch.wire((px, py), (px, py + 2.54), (px + 2.54, py + 2.54))
        sch.label_at(px + 2.54, py + 2.54, net, 0)
        return r

    def title(x, y, text):
        sch.text(x, y, text, size=2.54, bold=True)

    # ======================================================================
    # USB-C input
    # ======================================================================
    title(20.32, 22.86, "USB-C INPUT")
    j1 = sch.add("Connector:USB_C_Receptacle_USB2.0_16P", "J1", "USB-C", 38.1, 53.34,
                 footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                 fields={"LCSC": "C165948", "MPN": "TYPE-C-31-M-12"})
    # VBUS is the raw connector supply; +5V is the same rail behind the resettable fuse
    vb = j1.pos("A4")
    n_raw = (vb[0] + 5.08, vb[1])
    sch.wire(vb, n_raw)
    sch.power_at(*n_raw, "VBUS", (0, -1))
    f1 = sch.add("Device:Polyfuse", "F1", "0.75A", n_raw[0] + 8.89, vb[1], 90,
                 footprint="Fuse:Fuse_1206_3216Metric",
                 fields={"LCSC": "C371166", "MPN": "1206L075/16WR"},
                 ref_at=(-3.81, -3.81, "left"), value_at=(1.27, -3.81, "left"))
    sch.wire(n_raw, f1.pos(1))
    sch.wire(f1.pos(2), (vb[0] + 30.48, vb[1]))
    sch.power_at(vb[0] + 30.48, vb[1], "+5V", (0, -1))
    sch.label(j1, "A5", "CC1")
    sch.label(j1, "B5", "CC2")
    # D+ / D- appear on both rows of the connector; join each pair
    for a, b, net in (("A7", "B7", "USB_DN"), ("A6", "B6", "USB_DP")):
        pa, pb = j1.pos(a), j1.pos(b)
        sch.wire(pa, (pa[0] + 2.54, pa[1]))
        sch.wire(pb, (pb[0] + 2.54, pb[1]), (pa[0] + 2.54, pa[1]))
        sch.wire((pa[0] + 2.54, pa[1]), (pa[0] + 5.08, pa[1]))
        sch.junction(pa[0] + 2.54, pa[1])
        sch.label_at(pa[0] + 5.08, pa[1], net, 0)
    sch.nc(j1, "A8")
    sch.nc(j1, "B8")
    sch.power(j1, "A1", "GND")
    sch.power(j1, "SH", "GND")

    r_cc1 = res("5.1k", 76.2, 68.58)
    sch.label_at(*r_cc1.pos(1), "CC1", 0)
    sch.power_at(*r_cc1.pos(2), "GND", (0, 1))
    r_cc2 = res("5.1k", 91.44, 68.58)
    sch.label_at(*r_cc2.pos(1), "CC2", 0)
    sch.power_at(*r_cc2.pos(2), "GND", (0, 1))

    u_esd = sch.add("Power_Protection:USBLC6-2SC6", "U1", "USBLC6-2SC6", 109.22, 48.26,
                    fields={"LCSC": "C7519", "MPN": "USBLC6-2SC6"},
                    ref_at=(5.08, -7.62, "left"), value_at=(5.08, -5.08, "left"))
    sch.label(u_esd, "1", "USB_DP")
    sch.label(u_esd, "6", "USB_DP")
    sch.label(u_esd, "3", "USB_DN")
    sch.label(u_esd, "4", "USB_DN")
    sch.power(u_esd, "5", "VBUS")
    sch.power(u_esd, "2", "GND")

    # power flags tell the rule check which nets are sources
    for x, net, direction in ((99.06, "VBUS", (0, -1)), (114.3, "+5V", (0, -1)), (129.54, "GND", (0, 1))):
        sch.power_at(x, 27.94, net, direction)
        sch.wire((x, 27.94), (x + 7.62, 27.94))
        sch.flag_at(x + 7.62, 27.94)

    # ======================================================================
    # 3.3 V buck converter (MCU rail)
    # ======================================================================
    title(144.78, 22.86, "3V3 BUCK - MCU RAIL")
    u_buck = sch.add("Regulator_Switching:TPS62A01DRL", "U2", "TPS62A01DRL", 172.72, 45.72,
                     fields={"LCSC": "C5157937", "MPN": "TPS62A01DRLR"})
    vin, en = u_buck.pos(3), u_buck.pos(4)
    sch.wire(vin, (162.56, vin[1]))
    sch.wire((162.56, vin[1]), (152.4, vin[1]))
    sch.wire(en, (162.56, en[1]), (162.56, vin[1]))
    sch.junction(162.56, vin[1])
    sch.power_at(152.4, vin[1], "+5V", (0, -1))
    c_in = cap("10uF", 152.4, vin[1] + 3.81)
    sch.power_at(*c_in.pos(2), "GND", (0, 1))
    sch.power(u_buck, "1", "GND")
    sch.nc(u_buck, "6")

    sw = u_buck.pos(2)
    l1 = sch.add("Device:L", "L1", "1uH", 189.23, sw[1], 90,
                 footprint="Inductor_SMD:L_1008_2520Metric",
                 fields={"LCSC": "C435392", "MPN": "DFE252012F-1R0M=P2"},
                 ref_at=(-1.27, -2.54, "right"), value_at=(1.27, -2.54, "left"))
    sch.wire(sw, l1.pos(1))
    out_y = sw[1]
    x_fb, x_cout, x_rail = 203.2, 215.9, 228.6
    sch.wire(l1.pos(2), (x_fb, out_y))
    sch.wire((x_fb, out_y), (x_cout, out_y))
    sch.wire((x_cout, out_y), (x_rail, out_y))
    sch.junction(x_fb, out_y)
    sch.junction(x_cout, out_y)
    sch.power_at(x_rail, out_y, "+3V3", (0, -1))
    sch.wire((x_rail, out_y), (x_rail + 12.7, out_y))
    sch.flag_at(x_rail + 12.7, out_y)
    r_top = res("68k", x_fb, out_y + 3.81)
    r_bot = res("15k", x_fb, out_y + 11.43)
    sch.power_at(*r_bot.pos(2), "GND", (0, 1))
    fb = u_buck.pos(5)
    node = r_top.pos(2)
    sch.wire(node, (182.88, node[1]), (182.88, fb[1]), fb)
    sch.junction(*node)
    c_out = cap("22uF", x_cout, out_y + 3.81)
    sch.power_at(*c_out.pos(2), "GND", (0, 1))
    sch.text(144.78, 68.58, "VOUT = 0.6 V x (1 + 68k/15k) = 3.32 V", size=1.27)

    # ======================================================================
    # 3.3 V LDO (sensor rail)
    # ======================================================================
    title(266.7, 22.86, "3V3_SENS LDO - SENSOR RAIL")
    u_ldo = sch.add("Regulator_Linear:TLV75533PDBV", "U3", "TLV75533PDBV", 309.88, 45.72,
                    fields={"LCSC": "C404027", "MPN": "TLV75533PDBVR"})
    lin = u_ldo.pos(1)
    sch.wire(lin, (279.4, lin[1]))
    sch.power_at(279.4, lin[1], "+5V", (0, -1))
    c_lin = cap("1uF", 279.4, lin[1] + 3.81)
    sch.power_at(*c_lin.pos(2), "GND", (0, 1))
    sch.label(u_ldo, "3", "SENS_EN")
    sch.power(u_ldo, "2", "GND")
    lout = u_ldo.pos(5)
    sch.wire(lout, (330.2, lout[1]))
    sch.wire((330.2, lout[1]), (342.9, lout[1]))
    sch.junction(330.2, lout[1])
    sch.power_at(342.9, lout[1], "+3V3_SENS", (0, -1))
    c_lout = cap("1uF", 330.2, lout[1] + 3.81)
    sch.power_at(*c_lout.pos(2), "GND", (0, 1))
    pullup("100k", 363.22, 46.99, "+3V3", "SENS_EN")
    sch.text(266.7, 68.58,
             "SENS_EN is pulled high: sensors are on by default.\\n"
             "The MCU can pull it low to power-cycle the sensor rail.", size=1.27)

    # ======================================================================
    # MCU
    # ======================================================================
    title(20.32, 96.52, "MCU")
    u_mcu = sch.add("climasense:ESP32-C6-WROOM-1", "U4", "ESP32-C6-WROOM-1-N8", 99.06, 154.94,
                    fields={"LCSC": "C5366877", "MPN": "ESP32-C6-WROOM-1-N8"})
    mcu_nets = {
        "3": "EN", "15": "BOOT", "10": "IO8", "13": "USB_DN", "14": "USB_DP",
        "6": "I2C_SDA", "7": "I2C_SCL",
        # BMP580 interrupt on IO0 (revision 2.0; IO10 on 1.0): IO0 to IO7 can wake the chip from
        # deep sleep and be read by the low-power core. IO0/IO1 were kept free for a 32 kHz
        # crystal on 1.0; that option was dropped on 2026-11-22 (no battery variant planned).
        "8": "BMP_INT", "19": "LED_G", "20": "LED_R", "21": "LED_B",
        # e-paper display (revision 2.0). BUSY is driven by the panel, so it sits on IO3, not
        # on a start-up configuration pin (IO4, IO5, IO15 are); the ESP32 drives the others only
        # after start.
        # RST sits on IO10 (pin 11), at the module's end nearest the connector; it floats while
        # the chip is in reset, which only holds the panel in an undefined state until start.
        "26": "EPD_BUSY", "11": "EPD_RST", "4": "EPD_SCK", "5": "EPD_MOSI", "23": "EPD_CS",
        "9": "EPD_DC",
        # IO18 to IO23 have a weak pull-up while the chip is in reset (chip datasheet table 2-1),
        # IO10 and IO11 have none. An enable that must stay low in reset (QWIIC_EN, held by
        # a 100 k pull-down) therefore sits on IO11; SENS_EN, which is pulled high anyway,
        # sits on IO18.
        "12": "QWIIC_EN", "16": "SENS_EN",
        "17": "QWIIC_SDA", "18": "QWIIC_SCL",
        # UART0, on the fallback serial header J3
        "25": "UART_TX", "24": "UART_RX",
    }
    for pin, net in mcu_nets.items():
        sch.label(u_mcu, pin, net)
    sch.nc(u_mcu, "27")  # IO2, spare
    sch.power(u_mcu, "2", "+3V3")
    g = [sch.stub(u_mcu, p)[0] for p in ("1", "28", "29")]
    sch.wire(g[0], g[1])
    sch.wire(g[1], g[2])
    sch.junction(*g[1])
    sch.power_at(*g[1], "GND", (0, 1))
    cap_between("10uF", 129.54, 116.84, "+3V3")
    cap_between("100nF", 144.78, 116.84, "+3V3")

    # reset: RC on EN plus button
    r_en = res("10k", 27.94, 116.84)
    sch.power_at(*r_en.pos(1), "+3V3", (0, -1))
    n_en = r_en.pos(2)
    c_en = cap("1uF", n_en[0], n_en[1] + 3.81)
    sch.power_at(*c_en.pos(2), "GND", (0, 1))
    sw_rst = sch.add("Switch:SW_Push", "SW1", "RESET", 48.26, n_en[1],
                     footprint="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
                     fields={"LCSC": "C318884", "MPN": "TS-1187A-B-A-B"})
    sch.wire(n_en, (n_en[0] + 7.62, n_en[1]))
    sch.wire((n_en[0] + 7.62, n_en[1]), sw_rst.pos(1))
    sch.label_at(n_en[0] + 7.62, n_en[1], "EN", 0)
    sch.power(sw_rst, "2", "GND")

    # boot / user button
    r_boot = res("10k", 27.94, 149.86)
    sch.power_at(*r_boot.pos(1), "+3V3", (0, -1))
    n_boot = r_boot.pos(2)
    sw_boot = sch.add("Switch:SW_Push", "SW2", "BOOT / USER", 48.26, n_boot[1],
                      footprint="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
                      fields={"LCSC": "C318884", "MPN": "TS-1187A-B-A-B"})
    sch.wire(n_boot, (n_boot[0] + 7.62, n_boot[1]))
    sch.wire((n_boot[0] + 7.62, n_boot[1]), sw_boot.pos(1))
    sch.label_at(n_boot[0] + 7.62, n_boot[1], "BOOT", 0)
    sch.power(sw_boot, "2", "GND")

    # Fallback serial port. If USB does not work there is otherwise no way to flash the board
    # or to see its boot messages. Three holes for a pin header, not populated.
    j3 = sch.add("Connector_Generic:Conn_01x03", "J3", "UART0", 172.72, 147.32,
                 footprint="climasense:PinHeader_1x03_P2.54mm_NotFitted", in_bom=False, dnp=True)
    sch.power(j3, "1", "GND", 17.78)
    sch.label(j3, "2", "UART_TX")
    sch.label(j3, "3", "UART_RX")
    sch.text(149.86, 162.56,
             "Fallback serial port (UART0), not populated: for flashing and boot messages\\n"
             "if USB does not work. 3.3 V logic only. TX is the ESP32's output.", size=1.27)
    # test pads for a multimeter on the three supplies and ground
    for i, net in enumerate(("+5V", "+3V3", "+3V3_SENS", "GND")):
        tp = sch.add("Connector:TestPoint", f"TP{i + 1}", net.lstrip("+"), 157.48 + i * 7.62, 132.08,
                     footprint="TestPoint:TestPoint_Pad_D1.5mm", in_bom=False)
        sch.power(tp, "1", net)

    # strapping: GPIO8 must be high to enter download mode
    pullup("10k", 27.94, 172.72, "+3V3", "IO8")

    # status LED, active low
    led = sch.add("climasense:LED_RGB_19-337", "D1", "19-337/R6GHBHC-A01/2T", 182.88, 187.96,
                  fields={"LCSC": "C264519", "MPN": "19-337/R6GHBHC-A01/2T"},
                  ref_at=(0, 8.89, None), value_at=(0, 11.43, None))
    xa = led.pos(5)[0] + 5.08
    for pin in ("5", "6", "4"):
        p = led.pos(pin)
        sch.wire(p, (xa, p[1]))
    ya = [led.pos(p)[1] for p in ("5", "6", "4")]
    sch.wire((xa, ya[0]), (xa, ya[1]))
    sch.wire((xa, ya[1]), (xa, ya[2]))
    sch.junction(xa, ya[1])
    sch.wire((xa, ya[0]), (xa, ya[0] - 5.08))
    sch.power_at(xa, ya[0] - 5.08, "+3V3", (0, -1))
    for pin, value, net in (("2", "330R", "LED_R"), ("3", "100R", "LED_G"), ("1", "100R", "LED_B")):
        k = led.pos(pin)
        r = res(value, k[0] - 11.43, k[1], horizontal=True)
        sch.wire(r.pos(2), k)
        sch.label_at(r.pos(1)[0], k[1], net, 180)
    sch.text(137.16, 203.2, "Active low: drive the GPIO low to light a colour.", size=1.27)

    sch.text(20.32, 226.06,
             "Boot: IO9 low at reset enters download mode (IO8 must be high).\\n"
             "USB D+/D- go straight to the ESP32-C6 USB Serial/JTAG controller.\\n"
             "IO6/IO7 are the LP I2C pins, usable from the low-power core.\\n"
             "IO10 is unused (spare).", size=1.27)

    # ======================================================================
    # Sensors (I2C, powered from +3V3_SENS)
    # ======================================================================
    title(213.36, 96.52, "SENSORS - I2C ON +3V3_SENS (IO6 / IO7)")
    pullup("4.7k", 220.98, 116.84, "+3V3_SENS", "I2C_SDA")
    pullup("4.7k", 238.76, 116.84, "+3V3_SENS", "I2C_SCL")

    u_sht = sch.add("Sensor_Humidity:SHT4x", "U5", "SHT45-AD1B", 279.4, 119.38,
                    fields={"LCSC": "C5221601", "MPN": "SHT45-AD1B-R2"})
    sch.label(u_sht, "1", "I2C_SDA")
    sch.label(u_sht, "2", "I2C_SCL")
    sch.power(u_sht, "3", "+3V3_SENS")
    sch.power(u_sht, "4", "GND")
    cap_between("100nF", 297.18, 119.38, "+3V3_SENS")

    u_scd = sch.add("Sensor_Gas:SCD41-D-R2", "U6", "SCD41-D-R2", 340.36, 119.38,
                    fields={"LCSC": "C3659294", "MPN": "SCD41-D-R2"})
    sch.label(u_scd, "10", "I2C_SDA")
    sch.label(u_scd, "9", "I2C_SCL")
    sch.power(u_scd, "7", "+3V3_SENS")
    sch.power(u_scd, "6", "GND")
    cap_between("10uF", 373.38, 119.38, "+3V3_SENS")
    cap_between("100nF", 388.62, 119.38, "+3V3_SENS")

    u_sgp = sch.add("climasense:SGP41", "U7", "SGP41-D-R4", 279.4, 167.64,
                    fields={"LCSC": "C3659325", "MPN": "SGP41-D-R4"},
                    ref_at=(11.43, 10.16, "left"), value_at=(11.43, 12.7, "left"))
    sch.label(u_sgp, "3", "I2C_SDA")
    sch.label(u_sgp, "6", "I2C_SCL")
    sch.label(u_sgp, "1", "SGP_VDD", 5.08)
    sch.power(u_sgp, "5", "+3V3_SENS")
    g = [sch.stub(u_sgp, p)[0] for p in ("2", "4", "7")]
    sch.wire(g[0], g[1])
    sch.wire(g[1], g[2])
    sch.junction(*g[1])
    sch.power_at(*g[1], "GND", (0, 1))
    # RC filter on the logic supply, per the SGP41 datasheet
    r_sgp = res("4.7R", 228.6, 163.83)
    sch.power_at(*r_sgp.pos(1), "+3V3_SENS", (0, -1))
    n_sgp = r_sgp.pos(2)
    c_sgp = cap("1uF", n_sgp[0], n_sgp[1] + 3.81)
    sch.power_at(*c_sgp.pos(2), "GND", (0, 1))
    sch.wire(n_sgp, (n_sgp[0] - 7.62, n_sgp[1]))
    sch.flag_at(n_sgp[0] - 7.62, n_sgp[1])
    sch.wire(n_sgp, (n_sgp[0] + 7.62, n_sgp[1]))
    sch.label_at(n_sgp[0] + 7.62, n_sgp[1], "SGP_VDD", 0)
    cap_between("1uF", 297.18, 167.64, "+3V3_SENS")

    u_bmp = sch.add("climasense:BMP580", "U8", "BMP580", 335.28, 167.64,
                    fields={"LCSC": "C22391138", "MPN": "BMP580"})
    sch.label(u_bmp, "4", "I2C_SDA")
    sch.label(u_bmp, "2", "I2C_SCL")
    sch.label(u_bmp, "7", "BMP_INT")
    v = [sch.stub(u_bmp, p)[0] for p in ("10", "1")]
    mid = ((v[0][0] + v[1][0]) / 2, v[0][1])
    sch.wire(v[0], mid)
    sch.wire(mid, v[1])
    sch.power_at(*mid, "+3V3_SENS", (0, -1))
    csb, sdo = sch.stub(u_bmp, "6", 5.08)[0], sch.stub(u_bmp, "5", 5.08)[0]
    sch.wire(csb, sdo)
    sch.power_at(*csb, "+3V3_SENS", (1, 0))
    g = [sch.stub(u_bmp, p)[0] for p in ("3", "8", "9")]
    sch.wire(g[0], g[1])
    sch.wire(g[1], g[2])
    sch.junction(*g[1])
    sch.power_at(*g[1], "GND", (0, 1))
    cap_between("100nF", 378.46, 167.64, "+3V3_SENS")
    cap_between("100nF", 393.7, 167.64, "+3V3_SENS")

    # Header on the sensor side, not populated: the sensors' bus for a logic analyser, or for
    # another microcontroller if the ESP32 side does not work. The 3.3 V pin may only be fed
    # after the sensor side has been cut off the board: fed while joined and unpowered, the
    # current would run backwards through the sensor regulator U3.
    j4 = sch.add("Connector_Generic:Conn_01x05", "J4", "SENSORS", 408.94, 139.7,
                 footprint="climasense:PinHeader_1x05_P2.54mm_NotFitted", in_bom=False, dnp=True)
    sch.power(j4, "1", "GND", 17.78)
    sch.power(j4, "2", "+3V3_SENS", 22.86)
    sch.label(j4, "3", "I2C_SDA")
    sch.label(j4, "4", "I2C_SCL")
    sch.label(j4, "5", "BMP_INT")

    sch.text(350.52, 187.96,
             "I2C addresses\\n"
             "0x44  SHT45   temperature / humidity\\n"
             "0x47  BMP580  pressure (SDO high)\\n"
             "0x59  SGP41   VOC / NOx\\n"
             "0x62  SCD41   CO2", size=1.27)

    # ======================================================================
    # Qwiic: its own I2C bus and its own switched 3.3 V supply
    # ======================================================================
    # Nothing plugged in here shares a bus or a supply with the on-board sensors.
    # (These parts come last so that the numbering of the earlier ones stays as it was.)
    title(213.36, 203.2, "QWIIC - OWN I2C BUS (IO19 / IO20), OWN SWITCHED SUPPLY")
    u_q = sch.add("Regulator_Linear:TLV75533PDBV", "U9", "TLV75533PDBV", 256.54, 223.52,
                  fields={"LCSC": "C404027", "MPN": "TLV75533PDBVR"})
    qin = u_q.pos(1)
    sch.wire(qin, (218.44, qin[1]))
    sch.power_at(218.44, qin[1], "+5V", (0, -1))
    c_qin = cap("1uF", 218.44, qin[1] + 3.81)
    sch.power_at(*c_qin.pos(2), "GND", (0, 1))
    sch.label(u_q, "3", "QWIIC_EN")
    sch.power(u_q, "2", "GND")
    qout = u_q.pos(5)
    sch.wire(qout, (276.86, qout[1]))
    sch.wire((276.86, qout[1]), (287.02, qout[1]))
    sch.junction(276.86, qout[1])
    sch.power_at(287.02, qout[1], "+3V3_QWIIC", (0, -1))
    # 2.2 uF: this output has no other capacitor on it, and the regulator wants 0.47 uF that is
    # really there under voltage
    c_qout = cap("2.2uF", 276.86, qout[1] + 3.81)
    sch.power_at(*c_qout.pos(2), "GND", (0, 1))
    # pulled low: the Qwiic supply is off until the firmware turns it on
    r_qen = res("100k", 304.8, 226.06)
    sch.label_at(*r_qen.pos(1), "QWIIC_EN", 0)
    sch.power_at(*r_qen.pos(2), "GND", (0, 1))
    pullup("4.7k", 325.12, 220.98, "+3V3_QWIIC", "QWIIC_SDA")
    pullup("4.7k", 345.44, 220.98, "+3V3_QWIIC", "QWIIC_SCL")

    j2 = sch.add("Connector_Generic_MountingPin:Conn_01x04_MountingPin", "J2", "Qwiic", 391.16, 223.52,
                 footprint="Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal",
                 fields={"LCSC": "C160404", "MPN": "SM04B-SRSS-TB(LF)(SN)"})
    sch.power(j2, "1", "GND", 5.08)
    sch.power(j2, "2", "+3V3_QWIIC", 17.78)
    sch.label(j2, "3", "QWIIC_SDA")
    sch.label(j2, "4", "QWIIC_SCL")
    sch.power(j2, "MP", "GND")
    sch.text(213.36, 243.84,
             "QWIIC_EN is pulled low: the Qwiic supply is off by default. It is on IO11,\\n"
             "which has no pull-up while the ESP32 is in reset.\\n"
             "The regulator limits the current, so a short on the connector cannot pull down the board.", size=1.27)

    # ======================================================================
    # E-paper display (revision 2.0): Good Display GDEY0213B74, SSD1680, 24-pin FPC
    # ======================================================================
    # Reference circuit from the panel's specification (page 29). The panel makes its driving
    # voltages itself, switching Q1 through GDR and sensing its current on RESE; L2/Q1/D2
    # boost +3V3 to PREVGH, and C/D3/D4 pump PREVGL negative. VPP (test pin), the
    # temperature-sensor pins and NC stay open. BS1 low selects 4-wire SPI.
    title(431.8, 22.86, "E-PAPER DISPLAY - GDEY0213B74 (SSD1680), 4-WIRE SPI")

    def cap_net(value, x, y, net):
        c = cap(value, x, y)
        top = c.pos(1)
        sch.wire(top, (top[0], top[1] - 2.54))
        sch.label_at(top[0], top[1] - 2.54, net, 90)
        sch.power_at(*c.pos(2), "GND", (0, 1))
        return c

    j5 = sch.add("Connector_Generic_MountingPin:Conn_01x24_MountingPin", "J5", "GDEY0213B74", 556.26, 101.6,
                 footprint="Connector_FFC-FPC:Hirose_FH12-24S-0.5SH_1x24-1MP_P0.50mm_Horizontal",
                 fields={"LCSC": "C3249999", "MPN": "KH-FPC0.5-H2.0SMT-24P-QCHF"},
                 ref_at=(0, -33.02, None), value_at=(0, 35.56, None))
    fpc = {
        "2": "EPD_GDR", "3": "EPD_RESE", "5": "EPD_VSH2", "9": "EPD_BUSY", "10": "EPD_RST",
        "11": "EPD_DC", "12": "EPD_CS", "13": "EPD_SCK", "14": "EPD_MOSI", "18": "EPD_VDD",
        "20": "EPD_VSH1", "21": "EPD_VGH", "22": "EPD_VSL", "23": "EPD_VGL", "24": "EPD_VCOM",
    }
    # The keys above are the panel's pin numbers. On the board the tail makes a U-turn
    # through its slot into the connector, which puts the panel's pin 1 on the connector's
    # pin 24 (see gen_pcb.py, "Revision 2.0"). The connector's pins are wired accordingly.
    FPC_REVERSED = True

    def cpin(panel_pin):
        return str(25 - int(panel_pin)) if FPC_REVERSED else panel_pin

    for pin, net in fpc.items():
        sch.label(j5, cpin(pin), net, 5.08)
    for pin in ("15", "16"):  # VDDIO, VCI
        sch.power(j5, cpin(pin), "+3V3", 5.08)
    for pin in ("8", "17"):   # BS1 (4-wire SPI), VSS
        sch.power(j5, cpin(pin), "GND", 5.08)
    sch.power(j5, "MP", "GND")
    for pin in ("1", "4", "6", "7", "19"):
        sch.nc(j5, cpin(pin))

    # supply and driving-voltage capacitors, 25 V
    for i, net in enumerate(("+3V3", "EPD_VDD", "EPD_VSH1", "EPD_VSH2", "EPD_VSL",
                             "EPD_VGH", "EPD_VGL", "EPD_VCOM")):
        x = 439.42 + i * 10.16
        if net == "+3V3":
            cap_between("1uF/25V", x, 160.02, "+3V3")
        else:
            cap_net("1uF/25V", x, 160.02, net)

    # boost converter
    l2 = sch.add("Device:L", "L2", "47uH", 457.2, 53.34, 90,
                 # Good Display names NR3015 (3 x 3 mm), but those carry only 300 mA; this 4 x 4 mm
                 # part is rated 720 mA. Footprint: Sunlord's SWPA4030S, which the APV part copies
                 # (to be checked against APV's drawing).
                 footprint="Inductor_SMD:L_Sunlord_SWPA4030S",
                 fields={"LCSC": "C5363795", "MPN": "APSWPA4030S470MTF"},
                 ref_at=(-1.27, -2.54, "right"), value_at=(1.27, -2.54, "left"))
    lin = l2.pos(1)
    sch.wire(lin, (lin[0] - 7.62, lin[1]))
    sch.power_at(lin[0] - 7.62, lin[1], "+3V3", (0, -1))
    c_bin = cap("4.7uF/25V", lin[0] - 7.62, lin[1] + 3.81)
    sch.power_at(*c_bin.pos(2), "GND", (0, 1))
    lsw = l2.pos(2)
    sch.wire(lsw, (lsw[0] + 2.54, lsw[1]))
    sch.label_at(lsw[0] + 2.54, lsw[1], "EPD_SW", 0)

    q1 = sch.add("Transistor_FET:Si1308EDL", "Q1", "Si1308EDL", 457.2, 81.28,
                 fields={"LCSC": "C469327", "MPN": "SI1308EDL-T1-GE3"})
    sch.label(q1, "3", "EPD_SW")
    sch.label(q1, "1", "EPD_GDR")
    sch.label(q1, "2", "EPD_RESE")
    r_gate = res("1M", 444.5, 96.52)
    sch.label_at(*r_gate.pos(1), "EPD_GDR", 90)
    sch.power_at(*r_gate.pos(2), "GND", (0, 1))
    r_sense = res("2.2R", 469.9, 96.52)
    sch.label_at(*r_sense.pos(1), "EPD_RESE", 90)
    sch.power_at(*r_sense.pos(2), "GND", (0, 1))

    diodes = []
    for i, (anode, cathode) in enumerate((("EPD_SW", "EPD_VGH"),      # boost to PREVGH
                                          ("EPD_PUMP", "GND"),         # charge pump, ground side
                                          ("EPD_VGL", "EPD_PUMP"))):   # charge pump to PREVGL
        d = sch.add("Diode:MBR0530", f"D{i + 2}", "MBR0530", 495.3, 53.34 + i * 15.24, 0,
                    # onsemi part: Vf <= 430 mV at 0.5 A, as Good Display asks. JSCJ's MBR0530
                    # (C77336) is cheaper but specifies 550 mV. LCSC number not yet confirmed.
                    fields={"LCSC": "C232832", "MPN": "MBR0530T1G"})
        sch.label(d, "2", anode)
        if cathode == "GND":
            sch.power(d, "1", "GND")
        else:
            sch.label(d, "1", cathode)
        diodes.append(d)
    c_pump = cap("4.7uF/25V", 515.62, 99.06)
    top = c_pump.pos(1)
    sch.wire(top, (top[0], top[1] - 2.54))
    sch.label_at(top[0], top[1] - 2.54, "EPD_SW", 90)
    bot = c_pump.pos(2)
    sch.wire(bot, (bot[0], bot[1] + 2.54))
    sch.label_at(bot[0], bot[1] + 2.54, "EPD_PUMP", 270)

    sch.text(431.8, 182.88,
             "Values from the GDEY0213B74 specification, reference circuit (page 29).\\n"
             "Capacitors 0603/0805, X5R/X7R, 25 V. PREVGH/PREVGL reach about +/-20 V.\\n"
             "The panel sits on the back of the board; its FPC passes through a slot and turns\\n"
             "back into J5, so panel pin N is connector pin 25 - N.", size=1.27)
    return sch


def main():
    lib = Library(KICAD_SYMBOL_DIR)
    symbols = project_symbols(lib)
    for s in symbols:
        lib.add_project_symbol(PROJECT, s)
    (HW / "lib").mkdir(exist_ok=True)
    (HW / "build").mkdir(exist_ok=True)
    write_symbol_lib(HW / "lib" / f"{PROJECT}.kicad_sym", symbols)

    sch = build(lib)
    nets = sch.netlist()
    (HW / f"{PROJECT}.kicad_sch").write_text(sch.render(), encoding="utf-8", newline="\n")
    (HW / "build" / "expected_netlist.json").write_text(
        json.dumps({k: sorted(map(list, v)) for k, v in sorted(nets.items())}, indent=1), encoding="utf-8")

    (HW / "sym-lib-table").write_text(
        '(sym_lib_table\n\t(version 7)\n\t(lib (name "climasense") (type "KiCad") '
        '(uri "${KIPRJMOD}/lib/climasense.kicad_sym") (options "") (descr "ClimaSense project symbols"))\n)\n',
        encoding="utf-8", newline="\n")

    pro = HW / f"{PROJECT}.kicad_pro"
    if not pro.exists():
        pro.write_text(json.dumps({
            "board": {}, "boards": [],
            "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
            "meta": {"filename": pro.name, "version": 3},
            "net_settings": {}, "pcbnew": {}, "schematic": {},
            "sheets": [[sch.root_uuid, "Root"]], "text_variables": {},
        }, indent=2) + "\n", encoding="utf-8", newline="\n")

    # let KiCad re-save the file so its formatting matches what the GUI writes
    if Path(KICAD_CLI).exists():
        subprocess.run([KICAD_CLI, "sch", "upgrade", "--force", str(HW / f"{PROJECT}.kicad_sch")],
                       check=True, capture_output=True)
    else:
        print(f"note: kicad-cli not found at {KICAD_CLI}; schematic left in generator formatting")

    print(f"{len(sch.parts)} parts, {len(nets)} nets")
    for name, members in sorted(nets.items()):
        print(f"  {name:12s} " + " ".join(f"{r}.{p}" for r, p in sorted(members)))


if __name__ == "__main__":
    main()

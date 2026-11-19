"""Small helper library for generating KiCad 10 schematics from Python.

Only what the ClimaSense generator needs: S-expression parsing, pulling symbols
out of the installed KiCad libraries, placing them, wiring by net label /
power symbol, and a built-in connectivity model so the result can be compared
against the netlist KiCad itself exports.

Standard library only.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path

GRID = 1.27
SCH_VERSION = 20260306
LIB_VERSION = 20251024
_NS = uuid.UUID("6f1d3c0e-5a54-4b53-9d0b-c11a5e45e000")


# --------------------------------------------------------------------------
# S-expressions
# --------------------------------------------------------------------------
class Sym(str):
    """A bare (unquoted) token."""


def parse(text: str):
    i, n = 0, len(text)
    stack, cur, root = [], None, None
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            new = []
            if cur is not None:
                cur.append(new)
                stack.append(cur)
            cur = new
            i += 1
        elif c == ")":
            if stack:
                cur = stack.pop()
            else:
                root, cur = cur, None
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while text[j] != '"':
                if text[j] == "\\":
                    buf.append(text[j : j + 2])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            cur.append("".join(buf))  # kept in escaped form
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()":
                j += 1
            cur.append(Sym(text[i:j]))
            i = j
    return root


def dump(node, indent: int = 0) -> str:
    if isinstance(node, list):
        if all(not isinstance(x, list) for x in node):
            return "(" + " ".join(dump(x) for x in node) + ")"
        pad = "\t" * (indent + 1)
        out = "(" + dump(node[0])
        for x in node[1:]:
            if isinstance(x, list):
                out += "\n" + pad + dump(x, indent + 1)
            else:
                out += " " + dump(x)
        return out + "\n" + "\t" * indent + ")"
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, str):
        return '"' + node + '"'
    if isinstance(node, float):
        return fmt(node)
    return str(node)


def S(*items):
    """Build a list node; the first item is the keyword."""
    return [Sym(items[0]), *items[1:]]


def find(node, key):
    return [x for x in node[1:] if isinstance(x, list) and x and x[0] == key]


def first(node, key):
    r = find(node, key)
    return r[0] if r else None


def fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def num(v) -> float:
    return float(str(v))


def uid(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


def on_grid(v: float) -> bool:
    return abs(v / GRID - round(v / GRID)) < 1e-6


def P(x: float, y: float) -> tuple[float, float]:
    return (round(x, 4), round(y, 4))


# --------------------------------------------------------------------------
# Symbol libraries
# --------------------------------------------------------------------------
def effects(size: float = 1.27, justify: str | None = None, bold: bool = False):
    font = S("font", S("size", size, size))
    if bold:
        font.append(S("bold", Sym("yes")))
    e = S("effects", font)
    if justify:
        e.append(S("justify", *[Sym(j) for j in justify.split()]))
    return e


def prop(name, value, x=0.0, y=0.0, angle=0, hide=False, justify=None, size=1.27):
    p = S("property", name, value, S("at", x, y, angle))
    if hide:
        p.append(S("hide", Sym("yes")))
    p.append(S("show_name", Sym("no")))
    p.append(S("do_not_autoplace", Sym("no")))
    p.append(effects(size, justify))
    return p


class Library:
    """Read-only access to an installed KiCad symbol library directory."""

    def __init__(self, symbol_dir: str | Path):
        self.dir = Path(symbol_dir)
        self._cache: dict[str, list] = {}
        self.extra: dict[str, dict[str, list]] = {}  # project libs: name -> {symbol: node}

    def add_project_symbol(self, lib: str, node: list):
        self.extra.setdefault(lib, {})[node[1]] = node

    def _lib(self, name: str):
        if name not in self._cache:
            path = self.dir / f"{name}.kicad_sym"
            self._cache[name] = parse(path.read_text(encoding="utf-8"))
        return self._cache[name]

    def raw(self, lib: str, name: str):
        if lib in self.extra:
            return self.extra[lib][name]
        for s in find(self._lib(lib), "symbol"):
            if s[1] == name:
                return s
        raise KeyError(f"{lib}:{name}")

    def flat(self, lib: str, name: str):
        """Return the symbol with any `extends` parent merged in."""
        sym = self.raw(lib, name)
        ext = first(sym, "extends")
        if ext is None:
            return sym
        parent = self.flat(lib, ext[1])
        pname = parent[1]
        out = [Sym("symbol"), name]
        out += [x for x in parent[2:] if isinstance(x, list) and x[0] not in ("property", "symbol", "embedded_fonts")]
        props = {p[1]: p for p in find(parent, "property")}
        for p in find(sym, "property"):
            props[p[1]] = p
        out += list(props.values())
        for unit in find(parent, "symbol"):
            out.append([Sym("symbol"), name + unit[1][len(pname) :], *unit[2:]])
        out.append(S("embedded_fonts", Sym("no")))
        return out


def symbol_pins(sym) -> list[dict]:
    pins = []
    for unit in find(sym, "symbol"):
        for p in find(unit, "pin"):
            at = first(p, "at")
            pins.append(
                {
                    "number": first(p, "number")[1],
                    "name": first(p, "name")[1],
                    "type": str(p[1]),
                    "x": num(at[1]),
                    "y": num(at[2]),
                    "angle": int(num(at[3])) if len(at) > 3 else 0,
                    "hidden": first(p, "hide") is not None,
                }
            )
    return pins


def make_pin(number, name, etype, x, y, angle, length=2.54):
    return S(
        "pin", Sym(etype), Sym("line"),
        S("at", x, y, angle), S("length", length),
        S("name", name, effects()), S("number", number, effects()),
    )


def box_symbol(name, ref, left=(), right=(), top=(), bottom=(), width=20.32, value=None,
               footprint="", datasheet="", description="", keywords="", vpad=0):
    """Rectangular symbol. Pin lists hold (number, name, type) tuples or None
    for a blank row. Pins sit on a 2.54 mm pitch. `vpad` adds blank rows above
    and below so the names of top/bottom pins do not run into side pin names."""
    rows = max(len(left), len(right), 1)
    # keep horizontal pins on the 2.54 grid
    y0 = math.floor(((rows - 1) * 2.54 / 2) / 2.54) * 2.54
    half_h = y0 + 2.54 * (1 + vpad)
    bottom_y = -(y0 - (rows - 1) * 2.54) + 2.54 * (1 + vpad)
    half_w = width / 2
    unit = [Sym("symbol"), f"{name}_1_1",
            S("rectangle", S("start", -half_w, half_h), S("end", half_w, -bottom_y),
              S("stroke", S("width", 0.254), S("type", Sym("default"))),
              S("fill", S("type", Sym("background"))))]
    for i, p in enumerate(left):
        if p:
            unit.append(make_pin(p[0], p[1], p[2], -half_w - 2.54, y0 - i * 2.54, 0))
    for i, p in enumerate(right):
        if p:
            unit.append(make_pin(p[0], p[1], p[2], half_w + 2.54, y0 - i * 2.54, 180))

    def spread(pins):
        n = len(pins)
        start = -((n - 1) // 2) * 2.54
        return [(start + i * 2.54, p) for i, p in enumerate(pins) if p]

    for x, p in spread(top):
        unit.append(make_pin(p[0], p[1], p[2], x, half_h + 2.54, 270))
    for x, p in spread(bottom):
        unit.append(make_pin(p[0], p[1], p[2], x, -bottom_y - 2.54, 90))

    return [
        Sym("symbol"), name,
        S("exclude_from_sim", Sym("no")), S("in_bom", Sym("yes")), S("on_board", Sym("yes")),
        S("in_pos_files", Sym("yes")), S("duplicate_pin_numbers_are_jumpers", Sym("no")),
        prop("Reference", ref, half_w + 1.27, half_h + 3.81, justify="left"),
        prop("Value", value or name, half_w + 1.27, half_h + 1.27, justify="left"),
        prop("Footprint", footprint, hide=True),
        prop("Datasheet", datasheet, hide=True),
        prop("Description", description, hide=True),
        prop("ki_keywords", keywords, hide=True),
        unit,
        S("embedded_fonts", Sym("no")),
    ]


def write_symbol_lib(path: Path, symbols: list[list]):
    root = [Sym("kicad_symbol_lib"), S("version", LIB_VERSION),
            S("generator", "climasense_gen"), S("generator_version", "10.0"), *symbols]
    path.write_text(dump(root) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Schematic
# --------------------------------------------------------------------------
_ROT = {0: (1, 0, 0, -1), 90: (0, -1, -1, 0), 180: (-1, 0, 0, 1), 270: (0, 1, 1, 0)}
_DIR_ANGLE = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}  # schematic coords, y down


class Part:
    def __init__(self, sch, lib_id, ref, value, x, y, rot, sym):
        self.sch, self.lib_id, self.ref, self.value = sch, lib_id, ref, value
        self.x, self.y, self.rot, self.sym = x, y, rot, sym
        self.pins = symbol_pins(sym)

    def _pin(self, number):
        for p in self.pins:
            if p["number"] == str(number):
                return p
        raise KeyError(f"{self.ref} has no pin {number}")

    def _xf(self, x, y):
        a, b, c, d = _ROT[self.rot]
        return (a * x + b * y, c * x + d * y)

    def pos(self, number):
        p = self._pin(number)
        dx, dy = self._xf(p["x"], p["y"])
        return P(self.x + dx, self.y + dy)

    def out_dir(self, number):
        """Unit vector pointing away from the symbol body (schematic coords)."""
        p = self._pin(number)
        a = math.radians(p["angle"])
        dx, dy = self._xf(-math.cos(a), -math.sin(a))
        return (round(dx), round(dy))


class Schematic:
    def __init__(self, lib: Library, project: str, title: str, rev: str, date: str, paper="A3"):
        self.lib, self.project = lib, project
        self.title, self.rev, self.date, self.paper = title, rev, date, paper
        self.root_uuid = uid(f"{project}/root")
        self.used: dict[str, list] = {}
        self.parts: list[Part] = []
        self.items: list[list] = []
        self.segments: list[tuple] = []
        self.junctions: set = set()
        self.labels: list[tuple] = []          # (point, name)
        self.powers: list[tuple] = []          # (point, net)
        self.flags: list[tuple] = []
        self.ncs: set = set()
        self._n = 0
        self._pwr = 0
        self._flg = 0
        self.power_libs = {"GND": "power:GND", "+3V3": "power:+3V3", "VBUS": "power:VBUS"}

    # -- helpers ----------------------------------------------------------
    def _uid(self, kind):
        self._n += 1
        return uid(f"{self.project}/{kind}/{self._n}")

    def _symbol(self, lib_id):
        if lib_id not in self.used:
            lib, name = lib_id.split(":")
            flat = self.lib.flat(lib, name)
            self.used[lib_id] = [Sym("symbol"), lib_id, *flat[2:]]
        return self.used[lib_id]

    @staticmethod
    def _check(*pts):
        for x, y in pts:
            assert on_grid(x) and on_grid(y), f"off-grid point {x},{y}"

    # -- placement --------------------------------------------------------
    def add(self, lib_id, ref, value, x, y, rot=0, footprint=None, fields=None,
            ref_at=None, value_at=None, in_bom=True, hide_value=False):
        self._check((x, y))
        sym = self._symbol(lib_id)
        part = Part(self, lib_id, ref, value, x, y, rot, sym)
        self.parts.append(part)
        lp = {p[1]: p for p in find(sym, "property")}

        def field_pos(name, override, default_justify=None):
            if override:
                fx, fy, just = (*override, None)[:3] if len(override) == 2 else override
                return x + fx, y + fy, just
            at = first(lp[name], "at")
            eff = first(lp[name], "effects")
            just = first(eff, "justify") if eff else None
            jtxt = " ".join(str(j) for j in just[1:]) if just else default_justify
            dx, dy = num(at[1]), num(at[2])
            return x + dx, y - dy, jtxt

        rx, ry, rj = field_pos("Reference", ref_at)
        vx, vy, vj = field_pos("Value", value_at)
        is_power = ref.startswith("#")
        # field angles are relative to the symbol: 90 keeps text horizontal on a rotated part
        fa = 90 if rot in (90, 270) else 0
        if rot == 90:  # KiCad mirrors the horizontal justification at this rotation
            swap = {"left": "right", "right": "left"}
            rj, vj = swap.get(rj, rj), swap.get(vj, vj)
        node = [
            Sym("symbol"), S("lib_id", lib_id), S("at", x, y, rot), S("unit", 1), S("body_style", 1),
            S("exclude_from_sim", Sym("no")), S("in_bom", Sym("yes" if in_bom else "no")),
            S("on_board", Sym("yes")), S("in_pos_files", Sym("yes")), S("dnp", Sym("no")),
            S("uuid", self._uid("sym")),
            prop("Reference", ref, rx, ry, fa, hide=is_power, justify=rj),
            prop("Value", value, vx, vy, fa, hide=hide_value, justify=vj),
        ]
        fp = footprint if footprint is not None else lp["Footprint"][2]
        node.append(prop("Footprint", fp, x, y, hide=True))
        node.append(prop("Datasheet", lp["Datasheet"][2] if "Datasheet" in lp else "", x, y, hide=True))
        node.append(prop("Description", lp["Description"][2] if "Description" in lp else "", x, y, hide=True))
        for k, v in (fields or {}).items():
            node.append(prop(k, v, x, y, hide=True))
        for p in part.pins:
            node.append(S("pin", p["number"], S("uuid", self._uid("pin"))))
        node.append(S("instances", S("project", self.project,
                                     S("path", "/" + self.root_uuid, S("reference", ref), S("unit", 1)))))
        self.items.append(node)
        return part

    # -- primitives -------------------------------------------------------
    def wire(self, *pts):
        pts = [P(*p) for p in pts]
        self._check(*pts)
        for a, b in zip(pts, pts[1:]):
            assert a != b and (a[0] == b[0] or a[1] == b[1]), f"bad wire {a}->{b}"
            self.segments.append((a, b))
            self.items.append(S("wire", S("pts", S("xy", *a), S("xy", *b)),
                                S("stroke", S("width", 0), S("type", Sym("default"))),
                                S("uuid", self._uid("wire"))))

    def junction(self, x, y):
        pt = P(x, y)
        self.junctions.add(pt)
        self.items.append(S("junction", S("at", *pt), S("diameter", 0), S("color", 0, 0, 0, 0),
                            S("uuid", self._uid("junction"))))

    def label_at(self, x, y, name, angle=0):
        pt = P(x, y)
        self._check(pt)
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[angle]
        self.labels.append((pt, name))
        self.items.append(S("label", name, S("at", *pt, angle), effects(justify=just),
                            S("uuid", self._uid("label"))))

    def power_at(self, x, y, net, direction=(0, -1)):
        """Power symbol with its pin at x,y, drawn pointing in `direction`."""
        pt = P(x, y)
        self._check(pt)
        gnd = net == "GND"
        natural = (0, 1) if gnd else (0, -1)
        rot = {((0, -1), (0, -1)): 0, ((0, -1), (-1, 0)): 90, ((0, -1), (0, 1)): 180, ((0, -1), (1, 0)): 270,
               ((0, 1), (0, 1)): 0, ((0, 1), (1, 0)): 90, ((0, 1), (0, -1)): 180, ((0, 1), (-1, 0)): 270}[(natural, direction)]
        self._pwr += 1
        off = 3.81 if gnd else 3.556
        vx, vy = direction[0] * off, direction[1] * off
        just = {(-1, 0): "right", (1, 0): "left"}.get(direction)
        if direction[0]:
            vx = direction[0] * (off + 0.5)
        self.add(self.power_libs[net], f"#PWR{self._pwr:03d}", net, pt[0], pt[1], rot,
                 ref_at=(0, 0), value_at=(vx, vy, just), hide_value=gnd and direction != (0, 1))
        self.parts.pop()  # power symbols are not real parts
        self.powers.append((pt, net))

    def flag_at(self, x, y):
        pt = P(x, y)
        self._flg += 1
        self.add("power:PWR_FLAG", f"#FLG{self._flg:02d}", "PWR_FLAG", pt[0], pt[1], 0,
                 ref_at=(0, 0), value_at=(0, -5.08))
        self.parts.pop()
        self.flags.append(pt)

    def text(self, x, y, s, size=1.27, bold=False):
        self.items.append(S("text", s, S("exclude_from_sim", Sym("no")), S("at", x, y, 0),
                            effects(size, "left bottom", bold), S("uuid", self._uid("text"))))

    def box(self, x1, y1, x2, y2):
        self.items.append(S("rectangle", S("start", x1, y1), S("end", x2, y2),
                            S("stroke", S("width", 0), S("type", Sym("dash"))),
                            S("fill", S("type", Sym("none"))), S("uuid", self._uid("rect"))))

    # -- pin-level connections -------------------------------------------
    def stub(self, part, pin, length=2.54):
        x, y = part.pos(pin)
        dx, dy = part.out_dir(pin)
        end = P(x + dx * length, y + dy * length)
        if length:
            self.wire((x, y), end)
        return end, (dx, dy)

    def label(self, part, pin, name, length=2.54):
        end, d = self.stub(part, pin, length)
        self.label_at(end[0], end[1], name, _DIR_ANGLE[d])
        return end

    def power(self, part, pin, net, length=2.54):
        end, d = self.stub(part, pin, length)
        self.power_at(end[0], end[1], net, d)
        return end

    def nc(self, part, pin):
        pt = part.pos(pin)
        self.ncs.add(pt)
        self.items.append(S("no_connect", S("at", *pt), S("uuid", self._uid("nc"))))

    # -- connectivity model ----------------------------------------------
    def netlist(self) -> dict[str, set]:
        """Nets as {name: {(ref, pin), ...}} according to the drawn geometry."""
        parent: dict = {}

        def root(p):
            parent.setdefault(p, p)
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        def union(a, b):
            parent[root(a)] = root(b)

        for a, b in self.segments:
            union(a, b)
        pin_pts = [(part.pos(p["number"]), part.ref, p["number"]) for part in self.parts for p in part.pins]
        attach = [pt for pt, *_ in pin_pts] + [pt for pt, _ in self.labels] + [pt for pt, _ in self.powers] + self.flags
        ends = {e for seg in self.segments for e in seg}
        # refuse geometry KiCad might interpret differently from this model
        for pt in set(attach) | ends:
            for a, b in self.segments:
                inside = (a[0] == b[0] == pt[0] and min(a[1], b[1]) < pt[1] < max(a[1], b[1])) or \
                         (a[1] == b[1] == pt[1] and min(a[0], b[0]) < pt[0] < max(a[0], b[0]))
                assert not inside, f"point {pt} lies inside wire {a}->{b}; split the wire there"
        for pt in attach:
            root(pt)
        names: dict = {}
        for pt, name in self.powers + self.labels:
            r = root(pt)
            if r in names and names[r] != name:
                raise AssertionError(f"nets {names[r]} and {name} are shorted at {pt}")
            names[r] = name
        nets: dict[str, set] = {}
        unnamed = 0
        groups: dict = {}
        for pt, ref, number in pin_pts:
            groups.setdefault(root(pt), set()).add((ref, number))
        for r, members in groups.items():
            if r in names:
                nets.setdefault(names[r], set()).update(members)
            elif len(members) > 1 or r in {root(e) for e in ends}:
                unnamed += 1
                nets[f"<unnamed {unnamed}: {sorted(members)[0]}>"] = members
            else:
                (ref, number), = members
                pt = next(p for p, rf, nb in pin_pts if rf == ref and nb == number)
                part = next(p for p in self.parts if p.ref == ref)
                if pt not in self.ncs and part._pin(number)["type"] != "no_connect":
                    raise AssertionError(f"{ref} pin {number} is unconnected and has no no-connect flag")
        return nets

    # -- output -----------------------------------------------------------
    def render(self) -> str:
        root = [
            Sym("kicad_sch"), S("version", SCH_VERSION), S("generator", "eeschema"),
            S("generator_version", "10.0"), S("uuid", self.root_uuid), S("paper", self.paper),
            S("title_block", S("title", self.title), S("date", self.date), S("rev", self.rev)),
            [Sym("lib_symbols"), *self.used.values()],
            *self.items,
            S("sheet_instances", S("path", "/", S("page", "1"))),
            S("embedded_fonts", Sym("no")),
        ]
        return dump(root) + "\n"

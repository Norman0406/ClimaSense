"""Route the ClimaSense board. Called by gen_pcb.py after the parts are placed.

Strategy
--------
* Every net except ground is routed as tracks by the grid router in router.py.
* The five nets that go to the sensor island cross the middle bridge on fixed,
  thin, parallel tracks, so as little copper as possible conducts heat across.
* Ground on the main part of the board is two copper pours (top and bottom);
  every ground pad there gets a short track to a via.
* Ground on the sensor island is routed as tracks: no pours there, so the
  island's own warm parts do not spread their heat to the SHT45.
* Nothing is routed under the ESP32 module on the top layer, and nothing at
  all near the antenna.
* Pads of fine-pitch parts first get a short escape stub pointing away from
  the part, so later tracks cannot box a pad in between its neighbours.
* A few connections are not left to the router at all: gen_pcb.py draws them
  by hand (the buck converter's input loop, the link between the SCD41's two
  supply pins, the ESP32's supply pin to its capacitors). They are laid down
  first and the router connects to them like to any other copper.
* The supply trunk from the buck converter to the ESP32 is routed before the
  signals, as wide as it fits.

The router lays connections one after another, shortest first across all nets,
and never moves a track once it is down, so the order matters. When a
connection cannot be made, the whole board is routed again with that
connection moved earlier; the best attempt is kept.
"""

from __future__ import annotations

import math
import time

import pcbnew
from pcbnew import FromMM, VECTOR2I

from router import BLOCK, BOT, FREE, TOP, Router

W_SIG, W_PWR, W_WIDE = 0.2, 0.4, 0.6
WIDTH = {"sig": W_SIG, "pwr": W_PWR, "wide": W_WIDE}
VIA_DIAMETER, VIA_DRILL = 0.6, 0.3
EDGE_CLEARANCE = 0.31
HOLE_CLEARANCE = 0.26
WIDE_NETS = {"GND", "VBUS", "+5V", "+3V3", "+3V3_SENS", "+3V3_QWIIC", "Net-(U2-SW)"}
ISLAND_GND = "GND (island)"
MAX_ATTEMPTS = 16
SEARCH_LIMIT = 300000


def run(board, origin, geo, log=print):
    t0 = time.time()
    ox, oy = origin
    W, H = geo["W"], geo["H"]

    def mm(v):
        return pcbnew.ToMM(v)

    R = Router(W, H)
    n = R.n

    # --- where copper may not go ------------------------------------------
    big = 9.0
    for rect in ((-big, -big, W + big, 0), (-big, H, W + big, H + big),
                 (-big, -big, 0, H + big), (W, -big, W + big, H + big), *geo["cutouts"]):
        R.block_rect(*rect, grow=EDGE_CLEARANCE)
    R.block_rect(0, 0, geo["antenna_x"], H)                          # antenna: no copper at all
    mx0, my0, mx1, my1 = geo["module_inner"]
    R.block_rect(mx0, my0, mx1, my1, layers=(TOP,))                  # no top tracks under the module
    R.block_rect(mx0, my0 - 1.0, mx1, my1 + 1.0, classes=("via",))   # and no vias under it
    for x, y in geo["holes"]:
        R.block_disc(x, y, geo["hole_keepout"])                      # room for the screw head
    bx0, bx1 = geo["bridge_x"]
    R.block_rect(bx0 - 0.8, 0, bx1 + 0.8, H, classes=("pwr", "wide"))       # only thin tracks cross the slot
    R.block_rect(bx0 - 0.4, 0, bx1 + 0.4, H, classes=("via",))
    R.block_rect(*geo["thin_only"], classes=("pwr", "wide"))                # and only thin tracks on the SHT45 tongue
    # The bridges across the slot and the neck of the tongue carry the fixed tracks laid
    # down below and nothing else, on either layer. Routes join those tracks at their ends.
    for rect in geo.get("fixed_only", ()):
        R.block_rect(*rect)

    # keep-out areas that footprints bring along (antenna, underside of the SHT45)
    for fp in board.GetFootprints():
        for z in fp.Zones():
            if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                bb = z.GetBoundingBox()
                on = tuple(layer for layer, kicad in ((TOP, pcbnew.F_Cu), (BOT, pcbnew.B_Cu)) if z.IsOnLayer(kicad))
                R.block_rect(mm(bb.GetLeft()) - ox, mm(bb.GetTop()) - oy, mm(bb.GetRight()) - ox,
                             mm(bb.GetBottom()) - oy, layers=on)

    # --- pads ---------------------------------------------------------------
    net_id, net_name = {}, {}

    def nid(name):
        if name not in net_id:
            net_id[name] = len(net_id) + 1
            net_name[net_id[name]] = name
        return net_id[name]

    pads = []
    centre = {}
    anonymous = 100000
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        centre[ref] = (mm(fp.GetPosition().x) - ox, mm(fp.GetPosition().y) - oy)
        for pad in fp.Pads():
            pos = pad.GetPosition()
            cx, cy = mm(pos.x) - ox, mm(pos.y) - oy
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                if not ref.startswith("H"):
                    d = pad.GetDrillSize()
                    R.block_disc(cx, cy, max(mm(d.x), mm(d.y)) / 2, grow=HOLE_CLEARANCE)
                continue
            on = tuple(layer for layer, kicad in ((TOP, pcbnew.F_Cu), (BOT, pcbnew.B_Cu)) if pad.IsOnLayer(kicad))
            if not on:
                continue                                              # paste-only aperture
            bb = pad.GetBoundingBox()
            x0, y0 = mm(bb.GetLeft()) - ox, mm(bb.GetTop()) - oy
            x1, y1 = mm(bb.GetRight()) - ox, mm(bb.GetBottom()) - oy
            name = pad.GetNetname()
            if name:
                net = nid(name)
            else:
                anonymous += 1
                net = anonymous
            R.copper_rect(net, x0, y0, x1, y1, on)
            pads.append(dict(ref=ref, num=pad.GetNumber(), net=net, name=name, x=cx, y=cy,
                             rect=(x0, y0, x1, y1), layers=on, smd=len(on) == 1,
                             narrow=min(x1 - x0, y1 - y0) < 0.5))
    for p in pads:
        if p["smd"]:
            R.block_rect(*p["rect"], grow=0.05, classes=("via",))    # no via in or touching a pad
    # The USB connector's metal shell lies flat on the board, with only the solder mask
    # between it and the copper: no via and no track under it. That holds for the bottom
    # layer too (decided 2026-11-20): the ground under the connector stays whole.
    R.block_rect(*geo["usb_body"], classes=("via", "sig", "pwr", "wide"))

    used = set()     # every node a committed path passes through

    # --- legs of one terminal that are joined inside the part ------------------
    same = {}
    for p in pads:
        if p["name"] and p["ref"] in geo.get("internally_joined", ()):
            same.setdefault((p["ref"], p["num"]), []).append(p)
    internal = [group for group in same.values() if len(group) > 1]

    # --- strips the wide supply trunk must leave free (pin escape channels) ----
    for rect in geo.get("no_trunk", ()):
        R.block_rect(*rect, layers=(TOP,), classes=("wide",))

    # --- areas whose bottom layer stays ground (under the buck converter) -----
    for name, (x0, y0, x1, y1) in geo.get("reserve_bottom", ()):
        R.reserve_rect(nid(name), x0, y0, x1, y1, layers=(BOT,))

    # --- hand-drawn tracks ----------------------------------------------------
    # Each group joins the listed pads of one net. The tracks follow the grid, so the
    # router can branch off them anywhere; KiCad's rule check verifies their clearances.
    # A track is (width, points) on the top layer, or (width, points, "bottom"); a group
    # may also list vias, which its tracks on the two layers have to end on.
    pad_by_name = {f"{p['ref']}.{p['num']}": p for p in pads if p["name"]}
    prejoins = []
    width_at = {}          # node on a track -> width of that track (the widest, where several meet)
    for group in geo.get("prerouted", ()):
        net = nid(group["net"])
        nodes = set()
        for width, pts, *side in group["tracks"]:
            layer = BOT if side == ["bottom"] else TOP
            R.add_track(net, pts, layer, width)
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                steps = max(1, int(round(max(abs(xb - xa), abs(yb - ya)) / R.step)))
                piece = {R.node(xa + (xb - xa) * k / steps, ya + (yb - ya) * k / steps, layer) for k in range(steps + 1)}
                nodes.update(piece)
                for node in piece:
                    width_at[node] = max(width_at.get(node, 0.0), width)
        for x, y in group.get("vias", ()):
            R.add_via(net, x, y)
            nodes.update((R.node(x, y, TOP), R.node(x, y, BOT)))
        members = [pad_by_name[name] for name in group["pads"]]
        for q in members:
            if q["net"] != net:
                raise SystemExit(f"hand-drawn track on {group['net']} lists {q['ref']}.{q['num']}, which is on {q['name']}")
            q["pre"] = True
        prejoins.append(dict(net=net, pads=members, nodes=nodes))
    prejoins += [dict(net=group[0]["net"], pads=group, nodes=set()) for group in internal]

    # --- escape stubs -------------------------------------------------------
    def snap(v, sign=0):
        k = v / R.step
        k = math.ceil(k - 1e-6) if sign > 0 else math.floor(k + 1e-6) if sign < 0 else round(k)
        return round(k * R.step, 4)

    stub_width_at = {}     # node on an escape stub -> width of that stub
    # Along a row of pads every second stub is longer. A track that leaves a neighbouring
    # pad and turns sideways then has to go round the long stub's end, which stays open.
    rows = {}
    for p in pads:
        x0, y0, x1, y1 = p["rect"]
        if p["ref"] not in geo["fanout"] or not p["smd"] or min(x1 - x0, y1 - y0) > 1.0:
            continue
        dx, dy = p["x"] - centre[p["ref"]][0], p["y"] - centre[p["ref"]][1]
        horizontal = abs(dx) >= abs(dy)
        s = (1 if dx > 0 else -1) if horizontal else (1 if dy > 0 else -1)
        rows.setdefault((p["ref"], horizontal, s), {}).setdefault(round(p["y"] if horizontal else p["x"], 2), []).append(p)
    for (ref, horizontal, s), row in rows.items():
        for index, key in enumerate(sorted(row)):
            for p in row[key]:
                if not p["name"] or p["name"].startswith("unconnected-") or p.get("pre"):
                    continue
                x0, y0, x1, y1 = p["rect"]
                # a supply pin gets a stub of power width if its pad is wide enough for one
                options = [("sig", W_SIG)]
                if p["name"] in WIDE_NETS and not p["narrow"]:
                    options.insert(0, ("pwr", W_PWR))
                tries = [(extra, cls, width) for extra in ((1.2, 0.4) if index % 2 else (0.4,))
                         for cls, width in options]
                # The stub runs along the grid line nearest the pad centre (at most 0.05 mm
                # off-centre), so the track that continues it later has no kink.
                begin = (snap(p["x"]), snap(p["y"]))
                for extra, cls, width in tries:
                    if horizontal:
                        e = snap((x1 if s > 0 else x0) + s * extra, s)
                        grid_pt = (round(e + s * R.step, 4), begin[1])
                    else:
                        e = snap((y1 if s > 0 else y0) + s * extra, s)
                        grid_pt = (begin[0], round(e + s * R.step, 4))
                    steps = int(math.hypot(grid_pt[0] - begin[0], grid_pt[1] - begin[1]) / 0.05) + 1
                    line = [(begin[0] + (grid_pt[0] - begin[0]) * k / steps, begin[1] + (grid_pt[1] - begin[1]) * k / steps)
                            for k in range(steps + 1)]
                    if all(R.passable(cls, TOP, R.cell(x, y), p["net"]) for x, y in line):
                        first = len(R.tracks)
                        R.add_track(p["net"], [begin, grid_pt], TOP, width)
                        p["stub"] = R.node(*grid_pt, TOP)
                        p["stub_nodes"] = {R.node(x, y, TOP) for x, y in line}
                        p["stub_width"] = width
                        for node in p["stub_nodes"] - {R.node(*begin, TOP)}:
                            stub_width_at[node] = width
                        p["stub_tracks"] = (first, len(R.tracks))
                        break

    # --- centre pads --------------------------------------------------------
    # A sensor's large centre ground pad sits inside its ring of pads and is easily
    # walled in. Join it straight away to the ground pads of the same part that face it.
    for ep in pads:
        ex0, ey0, ex1, ey1 = ep["rect"]
        if not ep["smd"] or ep["ref"] not in geo["fanout"] or min(ex1 - ex0, ey1 - ey0) <= 1.0:
            continue
        for q in pads:
            if q is ep or q["ref"] != ep["ref"] or q["net"] != ep["net"] or not q["smd"]:
                continue
            inside_x = min(max(q["x"], ex0 + 0.2), ex1 - 0.2)
            inside_y = min(max(q["y"], ey0 + 0.2), ey1 - 0.2)
            # A straight tab from inside the small pad to inside the centre pad, centred on
            # the stretch the two pads have in common and as wide as that stretch allows.
            qx0, qy0, qx1, qy1 = q["rect"]
            if not ey0 <= q["y"] <= ey1 and min(qx1, ex1) - max(qx0, ex0) >= 0.2:      # pad above or below
                lo, hi = max(qx0, ex0), min(qx1, ex1)
                jx = round(round((lo + hi) / 2 / 0.05) * 0.05, 4)
                join_width = min(W_PWR, math.floor((hi - lo) / 0.05 + 1e-6) * 0.05)
                pts = [(jx, snap(q["y"])), (jx, snap(inside_y))]
            elif not ex0 <= q["x"] <= ex1 and min(qy1, ey1) - max(qy0, ey0) >= 0.2:    # pad left or right
                lo, hi = max(qy0, ey0), min(qy1, ey1)
                jy = round(round((lo + hi) / 2 / 0.05) * 0.05, 4)
                join_width = min(W_PWR, math.floor((hi - lo) / 0.05 + 1e-6) * 0.05)
                pts = [(snap(q["x"]), jy), (snap(inside_x), jy)]
            else:
                continue
            steps = int(math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]) / 0.05) + 1
            line = [(pts[0][0] + (pts[1][0] - pts[0][0]) * k / steps, pts[0][1] + (pts[1][1] - pts[0][1]) * k / steps)
                    for k in range(steps + 1)]
            if all(R.passable("sig", TOP, R.cell(x, y), q["net"]) for x, y in line):
                R.add_track(q["net"], pts, TOP, join_width)
                prejoins.append(dict(net=q["net"], pads=[q, ep], nodes=set()))     # one piece from now on

    # --- fixed thin tracks: across the bridge and through the neck of the tongue ----
    # Laid down first, parallel and evenly spaced, so the nets that have to pass these
    # two narrow places all fit.
    fixed_tracks = []
    seeds = {}
    for name, x_a, x_b, y in geo["fixed_tracks"]:
        net = nid(name)
        fixed_tracks.append((len(R.tracks), x_a, x_b, y))
        R.add_track(net, [(x_a, y), (x_b, y)], TOP, W_SIG)
        steps = int(round((x_b - x_a) / R.step))
        seeds.setdefault(net, []).append(dict(
            pad=None, pts=[(x_a, y), (x_b, y)],
            nodes={R.node(x_a + k * R.step, y, TOP) for k in range(steps + 1)}))

    # --- fixed feeds: hand-drawn top-layer runs that lead to the start of a fixed track ----
    # They become part of that fixed track's copper, so the router may join the net anywhere
    # along them; what stays unused at their far end is pruned like any other spur.
    keep_x = {}            # index of a fixed track -> x on it that must survive the trimming
    for feed in geo.get("fixed_feeds", ()):
        net = nid(feed["net"])
        index, x_a, x_b, y = next(f for f, (name, *_) in zip(fixed_tracks, geo["fixed_tracks"]) if nid(name) == net)
        seed = next(s for s in seeds[net] if (x_a, y) in s["pts"])
        for width, pts in feed["tracks"]:
            R.add_track(net, pts, TOP, width)
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                steps = max(1, int(round(max(abs(xb - xa), abs(yb - ya)) / R.step)))
                for k in range(steps + 1):
                    node = R.node(xa + (xb - xa) * k / steps, ya + (yb - ya) * k / steps, TOP)
                    seed["nodes"].add(node)
                    width_at[node] = max(width_at.get(node, 0.0), width)
            seed["pts"] = seed["pts"] + list(pts)
        keep_x.setdefault(index, []).append(x_a)

    # --- ESP32 ground pad: the twelve thermal vias of Espressif's land pattern ---
    # The pad is nine squares on a 1.25 mm pitch. A via sits in the middle of every gap
    # between two neighbouring squares; its copper ring overlaps both and joins them, and
    # takes the pad down to the ground pour on the bottom.
    gnd = nid("GND")
    epads = [p for p in pads if p["ref"] == geo["module_ref"] and p["num"] == geo["module_epad"]]
    ex, ey = sum(p["x"] for p in epads) / len(epads), sum(p["y"] for p in epads) / len(epads)
    for a in (-1.25, 0.0, 1.25):
        for b in (-0.625, 0.625):
            R.add_via(gnd, round(ex + a, 3), round(ey + b, 3))
            R.add_via(gnd, round(ex + b, 3), round(ey + a, 3))

    # --- pads are entered, left and crossed along their centre lines only -------
    # Inside every connected pad all nodes except those on the horizontal and the vertical
    # line through its centre are closed. A track then meets a pad at the middle of an
    # edge and runs straight to the centre, never in through a corner or along an edge.
    for p in pads:
        if not p["name"] or p["name"].startswith("unconnected-"):
            continue
        cx, cy = snap(p["x"]), snap(p["y"])
        for layer in p["layers"]:
            for idx in R.cells_in_rect(*p["rect"]):
                x, y = R.xy(idx)
                if abs(x - cx) > 1e-6 and abs(y - cy) > 1e-6:
                    for cls in ("sig", "pwr", "wide"):
                        R.grid[cls][layer][idx] = BLOCK

    # --- helpers that work on the current attempt -----------------------------
    def pad_cells(p, cls):
        """Where a track of this class may leave or reach the pad: at its centre (the
        nearest grid node), or anywhere along its escape stub. Never at its edge, so no
        track enters a pad off-centre."""
        out = {}
        # a wide track does not leave through a thin stub
        fits = "stub" in p and WIDTH[cls] <= p["stub_width"] + 1e-9
        for layer in p["layers"]:
            node = R.node(snap(p["x"]), snap(p["y"]), layer)
            if not R.passable(cls, layer, node % n, p["net"]):
                # The centre is not allowed (the SHT45's pads reach into the no-track area
                # under the part): take the allowed point of the pad nearest to it.
                free = [idx for idx in R.cells_in_rect(*p["rect"]) if R.passable(cls, layer, idx, p["net"])]
                if not free:
                    continue
                node = layer * n + min(free, key=lambda idx: math.hypot(R.xy(idx)[0] - p["x"], R.xy(idx)[1] - p["y"]))
            out[node] = 3.0 if fits else 0.0
        # the stub can be left (and joined) anywhere along its length; what stays unused
        # of it is cut off at the end
        for node in p["stub_nodes"] if fits else ():
            if R.passable(cls, TOP, node % n, p["net"]):
                out[node] = 0.0
        return out

    def connect(p, targets=None, goal=None, classes=None, sources=None, **kw):
        """Route pad `p` to one of `targets` (or to `goal`). Returns the path or None.

        `sources` are the nodes of the copper the pad is already connected to. The new
        track may start from any of them instead of from the pad: it then branches off
        where that is shortest, and never has to cross the copper it belongs to. A power
        track only branches off copper that is at least as wide as itself.
        """
        net, name = p["net"], p["name"]
        if classes is None:
            classes = ["sig"]
            if name in WIDE_NETS and not p["narrow"]:
                classes.insert(0, "pwr")
        kw.setdefault("limit", SEARCH_LIMIT)
        for cls in classes:
            src = pad_cells(p, cls)
            for node in sources or ():
                if node not in src and R.passable(cls, node // n, node % n, net) and (
                        cls == "sig" or min(width_at.get(node, 9.0), stub_width_at.get(node, 9.0)) + 1e-9 >= WIDTH[cls]):
                    src[node] = 0.0
            if goal is None:
                # a wide track does not end on a thin stub either
                fit = targets if cls == "sig" else {t for t in targets if stub_width_at.get(t, 9.0) + 1e-9 >= WIDTH[cls]}
                path = R.find(net, src, cls, targets=fit, **kw)
            else:
                path = R.find(net, src, cls, goal=lambda node, c=cls: goal(node, c), **kw)
            if path:
                path = R.straighten(net, path, cls)
                R.commit_path(net, path, WIDTH[cls])
                used.update(path)
                for node in path:
                    width_at[node] = max(width_at.get(node, 0.0), WIDTH[cls])
                return path
        return None

    # --- what has to be connected ---------------------------------------------
    # Every net is broken into single connections (a minimum spanning tree over its
    # pads). All connections of all nets are then routed shortest first, so local links
    # - a chip pin to its capacitor - are made before long buses pass by.
    by_net = {}
    for p in pads:
        if p["name"] and not p["name"].startswith("unconnected-"):
            by_net.setdefault(p["name"], []).append(p)
    island_x = bx1
    gnd_pads = by_net.pop("GND", [])
    main_gnd = [p for p in gnd_pads if p["x"] <= island_x and p["smd"] and not any(p is q for q in epads)]
    groups = dict(by_net)
    groups[ISLAND_GND] = [p for p in gnd_pads if p["x"] > island_x]

    def gap(a, b):
        return min(math.hypot(ax - bx, ay - by) for ax, ay in a["pts"] for bx, by in b["pts"])

    edges = []
    items_of = {}
    for label, plist in groups.items():
        net = gnd if label == ISLAND_GND else net_id[label]
        items = [dict(pad=p, pts=[(p["x"], p["y"])]) for p in plist]
        items += seeds.get(net, [])                                  # the fixed tracks
        items_of[label] = (net, items)
        linked, rest = [items[0]], items[1:]
        while rest:                                                  # Prim's algorithm
            d, i, j = min((gap(x, y), i, j) for i, x in enumerate(linked) for j, y in enumerate(rest))
            edges.append(dict(label=label, net=net, a=linked[i], b=rest[j], length=d))
            linked.append(rest.pop(j))
    edges.sort(key=lambda e: e["length"])

    def route_everything(order):
        failures = []

        # 1. ground on the main part: every pad gets a short track to a via into the pours.
        #    First, while there is still room next to every pad.
        gnd_points = set()

        def to_pour(node, cls):
            idx = node % n
            if node >= n:
                return False
            if node in gnd_points:
                return True
            return R.via_allowed(idx, gnd) and R.passable(cls, BOT, idx, gnd) and R.xy(idx)[0] < bx0 - 0.9

        y_gnd = geo["bridge_y"]["GND"]
        stub_end = dict(ref="bridge", num="GND", net=gnd, name="GND", x=bx0 - 1.8, y=y_gnd,
                        rect=(bx0 - 1.8, y_gnd, bx0 - 1.8, y_gnd), layers=(TOP,), smd=True, narrow=True)
        for p in [stub_end] + sorted(main_gnd, key=lambda p: (p["x"], p["y"])):
            path = connect(p, goal=to_pour, allow_via=False, limit=60000)
            if path:
                if path[-1] not in gnd_points:
                    R.add_via(gnd, *R.xy(path[-1] % n))
                gnd_points.update(path)
            else:
                failures.append(dict(label="GND (via)", a=dict(pad=p), b=None, length=0))

        # 2. everything else, connection by connection
        comp = {}          # id(item) -> component number
        nodes = {}         # component number -> set of nodes (None: just the unrouted pad)
        members = {}       # component number -> items
        for label, (net, items) in items_of.items():
            for it in items:
                c = len(comp)
                comp[id(it)] = c
                nodes[c] = set(it["nodes"]) if it["pad"] is None else None
                members[c] = [it]

        def cells_of(c):
            if nodes[c] is None:
                return set(pad_cells(members[c][0]["pad"], "sig"))
            return nodes[c]

        def merge(c_keep, c_gone, extra=()):
            if c_keep == c_gone:
                nodes[c_keep] = set(cells_of(c_keep)) | set(extra)
                return
            merged = set(cells_of(c_keep)) | set(cells_of(c_gone)) | set(extra)
            for it in members[c_gone]:
                comp[id(it)] = c_keep
            members[c_keep] += members.pop(c_gone)
            nodes[c_keep] = merged
            nodes.pop(c_gone)

        item_of = {id(it["pad"]): it for _, items in items_of.values() for it in items if it["pad"] is not None}

        # pads joined by hand-drawn tracks are one piece of copper from the start
        for group in prejoins:
            its = [item_of[id(q)] for q in group["pads"] if id(q) in item_of]
            for it in its:
                merge(comp[id(its[0])], comp[id(it)], group["nodes"])

        # supply trunks: before any signal, as wide as they fit
        for name_a, name_b in geo.get("trunks", ()):
            a, b = item_of[id(pad_by_name[name_a])], item_of[id(pad_by_name[name_b])]
            if comp[id(a)] == comp[id(b)]:
                continue
            path = connect(a["pad"], targets=set(cells_of(comp[id(b)])), classes=["wide", "pwr", "sig"])
            if path:
                merge(comp[id(a)], comp[id(b)], path)
            else:
                failures.append(dict(label=f"trunk {name_a}", a=a, b=b, length=0))

        def reach_out(e, src):
            """Route the pad of `src` to any other part of its net; merge what it hits."""
            _, items = items_of[e["label"]]
            c_src = comp[id(src)]
            others = {comp[id(it)] for it in items} - {c_src}
            targets = set()
            for c in others:
                targets |= cells_of(c)
            path = connect(src["pad"], targets=targets, sources=nodes[c_src])
            if not path:
                return False
            if geo.get("debug"):
                log(f"    {e['label']:14s} {src['pad']['ref']}.{src['pad']['num']:4s} len={len(path)}")
            hit = next(c for c in others if path[-1] in cells_of(c))
            merge(c_src, hit, path)
            return True

        def try_edge(e):
            """Make sure both ends of the connection are in one piece of copper."""
            a, b = e["a"], e["b"]
            for _ in range(len(items_of[e["label"]][1])):
                if comp[id(a)] == comp[id(b)]:
                    return True
                # the end in the smaller piece reaches out, a thin pad before a wide one;
                # the fixed bridge track never does
                cands = [x for x in (a, b) if x["pad"] is not None]
                cands.sort(key=lambda x: (len(members[comp[id(x)]]), not x["pad"]["narrow"]))
                if not any(reach_out(e, src) for src in cands):
                    return False
            return comp[id(a)] == comp[id(b)]

        pending = []
        for e in order:
            if not try_edge(e):
                pending.append(e)
        for e in pending:                                           # once more, now that the rest is in
            if not try_edge(e):
                failures.append(e)
        return failures

    def describe(e):
        p = e["a"]["pad"] or e["b"]["pad"]
        q = e["b"]["pad"] if e.get("b") and e["b"]["pad"] is not p else None
        return f"{e['label']} {p['ref']}.{p['num']}" + (f"-{q['ref']}.{q['num']}" if q else "")

    # --- route, and route again with the failed connections earlier -------------
    order = list(edges)
    base = dict(grid={c: [list(g) for g in layers] for c, layers in R.grid.items()},
                tracks=list(R.tracks), vias=list(R.vias))

    base_width = dict(width_at)

    def restore():
        R.grid = {c: [list(g) for g in layers] for c, layers in base["grid"].items()}
        R.tracks, R.vias = list(base["tracks"]), list(base["vias"])
        used.clear()
        width_at.clear()
        width_at.update(base_width)

    # --- pockets of the ground pours -------------------------------------------
    # Tracks of other nets can close off part of a pour on both layers at once. KiCad then
    # counts the ground pads and vias inside as unconnected, though the router has joined
    # every pad to "the pour". Estimate the pours from the grid: wherever a thin ground track
    # could lie, inside the pours' outline, copper will be. Ground vias and through-hole pads
    # join the layers. Every piece holding ground copper beyond the largest is a pocket.
    pour_x0, pour_x1 = geo["antenna_x"] + 0.2, bx0 - 0.1

    def ground_pockets():
        nx, ny = R.nx, R.ny
        ix0, ix1 = int(math.ceil(pour_x0 / R.step)), int(pour_x1 / R.step)
        label = [[0] * n, [0] * n]
        parent = []

        def find_root(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for layer in (TOP, BOT):
            g, lab = R.grid["sig"][layer], label[layer]
            for iy in range(1, ny - 1):
                row = iy * nx
                for ix in range(ix0, ix1 + 1):
                    start = row + ix
                    if lab[start] or not (g[start] == FREE or g[start] == gnd):
                        continue
                    parent.append(len(parent))
                    comp = len(parent)
                    lab[start] = comp
                    stack = [start]
                    while stack:
                        i = stack.pop()
                        jx = i % nx
                        for j in ((i - 1,) if jx > ix0 else ()) + ((i + 1,) if jx < ix1 else ()) + (i - nx, i + nx):
                            if 0 <= j < n and not lab[j] and (g[j] == FREE or g[j] == gnd):
                                lab[j] = comp
                                stack.append(j)
        holders = []
        for x, y, net in R.vias:
            if net == gnd and pour_x0 <= x <= pour_x1:
                a, b = label[TOP][R.cell(x, y)], label[BOT][R.cell(x, y)]
                if a and b:
                    parent[find_root(a - 1)] = find_root(b - 1)
                holders.append(((x, y), a or b))
        legs = {}            # legs of one terminal are joined inside the part (push buttons)
        for p in pads:
            if p["net"] == gnd and pour_x0 <= p["x"] <= pour_x1:
                labs = [label[layer][R.cell(p["x"], p["y"])] for layer in p["layers"]]
                labs = [v for v in labs if v]
                if p["ref"] in geo.get("internally_joined", ()):
                    labs += legs.get((p["ref"], p["num"]), [])
                    legs.setdefault((p["ref"], p["num"]), []).extend(labs[:1])
                for v in labs[1:]:
                    parent[find_root(v - 1)] = find_root(labs[0] - 1)
                if labs:
                    holders.append(((p["x"], p["y"]), labs[0]))
        groups = {}
        for xy, v in holders:
            groups.setdefault(find_root(v - 1), []).append(xy)
        if len(groups) <= 1:
            return []
        main = max(groups.values(), key=len)
        return [g[0] for g in groups.values() if g is not main]

    best = None
    for attempt in range(1, geo.get("attempts", MAX_ATTEMPTS) + 1):
        restore()
        failures = route_everything(order)
        failures += [dict(label="GND (pour pocket)", a=dict(pad=dict(ref=f"({x:.1f}", num=f"{y:.1f})")), b=None, length=0)
                     for x, y in ground_pockets()]
        log(f"  attempt {attempt}: {len(failures)} unrouted, {len(R.tracks)} segments, {len(R.vias)} vias, "
            f"{time.time() - t0:.0f} s" + ("" if not failures else "  [" + ", ".join(describe(e) for e in failures[:8]) + "]"))
        if best is None or len(failures) < len(best["failures"]):
            best = dict(failures=failures, tracks=list(R.tracks), vias=list(R.vias), used=set(used), attempt=attempt)
        if not failures:
            break
        # move each failed connection halfway towards the front
        failed = {id(e) for e in failures}
        rank = {id(e): (i / 2 - 0.5 if id(e) in failed else i) for i, e in enumerate(order)}
        order = sorted(order, key=lambda e: rank[id(e)])

    tracks, vias, used_nodes = best["tracks"], best["vias"], best["used"]

    # --- tidy up ---------------------------------------------------------------
    # escape stubs nobody used, and the unused ends of the fixed tracks
    drop = set()
    for p in pads:
        if "stub" in p and not (p["stub_nodes"] & used_nodes):
            drop.update(range(*p["stub_tracks"]))
    for index, x_a, x_b, y in fixed_tracks:
        xs = [x_a + k * R.step for k in range(int(round((x_b - x_a) / R.step)) + 1)]
        hit = [x for x in xs if R.node(x, y, TOP) in used_nodes] + keep_x.get(index, [])
        if hit:
            tracks[index] = (round(min(hit), 4), y, round(max(hit), 4), y) + tracks[index][4:]
    tracks = [t for i, t in enumerate(tracks) if i not in drop and (t[0], t[1]) != (t[2], t[3])]

    # Dead ends. A connection that was made to a fixed track or a stub which then stayed
    # unused leaves a spur behind. Remove every track with an end that touches nothing,
    # and every via left with copper on one layer only, until nothing changes.
    def touches(pt, a, b):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        return abs(math.hypot(pt[0] - a[0], pt[1] - a[1]) + math.hypot(b[0] - pt[0], b[1] - pt[1]) - length) < 1e-6

    def prune(tracks, vias):
        """Cut every track back to the last point where something is attached to it."""
        while True:
            changed = False
            result = []
            # a track lying entirely on another track of its net that is at least as wide
            # adds nothing (a thin stub under a power track, for instance)
            covered = {i for i, t in enumerate(tracks) for j, o in enumerate(tracks)
                       if j != i and o[6] == t[6] and o[4] == t[4] and o[5] >= t[5]
                       and touches(t[0:2], o[0:2], o[2:4]) and touches(t[2:4], o[0:2], o[2:4])
                       and (o[5] > t[5] + 1e-9
                            or math.hypot(o[2] - o[0], o[3] - o[1]) > math.hypot(t[2] - t[0], t[3] - t[1]) + 1e-6
                            or j < i)}          # of two identical tracks one stays
            if covered:
                tracks = [t for i, t in enumerate(tracks) if i not in covered]
                changed = True
            # ... and one that such a track covers in part is cut back to where that track ends
            for i, t in enumerate(tracks):
                for j, o in enumerate(tracks):
                    if j == i or o[6] != t[6] or o[4] != t[4] or o[5] < t[5] or (o[5] == t[5] and j > i):
                        continue
                    for a, b in ((t[0:2], t[2:4]), (t[2:4], t[0:2])):
                        inner = [q for q in (o[0:2], o[2:4]) if touches(q, a, b) and q != a and q != b]
                        outer = [q for q in (o[0:2], o[2:4]) if q not in inner]
                        if len(inner) == 1 and touches(a, o[0:2], o[2:4]) and                                 abs((b[0] - a[0]) * (outer[0][1] - a[1]) - (b[1] - a[1]) * (outer[0][0] - a[0])) < 1e-6:
                            # `a` is the end lying under the wider track: the track now starts
                            # where the wider one ends
                            tracks[i] = t = (*inner[0], *b, *t[4:])
                            changed = True
                            break
            for i, t in enumerate(tracks):
                a, b, layer, net = t[0:2], t[2:4], t[4], t[6]
                length = math.hypot(b[0] - a[0], b[1] - a[1])
                # everything attached to this track, as distances from its start
                held = []
                for j, o in enumerate(tracks):
                    if j != i and o[6] == net and o[4] == layer:
                        held += [math.hypot(e[0] - a[0], e[1] - a[1]) for e in (o[0:2], o[2:4]) if touches(e, a, b)
                                 or e == a or e == b]
                        # the other track may also pass over one of this track's ends
                        held += [d for e, d in ((a, 0.0), (b, length)) if touches(e, o[0:2], o[2:4])]
                held += [math.hypot(v[0] - a[0], v[1] - a[1]) for v in vias
                         if v[2] == net and (touches(v[0:2], a, b) or v[0:2] == a or v[0:2] == b)]
                steps = max(1, int(round(length / 0.05)))
                # A pad holds the track at one point, the one nearest the pad's centre. A
                # piece that only pokes into a pad and leads nowhere then counts as a dead
                # end and goes, instead of surviving as a bump on the pad's edge.
                for q in pads:
                    if q["net"] == net and layer in q["layers"]:
                        x0, y0, x1, y1 = q["rect"]
                        inside = [k for k in range(steps + 1)
                                  if x0 - 0.01 <= a[0] + (b[0] - a[0]) * k / steps <= x1 + 0.01
                                  and y0 - 0.01 <= a[1] + (b[1] - a[1]) * k / steps <= y1 + 0.01]
                        if inside:
                            k = min(inside, key=lambda k: math.hypot(a[0] + (b[0] - a[0]) * k / steps - q["x"],
                                                                     a[1] + (b[1] - a[1]) * k / steps - q["y"]))
                            held.append(length * k / steps)
                lo, hi = (min(held), max(held)) if held else (0.0, 0.0)
                if hi - lo < 1e-6:
                    changed = True                                   # attached at one point at most: a dead end
                    if geo.get("debug"):
                        log(f"    dead end removed: {net_name[net]} {a} - {b}")
                    continue
                if lo > 1e-6 or hi < length - 1e-6:
                    changed = True                                   # a loose end: cut it back
                    if geo.get("debug"):
                        log(f"    loose end cut back: {net_name[net]} {a} - {b}")
                    p = lambda d: (round(a[0] + (b[0] - a[0]) * d / length, 4), round(a[1] + (b[1] - a[1]) * d / length, 4))
                    t = (*p(lo), *p(hi), *t[4:])
                result.append(t)
            tracks = result

            def live(v):
                if v[2] == gnd and v[0] < bx0:
                    return True                                       # joins the two ground pours
                on = {t[4] for t in tracks if t[6] == v[2] and (touches(v[0:2], t[0:2], t[2:4])
                                                                 or v[0:2] in (t[0:2], t[2:4]))}
                return len(on) == 2
            kept = [v for v in vias if live(v)]
            if not changed and len(kept) == len(vias):
                return tracks, vias
            vias = kept

    before = len(tracks), len(vias)
    tracks, vias = prune(tracks, vias)
    if (len(tracks), len(vias)) != before:
        log(f"  removed {before[0] - len(tracks)} dead-end track segments and {before[1] - len(vias)} vias")

    # The clean-up below moves copper by a fraction of a millimetre. The grids are too
    # coarse to judge that (they are built to be safe, not exact), so these checks measure
    # the real distance to every other net's tracks, vias and pads.
    def point_seg(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d2 = dx * dx + dy * dy
        u = 0.0 if d2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2))
        return math.hypot(p[0] - a[0] - u * dx, p[1] - a[1] - u * dy)

    def seg_seg(a, b, c, d):
        def side(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        if side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0:
            return 0.0                                        # they cross
        return min(point_seg(a, c, d), point_seg(b, c, d), point_seg(c, a, b), point_seg(d, a, b))

    def seg_rect(a, b, rect):
        x0, y0, x1, y1 = rect
        if x0 <= a[0] <= x1 and y0 <= a[1] <= y1:
            return 0.0
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        return min(seg_seg(a, b, corners[k], corners[(k + 1) % 4]) for k in range(4))

    def legal(a, b, width, layer, net, tracks):
        """May a track of `net` run from a to b? Measured, with the router's own margin."""
        cls = "sig" if width <= W_SIG else "pwr" if width <= W_PWR else "wide"
        steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.05))
        if any(R.hard[cls][layer][R.cell(a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)]
               for k in range(steps + 1)):
            return False                                      # board edge, slot or keep-out
        need = 0.153 + width / 2                               # the board's 0.15 mm rule and a hair
        return (all(seg_seg(a, b, t[0:2], t[2:4]) >= need + t[5] / 2 for t in tracks if t[4] == layer and t[6] != net)
                and all(point_seg(v[0:2], a, b) >= need + VIA_DIAMETER / 2 for v in vias if v[2] != net)
                and all(seg_rect(a, b, q["rect"]) >= need for q in pads if q["net"] != net and layer in q["layers"]))

    # Staircases. Squeezed along another net's diagonal track, the search cannot step
    # diagonally (the grid forbids cutting corners) and climbs in 0.1 mm steps instead.
    # Replace every run of such short pieces by one straight and one diagonal piece.
    def destair(tracks):
        def key(x, y):
            return (round(x, 4), round(y, 4))

        def length(t):
            return math.hypot(t[2] - t[0], t[3] - t[1])

        done, tried = 0, set()
        while True:
            ends = {}
            for i, t in enumerate(tracks):
                for end in (key(*t[0:2]), key(*t[2:4])):
                    ends.setdefault((end, t[4], t[6]), []).append(i)

            def inner(v, layer, net):
                """Exactly two pieces meet at v and nothing else is attached there."""
                idx = ends.get((v, layer, net), [])
                if len(idx) != 2 or any(key(x, y) == v for x, y, _ in vias):
                    return False
                if any(q["net"] == net and layer in q["layers"] and q["rect"][0] - 0.02 <= v[0] <= q["rect"][2] + 0.02
                       and q["rect"][1] - 0.02 <= v[1] <= q["rect"][3] + 0.02 for q in pads):
                    return False
                return not any(k not in idx and t[6] == net and t[4] == layer and touches(v, t[0:2], t[2:4])
                               for k, t in enumerate(tracks))

            for i, t in enumerate(tracks):
                if length(t) > 0.25:
                    continue
                layer, net = t[4], t[6]
                chain, tips = [i], [key(*t[0:2]), key(*t[2:4])]
                for side in (0, 1):                               # grow the run at both ends
                    while inner(tips[side], layer, net):
                        j = next((k for k in ends[(tips[side], layer, net)] if k not in chain), None)
                        if j is None or length(tracks[j]) > 0.25 or tracks[j][5] != t[5]:
                            break
                        chain.insert(0, j) if side == 0 else chain.append(j)
                        o = tracks[j]
                        tips[side] = key(*o[2:4]) if key(*o[0:2]) == tips[side] else key(*o[0:2])
                s, e = tips
                if len(chain) < 2 or s == e or (s, e, layer, net) in tried:
                    continue
                tried.add((s, e, layer, net))
                dx, dy = round((e[0] - s[0]) / R.step), round((e[1] - s[1]) / R.step)
                if abs(s[0] + dx * R.step - e[0]) > 1e-6 or abs(s[1] + dy * R.step - e[1]) > 1e-6:
                    continue                                      # an end is off the grid
                sx, sy, d = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0), min(abs(dx), abs(dy))
                mids = {key(s[0] + sx * d * R.step, s[1] + sy * d * R.step),          # diagonal first
                        key(e[0] - sx * d * R.step, e[1] - sy * d * R.step)}          # diagonal last
                rest = [o for k, o in enumerate(tracks) if k not in chain]
                for m in mids:
                    pieces = [(p, q) for p, q in ((s, m), (m, e)) if p != q]
                    if len(pieces) < len(chain) and all(legal(p, q, t[5], layer, net, rest) for p, q in pieces):
                        tracks = rest + [(p[0], p[1], q[0], q[1], layer, t[5], net) for p, q in pieces]
                        done += 1
                        break
                else:
                    continue
                break
            else:
                return tracks, done

    tracks, straightened = destair(tracks)
    if straightened:
        log(f"  replaced {straightened} staircases by straight pieces")

    # Right angles. Where two separately routed pieces meet end to end - a connection
    # arriving at the end of a stub or of a fixed track - they often meet at 90 degrees.
    # Cut such a corner with a 45 degree piece, as large as the copper around it allows.
    # Corners that hug another net's copper stay: cutting them would break the clearance.
    def chamfer(tracks):
        def key(x, y):
            return (round(x, 4), round(y, 4))

        def grid_steps(a, b):
            """(unit step, count) if a-b runs along the grid at 0/45/90 degrees."""
            dx, dy = round((b[0] - a[0]) / R.step, 3), round((b[1] - a[1]) / R.step, 3)
            if dx != int(dx) or dy != int(dy) or (dx and dy and abs(dx) != abs(dy)) or not (dx or dy):
                return None
            count = int(max(abs(dx), abs(dy)))
            return (int(dx) // count, int(dy) // count), count

        def try_corner(v, layer, net, i, j):
            ti, tj = tracks[i], tracks[j]
            p = key(*ti[2:4]) if key(*ti[0:2]) == v else key(*ti[0:2])
            q = key(*tj[2:4]) if key(*tj[0:2]) == v else key(*tj[0:2])
            gp, gq = grid_steps(v, p), grid_steps(v, q)
            if not gp or not gq:
                return None
            (ux, uy), np_ = gp
            (wx, wy), nq = gq
            if ux * wx + uy * wy != 0:
                return None                                   # not a right angle
            if any(abs(x - v[0]) < 1e-6 and abs(y - v[1]) < 1e-6 for x, y, _ in vias):
                return None
            mine = [pd for pd in pads if pd["net"] == net and layer in pd["layers"]]
            width = min(ti[5], tj[5])
            cls = "sig" if width <= W_SIG else "pwr" if width <= W_PWR else "wide"
            others = [t for k, t in enumerate(tracks) if k not in (i, j) and t[6] == net and t[4] == layer]
            for size in range(min(np_, nq, 6 if not (ux and uy) else 4), 0, -1):
                a = key(v[0] + ux * size * R.step, v[1] + uy * size * R.step)
                b = key(v[0] + wx * size * R.step, v[1] + wy * size * R.step)
                # nothing else may hang on the two pieces that disappear
                gone = [key(v[0] + ux * k * R.step / 2, v[1] + uy * k * R.step / 2) for k in range(2 * size)] + \
                       [key(v[0] + wx * k * R.step / 2, v[1] + wy * k * R.step / 2) for k in range(2 * size)]
                if any(x0 - 0.02 <= x <= x1 + 0.02 and y0 - 0.02 <= y <= y1 + 0.02
                       for x, y in gone for x0, y0, x1, y1 in (pd["rect"] for pd in mine)):
                    continue
                if any(touches(e, v, a) or touches(e, v, b) or e == v
                       for t in others for e in (key(*t[0:2]), key(*t[2:4]))):
                    continue
                if any(net_ == net and (touches((x, y), v, a) or touches((x, y), v, b)) for x, y, net_ in vias):
                    continue
                if not legal(a, b, width, layer, net, tracks):
                    continue
                new = [(p, a, ti[5]), (a, b, width), (b, q, tj[5])]
                return [(s[0], s[1], e[0], e[1], layer, w, net) for s, e, w in new if s != e]
            return None

        done = 0
        skip = set()
        while True:
            ends = {}
            for i, t in enumerate(tracks):
                for end in (key(*t[0:2]), key(*t[2:4])):
                    ends.setdefault((end, t[4], t[6]), []).append(i)
            for (v, layer, net), idx in ends.items():
                if len(idx) != 2 or idx[0] == idx[1] or (v, layer, net) in skip:
                    continue
                new = try_corner(v, layer, net, *idx)
                if new is None:
                    skip.add((v, layer, net))
                    continue
                tracks = [t for k, t in enumerate(tracks) if k not in idx] + new
                done += 1
                break
            else:
                return tracks, done

    tracks, cut = chamfer(tracks)
    if cut:
        log(f"  cut {cut} right-angle corners")

    # One-step diagonals into the side of a track. A branch that reaches a straight track of
    # its own net with a last diagonal step of 0.1 mm starts that step inside the track's
    # copper; KiCad then reports the piece as a dangling end. Let the branch run straight
    # into the track instead, at a right angle, which is how a T-junction should look.
    def square_up(tracks):
        def key(x, y):
            return (round(x, 4), round(y, 4))
        done = 0
        for i, t in enumerate(tracks):
            if t is None:
                continue
            a, b = key(*t[0:2]), key(*t[2:4])
            if abs(abs(a[0] - b[0]) - R.step) > 1e-6 or abs(abs(a[1] - b[1]) - R.step) > 1e-6:
                continue
            for end, start in ((b, a), (a, b)):
                for o in tracks:
                    if o is None or o is t or o[6] != t[6] or o[4] != t[4] or end in (key(*o[0:2]), key(*o[2:4])):
                        continue
                    if not touches(end, o[0:2], o[2:4]):
                        continue
                    horizontal = abs(o[1] - o[3]) < 1e-6
                    if not horizontal and abs(o[0] - o[2]) > 1e-6:
                        continue                                      # only into straight tracks
                    foot = (start[0], end[1]) if horizontal else (end[0], start[1])
                    if not touches(foot, o[0:2], o[2:4]):
                        continue
                    # the piece before, if it runs in the new direction, simply gets longer
                    prev = next((k for k, q in enumerate(tracks) if q is not None and q is not t and q[6] == t[6] and q[4] == t[4]
                                 and start in (key(*q[0:2]), key(*q[2:4]))
                                 and (abs(q[0] - q[2]) < 1e-6) == horizontal and (abs(q[1] - q[3]) < 1e-6) != horizontal), None)
                    if prev is None:
                        tracks[i] = (*start, *foot, *t[4:])
                    else:
                        q = tracks[prev]
                        far = key(*q[2:4]) if key(*q[0:2]) == start else key(*q[0:2])
                        tracks[prev] = (*far, *foot, *q[4:])
                        tracks[i] = None
                    done += 1
                    break
                else:
                    continue
                break
        return [t for t in tracks if t is not None], done

    tracks, squared = square_up(tracks)
    if squared:
        log(f"  squared up {squared} one-step diagonals into a track")

    # --- hand the result to KiCad ---------------------------------------------
    def P(x, y):
        return VECTOR2I(FromMM(ox + x), FromMM(oy + y))

    kicad_net = {name: board.FindNet(name) for name in net_id}
    for x1, y1, x2, y2, layer, width, net in tracks:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(x1, y1))
        t.SetEnd(P(x2, y2))
        t.SetWidth(FromMM(width))
        t.SetLayer(pcbnew.F_Cu if layer == TOP else pcbnew.B_Cu)
        t.SetNet(kicad_net[net_name[net]])
        board.Add(t)
    for x, y, net in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetPosition(P(x, y))
        v.SetDrill(FromMM(VIA_DRILL))
        try:
            v.SetWidth(pcbnew.F_Cu, FromMM(VIA_DIAMETER))
        except TypeError:
            v.SetWidth(FromMM(VIA_DIAMETER))
        v.SetNet(kicad_net[net_name[net]])
        board.Add(v)

    # --- ground pours on the main part, keep-out at the antenna ----------------
    def zone(pts, layer=None, net=None, name=""):
        z = pcbnew.ZONE(board)
        z.SetZoneName(name)
        outline = z.Outline()
        outline.NewOutline()
        for x, y in pts:
            outline.Append(FromMM(ox + x), FromMM(oy + y))
        if net is None:
            z.SetIsRuleArea(True)
            z.SetLayerSet(pcbnew.LSET.AllCuMask())
            z.SetDoNotAllowZoneFills(True)
            z.SetDoNotAllowTracks(True)
            z.SetDoNotAllowVias(True)
            z.SetDoNotAllowPads(False)
            z.SetDoNotAllowFootprints(False)
        else:
            z.SetLayer(layer)
            z.SetNet(net)
            z.SetLocalClearance(FromMM(0.2))
            z.SetMinThickness(FromMM(0.2))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
            z.SetThermalReliefGap(FromMM(0.25))
            z.SetThermalReliefSpokeWidth(FromMM(0.3))
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)
        return z

    ax = geo["antenna_x"]
    zone([(0, 0), (ax, 0), (ax, H), (0, H)], name="Antenna keep-out")
    px0, px1 = ax + 0.2, bx0 - 0.1
    for layer, label in ((pcbnew.F_Cu, "GND top"), (pcbnew.B_Cu, "GND bottom")):
        zone([(px0, 0), (px1, 0), (px1, H), (px0, H)], layer=layer, net=kicad_net["GND"], name=label)
    # Pads at the end of a tight row can only get one thermal spoke; join those solidly.
    for fp in board.GetFootprints():
        if fp.GetReference() in geo["solid_pour_pads"]:
            for pad in fp.Pads():
                if pad.GetNetname() == "GND":
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    # The pours are filled afterwards by kicad-cli (see gen_pcb.py): its fill respects the
    # board edge and unplated holes, which the fill available to scripts here does not.

    log(f"  {len(tracks)} track segments, {len(vias)} vias, {time.time() - t0:.0f} s in total")
    for e in best["failures"]:
        log(f"  NOT ROUTED  {describe(e)}")
    return best["failures"]

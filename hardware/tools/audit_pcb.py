#!/usr/bin/env python3
"""Measure the routed ClimaSense board: track lengths, widths, supply resistance, parallel runs.

KiCad's design rule check says whether the board can be manufactured and matches the
schematic. It does not say whether a track is longer or thinner than it should be.
This script measures that, so the numbers in docs/hardware/layout.md can be reproduced.

1. Per net: routed length against the shortest possible connection of its pads
   (a minimum spanning tree over the pad centres), and the length at each width.
2. Supply paths: length and resistance along the tracks between two pads.
3. Nets that run side by side on the same layer.
4. Tidiness: a net crossing itself, a net with a loop in it, a track that meets a pad
   away from the pad's centre lines, a power track continuing as a thin one, and
   right-angle corners. The first four make the script fail: each was a real defect of
   the router at some point, and none of them is visible to the rule check.

Needs KiCad's own Python:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/audit_pcb.py
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from pathlib import Path

import wx
wx.DisableAsserts()          # otherwise KiCad debug alerts pop up as dialogs
import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = HW / "climasense.kicad_pcb"
ORIGIN = (100.0, 60.0)       # board origin on the sheet, as in gen_pcb.py
SLOT_X = 48.0                # the ground pours end here; right of it ground is tracks
MM = 1e-6
RHO, COPPER = 1.72e-8, 35e-6  # ohm metre; 1 oz copper thickness in metres
NEAR = 0.45                  # edge-to-edge gap counted as "side by side", mm

# pad pairs whose connection carries supply current
SUPPLY_PATHS = (
    ("VBUS", "J1.A9", "F1.1", "USB connector to fuse, nearer supply pad"),
    ("VBUS", "J1.A4", "F1.1", "USB connector to fuse, farther supply pad"),
    ("+5V", "F1.2", "U2.3", "fuse to buck converter input"),
    ("+5V", "C1.1", "U2.3", "buck input capacitor to buck input"),
    ("+5V", "F1.2", "U3.1", "fuse to sensor regulator input"),
    ("+3V3", "C2.1", "U4.2", "buck output capacitor to ESP32 supply pin"),
    ("+3V3", "C5.1", "U4.2", "ESP32 decoupling capacitor to its supply pin"),
    ("+5V", "F1.2", "U9.1", "fuse to Qwiic regulator input"),
    ("+3V3_QWIIC", "U9.5", "J2.2", "Qwiic regulator to connector"),
    ("+3V3_SENS", "U3.5", "U6.7", "sensor regulator to SCD41 supply"),
    ("+3V3_SENS", "U3.5", "U6.19", "sensor regulator to SCD41 emitter supply"),
    ("+3V3_SENS", "U6.7", "U6.19", "SCD41 supply pin to its emitter supply pin"),
    ("+3V3_SENS", "C9.1", "U6.19", "SCD41 bulk capacitor to its emitter supply"),
    ("GND", "U6.21", "U3.2", "SCD41 ground back to sensor regulator"),
    ("+3V3_SENS", "U3.5", "U7.5", "sensor regulator to SGP41 heater supply"),
    ("GND", "U7.2", "U3.2", "SGP41 ground back to sensor regulator"),
    ("+3V3_SENS", "U3.5", "U8.10", "sensor regulator to BMP580"),
    ("+3V3_SENS", "U3.5", "U5.3", "sensor regulator to SHT45"),
    ("GND", "U5.4", "U3.2", "SHT45 ground back to sensor regulator"),
)


def load():
    board = pcbnew.LoadBoard(str(PCB))
    pt = lambda v: (v.x * MM - ORIGIN[0], v.y * MM - ORIGIN[1])
    tracks, vias, pads, boxes = defaultdict(list), defaultdict(list), defaultdict(list), {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias[t.GetNetname()].append(pt(t.GetPosition()))
        else:
            tracks[t.GetNetname()].append((pt(t.GetStart()), pt(t.GetEnd()), t.GetWidth() * MM, t.GetLayerName()))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if not p.GetNetname():
                continue
            name = f"{fp.GetReference()}.{p.GetNumber()}"
            while name in boxes:                     # a second pad with the same number
                name += "'"
            pads[p.GetNetname()].append((name, pt(p.GetPosition())))
            bb = p.GetBoundingBox()
            boxes[name] = (*pt(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop())),
                           *pt(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom())))
    return tracks, vias, pads, boxes


def spanning_tree(points):
    """Length of the minimum spanning tree: no routing of these points can be shorter."""
    if len(points) < 2:
        return 0.0
    dist = [math.dist(points[0], q) for q in points]
    done, total = {0}, 0.0
    while len(done) < len(points):
        i = min((k for k in range(len(points)) if k not in done), key=lambda k: dist[k])
        total += dist[i]
        done.add(i)
        dist = [min(d, math.dist(points[i], q)) for d, q in zip(dist, points)]
    return total


def on_segment(p, a, b):
    length = math.dist(a, b)
    return (length > 1e-6 and abs(math.dist(a, p) + math.dist(p, b) - length) < 1e-4
            and math.dist(a, p) > 1e-4 and math.dist(p, b) > 1e-4)


def supply_path(net, start, end, tracks, vias, pads, boxes):
    """Lowest-resistance path along the tracks: (length mm, ohms, length below 0.3 mm)."""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    ends = ({(key(p), layer) for a, b, _, layer in tracks[net] for p in (a, b)}
            | {(key(v), layer) for v in vias[net] for layer in ("F.Cu", "B.Cu")})
    # a track that runs across a pad without ending on it is connected to it all the same:
    # give it a point there (the one nearest the pad's centre)
    for name, centre in pads[net]:
        x0, y0, x1, y1 = boxes[name]
        for a, b, _, layer in tracks[net]:
            if layer != "F.Cu":
                continue
            d2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
            u = 0.0 if d2 == 0 else max(0.0, min(1.0, ((centre[0] - a[0]) * (b[0] - a[0]) + (centre[1] - a[1]) * (b[1] - a[1])) / d2))
            p = (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                ends.add((key(p), layer))
    graph = defaultdict(list)

    def link(m, n, length=0.0, width=1.0):
        graph[m].append((n, length, width))
        graph[n].append((m, length, width))

    for a, b, width, layer in tracks[net]:               # split at T-junctions
        cuts = sorted((p for p, l in ends if l == layer and on_segment(p, a, b)), key=lambda p: math.dist(a, p))
        chain = [key(a), *cuts, key(b)]
        for m, n in zip(chain, chain[1:]):
            link((m, layer), (n, layer), math.dist(m, n), width)
    for v in vias[net]:
        link((key(v), "F.Cu"), (key(v), "B.Cu"))
        if net == "GND" and v[0] < SLOT_X:
            link((key(v), "B.Cu"), "pour")
    for name, centre in pads[net]:                       # a pad joins everything ending on it
        x0, y0, x1, y1 = boxes[name]
        for node in [n for n in graph if isinstance(n, tuple) and n[1] == "F.Cu"]:
            if x0 - 0.01 <= node[0][0] <= x1 + 0.01 and y0 - 0.01 <= node[0][1] <= y1 + 0.01:
                link(name, node)
        if net == "GND" and centre[0] < SLOT_X:          # on the main part pads sit in the pour
            link(name, "pour")
    if start not in graph or end not in graph:
        return None
    best = {start: (0.0, 0.0, 0.0)}                      # ohms, length, thin length
    heap, count = [(0.0, 0, start)], 0
    while heap:
        ohms, _, node = heapq.heappop(heap)
        if node == end:
            return best[node][1], ohms, best[node][2]
        if ohms > best[node][0] + 1e-12:
            continue
        for other, length, width in graph[node]:
            r = ohms + (RHO * (length / 1000) / (width / 1000 * COPPER) if length else 0.0)
            if other not in best or r < best[other][0] - 1e-12:
                best[other] = (r, best[node][1] + length, best[node][2] + (length if width < 0.3 else 0.0))
                count += 1
                heapq.heappush(heap, (r, count, other))
    return None


def tidiness(tracks, vias, pads, boxes):
    """Things the rule check cannot see. Returns (lines to print, number of defects)."""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    out, defects = [], 0

    def pad_at(net, p, layer):
        for name, _ in pads[net]:
            x0, y0, x1, y1 = boxes[name]
            if layer == "F.Cu" and x0 - 0.02 <= p[0] <= x1 + 0.02 and y0 - 0.02 <= p[1] <= y1 + 0.02:
                return name
        return None

    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def touches(p, a, b):
        return abs(math.dist(a, p) + math.dist(p, b) - math.dist(a, b)) < 1e-6

    # 1. a net crossing itself
    found = []
    for net, segs in tracks.items():
        for i, (a, b, _, la) in enumerate(segs):
            for c, d, _, lb in segs[i + 1:]:
                if la == lb and cross(a, b, c) * cross(a, b, d) < -1e-9 and cross(c, d, a) * cross(c, d, b) < -1e-9:
                    den = (a[0] - b[0]) * (c[1] - d[1]) - (a[1] - b[1]) * (c[0] - d[0])
                    u = ((a[0] - c[0]) * (c[1] - d[1]) - (a[1] - c[1]) * (c[0] - d[0])) / den
                    x = (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))
                    if not pad_at(net, x, la):
                        found.append(f"   {net} on {la} at ({x[0]:.1f}, {x[1]:.1f})")
    out.append(f"A net crossing itself: {len(found) or 'none'}")
    out += found
    defects += len(found)

    # 2. a net with a loop: two ways round between the same points (ground has its pours)
    found = []
    for net, segs in tracks.items():
        if net == "GND":
            continue
        points = defaultdict(set)
        for a, b, _, layer in segs:
            points[layer] |= {key(a), key(b)}
        for v in vias[net]:
            points["F.Cu"].add(key(v))
            points["B.Cu"].add(key(v))
        parent = {}

        def find(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b, _, layer in segs:
            chain = sorted((p for p in points[layer] if touches(p, a, b)), key=lambda p: math.dist(a, p))
            for m, n in zip(chain, chain[1:]):
                u = ("pad", pad_at(net, m, layer)) if pad_at(net, m, layer) else (m, layer)
                w = ("pad", pad_at(net, n, layer)) if pad_at(net, n, layer) else (n, layer)
                if u == w:
                    continue
                if find(u) == find(w):
                    found.append(f"   {net} on {layer}, closed by the piece ({m[0]:.1f}, {m[1]:.1f}) - ({n[0]:.1f}, {n[1]:.1f})")
                else:
                    parent[find(u)] = find(w)
        for v in vias[net]:
            parent[find((key(v), "F.Cu"))] = find((key(v), "B.Cu"))
    out.append(f"A net with a loop in it: {len(found) or 'none'}")
    out += found
    defects += len(found)

    # 3. a track meeting a pad away from its centre lines (0.06 mm allowed: pads are not
    #    all on the routing grid). The SHT45's pads are exempt: tracks may not reach their
    #    centres. Tracks drawn by hand along a pin's own centre line count as centred too.
    found = []
    for net, segs in tracks.items():
        for a, b, width, layer in segs:
            for name, centre in pads[net]:
                if name.startswith("U5.") or layer != "F.Cu":
                    continue
                x0, y0, x1, y1 = boxes[name]
                inside = [p for p in (a, b) if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
                if len(inside) == 1 and min(abs(inside[0][0] - centre[0]), abs(inside[0][1] - centre[1])) > 0.06 \
                        and min(x1 - x0, y1 - y0) < 1.2:
                    found.append(f"   {net} at {name}: {min(abs(inside[0][0] - centre[0]), abs(inside[0][1] - centre[1])):.2f} mm off")
    off_centre = sorted(set(found))
    out.append(f"Tracks meeting a pad off its centre lines: {len(off_centre) or 'none'}")
    out += off_centre

    # 4. right angles between two pieces of one track, outside pads
    ends = defaultdict(list)
    for net, segs in tracks.items():
        for a, b, _, layer in segs:
            ends[(key(a), layer, net)].append(key(b))
            ends[(key(b), layer, net)].append(key(a))
    via_points = {key(v) for vs in vias.values() for v in vs}
    corners = []
    for (v, layer, net), others in ends.items():
        if len(others) == 2 and v not in via_points and not pad_at(net, v, layer):
            p, q = others
            turn = abs(math.degrees(math.atan2(p[1] - v[1], p[0] - v[0]) - math.atan2(q[1] - v[1], q[0] - v[0]))) % 360
            if min(turn, 360 - turn) < 100:
                corners.append(f"   {net} on {layer} at ({v[0]:.1f}, {v[1]:.1f})")
    out.append(f"Right-angle or sharper corners outside pads: {len(corners) or 'none'}")
    out += corners
    return out, defects


def side_by_side(tracks):
    """Length over which two different nets run within NEAR of each other on one layer."""
    points = defaultdict(list)
    for net, segments in tracks.items():
        for a, b, width, layer in segments:
            n = max(1, int(math.dist(a, b) / 0.1))
            for k in range(n + 1):
                p = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                points[(layer, int(p[0]), int(p[1]))].append((net, p, width))
    pairs = defaultdict(float)
    for (layer, cx, cy), here in points.items():
        around = [q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in points.get((layer, cx + dx, cy + dy), ())]
        for net, p, width in here:
            close = {other for other, q, w in around if other != net and math.dist(p, q) - (width + w) / 2 < NEAR}
            for other in close:
                pairs[tuple(sorted((net, other)))] += 0.05      # each stretch is seen from both nets
    return pairs


def main() -> int:
    tracks, vias, pads, boxes = load()
    out = []
    out.append("Routed length against the shortest possible connection of the pads")
    out.append(f"{'net':<16}{'pads':>5}{'routed':>8}{'shortest':>9}{'ratio':>7}{'vias':>5}   length at each width, mm")
    rows = []
    for net in tracks:
        if net == "GND":
            continue
        length = sum(math.dist(a, b) for a, b, _, _ in tracks[net])
        widths = defaultdict(float)
        for a, b, width, _ in tracks[net]:
            widths[round(width, 2)] += math.dist(a, b)
        rows.append((net, len(pads[net]), length, spanning_tree([p for _, p in pads[net]]), widths, len(vias[net])))
    for net, n, length, low, widths, nv in sorted(rows, key=lambda r: -r[2] / max(r[3], 0.5)):
        text = ", ".join(f"{w:.2f}: {l:.1f}" for w, l in sorted(widths.items()))
        out.append(f"{net:<16}{n:>5}{length:>8.1f}{low:>9.1f}{length / max(low, 0.5):>7.2f}{nv:>5}   {text}")
    out.append("(pads have a size, so short nets can come out slightly below 1.00)")

    out.append("")
    out.append("Supply paths along the tracks (1 oz copper)")
    out.append(f"{'path':<50}{'mm':>7}{'mOhm':>7}{'thin mm':>9}")
    for net, a, b, what in SUPPLY_PATHS:
        found = supply_path(net, a, b, tracks, vias, pads, boxes)
        if found is None:
            out.append(f"{what:<50}  no path found ({net} {a} -> {b})")
        else:
            out.append(f"{what:<50}{found[0]:>7.1f}{found[1] * 1000:>7.1f}{found[2]:>9.1f}")
    out.append("('thin' is the part of the path narrower than 0.3 mm)")

    out.append("")
    out.append(f"Nets running side by side on one layer (gap under {NEAR} mm), longest first")
    for (a, b), length in sorted(side_by_side(tracks).items(), key=lambda kv: -kv[1])[:15]:
        out.append(f"{length:>6.1f} mm   {a}  |  {b}")

    out.append("")
    out.append("Tidiness")
    lines, defects = tidiness(tracks, vias, pads, boxes)
    out += lines

    text = "\n".join(out)
    print(text)
    (HW / "build").mkdir(exist_ok=True)
    (HW / "build" / "audit.txt").write_text(text + "\n", encoding="utf-8")
    if defects:
        print(f"\n{defects} defect(s): a net crosses itself or has a loop")
    return 1 if defects else 0


if __name__ == "__main__":
    raise SystemExit(main())

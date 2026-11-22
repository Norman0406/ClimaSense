"""A small two-layer grid router for the ClimaSense board.

Pure Python, no KiCad dependency: it works on rectangles, discs and net
numbers and returns track segments and vias. The board generator feeds it the
pads and keep-outs and turns the result into KiCad tracks.

Model
-----
The board is a 0.1 mm grid. A track is the path of its centre line through
grid nodes. For every track width class there is one grid per layer that says,
for each node, whether a centre line of that class may be there:

    FREE      nobody's copper is near
    <net id>  only this net may be here (the node is within clearance of that
              net's copper, or on it)
    BLOCK     nobody may be here (board edge, keep-out, or within clearance of
              two different nets)

Obstacles are grown by "clearance + half the track width" when they are
entered, so the search itself only has to look at single nodes. Rectangles are
grown with square corners, which is slightly conservative. With this model a
path of 0/45/90 degree steps between allowed nodes cannot come closer to
foreign copper than the clearance, as long as diagonal steps do not cut
corners - the search enforces that.
"""

from __future__ import annotations

import heapq
import math

FREE, BLOCK = 0, -1
TOP, BOT = 0, 1
SQRT2 = math.sqrt(2.0)
_DIRS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
         (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2))


def _turn_table(gentle, right, sharp):
    """Extra cost of leaving a node in direction j after arriving in direction i."""
    table = []
    for ax, ay, al in _DIRS:
        row = []
        for bx, by, bl in _DIRS:
            cos = (ax * bx + ay * by) / (al * bl)
            row.append(0.0 if cos > 0.99 else gentle if cos > 0.5 else right if cos > -0.5 else sharp)
        table.append(row)
    return table


class Router:
    def __init__(self, width, height, step=0.1, clearance=0.16, via_radius=0.3, via_drill=0.3,
                 hole_to_hole=0.5, bottom_cost=1.5, via_cost=30.0, turn_cost=(0.2, 5.0, 20.0)):
        self.step = step
        self.nx = int(round(width / step)) + 1
        self.ny = int(round(height / step)) + 1
        self.n = self.nx * self.ny
        self.clear = clearance
        self.via_radius = via_radius
        self.via_spacing = via_drill + hole_to_hole + 0.05      # centre to centre, any two vias
        self.bottom_cost = bottom_cost
        self.via_cost = via_cost
        # A bend costs extra, in grid steps: almost nothing at 45 degrees, half a millimetre
        # at 90, two at anything sharper. A track then goes round a pad with two 45 degree
        # bends where there is room, and only turns a right angle where it has to.
        self.turn = _turn_table(*turn_cost)
        # half widths of what is being placed: thin track, power track, supply trunk, via
        self.half = {"sig": 0.1, "pwr": 0.2, "wide": 0.3, "via": via_radius}
        self.grid = {c: [[FREE] * self.n, [FREE] * self.n] for c in self.half}
        # where no copper may be at all (board edge, slots, keep-outs), whatever the net
        self.hard = {c: [[FREE] * self.n, [FREE] * self.n] for c in self.half}
        self.vias = []       # (x, y, net)
        self.tracks = []     # (x1, y1, x2, y2, layer, width, net)
        self._discs = {}

    # -- coordinates --------------------------------------------------------
    def cell(self, x, y):
        return int(round(y / self.step)) * self.nx + int(round(x / self.step))

    def xy(self, idx):
        iy, ix = divmod(idx, self.nx)
        return round(ix * self.step, 4), round(iy * self.step, 4)

    def node(self, x, y, layer):
        return layer * self.n + self.cell(x, y)

    # -- entering obstacles ---------------------------------------------------
    def _mark_rect(self, g, x0, y0, x1, y1, owner):
        s, nx = self.step, self.nx
        ix0 = max(0, int(math.ceil(x0 / s - 1e-6)))
        ix1 = min(nx - 1, int(math.floor(x1 / s + 1e-6)))
        iy0 = max(0, int(math.ceil(y0 / s - 1e-6)))
        iy1 = min(self.ny - 1, int(math.floor(y1 / s + 1e-6)))
        for iy in range(iy0, iy1 + 1):
            base = iy * nx
            for i in range(base + ix0, base + ix1 + 1):
                cur = g[i]
                if cur == FREE:
                    g[i] = owner
                elif cur != owner:
                    g[i] = BLOCK

    def _offsets(self, radius):
        key = round(radius, 3)
        if key not in self._discs:
            r = radius / self.step
            k = int(math.ceil(r))
            self._discs[key] = [(dx, dy) for dy in range(-k, k + 1) for dx in range(-k, k + 1)
                                if dx * dx + dy * dy <= r * r + 1e-9]
        return self._discs[key]

    def _mark_disc(self, g, idx, radius, owner):
        nx, ny = self.nx, self.ny
        iy0, ix0 = divmod(idx, nx)
        for dx, dy in self._offsets(radius):
            x, y = ix0 + dx, iy0 + dy
            if 0 <= x < nx and 0 <= y < ny:
                i = y * nx + x
                cur = g[i]
                if cur == FREE:
                    g[i] = owner
                elif cur != owner:
                    g[i] = BLOCK

    def block_rect(self, x0, y0, x1, y1, layers=(TOP, BOT), grow=0.0, classes=None):
        """Forbid an area. `grow` is the distance copper must keep from it."""
        for c in classes or self.half:
            e = grow + self.half[c]
            for layer in layers:
                self._mark_rect(self.grid[c][layer], x0 - e, y0 - e, x1 + e, y1 + e, BLOCK)
                self._mark_rect(self.hard[c][layer], x0 - e, y0 - e, x1 + e, y1 + e, BLOCK)

    def block_disc(self, x, y, radius, layers=(TOP, BOT), grow=0.0, classes=None):
        for c in classes or self.half:
            for layer in layers:
                self._mark_disc(self.grid[c][layer], self.cell(x, y), radius + grow + self.half[c], BLOCK)
                self._mark_disc(self.hard[c][layer], self.cell(x, y), radius + grow + self.half[c], BLOCK)

    def reserve_rect(self, net, x0, y0, x1, y1, layers, classes=("sig", "pwr", "wide")):
        """Keep an area for the tracks of one net only (vias are not affected)."""
        for c in classes:
            for layer in layers:
                self._mark_rect(self.grid[c][layer], x0, y0, x1, y1, net)

    def copper_rect(self, net, x0, y0, x1, y1, layers):
        """Copper of `net` (a pad)."""
        for c, half in self.half.items():
            e = self.clear + half
            for layer in layers:
                self._mark_rect(self.grid[c][layer], x0 - e, y0 - e, x1 + e, y1 + e, net)

    def _copper_node(self, net, idx, layer, radius):
        for c, half in self.half.items():
            self._mark_disc(self.grid[c][layer], idx, radius + self.clear + half, net)

    # -- committing results -------------------------------------------------
    def add_via(self, net, x, y):
        idx = self.cell(x, y)
        for layer in (TOP, BOT):
            self._copper_node(net, idx, layer, self.via_radius)
            # no second via closer than the drill spacing rule allows, not even on the same net
            self._mark_disc(self.grid["via"][layer], idx, self.via_spacing, BLOCK)
        self.vias.append((x, y, net))

    def add_track(self, net, pts, layer, width):
        """Commit a polyline that already follows the grid (or stays inside own copper)."""
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            if (xa, ya) != (xb, yb):
                self.tracks.append((xa, ya, xb, yb, layer, width, net))
            steps = max(1, int(math.ceil(math.hypot(xb - xa, yb - ya) / self.step)))
            for k in range(steps + 1):
                t = k / steps
                self._copper_node(net, self.cell(xa + (xb - xa) * t, ya + (yb - ya) * t), layer, width / 2)

    def commit_path(self, net, path, width, start_xy=None):
        """Turn a node path from `find` into tracks and vias. `start_xy` is the exact
        pad centre the path leaves from (it may be off the grid)."""
        n = self.n
        runs, cur = [], []
        for a, b in zip(path, path[1:]):
            la, ia = divmod(a, n)
            lb, ib = divmod(b, n)
            if not cur:
                cur = [(la, ia)]
            if la != lb:
                runs.append(cur)
                cur = []
                self.add_via(net, *self.xy(ia))
            else:
                cur.append((lb, ib))
        if cur:
            runs.append(cur)
        if not runs:
            runs = [[divmod(path[0], n)]]
        first = True
        for run in runs:
            layer = run[0][0]
            pts = [self.xy(i) for _, i in run]
            if first and start_xy is not None and pts[0] != tuple(start_xy):
                pts.insert(0, tuple(start_xy))
            first = False
            self.add_track(net, _simplify(pts), layer, width)

    # -- straightening ---------------------------------------------------------
    def octile(self, a, b):
        """Nodes from `a` to `b` on one layer: one straight run, then one diagonal run."""
        n, nx = self.n, self.nx
        layer = a // n
        (ax, ay), (bx, by) = ((a % n) % nx, (a % n) // nx), ((b % n) % nx, (b % n) // nx)
        dx, dy = bx - ax, by - ay
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        straight = (sx, 0, abs(dx) - abs(dy)) if abs(dx) > abs(dy) else (0, sy, abs(dy) - abs(dx))
        out, x, y = [a], ax, ay
        for mx, my, count in (straight, (sx, sy, min(abs(dx), abs(dy)))):
            for _ in range(count):
                x, y = x + mx, y + my
                out.append(layer * n + y * nx + x)
        return out

    def straighten(self, net, path, cls):
        """Redraw a path from `find` with as few bends as possible.

        The search returns one of many equally short paths, usually one that wanders in
        small steps. Between two of its corners the shortest connection is one straight
        run plus one diagonal run; wherever that is free, it replaces what is in between.
        End points, layer changes and length stay the same.
        """
        n = self.n
        out, run = [], [path[0]]
        for node in path[1:]:
            if node // n != run[-1] // n:
                out += self._straighten_run(net, run, cls)
                run = [node]
            else:
                run.append(node)
        return out + self._straighten_run(net, run, cls)

    def _straighten_run(self, net, run, cls):
        if len(run) < 4:
            return run
        n, nx = self.n, self.nx
        layer = run[0] // n
        g = self.grid[cls][layer]
        pts = [((node % n) % nx, (node % n) // nx) for node in run]

        def free(x, y):
            v = g[y * nx + x]
            return v == FREE or v == net

        def walk(a, moves):
            x, y = a
            got = []
            for dx, dy, count in moves:
                for _ in range(count):
                    if dx and dy and not (free(x + dx, y) and free(x, y + dy)):
                        return None                      # a diagonal step may not cut a corner
                    x, y = x + dx, y + dy
                    if not free(x, y):
                        return None
                    got.append((x, y))
            return got

        def link(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
            diagonal = (sx, sy, min(abs(dx), abs(dy)))
            straight = (sx, 0, abs(dx) - abs(dy)) if abs(dx) > abs(dy) else (0, sy, abs(dy) - abs(dx))
            return walk(a, (straight, diagonal)) or walk(a, (diagonal, straight))

        step = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
        corners = [0] + [k for k in range(1, len(pts) - 1) if step[k - 1] != step[k]] + [len(pts) - 1]
        result, ci = [pts[0]], 0
        while ci < len(corners) - 1:
            for cj in range(len(corners) - 1, ci, -1):
                if cj == ci + 1:
                    piece = pts[corners[ci] + 1:corners[cj] + 1]
                    break
                piece = link(pts[corners[ci]], pts[corners[cj]])
                if piece:
                    break
            result += piece
            ci = cj
        return [layer * n + y * nx + x for x, y in result]

    # -- searching ------------------------------------------------------------
    def passable(self, cls, layer, idx, net):
        v = self.grid[cls][layer][idx]
        return v == FREE or v == net

    def via_allowed(self, idx, net):
        gv = self.grid["via"]
        a, b = gv[TOP][idx], gv[BOT][idx]
        return (a == FREE or a == net) and (b == FREE or b == net)

    def cells_in_rect(self, x0, y0, x1, y1):
        s, nx = self.step, self.nx
        ix0 = max(0, int(math.ceil(x0 / s - 1e-6)))
        ix1 = min(nx - 1, int(math.floor(x1 / s + 1e-6)))
        iy0 = max(0, int(math.ceil(y0 / s - 1e-6)))
        iy1 = min(self.ny - 1, int(math.floor(y1 / s + 1e-6)))
        return [iy * nx + ix for iy in range(iy0, iy1 + 1) for ix in range(ix0, ix1 + 1)]

    def find(self, net, sources, cls, targets=None, goal=None, allow_via=True, limit=900000,
             layers=(TOP, BOT)):
        """Cheapest path for `net` from any source node to a target.

        sources  {node: start cost}
        targets  set of nodes, or
        goal     function(node) -> bool (then the search is uninformed)
        Returns the list of nodes, or None.
        """
        if not sources:
            return None
        n, nx, ny = self.n, self.nx, self.ny
        grid = self.grid[cls]
        gv = self.grid["via"]
        if targets is not None:
            if not targets:
                return None
            cols = [(t % n) % nx for t in targets]
            rows = [(t % n) // nx for t in targets]
            bx0, bx1, by0, by1 = min(cols), max(cols), min(rows), max(rows)

            def h(ix, iy):
                dx = bx0 - ix if ix < bx0 else (ix - bx1 if ix > bx1 else 0)
                dy = by0 - iy if iy < by0 else (iy - by1 if iy > by1 else 0)
                return (dx + dy) + (SQRT2 - 2) * min(dx, dy)
        else:
            def h(ix, iy):
                return 0.0
        best = dict(sources)
        prev = {}
        came = {}            # node -> index of the step that reached it (for the bend cost)
        turn = self.turn
        heap = []
        for s, c in sources.items():
            idx = s % n
            heap.append((c + h(idx % nx, idx // nx), c, s))
        heapq.heapify(heap)
        cost_of = (1.0, self.bottom_cost)
        count = 0
        while heap:
            _, cst, node = heapq.heappop(heap)
            if cst > best.get(node, 1e18):
                continue
            if (targets is not None and node in targets) or (goal is not None and goal(node)):
                path = [node]
                while node in prev:
                    node = prev[node]
                    path.append(node)
                return path[::-1]
            count += 1
            if count > limit:
                return None
            layer, idx = divmod(node, n)
            iy, ix = divmod(idx, nx)
            gl = grid[layer]
            lc = cost_of[layer]
            base = layer * n
            bend = turn[came[node]] if node in came else None
            for di, (dx, dy, dc) in enumerate(_DIRS):
                x, y = ix + dx, iy + dy
                if x < 0 or y < 0 or x >= nx or y >= ny:
                    continue
                j = y * nx + x
                v = gl[j]
                if v != FREE and v != net:
                    continue
                if dx and dy:
                    v1, v2 = gl[iy * nx + x], gl[y * nx + ix]
                    if (v1 != FREE and v1 != net) or (v2 != FREE and v2 != net):
                        continue
                nc = cst + dc * lc + (bend[di] if bend else 0.0)
                nn = base + j
                if nc < best.get(nn, 1e18):
                    best[nn] = nc
                    prev[nn] = node
                    came[nn] = di
                    heapq.heappush(heap, (nc + h(x, y), nc, nn))
            if allow_via:
                other = 1 - layer
                if other in layers:
                    a, b = gv[TOP][idx], gv[BOT][idx]
                    if (a == FREE or a == net) and (b == FREE or b == net):
                        v = grid[other][idx]
                        if v == FREE or v == net:
                            nc = cst + self.via_cost
                            nn = other * n + idx
                            if nc < best.get(nn, 1e18):
                                best[nn] = nc
                                prev[nn] = node
                                came.pop(nn, None)       # a via starts a new run
                                heapq.heappush(heap, (nc + h(ix, iy), nc, nn))
        return None


def _simplify(pts):
    """Drop points that lie on a straight line between their neighbours."""
    out = [pts[0]]
    for p in pts[1:]:
        if p == out[-1]:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            cross = (bx - ax) * (p[1] - by) - (by - ay) * (p[0] - bx)
            dot = (bx - ax) * (p[0] - bx) + (by - ay) * (p[1] - by)
            if abs(cross) < 1e-9 and dot > 0:
                out[-1] = p
                continue
        out.append(p)
    return out

"""The drawing order of each edge, from the data alone (docs/design/levels_split_casing.md): ``casing_level_col`` / ``fill_level_col``."""
from __future__ import annotations

import warnings
from collections import defaultdict


def _level(row, layer_col, bridge_col, tunnel_col):
    """The OSM level of an edge: a non-zero ``layer``, else bridge 1, tunnel -1, else 0 (the rule of ``render_edges``)."""
    import pandas as pd

    from .render_web import _truthy
    row = {k: (None if pd.isna(v) else v) for k, v in row.items() if k in (layer_col, bridge_col, tunnel_col)}   # NaN is null here, as in the GeoJSON the renderer reads
    try:
        ly = int(float(row.get(layer_col)))
    except (TypeError, ValueError):
        ly = 0
    return ly or (1 if _truthy(row.get(bridge_col)) else -1 if _truthy(row.get(tunnel_col)) else 0)


_TIER = 100      # order="priority": each tier is over every class (the class orders are 0 to 9)


def _tier(row, junction_col, bridge_col, tunnel_col):
    """order="priority": roundabout 3, tunnel 2, bridge 1, any other road 0 (Kaveh, 2026-10-06)."""
    import pandas as pd

    from .render_web import _truthy
    row = {k: (None if pd.isna(v) else v) for k, v in row.items() if k in (junction_col, bridge_col, tunnel_col)}
    if str(row.get(junction_col) or "").lower() in ("roundabout", "circular"):
        return 3
    return 2 if _truthy(row.get(tunnel_col)) else 1 if _truthy(row.get(bridge_col)) else 0


def _tag_intervals(ends, lv):
    """method="tags": c = min(N(s), N(t), L), f = max(...), N(v) the point of [min S(v), max S(v)] nearest 0."""
    at = defaultdict(set)
    for (a, b), L in zip(ends, lv, strict=True):
        at[a].add(L), at[b].add(L)
    N = {v: min(max(0, min(s)), max(s)) for v, s in at.items()}
    return [(min(N[a], N[b], L), max(N[a], N[b], L)) for (a, b), L in zip(ends, lv, strict=True)]


def _compress(values):
    """Order-preserving small integers: negatives to -1, -2 ..., positives to 1, 2 ..., zero stays zero."""
    vs = sorted(set(values) | {0})
    neg, pos = [v for v in vs if v < 0], [v for v in vs if v > 0]
    m = {0: 0}
    m.update({v: -(len(neg) - i) for i, v in enumerate(neg)})
    m.update({v: i + 1 for i, v in enumerate(pos)})
    return m


def _class_order(highway):
    """The class order ``z_order`` of the renderer (a link just under its parent, or the table's own value): higher = on top."""
    from .render_web import ROAD_Z, _base
    b, link = _base(highway)
    return ROAD_Z[highway] if highway in ROAD_Z else ROAD_Z.get(b, 4) - (0.5 if link else 0)


def _difference_lp(cost, A, b, hi):
    """Stage 0 as a minimum-cost flow. Every row of ``A`` is ``x_i - x_j <= b`` (one +1, one -1, integer ``b``): the dual of this LP is a min-cost
    flow on the arcs ``i -> j`` (cost ``b``, supply ``-cost``, the cost coefficients sum to 0). OR-tools solves the flow; the numbers ``x`` are the shortest
    distances from an extra node ``Z`` (arcs ``Z -> v`` of cost 0) in the residual graph (arc ``j -> i`` of cost ``b`` for each row, and ``i -> j`` of cost
    ``-b`` where the flow runs), found by repeated relaxation until nothing changes. The bounds ``0 <= x <= hi`` are not in the flow: the result is shifted
    to start at 0 and its range is checked. Returns ``x``, or ``None`` when the flow cannot certify the answer (an arc is saturated: the system has no
    solution; the cost is not integral; a costed variable is in no row; or the range is above ``hi``); the caller then solves the LP with HiGHS."""
    import numpy as np
    from ortools.graph.python import min_cost_flow
    n, A = A.shape[1], A.tocoo()
    cc, w = np.round(cost).astype(np.int64), np.round(b).astype(np.int64)
    if (np.abs(cost - cc) > 1e-9).any() or (np.abs(b - w) > 1e-9).any() or cc.sum() != 0:
        return None
    pos = A.data > 0
    if A.nnz != 2 * A.shape[0] or pos.sum() != A.shape[0] or (np.abs(A.data) != 1).any():
        raise ValueError("compute_levels: a row of the LP is not x_i - x_j <= b")
    ii, jj = np.empty(A.shape[0], np.int64), np.empty(A.shape[0], np.int64)
    ii[A.row[pos]], jj[A.row[~pos]] = A.col[pos], A.col[~pos]
    touched = np.zeros(n, bool)
    touched[ii] = touched[jj] = True
    if (cc[~touched] != 0).any():                      # a costed variable in no row: OR-tools does not know the node (and crashes); the LP has the bounds
        return None
    cap = int(np.abs(cc).sum()) + 1
    f = min_cost_flow.SimpleMinCostFlow()
    f.add_arcs_with_capacity_and_unit_cost(ii, jj, np.full(len(ii), cap), w)
    for v in np.nonzero(cc)[0]:
        f.set_node_supply(int(v), int(-cc[v]))
    if f.solve() != f.OPTIMAL:
        return None
    flow = f.flows(np.arange(len(ii)))
    if (flow >= cap).any():
        return None
    used, Z = flow > 0, n
    src = np.concatenate([jj, ii[used], np.full(n, Z)])
    dst = np.concatenate([ii, jj[used], np.arange(n)])
    wt = np.concatenate([w, -w[used], np.zeros(n, np.int64)]).astype(float)
    order = np.argsort(dst, kind="stable")
    src, dst, wt = src[order], dst[order], wt[order]
    first = np.r_[0, np.nonzero(np.diff(dst))[0] + 1]
    heads = dst[first]
    dist = np.full(n + 1, np.inf)
    dist[Z] = 0.0
    for _ in range(n + 2):
        new = np.minimum(dist[heads], np.minimum.reduceat(dist[src] + wt, first))
        if np.array_equal(new, dist[heads]):
            break
        dist[heads] = new
    else:
        return None
    x = dist[:n] - dist[:n].min()
    if not np.isfinite(x).all() or (x[ii] - x[jj] > w + 1e-9).any():
        raise RuntimeError("compute_levels: the flow solution is not a solution of the LP")
    return x if x.max() <= hi + 1e-9 else None


def _relations(metres, ends, beta, omega, band_dist, mouths=True):
    """The relations of the roads (docs/design/level_input.md): ``(meets, stacks, orders)``.
    ``meets``: ``(x, x_end, y, y_end)`` for every two roads whose ends ``x_end`` / ``y_end`` ("start" / "end") are one node; ``stacks``: ``(upper, lower)``
    for roads of different bands that cross or run within ``band_dist`` metres of each other away from a node they share; ``orders``: ``(higher, lower)``
    by ``omega`` for roads that meet, of one band or of different bands that only meet (Kaveh 2026-10-06: at a tunnel mouth the priority decides,
    where roads cross the band does; at a mouth where the upper band's road goes on into a road that crosses over the lower one, the band too). ``mouths`` False: roads of different bands are always a stack pair, as when the caller gives the bands
    (``band_col``: a zebra crossing set over its street stays over it). ``metres``: the roads' lines in metres."""
    import shapely
    from shapely import STRtree

    at = defaultdict(list)                                     # node -> [(road, end)]
    for r, (s, t) in enumerate(ends):
        at[s].append((r, "start"))
        at[t].append((r, "end"))
    meets, shared = [], defaultdict(set)                        # shared[(x, y)]: the nodes the two roads share
    for v, here in at.items():
        for i, (x, ex) in enumerate(here):
            for y, ey in here[i + 1:]:
                if x != y:
                    meets.append((x, ex, y, ey) if x < y else (y, ey, x, ex))
                    shared[(min(x, y), max(x, y))].add(v)
    node_at = {}
    for r, (s, t) in enumerate(ends):
        node_at.setdefault(s, shapely.get_point(metres[r], 0))
        node_at.setdefault(t, shapely.get_point(metres[r], -1))
    near = set()
    if len(set(beta)) > 1:
        qi, ti = STRtree(metres).query(metres, predicate="dwithin", distance=band_dist)
        near = {(i, j) for i, j in zip(qi.tolist(), ti.tolist(), strict=True) if i < j and beta[i] != beta[j]}
    stacks, only_meet = [], set()
    for i, j in sorted(near):
        if mouths and (i, j) in shared:                        # they meet: a stack pair only if they are near away from the junction(s)
            hole = shapely.union_all([node_at[v].buffer(band_dist) for v in shared[(i, j)]])
            a, b = metres[i].difference(hole), metres[j].difference(hole)
            if a.is_empty or b.is_empty or a.distance(b) > band_dist:
                only_meet.add((i, j))
                continue
        stacks.append((i, j) if beta[i] > beta[j] else (j, i))
    orders = []
    if omega is not None:
        crossing, joined = set(stacks), defaultdict(set)
        for x, _, y, _ in meets:
            joined[x].add(y)
            joined[y].add(x)
        for x, y in sorted(shared):
            if (x, y) in only_meet:                            # a mouth: the priority decides, unless the upper band's road goes on into a
                up, down = (x, y) if beta[x] > beta[y] else (y, x)    # road that crosses over the lower one: then the band, like the rest of
                if any((n, down) in crossing for n in joined[up] - {down}):   # its street (Kaveh 2026-10-06: the street was cut by its tunnel)
                    orders.append((up, down))
                    continue
            if omega[x] is None or omega[y] is None or omega[x] == omega[y]:
                continue
            if beta[x] == beta[y] or (x, y) in only_meet:
                orders.append((x, y) if omega[x] > omega[y] else (y, x))
    return meets, stacks, orders


def _solve_intervals(metres, meets, stacks, orders, limit, max_level, margin, min_positions=True, max_positions=None, forced=(), off=(), empty=(), near=()):
    """The solver on roads (one per segment, both directions together) and their relations (:func:`_relations`, or a pairs table). Every road has
    one fill number ``b`` and a casing of three parts: a start head, a main part and an end head, whatever its length (Kaveh 2026-10-06: the
    drawing gives a part its metres, zero for the main part of a road shorter than its two heads; the solver takes no length). ``empty``: the
    roads whose main part is drawn with no length; a stack never lifts it (a rule on a part nobody sees would only cost real ones). ``near``:
    the stack rules ``(upper, lower, "s" / "m" / "e")`` whose part does not cross the lower road: kept last, after the order wishes (Kaveh
    2026-10-06: a part that only comes near is a warning, never worth a real crossing or a wish); an edit's part is never near.
    Returns ``(parts, given_up, info)``: ``parts[r] = (a_start, a_main, a_end, b)``. The model is a linear program solved on a sparse matrix with
    HiGHS (docs/design/levels_split_casing.md, section 7)."""
    import time
    from types import SimpleNamespace

    import numpy as np
    import scipy.sparse as sp
    t0, n = time.time(), len(metres)
    zero = [(0, 0, 0, 0)] * n
    whole = set(stacks)                                        # the stack pairs of the whole road (the rule below); forced / off: (A, B, "s" / "m" / "e")
    pair_list = sorted(whole | {(u, l) for u, l, _ in forced})
    empty = set(empty)
    info = {"pairs": len(pair_list), "roads": n, "meets": len(meets), "empty_mains": len(empty)}
    O = sorted(set(orders))
    if not pair_list and not O:
        return zero, [], {**info, "pairs": 0, "order_pairs": 0, "order_violations": 0, "solves": 0, "seconds": 0.0}      # no pair, no order: all zero is the optimum

    # variables: b_r = column r; then the three casing parts of every road; the slacks of the stages 1-3 come after
    part, ncol, casing = [], n, []                             # part[r]: "s" / "m" / "e" -> column; casing: (road, column) of every casing part
    for r in range(n):
        part.append({"s": ncol, "m": ncol + 1, "e": ncol + 2})
        casing += [(r, ncol), (r, ncol + 1), (r, ncol + 2)]
        ncol += 3
    rows, cols, vals, rhs = [], [], [], []
    def le(terms, c):                                          # sum(coefficient * variable) <= c, one sparse row
        k = len(rhs)
        for v, co in terms:
            rows.append(k), cols.append(v), vals.append(co)
        rhs.append(c)
    for r, v in casing:
        le([(v, 1.0), (r, -1.0)], 0.0)                         # H1: a_c <= b_road(c)
    for x, ex, y, ey in meets:                                 # H2: the heads of two roads that meet are each under the other's fill
        le([(part[x]["s" if ex == "start" else "e"], 1.0), (y, -1.0)], 0.0)
        le([(part[y]["s" if ey == "start" else "e"], 1.0), (x, -1.0)], 0.0)
    if min_positions or max_positions:                         # section 7.3.1: H above and L below every number; the span H - L is in the cost
        H, Lo, first_nv = ncol, ncol + 1, ncol
        for v in range(first_nv):
            le([(v, 1.0), (H, -1.0)], 0.0)                     # x_v <= H
            le([(Lo, 1.0), (v, -1.0)], 0.0)                    # L <= x_v
        ncol += 2
        if max_positions:                                      # at most max_positions numbers: H - L <= (max_positions - 1) steps (a hard bound;
            le([(H, 1.0), (Lo, -1.0)], (max_positions - 1) * margin)   # the stack pairs and the order wishes give way to it)
    base = len(rhs)
    # H3, A over B (Kaveh 2026-10-06): every part of A's casing (start head, main part, end head; a short road's one number), and so its fill (H1),
    # after B's fill: b_B + margin <= a_(A, part). Left out: a head of A that joins B, or joins a road that joins B (the next piece of the tunnel
    # A runs into at its mouth): a junction, where the head is under the fills it joins (H2); without it such a head and the head of a street
    # over that next piece made a loop no order can keep. Two ramps, each over one tube of a tunnel and joining the other tube, still make one:
    # the solver gives one of their pairs up and says so (Monaco: 16).
    touching = defaultdict(set)                                # road -> the roads it shares a node with
    for x, _, y, _ in meets:
        touching[x].add(y)
        touching[y].add(x)
    at_head = defaultdict(set)                                 # (road, "s" / "e") -> the roads that head joins
    for x, ex, y, ey in meets:
        at_head[(x, "s" if ex == "start" else "e")].add(y)
        at_head[(y, "s" if ey == "start" else "e")].add(x)
    def junction(u, heads, l):
        return any(l in at_head[(u, h)] or at_head[(u, h)] & touching[l] for h in heads)
    stack_rows, row_near = [], []                              # (pair index, the casing column it lifts); whether that rule is only "near"
    near = set(near)
    off, forced = set(off), set(forced)
    for k, (u, l) in enumerate(pair_list):
        lift = []
        if (u, l) in whole:
            lift = [part[u][h] for h in ("m", "s", "e") if (u not in empty if h == "m" else not junction(u, (h,), l)) and (u, l, h) not in off]
        own = {part[u][h] for (a, b, h) in forced if (a, b) == (u, l)}          # an edit's part: lifted even at a junction, never near
        name = {c: h for h, c in part[u].items()}
        for c in dict.fromkeys(lift + sorted(own)):
            stack_rows.append((k, c))
            row_near.append(c not in own and (u, l, name[c]) in near)
    for k, c in stack_rows:
        le([(pair_list[k][1], 1.0), (c, -1.0)], -margin)
    for x, y in O:
        le([(y, 1.0), (x, -1.0)], -margin)                     # H4: b_y + margin <= b_x
    nrow, nP, nO = len(rhs), len(stack_rows), len(O)
    A0 = sp.csr_matrix((vals, (rows, cols)), shape=(nrow, ncol))
    b_ub = np.array(rhs)
    cost = np.zeros(ncol)                                      # T3: the sum of (b_road(c) - a_c)
    for r, v in casing:
        cost[r] += 1.0
        cost[v] -= 1.0
    if min_positions or max_positions:
        w4 = float(cost[cost > 0].sum() * 2 * max_level + 1)   # W4 > the whole range of T3
        cost[H], cost[Lo] = w4, -w4

    def solve(c, A, bu, lo_hi):
        # whole numbers (HiGHS MILP): a staged problem (its "keep the stage before" rows) has fractional corners, and every fraction was
        # one more drawing position (Monaco: 15 numbers in a span of 9)
        from scipy.optimize import Bounds, LinearConstraint, milp
        lo_hi = [lo_hi] * len(c) if isinstance(lo_hi, tuple) else lo_hi
        lo = np.array([b[0] if b[0] is not None else -np.inf for b in lo_hi], dtype=float)
        hi = np.array([b[1] if b[1] is not None else np.inf for b in lo_hi], dtype=float)
        # in steps of the margin: whole multiples of it (the margin is the step of every constraint; it only scales the numbers)
        r = milp(c, constraints=LinearConstraint(A, -np.inf, np.asarray(bu, dtype=float) / margin), bounds=Bounds(lo / margin, hi / margin),
                 integrality=np.ones(len(c)), options={"time_limit": limit})
        x = None if r.x is None else r.x * margin
        return SimpleNamespace(status={0: 0, 2: 2}.get(r.status, r.status), x=x, fun=None if r.fun is None else r.fun * margin, message=r.message)
    box = (0, 2 * max_level)                                  # non-negative: the lowest number is pinned at 0; the shift to the ground comes afterwards
    solves, staged = 1, False
    x0 = _difference_lp(cost, A0, b_ub, box[1])                # stage 0: nothing violated; a min-cost flow
    if x0 is not None:
        res, how = SimpleNamespace(status=0, x=x0), "flow"
    else:
        res, how = solve(cost, A0, b_ub, box), "highs"          # the flow cannot certify: the LP with HiGHS
    slack = np.zeros(nP + nO)
    if res.status == 2:                                        # infeasible: some stack rules / wishes must be broken: stages with slacks
        S = sp.csr_matrix((-np.ones(nP + nO), (np.arange(base, nrow), np.arange(nP + nO))), shape=(nrow, nP + nO))
        A1 = sp.hstack([A0, S], format="csr")
        bounds = [box] * ncol + [(0, None)] * (nP + nO)
        rn = np.asarray(row_near, dtype=bool)
        stages = [np.concatenate([np.zeros(ncol), (~rn).astype(float), np.zeros(nO)]),     # 1: the real crossings
                  np.concatenate([np.zeros(ncol), np.zeros(nP), np.ones(nO)]),             # 2: the order wishes
                  np.concatenate([np.zeros(ncol), rn.astype(float), np.zeros(nO)])]        # 3: the near rules
        Ak, bk = A1, b_ub
        for c in stages:                                       # each stage at its optimum, held by the next ones
            if not c.any():
                continue
            r = solve(c, Ak, bk, bounds)
            if r.status != 0:
                raise RuntimeError(f"compute_levels: the solver returned status {r.status}: {r.message}")
            solves += 1
            Ak, bk = sp.vstack([Ak, sp.csr_matrix(c)], format="csr"), np.append(bk, r.fun + 1e-7 * max(1.0, r.fun))
        res = solve(np.concatenate([cost, np.zeros(nP + nO)]), Ak, bk, bounds)
        solves += 1
        staged = True
    if res.status != 0:
        raise RuntimeError(f"compute_levels: the solver returned status {res.status}: {res.message}")
    x = res.x
    if staged:
        slack = x[ncol:]
    x = np.round(x[:ncol], 6)
    integral = bool(np.all(np.abs(x - np.round(x)) < 1e-6))
    val = (lambda v: int(round(v))) if integral else (lambda v: float(v))             # integers in practice: the constraints are x - y <= c with integer c
    parts = [(val(x[part[r]["s"]]), val(x[part[r]["m"]]), val(x[part[r]["e"]]), val(x[r])) for r in range(n)]
    broke = [i for i in range(nP) if slack[i] >= margin * (1 - 1e-6)]                 # a part of the upper casing is not after the lower fill
    gu = sorted({pair_list[stack_rows[i][0]] for i in broke if not row_near[i]})       # given up: a real crossing broke; a near rule is a warning
    violated = int((slack[nP:] >= margin * (1 - 1e-6)).sum())
    name = {c: (r, h) for r in range(n) for h, c in part[r].items()}
    word = {"s": "start", "m": "main", "e": "end"}
    info["given_up_parts"] = sorted({(*pair_list[stack_rows[i][0]], word[name[stack_rows[i][1]][1]]) for i in broke if not row_near[i]})
    info["near_parts"] = sorted({(*pair_list[stack_rows[i][0]], word[name[stack_rows[i][1]][1]]) for i in broke if row_near[i]})
    info["near_warnings"] = len({(u, l) for u, l, _ in info["near_parts"]})              # pairs, as given_up counts them
    return parts, gu, {**info, "order_pairs": nO, "order_violations": violated, "solves": solves, "solver": how, "status": "OPTIMAL", "seconds": round(time.time() - t0, 1)}


def _road_split(g):
    """Both directions of a segment are one road: ``(ends, first, rid, same)``: the end nodes of every row (exact equality of the end points),
    the first row of every road, the road of every row, and whether a row runs the same way as its road's first row."""
    import numpy as np
    import shapely
    geoms = np.asarray(g.geometry.values, dtype=object)
    xy, gi = shapely.get_coordinates(geoms, return_index=True)
    cnt = np.bincount(gi, minlength=len(geoms))
    if (cnt < 2).any():
        raise ValueError(f"compute_levels: every edge needs a line of at least two points; rows {list(g.index[cnt < 2][:5])} have not")
    off = np.r_[0, np.cumsum(cnt)]
    _, node = np.unique(np.vstack([xy[off[:-1]], xy[off[1:] - 1]]), axis=0, return_inverse=True)
    node = node.ravel()
    ends = list(zip(node[:len(geoms)].tolist(), node[len(geoms):].tolist(), strict=True))
    fwd = [xy[off[i]:off[i + 1]].tobytes() for i in range(len(geoms))]
    rev = [xy[off[i]:off[i + 1]][::-1].tobytes() for i in range(len(geoms))]
    road, first = {}, []
    for i, k in enumerate((frozenset(e), min(f, r)) for e, f, r in zip(ends, fwd, rev, strict=True)):
        if k not in road:
            road[k] = len(first)
            first.append(i)
    rid = [road[(frozenset(e), min(f, r))] for e, f, r in zip(ends, fwd, rev, strict=True)]
    same = [fwd[i] == fwd[first[rid[i]]] for i in range(len(geoms))]
    return ends, first, rid, same


def _metres(geoseries):
    return geoseries.to_crs(geoseries.estimate_utm_crs()) if geoseries.crs is not None and geoseries.crs.is_geographic else geoseries


def level_input(edges, id_col="edge_id", layer_col="layer", bridge_col="bridge", tunnel_col="tunnel", band_col=None, order="priority",
                highway_col="highway", junction_col="junction", band_dist=10.0):
    """The solver's input (docs/design/level_input.md), from any edges roadstyle draws: ``(roads, pairs)``.

    ``roads``: one row per road (both directions of a segment together): ``road`` (the ``id_col`` of its first edge, as text; the row number
    without ``id_col``), ``edges`` / ``reversed`` (the ids of its edges in its own direction / the other way), ``band`` (``band_col``, else the
    level from the tags), ``priority`` (the ``order``: ``"priority"``, ``"class"``, a column of numbers, or None) and the geometry of its first
    edge, and its ``highway_col``, ``name``, ``edge_ref``, ``lanes``, ``tunnel_col``, ``bridge_col`` and ``layer_col`` when the edges have them. ``pairs``: one row per relation, ``relation`` / ``a`` / ``b`` / ``a_end`` / ``b_end``: ``meet`` (the end ``a_end`` of ``a`` is the end
    ``b_end`` of ``b``), ``stack`` (``a`` is over ``b``: different bands, crossing or near away from a shared node) and ``order`` (``a``'s fill
    after ``b``'s where they meet: one band, or different bands that only meet). With ``band_col`` the caller's bands decide over and under
    everywhere: roads of different bands are a stack pair even where they only meet (a zebra crossing set over its street stays over it)."""
    import geopandas as gpd
    import pandas as pd
    g = edges
    ends, first, rid, same = _road_split(g)
    ids = [str(v) for v in g[id_col]] if id_col and id_col in g.columns else [str(i) for i in range(len(g))]
    head = g.iloc[first]
    if band_col:
        beta = pd.to_numeric(head[band_col], errors="coerce").fillna(0).round().astype(int).tolist()
    else:
        beta = [_level(r, layer_col, bridge_col, tunnel_col) for r in head.to_dict("records")]
    omega = None
    if order in ("class", "priority"):                         # a road with no class takes no part in the order: no wish for it (None)
        z = {h: _class_order(h) for h in head[highway_col].dropna().unique()}
        omega = [None if pd.isna(h) else z[h] for h in head[highway_col]]
        if order == "priority":
            omega = [None if w is None else w + _TIER * _tier(r, junction_col, bridge_col, tunnel_col)
                     for w, r in zip(omega, head.to_dict("records"), strict=True)]
    elif order:
        omega = [None if pd.isna(v) else float(v) for v in pd.to_numeric(head[order], errors="coerce")]
    re_ = [ends[i] for i in first]
    meets, stacks, orders = _relations(list(_metres(head.geometry)), re_, beta, omega, band_dist, mouths=not band_col)
    name = [ids[i] for i in first]
    mine = [[] for _ in first], [[] for _ in first]
    for i, r in enumerate(rid):
        mine[0 if same[i] else 1][r].append(ids[i])
    shown = {c: list(head[c]) for c in dict.fromkeys((highway_col, "name", "edge_ref", "lanes", tunnel_col, bridge_col, layer_col))     # to read and draw the
             if c in g.columns}                                                                                                     # roads (the editor): look and all
    roads = gpd.GeoDataFrame({"road": name, "edges": mine[0], "reversed": mine[1], "band": beta,
                              "priority": omega if omega is not None else [None] * len(first), **shown}, geometry=list(head.geometry), crs=g.crs)
    rows = ([("meet", name[x], name[y], ex, ey) for x, ex, y, ey in meets] + [("stack", name[u], name[l], None, None) for u, l in stacks]
            + [("order", name[x], name[y], None, None) for x, y in orders])
    return roads, pd.DataFrame(rows, columns=["relation", "a", "b", "a_end", "b_end"])


def _read_pairs(pairs):
    """The rows of a pairs / edits table (or CSV) as dicts, an empty a / b / a_end / b_end as None."""
    import pandas as pd
    t = pd.read_csv(pairs, dtype=str, keep_default_na=False) if isinstance(pairs, (str, bytes)) or hasattr(pairs, "__fspath__") else pairs
    out = t.to_dict("records")
    for row in out:
        for c in ("a", "b", "a_end", "b_end"):
            v = row.get(c)
            row[c] = None if v is None or (isinstance(v, float) and v != v) or v == "" else str(v)
    return out


def auto_ends(roads, pairs, zoom=18.0, highway_col="highway", min_m=0.5, step=0.25, cover=0.99, levels=None):
    """Each road end's head length and cap from the geometry and the widths the page draws at ``zoom`` (Kaveh 2026-10-06: better than one
    number and one cap for all). Returns a table ``road``, ``start_m``, ``end_m``, ``cap_start``, ``cap_end`` (in the road's own way):

    * a head reaches as far as the road's drawing still overlaps a road joined at that end: from the node along the road until its line is
      ``(own width + the other's) / 2`` from every joined road (a right angle: about half the other's width; a narrow merge: much more); a
      dead end has ``min_m``; start + end never more than the road (cut in their ratio);
    * a cap is ``"round"`` where the round end of its fill lies inside the fills of the roads joined there that are drawn at its level or
      above (at least ``cover`` of its half disc), else ``"flat"``: a round end on top of a lower road shows as a bump on it (a road going
      on into a lower piece, Kaveh 2026-10-06), and one reaching out of the joined roads crosses their outlines (a wide road ending on a
      narrower one); a square end covers the round one and more, so it never helps. ``levels``: the solved roads (``road``,
      ``fill_level``, :func:`solve_levels`); the caps need them, so they are made after solving (without: every joined road counts).

    ``pairs``: :func:`level_input`'s (its ``meet`` rows say which roads join at which end). The widths are in pixels, so the metres hold for
    ``zoom`` (street level by default); at lower zooms the roads are wider on the ground."""
    import math

    import numpy as np
    import pandas as pd
    import shapely
    from shapely.ops import unary_union

    from .render_web import class_width_px
    geo = list(_metres(roads.geometry))
    ids = list(roads["road"])
    idx = {r: i for i, r in enumerate(ids)}
    lat = float(roads.to_crs(4326).geometry.union_all().centroid.y) if roads.crs is not None else 0.0
    mpp = 40075016.686 * math.cos(math.radians(lat)) / (512 * 2 ** zoom)       # metres per pixel at that zoom, here
    cls = roads[highway_col] if highway_col in roads else [None] * len(ids)
    w = [class_width_px(None if c is None or c != c else str(c), zoom) * mpp for c in cls]                     # whole width, casing included
    wf = [class_width_px(None if c is None or c != c else str(c), zoom, casing=False) * mpp for c in cls]      # the fill
    fill = None
    if levels is not None:
        f = dict(zip(levels["road"], levels["fill_level"], strict=True))
        fill = [f[r] for r in ids]
    joins = {}
    for row in _read_pairs(pairs):
        if row["relation"] == "meet" and row["a"] in idx and row["b"] in idx:
            a, b = idx[row["a"]], idx[row["b"]]
            joins.setdefault((a, row["a_end"]), set()).add(b)
            joins.setdefault((b, row["b_end"]), set()).add(a)
    rows = []
    for i, g in enumerate(geo):
        n, out = g.length, []
        for end in ("start", "end"):
            J = sorted(joins.get((i, end), ()))
            if not J or n == 0:
                out.append((min_m, "round"))
                continue
            line = g if end == "start" else shapely.LineString(list(g.coords)[::-1])
            d = 0.0
            for d in np.arange(0.0, n + step, step):           # walk from the node until the drawings part
                p = line.interpolate(min(d, n))
                if all(p.distance(geo[j]) >= (w[i] + w[j]) / 2 for j in J):
                    break
            head = max(min_m, math.ceil(min(d, n) / 0.5) * 0.5)
            node = shapely.Point(line.coords[0])
            beyond = node.buffer(wf[i] / 2).difference(line.buffer(wf[i] / 2, cap_style="flat"))   # the round end of the fill past the node
            over = [j for j in J if fill is None or fill[j] >= fill[i]]                             # the joined roads drawn at its level or above
            joined = unary_union([geo[j].buffer(wf[j] / 2) for j in over]) if over else shapely.Point()
            out_area = beyond.difference(joined).area
            out.append((head, "flat" if beyond.area > 0 and out_area > (1 - cover) * beyond.area else "round"))
        (hs, cs), (he, ce) = out
        if hs + he > n > 0:
            hs, he = n * hs / (hs + he), n * he / (hs + he)
        rows.append((ids[i], round(hs, 2), round(he, 2), cs, ce))
    return pd.DataFrame(rows, columns=["road", "start_m", "end_m", "cap_start", "cap_end"])


def casing_parts(roads, head_m=5.0, heads=None):
    """Each road's three casing parts as drawn, in metres: ``{road: (start head, main part or None, end head)}``; the heads ``head_m`` long
    or ``heads``' own (a table or CSV: ``road`` (any edge id of it), ``start_m``, ``end_m``; empty = ``head_m``), a road shorter than its two
    heads cut in their ratio with no main part. For :func:`solve_levels`' ``parts``: which main parts are empty, and which parts of an upper
    road cross the road under it (the others only come near). The solver itself takes no length."""
    import pandas as pd
    from shapely.ops import substring
    hl = {r: [head_m, head_m] for r in roads["road"]}
    if heads is not None:
        of, back = {}, set()
        for r in roads.itertuples():
            for e in [r.road, *list(r.edges), *list(r.reversed)]:
                of[str(e)] = r.road
            back |= {str(e) for e in r.reversed}
        t = pd.read_csv(heads, dtype=str, keep_default_na=False) if isinstance(heads, (str, bytes)) or hasattr(heads, "__fspath__") else heads
        for row in t.to_dict("records"):
            e = str(row["road"])
            if e not in of:
                raise ValueError(f"heads: {e!r} is not an edge of the roads")
            v = [str(row.get(c, "") or "").strip() for c in ("start_m", "end_m")]
            if any(x and not float(x) > 0 for x in v):
                raise ValueError(f"heads: the head lengths of {e} must be positive numbers of metres, not {v}")
            v = [float(x) if x else head_m for x in v]
            hl[of[e]] = v[::-1] if e in back else v              # named by the edge that runs the other way: its start is the road's end
    out = {}
    for r, g in zip(roads["road"], _metres(roads.geometry), strict=True):
        n, (h0, h1) = g.length, hl[r]
        if h0 + h1 >= n:
            h0, h1 = n * h0 / (h0 + h1), n * h1 / (h0 + h1)
        out[r] = (substring(g, 0, h0), substring(g, h0, n - h1) if n - h1 > h0 else None, substring(g, n - h1, n))
    return out


def _crosses(part, upper, lower, tol=0.5):
    """Whether this part of the upper road crosses the lower road: they meet at a point that is not an end of either road (a join is not a crossing)."""
    import shapely
    x = part.intersection(lower)
    if x.is_empty:
        return False
    ends = shapely.MultiPoint([upper.coords[0], upper.coords[-1], lower.coords[0], lower.coords[-1]]).buffer(tol)
    return not x.difference(ends).is_empty


def solve_levels(roads, pairs, edits=None, max_level=20, margin=1.0, time_limit=60.0, min_positions=True, max_positions=None, parts=None):
    """Solve the drawing levels of ``roads`` from their ``pairs`` (both from :func:`level_input`, or read back from ``roads.parquet`` /
    ``pairs.csv``) and the caller's ``edits`` (a table or a CSV with the columns of ``pairs`` and ``enabled``: a row with ``enabled`` false
    switches off the same relation of ``pairs``, any other row is added; ``a`` / ``b`` may name any edge of a road, and a ``meet`` naming the
    edge that runs the other way has its end (start / end) turned to the road's way; a ``meet`` is the same in either order). A ``stack`` edit may name
    a part of A in ``a_end``: ``start`` / ``main`` / ``end`` (empty: the whole road, the rule with its junction exceptions). Added, that part is after
    B's fill even at a junction; switched off, only that part of the found pair is left out. Returns ``roads`` with
    ``casing_start``, ``casing_level``, ``casing_end`` and ``fill_level`` (in the road's own direction); ``attrs["levels_given_up"]`` (the
    stack pairs that could not be kept, as road ids) and ``attrs["levels_info"]``. Every road has three casing parts whatever its length: the head lengths are the drawing's (``render_edges(head_m=...)``);
    ``parts`` (:func:`casing_parts`: the parts as drawn) tells it the roads whose main part has no length (never lifted) and, for each stack
    pair, which parts of the upper road cross the lower one: a part that only comes near is a last-priority rule, and when it breaks a
    warning (``attrs["levels_near"]``), not a given-up pair. Without ``parts`` every main part counts and every rule is a crossing."""
    of, back = {}, set()                                       # any edge id -> its road's row; the ids of the edges that run against their road
    for i, r in enumerate(roads.itertuples()):
        for e in [r.road, *list(r.edges), *list(r.reversed)]:
            of[str(e)] = i
        back |= {str(e) for e in r.reversed}
    def key(row):
        if row["relation"] == "meet":                          # no direction: the same pair whichever road is named first
            return ("meet", *sorted([(row["a"], row["a_end"]), (row["b"], row["b_end"])]))
        if row["relation"] == "stack":                         # a part of A, or the whole road ("")
            return ("stack", row["a"], row["b"], row["a_end"] or "")
        return (row["relation"], row["a"], row["b"])
    off = set()                                                # (A, B, part): switched off in a found whole pair
    rel = {key(row): row for row in _read_pairs(pairs)}
    if edits is not None:
        for row in _read_pairs(edits):
            if row["relation"] == "stack" and (row["a_end"] or "") not in ("", "start", "main", "end"):
                raise ValueError(f"edits: a stack's part (a_end) is start, main, end or empty, not {row['a_end']!r}")
            for c in ("a", "b"):
                if row[c] not in of:
                    raise ValueError(f"edits: {row[c]!r} is not an edge of the roads")
                if (row["relation"] == "meet" or (row["relation"] == "stack" and c == "a")) and row[c] in back:     # that edge's start is its road's end
                    row[c + "_end"] = {"start": "end", "end": "start"}.get(row[c + "_end"], row[c + "_end"])
                row[c] = roads["road"].iat[of[row[c]]]
            if str(row.get("enabled", "")).strip().lower() in ("false", "0", "no"):
                k = key(row)
                if rel.pop(k, None) is None:
                    if k[0] == "stack" and k[3] and ("stack", k[1], k[2], "") in rel:        # one part of a found whole pair
                        off.add((k[1], k[2], k[3]))
                    else:
                        raise ValueError(f"edits: no {row['relation']} pair {row['a']} {row['b']} {k[3] if k[0] == 'stack' else ''} to switch off".rstrip())
            else:
                rel[key(row)] = row
    idx = {r: i for i, r in enumerate(roads["road"])}
    meets = [(idx[r["a"]], r["a_end"], idx[r["b"]], r["b_end"]) for r in rel.values() if r["relation"] == "meet"]
    stacks = [(idx[r["a"]], idx[r["b"]]) for r in rel.values() if r["relation"] == "stack" and not r["a_end"]]
    short = {"start": "s", "main": "m", "end": "e"}
    forced = [(idx[r["a"]], idx[r["b"]], short[r["a_end"]]) for r in rel.values() if r["relation"] == "stack" and r["a_end"]]
    off = [(idx[a], idx[b], short[h]) for a, b, h in off]
    orders = [(idx[r["a"]], idx[r["b"]]) for r in rel.values() if r["relation"] == "order"]
    empty, near = [], []
    if parts is not None:
        geo = list(_metres(roads.geometry))
        ids = list(roads["road"])
        empty = [i for i, r in enumerate(ids) if parts[r][1] is None]
        near = [(u, l, h) for u, l in stacks for h, p in zip("sme", parts[ids[u]], strict=True)
                if p is not None and not _crosses(p, geo[u], geo[l])]
    iv, given, info = _solve_intervals(list(_metres(roads.geometry)), meets, stacks, orders, time_limit, max_level, margin, min_positions,
                                       max_positions, forced, off, empty, near)
    counts = defaultdict(int)                                  # the solution can sit at any height: the main casing number most edges have becomes 0 (the ground)
    for r, row in enumerate(roads.itertuples()):
        counts[iv[r][1]] += len(row.edges) + len(row.reversed)
    ground = max(counts, key=lambda v: (counts[v], -v))
    iv = [tuple(x - ground for x in p) for p in iv]
    cm = _compress([v for p in iv for v in p])
    out = roads.copy()
    out["casing_start"], out["casing_level"], out["casing_end"], out["fill_level"] = ([cm[p[k]] for p in iv] for k in range(4))
    out.attrs["levels_given_up"] = [(roads["road"].iat[u], roads["road"].iat[l]) for u, l in given]
    out.attrs["levels_given_up_parts"] = [(roads["road"].iat[u], roads["road"].iat[l], h) for u, l, h in info.pop("given_up_parts", [])]
    out.attrs["levels_near"] = [(roads["road"].iat[u], roads["road"].iat[l], h) for u, l, h in info.pop("near_parts", [])]
    out.attrs["levels_info"] = info
    return out


def compute_levels(edges, layer_col="layer", bridge_col="bridge", tunnel_col="tunnel",
                   method="solve", band_col=None, order="priority", highway_col="highway", junction_col="junction", band_dist=10.0, head_m=5.0, max_level=20, margin=1.0, time_limit=60.0, min_positions=True):
    """A copy of ``edges`` with the drawing-order columns ``casing_start``, ``casing_level`` (the main part), ``casing_end`` and ``fill_level``;
    ``render_edges(casing_level_col=..., fill_level_col=...)`` draws by the last two (the heads are not drawn yet).

    ``method="solve"`` (default): the optimization of docs/design/levels_split_casing.md, section 7 (a minimum-cost flow, OR-tools; HiGHS when a wish must be given up).
    ``method="tags"``: a rule on the ``layer`` / ``bridge`` / ``tunnel`` tags and the shared end nodes, O(edges); the three casing numbers are equal
    (section 10).
    * the **band** of a road is the column ``band_col`` (integers) if given, else its level from the tags (``layer``, else bridge 1, tunnel -1, else 0);
      two roads within ``band_dist`` metres with different bands are a stack pair (the higher band is over the lower one), a crossing included;
    * every road's casing is divided into a start head, a main part and an end head; the heads merge with the roads that meet there, the main
      part is stacked. ``head_m`` (the heads' length in the drawing) tells the solver which main parts are empty and which parts cross (:func:`casing_parts`) and is stored with the numbers (``attrs["levels_params"]``) as the head length to draw them with;
    * ``order`` (a column of numbers, ``"class"`` for the renderer's class order, or ``"priority"``: roundabouts (``junction_col`` is ``roundabout`` or
      ``circular``), then tunnels, then bridges, then the class order): where roads of one band meet, the one with the higher number has the later fill
      where the other constraints allow; this is a wish, not a requirement. A road with no class takes no part in ``"class"`` or ``"priority"``.
    ``max_level``: the numbers are in ``[-max_level, max_level]``; ``margin``: how much later a road is painted where one must be painted after another
    (only the order matters: it changes the scale); ``time_limit``: seconds for each LP solve; ``min_positions``: also minimise the span of the numbers (fewer positions, a little
    less compaction; section 7.3.1); False leaves it out.
    Results beyond the columns: ``result.attrs["levels_given_up"]`` = ``[(upper index, lower index)]`` (also warned about;
    ``attrs["levels_given_up_parts"]``: ``(upper, lower, "start" / "main" / "end")``, the parts that broke),
    ``result.attrs["levels_info"]`` = counts, order violations, solver status, seconds.
    ponytail: tags method ignores crossings without tags and band / order; solve method does not cut a road at the place where it changes level."""
    if method not in ("tags", "solve"):
        raise ValueError(f"compute_levels: method must be 'tags' or 'solve', not {method!r}")
    if method == "tags" and (band_col or order not in (None, "priority")):           # the default order is no request: tags has none
        raise ValueError("compute_levels: band_col and order are part of the optimization problem; use method='solve'")
    if method == "solve" and not (margin > 0 and max_level > 0):
        raise ValueError(f"compute_levels: margin and max_level must be greater than 0, not {margin!r} and {max_level!r}")
    g = edges.copy()
    ends, _, rid, same = _road_split(g)
    if method == "tags":
        lv = [_level(r, layer_col, bridge_col, tunnel_col) for r in g.to_dict("records")]
        pos = [(c, c, c, f) for c, f in _tag_intervals(ends, lv)]
    else:
        roads, pairs = level_input(g, id_col=None, layer_col=layer_col, bridge_col=bridge_col, tunnel_col=tunnel_col, band_col=band_col,
                                   order=order, highway_col=highway_col, junction_col=junction_col, band_dist=band_dist)
        out = solve_levels(roads, pairs, parts=casing_parts(roads, head_m), max_level=max_level, margin=margin, time_limit=time_limit, min_positions=min_positions)
        lv = out[["casing_start", "casing_level", "casing_end", "fill_level"]].to_numpy().tolist()
        pos = [tuple(lv[r]) if same[i] else (lv[r][2], lv[r][1], lv[r][0], lv[r][3]) for i, r in enumerate(rid)]   # the other direction: heads swapped
        given = out.attrs["levels_given_up"]
        g.attrs["levels_given_up"] = [(int(u), int(l)) for u, l in given]
        g.attrs["levels_given_up_parts"] = [(int(u), int(l), h) for u, l, h in out.attrs["levels_given_up_parts"]]
        g.attrs["levels_near"] = [(int(u), int(l), h) for u, l, h in out.attrs["levels_near"]]
        g.attrs["levels_info"] = out.attrs["levels_info"]
        if given:
            warnings.warn(f"compute_levels: {len(given)} stack pair(s) could not be satisfied; see result.attrs['levels_given_up']", stacklevel=2)
    g["casing_start"], g["casing_level"], g["casing_end"], g["fill_level"] = ([p[i] for p in pos] for i in (0, 1, 2, 3))
    from .levels_store import levels_params
    g.attrs["levels_params"] = levels_params(method, head_m, band_dist, margin, max_level, band_col, order, min_positions and method == "solve")       # what the numbers were computed with (save_levels stores it)
    return g

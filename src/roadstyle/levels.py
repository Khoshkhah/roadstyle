"""The drawing order of each edge, from the data alone (docs/design/levels_split_casing.md): ``casing_level_col`` / ``fill_level_col``."""
from __future__ import annotations

import re
import warnings
from collections import defaultdict

from ._na import missing


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
    """order="priority": roundabout 3, tunnel 2, bridge 1, any other road 0 (2026-10-06)."""
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
    by ``omega`` for roads that meet, of one band or of different bands that only meet (2026-10-06: at a tunnel mouth the priority decides,
    where roads cross the band does). ``mouths`` False: roads of different bands are always a stack pair, as when the caller gives the bands
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
        for x, y in sorted(shared):
            if omega[x] is None or omega[y] is None or omega[x] == omega[y]:
                continue
            if beta[x] == beta[y] or (x, y) in only_meet:
                orders.append((x, y) if omega[x] > omega[y] else (y, x))
    return meets, stacks, orders


def _difference_rules(n, meets, lifts, orders, margin):
    """The rules of the solver as ``(i, j, w, rule)``: ``x_i - x_j <= w`` on the columns of :func:`_solve_intervals` (``b_r`` = r; the casing
    parts of road r = n + 3 r + 0 / 1 / 2 for start / main / end). ``rule``: None for H1 (each casing part under its road's fill), else
    ``("meet" / "stack" / "order", k)``, k the index into ``meets`` / ``lifts`` / ``orders``. H2: the heads of two roads that meet are each under
    the other's fill; H3: the part ``(u, l, h)`` after l's fill by ``margin``; H4: ``(x, y)``, x's fill after y's by ``margin``."""
    col = lambda r, h: n + 3 * r + "sme".index(h)             # noqa: E731
    out = [(col(r, h), r, 0.0, None) for r in range(n) for h in "sme"]
    for k, (x, ex, y, ey) in enumerate(meets):
        out += [(col(x, ex[0]), y, 0.0, ("meet", k)), (col(y, ey[0]), x, 0.0, ("meet", k))]
    out += [(l, col(u, h), -margin, ("stack", k)) for k, (u, l, h) in enumerate(lifts)]
    out += [(y, x, -margin, ("order", k)) for k, (x, y) in enumerate(orders)]
    return out


def _solve_intervals(metres, meets, stacks, orders, limit, max_level, margin, min_positions=True, max_positions=None, near=(), fix=None):
    """The solver on roads (one per segment, both directions together) and their relations (a pairs table). Every road has one fill number
    ``b`` and a casing of three parts: a start head, a main part and an end head, whatever its length; the solver takes no length and no
    geometry (2026-10-08: it works from the tables only, so a head change never needs a solve). ``stacks``: ``(upper, lower, "s" / "m" / "e")``,
    that part of the upper road's casing after the lower road's fill; ``near``: the same for parts that only come near the lower road (pairs.csv's
    ``near`` rows, written by make with ``near_rules``): kept last, after the order wishes, a broken one a warning. ``fix``: ``{road: (a_start,
    a_main, a_end, b)}``, numbers held as they are (bounds; the editor's local re-solve), the others solved with the same rules.
    Returns ``(parts, given_up, info)``: ``parts[r] = (a_start, a_main, a_end, b)``. The model is a linear program solved on a sparse matrix with
    HiGHS (docs/design/levels_split_casing.md, section 7)."""
    import time
    from types import SimpleNamespace

    import numpy as np
    import scipy.sparse as sp
    t0, n = time.time(), len(metres)
    zero = [(0, 0, 0, 0)] * n
    stacks = set(stacks)
    lifts = sorted(stacks | set(near), key=lambda t: (t[0], t[1], "mse".index(t[2])))     # a part named twice is one rule; a stack outranks a near
    pair_list = sorted({(u, l) for u, l, _ in lifts})
    info = {"pairs": len(pair_list), "roads": n, "meets": len(meets)}
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
    rules = _difference_rules(n, meets, lifts, O, margin)     # every rule x_i - x_j <= w (the editor's check reads the same ones)
    for i, j, w, t in rules:
        if t is None or t[0] == "meet":                        # H1, H2: hard
            le([(i, 1.0), (j, -1.0)], w)
    if min_positions or max_positions:                         # section 7.3.1: H above and L below every number; the span H - L is in the cost
        H, Lo, first_nv = ncol, ncol + 1, ncol
        for v in range(first_nv):
            le([(v, 1.0), (H, -1.0)], 0.0)                     # x_v <= H
            le([(Lo, 1.0), (v, -1.0)], 0.0)                    # L <= x_v
        ncol += 2
        if max_positions:                                      # at most max_positions numbers: H - L <= (max_positions - 1) steps (a hard bound;
            le([(H, 1.0), (Lo, -1.0)], (max_positions - 1) * margin)   # the stack pairs and the order wishes give way to it)
    base = len(rhs)
    # H3, A over B: each named part of A's casing (start head, main part, end head), and so its fill (H1), after B's fill: b_B + margin <= a_(A, part)
    k_of = {p: k for k, p in enumerate(pair_list)}
    stack_rows = [(k_of[(u, l)], part[u][h]) for u, l, h in lifts]      # (pair index, the casing column it lifts)
    row_near = [t not in stacks for t in lifts]                         # whether that rule is only "near"
    for i, j, w, t in rules:
        if t is not None and t[0] != "meet":                   # H3 (stack rows, in the order of stack_rows), H4: given up in the stages
            le([(i, 1.0), (j, -1.0)], w)
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
    within = [box] * ncol                                      # the bounds of every column: a fixed road's four held at its numbers
    for r, v in (fix or {}).items():
        for c, x in zip((part[r]["s"], part[r]["m"], part[r]["e"], r), v, strict=True):
            within[c] = (x, x)
    solves, staged = 1, False
    x0 = None if fix else _difference_lp(cost, A0, b_ub, box[1])   # stage 0: nothing violated; a min-cost flow (it knows no bounds but the box)
    if x0 is not None:
        res, how = SimpleNamespace(status=0, x=x0), "flow"
    else:
        res, how = solve(cost, A0, b_ub, within), "highs"       # the flow cannot certify (or some numbers are held): the LP with HiGHS
    slack = np.zeros(nP + nO)
    if res.status == 2:                                        # infeasible: some stack rules / wishes must be broken: stages with slacks
        S = sp.csr_matrix((-np.ones(nP + nO), (np.arange(base, nrow), np.arange(nP + nO))), shape=(nrow, nP + nO))
        A1 = sp.hstack([A0, S], format="csr")
        bounds = within + [(0, None)] * (nP + nO)
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
    status = "OPTIMAL"
    if res.status == 1 and res.x is not None:                  # the last stage (cost, fewest positions) at its time limit: what is over what is
        status = "TIME_LIMIT"                                  # fixed by the stages before; keep its best numbers and say so (2026-10-07)
        warnings.warn(f"compute_levels: the last stage (cost, fewest positions) reached its time limit ({limit} s); its best numbers are kept: "
                      "every rule of the stages before holds, the drawing may have a few more positions", stacklevel=2)
    elif res.status != 0:
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
    info["orders_not_kept"] = [O[i] for i in range(nO) if slack[nP + i] >= margin * (1 - 1e-6)]    # (higher, lower): the wishes given way
    name = {c: (r, h) for r in range(n) for h, c in part[r].items()}
    word = {"s": "start", "m": "main", "e": "end"}
    info["given_up_parts"] = sorted({(*pair_list[stack_rows[i][0]], word[name[stack_rows[i][1]][1]]) for i in broke if not row_near[i]})
    info["near_parts"] = sorted({(*pair_list[stack_rows[i][0]], word[name[stack_rows[i][1]][1]]) for i in broke if row_near[i]})
    info["near_warnings"] = len({(u, l) for u, l, _ in info["near_parts"]})              # pairs, as given_up counts them
    return parts, gu, {**info, "order_pairs": nO, "order_violations": violated, "solves": solves, "solver": how, "status": status, "seconds": round(time.time() - t0, 1)}


def _road_split(g, cols=()):
    """Both directions of a segment are one road: ``(ends, first, rid, same)``: the end nodes of every row (exact equality of the end points),
    the first row of every road, the road of every row, and whether a row runs the same way as its road's first row. Rows on the same line
    are one road only if they also agree on ``cols`` (the kind of road): a footway lying exactly on a tunnel's piece is a road of its own
    (2026-10-07: joined, the tunnel piece took the footway's tags and was solved and drawn as a footway)."""
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
    have = [c for c in cols if c and c in g.columns]
    kind = list(zip(*[["" if missing(v) else str(v) for v in g[c]] for c in have], strict=True)) if have else [()] * len(geoms)
    keys = [(frozenset(e), min(f, r), k) for e, f, r, k in zip(ends, fwd, rev, kind, strict=True)]
    road, first = {}, []
    for i, k in enumerate(keys):
        if k not in road:
            road[k] = len(first)
            first.append(i)
    rid = [road[k] for k in keys]
    same = [fwd[i] == fwd[first[rid[i]]] for i in range(len(geoms))]
    return ends, first, rid, same


def _metres(geoseries):
    return geoseries.to_crs(geoseries.estimate_utm_crs()) if geoseries.crs is not None and geoseries.crs.is_geographic else geoseries


def level_input(edges, id_col="edge_id", layer_col="layer", bridge_col="bridge", tunnel_col="tunnel", band_col=None, order="priority",
                highway_col="highway", junction_col="junction", band_dist=10.0, head_m=5.0, heads=None, near_rules=False):
    """The solver's input (docs/design/level_input.md), from any edges roadstyle draws: ``(roads, pairs)``.

    ``roads``: one row per road (both directions of a segment together): ``road`` (the ``id_col`` of its first edge, as text; the row number
    without ``id_col``), ``edges`` / ``reversed`` (the ids of its edges in its own direction / the other way), ``band`` (``band_col``, else the
    level from the tags), ``priority`` (the ``order``: ``"priority"``, ``"class"``, a column of numbers, or None) and the geometry of its first
    edge, and its ``highway_col``, ``name``, ``edge_ref`` (and ``edge_refs`` / ``reversed_refs``, and ``edges_oneway`` / ``reversed_oneway`` and ``edges_driving`` / ``reversed_driving`` and ``edges_directed`` / ``reversed_directed`` (:func:`roadstyle.is_directed`, from the edges' ``driving``, ``cycling`` and ``highway_col``): each edge's own, null where the edges have no such column, as ``edges`` / ``reversed``), ``lanes``, ``modes`` (who may use it, e.g. duckOSM's travel modes), ``tunnel_col``, ``bridge_col`` and ``layer_col`` when the edges have them. ``pairs``: one row per relation, ``relation`` / ``a`` / ``b`` / ``a_end`` / ``b_end``: ``meet`` (the end ``a_end`` of ``a`` is the end
    ``b_end`` of ``b``), ``stack`` (``a`` is over ``b``: different bands, crossing or near away from a shared node) and ``order`` (``a``'s fill
    after ``b``'s where they meet: one band, or different bands that only meet). A stack is one row per part of ``a``'s casing that must be
    after ``b``'s fill, its ``a_end`` ``start`` / ``main`` / ``end`` (2026-10-08): the parts that cross ``b``, worked out here once with the heads
    ``head_m`` long, or ``heads``' own (a table or CSV ``road``, ``start_m``, ``end_m``, as heads.csv; :func:`casing_parts`), leaving out a head
    at a junction with ``b`` and an empty main part (:func:`_stack_parts`); the solver takes no geometry. ``near_rules``: also a ``near`` row for each
    part that only comes near ``b`` (the solver's last priority, a warning when broken). With ``band_col`` the caller's bands decide over and under
    everywhere: roads of different bands are a stack pair even where they only meet (a zebra crossing set over its street stays over it)."""
    import geopandas as gpd
    import pandas as pd
    g = edges
    if {"driving", "cycling"} <= set(g.columns):        # directed: what draws two directions or one line, the one rule (edges.is_directed)
        from .edges import is_directed
        g = g.assign(directed=is_directed(g, highway_col=highway_col))
    ends, first, rid, same = _road_split(g, (highway_col, tunnel_col, bridge_col, layer_col, band_col))
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
            if junction_col not in g.columns:                  # no silent fallback: say that no roundabout can be put on top
                warnings.warn(f"the edges have no {junction_col!r} column: no road is known as a roundabout, so none is put on top where roads meet "
                              f"(add the OSM junction tag as {junction_col!r}, or pass junction_col=...)", stacklevel=2)
            omega = [None if w is None else w + _TIER * _tier(r, junction_col, bridge_col, tunnel_col)
                     for w, r in zip(omega, head.to_dict("records"), strict=True)]
    elif order:
        omega = [None if pd.isna(v) else float(v) for v in pd.to_numeric(head[order], errors="coerce")]
    re_ = [ends[i] for i in first]
    metres = list(_metres(head.geometry))
    meets, stacks, orders = _relations(metres, re_, beta, omega, band_dist, mouths=not band_col)
    name = [ids[i] for i in first]
    mine = [[] for _ in first], [[] for _ in first]
    for i, r in enumerate(rid):
        mine[0 if same[i] else 1][r].append(ids[i])
    shown = {c: list(head[c]) for c in dict.fromkeys((highway_col, "name", "edge_ref", "lanes", "modes", tunnel_col, bridge_col, layer_col))     # to read and draw the
             if c in g.columns}                                                                                                     # roads (the editor): look and all
    if "modes" in shown:                                # the modes of all the road's edges: a one-way street's reverse is often walking only
        both = [[] for _ in first]
        for i, r in enumerate(rid):
            v = g["modes"].iloc[i]
            both[r] += [] if missing(v) else [t for t in str(v).split(" + ") if t not in both[r]]
        shown["modes"] = [" + ".join(m) or None for m in both]
    if "bus_lines" in g.columns:                        # the bus lines on any of the road's edges (duckOSM's bus.route_edges), e.g. "3, 607, X1"
        lines = [[] for _ in first]
        for i, r in enumerate(rid):
            v = g["bus_lines"].iloc[i]
            lines[r] += [] if missing(v) else [t.strip() for t in str(v).split(",") if t.strip() and t.strip() not in lines[r]]
        key = lambda t: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", t)]                     # noqa: E731  natural order
        shown["bus_lines"] = [", ".join(sorted(m, key=key)) or None for m in lines]
    if "edge_ref" in g.columns:                         # each edge's own edge_ref, as edges / reversed (the editor shows both directions)
        refs = ([[] for _ in first], [[] for _ in first])
        for i, r in enumerate(rid):
            v = g["edge_ref"].iloc[i]
            refs[0 if same[i] else 1][r].append(None if missing(v) else str(v))
        shown["edge_refs"], shown["reversed_refs"] = refs
    for c in ("oneway", "driving", "directed"):         # each edge's own oneway / driving (its arrow) and directed (two directions or one line), as edges / reversed
        per = ([[] for _ in first], [[] for _ in first])           # no such column: null on every edge, which the pages read as "not given"
        for i, r in enumerate(rid):
            v = g[c].iloc[i] if c in g.columns else None
            per[0 if same[i] else 1][r].append(None if missing(v) else bool(v))
        shown[f"edges_{c}"], shown[f"reversed_{c}"] = per
    roads = gpd.GeoDataFrame({"road": name, "edges": mine[0], "reversed": mine[1], "band": beta,
                              "priority": omega if omega is not None else [None] * len(first), **shown}, geometry=list(head.geometry), crs=g.crs)
    lift, near = _stack_parts(metres, name, meets, stacks, casing_parts(roads, head_m, heads))
    word = {"s": "start", "m": "main", "e": "end"}
    rows = ([("meet", name[x], name[y], ex, ey) for x, ex, y, ey in meets] + [("stack", name[u], name[l], word[h], None) for u, l, h in lift]
            + ([("near", name[u], name[l], word[h], None) for u, l, h in near] if near_rules else [])
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
            row[c] = None if missing(v) or v == "" else str(v)
    return out


def dead_end_cap(roads, pairs):
    """The automatic cap of an end that meets no other road (no ``meet`` row at it), as ``{(road index, "start" / "end"): cap}``: ``"square"`` on
    a two-way road (one casing around both directions: two half-width round fill ends left a notch at the tip), ``"round"`` on a one-way one."""
    idx = {r: i for i, r in enumerate(roads["road"])}
    met = set()
    for row in _read_pairs(pairs):
        if row["relation"] == "meet" and row["a"] in idx and row["b"] in idx:
            met |= {(idx[row["a"]], row["a_end"]), (idx[row["b"]], row["b_end"])}
    two = [len(e) > 0 and len(b) > 0 for e, b in zip(roads["edges"], roads["reversed"], strict=True)]
    return {(i, end): "square" if two[i] else "round" for i in range(len(idx)) for end in ("start", "end") if (i, end) not in met}


def auto_ends(roads, pairs, zoom=18.0, highway_col="highway", min_m=0.5, step=0.25, cover=0.99, levels=None):
    """Each road end's head length and cap from the geometry and the widths the page draws at ``zoom`` (2026-10-06: better than one
    number and one cap for all). Returns a table ``road``, ``start_m``, ``end_m``, ``cap_start``, ``cap_end`` (in the road's own way):

    * a head reaches as far as the road's drawing still overlaps a road joined at that end: from the node along the road until its line is
      ``(own width + the other's) / 2`` from every joined road (a right angle: about half the other's width; a narrow merge: much more); a
      dead end has ``min_m``; start + end never more than the road (cut in their ratio);
    * a dead end's cap is :func:`dead_end_cap`'s (square on a two-way road);
    * a cap is ``"round"`` where the round end of its fill lies inside the fills of the roads joined there that are drawn at its level or
      above (at least ``cover`` of its half disc), else ``"flat"``: a round end on top of a lower road shows as a bump on it (a road going
      on into a lower piece, 2026-10-06), and one reaching out of the joined roads crosses their outlines (a wide road ending on a
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
    w = [class_width_px(None if missing(c) else str(c), zoom) * mpp for c in cls]                     # whole width, casing included
    wf = [class_width_px(None if missing(c) else str(c), zoom, casing=False) * mpp for c in cls]      # the fill
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
    dead = dead_end_cap(roads, pairs)
    rows = []
    for i, g in enumerate(geo):
        n, out = g.length, []
        for end in ("start", "end"):
            J = sorted(joins.get((i, end), ()))
            if not J or n == 0:
                out.append((min_m, dead.get((i, end), "round")))
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
    heads cut in their ratio with no main part. For :func:`level_input` (make): which main parts are empty, and which parts of an upper
    road cross the road under it (the others only come near), decided once into the stack rows. The solver takes no length."""
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
        out[r] = (substring(g, 0, h0), substring(g, h0, n - h1) if n - h1 - h0 > 0.05 else None, substring(g, n - h1, n))   # under 5 cm: no main part
    return out


def _crosses(part, upper, lower, tol=0.5):
    """Whether this part of the upper road crosses the lower road: they meet at a point that is not an end of either road (a join is not a crossing)."""
    import shapely
    x = part.intersection(lower)
    if x.is_empty:
        return False
    ends = shapely.MultiPoint([upper.coords[0], upper.coords[-1], lower.coords[0], lower.coords[-1]]).buffer(tol)
    return not x.difference(ends).is_empty


def _stack_parts(metres, ids, meets, stacks, parts):
    """The parts of each stack pair's upper road that must be over the lower one, at make time: ``(lift, near)``, each ``(upper, lower,
    "s" / "m" / "e")`` (road indexes). ``parts``: :func:`casing_parts`. Left out: an empty main part (it is never drawn), and a head of A that
    joins B, or joins a road that joins B (the next piece of the tunnel A runs into at its mouth): a junction, where the head is under the fills
    it joins; without that, such a head and the head of a street over that next piece made a loop no order can keep. Two ramps, each over one
    tube of a tunnel and joining the other tube, still make one: the solver gives one of their pairs up and says so. Of the others, a part that
    crosses B is in ``lift``, a part that only comes near it in ``near``."""
    touching, at_head = defaultdict(set), defaultdict(set)     # road -> the roads it shares a node with; (road, "s" / "e") -> the roads that head joins
    for x, ex, y, ey in meets:
        touching[x].add(y)
        touching[y].add(x)
        at_head[(x, "s" if ex == "start" else "e")].add(y)
        at_head[(y, "s" if ey == "start" else "e")].add(x)
    lift, near = [], []
    for u, l in stacks:
        for h, p in zip("sme", parts[ids[u]], strict=True):
            if p is None or (h != "m" and (l in at_head[(u, h)] or at_head[(u, h)] & touching[l])):
                continue
            (lift if _crosses(p, metres[u], metres[l]) else near).append((u, l, h))
    return lift, near


def merged_relations(roads, pairs, edits=None):
    """The pairs with the edits on top: key -> row, an edit's row marked ``own``. The rows union (2026-10-08): an edit row adds its relation
    (a stack: one part of A), an edit with ``enabled`` false switches off that exact row (a stack: pair and part); nothing else overrides
    anything. A stack or near row with no part (a pairs.csv made before 2026-10-08, one row for the whole road) is an error: make it again."""
    of, back = {}, set()                                       # any edge id -> its road's row; the ids of the edges that run against their road
    for i, r in enumerate(roads.itertuples()):
        for e in [r.road, *list(r.edges), *list(r.reversed)]:
            of[str(e)] = i
        back |= {str(e) for e in r.reversed}
    def key(row):
        if row["relation"] == "meet":                          # no direction: the same pair whichever road is named first
            return ("meet", *sorted([(row["a"], row["a_end"]), (row["b"], row["b_end"])]))
        if row["relation"] in ("stack", "near"):               # one part of A
            return (row["relation"], row["a"], row["b"], row["a_end"])
        return (row["relation"], row["a"], row["b"])
    rows = _read_pairs(pairs)
    whole = [r for r in rows if r["relation"] in ("stack", "near") and r["a_end"] not in _PARTS]
    if whole:
        raise ValueError(f"pairs: {len(whole)} stack row(s) name no part of the upper road (first: {whole[0]['a']} over {whole[0]['b']}): a pairs.csv "
                         "made before 2026-10-08, with one row for the whole road. Make the area again (roadstyle-levels make, or duckosm levels): it "
                         "writes one row per part (a_end start / main / end); your edits.csv, heads.csv and caps.csv are kept")
    rel = {key(row): row for row in rows}
    if edits is not None:
        for row in _read_pairs(edits):
            if row["relation"] in ("stack", "near") and row["a_end"] not in _PARTS:
                raise ValueError(f"edits: a stack names one part of the upper road in a_end (start, main or end), not {row['a_end'] or 'none'!r} "
                                 f"({row['a']} over {row['b']}); since 2026-10-08 there is no whole-road stack: one row per part")
            for c in ("a", "b"):
                if row[c] not in of:
                    raise ValueError(f"edits: {row[c]!r} is not an edge of the roads")
                if (row["relation"] == "meet" or (row["relation"] in ("stack", "near") and c == "a")) and row[c] in back:   # that edge's start is its road's end
                    row[c + "_end"] = {"start": "end", "end": "start"}.get(row[c + "_end"], row[c + "_end"])
                row[c] = roads["road"].iat[of[row[c]]]
            if str(row.get("enabled", "")).strip().lower() in ("false", "0", "no"):
                k = key(row)
                if rel.pop(k, None) is None:
                    raise ValueError(f"edits: no {row['relation']} pair {row['a']} {row['b']} {k[3] if len(k) == 4 and k[0] != 'meet' else ''} to switch off".rstrip())
            else:
                rel[key(row)] = {**row, "own": True}
    return rel


_PARTS = ("start", "main", "end")


def _indexed(roads, rel):
    """The rows of ``rel`` (:func:`merged_relations`) on road indexes, as the solver takes them: ``{relation: [(rule, row)]}``; a rule is
    ``(x, x_end, y, y_end)`` (meet), ``(upper, lower, "s" / "m" / "e")`` (stack, near) or ``(higher, lower)`` (order)."""
    idx = {r: i for i, r in enumerate(roads["road"])}
    out = {"meet": [], "stack": [], "near": [], "order": []}
    for r in rel.values():
        if r["relation"] not in out:
            raise ValueError(f"pairs: the relation {r['relation']!r} is not meet, stack, near or order")
        a, b = idx[r["a"]], idx[r["b"]]
        out[r["relation"]].append(((a, r["a_end"], b, r["b_end"]) if r["relation"] == "meet" else (a, b, r["a_end"][0])
                                   if r["relation"] in ("stack", "near") else (a, b), r))
    return out


def rule_conflicts(roads, pairs, edits, rows, margin=1.0):
    """The level editor's check before rules are added (2026-10-08): ``[(row, "duplicate" / "loop", [rule rows])]`` for each of ``rows`` (rules
    as edits.csv rows) that conflicts with the enabled rules (``pairs`` with ``edits`` on top, and the ``rows`` before it). A duplicate: the same
    row is there. A loop: a cycle of the solver's rules (:func:`_difference_rules`) through the new one, each keeping a number at or above the
    next and at least one strictly above, back to the first: no numbers keep them all, so the solver gives one up. From the rules only, no
    geometry: a path in the graph of ``x_i - x_j <= w`` (an arc j -> i, every ``w`` 0 or -margin) from the new rule's i back to its j that
    has a strict arc if the new rule has none (a breadth-first search on (number, strict yet)). Rows with ``enabled`` false are not checked."""
    from collections import deque

    import pandas as pd
    none = pd.DataFrame(columns=["relation", "a", "b", "a_end", "b_end"])
    rel, n, out = merged_relations(roads, pairs, edits), len(roads), []
    for row in rows:
        if str(row.get("enabled", "")).strip().lower() in ("false", "0", "no"):
            continue
        ((k, new),) = merged_relations(roads, none, pd.DataFrame([row])).items()
        if k in rel:
            out.append((row, "duplicate", [rel[k]]))
            continue
        by, adj = _indexed(roads, rel), defaultdict(list)
        lists = {"meet": by["meet"], "stack": by["stack"] + by["near"], "order": by["order"]}
        for i, j, w, t in _difference_rules(n, *([r for r, _ in lists[x]] for x in ("meet", "stack", "order")), margin):
            adj[j].append((i, w < 0, None if t is None else lists[t[0]][t[1]][1]))
        ((rule, _),) = sum(_indexed(roads, {k: new}).values(), [])
        kind = new["relation"] if new["relation"] != "near" else "stack"
        mine = [x for x in _difference_rules(n, *([rule] if kind == x else [] for x in ("meet", "stack", "order")), margin) if x[3] is not None]
        for i, j, w, _ in mine:
            start = (i, w < 0)
            prev, q, end = {start: None}, deque([start]), None
            while q and end is None:
                v, f = s = q.popleft()
                for u, strict, src in adj[v]:
                    t = (u, f or strict)
                    if t not in prev:
                        prev[t] = (s, src)
                        if t == (j, True):
                            end = t
                            break
                        q.append(t)
            if end is not None:
                path = []
                while prev[end] is not None:
                    end, src = prev[end]
                    if src is not None and src not in path:
                        path.append(src)
                out.append((row, "loop", path[::-1]))
                break
        rel[k] = new
    return out


def solve_levels(roads, pairs, edits=None, max_level=20, margin=1.0, time_limit=60.0, min_positions=True, max_positions=None, fixed=None):
    """Solve the drawing levels of ``roads`` from their ``pairs`` (both from :func:`level_input`, or read back from ``roads.parquet`` /
    ``pairs.csv``) and the caller's ``edits`` (a table or a CSV with the columns of ``pairs`` and ``enabled``: a row with ``enabled`` false
    switches off the same row of ``pairs``, any other row is added; ``a`` / ``b`` may name any edge of a road, and a ``meet`` naming the
    edge that runs the other way has its end (start / end) turned to the road's way; a ``meet`` is the same in either order). A ``stack`` row names
    one part of A in ``a_end``: ``start`` / ``main`` / ``end``; that part is after B's fill (several rows of a pair: each part). The solver works
    from the tables only (2026-10-08): no geometry, no head lengths; which parts cross was decided when the pairs were made (:func:`level_input`).
    ``near`` rows (``level_input(near_rules=True)``) are last-priority rules; a broken one is a warning (``attrs["levels_near"]``), not a given-up
    pair. Returns ``roads`` with ``casing_start``, ``casing_level``, ``casing_end`` and ``fill_level`` (in the road's own direction);
    ``attrs["levels_given_up"]`` (the stack pairs that could not be kept, as road ids) and ``attrs["levels_info"]``.
    ``fixed``: ``{road: (casing_start, casing_level, casing_end, fill_level)}``, numbers of an earlier result held as they are; only the other
    roads are solved, with the same rules (the level editor's local re-solve, level_area.solve_local)."""
    by = _indexed(roads, merged_relations(roads, pairs, edits))
    meets, stacks, near, orders = ([t for t, _ in by[k]] for k in ("meet", "stack", "near", "order"))
    idx = {r: i for i, r in enumerate(roads["road"])}
    fix = None
    if fixed:                                                  # an earlier result's numbers (around its ground 0) into the box [0, 2 max_level]
        fix = {idx[r]: tuple((x + max_level) * margin for x in v) for r, v in fixed.items()}
        if any(not 0 <= x <= 2 * max_level * margin for v in fix.values() for x in v):
            raise ValueError(f"solve_levels: a fixed number is outside [-max_level, max_level] ({max_level})")
    iv, given, info = _solve_intervals(list(roads["road"]), meets, stacks, orders, time_limit, max_level, margin, min_positions,
                                       max_positions, near, fix)
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
    out.attrs["levels_orders_not_kept"] = [(roads["road"].iat[x], roads["road"].iat[y]) for x, y in info.pop("orders_not_kept", [])]
    out.attrs["levels_info"] = info
    return out


def compute_levels(edges, layer_col="layer", bridge_col="bridge", tunnel_col="tunnel",
                   method="solve", band_col=None, order="priority", highway_col="highway", junction_col="junction", band_dist=10.0, head_m=5.0, max_level=20, margin=1.0, time_limit=60.0, min_positions=True, near_rules=False):
    """A copy of ``edges`` with the drawing-order columns ``casing_start``, ``casing_level`` (the main part), ``casing_end`` and ``fill_level``;
    ``render_edges(casing_level_col=..., fill_level_col=...)`` draws by the last two (the heads are not drawn yet).

    ``method="solve"`` (default): the optimization of docs/design/levels_split_casing.md, section 7 (a minimum-cost flow, OR-tools; HiGHS when a wish must be given up).
    ``method="tags"``: a rule on the ``layer`` / ``bridge`` / ``tunnel`` tags and the shared end nodes, O(edges); the three casing numbers are equal
    (section 10).
    * the **band** of a road is the column ``band_col`` (integers) if given, else its level from the tags (``layer``, else bridge 1, tunnel -1, else 0);
      two roads within ``band_dist`` metres with different bands are a stack pair (the higher band is over the lower one), a crossing included;
    * every road's casing is divided into a start head, a main part and an end head; the heads merge with the roads that meet there, the main
      part is stacked. ``head_m`` (the heads' length in the drawing) decides once, before the solve, which parts of a stack's upper road cross the
      road under it (:func:`level_input`; an empty main part is never lifted) and is stored with the numbers (``attrs["levels_params"]``) as the head length to draw them with;
    * ``order`` (a column of numbers, ``"class"`` for the renderer's class order, or ``"priority"``: roundabouts (``junction_col`` is ``roundabout`` or
      ``circular``), then tunnels, then bridges, then the class order): where roads of one band meet, the one with the higher number has the later fill
      where the other constraints allow; this is a wish, not a requirement. A road with no class takes no part in ``"class"`` or ``"priority"``.
    ``max_level``: the numbers are in ``[-max_level, max_level]``; ``margin``: how much later a road is painted where one must be painted after another
    (only the order matters: it changes the scale); ``time_limit``: seconds for each LP solve; ``min_positions``: also minimise the span of the numbers (fewer positions, a little
    less compaction; section 7.3.1); False leaves it out. ``near_rules``: also lift the parts that only come near the road under them, as last-priority
    rules (a broken one is a warning in ``attrs["levels_near"]``); off by default (see :func:`solve_levels`).
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
    ends, _, rid, same = _road_split(g, (highway_col, tunnel_col, bridge_col, layer_col, band_col))
    if method == "tags":
        lv = [_level(r, layer_col, bridge_col, tunnel_col) for r in g.to_dict("records")]
        pos = [(c, c, c, f) for c, f in _tag_intervals(ends, lv)]
    else:
        roads, pairs = level_input(g, id_col=None, layer_col=layer_col, bridge_col=bridge_col, tunnel_col=tunnel_col, band_col=band_col,
                                   order=order, highway_col=highway_col, junction_col=junction_col, band_dist=band_dist, head_m=head_m, near_rules=near_rules)
        out = solve_levels(roads, pairs, max_level=max_level, margin=margin, time_limit=time_limit, min_positions=min_positions)
        lv = out[["casing_start", "casing_level", "casing_end", "fill_level"]].to_numpy().tolist()
        pos = [tuple(lv[r]) if same[i] else (lv[r][2], lv[r][1], lv[r][0], lv[r][3]) for i, r in enumerate(rid)]   # the other direction: heads swapped
        given = out.attrs["levels_given_up"]
        g.attrs["levels_given_up"] = [(int(u), int(l)) for u, l in given]
        g.attrs["levels_given_up_parts"] = [(int(u), int(l), h) for u, l, h in out.attrs["levels_given_up_parts"]]
        g.attrs["levels_near"] = [(int(u), int(l), h) for u, l, h in out.attrs["levels_near"]]
        g.attrs["levels_orders_not_kept"] = [(int(x), int(y)) for x, y in out.attrs["levels_orders_not_kept"]]
        g.attrs["levels_info"] = out.attrs["levels_info"]
        if given:
            warnings.warn(f"compute_levels: {len(given)} stack pair(s) could not be satisfied; see result.attrs['levels_given_up']", stacklevel=2)
    g["casing_start"], g["casing_level"], g["casing_end"], g["fill_level"] = ([p[i] for p in pos] for i in (0, 1, 2, 3))
    from .levels_store import levels_params
    g.attrs["levels_params"] = levels_params(method, head_m, band_dist, margin, max_level, band_col, order, min_positions and method == "solve")       # what the numbers were computed with (save_levels stores it)
    return g

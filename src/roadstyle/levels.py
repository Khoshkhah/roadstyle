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


def _solve_intervals(metres, meets, stacks, orders, limit, head_m, max_level, margin, min_positions=True, max_positions=None):
    """The solver on roads (one per segment, both directions together) and their relations (:func:`_relations`, or a pairs table). Every road has
    one fill number ``b`` and a casing divided into a start head, a main part and an end head (one number for a road shorter than ``2 * head_m``).
    Returns ``(parts, given_up, info)``: ``parts[r] = (a_start, a_main, a_end, b)``. The model is a linear program solved on a sparse matrix with
    HiGHS (docs/design/levels_split_casing.md, section 7)."""
    import time
    from types import SimpleNamespace

    import numpy as np
    import scipy.sparse as sp
    t0, n = time.time(), len(metres)
    zero = [(0, 0, 0, 0)] * n
    import shapely
    long_ = (shapely.length(np.asarray(metres, dtype=object)) >= 2 * head_m).tolist()
    pair_list = sorted(set(stacks))
    # a short upper road has no main part, its one casing number meets the roads at both ends (docs/design/levels_split_casing.md, section 6): its
    # pair puts its FILL after the lower road's fill, not its casing (Kaveh 2026-10-06: short ground pieces over a tunnel were drawn level with it)
    short_upper = sum(not long_[u] for u, _ in pair_list)
    info = {"pairs": len(pair_list) - short_upper, "roads": n, "short_roads": long_.count(False), "short_upper_pairs": short_upper, "meets": len(meets)}
    O = sorted(set(orders))
    if not pair_list and not O:
        return zero, [], {**info, "pairs": 0, "order_pairs": 0, "order_violations": 0, "solves": 0, "seconds": 0.0}      # no pair, no order: all zero is the optimum

    # variables: b_r = column r; then the casing parts (three for a long road, one for a short road); the slacks of the stages 1-3 come after
    part, ncol, casing = [], n, []                             # part[r]: "s" / "m" / "e" -> column; casing: (road, column) of every casing part
    for r in range(n):
        if long_[r]:
            part.append({"s": ncol, "m": ncol + 1, "e": ncol + 2})
            casing += [(r, ncol), (r, ncol + 1), (r, ncol + 2)]
            ncol += 3
        else:
            part.append({"s": ncol, "m": ncol, "e": ncol})
            casing.append((r, ncol))
            ncol += 1
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
    for u, l in pair_list:
        le([(l, 1.0), (part[u]["m"] if long_[u] else u, -1.0)], -margin)    # H3: b_l + margin <= a_(u, main); a short upper road: <= b_u
    for x, y in O:
        le([(y, 1.0), (x, -1.0)], -margin)                     # H4: b_y + margin <= b_x
    nrow, nP, nO = len(rhs), len(pair_list), len(O)
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
    solves = 1
    x0 = _difference_lp(cost, A0, b_ub, box[1])                # stage 0: nothing violated; a min-cost flow
    if x0 is not None:
        res, how = SimpleNamespace(status=0, x=x0), "flow"
    else:
        res, how = solve(cost, A0, b_ub, box), "highs"          # the flow cannot certify: the LP with HiGHS
    slack = np.zeros(nP + nO)
    if res.status == 2:                                        # infeasible: some Q3 / Q4 must be violated; stages 1-3 with slacks
        S = sp.csr_matrix((-np.ones(nP + nO), (np.arange(base, nrow), np.arange(nP + nO))), shape=(nrow, nP + nO))
        A1 = sp.hstack([A0, S], format="csr")
        bounds = [box] * ncol + [(0, None)] * (nP + nO)
        c1 = np.concatenate([np.zeros(ncol), np.ones(nP), np.zeros(nO)])
        c2 = np.concatenate([np.zeros(ncol), np.zeros(nP), np.ones(nO)])
        c3 = np.concatenate([cost, np.zeros(nP + nO)])
        sum_s = sp.csr_matrix((np.ones(nP), (np.zeros(nP, dtype=int), ncol + np.arange(nP))), shape=(1, ncol + nP + nO))
        sum_t = sp.csr_matrix((np.ones(nO), (np.zeros(nO, dtype=int), ncol + nP + np.arange(nO))), shape=(1, ncol + nP + nO))
        r1 = solve(c1, A1, b_ub, bounds)
        if r1.status != 0:
            raise RuntimeError(f"compute_levels: the solver returned status {r1.status}: {r1.message}")
        tol = 1e-7 * max(1.0, r1.fun)
        A2, b2 = sp.vstack([A1, sum_s], format="csr"), np.append(b_ub, r1.fun + tol)                 # stage 2: T1 held at its optimum
        r2 = solve(c2, A2, b2, bounds)
        if r2.status != 0:
            raise RuntimeError(f"compute_levels: the solver returned status {r2.status}: {r2.message}")
        tol2 = 1e-7 * max(1.0, r2.fun)
        A3, b3 = sp.vstack([A2, sum_t], format="csr"), np.append(b2, r2.fun + tol2)                  # stage 3: T1 and T2 held
        res = solve(c3, A3, b3, bounds)
        solves = 4
    if res.status != 0:
        raise RuntimeError(f"compute_levels: the solver returned status {res.status}: {res.message}")
    x = res.x
    if solves == 4:
        slack = x[ncol:]
    x = np.round(x[:ncol], 6)
    integral = bool(np.all(np.abs(x - np.round(x)) < 1e-6))
    val = (lambda v: int(round(v))) if integral else (lambda v: float(v))             # integers in practice: the constraints are x - y <= c with integer c
    parts = [(val(x[part[r]["s"]]), val(x[part[r]["m"]]), val(x[part[r]["e"]]), val(x[r])) for r in range(n)]
    gu = [pair_list[i] for i in range(nP) if slack[i] >= margin * (1 - 1e-6)]          # the upper casing is not after the lower fill
    violated = int((slack[nP:] >= margin * (1 - 1e-6)).sum())
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
    edge, and its ``highway_col``, ``name``, ``edge_ref``, ``tunnel_col``, ``bridge_col`` and ``layer_col`` when the edges have them. ``pairs``: one row per relation, ``relation`` / ``a`` / ``b`` / ``a_end`` / ``b_end``: ``meet`` (the end ``a_end`` of ``a`` is the end
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
    shown = {c: list(head[c]) for c in dict.fromkeys((highway_col, "name", "edge_ref", tunnel_col, bridge_col, layer_col))     # to read and draw the
             if c in g.columns}                                                                                                     # roads (the editor): look and all
    roads = gpd.GeoDataFrame({"road": name, "edges": mine[0], "reversed": mine[1], "band": beta,
                              "priority": omega if omega is not None else [None] * len(first), **shown}, geometry=list(head.geometry), crs=g.crs)
    rows = ([("meet", name[x], name[y], ex, ey) for x, ex, y, ey in meets] + [("stack", name[u], name[l], None, None) for u, l in stacks]
            + [("order", name[x], name[y], None, None) for x, y in orders])
    return roads, pd.DataFrame(rows, columns=["relation", "a", "b", "a_end", "b_end"])


def _read_pairs(pairs):
    import pandas as pd
    t = pd.read_csv(pairs, dtype=str, keep_default_na=False) if isinstance(pairs, (str, bytes)) or hasattr(pairs, "__fspath__") else pairs.copy()
    for c in ("a", "b", "a_end", "b_end"):
        t[c] = [None if v is None or (isinstance(v, float) and v != v) or v == "" else str(v) for v in t[c]] if c in t else None
    return t


def solve_levels(roads, pairs, edits=None, head_m=5.0, max_level=20, margin=1.0, time_limit=60.0, min_positions=True, max_positions=None):
    """Solve the drawing levels of ``roads`` from their ``pairs`` (both from :func:`level_input`, or read back from ``roads.parquet`` /
    ``pairs.csv``) and the caller's ``edits`` (a table or a CSV with the columns of ``pairs`` and ``enabled``: a row with ``enabled`` false
    switches off the same relation of ``pairs``, any other row is added; ``a`` / ``b`` may name any edge of a road). Returns ``roads`` with
    ``casing_start``, ``casing_level``, ``casing_end`` and ``fill_level`` (in the road's own direction); ``attrs["levels_given_up"]`` (the
    stack pairs that could not be kept, as road ids) and ``attrs["levels_info"]``."""
    t = _read_pairs(pairs)
    of = {}
    for i, r in enumerate(roads.itertuples()):
        for e in [r.road, *list(r.edges), *list(r.reversed)]:
            of[str(e)] = i
    def key(row):
        return (row["relation"], row["a"], row["b"], row["a_end"] if row["relation"] == "meet" else None, row["b_end"] if row["relation"] == "meet" else None)
    rel = {key(row): row for row in t.to_dict("records")}
    if edits is not None:
        for row in _read_pairs(edits).to_dict("records"):
            for c in ("a", "b"):
                if row[c] not in of:
                    raise ValueError(f"edits: {row[c]!r} is not an edge of the roads")
                row[c] = roads["road"].iat[of[row[c]]]
            if str(row.get("enabled", "")).strip().lower() in ("false", "0", "no"):
                if rel.pop(key(row), None) is None:
                    raise ValueError(f"edits: no {row['relation']} pair {row['a']} {row['b']} to switch off")
            else:
                rel[key(row)] = row
    idx = {r: i for i, r in enumerate(roads["road"])}
    meets = [(idx[r["a"]], r["a_end"], idx[r["b"]], r["b_end"]) for r in rel.values() if r["relation"] == "meet"]
    stacks = [(idx[r["a"]], idx[r["b"]]) for r in rel.values() if r["relation"] == "stack"]
    orders = [(idx[r["a"]], idx[r["b"]]) for r in rel.values() if r["relation"] == "order"]
    iv, given, info = _solve_intervals(list(_metres(roads.geometry)), meets, stacks, orders, time_limit, head_m, max_level, margin, min_positions,
                                       max_positions)
    counts = defaultdict(int)                                  # the solution can sit at any height: the main casing number most edges have becomes 0 (the ground)
    for r, row in enumerate(roads.itertuples()):
        counts[iv[r][1]] += len(row.edges) + len(row.reversed)
    ground = max(counts, key=lambda v: (counts[v], -v))
    iv = [tuple(x - ground for x in p) for p in iv]
    cm = _compress([v for p in iv for v in p])
    out = roads.copy()
    out["casing_start"], out["casing_level"], out["casing_end"], out["fill_level"] = ([cm[p[k]] for p in iv] for k in range(4))
    out.attrs["levels_given_up"] = [(roads["road"].iat[u], roads["road"].iat[l]) for u, l in given]
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
    * every road's casing is divided into two heads of ``head_m`` metres (at its nodes) and a main part; the heads merge with the roads that meet there, the main
      part is stacked; a road shorter than ``2 * head_m`` is one head;
    * ``order`` (a column of numbers, ``"class"`` for the renderer's class order, or ``"priority"``: roundabouts (``junction_col`` is ``roundabout`` or
      ``circular``), then tunnels, then bridges, then the class order): where roads of one band meet, the one with the higher number has the later fill
      where the other constraints allow; this is a wish, not a requirement. A road with no class takes no part in ``"class"`` or ``"priority"``.
    ``max_level``: the numbers are in ``[-max_level, max_level]``; ``margin``: how much later a road is painted where one must be painted after another
    (only the order matters: it changes the scale); ``time_limit``: seconds for each LP solve; ``min_positions``: also minimise the span of the numbers (fewer positions, a little
    less compaction; section 7.3.1); False leaves it out.
    Results beyond the columns: ``result.attrs["levels_given_up"]`` = ``[(upper index, lower index)]`` (also warned about),
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
        out = solve_levels(roads, pairs, head_m=head_m, max_level=max_level, margin=margin, time_limit=time_limit, min_positions=min_positions)
        lv = out[["casing_start", "casing_level", "casing_end", "fill_level"]].to_numpy().tolist()
        pos = [tuple(lv[r]) if same[i] else (lv[r][2], lv[r][1], lv[r][0], lv[r][3]) for i, r in enumerate(rid)]   # the other direction: heads swapped
        given = out.attrs["levels_given_up"]
        g.attrs["levels_given_up"] = [(int(u), int(l)) for u, l in given]
        g.attrs["levels_info"] = out.attrs["levels_info"]
        if given:
            warnings.warn(f"compute_levels: {len(given)} stack pair(s) could not be satisfied; see result.attrs['levels_given_up']", stacklevel=2)
    g["casing_start"], g["casing_level"], g["casing_end"], g["fill_level"] = ([p[i] for p in pos] for i in (0, 1, 2, 3))
    from .levels_store import levels_params
    g.attrs["levels_params"] = levels_params(method, head_m, band_dist, margin, max_level, band_col, order, min_positions and method == "solve")       # what the numbers were computed with (save_levels stores it)
    return g

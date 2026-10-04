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


def _solve_intervals(metres, ends, beta, omega, limit, band_dist, head_m, max_level, margin, min_positions=True):
    """method="solve" on roads (one per segment, both directions together). Every road has one fill number ``b`` and a casing divided into a start head,
    a main part and an end head (one number for a road shorter than ``2 * head_m``). Returns ``(parts, given_up, info)``: ``parts[r] = (a_start, a_main, a_end, b)``.
    The model is a linear program solved on a sparse matrix with HiGHS (docs/design/levels_split_casing.md, section 7)."""
    import time
    from types import SimpleNamespace

    import numpy as np
    import scipy.sparse as sp
    from scipy.optimize import linprog
    from shapely import STRtree
    t0, n = time.time(), len(metres)
    zero = [(0, 0, 0, 0)] * n
    import shapely
    long_ = (shapely.length(np.asarray(metres, dtype=object)) >= 2 * head_m).tolist()
    at = defaultdict(set)
    for r, (s, t) in enumerate(ends):
        at[s].add(r), at[t].add(r)
    # stack pairs (upper, lower): roads within band_dist of each other whose bands differ (a crossing and a meeting are both at distance 0)
    pairs = set()
    if len(set(beta)) > 1:
        qi, ti = STRtree(metres).query(metres, predicate="dwithin", distance=band_dist)
        for i, j in zip(qi.tolist(), ti.tolist(), strict=True):
            if i < j and beta[i] != beta[j]:
                pairs.add((i, j) if beta[i] > beta[j] else (j, i))
    pair_list = sorted(p for p in pairs if long_[p[0]])        # a short upper road has no main part: its pairs are not stack pairs (docs/design/levels_split_casing.md, section 6)
    short_upper = len(pairs) - len(pair_list)
    info = {"pairs": len(pair_list), "roads": n, "short_roads": long_.count(False), "short_upper_pairs": short_upper}
    if not pair_list and omega is None:
        return zero, [], {**info, "pairs": 0, "solves": 0, "seconds": 0.0}      # no pair, no order: all zero is the optimum
    J = sorted({(x, y) for rs in at.values() for x in rs for y in rs if x < y})              # roads that share an end node
    O = [(x, y) if omega[x] > omega[y] else (y, x) for x, y in J
         if omega is not None and omega[x] is not None and omega[y] is not None and beta[x] == beta[y] and omega[x] != omega[y]]

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
    for v, rs in at.items():                                   # H2: every pair that meets at the node v
        rs = sorted(rs)
        for i, x in enumerate(rs):
            for y in rs[i + 1:]:
                for p, node in (("s", ends[x][0]), ("e", ends[x][1])):
                    if node == v:
                        le([(part[x][p], 1.0), (y, -1.0)], 0.0)
                for p, node in (("s", ends[y][0]), ("e", ends[y][1])):
                    if node == v:
                        le([(part[y][p], 1.0), (x, -1.0)], 0.0)
    if min_positions:                                          # section 7.3.1: H above and L below every number; the span H - L is in the cost
        H, Lo, first_nv = ncol, ncol + 1, ncol
        for v in range(first_nv):
            le([(v, 1.0), (H, -1.0)], 0.0)                     # x_v <= H
            le([(Lo, 1.0), (v, -1.0)], 0.0)                    # L <= x_v
        ncol += 2
    base = len(rhs)
    for u, l in pair_list:
        le([(l, 1.0), (part[u]["m"], -1.0)], -margin)         # H3: b_l + margin <= a_(u, main)
    for x, y in O:
        le([(y, 1.0), (x, -1.0)], -margin)                     # H4: b_y + margin <= b_x
    nrow, nP, nO = len(rhs), len(pair_list), len(O)
    A0 = sp.csr_matrix((vals, (rows, cols)), shape=(nrow, ncol))
    b_ub = np.array(rhs)
    cost = np.zeros(ncol)                                      # T3: the sum of (b_road(c) - a_c)
    for r, v in casing:
        cost[r] += 1.0
        cost[v] -= 1.0
    if min_positions:
        w4 = float(cost[cost > 0].sum() * 2 * max_level + 1)   # W4 > the whole range of T3
        cost[H], cost[Lo] = w4, -w4

    def solve(c, A, bu, lo_hi):
        res = linprog(c, A_ub=A, b_ub=bu, bounds=lo_hi, method="highs-ipm", options={"time_limit": limit})
        return res
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


def compute_levels(edges, layer_col="layer", bridge_col="bridge", tunnel_col="tunnel",
                   method="solve", band_col=None, order=None, highway_col="highway", band_dist=10.0, head_m=5.0, max_level=20, margin=1.0, time_limit=60.0, min_positions=True):
    """A copy of ``edges`` with the drawing-order columns ``casing_start``, ``casing_level`` (the main part), ``casing_end`` and ``fill_level``;
    ``render_edges(casing_level_col=..., fill_level_col=...)`` draws by the last two (the heads are not drawn yet).

    ``method="solve"`` (default): the optimization of docs/design/levels_split_casing.md, section 7 (a minimum-cost flow, OR-tools; HiGHS when a wish must be given up).
    ``method="tags"``: a rule on the ``layer`` / ``bridge`` / ``tunnel`` tags and the shared end nodes, O(edges); the three casing numbers are equal
    (section 10).
    * the **band** of a road is the column ``band_col`` (integers) if given, else its level from the tags (``layer``, else bridge 1, tunnel -1, else 0);
      two roads within ``band_dist`` metres with different bands are a stack pair (the higher band is over the lower one), a crossing included;
    * every road's casing is divided into two heads of ``head_m`` metres (at its nodes) and a main part; the heads merge with the roads that meet there, the main
      part is stacked; a road shorter than ``2 * head_m`` is one head;
    * ``order`` (a column of numbers, or ``"class"`` for the renderer's class order): where roads meet, the one with the higher number has the later fill
      where the other constraints allow; this is a wish, not a requirement.
    ``max_level``: the numbers are in ``[-max_level, max_level]``; ``margin``: how much later a road is painted where one must be painted after another
    (only the order matters: it changes the scale); ``time_limit``: seconds for each LP solve; ``min_positions``: also minimise the span of the numbers (fewer positions, a little
    less compaction; section 7.3.1); False leaves it out.
    Results beyond the columns: ``result.attrs["levels_given_up"]`` = ``[(upper index, lower index)]`` (also warned about),
    ``result.attrs["levels_info"]`` = counts, order violations, solver status, seconds.
    ponytail: tags method ignores crossings without tags and band / order; solve method does not cut a road at the place where it changes level."""
    if method not in ("tags", "solve"):
        raise ValueError(f"compute_levels: method must be 'tags' or 'solve', not {method!r}")
    if method == "tags" and (band_col or order):
        raise ValueError("compute_levels: band_col and order are part of the optimization problem; use method='solve'")
    if method == "solve" and not (margin > 0 and max_level > 0):
        raise ValueError(f"compute_levels: margin and max_level must be greater than 0, not {margin!r} and {max_level!r}")
    import numpy as np
    import shapely
    g = edges.copy()
    geoms = np.asarray(g.geometry.values, dtype=object)
    xy, gi = shapely.get_coordinates(geoms, return_index=True)
    cnt = np.bincount(gi, minlength=len(geoms))
    if (cnt < 2).any():
        raise ValueError(f"compute_levels: every edge needs a line of at least two points; rows {list(g.index[cnt < 2][:5])} have not")
    off = np.r_[0, np.cumsum(cnt)]
    _, node = np.unique(np.vstack([xy[off[:-1]], xy[off[1:] - 1]]), axis=0, return_inverse=True)      # the end points of every edge, by exact equality, as node numbers
    node = node.ravel()
    ends = list(zip(node[:len(geoms)].tolist(), node[len(geoms):].tolist(), strict=True))
    if method == "tags":
        lv = [_level(r, layer_col, bridge_col, tunnel_col) for r in g.to_dict("records")]
        pos = [(c, c, c, f) for c, f in _tag_intervals(ends, lv)]
    else:
        import pandas as pd
        fwd = [xy[off[i]:off[i + 1]].tobytes() for i in range(len(geoms))]
        rev = [xy[off[i]:off[i + 1]][::-1].tobytes() for i in range(len(geoms))]
        key = [(frozenset(e), min(f, r)) for e, f, r in zip(ends, fwd, rev, strict=True)]     # both directions of a segment are one road
        road, first = {}, []
        for i, k in enumerate(key):
            if k not in road:
                road[k] = len(first)
                first.append(i)
        rid = [road[k] for k in key]
        head = g.iloc[first]
        if band_col:
            beta = pd.to_numeric(head[band_col], errors="coerce").fillna(0).round().astype(int).tolist()
        else:
            beta = [_level(r, layer_col, bridge_col, tunnel_col) for r in head.to_dict("records")]
        omega = None
        if order == "class":                                   # a road with no class takes no part in the order: no wish for it (None)
            z = {h: _class_order(h) for h in head[highway_col].dropna().unique()}
            omega = [None if pd.isna(h) else z[h] for h in head[highway_col]]
        elif order:
            omega = [None if pd.isna(v) else float(v) for v in pd.to_numeric(head[order], errors="coerce")]
        gm = g.geometry
        if g.crs is not None and g.crs.is_geographic:
            gm = g.to_crs(g.estimate_utm_crs()).geometry
        rm, re_ = list(gm.iloc[first]), [ends[i] for i in first]
        iv, given, info = _solve_intervals(rm, re_, beta, omega, time_limit, band_dist, head_m, max_level, margin, min_positions)
        counts = defaultdict(int)                              # the solution can sit at any height: the main casing number most rows have becomes 0 (the ground)
        for r in rid:
            counts[iv[r][1]] += 1
        ground = max(counts, key=lambda v: (counts[v], -v))
        iv = [tuple(x - ground for x in p) for p in iv]
        cm = _compress([v for p in iv for v in p])
        pos = [tuple(cm[x] for x in iv[r]) for r in rid]
        for i in range(len(pos)):                              # the numbers belong to the road's first edge: the reversed direction has its heads the other way round
            if fwd[i] != fwd[first[rid[i]]]:
                pos[i] = (pos[i][2], pos[i][1], pos[i][0], pos[i][3])
        g.attrs["levels_given_up"] = [(first[u], first[l]) for u, l in given]
        g.attrs["levels_info"] = info
        if given:
            warnings.warn(f"compute_levels: {len(given)} stack pair(s) could not be satisfied; see result.attrs['levels_given_up']", stacklevel=2)
    g["casing_start"], g["casing_level"], g["casing_end"], g["fill_level"] = ([p[i] for p in pos] for i in (0, 1, 2, 3))
    from .levels_store import levels_params
    g.attrs["levels_params"] = levels_params(method, head_m, band_dist, margin, max_level, band_col, order, min_positions and method == "solve")       # what the numbers were computed with (save_levels stores it)
    return g

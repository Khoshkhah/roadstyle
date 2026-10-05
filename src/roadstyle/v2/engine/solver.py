"""Linear Programming (LP) & Min-Cost Flow Stacking Solver for roadstyle v2 Core Engine.

Resolves vertical grade separation (tunnels, bridges, flyovers) and junction
flow priorities (roundabout rings, through-movements) into discrete painting
order levels for casings (cs, cm, ce) and fills (fl), utilizing the proven
optimization solver from roadstyle v1 (levels.py).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np
import shapely
from shapely.geometry import LineString

from ...levels import _class_order, _compress, _solve_intervals
from .primitives import Corridor


@dataclass(slots=True)
class StackingSolution:
    """Computed discrete casing and fill levels for a list of corridors."""

    casing_levels: list[tuple[int, int, int]]  # (cs, cm, ce) per corridor
    fill_levels: list[int]                    # fl per corridor
    status: str = "OPTIMAL"
    info: dict[str, Any] = field(default_factory=dict)


def _compute_metric_scale(corridors: list[Corridor]) -> tuple[bool, float, float, float, float]:
    """Compute dataset-level metric projection scale factors and origin."""
    all_lats: list[float] = []
    all_lons: list[float] = []
    for c in corridors:
        g = c.geometry
        if isinstance(g, LineString) and len(g.coords) > 0:
            all_lons.append(g.coords[0][0])
            all_lats.append(g.coords[0][1])

    if all_lats and max(abs(min(all_lons)), abs(max(all_lons))) <= 180.0 and max(abs(min(all_lats)), abs(max(all_lats))) <= 90.0:
        lon0 = sum(all_lons) / len(all_lons)
        lat0 = sum(all_lats) / len(all_lats)
        kx = 111320.0 * math.cos(math.radians(lat0))
        ky = 110540.0
        return True, lon0, lat0, kx, ky
    return False, 0.0, 0.0, 1.0, 1.0


def solve_stacking(
    corridors: list[Corridor],
    *,
    band_dist: float = 10.0,
    head_m: float = 5.0,
    max_level: int = 20,
    margin: float = 1.0,
    time_limit: float = 60.0,
    assign: bool = True,
) -> StackingSolution:
    """Solve drawing order for corridors using the proven optimization solver.

    Parameters
    ----------
    corridors : list[Corridor]
        The corridors to solve stacking for.
    band_dist : float
        Distance in meters within which corridors of differing bands are treated as grade crossings.
    head_m : float
        Length in meters of junction casing heads (default 5.0m).
    max_level : int
        Maximum absolute level range (default 20).
    margin : float
        Minimum level separation between stacked layers (default 1.0).
    time_limit : float
        Maximum seconds for LP solve (default 60.0).
    assign : bool
        If True, writes the computed levels directly onto corridor.casing_levels and corridor.fill_level.

    Returns
    -------
    StackingSolution
        Discrete integer levels for casing start, casing main, casing end, and fill.
    """
    n = len(corridors)
    if n == 0:
        return StackingSolution(casing_levels=[], fill_levels=[], status="EMPTY")

    # 1. Compute discrete node IDs from line endpoints
    geoms = np.asarray([c.geometry for c in corridors], dtype=object)
    xy, gi = shapely.get_coordinates(geoms, return_index=True)
    cnt = np.bincount(gi, minlength=len(geoms))
    off = np.r_[0, np.cumsum(cnt)]
    _, node = np.unique(np.vstack([xy[off[:-1]], xy[off[1:] - 1]]), axis=0, return_inverse=True)
    node = node.ravel()
    ends = list(zip(node[:len(geoms)].tolist(), node[len(geoms):].tolist(), strict=True))

    # 2. Metric projection for accurate metric lengths and setbacks
    is_lonlat, lon0, lat0, kx, ky = _compute_metric_scale(corridors)
    if is_lonlat:
        rm = [
            LineString([((x - lon0) * kx, (y - lat0) * ky) for x, y in c.geometry.coords])
            if hasattr(c.geometry, "coords") else c.geometry
            for c in corridors
        ]
    else:
        rm = [c.geometry for c in corridors]

    beta = [c.band for c in corridors]

    # Flow priority / class order
    omega: list[float | None] = []
    has_omega = False
    for c in corridors:
        p = c.junction_priority
        hw = c.properties.get("highway")
        if p is not None and (p != 0.0 or hw is None):
            omega.append(float(p))
            if p != 0.0:
                has_omega = True
        elif hw:
            co = _class_order(hw)
            omega.append(co)
            has_omega = True
        else:
            omega.append(0.0)

    omega_arg = omega if has_omega else None

    # Determine head_m from split_start if available
    avg_head = head_m
    if corridors:
        sample_heads = [c.split_start for c in corridors if c.split_start and c.split_start > 0]
        if sample_heads:
            avg_head = float(sum(sample_heads) / len(sample_heads))

    # 3. Solve with proven optimization engine (Dual min-cost flow / HiGHS-IPM)
    iv, given, info = _solve_intervals(
        metres=rm,
        ends=ends,
        beta=beta,
        omega=omega_arg,
        limit=time_limit,
        band_dist=band_dist,
        head_m=avg_head,
        max_level=max_level,
        margin=margin,
        min_positions=True,
    )

    # 4. Center ground around 0 and compress to small order-preserving integers
    counts: dict[int, int] = defaultdict(int)
    for p in iv:
        counts[p[1]] += 1
    ground = max(counts, key=lambda v: (counts[v], -v)) if counts else 0
    iv_shifted = [tuple(x - ground for x in p) for p in iv]
    cm = _compress([v for p in iv_shifted for v in p])
    pos = [tuple(cm[x] for x in p) for p in iv_shifted]

    casing_results: list[tuple[int, int, int]] = []
    fill_results: list[int] = []
    for i in range(n):
        cs, cm_lvl, ce, fl = pos[i]
        casing_results.append((cs, cm_lvl, ce))
        fill_results.append(fl)
        if assign:
            corridors[i].casing_levels = (cs, cm_lvl, ce)
            corridors[i].fill_level = fl

    return StackingSolution(
        casing_levels=casing_results,
        fill_levels=fill_results,
        status="OPTIMAL",
        info=info,
    )

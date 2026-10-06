"""Linear Programming (LP) & Min-Cost Flow Stacking Solver for roadstyle v2 Core Engine.

Resolves vertical grade separation (tunnels, bridges, flyovers) and junction
flow priorities (roundabout rings, through-movements) into discrete painting
order levels for casings (cs, cm, ce) and fills (fl), utilizing the proven
optimization solver from roadstyle v1 (levels.py).
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
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


def _physical_road_id(corridor: Corridor) -> str | None:
    """Return an explicit source identifier shared by directional road copies."""
    for key in ("physical_road_id", "road_id", "way_id", "osm_id"):
        value = corridor.properties.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _direction_twin_groups(
    corridors: list[Corridor],
) -> tuple[list[int], list[tuple[int, bool]]]:
    """Map exact reverse geometries with matching physical IDs to one representative."""
    representative_indices: list[int] = []
    mapping: list[tuple[int, bool]] = []
    representatives: dict[tuple[str, int, tuple[tuple[float, ...], ...]], list[int]] = {}

    for index, corridor in enumerate(corridors):
        geometry = corridor.geometry
        physical_id = _physical_road_id(corridor)
        if not isinstance(geometry, LineString) or physical_id is None:
            representative_indices.append(index)
            mapping.append((len(representative_indices) - 1, False))
            continue

        coordinates = tuple(tuple(coord) for coord in geometry.coords)
        reverse_coordinates = tuple(reversed(coordinates))
        signature = (physical_id, corridor.band, reverse_coordinates)
        twin_index = None
        for candidate_index in representatives.get(signature, []):
            candidate = corridors[representative_indices[candidate_index]]
            if (
                corridor.junction_priority == candidate.junction_priority
                and corridor.split_mode == candidate.split_mode
                and corridor.split_start == candidate.split_end
                and corridor.split_end == candidate.split_start
                and (
                    corridor.junction_priority != 0
                    or corridor.properties.get("highway") == candidate.properties.get("highway")
                )
            ):
                twin_index = candidate_index
                break

        if twin_index is not None:
            mapping.append((twin_index, True))
            continue

        representative_index = len(representative_indices)
        representative_indices.append(index)
        mapping.append((representative_index, False))
        representatives.setdefault(
            (physical_id, corridor.band, coordinates), [],
        ).append(representative_index)

    return representative_indices, mapping


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
    pair_table: list[dict[str, Any]] | str | Path | None = None,
    pair_overrides: list[dict[str, Any]] | str | Path | None = None,
    band_dist: float = 10.0,
    head_m: float = 15.0,
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
    pair_table : rows or CSV path, optional
        Original pair table. If omitted, the original table is discovered from geometry and tags.
    pair_overrides : rows or CSV path, optional
        Sparse CSV/table overrides applied to the original pair table before solving.
    band_dist : float
        Distance in meters within which corridors of differing bands are treated as grade crossings.
    head_m : float
        Length in meters of junction casing heads (default 15.0m).
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
    original_count = len(corridors)
    if original_count == 0:
        return StackingSolution(casing_levels=[], fill_levels=[], status="EMPTY")

    from .pairs import (
        _corridor_refs,
        discover_pair_table,
        merge_pair_overrides,
        read_pair_table,
    )

    refs = _corridor_refs(corridors)
    if len(set(refs)) != len(refs):
        raise ValueError("solve_stacking: corridor edge references must be unique")
    representative_indices, corridor_mapping = _direction_twin_groups(corridors)
    solve_corridors = [corridors[index] for index in representative_indices]
    n = len(solve_corridors)

    # 1. Compute discrete node IDs from line endpoints
    geoms = np.asarray([c.geometry for c in solve_corridors], dtype=object)
    xy, gi = shapely.get_coordinates(geoms, return_index=True)
    cnt = np.bincount(gi, minlength=len(geoms))
    off = np.r_[0, np.cumsum(cnt)]
    _, node = np.unique(np.vstack([xy[off[:-1]], xy[off[1:] - 1]]), axis=0, return_inverse=True)
    node = node.ravel()
    ends = list(zip(node[:len(geoms)].tolist(), node[len(geoms):].tolist(), strict=True))

    # 2. Metric projection for accurate metric lengths and setbacks
    is_lonlat, lon0, lat0, kx, ky = _compute_metric_scale(solve_corridors)
    if is_lonlat:
        rm = [
            LineString([((x - lon0) * kx, (y - lat0) * ky) for x, y in c.geometry.coords])
            if hasattr(c.geometry, "coords") else c.geometry
            for c in solve_corridors
        ]
    else:
        rm = [c.geometry for c in solve_corridors]

    beta = [c.band for c in solve_corridors]

    # Flow priority / class order
    omega: list[float | None] = []
    has_omega = False
    for c in solve_corridors:
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

    # Pair discovery is separate from optimization. Persisted tables can be edited
    # and passed back in so an optimization rerun uses the same relationships.
    if pair_table is None:
        original_pairs = discover_pair_table(corridors, band_dist=band_dist)
    elif isinstance(pair_table, (str, Path)):
        original_pairs = read_pair_table(pair_table)
    else:
        original_pairs = [{str(k): str(v) for k, v in row.items()} for row in pair_table]
    if isinstance(pair_overrides, (str, Path)):
        override_rows = read_pair_table(pair_overrides, overrides=True)
    else:
        override_rows = pair_overrides or []
    effective_pairs = merge_pair_overrides(original_pairs, override_rows)

    ref_to_index = {ref: i for i, ref in enumerate(refs)}
    ref_to_solver_index = {
        ref: corridor_mapping[index][0] for index, ref in enumerate(refs)
    }
    node_refs = sorted({
        f"{coord[0]:.7f},{coord[1]:.7f}"
        for c in solve_corridors
        for coord in (c.geometry.coords[0], c.geometry.coords[-1])
    })
    node_ids = {node_ref: i for i, node_ref in enumerate(node_refs)}
    stack_pairs: set[tuple[int, int]] = set()
    connect_pairs: set[tuple[int, str, int, str, int]] = set()
    order_pairs: set[tuple[int, int]] = set()
    for row in effective_pairs:
        if str(row.get("enabled", "true")).lower() in {"false", "0", "no"}:
            continue
        relation = row.get("relation")
        if relation in {"near", "cross"}:
            upper, lower = row.get("upper_edge_ref"), row.get("lower_edge_ref")
            if upper not in ref_to_index or lower not in ref_to_index:
                raise ValueError(f"pair {row.get('pair_id')!r} references an unknown upper/lower edge")
            upper_index, lower_index = ref_to_solver_index[upper], ref_to_solver_index[lower]
            if upper_index != lower_index:
                stack_pairs.add((upper_index, lower_index))
        elif relation == "connect":
            edge_a, edge_b = row.get("edge_a"), row.get("edge_b")
            if edge_a not in ref_to_index or edge_b not in ref_to_index:
                raise ValueError(f"pair {row.get('pair_id')!r} references an unknown connected edge")
            node_ref = row.get("node_ref", "")
            if node_ref:
                try:
                    node = node_ids[node_ref]
                except KeyError:
                    raise ValueError(f"pair {row.get('pair_id')!r} has a node_ref that is not a corridor endpoint") from None
            else:
                # Manual connects constrain selected edge heads without a node.
                node = -1
            side_a, side_b = row.get("endpoint_a"), row.get("endpoint_b")
            if side_a not in {"start", "end"} or side_b not in {"start", "end"}:
                raise ValueError(f"pair {row.get('pair_id')!r} must specify start/end endpoints")
            solver_a, solver_b = ref_to_solver_index[edge_a], ref_to_solver_index[edge_b]
            if corridor_mapping[ref_to_index[edge_a]][1]:
                side_a = "end" if side_a == "start" else "start"
            if corridor_mapping[ref_to_index[edge_b]][1]:
                side_b = "end" if side_b == "start" else "start"
            if solver_a != solver_b:
                connect_pairs.add((solver_a, side_a, solver_b, side_b, node))
        elif relation == "order":
            upper, lower = row.get("upper_edge_ref"), row.get("lower_edge_ref")
            if upper not in ref_to_index or lower not in ref_to_index:
                raise ValueError(f"pair {row.get('pair_id')!r} references an unknown ordered edge")
            upper_index, lower_index = ref_to_solver_index[upper], ref_to_solver_index[lower]
            if upper_index != lower_index:
                order_pairs.add((upper_index, lower_index))
        else:
            raise ValueError(f"pair {row.get('pair_id')!r} has unsupported relation {relation!r}")

    # Determine head_m from split_start if available
    avg_head = head_m
    if solve_corridors:
        sample_heads = [c.split_start for c in solve_corridors if c.split_start and c.split_start > 0]
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
        pair_constraints={
            "stack_pairs": sorted(stack_pairs),
            "connect_pairs": sorted(connect_pairs),
            "order_pairs": sorted(order_pairs),
        },
    )

    # 4. Center ground around 0 and compress to small order-preserving integers
    counts: dict[int, int] = defaultdict(int)
    for p in iv:
        counts[p[1]] += 1
    ground = max(counts, key=lambda v: (counts[v], -v)) if counts else 0
    iv_shifted = [tuple(x - ground for x in p) for p in iv]
    cm = _compress([v for p in iv_shifted for v in p])
    pos = [tuple(cm[x] for x in p) for p in iv_shifted]

    representative_casings: list[tuple[int, int, int]] = []
    representative_fills: list[int] = []
    for i in range(n):
        cs, cm_lvl, ce, fl = pos[i]
        representative_casings.append((cs, cm_lvl, ce))
        representative_fills.append(fl)

    casing_results: list[tuple[int, int, int]] = []
    fill_results: list[int] = []
    for corridor, (solver_index, is_reverse) in zip(corridors, corridor_mapping, strict=True):
        cs, cm_lvl, ce = representative_casings[solver_index]
        if is_reverse:
            cs, ce = ce, cs
        casing = (cs, cm_lvl, ce)
        fill = representative_fills[solver_index]
        casing_results.append(casing)
        fill_results.append(fill)
        if assign:
            corridor.casing_levels = casing
            corridor.fill_level = fill

    return StackingSolution(
        casing_levels=casing_results,
        fill_levels=fill_results,
        status="OPTIMAL",
        info={**info, "direction_twin_count": original_count - n},
    )


def write_pair_tables(
    corridors: list[Corridor],
    original_path: str | Path,
    override_path: str | Path,
    *,
    band_dist: float = 10.0,
) -> None:
    """Write discovered original pairs and an empty, editable override CSV."""
    from .pairs import _corridor_refs, discover_pair_table, write_pair_table

    if any(ref.startswith("@index:") for ref in _corridor_refs(corridors)):
        raise ValueError(
            "write_pair_tables: persistent pair tables require a stable id, edge_ref, "
            "ref, or edge_id on every corridor"
        )
    write_pair_table(original_path, discover_pair_table(corridors, band_dist=band_dist))
    write_pair_table(override_path, [], overrides=True)


def write_level_table(
    corridors: list[Corridor],
    solution: StackingSolution,
    path: str | Path,
) -> None:
    """Write solved levels for every corridor to a CSV file."""
    from .pairs import _corridor_refs

    if len(solution.casing_levels) != len(corridors) or len(solution.fill_levels) != len(corridors):
        raise ValueError("write_level_table: solution must contain one result per corridor")
    refs = _corridor_refs(corridors)
    if len(set(refs)) != len(refs) or any(ref.startswith("@index:") for ref in refs):
        raise ValueError("write_level_table: every corridor needs a stable, unique edge reference")

    fields = ("edge_ref", "physical_road_id", "band", "cs", "cm", "ce", "fl")
    with Path(path).open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for corridor, ref, casing, fill in zip(
            corridors, refs, solution.casing_levels, solution.fill_levels, strict=True,
        ):
            writer.writerow({
                "edge_ref": ref,
                "physical_road_id": _physical_road_id(corridor) or "",
                "band": corridor.band,
                "cs": casing[0],
                "cm": casing[1],
                "ce": casing[2],
                "fl": fill,
            })

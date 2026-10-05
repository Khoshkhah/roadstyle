"""Pure mathematical 2-point casing splitting engine for roadstyle v2."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _cum_lengths(xy: np.ndarray) -> np.ndarray:
    """Cumulative lengths along 2D polyline xy."""
    d = np.diff(xy, axis=0)
    seg = np.hypot(d[:, 0], d[:, 1])
    return np.concatenate([[0.0], np.cumsum(seg)])


def _point_at_distance(xy: np.ndarray, cum: np.ndarray, d: float) -> np.ndarray:
    """Interpolate coordinates at distance d along polyline xy."""
    if d <= 0.0:
        return xy[0]
    if d >= cum[-1]:
        return xy[-1]
    idx = min(max(int(np.searchsorted(cum, d, side="right")) - 1, 0), len(cum) - 2)
    seg_len = cum[idx + 1] - cum[idx]
    frac = (d - cum[idx]) / seg_len if seg_len > 0.0 else 0.0
    return xy[idx] + frac * (xy[idx + 1] - xy[idx])


def _extract_part(xy: np.ndarray, cum: np.ndarray, a: float, b: float) -> np.ndarray:
    """The coordinates of polyline xy between distances a and b."""
    p_a = _point_at_distance(xy, cum, a)
    p_b = _point_at_distance(xy, cum, b)
    middle = xy[np.searchsorted(cum, a, side="right") : np.searchsorted(cum, b, side="left")]
    return np.vstack([p_a, middle, p_b])


def split_casing_geometry(
    coords: list[tuple[float, float]] | list[list[float]],
    split_start: float,
    split_end: float,
    split_mode: str = "setbacks",
    casing_levels: tuple[int, int, int] = (0, 0, 0),
    properties: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Subdivide a polyline into up to 3 casing pieces based on two cut numbers.

    Parameters
    ----------
    coords : list of (lon, lat)
        WGS84 polyline coordinates.
    split_start : float
        First split parameter (setback from start in meters, or start station).
    split_end : float
        Second split parameter (setback from end in meters, or end station).
    split_mode : str
        "setbacks" (distances from vertex 0 and -1) or "stations" (distances from vertex 0).
    casing_levels : tuple of (cs, cm, ce)
        Integer casing levels for start head, main span, and end head.
    properties : dict, optional
        Base properties to attach to each subdivided feature.

    Returns
    -------
    list of GeoJSON Feature dicts
        Subdivided casing LineString features with `__rs_cl` (casing level) and
        `__rs_cap` (True for main piece flat butt ends).
    """
    props = dict(properties or {})
    cs, cm, ce = casing_levels

    if hasattr(coords, "coords"):
        coords = list(coords.coords)

    # Pass-through for invalid line or identical levels (unsplit)
    if len(coords) < 2 or (cs == cm == ce):
        return [
            {
                "type": "Feature",
                "properties": {**props, "__rs_cl": cm},
                "geometry": {"type": "LineString", "coordinates": [list(pt[:2]) for pt in coords]},
            }
        ]

    lon0, lat0 = coords[0][0], coords[0][1]
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 111320.0

    # Project to local meters
    xy = np.column_stack(
        [
            np.asarray([(pt[0] - lon0) * kx for pt in coords]),
            np.asarray([(pt[1] - lat0) * ky for pt in coords]),
        ]
    )

    cum = _cum_lengths(xy)
    total_len = float(cum[-1])

    # Determine cut points (cut1, cut2) along polyline
    if split_mode == "stations":
        cut1 = min(total_len, max(0.0, float(split_start)))
        cut2 = min(total_len, max(cut1, float(split_end)))
    else:  # "setbacks"
        h1 = max(0.0, float(split_start))
        h2 = max(0.0, float(split_end))
        if h1 + h2 >= total_len:
            # Short road: heads meet proportionally; middle piece drops out
            sum_h = h1 + h2
            ratio = (h1 / sum_h) if sum_h > 0.0 else 0.5
            cut1 = cut2 = total_len * ratio
        else:
            cut1 = h1
            cut2 = total_len - h2

    cuts = [
        (0.0, cut1, cs, False),       # Start Head: round cap
        (cut1, cut2, cm, True),        # Main Span: flat butt cap (__rs_cap = True)
        (cut2, total_len, ce, False),  # End Head: round cap
    ]

    pieces = []
    for a, b, lvl, flat in cuts:
        if b - a < 1e-4:
            continue  # Omit zero-length or degenerate pieces

        pts = _extract_part(xy, cum, a, b)
        if len(pts) < 2 or not (np.diff(pts, axis=0) != 0).any():
            continue

        # Back-project to WGS84
        unproj_lon = np.round(pts[:, 0] / kx + lon0, 7)
        unproj_lat = np.round(pts[:, 1] / ky + lat0, 7)
        part_coords = np.column_stack([unproj_lon, unproj_lat]).tolist()

        piece_props = {**props, "__rs_cl": lvl}
        if flat:
            piece_props["__rs_cap"] = True

        pieces.append(
            {
                "type": "Feature",
                "properties": piece_props,
                "geometry": {"type": "LineString", "coordinates": part_coords},
            }
        )

    return pieces or [
        {
            "type": "Feature",
            "properties": {**props, "__rs_cl": cm},
            "geometry": {"type": "LineString", "coordinates": [list(pt[:2]) for pt in coords]},
        }
    ]

"""Filter edges by OSM ``highway`` type."""
from __future__ import annotations

from .style import normalize_highway


def _as_set(types) -> set[str] | None:
    if types is None:
        return None
    if isinstance(types, str):
        types = [types]
    return {t.strip().lower() for t in types}


def filter_edges(
    gdf,
    include=None,
    exclude=None,
    highway_col: str = "highway",
    match_links: bool = True,
):
    """Return a subset of ``gdf`` by highway type.

    - ``include``: keep only these types (str or iterable).
    - ``exclude``: drop these types.
    - ``match_links``: if True, ``primary`` also matches ``primary_link`` (compares the
      normalized base class). If False, exact tag match.
    Include is applied before exclude. Returns a copy.
    """
    inc, exc = _as_set(include), _as_set(exclude)
    if inc is None and exc is None:
        return gdf

    if match_links:
        key = gdf[highway_col].map(lambda h: normalize_highway(h)[0])
    else:
        key = gdf[highway_col].map(lambda h: (str(h) if h is not None else "").strip().lower())

    mask = key.notna() if hasattr(key, "notna") else None
    if inc is not None:
        mask = key.isin(inc)
    else:
        mask = key.map(lambda k: True)
    if exc is not None:
        mask = mask & ~key.isin(exc)
    return gdf[mask].copy()


def highway_types(gdf, highway_col: str = "highway", normalize: bool = True):
    """Return the sorted unique highway types present (counts via value_counts on the gdf)."""
    col = gdf[highway_col]
    if normalize:
        col = col.map(lambda h: normalize_highway(h)[0])
    return sorted(col.dropna().unique().tolist())

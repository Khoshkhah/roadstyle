"""Overlays: extra map layers the caller brings (zones, POIs, any geometry) drawn alongside the
styled roads.

An :class:`Overlay` is *passthrough* data — the caller's own geometry with the caller's own style
— so it does **not** go through roadstyle's road-styling compiler. The web backend turns each
overlay into its own MapLibre source + layer(s), placed under or over the roads, optionally
clickable (a popup of the chosen fields) and toggled from a *Layers* control.

Geometry kind is auto-detected (polygons -> ``fill``, lines -> ``line``, points -> ``circle``) but
can be forced via ``kind``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Overlay:
    """An extra layer to draw with the roads.

    Parameters
    ----------
    data : a GeoDataFrame / GeoSeries (any CRS; reprojected to EPSG:4326) or a GeoJSON mapping
        (geometry, Feature, or FeatureCollection — assumed lon/lat). Feature ``properties`` are
        kept and shown in the click popup.
    kind : ``"fill"`` | ``"line"`` | ``"circle"`` | ``"text"`` — defaults to auto-detect from the geometry (``"text"`` is never detected).
    placement : ``"under"`` (below the roads — e.g. zone fills) or ``"over"`` (on top — e.g. POIs).
    color / opacity : the layer's paint colour and (kind-dependent) default opacity.
    outline : polygon outline colour (``fill`` only; defaults to ``color``).
    radius : circle radius in px (``circle`` only).
    width : line / outline width in px (``line`` / ``fill`` outline).
    label : the name shown in the *Layers* toggle (defaults to ``"Layer N"``).
    popup : property fields to show when a feature is clicked; if set, the layer is interactive.
        Pass ``[]`` for a non-interactive overlay (decoration only).
    edge_col / order_col / color_col : an overlay attached to edges (docs/design/edge_overlays.md): ``edge_col`` names the property
        with the id of the feature's edge (the ids of the roads' ``edge_id_col``), ``order_col`` the property with its order (whole
        number, lower first), ``color_col`` a property with a colour per feature. Each feature is drawn at the position of its edge's
        fill number, after the fills, by order; ``placement`` is not used.
    style / width_m / dash / min_zoom / max_zoom / text_col / text_size / text_color / text_halo : the look (docs/design/overlay_styles.md): ``style`` names a style that the caller
        passes in ``settings=`` (``config.overlays.styles``; roadstyle ships none), the other fields are its fields as arguments, which win over the style.
    tooltip : property fields to show in a HOVER tooltip (independent of ``popup``, exactly like
        the road layer's ``tooltip`` vs ``road_popup``). ``None``/``[]`` = hover only highlights.
    select : with ``edge_col``, what a hover or click on a feature picks: ``"road"`` (default) its road (the road's highlight, popup and
        ``rs:select``), ``"item"`` the feature itself (its own highlight and popup; ``rs:select`` carries it as ``item`` next to its road).
    width_m_col / offset_m_col : with ``edge_col`` and line features, in simple mode: the items are drawn IN the one road layer at their edge's
        fill (docs/design/edge_items.md), each with its own width and line-offset in metres from these properties (the width else ``width_m``).
    cap_col : with ``edge_col`` and line features, in simple mode: the property with each item's end shape, ``"round"`` (null too), ``"flat"``
        or ``"square"``; a dashed item is always flat.
    casing : with ``edge_col`` and line features, in simple mode: the items are drawn with the casings, at their edge's casing number (under
        every fill and item of that number), not after the fills: an outline of their own (a lane connector's casing).
    """
    data: object
    kind: str | None = None
    placement: str = "over"
    color: str | None = None           # None = the `overlays` settings default
    opacity: float | None = None
    outline: str | None = None
    radius: float | None = None
    width: float | None = None
    label: str | None = None
    popup: list[str] | None = None
    tooltip: list[str] | None = None
    visible: bool = True               # initial visibility (the Layers toggle starts checked/unchecked to match)
    edge_col: str | None = None        # the property with the id of the feature's edge: drawn at its edge's fill number (docs/design/edge_overlays.md)
    order_col: str | None = None       # with edge_col: the property with the feature's order (whole number, lower first; null = 0)
    color_col: str | None = None       # the property with a CSS colour per feature (null / missing: ``color``)
    style: str | None = None           # the name of a style in the settings ``config.overlays.styles`` (docs/design/overlay_styles.md); an argument given here wins over its field
    width_m: float | None = None       # a line's (or outline's) width in METRES, exact from ``min_zoom`` on; replaces ``width``
    dash: list | None = None           # a line's dash pattern, in line widths: [3, 3]
    min_zoom: float | None = None      # the zooms in which the overlay is drawn
    max_zoom: float | None = None
    text_col: str | None = None        # ``kind="text"``: the property that holds the text
    text_size: float | None = None     # px
    text_color: str | None = None
    text_halo: str | None = None       # the halo colour (none if absent)
    select: str = "road"               # with edge_col: a click picks its "road" or the "item" itself (docs/design/edge_items.md)
    width_m_col: str | None = None     # with edge_col, lines, simple mode: the property with each item's width in metres (else ``width_m``)
    offset_m_col: str | None = None    # with edge_col, lines, simple mode: the property with each item's line-offset in metres (right of the line's direction; null = 0)
    dash_col: str | None = None        # with edge_col, lines, simple mode: the property with each item's dash pattern in line widths ([3, 3] or "3,3"; null = ``dash``, else solid)
    cap_col: str | None = None         # with edge_col, lines, simple mode: the property with each item's end shape: "round" (null: round), "flat" or "square"
    casing: bool = False               # with edge_col, lines, simple mode: drawn with the casings (the edge's casing number), not after the fills

    def __post_init__(self):
        if self.select not in ("road", "item"):
            raise ValueError(f"Overlay select must be 'road' or 'item', not {self.select!r}")


def to_fc(data) -> dict:
    """Normalise overlay ``data`` to a GeoJSON FeatureCollection in EPSG:4326 (properties kept)."""
    if hasattr(data, "to_crs"):
        try:
            data = data.to_crs(4326)
        except Exception:
            pass
    if hasattr(data, "to_json"):                      # GeoDataFrame / GeoSeries -> clean JSON
        return json.loads(data.to_json())
    gj = data.__geo_interface__ if hasattr(data, "__geo_interface__") else data
    t = (gj or {}).get("type")
    if t == "FeatureCollection":
        return gj
    if t == "Feature":
        return {"type": "FeatureCollection", "features": [gj]}
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": gj}]}


def detect_kind(fc: dict) -> str:
    """Infer a draw kind from the first feature's geometry: polygon->fill, line->line, point->circle."""
    for ft in fc.get("features", []):
        t = ((ft.get("geometry") or {}).get("type") or "")
        if "Polygon" in t:
            return "fill"
        if "Line" in t:
            return "line"
        if "Point" in t:
            return "circle"
    return "fill"

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
    kind : ``"fill"`` | ``"line"`` | ``"circle"`` — defaults to auto-detect from the geometry.
    placement : ``"under"`` (below the roads — e.g. zone fills) or ``"over"`` (on top — e.g. POIs).
    color / opacity : the layer's paint colour and (kind-dependent) default opacity.
    outline : polygon outline colour (``fill`` only; defaults to ``color``).
    radius : circle radius in px (``circle`` only).
    width : line / outline width in px (``line`` / ``fill`` outline).
    label : the name shown in the *Layers* toggle (defaults to ``"Layer N"``).
    popup : property fields to show when a feature is clicked; if set, the layer is interactive.
        Pass ``[]`` for a non-interactive overlay (decoration only).
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
    visible: bool = True               # initial visibility (the Layers toggle starts checked/unchecked to match)


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

"""Render styled edges to an interactive folium (Leaflet) map.

Implements the "geometry sandwich": all casings are drawn first (one layer), then all
fills on top (second layer), so road borders never slice through higher-importance roads.
The road layers are always on (no toggle). Base maps use a thumbnail *switcher* control
(see controls.BaseLayerSwitcher), not the default Leaflet layer box.
"""
from __future__ import annotations

import json

from .basemaps import DEFAULT_SWITCHER, get_basemap
from .controls import BaseLayerSwitcher
from .interactive import InteractiveRoads
from .style import selection_style
from .themes import get_theme


def _shown_basemap(th, basemap, basemaps):
    """Which base map is shown initially (drives initial casing darkness)."""
    if basemap and not basemaps:
        return get_basemap(basemap)
    keys = list(basemaps) if basemaps else list(DEFAULT_SWITCHER)
    key = th.default_basemap if th.default_basemap in keys else keys[0]
    return get_basemap(key)


def _add_base(m, folium, th, basemap, basemaps):
    """Single fixed base map (``basemap=``) or a thumbnail switcher (default / ``basemaps=``)."""
    if basemap and not basemaps:
        bm = get_basemap(basemap)
        folium.TileLayer(tiles=bm.url, attr=bm.attr, name=bm.label, control=False,
                         subdomains=bm.subdomains, max_zoom=20).add_to(m)
        if bm.satellite:
            m.get_root().header.add_child(folium.Element(
                "<style>.leaflet-tile-pane{filter:saturate(.8) brightness(.9)}</style>"))
        return
    keys = list(basemaps) if basemaps else list(DEFAULT_SWITCHER)
    default_key = th.default_basemap if th.default_basemap in keys else keys[0]
    m.add_child(BaseLayerSwitcher(keys, default_key))


def _add_styled_layers(m, folium, g, styler, theme, fields):
    """Data-driven path: resolve per-edge styles and draw the casing+fill geometry sandwich.

    Each feature carries precomputed ``__rs_*`` properties; two GeoJson layers (casing under,
    fill over) read them via a style_function, so any styling mode renders the same way.
    """
    rf = styler.resolve_frame(g, theme)
    th = get_theme(theme)
    dark = th.casing == "dark"

    gj = json.loads(g.to_json())
    feats = gj.get("features", [])
    for i, feat in enumerate(feats):
        props = feat.setdefault("properties", {})
        casing = rf.casing_dark[i] if dark else rf.casing_light[i]
        props["__rs_fill"] = rf.fill[i]
        props["__rs_w"] = rf.width[i]
        props["__rs_op"] = rf.opacity[i]
        props["__rs_dash"] = rf.dash[i]
        props["__rs_casing"] = casing
        props["__rs_cw"] = rf.casing_width[i]
        props["__rs_cop"] = rf.casing_opacity[i]

    def casing_style(feat):
        p = feat["properties"]
        if not p.get("__rs_casing") or not p.get("__rs_cw"):
            return {"opacity": 0, "weight": 0}
        return {"color": p["__rs_casing"], "weight": p["__rs_cw"],
                "opacity": p["__rs_cop"], "lineCap": "round", "lineJoin": "round"}

    def fill_style(feat):
        p = feat["properties"]
        return {"color": p["__rs_fill"], "weight": p["__rs_w"], "opacity": p["__rs_op"],
                "dashArray": p.get("__rs_dash"), "lineCap": "round", "lineJoin": "round"}

    folium.GeoJson(gj, name="casing", control=False, style_function=casing_style).add_to(m)
    tip = folium.GeoJsonTooltip(fields=fields) if fields else None
    folium.GeoJson(gj, name="roads", control=False, style_function=fill_style,
                   tooltip=tip).add_to(m)
    return rf


def _add_legend(m, rf, position="bottomleft"):
    """Add a legend for a data-driven ResolvedFrame, if it carries legend metadata."""
    from .legend import make_legend

    leg = make_legend(getattr(rf, "legend", None), position=position)
    if leg is not None:
        m.add_child(leg)


def render(
    gdf,
    palette: str = "highsat",
    theme: str = "dark",
    highway_col: str = "highway",
    tunnel_col: str | None = "tunnel",
    bridge_col: str | None = "bridge",
    tooltip: list[str] | None = None,
    selected=None,
    name: str = "roads",
    basemap: str | None = None,
    basemaps: list[str] | None = None,
    filter_control: bool = True,
    styler=None,
    legend: bool = True,
    legend_position: str = "bottomleft",
    **map_kwargs,
):
    import folium

    th = get_theme(theme)
    g = gdf.to_crs(4326)

    m = folium.Map(tiles=None, **map_kwargs)
    _add_base(m, folium, th, basemap, basemaps)

    fields = tooltip if tooltip is not None else [c for c in g.columns if c != g.geometry.name]
    fields = [f for f in fields if f in g.columns]
    initial_dark = _shown_basemap(th, basemap, basemaps).is_dark

    if styler is None:
        # classic OSM path (unchanged): interactive road layer with dynamic casing,
        # hover highlight (edge -> white), and an in-map highway-type filter panel.
        m.add_child(InteractiveRoads(
            g.to_json(), palette=palette, highway_col=highway_col,
            tooltip=fields, initial_dark=initial_dark, show_filter=filter_control,
        ))
    else:
        # data-driven path: resolve per-edge styles, draw the casing+fill sandwich.
        rf = _add_styled_layers(m, folium, g, styler, theme, fields)
        if legend:
            _add_legend(m, rf, position=legend_position)

    # selected edges (neon-violet glow / casing / core, stacked on top)
    if selected is not None and len(selected):
        sel = selected.to_crs(4326).to_json()
        sty = selection_style(theme)
        for layer in ("glow", "casing", "core"):
            s = sty[layer]
            folium.GeoJson(
                sel, name=f"selected {layer}", control=False,
                style_function=(lambda c, w, o: (lambda f: {"color": c, "weight": w, "opacity": o}))(
                    s["color"], s["width"], s["opacity"]),
            ).add_to(m)

    try:
        b = g.total_bounds
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    except Exception:
        pass
    return m

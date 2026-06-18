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
from .stylers import bake_props, build_styler
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
    copy_field: str | None = "edge_id",
    arrows: bool = False,
    arrow_col: str | None = None,
    arrow_color: str = "#555555",     # gray
    arrow_size_m: float = 2.8,        # ~chevron barb length in metres (small, sits in-road)
    arrow_min_zoom: int | None = 18,  # zoom-gate: only render arrows at street-level zoom
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

    # One folium path: resolve a styler (default = OSM class styling) → bake the per-edge __rs_*
    # props → a single InteractiveRoads layer that reads them (dynamic casing, hover highlight,
    # click-to-pin + copy). A class styler carries no legend, so it gets the road-type filter
    # panel; categorical / numeric stylers carry a legend instead.
    if styler is None:
        styler = build_styler(palette=palette, highway_col=highway_col)
    rf = styler.resolve_frame(g, theme)
    gj = bake_props(json.loads(g.to_json()), rf, th.casing == "dark")
    has_legend = getattr(rf, "legend", None) is not None
    m.add_child(InteractiveRoads(
        json.dumps(gj), tooltip=fields, initial_dark=initial_dark,
        show_filter=filter_control and not has_legend,
        copy_field=(copy_field if copy_field and copy_field in g.columns else None),
    ))
    if legend and has_legend:
        _add_legend(m, rf, position=legend_position)

    # selected edges (neon-violet glow / casing / core, stacked on top)
    if selected is not None and len(selected):
        sel = selected.to_crs(4326).to_json()
        sty = selection_style(theme)
        for layer in ("glow", "casing", "core"):
            s = sty[layer]
            folium.GeoJson(
                sel, name=f"selected {layer}", control=False,
                style_function=(
                    lambda c, w, o: (lambda f: {"color": c, "weight": w, "opacity": o})
                )(s["color"], s["width"], s["opacity"]),
            ).add_to(m)

    # direction arrows (source->target chevrons), drawn as one cheap GeoJSON line layer
    if arrows:
        from .arrows import chevron_features

        fc = chevron_features(g, where_col=arrow_col, size_m=arrow_size_m)
        if fc["features"]:
            gj = folium.GeoJson(
                fc, name="direction", control=False,
                style_function=(lambda c: (lambda f: {"color": c, "weight": 2, "opacity": 0.9}))(arrow_color),
            )
            gj.add_to(m)
            if arrow_min_zoom is not None:
                _zoom_gate(m, gj, int(arrow_min_zoom))

    try:
        b = g.total_bounds
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    except Exception:
        pass
    return m


def _zoom_gate(m, layer, min_zoom):
    """Show `layer` only at map zoom >= min_zoom (keeps the zoomed-out view clean and light)."""
    from branca.element import MacroElement
    from jinja2 import Template

    el = MacroElement()
    el._template = Template(
        "{% macro script(this, kwargs) %}\n"
        "  var _zmap = {{ this._parent.get_name() }};\n"
        "  var _zlyr = " + layer.get_name() + ";\n"
        "  function _zvis() {\n"
        "    if (_zmap.getZoom() >= " + str(min_zoom) + ") {\n"
        "      if (!_zmap.hasLayer(_zlyr)) _zmap.addLayer(_zlyr);\n"
        "    } else if (_zmap.hasLayer(_zlyr)) { _zmap.removeLayer(_zlyr); }\n"
        "  }\n"
        "  _zmap.on('zoomend', _zvis); _zvis();\n"
        "{% endmacro %}"
    )
    m.add_child(el)

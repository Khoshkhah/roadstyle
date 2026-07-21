"""Render styled edges to an interactive folium (Leaflet) map.

Implements the "geometry sandwich": all casings are drawn first (one layer), then all
fills on top (second layer), so road borders never slice through higher-importance roads.
The road layers are always on (no toggle). Base maps use a thumbnail *switcher* control
(see controls.BaseLayerSwitcher), not the default Leaflet layer box.
"""
from __future__ import annotations

import json

from .config import DEFAULT as CONFIG
from .basemaps import DEFAULT_SWITCHER, get_basemap
from .controls import BaseLayerSwitcher
from .interactive import InteractiveRoads
from .style import selection_style
from .stylers import bake_props, build_styler


def _add_base(m, folium, basemap, basemaps):
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
    default_key = CONFIG.basemap if CONFIG.basemap in keys else keys[0]
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
    **map_kwargs,
):
    import folium

    # web-backend-only UI kwargs may arrive via render_edges(**kwargs); drop them so they don't
    # reach folium.Map() (folium has its own filter_control / legend).
    for _k in ("arrows", "labels", "basemap_switcher"):
        map_kwargs.pop(_k, None)

    g = gdf.to_crs(4326)

    m = folium.Map(tiles=None, **map_kwargs)
    _add_base(m, folium, basemap, basemaps)

    fields = tooltip if tooltip is not None else [c for c in g.columns if c != g.geometry.name]
    fields = [f for f in fields if f in g.columns]

    # One folium path: resolve a styler (default = OSM class styling) → bake the per-edge __rs_*
    # props → a single InteractiveRoads layer that reads them (dynamic casing, hover highlight,
    # click-to-pin + copy). A class styler carries no legend, so it gets the road-type filter
    # panel; categorical / numeric stylers carry a legend instead.
    if styler is None:
        styler = build_styler(palette=palette, highway_col=highway_col)
    rf = styler.resolve_frame(g)
    gj = bake_props(json.loads(g.to_json()), rf)
    has_legend = getattr(rf, "legend", None) is not None
    m.add_child(InteractiveRoads(
        json.dumps(gj), tooltip=fields,
        show_filter=filter_control and not has_legend,
        copy_field=(copy_field if copy_field and copy_field in g.columns else None),
    ))
    if legend and has_legend:
        _add_legend(m, rf, position=legend_position)

    # selected edges (neon-violet glow / casing / core, stacked on top)
    if selected is not None and len(selected):
        sel = selected.to_crs(4326).to_json()
        sty = selection_style()
        for layer in ("glow", "casing", "core"):
            s = sty[layer]
            folium.GeoJson(
                sel, name=f"selected {layer}", control=False,
                style_function=(
                    lambda c, w, o: (lambda f: {"color": c, "weight": w, "opacity": o})
                )(s["color"], s["width"], s["opacity"]),
            ).add_to(m)

    try:
        b = g.total_bounds
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    except Exception:
        pass
    return m

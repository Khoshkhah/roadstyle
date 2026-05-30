"""Output / emit layer — turn styled edges into web-ready artifacts.

One core function, :func:`to_spec`, produces the **canonical JSON interchange**: the normalized
road data *plus* the baked-in resolved style (per-edge colours/widths) *plus* legend and basemap
metadata. It is stack-agnostic — any frontend (Leaflet, MapLibre GL, deck.gl) can render it.
Everything else is a thin wrapper:

- :func:`to_geojson` — just the styled ``FeatureCollection`` from the spec.
- :func:`save_spec` / :func:`load_spec` — round-trip the spec to a ``.json`` file.
- :func:`to_html` — a full HTML page (``full=True``) or an embeddable ``<div>+<script>`` fragment.
- :func:`to_iframe` — the full page wrapped in an ``<iframe srcdoc=...>``.
- :func:`save` — write a standalone HTML file.

Each styled feature carries reserved properties: ``__rs_fill``, ``__rs_w`` (width px),
``__rs_op`` (fill opacity), ``__rs_dash``, ``__rs_casing``, ``__rs_cw`` (casing width),
``__rs_cop`` (casing opacity), ``__rs_class``.
"""
from __future__ import annotations

import json

from .edges import as_edges
from .stylers import build_styler
from .themes import get_theme

SPEC_VERSION = "1"


def to_spec(
    gdf,
    *,
    theme: str = "dark",
    palette: str = "highsat",
    highway_col: str = "highway",
    style=None,
    color_by: str | None = None,
    colors=None,
    cmap=None,
    vmin: float | None = None,
    vmax: float | None = None,
    width_by=None,
    basemap: str | None = None,
    tooltip: list[str] | None = None,
) -> dict:
    """Build the canonical JSON spec (data + baked-in resolved style + legend + metadata).

    Returns a plain ``dict`` ready for ``json.dump``. The styling arguments mirror
    :func:`roadstyle.render_edges`; the default (no data-driven args) bakes the OSM class style.
    """
    from .basemaps import get_basemap

    edges = as_edges(gdf, class_col=highway_col)
    g = edges.gdf
    col = edges.class_col

    styler = build_styler(
        style=style, palette=palette, highway_col=col,
        color_by=color_by, colors=colors, cmap=cmap,
        vmin=vmin, vmax=vmax, width_by=width_by,
    )
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
        props["__rs_class"] = rf.klass[i]

    b = list(g.total_bounds)   # [minx, miny, maxx, maxy]
    bounds = [[b[1], b[0]], [b[3], b[2]]]   # [[S,W],[N,E]] (Leaflet order)

    bm = get_basemap(basemap or th.default_basemap)
    fields = tooltip if tooltip is not None else [c for c in g.columns if c != g.geometry.name]
    fields = [f for f in fields if f in g.columns]

    return {
        "roadstyle": f"spec/{SPEC_VERSION}",
        "crs": "EPSG:4326",
        "theme": th.name,
        "bounds": bounds,
        "render": {"sandwich": True, "line_cap": "round", "line_join": "round"},
        "basemap": {"key": bm.key, "label": bm.label, "url": bm.url, "attr": bm.attr,
                    "is_dark": bm.is_dark, "subdomains": bm.subdomains},
        "tooltip": fields,
        "legend": getattr(rf, "legend", None),
        "geojson": gj,
    }


def to_geojson(gdf, **kw) -> dict:
    """Return just the styled GeoJSON ``FeatureCollection`` (features carry ``__rs_*`` props)."""
    return to_spec(gdf, **kw)["geojson"]


def save_spec(spec_or_gdf, path, **kw) -> None:
    """Write a spec to a JSON file. Accepts a prebuilt spec dict or a GeoDataFrame (+ style kw)."""
    spec = spec_or_gdf if _is_spec(spec_or_gdf) else to_spec(spec_or_gdf, **kw)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh)


def load_spec(path) -> dict:
    """Load a canonical spec JSON file written by :func:`save_spec`."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _is_spec(obj) -> bool:
    return isinstance(obj, dict) and "geojson" in obj and "roadstyle" in obj


# ── HTML rendering (self-contained Leaflet page that consumes a spec) ──────────────────────────

_FRAGMENT = """\
<div id="{div_id}" style="width:{width};height:{height};"></div>
<script>
(function(){{
  var spec = {spec_json};
  function start(){{
    var map = L.map("{div_id}");
    var bm = spec.basemap || {{}};
    if (bm.url) L.tileLayer(bm.url, {{attribution: bm.attr || "", subdomains: bm.subdomains || "abc", maxZoom: 20}}).addTo(map);
    function casingStyle(f){{ var p=f.properties; if(!p.__rs_casing||!p.__rs_cw) return {{opacity:0,weight:0}};
      return {{color:p.__rs_casing, weight:p.__rs_cw, opacity:p.__rs_cop, lineCap:"round", lineJoin:"round"}}; }}
    function fillStyle(f){{ var p=f.properties;
      return {{color:p.__rs_fill, weight:p.__rs_w, opacity:p.__rs_op, dashArray:p.__rs_dash, lineCap:"round", lineJoin:"round"}}; }}
    L.geoJSON(spec.geojson, {{style:casingStyle}}).addTo(map);     // casing under
    var tip = spec.tooltip || [];
    L.geoJSON(spec.geojson, {{style:fillStyle, onEachFeature:function(ft,l){{    // fill over
      if(tip.length) l.bindTooltip(tip.map(function(k){{return "<b>"+k+"</b>: "+(ft.properties[k]==null?"":ft.properties[k]);}}).join("<br>"), {{sticky:true}});
    }}}}).addTo(map);
    if (spec.bounds) map.fitBounds(spec.bounds);
    {legend_js}
  }}
  if (window.L) start(); else {{
    var c=document.createElement("link"); c.rel="stylesheet"; c.href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"; document.head.appendChild(c);
    var s=document.createElement("script"); s.src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"; s.onload=start; document.head.appendChild(s);
  }}
}})();
</script>
"""

_PAGE = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>roadstyle map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body{{margin:0;height:100%}} #wrap{{height:100%}} {legend_css}</style>
</head><body><div id="wrap">{fragment}</div></body></html>
"""

_LEGEND_CSS = """
.rs-legend{position:absolute;z-index:9999;background:rgba(20,24,30,.82);border-radius:12px;
 padding:9px 11px;box-shadow:0 3px 14px rgba(0,0,0,.45);font:600 11px/1.4 system-ui,sans-serif;color:#cfd6dd;}
.rs-legend h4{margin:0 0 6px;font-size:10px;letter-spacing:.4px;color:#9fb0bf;text-transform:uppercase;}
.rs-legend .rs-row{display:flex;align-items:center;gap:7px;padding:1px 0;white-space:nowrap;}
.rs-legend .rs-sw{width:16px;height:6px;border-radius:2px;display:inline-block;flex:none;}
.rs-legend .rs-bar{height:10px;border-radius:3px;margin:2px 0 3px;}
.rs-legend .rs-ends{display:flex;justify-content:space-between;font-weight:500;color:#aeb8c2;}
"""


def _legend_js(legend: dict | None) -> str:
    """JS that injects a legend panel into the map container, from a legend spec."""
    if not legend:
        return ""
    payload = json.dumps(legend)
    return """
    var lg = %s;
    if (lg) {
      var d = L.DomUtil.create("div","rs-legend"); d.style.left="14px"; d.style.bottom="22px";
      var html = lg.title ? "<h4>"+lg.title+"</h4>" : "";
      if (lg.kind==="categorical") { (lg.entries||[]).forEach(function(e){ html+='<div class="rs-row"><span class="rs-sw" style="background:'+e[1]+'"></span>'+e[0]+'</div>'; }); }
      else if (lg.kind==="continuous") { html+='<div class="rs-bar" style="min-width:140px;background:linear-gradient(90deg,'+(lg.ramp||[]).join(",")+');"></div><div class="rs-ends"><span>'+lg.vmin+'</span><span>'+lg.vmax+'</span></div>'; }
      d.innerHTML = html; map.getContainer().appendChild(d);
    }
    """ % payload


def to_html(gdf_or_spec, *, full: bool = True, div_id: str = "rsmap",
            width: str = "100%", height: str = "500px", **kw) -> str:
    """Render the spec to HTML. ``full=True`` → a complete page; ``full=False`` → a
    ``<div>+<script>`` fragment to inject into an existing page (auto-loads Leaflet if absent)."""
    spec = gdf_or_spec if _is_spec(gdf_or_spec) else to_spec(gdf_or_spec, **kw)
    fragment = _FRAGMENT.format(
        div_id=div_id, width=width, height=height,
        spec_json=json.dumps(spec), legend_js=_legend_js(spec.get("legend")),
    )
    if not full:
        return fragment
    return _PAGE.format(fragment=fragment, legend_css=_LEGEND_CSS)


def to_iframe(gdf_or_spec, *, width: str = "100%", height: str = "500px", **kw) -> str:
    """Return an ``<iframe srcdoc=...>`` embedding a full self-contained map page."""
    page = to_html(gdf_or_spec, full=True, height="100%", **kw)
    esc = page.replace("&", "&amp;").replace('"', "&quot;")
    return (f'<iframe srcdoc="{esc}" style="width:{width};height:{height};border:0;" '
            f'loading="lazy"></iframe>')


def save(gdf_or_spec, path, **kw) -> None:
    """Write a standalone interactive HTML map file."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_html(gdf_or_spec, full=True, **kw))

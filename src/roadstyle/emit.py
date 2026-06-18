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
from functools import cache
from importlib.resources import files

from .edges import as_edges
from .stylers import build_styler
from .themes import get_theme

SPEC_VERSION = "1"


@cache
def _asset(name: str) -> str:
    """Read a bundled static asset (the canonical ``roadstyle.js`` / ``roadstyle.css``).

    This is the single source of truth for the browser renderer: ``to_html`` inlines the *same*
    file you would drop into a page on its own, so there is never a second copy to drift.
    """
    return (files("roadstyle") / "static" / name).read_text(encoding="utf-8")


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


# ── HTML rendering ────────────────────────────────────────────────────────────────────────────
# These wrappers inline the **canonical** browser renderer (``static/roadstyle.js`` +
# ``static/roadstyle.css``) — the exact same file you can drop into a page on its own. There is no
# second, hand-written copy of the rendering logic here, so the two can never drift.

_LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
_LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"


def _fragment_html(spec: dict, div_id: str, width: str, height: str) -> str:
    """A container div + the canonical CSS/JS + a tiny bootstrap on the embedded spec.

    Built by concatenation (not ``str.format``) because the inlined ``roadstyle.js`` source is full
    of literal ``{``/``}`` braces.
    """
    spec_json = json.dumps(spec)
    boot = (
        "(function(){var spec=" + spec_json + ";"
        'function start(){'
        'new RoadStyleMap("' + div_id + '",{widgets:{legend:true,filter:true}}).load(spec);}'
        "if(window.L){start();}else{"
        'var c=document.createElement("link");c.rel="stylesheet";c.href="' + _LEAFLET_CSS
        + '";document.head.appendChild(c);'
        'var s=document.createElement("script");s.src="' + _LEAFLET_JS
        + '";s.onload=start;document.head.appendChild(s);}})();'
    )
    return (
        '<div id="' + div_id + '" style="width:' + width + ";height:" + height + ';"></div>\n'
        "<style>" + _asset("roadstyle.css") + "</style>\n"
        "<script>" + _asset("roadstyle.js") + "</script>\n"
        "<script>" + boot + "</script>\n"
    )


def to_html(gdf_or_spec, *, full: bool = True, div_id: str = "rsmap",
            width: str = "100%", height: str = "500px", **kw) -> str:
    """Render the spec to HTML. ``full=True`` → a complete page; ``full=False`` → a
    ``<div>+<script>`` fragment to inject into an existing page (auto-loads Leaflet if absent).

    Both forms inline the canonical ``static/roadstyle.js`` renderer, so a generated map exercises
    the very code a standalone embed would use.
    """
    spec = gdf_or_spec if _is_spec(gdf_or_spec) else to_spec(gdf_or_spec, **kw)
    fragment = _fragment_html(spec, div_id=div_id, width=width, height=height)
    if not full:
        return fragment
    return (
        "<!DOCTYPE html>\n"
        '<html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>roadstyle map</title>\n"
        '<link rel="stylesheet" href="' + _LEAFLET_CSS + '"/>\n'
        '<script src="' + _LEAFLET_JS + '"></script>\n'
        "<style>html,body{margin:0;height:100%} #wrap{height:100%}</style>\n"
        "</head><body><div id=\"wrap\">" + fragment + "</div></body></html>\n"
    )


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

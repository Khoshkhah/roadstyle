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
from collections.abc import Mapping
from functools import cache
from importlib.resources import files

from .edges import as_edges
from .stylers import bake_color_options, bake_props, build_styler, option_styler
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
    theme: str = "light",
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
    basemaps: list[str] | None = None,
    tooltip: list[str] | None = None,
    color_options=None,
) -> dict:
    """Build the canonical JSON spec (data + baked-in resolved style + legend + metadata).

    Returns a plain ``dict`` ready for ``json.dump``. The styling arguments mirror
    :func:`roadstyle.render_edges`; the default (no data-driven args) bakes the OSM class style.

    ``basemap`` picks the *active* base map (else the theme default); ``basemaps`` is the list of
    keys offered to the in-map base-layer switcher (default :data:`DEFAULT_SWITCHER`). Both casing
    colours are baked per edge, so a light/dark base-map switch re-picks the casing client-side.

    ``color_options`` enables **client-side recolouring**: pass an ordered mapping of
    ``{name: {styler kwargs}}`` (or a list of ``{"name": ..., **kwargs}``) and each option's fill
    is pre-resolved and baked as a separate per-edge prop. The first option is the active one (it
    also drives the shared width/casing/class), and the browser swaps colours between them with no
    re-render. A neutral base reads best — pair the class option with ``palette="mono"`` so the
    data ramps stand out, e.g.::

        color_options={"Class": {}, "AADT": {"color_by": "aadt", "cmap": "viridis"}}, palette="mono"
    """
    from .basemaps import DEFAULT_SWITCHER, get_basemap

    edges = as_edges(gdf, class_col=highway_col)
    g = edges.gdf
    col = edges.class_col
    th = get_theme(theme)
    dark = th.casing == "dark"

    color_opts_meta = None
    if color_options:
        # one pre-resolved fill set per "colour by" option; option 0 is active (drives the shared
        # width/casing/class via bake_props), the rest bake only their fill under __rs_fill__<i>.
        items = (list(color_options.items()) if isinstance(color_options, Mapping)
                 else [(o["name"], {k: v for k, v in o.items() if k != "name"})
                       for o in color_options])
        frames = [(name, option_styler(col, palette, opts).resolve_frame(g, theme))
                  for name, opts in items]
        rf = frames[0][1]                                  # active option drives spec["legend"]
        gj, color_opts_meta = bake_color_options(json.loads(g.to_json()), frames, dark)
    else:
        styler = build_styler(
            style=style, palette=palette, highway_col=col,
            color_by=color_by, colors=colors, cmap=cmap,
            vmin=vmin, vmax=vmax, width_by=width_by,
        )
        rf = styler.resolve_frame(g, theme)
        # bake the per-edge __rs_* props (both casing variants for the in-map base-layer switcher)
        gj = bake_props(json.loads(g.to_json()), rf, dark)

    b = list(g.total_bounds)   # [minx, miny, maxx, maxy]
    bounds = [[b[1], b[0]], [b[3], b[2]]]   # [[S,W],[N,E]] (Leaflet order)

    bm = get_basemap(basemap or th.default_basemap)
    # Selectable base layers for the in-map switcher; the active `bm` is always present and first.
    keys = list(basemaps) if basemaps else list(DEFAULT_SWITCHER)
    if bm.key not in keys:
        keys = [bm.key, *keys]
    options = [_basemap_dict(get_basemap(k)) for k in keys]

    fields = tooltip if tooltip is not None else [c for c in g.columns if c != g.geometry.name]
    fields = [f for f in fields if f in g.columns]

    spec = {
        "roadstyle": f"spec/{SPEC_VERSION}",
        "crs": "EPSG:4326",
        "theme": th.name,
        "bounds": bounds,
        "render": {"sandwich": True, "line_cap": "round", "line_join": "round", "deadend_cap": "butt"},
        "basemap": _basemap_dict(bm),       # the active base map
        "basemaps": options,                # all base maps offered to the switcher
        "tooltip": fields,
        "legend": getattr(rf, "legend", None),
        "geojson": gj,
    }
    if color_opts_meta is not None:
        spec["color_options"] = color_opts_meta   # client-side recolour: name/prop/legend per option
        spec["color_active"] = 0
    return spec


def _basemap_dict(bm) -> dict:
    """Serialise a :class:`roadstyle.Basemap` to the spec JSON shape read by ``roadstyle.js``."""
    return {"key": bm.key, "label": bm.label, "url": bm.url, "attr": bm.attr,
            "is_dark": bm.is_dark, "satellite": bm.satellite, "subdomains": bm.subdomains}


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

# jsDelivr (npm mirror) — the same Leaflet CDN folium uses; unpkg is more often blocked/unreachable.
_LEAFLET_CSS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"
_LEAFLET_JS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"


def _inline_script(content: str) -> str:
    """Wrap JS in a ``<script>`` tag, neutralising any literal ``</script>`` inside it.

    The inlined ``roadstyle.js`` header carries a usage example containing ``</script>`` (and, in
    principle, string data in the embedded spec could too). Left raw, that sequence closes the
    page's inline ``<script>`` early — the rest of the renderer then spills onto the page as text
    and never runs. ``<\\/script`` is the standard escape: valid JS, inert to the HTML parser.
    """
    return "<script>" + content.replace("</script", "<\\/script") + "</script>\n"


def _fragment_html(spec: dict, div_id: str, width: str, height: str) -> str:
    """A container div + the canonical CSS/JS + a tiny bootstrap on the embedded spec.

    Built by concatenation (not ``str.format``) because the inlined ``roadstyle.js`` source is full
    of literal ``{``/``}`` braces.
    """
    spec_json = json.dumps(spec)
    # With recolour options present, offer the "colour by" picker (and drop the class filter, which
    # shares the top-right corner); otherwise keep the default class filter.
    has_co = bool(spec.get("color_options"))
    widgets = ("{legend:true,filter:%s,basemap:true,colors:%s}"
               % ("false" if has_co else "true", "true" if has_co else "false"))
    boot = (
        "(function(){var spec=" + spec_json + ";"
        "var opts={widgets:" + widgets + "};"
        'function start(){new RoadStyleMap("' + div_id + '",opts).load(spec);}'
        "if(window.L){start();}else{"
        'var c=document.createElement("link");c.rel="stylesheet";c.href="' + _LEAFLET_CSS
        + '";document.head.appendChild(c);'
        'var s=document.createElement("script");s.src="' + _LEAFLET_JS
        + '";s.onload=start;document.head.appendChild(s);}})();'
    )
    return (
        '<div id="' + div_id + '" style="width:' + width + ";height:" + height + ';"></div>\n'
        "<style>" + _asset("roadstyle.css") + "</style>\n"
        + _inline_script(_asset("roadstyle.js"))
        + _inline_script(boot)
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

"""One-call **dashboard** / **report** / **street view** pages.

Each renders the styled road map with the built-in map controls off and a bundled sidebar template
injected on top, wired to the map only through the public ``window.rs*`` API. The sidebars ship
inside the package (``roadstyle/templates/{dashboard,report,street_view}.html``), so ``pip install roadstyle``
can build these pages with no repo checkout::

    import geopandas as gpd, roadstyle as rs
    edges = gpd.read_file("edges.gpkg")
    rs.render_dashboard(edges, color_options={"Class": {},
                                              "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"}}
                       ).save("dashboard.html")
    rs.render_report(edges).save("report.html")
    rs.render_street_view(edges).save("street_view.html")

All three return a :class:`~roadstyle.render_web.WebMap` — ``.save(path)`` writes the self-contained
page, and it previews inline in a notebook. Every :func:`~roadstyle.render_edges` keyword passes
through (``color_options=`` populates the sidebar's *Colour by* picker); the injected sidebar is
plain HTML/CSS/JS, safe to copy out and reshape.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .render import render_edges


def sidebar_html(name: str) -> str:
    """The bundled sidebar template (``"dashboard"``, ``"report"`` or ``"street_view"``) as an HTML
    string — the exact fragment the matching ``render_*`` page injects. Handy to tweak and re-inject."""
    from importlib.resources import files
    return (files("roadstyle") / "templates" / f"{name}.html").read_text(encoding="utf-8")


def _page(gdf, template: str, *, defaults: dict, edit=None, **kw):
    kw.pop("backend", None)                       # web only — the sidebars drive a MapLibre map
    for k, v in defaults.items():
        kw.setdefault(k, v)
    m = render_edges(gdf, backend="web", **kw)
    # `name=` is the page title: besides the <title> tag (via render_edges), show it as the
    # sidebar's <h2> heading — the template ships with a placeholder heading.
    import html
    import re
    frag = re.sub(r"<h2>.*?</h2>", f"<h2>{html.escape(str(kw['name']))}</h2>",
                  sidebar_html(template), count=1)
    if edit:
        frag = edit(frag)
    # inject before the MapLibre placeholders resolve, so BOTH .html (the saved page) and the
    # notebook preview (_repr_html_) carry the sidebar
    m._tpl = m._tpl.replace("</body>", frag + "</body>", 1)
    return m


_LAYOUT_DIR = Path(__file__).resolve().parent / "static" / "dashboard_layout"


def _with_layout(m, layout, toolbar):
    """Add the overlay layout and the toolbar of a dashboard page (docs/guides/dashboard-layout.md): a style and a script before </body>."""
    import json
    if layout not in ("dock", "overlay"):
        raise ValueError(f"layout must be 'dock' or 'overlay', not {layout!r}")
    if toolbar not in (False, None, "right", "left", "top", "bottom"):
        raise ValueError(f"toolbar must be False, 'right', 'left', 'top' or 'bottom', not {toolbar!r}")
    if layout == "dock" and not toolbar:
        return m
    css = (_LAYOUT_DIR / "layout.css").read_text(encoding="utf-8")
    js = (_LAYOUT_DIR / "layout.js").read_text(encoding="utf-8")
    opt = json.dumps({"layout": layout, "toolbar": toolbar or False})
    # the style, the options and an empty bar are the first things of the body, so that the first paint has the layout and no old control column:
    # the class on <html> hides the column from the start, and the script at the end of the body fills the bar
    cls = ("rs-overlay " if layout == "overlay" else "") + ("rs-has-toolbar" if toolbar else "")
    bar = f'<div id="rs-toolbar" class="rs-tb-{toolbar}"></div>' if toolbar else ""
    head = (f"<style>{css}</style><script>window.rsLayout={opt};document.documentElement.className+=' {cls}';</script>" + bar)
    assert "<body" in m._tpl, "the page has no body"
    i = m._tpl.index(">", m._tpl.index("<body")) + 1
    m._tpl = m._tpl[:i] + head + m._tpl[i:]
    m._tpl = m._tpl.replace("</body>", f"<script>{js}</script></body>", 1)
    return m


def render_dashboard(gdf, *, layout="dock", toolbar=False, **kw):
    """A self-contained **dashboard** page: the styled map with every built-in control off and the
    bundled dashboard sidebar injected — base-map + colour-by selects, a class filter with a legend,
    a WHERE-clause query box with a result table, and a selected-road read-out.

    Populate the *Colour by* picker with ``color_options={...}`` (see :func:`render_edges`); any
    other ``render_edges`` keyword passes through. Returns a :class:`WebMap`;
    ``.save("dashboard.html")`` writes the page.

    ``layout="overlay"``: the map fills the window and the panels float over it (default ``"dock"``: the
    panels take their own space). ``toolbar="right"|"left"|"top"|"bottom"``: the map's controls on one
    bar at that edge (default ``False``: the plain control column). See docs/guides/dashboard-layout.md."""
    return _with_layout(_page(gdf, "dashboard",
                              defaults=dict(name="Roads dashboard", basemap_switcher=False,
                                            filter_control=False, road_popup=False), **kw), layout, toolbar)


def render_report(gdf, **kw):
    """A self-contained **report** page: the styled map with a stats-forward sidebar — headline KPI
    cards, the active colour-by legend, a checkbox filter (overlay layers + road types), search, and
    a selected-road read-out. The base map keeps its own on-map switcher.

    Same ``color_options=`` / ``render_edges`` keywords as :func:`render_dashboard`. Returns a
    :class:`WebMap`; ``.save("report.html")`` writes the page."""
    return _page(gdf, "report",
                 defaults=dict(name="Roads report", basemap_switcher=True,
                               filter_control=False, road_popup=False), **kw)


def render_street_view(gdf, *, panel_width: float = 42, resizable: bool = True,
                       layout: str = "beside", street_view_key: str | None = None, **kw):
    """A self-contained **map + Google Street View** page: the styled map on the left, Street View
    on the right (under the map on a phone). Clicking a road shows Street View at that point,
    looking the way the clicked edge runs, so a two-way road's two edges look opposite ways. No
    new window and no API key (it embeds Google's "Share > Embed a map" URL form).

    ``layout="beside"`` puts Street View next to the map (right), ``"below"`` under it; both have
    the draggable divider. ``panel_width`` is Street View's share of the window in percent (20-80):
    of its width, or of its height when below.
    ``street_view_key`` is a Google **Maps JavaScript API** key. Without it the panel is Google's
    keyless embed, which cannot say where the viewer walks. With it the panel is a real panorama:
    the map marker follows every step and turn inside it, and it shows Google's own street imagery
    only (the embed also shows people's indoor photos). The key is written into the page, as every
    browser key is - restrict it to your site's addresses in the Google Cloud console. Default: the
    environment variable ``GOOGLE_MAPS_KEY``.
    ``resizable=True`` adds a divider the viewer can drag to change it (their choice is remembered
    in their browser); ``False`` fixes the width. Any :func:`render_edges` keyword passes through.
    Returns a :class:`WebMap`; ``.save("street_view.html")`` writes the page."""
    if layout not in ("beside", "below"):
        raise ValueError(f'layout must be "beside" or "below", got {layout!r}')
    if not 20 <= panel_width <= 80:
        raise ValueError(f"panel_width must be 20-80 (percent of the window), got {panel_width}")

    def edit(frag):
        frag = frag.replace("--sv-w: 42%;", f"--sv-w: {panel_width:g}%;", 1)
        frag = frag.replace("__SV_KEY__", json.dumps(street_view_key or os.environ.get("GOOGLE_MAPS_KEY") or ""), 1)
        if layout == "below":
            frag = frag.replace('<div id="sv" data-layout="beside">', '<div id="sv" data-layout="below">', 1)
        if not resizable:
            frag = frag.replace('<div id="sv-drag" title="Drag to resize"></div>\n', "", 1)
        return frag
    return _page(gdf, "street_view", edit=edit,
                 # the panel IS the Street View; the map's own button would be a second one
                 defaults=dict(name="Roads and Street View", road_popup=False, street_view=True), **kw)

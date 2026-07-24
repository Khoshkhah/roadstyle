"""One-call **dashboard** / **report** pages.

Each renders the styled road map with the built-in map controls off and a bundled sidebar template
injected on top, wired to the map only through the public ``window.rs*`` API. The sidebars ship
inside the package (``roadstyle/templates/{dashboard,report}.html``), so ``pip install roadstyle``
can build these pages with no repo checkout::

    import geopandas as gpd, roadstyle as rs
    edges = gpd.read_file("edges.gpkg")
    rs.render_dashboard(edges, color_options={"Class": {},
                                              "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"}}
                       ).save("dashboard.html")
    rs.render_report(edges).save("report.html")

Both return a :class:`~roadstyle.render_web.WebMap` — ``.save(path)`` writes the self-contained
page, and it previews inline in a notebook. Every :func:`~roadstyle.render_edges` keyword passes
through (``color_options=`` populates the sidebar's *Colour by* picker); the injected sidebar is
plain HTML/CSS/JS, safe to copy out and reshape.
"""
from __future__ import annotations

from .render import render_edges


def sidebar_html(name: str) -> str:
    """The bundled sidebar template (``"dashboard"`` or ``"report"``) as an HTML string — the exact
    fragment :func:`render_dashboard` / :func:`render_report` inject. Handy to tweak and re-inject."""
    from importlib.resources import files
    return (files("roadstyle") / "templates" / f"{name}.html").read_text(encoding="utf-8")


def _page(gdf, template: str, *, defaults: dict, **kw):
    kw.pop("backend", None)                       # web only — the sidebars drive a MapLibre map
    for k, v in defaults.items():
        kw.setdefault(k, v)
    m = render_edges(gdf, backend="web", **kw)
    # inject before the MapLibre placeholders resolve, so BOTH .html (the saved page) and the
    # notebook preview (_repr_html_) carry the sidebar
    m._tpl = m._tpl.replace("</body>", sidebar_html(template) + "</body>", 1)
    return m


def render_dashboard(gdf, **kw):
    """A self-contained **dashboard** page: the styled map with every built-in control off and the
    bundled dashboard sidebar injected — base-map + colour-by selects, a class filter with a legend,
    a WHERE-clause query box with a result table, and a selected-road read-out.

    Populate the *Colour by* picker with ``color_options={...}`` (see :func:`render_edges`); any
    other ``render_edges`` keyword passes through. Returns a :class:`WebMap`;
    ``.save("dashboard.html")`` writes the page."""
    return _page(gdf, "dashboard",
                 defaults=dict(name="Roads dashboard", basemap_switcher=False,
                               filter_control=False, road_popup=False), **kw)


def render_report(gdf, **kw):
    """A self-contained **report** page: the styled map with a stats-forward sidebar — headline KPI
    cards, the active colour-by legend, a checkbox filter (overlay layers + road types), search, and
    a selected-road read-out. The base map keeps its own on-map switcher.

    Same ``color_options=`` / ``render_edges`` keywords as :func:`render_dashboard`. Returns a
    :class:`WebMap`; ``.save("report.html")`` writes the page."""
    return _page(gdf, "report",
                 defaults=dict(name="Roads report", basemap_switcher=True,
                               filter_control=False, road_popup=False), **kw)

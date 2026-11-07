"""One-call **dashboard** / **street view** pages.

Each renders the styled road map (with the defaults of a map page) and a bundled panel template
on top, wired to the map only through the public ``window.rs*`` API. The sidebars ship
inside the package (``roadstyle/templates/{dashboard,street_view}.html``), so ``pip install roadstyle``
can build these pages with no repo checkout::

    import geopandas as gpd, roadstyle as rs
    edges = gpd.read_file("edges.gpkg")
    rs.render_dashboard(edges, color_options={"Class": {},
                                              "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"}}
                       ).save("dashboard.html")
    rs.render_street_view(edges).save("street_view.html")

Both return a :class:`~roadstyle.render_web.WebMap` — ``.save(path)`` writes the self-contained
page, and it previews inline in a notebook. Every :func:`~roadstyle.render_edges` keyword passes
through (``color_options=`` fills the *Colour by* list of the toolbox); the injected panel is
plain HTML/CSS/JS, safe to copy out and reshape.
"""
from __future__ import annotations

import json
import os

from .render import render_edges


def sidebar_html(name: str) -> str:
    """The bundled sidebar template (``"dashboard"`` or ``"street_view"``) as an HTML
    string — the exact fragment the matching ``render_*`` page injects. Handy to tweak and re-inject."""
    from . import _assets
    return _assets.text(f"templates/{name}.html")


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


_MAX_SAFE = 2**53       # a larger integer goes into the page as text: JavaScript's numbers keep 53 bits


def chart_rows(data) -> dict:
    """The page's own rows of a chart card (``chart.data``, docs/guides/dashboard-parts.md, "A chart") as the page reads them: ``{"columns": [{"name", "type"}],
    "rows": [[...]]}``, with the SQL type names of the data dock (VARCHAR, DOUBLE, BIGINT, DATE, TIMESTAMP, BOOLEAN). ``data``: a pandas
    DataFrame, a GeoDataFrame (its geometry is left out) or a list of dicts. An integer of 2**53 or more is text, so it stays exact (as the road
    ids); a missing value is ``None``; a date is ``YYYY-MM-DD`` and a time ``YYYY-MM-DD HH:MM:SS``."""
    import datetime as dt

    import pandas as pd
    df = pd.DataFrame(data) if isinstance(data, (list, tuple)) else data
    if not isinstance(df, pd.DataFrame):
        raise ValueError(f"chart data must be a DataFrame or a list of dicts, got {type(data).__name__}")
    geo = getattr(df, "_geometry_column_name", None)
    df = df[[c for c in df.columns if c != geo and str(df[c].dtype) != "geometry"]]

    def kind(s):
        t = s.dtype
        if pd.api.types.is_bool_dtype(t):
            return "BOOLEAN"
        if pd.api.types.is_integer_dtype(t):
            return "BIGINT"
        if pd.api.types.is_float_dtype(t):
            return "DOUBLE"
        if pd.api.types.is_datetime64_any_dtype(t):
            return "TIMESTAMP"
        v = next((x for x in s if x is not None and x == x), None)
        return "DATE" if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else "TIMESTAMP" if isinstance(v, dt.datetime) else "VARCHAR"

    def value(v, t):
        if v is None or (not isinstance(v, (list, tuple, dict)) and pd.isna(v)):
            return None
        if t == "BOOLEAN":
            return bool(v)
        if t == "BIGINT":
            return int(v) if abs(int(v)) < _MAX_SAFE else str(int(v))
        if t == "DOUBLE":
            return float(v)
        if t == "DATE":
            return v.isoformat()[:10]
        if t == "TIMESTAMP":
            return pd.Timestamp(v).strftime("%Y-%m-%d %H:%M:%S")
        return str(v)

    types = [kind(df[c]) for c in df.columns]
    return {"columns": [{"name": str(c), "type": t} for c, t in zip(df.columns, types, strict=True)],
            "rows": [[value(v, t) for v, t in zip(r, types, strict=True)] for r in df.itertuples(index=False, name=None)]}


def _with_chart_rows(dashboard: dict) -> dict:
    """``dashboard=`` with each chart card's ``data`` as ``chart_rows`` makes it (a mapping stays: it is ``{columns, rows}``)."""
    panel = dashboard.get("panel")
    if not isinstance(panel, dict) or not isinstance(panel.get("sections"), list):
        return dashboard

    def rows_of(s):
        c = s.get("chart") if isinstance(s, dict) else None
        if isinstance(c, dict) and c.get("data") is not None and not isinstance(c["data"], dict):
            return {**s, "chart": {**c, "data": chart_rows(c["data"])}}
        return s
    return {**dashboard, "panel": {**panel, "sections": [rows_of(s) for s in panel["sections"]]}}


def render_dashboard(gdf, *, template="dashboard", **kw):
    """A self-contained **dashboard** page: the styled map (the defaults of a map page), the toolbox (base map, roads, colour and legend,
    settings, the windows) and a side panel that starts empty. The page adds what it needs to the panel: the parts ``query``,
    ``road_card`` and ``chart``, or its own HTML, with ``dashboard={"panel": {"sections": [...]}}`` (docs/guides/dashboards.md). A chart card
    reads the map's roads, or its own rows: ``"chart": {"kind": "line", "x": "hour", "y": "vehicles", "data": df}`` (a DataFrame or a list of dicts;
    docs/guides/dashboard-parts.md, "A chart").

    Populate the *Colour by* list of the toolbox with ``color_options={...}`` (see :func:`render_edges`); any
    other ``render_edges`` keyword passes through. Returns a :class:`WebMap`;
    ``.save("dashboard.html")`` writes the page.

    ``template="dashboard"`` (the default) is the overlay form: the map fills the window, the panel floats, the toolbox at the right edge
    (docs/guides/dashboard-layout.md). ``layout="dock"`` docks the panel at the left and has no toolbox."""
    kw.pop("backend", None)                       # web only: the panel drives a MapLibre map
    return render_edges(gdf, backend="web", template=template, **kw)


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

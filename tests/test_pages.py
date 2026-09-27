"""Packaged one-call pages: render_dashboard / render_report inject the bundled sidebars."""
import geopandas as gpd
from shapely.geometry import LineString

import roadstyle as rs


def _edges():
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "primary", "residential"],
         "name": ["E18", "Main St", "Back Ln"],
         "maxspeed_kmh": [70, 50, 30],
         "lanes": [4, 2, 1]},
        geometry=[LineString([(17.9, 59.37), (17.91, 59.38)]),
                  LineString([(17.91, 59.38), (17.92, 59.38)]),
                  LineString([(17.92, 59.38), (17.92, 59.39)])],
        crs=4326)


def test_sidebar_html_bundled():
    # the templates ship inside the package (importlib.resources), not the repo ui/ dir
    assert "Roads dashboard" in rs.sidebar_html("dashboard")
    assert 'id="rp"' in rs.sidebar_html("report")


def test_render_dashboard_injects_sidebar_once():
    h = rs.render_dashboard(_edges(), color_options={"Class": {}}).html
    assert '<div id="sb"' in h          # the dashboard sidebar fragment
    assert "rsSetColorField" in h       # public window.rs* API present for it to drive
    assert h.count("</body>") == 1      # injected exactly once, before the single close tag


def test_render_report_injects_sidebar():
    h = rs.render_report(_edges()).html
    assert '<div id="rp"' in h
    assert h.count("</body>") == 1


def test_name_shows_as_sidebar_heading():
    # name= is the visible page title, not just the <title> tag (escaped, so markup can't inject)
    h = rs.render_dashboard(_edges(), name="Södermalm <traffic>").html
    assert "<h2>Södermalm &lt;traffic&gt;</h2>" in h
    assert "<h2>Roads dashboard</h2>" not in h
    assert "<h2>Roads report</h2>" in rs.render_report(_edges()).html   # default still shows


def test_pages_are_web_only():
    # backend= is ignored (these are MapLibre-only); still yields a saveable page with the sidebar
    m = rs.render_dashboard(_edges(), backend="folium")
    assert '<div id="sb"' in m.html


def test_render_street_view_injects_panel():
    h = rs.render_street_view(_edges()).html
    assert '<div id="sv"' in h and 'id="sv-frame"' in h     # the Street View panel + its iframe
    assert "maps/embed?pb=" in h                              # built from rs:select's streetView
    assert 'location.protocol === "file:"' in h               # from disk: explain, don't show grey
    assert h.count("</body>") == 1
    # the panel replaces the popup; the map keeps its own base-map switcher and class filter
    assert "Roads and Street View" in h
    assert "const _svWindow = false;" in h                   # no second Street View (the map button)


def test_street_view_width_and_divider_are_options():
    import pytest
    h = rs.render_street_view(_edges()).html
    assert '<div id="sv-drag"' in h and "--sv-w: 42%;" in h      # draggable, 42% by default
    h = rs.render_street_view(_edges(), panel_width=60, resizable=False).html
    assert '<div id="sv-drag"' not in h and "--sv-w: 60%;" in h   # fixed at 60%
    with pytest.raises(ValueError):
        rs.render_street_view(_edges(), panel_width=95)

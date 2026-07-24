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

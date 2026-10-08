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


def test_street_view_below_layout():
    import pytest
    h = rs.render_street_view(_edges(), layout="below").html
    assert '<div id="sv" data-layout="below">' in h and "body.sv-below #sv" in h
    assert '<div id="sv" data-layout="beside">' in rs.render_street_view(_edges()).html
    # the phone layout only on phones: a docs text column (~690 px) keeps the side-by-side page
    assert "@media (max-width: 520px)" in h
    with pytest.raises(ValueError):
        rs.render_street_view(_edges(), layout="diagonal")


def test_street_view_key_turns_the_embed_into_a_panorama_that_reports_its_moves(monkeypatch):
    """Without a key: the keyless embed, no Maps script. With one: the key in the page, the panorama
    that moves the map marker, Google's own imagery only."""
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    h = rs.render_street_view(_edges()).html
    assert "const GKEY = \"\";" in h and "rsSetStreetViewMarkerAt" in h
    h = rs.render_street_view(_edges(), street_view_key="AIzaTEST").html
    assert 'const GKEY = "AIzaTEST";' in h
    assert "StreetViewSource.GOOGLE" in h and "position_changed" in h and "rsSetStreetViewMarkerAt(p.lng()" in h
    # both versions on the page, the viewer flips between them (shown only with a key)
    assert 'data-m="linked"' in h and 'data-m="classic"' in h and "rs-street-view-mode" in h


def test_street_view_window_takes_the_key_too(monkeypatch):
    """The floating window every dashboard uses: the same Linked / Classic switch with a key."""
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    h = rs.render_edges(_edges(), backend="web", street_view="window").html
    assert "const _svKey = \"\";" in h
    h = rs.render_edges(_edges(), backend="web", street_view="window", street_view_key="AIzaTEST").html
    assert 'const _svKey = "AIzaTEST";' in h and "__rsSvwReady" in h and 'class="rs-svw-mode"' in h


def test_street_view_key_comes_from_the_environment(monkeypatch):
    """GOOGLE_MAPS_API_KEY is every page's key when none is passed (2026-10-10: the editor, mapstyle and lanestyle pages had none); a passed one wins."""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "AIzaENV")
    assert 'const _svKey = "AIzaENV";' in rs.render_edges(_edges(), backend="web").html
    assert 'const GKEY = "AIzaENV";' in rs.render_street_view(_edges()).html
    assert 'const _svKey = "AIzaMINE";' in rs.render_edges(_edges(), backend="web", street_view_key="AIzaMINE").html


def test_street_view_spot_is_readable():
    """The spot - edge, metres along it, point, heading - is exposed as a getter and an event."""
    h = rs.render_edges(_edges(), backend="web").html
    assert "window.rsGetStreetViewSpot = rsGetStreetViewSpot" in h and '"rs:streetviewspot"' in h

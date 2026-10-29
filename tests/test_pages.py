"""Packaged one-call pages: render_dashboard injects the bundled sidebar."""
import geopandas as gpd
from shapely.geometry import LineString

import roadstyle as rs


def _in(needle, html):
    """A JSON fragment in a page, in either engine's spacing: Python's json.dumps (", ", ": ") or serde_json's compact text."""
    return needle in html or needle.replace(": ", ":").replace(", ", ",") in html


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


def test_render_dashboard_injects_sidebar_once():
    h = rs.render_dashboard(_edges(), color_options={"Class": {}}).html
    assert '<div id="sb"' in h          # the dashboard sidebar fragment
    assert "rsSetColorField" in h       # public window.rs* API present for it to drive
    assert h.count("</body>") == 1      # injected exactly once, before the single close tag


def test_name_shows_as_sidebar_heading():
    # name= is the visible page title, not just the <title> tag (escaped, so markup can't inject)
    h = rs.render_dashboard(_edges(), name="Södermalm <traffic>").html
    assert "<h2>Södermalm &lt;traffic&gt;</h2>" in h
    assert "<h2>Roads dashboard</h2>" not in h
    assert "<h2>Roads dashboard</h2>" in rs.render_dashboard(_edges()).html   # default still shows


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
    assert _in('"street_view": true, "street_view_key"', h)                   # no second Street View (the map button): a link, not the window


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
    monkeypatch.delenv("GOOGLE_MAPS_KEY", raising=False)
    h = rs.render_street_view(_edges()).html
    assert "const GKEY = \"\";" in h and "rsSetStreetViewMarkerAt" in h
    h = rs.render_street_view(_edges(), street_view_key="AIzaTEST").html
    assert 'const GKEY = "AIzaTEST";' in h
    assert "StreetViewSource.GOOGLE" in h and "position_changed" in h and "rsSetStreetViewMarkerAt(p.lng()" in h
    # both versions on the page, the viewer flips between them (shown only with a key)
    assert 'data-m="linked"' in h and 'data-m="classic"' in h and "rs-street-view-mode" in h


def test_street_view_window_takes_the_key_too(monkeypatch):
    """The floating window every dashboard uses: the same Linked / Classic switch with a key."""
    monkeypatch.delenv("GOOGLE_MAPS_KEY", raising=False)
    h = rs.render_edges(_edges(), backend="web", street_view="window").html
    assert _in('"street_view_key": "", "google_3d"', h)
    h = rs.render_edges(_edges(), backend="web", street_view="window", street_view_key="AIzaTEST").html
    assert _in('"street_view_key": "AIzaTEST", "google_3d"', h) and "__rsGmReady" in h and 'class="rs-svw-mode"' in h


def test_street_view_key_comes_from_the_environment(monkeypatch):
    """GOOGLE_MAPS_KEY is every page's key when none is passed (2026-10-10: the editor, mapstyle and lanestyle pages had none); a passed one wins."""
    monkeypatch.setenv("GOOGLE_MAPS_KEY", "AIzaENV")
    assert _in('"street_view_key": "AIzaENV", "google_3d"', rs.render_edges(_edges(), backend="web").html)
    assert 'const GKEY = "AIzaENV";' in rs.render_street_view(_edges()).html
    assert _in('"street_view_key": "AIzaMINE", "google_3d"', rs.render_edges(_edges(), backend="web", street_view_key="AIzaMINE").html)


def test_street_view_spot_is_readable():
    """The spot - edge, metres along it, point, heading - is exposed as a getter and an event."""
    h = rs.render_edges(_edges(), backend="web").html
    assert "window.rsGetStreetViewSpot = rsGetStreetViewSpot" in h and '"rs:streetviewspot"' in h


def _dashboard(html):
    """The typed `dashboard` option of a page (RS_OPTIONS.dashboard)."""
    import json
    return json.JSONDecoder().raw_decode(html, html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = "))[0]["dashboard"]


def test_each_page_has_its_template():
    assert _dashboard(rs.render_edges(_edges(), backend="web").html)["template"] == "map"
    d = _dashboard(rs.render_dashboard(_edges()).html)                      # the default of render_dashboard is the overlay form
    assert (d["template"], d["layout"], d["panel"], d["toolbar"]) == ("dashboard", "overlay", {"side": "right", "width_px": 340, "look": "frame"},
                                                                       {"position": "right", "settings": True, "hold": False})
    c = _dashboard(rs.render_dashboard(_edges(), layout="dock").html)
    assert (c["template"], c["layout"], c["panel"]["look"], c["toolbar"]) == ("dashboard", "dock", "frame", None)


def test_one_template_with_a_layout():
    """The old names are errors with the way out; the map has no layout; there is no report page."""
    import pytest
    for old in ("classic", "report"):
        with pytest.raises(ValueError, match=f'template="{old}" is gone'):
            rs.render_dashboard(_edges(), template=old)
    with pytest.raises(ValueError, match="layout must be"):
        rs.render_dashboard(_edges(), layout="grid")
    with pytest.raises(ValueError, match="layout= is for"):
        rs.render_edges(_edges(), backend="web", layout="dock")
    assert not hasattr(rs, "render_report")


def test_an_old_keyword_says_where_it_went():
    import pytest
    for old, hint in [("toolbar", 'dashboard={"toolbar"'), ("edit", "no edit hook"), ("panel", "no report panel")]:
        with pytest.raises(ValueError, match=hint.replace("{", r"\{").replace("}", r"\}").replace("(", r"\(")):
            rs.render_dashboard(_edges(), **{old: 1})


def test_the_ids_that_the_migration_guide_keeps_stable_are_in_the_panel():
    h = rs.render_dashboard(_edges()).html
    for i in ("sb", "sb-hide", "sb-show", "sb-th", "bm", "co", "sb-legend", "q", "tbl", "count", "detail"):
        assert f'id="{i}"' in h, i


def test_the_dashboard_keyword_merges_typed_options():
    import pytest
    d = _dashboard(rs.render_dashboard(_edges(), dashboard={"toolbar": {"position": "left", "hold": True},
                                                            "google_3d": {"selection_style": {"width": 12}}}).html)
    assert d["toolbar"] == {"position": "left", "settings": True, "hold": True}
    assert (d["google_3d"]["selection_style"]["width"], d["google_3d"]["selection_style"]["color"]) == (12.0, "#22d3ee")
    for bad, said in [({"toolbar": {"colour": 1}}, "colour"), ({"template": "map"}, "cannot change the template"), ({"windows": {"clamp": "x"}}, "invalid type")]:
        with pytest.raises(ValueError, match=said):
            rs.render_dashboard(_edges(), dashboard=bad)


def test_the_boundary_shade_and_limit_are_the_pages_choice():
    from shapely.geometry import box
    area = box(17.99, 59.29, 18.02, 59.32)
    d = _dashboard(rs.render_dashboard(_edges(), boundary=area).html)["boundary"]
    assert (d["dim"], d["limit"]) == (False, False)
    d = _dashboard(rs.render_dashboard(_edges(), boundary=area, boundary_dim=True, boundary_limit=True).html)["boundary"]
    assert (d["dim"], d["limit"], d["limit_pad"]) == (True, True, 2.0)


def test_the_dashboard_template_is_the_overlay_form():
    h = rs.render_dashboard(_edges()).html
    d = _dashboard(h)
    assert (d["layout"], d["toolbar"]) == ("overlay", {"position": "right", "settings": True, "hold": False})
    assert d["windows"]["clamp"] is True and d["windows"]["recenter_map"] is False
    assert '<div id="sb"' in h and "<h2>Roads dashboard</h2>" in h
    assert 'c.add("rs-tpl-dashboard","rs-overlay","rs-has-toolbar","rs-tb-right")' in h   # the first paint has the form


def test_a_template_name_is_checked_and_sidebar_is_gone():
    import pytest
    with pytest.raises(ValueError, match="template must be"):
        rs.render_dashboard(_edges(), template="wide")
    with pytest.raises(ValueError, match="unknown keyword .sidebar."):
        rs.render_edges(_edges(), backend="web", sidebar="dashboard")

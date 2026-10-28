"""The runtime API of the interaction contract (static/dashboard/api.js, docs/design/rust_library.md "The runtime API") in a browser: the
page's window.rs gives the state, sets a part of it through the controls, reports changes, and keeps a state in a URL (#rs=). Needs
playwright and its Chromium; skipped without them."""
import pytest

pw = pytest.importorskip("playwright.sync_api")


def _edges(n=12):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"highway": ["primary", "residential"] * (n // 2), "name": [f"Street {i}" for i in range(n)], "lanes": list(range(n)),
         "edge_id": [str(10**15 + i) for i in range(n)]},
        geometry=[LineString([(18.0 + i * 1e-3, 59.3), (18.0 + i * 1e-3, 59.301)]) for i in range(n)], crs=4326)


def test_the_page_has_one_object_for_its_state(tmp_path):
    import roadstyle as rs
    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("the Rust extension is not built")
    path = tmp_path / "api.html"
    rs.render_edges(_edges(), basemap="blank", color_options={"class": {}, "lanes": {"color_by": "lanes", "cmap": "Blues"}}).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rs", timeout=30_000)
        start = page.evaluate("rs.getState()")
        primary = page.evaluate("rs.query({highway: 'primary'})")
        page.evaluate("window.seen = []; rs.on('state', s => seen.push(s)); 0")     # not the remover: playwright would call it
        page.evaluate("rs.setState({roadFill: false, colorBy: 'lanes', filter: {bridges: false}})")
        page.evaluate(f"rs.select({primary[0]!r})")
        after = page.evaluate("rs.getState()")
        seen = page.evaluate("seen")
        link = page.evaluate("rs.link()")
        can = page.evaluate("[rs.can({colorBy: 'lanes'}), rs.can({colorBy: 'speed'}), rs.can({nope: 1})]")
        page.goto(path.resolve().as_uri() + link)                     # the same page with the state in its URL
        page.wait_for_function("window.map && window.map.loaded() && window.rs", timeout=30_000)
        page.wait_for_function("rs.getState().roadFill === false", timeout=10_000)
        again = page.evaluate("rs.getState()")
        browser.close()
    assert errors == []
    assert start["v"] == 1 and start["roadFill"] is True and start["colorBy"] == "class" and start["selection"] is None
    assert primary == [str(10**15 + i) for i in range(0, 12, 2)]     # edge ids, as text
    assert after["roadFill"] is False and after["colorBy"] == "lanes" and after["filter"]["bridges"] is False
    assert after["selection"] == primary[0]
    assert {"roadFill": False} in seen and {"colorBy": "lanes"} in seen
    assert link.startswith("#rs=") and can == [True, False, False]
    assert again["roadFill"] is False and again["colorBy"] == "lanes" and again["selection"] == primary[0]

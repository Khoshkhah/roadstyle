"""A box of the bar (the settings, the colour box, the attribution) keeps 12 px from the top and the bottom of the window, whatever the height of the window and
whichever edge of the box is fixed to the bar. The settings have no "Reset transparency" button and no note about the key, and the value of a slider is
in the row of its label. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_URL = "http://rs.test/page.html"
_BOX = """async (id) => { rs.tools.open(id); await new Promise(f => requestAnimationFrame(() => requestAnimationFrame(f))); const r = document.querySelector(id === "settings" ? "#rs-settings-box" : "#rs-attr-box").getBoundingClientRect();
  const sl = document.querySelector(".rs-set-slide"), lab = sl && sl.querySelector("span").getBoundingClientRect(), val = sl && sl.querySelector("b").getBoundingClientRect();
  const out = {top: r.top, bottom: r.bottom, same_row: !sl || Math.abs(lab.top - val.top) < 6, text: document.querySelector("#rs-settings-box").textContent}; rs.tools.close(id); return out; }"""


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary", "residential"], "edge_id": [1, 2]}, crs=4326,
                            geometry=[LineString([(18.0, 59.3), (18.001, 59.301)]), LineString([(18.002, 59.3), (18.003, 59.301)])])


def test_the_boxes_of_the_bar_stay_inside_the_window_and_the_settings_have_no_reset_or_key_note():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        for height in (900, 760, 600, 480):
            page = browser.new_page(viewport={"width": 1280, "height": height})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
            page.goto(_URL)
            page.wait_for_function("window.map && window.map.loaded() && !!window.rs", timeout=60_000)
            for box in ("settings", "attribution"):
                r = page.evaluate(_BOX, box)
                assert r["top"] >= 11 and r["bottom"] <= height - 11, (height, box, r)
            assert r["same_row"] or box == "attribution", r
            assert "Reset transparency" not in r["text"] and "never written into the page file" not in r["text"]
            page.close()
        browser.close()
    assert not errors, errors

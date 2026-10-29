"""The tool `legend` of the bar follows the roads style of the moment: a page whose style has no colour options has the greyed button; `rs.setStyle` with a
style that has colour options (a page that starts with `rsDashboard(map, {style: null, ...})` and gets its roads later) gives the tool, in the place of the
greyed button; a later style with none gives the greyed button again. Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")
_URL = "http://rs.test/page.html"
_STEPS = """(style) => {
  const plain = JSON.parse(JSON.stringify(style)); plain.metadata["roadstyle:color_options"] = [];
  const slot = () => [...document.querySelectorAll("#rs-toolbar > *")].findIndex(e => e.querySelector("button[title*='olour']"));
  const legend = () => ({...rs.tools.list().find(t => t.id === "legend"), slot: slot()});
  const steps = {start: legend()};
  rs.setStyle(style); steps.colour = legend();
  rs.tools.open("legend"); steps.box = document.querySelector("#rs-color-box").textContent; rs.tools.close("legend");
  rs.setStyle(plain); steps.plain = legend();
  return steps;
}"""


def test_the_legend_tool_comes_with_a_later_style_and_goes_with_a_style_that_has_no_colour_options():
    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("no roadstyle._rust")
    import geopandas as gpd
    import shapely.geometry as sg

    import roadstyle as rs
    g = gpd.GeoDataFrame({"highway": ["primary", "residential"], "edge_id": [1, 2]}, crs=4326,
                         geometry=[sg.LineString([(18.0, 59.3), (18.001, 59.301)]), sg.LineString([(18.002, 59.3), (18.003, 59.301)])])
    html = rs.render_dashboard(g, basemap="blank").html
    at = html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = ")
    opts, end = json.JSONDecoder().raw_decode(html, at)
    del opts["color_options"]       # a page that gets its style later does not give the colour options: they come with the style (the duckosm-rust page)
    html = html[:at] + json.dumps(opts) + html[end:]
    style = json.loads(_engine.rust().inline_style(_engine._arrow(g), _engine._look_of({"state": "live", "color_options": {"Road class": {}}}), None, None, "roads"))
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        steps = page.evaluate(_STEPS, style)
        browser.close()
    assert not errors, errors
    assert steps["start"]["disabled"] is True and steps["start"]["slot"] >= 0
    assert steps["colour"]["disabled"] is False and steps["colour"]["kind"] == "box" and steps["colour"]["title"] == "Colour by and legend"
    assert steps["colour"]["slot"] == steps["start"]["slot"] and "Road class" in steps["box"]
    assert steps["plain"]["disabled"] is True and steps["plain"]["slot"] == steps["start"]["slot"]

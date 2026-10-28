"""N23: the page puts the data into HTML only as text. A road named <img src=x onerror=...> must not run a script: not in the search,
the popup, the side panel, the hover tooltip or the legend (docs/design/dashboard_module.md, "Trusted inputs")."""
import pathlib

import pytest

pw = pytest.importorskip("playwright.sync_api")
DATA = pathlib.Path(__file__).parents[1] / "rust" / "roadstyle-rs" / "tests" / "data" / "monaco_part" / "roads.parquet"
EVIL = '<img src=x onerror="window.__xss=1">'


def _roads():
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely
    df = pq.read_table(DATA).to_pandas(integer_object_nulls=True)
    g = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    g["name"] = g["name"].astype(object)
    g.loc[g.index[0], "name"] = EVIL
    g["kind"] = ["ok"] * len(g)                         # a category whose label is the same text, for the legend
    g.loc[g.index[0], "kind"] = EVIL
    return g




@pytest.mark.parametrize("popup_mode", ["popup", "panel"])
def test_a_road_name_is_text_not_markup(tmp_path, popup_mode):
    import roadstyle as rs
    page = tmp_path / "xss.html"
    rs.render_edges(_roads(), basemap="blank", find_control=True, popup_mode=popup_mode, tooltip=["name"],
                    color_options={"Class": {}, "kind": {"color_by": "kind", "colors": {"ok": "#00aa00", EVIL: "#aa0000"}}},
                    legend=True).save(str(page))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(page.as_uri())
        pg.wait_for_function("window.rs && window.map && map.isStyleLoaded() && window.rsQuery && rsQuery(() => true).length", timeout=60000)
        # each step waits for its text (a fixed wait failed under the load of the whole suite); then 300 ms more, so that an <img> that
        # was not escaped has the time to fail and run its onerror
        shown = pg.evaluate("""async evil => {
          const wait = ms => new Promise(r => setTimeout(r, ms)), out = {};
          const until = async f => { for (let t = 0; t < 200 && !f().includes(evil); t++) await wait(50); return f(); };
          const q = document.querySelector('.rs-side-q input, input[type=search]');      // the search
          if (q) { q.value = 'img'; q.dispatchEvent(new Event('input')); }
          out.search = q ? await until(() => (document.querySelector('.rs-side-q-res, .rs-q-res') || {}).textContent || '') : '';
          rsSelect(0);                                                                   // the popup or the side panel
          out.select = await until(() => [...document.querySelectorAll('.maplibregl-popup-content, .rs-side')].map(e => e.textContent).join(' '));
          rsSetColorField('kind');                                                       // the legend
          out.legend = await until(() => (document.querySelector('.co-lg') || {}).textContent || '');
          await wait(300);
          out.xss = window.__xss === undefined ? 'none' : 'RAN';
          return out; }""", EVIL)
        browser.close()
    assert shown["xss"] == "none"
    assert EVIL in shown["select"] and EVIL in shown["legend"]          # shown as text
    if shown["search"]:
        assert EVIL in shown["search"]


def test_a_value_cannot_end_the_pages_script(tmp_path):
    """The page writers put the style and the dashboard's options into a <script> as JSON, and a legend's labels are data values. A value
    with "</script>" in it is "\\u003c/script>" there (render_web._script_json, page.rs script_json): it cannot end the script and run."""
    import roadstyle as rs
    close = "</script><img src=x onerror=window.__xss=3>"
    g = _roads()
    g.loc[g.index[1], "kind"] = close
    page = tmp_path / "close.html"
    page.write_text(rs.render_edges(g, basemap="blank", legend=True,
                                    color_options={"Class": {}, "kind": {"color_by": "kind", "colors": {"ok": "#00aa00", close: "#0000aa"}}}).html)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(page.as_uri())
        pg.wait_for_function("window.rs && window.map && map.isStyleLoaded()", timeout=60000)
        pg.evaluate("rsSetColorField('kind')")
        pg.wait_for_timeout(300)
        legend, xss = pg.evaluate("[(document.querySelector('.co-lg') || {}).textContent || '', window.__xss === undefined ? 'none' : 'RAN']")
        browser.close()
    assert xss == "none" and close in legend

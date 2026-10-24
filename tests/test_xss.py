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


ENGINES = ["python"] + (["rust"] if __import__("roadstyle._engine", fromlist=["available"]).available() else [])


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("popup_mode", ["popup", "panel"])
def test_a_road_name_is_text_not_markup(tmp_path, engine, popup_mode):
    import roadstyle as rs
    page = tmp_path / "xss.html"
    rs.render_edges(_roads(), engine=engine, basemap="blank", find_control=True, popup_mode=popup_mode, tooltip=["name"],
                    color_options={"Class": {}, "kind": {"color_by": "kind", "colors": {"ok": "#00aa00", EVIL: "#aa0000"}}},
                    legend=True).save(str(page))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(page.as_uri())
        pg.wait_for_function("window.rs && window.map && map.isStyleLoaded() && window.rsQuery && rsQuery(() => true).length", timeout=60000)
        shown = pg.evaluate("""async () => {
          const wait = () => new Promise(r => setTimeout(r, 300)), out = {};
          const q = document.querySelector('.rs-side-q input, input[type=search]');      // the search
          if (q) { q.value = 'img'; q.dispatchEvent(new Event('input')); await wait(); }
          out.search = (document.querySelector('.rs-side-q-res, .rs-q-res') || {}).textContent || '';
          rsSelect(0); await wait();                                                     // the popup or the side panel
          out.select = [...document.querySelectorAll('.maplibregl-popup-content, .rs-side')].map(e => e.textContent).join(' ');
          rsSetColorField('kind'); await wait();                                         // the legend
          out.legend = (document.querySelector('.co-lg') || {}).textContent || '';
          out.xss = window.__xss === undefined ? 'none' : 'RAN';
          return out; }""")
        browser.close()
    assert shown["xss"] == "none"
    assert EVIL in shown["select"] and EVIL in shown["legend"]          # shown as text
    if shown["search"]:
        assert EVIL in shown["search"]


@pytest.mark.parametrize("engine", ENGINES)
def test_a_value_cannot_end_the_pages_script(tmp_path, engine):
    """The page writers put the style and the dashboard's options into a <script> as JSON, and a legend's labels are data values. A value
    with "</script>" in it is "\\u003c/script>" there (render_web._script_json, page.rs script_json): it cannot end the script and run."""
    import roadstyle as rs
    close = "</script><img src=x onerror=window.__xss=3>"
    g = _roads()
    g.loc[g.index[1], "kind"] = close
    page = tmp_path / "close.html"
    page.write_text(rs.render_edges(g, engine=engine, basemap="blank", legend=True,
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

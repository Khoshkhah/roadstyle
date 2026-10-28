"""The two stages of the Rust engine as their own calls (docs/rust/architecture.md, "The three stages and the one call"):
export_geojson writes stage 1's files, tile_geojson makes stage 2's tiles from them, and the tiles are the tiles of the one call
(the Tiler of render(tiles=True) and export_style). rust/roadstyle-rs/tests/stages.rs compares them decoded on Monaco and Tartu."""
import json
from pathlib import Path

import pytest

import roadstyle as rs

DATA = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-rs" / "tests" / "data"
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")


@pytest.fixture(scope="module")
def part():
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    df = pq.read_table(DATA / "monaco_part" / "roads.parquet").to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")


@pytest.fixture(scope="module")
def keywords():
    look = json.loads((DATA / "look.json").read_text())
    return {"palette": look["palette"], "settings": look["settings"], **look["args"], "arrows": True, "labels": True}






def test_live_data_reads_the_feature_state_of_the_road(part, keywords):
    """R22: with live_data the road layer reads its colour (rs_c) and its width factor (rs_w) from the feature state of the road's row,
    over the baked values (the pieces have the row as their id in every style), and roadstyle:live names the states. Off, the
    style is as before."""
    off = rs.export_inline(part, **keywords)
    on = rs.export_inline(part, live_data=True, **keywords)
    road = lambda st: next(l for l in st["layers"] if l["id"] == "roads-simple")["paint"]      # noqa: E731
    assert "roadstyle:live" not in off["metadata"]
    assert "promoteId" not in on["sources"]["simple"] and "promoteId" not in off["sources"]["simple"]
    live = on["metadata"]["roadstyle:live"]
    assert (live["color"], live["width"], live["types"]) == ("rs_c", "rs_w", {"rs_c": "color", "rs_w": "factor"})
    assert len(live["ramp"]) == 9 and live["nodata"].startswith("#")
    text = json.dumps(road(on))
    assert '["feature-state", "rs_c"]' in text and '["coalesce", ["feature-state", "rs_w"], 1]' in text
    # the width is still a zoom curve at the top (MapLibre), the factor in each stop
    assert road(on)["line-width"][:3] == road(off)["line-width"][:3]
    off.pop("metadata"), on.pop("metadata")
    for st in (off, on):
        for l in st["layers"]:
            if l["id"] == "roads-simple":
                l.pop("paint")
    assert on == off




def test_a_live_page_gives_the_dashboard_the_states(part):
    """The page has no style metadata: it gives roadstyle:live to rsDashboard as the option `live` (null without live_data)."""
    from test_render_web import _opt, _style
    on = rs.render_edges(part, live_data=True, basemap="osm").html
    off = rs.render_edges(part, basemap="osm").html
    assert _opt(on, "live")["color"] == "rs_c" and _opt(off, "live") is None
    road = next(l for l in _style(on)["layers"] if l["id"] == "roads-simple")
    assert '["feature-state", "rs_c"]' in json.dumps(road["paint"]["line-color"])


def test_live_data_can_take_the_nearest_stop(part, tmp_path):
    """rs.setData(rows, {stepped: true}) gives each road the ramp's nearest stop, not a colour between two (SonoFlow's Daily page colours
    so); its legend draws the same steps."""
    pw = pytest.importorskip("playwright.sync_api")
    page_file = tmp_path / "live.html"
    page_file.write_text(rs.render_edges(part, live_data=True, basemap="blank").html)
    ids = [str(e) for e in part["edge_id"][:2]]
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(page_file.as_uri())
        page.wait_for_function("window.rs && window.map && map.isStyleLoaded() && window.RS_SIDE", timeout=60000)
        got = page.evaluate("""async ids => {
          const L = map.getLayer('roads-simple'), at = i => map.getFeatureState({source: L.source, sourceLayer: L.sourceLayer, id: i}).rs_c;
          const rows = [{edge_id: ids[0], v: 0.4}, {edge_id: ids[1], v: 0.6}], o = {colorBy: 'v', vmin: 0, vmax: 1, ramp: ['#000000', '#ffffff']};
          await rs.setData(rows, {...o, stepped: true});
          const stepped = [at(0), at(1)], bar = document.querySelector('.lg-bar').getAttribute('style');
          await rs.setData(rows, o);
          return {stepped, bar, linear: at(0)}; }""", ids)
        browser.close()
    assert got["stepped"] == ["#000000", "#ffffff"]          # 0.4 and 0.6 between the two stops: the nearer one
    assert got["linear"] == "#666666"                        # without it: the colour 40 % of the way
    assert "#000000 0%" in got["bar"] and "#ffffff 50.00%" in got["bar"]     # the legend's hard step half-way


def test_the_parquet_files_keep_big_ids_as_integers(part, keywords, tmp_path):
    """N1: duckOSM's edge ids are past 2**53 - 1; the model keeps them as integers, so DuckDB reads the road table and the roads' file
    with BIGINT ids (the BIGINT rule of the matchers), while every JSON form writes them as text (JavaScript would round them)."""
    duckdb = pytest.importorskip("duckdb")
    big = 2 ** 60
    roads = part.assign(edge_id=[big + i for i in range(len(part))])        # ids as duckOSM hashes them (the fixture's are text)
    rs.export_geojson(roads, tmp_path / "pq", format="geoparquet", **keywords)
    for name in ("road_table.parquet", "roads.parquet"):
        cols = {r[0]: r[1] for r in duckdb.sql(f"DESCRIBE SELECT * FROM '{tmp_path / 'pq' / name}'").fetchall()}
        assert cols["edge_id"] == "BIGINT", (name, cols["edge_id"])
    assert duckdb.sql(f"SELECT max(edge_id) FROM '{tmp_path / 'pq' / 'road_table.parquet'}'").fetchall()[0][0] == big + len(part) - 1
    rs.export_geojson(roads, tmp_path / "gj", format="geojson", **keywords)
    ids = [f["properties"]["edge_id"] for f in json.loads((tmp_path / "gj" / "roads.geojson").read_text())["features"]]
    assert ids[:2] == [str(big), str(big + 1)]                                # the JSON form: text


def test_the_tiled_style_says_its_tile_layers(part, keywords):
    """N3, N7: stage 2's one style (tile_stage) has a vector source with no promoteId (the MVT id is the road's row), and roadstyle:sources and
    roadstyle:arrows say the final layers: the road layer on the tile layer simple of the source roads."""
    from roadstyle import _engine

    lk = _engine._look_of({**keywords, "state": "live", "live_data": True})
    src = _engine.rust().style_sources(_engine._arrow(part), lk, None, None, "x")
    inline = json.loads(src.style())["metadata"]
    assert inline["roadstyle:sources"]["simple"] == {"source": "simple", "layer": None}
    text, t = src.tile_stage(only=["roads", "simple", "slots"], at=json.dumps({"url": "pmtiles://roads"}))      # as a page
    st = json.loads(text)
    assert "promoteId" not in st["sources"]["roads"] and st["sources"]["roads"]["url"] == "pmtiles://roads"
    assert st["metadata"]["roadstyle:contract"] == 2
    assert st["metadata"]["roadstyle:sources"]["simple"] == {"source": "roads", "layer": "simple"}
    assert st["metadata"]["roadstyle:arrows"] == inline["roadstyle:arrows"] and "simple" in t.layers()
    assert json.loads(src.style())["metadata"] == inline          # stage 2 borrows the sources (N6)


def test_stage_1_is_the_road_table_form_and_only_an_export_has_the_roads(part, keywords):
    """N2 (2026-10-24): stage 1 reads neither `state` nor `tiles`. A host's style (live or not) has no roads source, no pick or highlight
    layer, and no promoteId; only an export (export_inline, export_style: an app with no road table) has the roads source with
    its pick and highlight layers; the inline page's stage 3 makes the arrows points (page_arrows)."""
    from roadstyle import _engine

    def style(**kw):
        return json.loads(_engine.rust().inline_style(_engine._arrow(part), _engine._look_of({**keywords, **kw}), None, None, None))

    for kw in ({}, {"state": "live"}, {"state": "live", "tiles": True}):
        st = style(**kw)
        ids = [lyr["id"] for lyr in st["layers"]]
        assert "roads" not in st["sources"] and "roads-fill" not in ids and "roads-highlight" not in ids, kw
        assert "promoteId" not in st["sources"]["simple"]
        assert next(lyr for lyr in st["layers"] if lyr["id"] == "roads-arrows")["source"] == "slots", kw
    ex = rs.export_inline(part, **keywords)
    assert "roads" in ex["sources"] and {"roads-fill", "roads-highlight"} <= {lyr["id"] for lyr in ex["layers"]}
    src = _engine.rust().style_sources(_engine._arrow(part), _engine._look_of({**keywords, "state": "live"}), None, None, None)
    src.page_arrows()
    st = json.loads(src.style())
    assert next(lyr for lyr in st["layers"] if lyr["id"] == "roads-arrows")["source"] == "arrows" and st["metadata"]["roadstyle:arrows"] == "points"


def test_a_warning_of_the_rust_engine_is_a_python_warning():
    """R17: the engine gives its warnings back with its output (no thread-local in the engine); the binding gives them to Python. A
    two-way pair whose two directions have other casing numbers gets the twin_casing warning."""
    import geopandas as gpd
    from shapely.geometry import LineString

    a, b = (18.0, 59.30), (18.0, 59.301)
    g = gpd.GeoDataFrame({"edge_id": [1, 2], "highway": "primary", "cs": [1, 1], "cm": [1, 2], "ce": [1, 1], "fl": [3, 3]},
                         geometry=[LineString([a, b]), LineString([b, a])], crs=4326)
    kw = dict(casing_start_col="cs", casing_level_col="cm", casing_end_col="ce", fill_level_col="fl")
    with pytest.warns(UserWarning, match="twin_casing: 1 two-way pair"):
        rs.export_inline(g, **kw)


def test_the_binding_takes_arrow_tables_only(part, keywords):
    """The roads go to Rust as an Arrow stream (audit R15): a pyarrow table and GeoPandas' to_arrow give the same style; bytes are a
    TypeError."""
    import pyarrow as pa

    from roadstyle import _engine

    lk = _engine._look_of(keywords)
    t = _engine._arrow(part)
    assert _engine.rust().inline_style(pa.table(t), lk, None, None, None) == _engine.rust().inline_style(t, lk, None, None, None)
    with pytest.raises(TypeError, match="__arrow_c_stream__"):
        _engine.rust().inline_style(b"PAR1", lk, None, None, None)

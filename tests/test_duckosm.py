"""The duckOSM reader (roadstyle.duckosm, with the Rust engine's SQL, roadstyle_io::duckosm): a duckOSM file's roads are the roads that
an earlier reader gave roadstyle, value for value and in the same order, plus `source` and `target` (R13). The tests of Monaco need a
duckOSM file with features.* and stored levels ($DUCKOSM_DB, else ../duckOSM/monaco.duckdb beside this repository) and mapstyle:
skipped without them (CI has neither); the tests of a tiny file made here run everywhere."""
import json
import os
import tempfile
from pathlib import Path

import pytest

DB = Path(os.environ.get("DUCKOSM_DB") or Path(__file__).resolve().parents[1].parent / "duckOSM" / "monaco.duckdb")
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")
needs_db = pytest.mark.skipif(not DB.is_file(), reason=f"no duckOSM file at {DB}")


@needs_db
def test_the_base_map_rows():
    pytest.importorskip("pyarrow")
    from roadstyle import duckosm

    _, t, _ = duckosm.read(DB)
    assert t.num_rows > 0 and t.schema.names[:3] == ["spec", "layer", "rid"]
    with pytest.raises(ValueError, match="unknown mode"):
        duckosm.read(DB, "boat")


def _goldens():
    import importlib.util
    here = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-rs" / "tests"
    spec = importlib.util.spec_from_file_location("make_mapstyle_goldens", here / "make_mapstyle_goldens.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    return gen, json.loads((here / "data" / "mapstyle_digests.json").read_text())


@needs_db
@pytest.mark.parametrize("choice", ["all osm google", "driving osm google", "walking osm google", "cycling osm google", "all grey google",
                                    "walking google komoot", "driving osm google only", "walking osm google only"])
def test_the_style_is_mapstyles(choice):
    """The style of roadstyle.duckosm.export_inline (the reader, the base map's look and stage 1 in Rust) is the stored mapstyle
    export_inline of the same choice, both normalised (tests/make_mapstyle_goldens.py: the rules of `normalised` and `differences`, each
    with its reason)."""
    from roadstyle import duckosm

    gen, digests = _goldens()
    mode, theme, paths, *only = choice.split()
    name = gen.name_of(mode, theme, paths, bool(only))
    if not (gen.HERE / "data" / "mapstyle" / f"{name}.json.gz").is_file():
        pytest.skip("the stored mapstyle styles are local only: run rust/roadstyle-rs/tests/make_mapstyle_goldens.py styles")
    style = duckosm.export_inline(DB, mode, theme=theme, paths=paths, only=bool(only))
    # the stored mapstyle style (local, as the digests), normalised: the same, a colour within 1 in each channel (review D4); the digests
    # stay as the record of the stored styles
    want = gen.stored(name)
    assert gen.digest(want)["sha256"] == digests[name]["sha256"], f"{name}: not the stored golden"
    bad = gen.differences(gen.normalised(style), gen.normalised(want))
    assert not bad, "\n".join(bad)
    # the 3D decks' union area of each chain (the normalised form has their chains, edges, heights and heads)
    want, got = gen.deck_areas(gen.stored(name)), gen.deck_areas(style)
    assert set(got) == set(want)
    for (chain, slab), a in want.items():
        assert abs(got[chain, slab] - a) <= gen.DECK_AREA[slab] * a, f"chain {chain} ({'slabs' if slab else 'decks'}): {got[chain, slab]} against {a}"


@needs_db
def test_a_map_of_one_mode_needs_a_mode_and_its_stored_levels(tmp_path):
    """only=True: the roads of one network; the mode "all" is an error, and so is a road with no stored row (the levels were solved for
    other roads)."""
    import duckdb

    from roadstyle import duckosm

    with pytest.raises(ValueError, match="only: a map of one mode needs the mode driving, walking or cycling"):
        duckosm.read(DB, "all", only=True)
    db = tmp_path / "stale.duckdb"
    con = duckdb.connect(str(db))
    con.execute(f"ATTACH '{DB}' AS src (READ_ONLY)")
    for s, t in con.execute("SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = 'src'").fetchall():
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{s}"')
        con.execute(f'CREATE TABLE "{s}"."{t}" AS SELECT * FROM src."{s}"."{t}"')
    con.execute("DELETE FROM visualization.edge_levels WHERE edge_id = (SELECT min(edge_id) FROM driving.edges)")
    con.close()
    with pytest.raises(ValueError, match="1 of the edges are not edges the stored levels were solved for"):
        duckosm.read(db, "driving", only=True)


def _tiny(path, network=True):
    """A tiny duckOSM file made here (no real area): two driving edges with no private_edges (so no `access` of a restricted road),
    stored levels, and one base-map table."""
    import duckdb
    con = duckdb.connect(str(path))
    if network:
        con.execute("CREATE SCHEMA driving")
        con.execute("CREATE TABLE driving.edges (edge_id BIGINT, source BIGINT, target BIGINT, osm_id BIGINT, highway VARCHAR, name VARCHAR, "
                    "bridge VARCHAR, tunnel VARCHAR, layer VARCHAR, oneway BOOLEAN, geometry GEOMETRY)")
        con.execute("INSERT INTO driving.edges VALUES (1, 10, 11, 100, 'residential', 'A', NULL, NULL, NULL, false, "
                    "'LINESTRING(7.40 43.73, 7.41 43.73)'::GEOMETRY), (2, 11, 10, 100, 'residential', 'A', NULL, NULL, NULL, false, "
                    "'LINESTRING(7.41 43.73, 7.40 43.73)'::GEOMETRY)")
    con.execute("CREATE SCHEMA features")
    con.execute("CREATE TABLE features.water_polygons (osm_id BIGINT, kind VARCHAR, name VARCHAR, geom GEOMETRY)")
    con.execute("INSERT INTO features.water_polygons VALUES (5, 'water', 'P', 'POLYGON((7.40 43.72, 7.41 43.72, 7.41 43.725, 7.40 43.72))'::GEOMETRY)")
    con.close()
    return path


def test_a_file_with_no_private_edges_reads(tmp_path):
    """With no private_edges, the union's access is NULL only, which DuckDB typed as an integer: "Could not convert string 'bus' to
    INT32" (an older file, granville_island). The reader types it as text."""
    pytest.importorskip("pyarrow")
    from roadstyle import duckosm

    roads, features, levels = duckosm.read(_tiny(tmp_path / "t.duckdb"), levels="tags")
    t = roads
    assert t.num_rows == 2 and str(t.schema.field("access").type) == "string" and levels == "tags"
    assert features.num_rows == 1


def test_the_plan_has_the_base_map_of_a_file_with_no_network(tmp_path):
    """duckosm_plan gives the base map's queries for a file with no <mode>.edges ("roads" null and "roads_error"), so a reader of the
    base map alone works; read() of the roads is the error."""
    import duckdb

    from roadstyle import _engine, duckosm

    db = _tiny(tmp_path / "n.duckdb", network=False)
    con = duckdb.connect(str(db), read_only=True)
    tq, cq = _engine.rust().duckosm_catalog_sql("n")
    plan = json.loads(_engine.rust().duckosm_plan(con.execute(tq).fetchall(), con.execute(cq).fetchall(), "all", True,
                                                   json.dumps(duckosm.layer_specs())))
    con.close()
    assert plan["roads"] is None and "no <mode>.edges table" in plan["roads_error"]
    assert [lyr["name"] for lyr in plan["layers"]] == ["water"]
    with pytest.raises(ValueError, match="no <mode>.edges table"):
        duckosm.read(db, levels="tags")


def test_the_page_of_a_duckosm_file(tmp_path):
    """duckosm.page (mapstyle's render_map on the Rust engine): the page of the roads and the base map; render_map's interaction for a
    layer that the map does not have is a warning; dashboard=True gives the roads the column `modes` of the colour option "Modes"."""
    from roadstyle import duckosm

    db = _tiny(tmp_path / "p.duckdb")
    with pytest.warns(UserWarning, match="interaction: no layer nolayer on this map"):
        page = duckosm.page(db, "driving", levels="tags", interaction={"nolayer": {"clickable": True}})
    assert "rsDashboard" in page.html
    out = tmp_path / "dash.html"
    duckosm.page(db, "driving", levels="tags", dashboard=True).save(str(out))
    assert out.stat().st_size > 1000


def test_a_duckosm_page_takes_the_keywords_of_render_dashboard(tmp_path):
    """duckosm.page with a page's own data, as render_dashboard: overlays (rs.Overlay), a panel of its own (dashboard={...}), live
    data, a page script, colour options, a boundary, a minzoom and exclude."""
    import shapely

    import roadstyle as rs
    from roadstyle import duckosm

    db = _tiny(tmp_path / "p.duckdb")
    pts = __import__("geopandas").GeoDataFrame({"PK": [1, 2]}, geometry=shapely.points([[18.0, 59.0], [18.001, 59.0]]), crs=4326)
    html = duckosm.page(db, "driving", levels="tags", overlays=[rs.Overlay(pts, kind="circle", label="Walls", popup=["PK"])],
                        dashboard={"panel": {"width_px": 400, "sections": [{"id": "own", "label": "Own", "html": "<p id='own-p'></p>"}]}},
                        live_data=True, page_script="window.OWN_SCRIPT = 1;", color_options={"Class": {}},
                        boundary=shapely.box(17.99, 58.99, 18.01, 59.01), minzoom={"residential": 15}).html
    assert [o["label"] for o in _opt(html, "overlays")][-1] == "Walls"           # after the base map's layers
    assert _opt(html, "dashboard")["panel"]["width_px"] == 400 and "own-p" in html
    # include / exclude: the road classes, as render_edges takes them (the tiny file's roads are residential)
    assert "residential" not in _opt(duckosm.page(db, "driving", levels="tags", exclude=["residential"]).html, "filter")["classes"]
    assert "window.OWN_SCRIPT = 1;" in html and "roadstyle:live" in html
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + len("const style = "))[0]
    assert "boundary" in {lyr["id"] for lyr in style["layers"]} and [c["name"] for c in _opt(html, "color_options")] == ["Class"] and _opt(html, "filter")["minzoom"] == {"residential": 15}


def _opt(html, key):
    """One option of the page's RS_OPTIONS (static/web_template.html), as a Python value."""
    at = html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = ")
    return json.JSONDecoder().raw_decode(html, at)[0][key]


def test_an_own_theme_extends_a_bundled_theme(tmp_path, monkeypatch):
    """theme="noise" reads ./themes/noise.yaml, as a palette is read; with `extends: grey` it states only what it changes."""
    from roadstyle import duckosm

    db = _tiny(tmp_path / "p.duckdb")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "themes").mkdir()
    (tmp_path / "themes" / "noise.yaml").write_text('extends: grey\nfeatures:\n  areas:\n    buildings: {fill: "#d6d3ce", outline: "#bdb8b0"}\n')
    _, file, _ = duckosm.theme("noise")
    grey = duckosm.theme("grey")[1]
    assert file["features"]["areas"]["buildings"]["fill"] == "#d6d3ce" and file["background"] == grey["background"]
    assert duckosm.base_map(theme="noise")["features"]["style"]["areas"]["buildings"]["outline"] == "#bdb8b0"
    assert "rsDashboard" in duckosm.page(db, "driving", levels="tags", theme="noise").html
    with pytest.raises(ValueError, match="'noise'"):
        duckosm.theme("nois")


def test_the_modes_column_names_the_modes_of_each_road():
    import pyarrow as pa

    from roadstyle import duckosm

    t = pa.table({"driving": [True, True, False, False], "walking": [True, True, True, False], "cycling": [True, False, True, False]})
    got = duckosm._with_modes(t).column("modes").to_pylist()
    assert got == ["all modes", "driving + walking", "walking + cycling", ""]


def test_auto_levels_solve_a_file_with_no_stored_levels(tmp_path):
    """levels="auto" (render_map's rule, the page's default): a file with no visualization.edge_levels is drawn with the levels that the
    engine solves, and a warning says so; levels="stored" stays an error for that file."""
    import duckdb

    from roadstyle import duckosm

    db = _tiny(tmp_path / "a.duckdb")
    con = duckdb.connect(str(db))
    con.execute("DROP TABLE IF EXISTS visualization.edge_levels; DROP TABLE IF EXISTS visualization.edge_levels_meta")
    con.close()
    with pytest.warns(UserWarning, match="no visualization.edge_levels in this file: roadstyle solved the levels; run duckosm levels to "
                                         "store them"):
        _, _, level_kw = duckosm.read(db, "driving", levels="auto")
    assert level_kw is None
    with pytest.raises(ValueError, match="duckosm levels"):
        duckosm.read(db, "driving", levels="stored")


def _two_runs(db, mode="all"):
    """Two readings of `db` at the same time on one connection, their statements interleaved (a page that draws twice): the roads and
    the base map of each."""
    import duckdb

    from roadstyle import _engine, duckosm

    r = _engine.rust()
    con = duckdb.connect(str(db), read_only=True)
    try:
        tq, cq = r.duckosm_catalog_sql(con.execute("SELECT current_database()").fetchone()[0])
        tables, columns = con.execute(tq).fetchall(), con.execute(cq).fetchall()
        a, b = (json.loads(r.duckosm_plan(tables, columns, mode, True, json.dumps(duckosm.layer_specs()))) for _ in range(2))
        assert a["run"] != b["run"]
        for x, y in zip(a["roads"], b["roads"], strict=True):     # e of a, e of b, r of a, r of b, drop e of a, drop e of b
            con.execute(x)
            con.execute(y)
        made = {p["run"]: [] for p in (a, b)}
        for la, lb in zip(a["layers"], b["layers"], strict=True):
            for p, lyr in ((a, la), (b, lb)):
                for sql in lyr["sql"]:
                    try:
                        con.execute(f"CREATE OR REPLACE TEMP TABLE {lyr['table']} AS {sql}")
                    except duckdb.Error:
                        continue
                    made[p["run"]].append(lyr["spec"])
                    break
        out = []
        for p in (a, b):
            fsel = r.duckosm_features_select(made[p["run"]], p["run"])
            out.append((con.execute(p["select"]).to_arrow_table(), con.execute(fsel).to_arrow_table() if fsel else None))
        for p in (a, b):
            con.execute(p["drop"])
        return out
    finally:
        con.close()


def test_two_readings_at_the_same_time_give_the_same_tables(tmp_path):
    """duckosm_plan's temporary tables have the run's own names: two readings at the same time on one connection do not drop or replace
    each other's tables (the duckosm-rust page: "Table with name e does not exist!")."""
    (ra, fa), (rb, fb) = _two_runs(_tiny(tmp_path / "two.duckdb"))
    assert ra.num_rows == 2 and ra.equals(rb) and fa.equals(fb)


@needs_db
def test_two_readings_at_the_same_time_on_monaco():
    (ra, fa), (rb, fb) = _two_runs(DB)
    assert ra.num_rows > 1000 and ra.equals(rb) and fa.num_rows > 1000 and fa.equals(fb)


@needs_db
def test_the_buildings_3d_button_shows_and_hides_them(tmp_path):
    """rsSetBuildings3D on duckosm.page: the dashboard finds the 3D layer by its overlay's `extrude` (the page's layers have no metadata),
    and the button under the 2D/3D button shows and hides it. Before, the button did nothing on this page."""
    pw = pytest.importorskip("playwright.sync_api")
    from roadstyle import duckosm

    out = tmp_path / "monaco.html"
    duckosm.page(DB, "all").save(str(out))
    html = out.read_text()
    ovs = json.JSONDecoder().raw_decode(html, html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = "))[0]["overlays"]
    ids = [ov["extrude"] for ov in ovs if ov.get("extrude")]
    assert ids, "Monaco has buildings with heights"
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(out.as_uri())
        pg.wait_for_selector("#rs-b3d-btn", timeout=120000)         # the dashboard has found the 3D layer
        shown = lambda: pg.evaluate("ids => ids.map(id => map.getLayoutProperty(id, 'visibility'))", ids)  # noqa: E731
        assert shown() == ["none"] * len(ids)
        pg.click("#rs-b3d-btn")
        assert shown() == ["visible"] * len(ids) and pg.evaluate("rsGetBuildings3D()")
        pg.click("#rs-b3d-btn")
        assert shown() == ["none"] * len(ids)
        browser.close()



@needs_db
def test_the_pages_own_3d_blocks_hide_the_base_maps_3d_buildings(tmp_path):
    """rs.Overlay(height_col=): the page's blocks (noise-map, 2026-11-26) replace the base map's 3D buildings while they show; hidden, the base
    map's come back."""
    pw = pytest.importorskip("playwright.sync_api")
    import geopandas as gpd
    from shapely.geometry import box

    import roadstyle as rs
    from roadstyle import duckosm
    blocks = gpd.GeoDataFrame({"h": [20.0]}, geometry=[box(7.42, 43.73, 7.421, 43.731)], crs=4326)
    out = tmp_path / "blocks.html"
    duckosm.page(DB, "all", overlays=[rs.Overlay(blocks, label="Blocks", height_col="h")]).save(str(out))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(out.as_uri())
        pg.wait_for_selector("#rs-b3d-btn", timeout=120000)
        shown = lambda: pg.evaluate("RS_OVERLAYS.filter(o => o.extrude).map(o => [!!o.base_map, map.getLayoutProperty(o.extrude, 'visibility')])")  # noqa: E731
        pg.click("#rs-b3d-btn")
        assert sorted(shown()) == [[False, "visible"], [True, "none"]]
        pg.evaluate("rsSetOverlay('Blocks', false)")
        pg.wait_for_timeout(100)
        assert sorted(shown()) == [[False, "none"], [True, "visible"]]
        browser.close()

def test_a_building_tag_of_two_digits_gives_its_height(tmp_path):
    """Bug (E): a tag of the map `tags` is read with map_extract(tags, k)[1]. With tags[k][1], DuckDB 1.5 (and duckdb-wasm) give the
    first character: building:levels '25' was '2', so 7.32 m, not 25 x 3.66 = 91.5 m. Through the reader's SQL and the engine."""
    import duckdb

    from roadstyle import duckosm

    db = _tiny(tmp_path / "b.duckdb")
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE features.buildings (osm_id BIGINT, kind VARCHAR, name VARCHAR, tags MAP(VARCHAR, VARCHAR), geom GEOMETRY)")
    con.execute("INSERT INTO features.buildings VALUES (7, 'building', '', MAP {'building:levels': '25'}, "
                "'POLYGON((7.400 43.730, 7.401 43.730, 7.401 43.731, 7.400 43.731, 7.400 43.730))'::GEOMETRY)")
    con.close()
    _, features, _ = duckosm.read(db, "driving", levels="tags", layers=["buildings"])
    assert features.column("levels").to_pylist() == ["25"]
    html = duckosm.page(db, "driving", levels="tags", layers=["buildings"], tiles=False).html       # tiles=False: the height is in the page's GeoJSON
    assert '"height":91.5' in html.replace(" ", ""), "the building's height in the page's base map"


def _old_levels(db, ids=(1, 2)):
    """The stored levels as roadstyle 0.17.1 wrote them (`save_levels`): edge_levels with the four numbers, and a meta row with `method` and no
    `source`. Returns the bytes of the file's tables' content for the check that a read does not write."""
    import duckdb
    import numpy as np

    from roadstyle.levels_store import _hash

    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA visualization")
    con.execute("CREATE TABLE visualization.edge_levels(edge_id BIGINT, casing_start INTEGER, casing_level INTEGER, casing_end INTEGER, fill_level INTEGER)")
    con.execute("INSERT INTO visualization.edge_levels VALUES " + ", ".join(f"({i}, 0, 1, 0, {k + 1})" for k, i in enumerate(ids)))
    con.execute(f"CREATE TABLE visualization.edge_levels_meta AS SELECT 'solve' AS method, 5.0 AS head_m, 10.0 AS band_dist, 1.0 AS margin, "
                f"20 AS max_level, {len(ids)} AS n_edges, '{_hash(np.array(ids, dtype='int64'))}' AS edge_hash, '0.17.1' AS roadstyle_version")
    con.close()
    return db


def test_a_file_with_levels_of_roadstyle_0_17_1_reads_and_is_not_changed(tmp_path):
    """The stored levels of roadstyle 0.17.1 (the four numbers, no heads and caps; a meta row with `method`, no `source`) are read as they are:
    the method is the source, the heads and caps are NULL (the default ends), and the file is not written."""
    pytest.importorskip("pyarrow")
    from roadstyle import duckosm

    db = _old_levels(_tiny(tmp_path / "old.duckdb"))
    before = db.read_bytes()
    roads, _, level_kw = duckosm.read(db, "driving", levels="stored")
    assert level_kw["n_edges"] == 2 and level_kw["edge_hash"]
    by_edge = {r["edge_id"]: r for r in roads.to_pylist()}
    assert [by_edge[i]["fill_level"] for i in (1, 2)] == [1, 2] and by_edge[1]["casing_level"] == 1
    assert all(by_edge[i][c] is None for i in (1, 2) for c in ("head_start_m", "head_end_m", "cap_start", "cap_end"))
    assert db.read_bytes() == before, "a read does not write the file"
    # the one-mode map (only=True) checks the stored rows of its roads the same way
    _, _, subset_kw = duckosm.read(db, "driving", levels="stored", only=True)
    assert subset_kw["n_edges"] == 2


def test_a_meta_row_that_has_neither_source_nor_method_is_not_from_a_level_area(tmp_path):
    import duckdb

    pytest.importorskip("pyarrow")
    from roadstyle import duckosm

    db = _old_levels(_tiny(tmp_path / "odd.duckdb"))
    con = duckdb.connect(str(db))
    con.execute("CREATE OR REPLACE TABLE visualization.edge_levels_meta AS SELECT 2 AS n_edges, 'x' AS edge_hash")
    con.close()
    with pytest.raises(ValueError, match="not from a level area"):
        duckosm.read(db, "driving", levels="stored")


@needs_db
def test_the_page_without_a_dashboard_is_the_dashboard_without_a_panel():
    """duckosm.page(dashboard=False) is the dashboard form (the toolbox over a full-window map) with no panel; dashboard=True adds the panel."""
    from roadstyle import duckosm

    bare, full = duckosm.page(DB, "all").html, duckosm.page(DB, "all", dashboard=True).html
    assert '"template":"dashboard"' in bare and '"layout":"overlay"' in bare and 'id="sb"' not in bare
    assert '"template":"dashboard"' in full and 'id="sb"' in full


@needs_db
def test_the_tiled_page_draws_few_arrows():
    """duckosm.page (tiled): the arrows repeat along the slots, so the page thins them: odd slots only (the names are on the even ones), main
    classes below zoom 17. At Monaco's Boulevard Princesse Charlotte, zoom 16.5, they were 85; now they are a few, and not none."""
    pw = pytest.importorskip("playwright.sync_api")
    from roadstyle import duckosm

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "monaco.html"
        duckosm.page(DB, "all").save(str(out))
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            pg = browser.new_page(viewport={"width": 1000, "height": 700})
            pg.goto(out.as_uri())
            pg.wait_for_function("typeof window.map?.loaded === 'function' && map.loaded()", timeout=90000)
            pg.evaluate("map.jumpTo({center: [7.4189, 43.7316], zoom: 16.5})")
            pg.wait_for_function("map.loaded()", timeout=60000)
            pg.wait_for_timeout(2500)
            n = pg.evaluate("map.queryRenderedFeatures({layers: map.getStyle().layers.filter(l => /roads-arrows/.test(l.id)).map(l => l.id)}).length")
            browser.close()
    assert 0 < n < 30, n


@needs_db
def test_the_page_draws_the_base_maps_textures_and_icons(tmp_path):
    """duckosm.page: the base map's patterns and icons (RS_OPTIONS.images; the page writer takes them from roadstyle:images) are in the map
    at their size, and no image is "not found". The road arrow is not among them: arrows.js draws it."""
    pw = pytest.importorskip("playwright.sync_api")
    from roadstyle import duckosm

    out = tmp_path / "monaco.html"
    duckosm.page(DB, "all").save(str(out))
    html = out.read_text()
    images = json.JSONDecoder().raw_decode(html, html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = "))[0]["images"]
    assert "ms-pat-wetland" in images and "ms-icon-bicycle" in images and "rs-oneway" not in images
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 900, "height": 700})
        console = []
        pg.on("console", lambda m: console.append((m.type, m.text)))
        pg.goto(out.as_uri())
        pg.wait_for_function("typeof window.map?.loaded === 'function' && map.loaded()", timeout=90000)
        pg.wait_for_function("ids => ids.every(i => map.getImage(i) && map.getImage(i).data.width > 1)", arg=sorted(images), timeout=30000)
        browser.close()
    assert not [t for k, t in console if "could not be loaded" in t or "could not be read" in t], console


def test_the_base_map_layers_are_marked_and_a_wrong_base_map_key_is_an_error(tmp_path):
    """The area's own base-map layers carry `base_map` in the page's overlays (the base-map box's one switch takes them), the page's own do not. A key that
    is not a base map of the page is an error that lists them (before, rsSetBasemap returned and nothing changed)."""
    pw = pytest.importorskip("playwright.sync_api")
    import shapely

    import roadstyle as rs
    from roadstyle import duckosm

    pts = __import__("geopandas").GeoDataFrame({"PK": [1]}, geometry=shapely.points([[7.405, 43.73]]), crs=4326)
    out = tmp_path / "b.html"
    duckosm.page(_tiny(tmp_path / "b.duckdb"), "driving", levels="tags", overlays=[rs.Overlay(pts, kind="circle", label="Walls")]).save(str(out))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("https://**/*", lambda r: r.abort())
        pg.goto(out.as_uri())
        pg.wait_for_function("window.map && map.loaded && map.loaded() && window.RS_OVERLAYS", timeout=120000)
        assert pg.evaluate("Object.fromEntries(RS_OVERLAYS.map(o => [o.label, !!o.base_map]))") == {"water": True, "Walls": False}
        first = pg.evaluate("RS_BASEMAPS[0].key")
        msg = pg.evaluate("(() => { try { rsSetBasemap('ofm_nothing'); } catch(e) { return e.message; } })()")
        assert "not a base map of this page" in msg and first in msg, msg
        browser.close()
    assert errors == []


def test_the_base_map_layers_switch_keeps_the_pages_overlays_and_rs_set_roads_keeps_the_names(tmp_path):
    """The one switch of the base-map box ("Base map layers" on a duckOSM page) turns the base map's layers off, not the page's own overlays. rsSetRoads(false)
    hides every road layer and keeps the street names (labels: true); shown again, each layer has its visibility back; rs.getState and rs.setState have it."""
    pw = pytest.importorskip("playwright.sync_api")
    import shapely

    import roadstyle as rs
    from roadstyle import duckosm

    pts = __import__("geopandas").GeoDataFrame({"PK": [1]}, geometry=shapely.points([[7.405, 43.73]]), crs=4326)
    out = tmp_path / "r.html"
    db = _tiny(tmp_path / "r.duckdb")
    with __import__("duckdb").connect(str(db)) as con:
        con.execute("UPDATE driving.edges SET oneway = true WHERE edge_id = 1")      # a one-way road: the page has its arrow layer
    page = duckosm.page(db, "driving", levels="tags", overlays=[rs.Overlay(pts, kind="circle", label="Walls")],
                        dashboard={"toolbar": {}})
    assert _opt(page.html, "overlays_label") == "Base map layers"
    page.save(str(out))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("https://**/*", lambda r: r.abort())
        pg.goto(out.as_uri())
        pg.wait_for_function("window.map && map.loaded && map.loaded() && window.RS_OVERLAYS && window.rs", timeout=120000)
        pg.evaluate("rsSetOverlays(false)")
        assert pg.evaluate("Object.fromEntries(RS_OVERLAYS.map(o => [o.label, o.visible]))") == {"water": False, "Walls": True}
        assert not pg.evaluate("rsGetOverlays()")
        roads = """map.getStyle().layers.filter(l => ['simple', 'slots'].includes(l['source-layer'] || l.source))
                   .map(l => [l.id, l.type === 'symbol' && !!l.layout['text-field'], map.getLayoutProperty(l.id, 'visibility') || 'visible'])"""
        before = pg.evaluate(roads)
        assert any(name for _, name, _ in before) and any(not name for _, name, _ in before), before
        pg.evaluate("rs.on('state', s => { window.__st = s; }); rsSetRoads(false)")
        assert all(vis == ("visible" if name else "none") for _, name, vis in pg.evaluate(roads))
        assert pg.evaluate("rs.getState().roads") == {"on": False, "labels": True} and pg.evaluate("window.__st.roads.on") is False
        pg.evaluate("rsSetRoads(false, {labels: false})")
        assert all(vis == "none" for _, _, vis in pg.evaluate(roads))
        arrows = pg.evaluate("map.getStyle().layers.filter(l => l.type === 'symbol' && JSON.stringify(l.layout['icon-image'] || '').includes('rs-oneway')).map(l => l.id)")
        assert arrows, "the page has an arrow layer"
        pg.evaluate("rsSetArrows(true); document.dispatchEvent(new Event('rs:toprowschange'))")     # another switch of a road layer: the roads stay hidden
        assert all(vis == "none" for _, _, vis in pg.evaluate(roads))
        pg.evaluate("rsSetArrows(false)")                                # the arrows' switch off while the roads are hidden: off after rsSetRoads(true)
        pg.evaluate("rs.setState({roads: {on: true}})")
        assert pg.evaluate("ids => ids.map(id => map.getLayoutProperty(id, 'visibility'))", arrows) == ["none"] * len(arrows)
        pg.evaluate("rsSetArrows(true)")
        assert pg.evaluate(roads) == before
        browser.close()
    assert errors == []

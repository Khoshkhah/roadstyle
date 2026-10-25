"""The duckOSM reader (roadstyle.duckosm, with the Rust engine's SQL, roadstyle_io::duckosm): a duckOSM file's roads are the roads that
mapstyle's render_map gives roadstyle, value for value and in the same order, plus `source` and `target` (R13). The tests of Monaco need a
duckOSM file with features.* and stored levels ($DUCKOSM_DB, else ../duckOSM/monaco.duckdb beside this repository) and mapstyle:
skipped without them (CI has neither); the tests of a tiny file made here run everywhere."""
import json
import os
from pathlib import Path

import pytest

DB = Path(os.environ.get("DUCKOSM_DB") or Path(__file__).resolve().parents[1].parent / "duckOSM" / "monaco.duckdb")
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")
needs_db = pytest.mark.skipif(not DB.is_file(), reason=f"no duckOSM file at {DB}")


@needs_db
@pytest.mark.parametrize("mode", ["all", "walking"])
def test_the_roads_are_mapstyles(mode):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    render_map = pytest.importorskip("mapstyle.map").render_map
    from roadstyle import duckosm

    got = {}
    render_map(DB, mode, layers=False, _export=lambda roads, *a: got.update(roads=roads))
    ref = got["roads"]
    roads, features, levels = duckosm.read(DB, mode, layers=False)
    assert features is None and set(levels) == {"edge_hash", "n_edges"}
    a = roads.to_pandas()
    assert len(a) == len(ref) and set(a.columns) - set(ref.columns) == {"source", "target"}
    norm = lambda n: lambda v: None if v is None or pd.isna(v) else (str(v) if n in ("edge_id", "osm_id") else v)  # noqa: E731
    for n in (c for c in ref.columns if c != "geometry"):
        assert list(map(norm(n), a[n])) == list(map(norm(n), ref[n])), n


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

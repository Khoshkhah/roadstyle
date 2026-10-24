"""The duckOSM reader (roadstyle.duckosm, with the Rust engine's SQL, roadstyle_io::duckosm): a duckOSM file's roads are the roads that
mapstyle's render_map gives roadstyle, value for value and in the same order, plus `source` and `target` (R13). It needs a duckOSM file
with features.* and stored levels ($DUCKOSM_DB, else ../duckOSM/monaco.duckdb beside this repository) and mapstyle: skipped without
them (CI has neither)."""
import json
import os
from pathlib import Path

import pytest

DB = Path(os.environ.get("DUCKOSM_DB") or Path(__file__).resolve().parents[1].parent / "duckOSM" / "monaco.duckdb")
pytestmark = [pytest.mark.skipif(not DB.is_file(), reason=f"no duckOSM file at {DB}"),
              pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")]


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


# the maps of one mode (only=True) also differ in two engine rules (2026-10-24, the same roads in both engines): the name slots (slots.rs:
# 87 of 2,111 slots of walking name another road row) and edge_attach (overlays.rs: 1 to 2 points of a layer on another road, a tie)
_ONE_MODE = pytest.mark.xfail(strict=True, reason="a map of one mode: the Rust engine's slots and edge_attach differ from Python's")


# ponytail: xfail until the Rust engine's 3D decks equal Python's on all of Monaco (decks.rs, 2026-10-24: 1,312 decks, Python 1,311, other
# slabs and properties for the same roads; tests/test_engine_parity.py's area does not show it). strict: the test fails when they match.
@pytest.mark.xfail(strict=True, reason="the Rust engine's 3D decks differ from Python's on all of Monaco (decks.rs)")
@pytest.mark.parametrize("choice", ["all osm google", "driving osm google", "walking osm google", "cycling osm google", "all grey google",
                                    "walking google komoot", pytest.param("driving osm google only", marks=_ONE_MODE),
                                    pytest.param("walking osm google only", marks=_ONE_MODE)])
def test_the_style_is_mapstyles(choice):
    """The style of roadstyle.duckosm.export_inline (the reader, the base map's look and stage 1 in Rust) has the normalised digest of
    today's mapstyle export_inline of the same choice (tests/make_mapstyle_goldens.py: the rules of `normalised`, each with its reason)."""
    from roadstyle import duckosm

    gen, digests = _goldens()
    mode, theme, paths, *only = choice.split()
    style = duckosm.export_inline(DB, mode, theme=theme, paths=paths, only=bool(only))
    assert gen.digest(gen.normalised(style)) == digests[gen.name_of(mode, theme, paths, bool(only))]["normalised"]


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

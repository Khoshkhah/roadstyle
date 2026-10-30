"""Item 8: render_edges(..., levels_db=file) reads the stored drawing order for some of the edges."""
import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import LineString

import roadstyle as rs
from roadstyle.levels_store import AREA_COLS, LEVEL_KWARGS

BIG = 2**60 + 12345                                       # past 2**53: a float or a text id would round


def _edges(ids):
    return gpd.GeoDataFrame({"highway": ["primary"] * len(ids), "edge_id": ids},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.301)]) for i in range(len(ids))], crs=4326)


def _db(tmp_path, ids, meta=True):
    path = tmp_path / "area.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA visualization")
    rows = ", ".join(f"({i}, {k}, {k}, {k}, {k + 1}, 0.0, 0.0, NULL, NULL)" for k, i in enumerate(ids))
    con.execute("CREATE TABLE visualization.edge_levels(edge_id BIGINT, " + ", ".join(f"{c} DOUBLE" if c.endswith("_m") else f"{c} {'VARCHAR' if c.startswith('cap') else 'INTEGER'}" for c in AREA_COLS) + f") ; INSERT INTO visualization.edge_levels VALUES {rows}")
    if meta:
        con.execute(f"CREATE TABLE visualization.edge_levels_meta AS SELECT 'area' AS source, 'x' AS area, {len(ids)} AS n_edges, 'h' AS edge_hash")
    con.close()
    return path


def test_levels_db_reads_some_of_the_edges_int_or_text_ids(tmp_path):
    every = [1, 2, BIG, 4]
    db = _db(tmp_path, every)
    part = [BIG, 2]                                       # a map of some edges, in another order
    by_hand = _edges(part)                                # row k of the file has every number k (fill k + 1); BIG is row 2, 2 is row 1
    for c in AREA_COLS:
        by_hand[c] = [None, None] if c.startswith("cap") else [2 + (c == "fill_level"), 1 + (c == "fill_level")] if not c.endswith("_m") else [0.0, 0.0]
    want = rs.render_edges(by_hand, basemap="blank", **LEVEL_KWARGS).html
    assert rs.render_edges(_edges(part), basemap="blank", levels_db=db).html == want
    text = _edges(part)
    text["edge_id"] = text["edge_id"].astype(str)
    assert rs.render_edges(text, basemap="blank", levels_db=db).html                  # a text id reads the same row


def test_levels_db_errors(tmp_path):
    db = _db(tmp_path, [1, 2])
    with pytest.raises(ValueError, match="not edges the stored levels were solved for"):
        rs.render_edges(_edges([1, 3]), basemap="blank", levels_db=db)
    with pytest.raises(ValueError, match="two drawing orders"):
        rs.render_edges(_edges([1, 2]), basemap="blank", levels_db=db, fill_level_col="x")
    with pytest.raises(ValueError, match="edge_levels_meta"):
        rs.render_edges(_edges([1, 2]), basemap="blank", levels_db=_db(tmp_path / "..", [1, 2], meta=False))


def _old_db(tmp_path, ids):
    """The stored levels as roadstyle 0.17.1 wrote them: the four numbers, and a meta row with `method` and no `source`."""
    import numpy as np

    from roadstyle.levels_store import _hash

    path = tmp_path / "old.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA visualization")
    rows = ", ".join(f"({i}, {k}, {k}, {k}, {k + 1})" for k, i in enumerate(ids))
    con.execute(f"CREATE TABLE visualization.edge_levels(edge_id BIGINT, casing_start INTEGER, casing_level INTEGER, casing_end INTEGER, fill_level INTEGER); "
                f"INSERT INTO visualization.edge_levels VALUES {rows}")
    con.execute(f"CREATE TABLE visualization.edge_levels_meta AS SELECT 'solve' AS method, 5.0 AS head_m, {len(ids)} AS n_edges, "
                f"'{_hash(np.array(ids, dtype='int64'))}' AS edge_hash, '0.17.1' AS roadstyle_version")
    con.close()
    return path


def test_levels_db_reads_the_numbers_of_roadstyle_0_17_1_and_does_not_write(tmp_path):
    every = [1, 2, BIG, 4]
    db = _old_db(tmp_path, every)
    before = db.read_bytes()
    part = [BIG, 2]
    by_hand = _edges(part)                                # row k has every number k (fill k + 1); BIG is row 2, 2 is row 1; no heads, no caps
    for c in AREA_COLS:
        by_hand[c] = [None, None] if c.endswith("_m") or c.startswith("cap") else [2 + (c == "fill_level"), 1 + (c == "fill_level")]
    want = rs.render_edges(by_hand, basemap="blank", **LEVEL_KWARGS).html
    assert rs.render_edges(_edges(part), basemap="blank", levels_db=db).html == want
    assert db.read_bytes() == before
    with pytest.raises(ValueError, match="not edges the stored levels were solved for"):
        rs.render_edges(_edges([1, 3]), basemap="blank", levels_db=db)

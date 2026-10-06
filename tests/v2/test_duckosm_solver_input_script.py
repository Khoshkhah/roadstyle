"""Tests for preparing combined DuckOSM solver inputs."""

import json

import pytest
from shapely.geometry import LineString

from roadstyle.v2.engine.pairs import read_pair_table
from roadstyle.v2.engine.solver import solve_stacking, write_pair_tables
from scripts.v2.prepare_duckosm_solver_input import (
    load_duckosm_corridors,
    read_corridor_geojson,
    write_corridor_geojson,
)

duckdb = pytest.importorskip("duckdb")


def test_duckosm_modes_export_combined_solver_inputs(tmp_path):
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE SCHEMA driving")
    connection.execute(
        "CREATE TABLE driving.edges "
        "(edge_id VARCHAR, osm_id BIGINT, highway VARCHAR, band INTEGER, geom BLOB)"
    )
    forward = LineString([(0, 0), (100, 0)])
    reverse = LineString([(100, 0), (0, 0)])
    connection.executemany(
        "INSERT INTO driving.edges VALUES (?, ?, ?, ?, ?)",
        [
            ("drive-forward", 10, "primary", 0, forward.wkb),
            ("drive-reverse", 10, "primary", 0, reverse.wkb),
        ],
    )
    connection.execute("CREATE SCHEMA walking")
    connection.execute(
        "CREATE TABLE walking.edges "
        "(edge_id VARCHAR, osm_id BIGINT, highway VARCHAR, band INTEGER, geom BLOB)"
    )
    bridge = LineString([(50, -50), (50, 50)])
    connection.execute(
        "INSERT INTO walking.edges VALUES (?, ?, ?, ?, ?)",
        ["walk-bridge", 20, "footway", 1, bridge.wkb],
    )

    corridors, modes = load_duckosm_corridors(connection)
    corridor_path = tmp_path / "corridors.geojson"
    pairs_path = tmp_path / "road_pairs_original.csv"
    overrides_path = tmp_path / "road_pairs_overrides.csv"
    write_corridor_geojson(corridors, corridor_path)
    write_pair_tables(corridors, pairs_path, overrides_path)
    loaded_corridors = read_corridor_geojson(corridor_path)
    solution = solve_stacking(loaded_corridors, pair_table=pairs_path)
    pair_rows = read_pair_table(pairs_path)

    assert modes == ["driving", "walking"]
    assert len(loaded_corridors) == 3
    assert solution.info["direction_twin_count"] == 1
    assert solution.fill_levels[0] == solution.fill_levels[1]
    assert solution.casing_levels[0] == tuple(reversed(solution.casing_levels[1]))
    assert {corridor.band for corridor in loaded_corridors} == {0, 1}
    assert all(corridor.properties["mode"] in modes for corridor in loaded_corridors)
    assert {row["edge_a"] for row in pair_rows} | {row["edge_b"] for row in pair_rows} == {
        corridor.properties["edge_ref"] for corridor in loaded_corridors
    }
    assert len(json.loads(corridor_path.read_text())["features"]) == 3
    assert read_pair_table(overrides_path, overrides=True) == []

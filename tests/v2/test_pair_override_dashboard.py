"""Tests for pair-editor override row construction and validation."""

import importlib

import pytest

pair_tables = importlib.import_module("roadstyle.v2.engine.pairs")
read_pair_table = pair_tables.read_pair_table
write_pair_table = pair_tables.write_pair_table
dashboard = importlib.import_module("scripts.v2.pair_override_dashboard")


def _original_pair():
    return {
        "pair_id": "original-pair",
        "relation": "near",
        "edge_a": "road-a",
        "edge_b": "road-b",
        "node_ref": "",
        "endpoint_a": "",
        "endpoint_b": "",
        "upper_edge_ref": "road-a",
        "lower_edge_ref": "road-b",
        "enabled": "true",
    }


def test_new_stacking_override_has_all_required_fields():
    override = dashboard._new_pair_override(
        "cross",
        "bridge",
        "surface",
        upper="bridge",
        lower="surface",
    )

    assert override["action"] == "add"
    assert override["relation"] == "cross"
    assert override["edge_a"] == "bridge"
    assert override["edge_b"] == "surface"
    assert override["upper_edge_ref"] == "bridge"
    assert override["lower_edge_ref"] == "surface"
    assert len(override["pair_id"]) == 20
    dashboard._validate_overrides(
        [_original_pair()],
        [override],
        known_refs={"road-a", "road-b", "bridge", "surface"},
    )


def test_connection_override_needs_head_sides_but_not_a_node():
    override = dashboard._new_pair_override(
        "connect",
        "road-a",
        "road-b",
        endpoint_a="end",
        endpoint_b="start",
    )
    dashboard._validate_overrides(
        [_original_pair()],
        [override],
        known_refs={"road-a", "road-b"},
    )
    override["endpoint_a"] = ""
    with pytest.raises(ValueError, match="endpoint_a"):
        dashboard._validate_overrides([_original_pair()], [override])


def test_override_dashboard_rejects_edges_not_in_corridor_input():
    override = dashboard._new_pair_override(
        "order",
        "missing-road",
        "road-b",
        upper="missing-road",
        lower="road-b",
    )

    with pytest.raises(ValueError, match="unknown edge"):
        dashboard._validate_overrides(
            [_original_pair()],
            [override],
            known_refs={"road-a", "road-b"},
        )


def test_connection_must_use_the_selected_road_endpoints():
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[0, 0], [1, 1]],
            },
            "properties": {"edge_ref": "road-a"},
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[1, 1], [2, 2]],
            },
            "properties": {"edge_ref": "road-b"},
        },
    ]
    original = [{
        **_original_pair(),
        "relation": "connect",
        "node_ref": "1.0000000,1.0000000",
        "endpoint_a": "end",
        "endpoint_b": "start",
        "upper_edge_ref": "",
        "lower_edge_ref": "",
    }]
    dashboard._validate_overrides(
        original,
        [],
        known_refs={"road-a", "road-b"},
        features=features,
    )
    original[0]["node_ref"] = "0.0000000,0.0000000"
    # A stale original row is solver output and must not block saving other overrides.
    dashboard._validate_overrides(original, [], features=features)
    bad = dashboard._new_pair_override(
        "connect", "road-a", "road-b",
        node_ref="0.0000000,0.0000000", endpoint_a="end", endpoint_b="start",
    )
    warnings = dashboard._validate_overrides(original, [bad], features=features)
    assert len(warnings) == 2 and all("does not match" in item for item in warnings)


def test_coordinate_free_connection_allows_different_geometry_endpoints():
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            "properties": {"edge_ref": "road-a"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[2, 2], [3, 3]]},
            "properties": {"edge_ref": "road-b"},
        },
    ]
    override = dashboard._new_pair_override(
        "connect",
        "road-a",
        "road-b",
        endpoint_a="end",
        endpoint_b="start",
    )

    dashboard._validate_overrides(
        [_original_pair()],
        [override],
        known_refs={"road-a", "road-b"},
        features=features,
    )


def test_save_writes_validated_overrides_csv(tmp_path):
    override = dashboard._new_pair_override(
        "order",
        "road-a",
        "road-b",
        upper="road-a",
        lower="road-b",
    )
    output = tmp_path / "overrides.csv"

    dashboard._save_overrides(
        output,
        [_original_pair()],
        [override],
        known_refs={"road-a", "road-b"},
    )

    assert output.exists()
    assert dashboard.read_pair_table(output, overrides=True) == [override]


def test_editor_page_reuses_embedded_maplibre_map():
    map_path = dashboard.DEFAULT_MAP_HTML

    page = dashboard._render_editor_page(map_path)

    assert "window.__pairEditorMap = new maplibregl.Map" in page
    assert "window.__pairEditorStyleSpec = " in page
    assert '<script src="/pair_override_editor.js"></script>' in page


def test_embedded_map_features_have_unique_corridor_references():
    features = dashboard._load_map_features(dashboard.DEFAULT_MAP_HTML)
    refs = [feature["properties"]["edge_ref"] for feature in features]

    assert len(features) > 100
    assert len(refs) == len(set(refs))


def test_map_selected_pair_builds_replace_override():
    original = _original_pair()
    override = dashboard._pair_override_from_selection(
        "near",
        "road-a",
        "road-b",
        upper="road-b",
        lower="road-a",
        existing=original,
    )

    assert override["action"] == "replace"
    assert override["pair_id"] == original["pair_id"]
    assert override["upper_edge_ref"] == "road-b"
    assert override["lower_edge_ref"] == "road-a"


def test_map_selected_pair_rejects_the_same_road_twice():
    with pytest.raises(ValueError, match="two different roads"):
        dashboard._pair_override_from_selection("near", "road-a", "road-a")


def test_local_save_endpoint_helper_writes_only_requested_override(tmp_path):
    original_path = tmp_path / "original.csv"
    override_path = tmp_path / "overrides.csv"
    write_pair_table(original_path, [_original_pair()])
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            "properties": {"edge_ref": "road-a"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[0, 1], [1, 0]]},
            "properties": {"edge_ref": "road-b"},
        },
    ]
    row = dashboard._new_pair_override(
        "order",
        "road-a",
        "road-b",
        upper="road-a",
        lower="road-b",
    )
    row["edge_a"] = "road-a"
    row["edge_b"] = "road-b"

    saved = dashboard._save_override(
        row,
        original_path,
        override_path,
        {"road-a", "road-b"},
        features,
    )

    assert dashboard.read_pair_table(override_path, overrides=True) == saved
    assert saved == [row]


def test_delete_override_removes_only_the_requested_row(tmp_path):
    path = tmp_path / "overrides.csv"
    first = dashboard._new_pair_override(
        "order", "road-a", "road-b", upper="road-a", lower="road-b"
    )
    second = dashboard._new_pair_override(
        "order", "road-a", "road-b", upper="road-b", lower="road-a"
    )
    write_pair_table(path, [first, second], overrides=True)

    remaining = dashboard._delete_override(first["pair_id"], path)

    assert remaining == [second]
    assert dashboard.read_pair_table(path, overrides=True) == [second]


def test_delete_override_rejects_unknown_pair_id(tmp_path):
    path = tmp_path / "overrides.csv"
    write_pair_table(path, [], overrides=True)

    with pytest.raises(ValueError, match="does not exist"):
        dashboard._delete_override("missing-pair", path)


def test_delete_override_keeps_a_backup_of_the_previous_file(tmp_path):
    from roadstyle.v2.engine.pairs import read_pair_table

    path = tmp_path / "road_pairs_overrides.csv"
    row = dashboard._new_pair_override("near", "road-a", "road-b")
    dashboard.write_pair_table(path, [row], overrides=True)
    assert dashboard._delete_override(row["pair_id"], path) == []
    backup = tmp_path / "road_pairs_overrides.deleted-backup.csv"
    assert [r["pair_id"] for r in read_pair_table(backup, overrides=True)] == [row["pair_id"]]

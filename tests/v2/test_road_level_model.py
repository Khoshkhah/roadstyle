import sys
from pathlib import Path

from shapely.geometry import LineString

from roadstyle.v2.engine.pairs import discover_pair_table, write_pair_table
from roadstyle.v2.engine.primitives import Corridor

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "v2"))

from build_road_levels import RoadLevelModel, build  # noqa: E402


def _corridors():
    lines = {"a": [(0, 0), (0.001, 0)], "b": [(0.0005, -0.0005), (0.0005, 0.0005)]}
    return [
        Corridor(
            geometry=LineString(coords), id=ref, split_start=15, split_end=15,
            properties={"edge_ref": ref},
        )
        for ref, coords in lines.items()
    ]


def test_build_writes_original_and_levels_without_touching_overrides(tmp_path):
    overrides = tmp_path / "overrides.csv"
    original = tmp_path / "original.csv"
    levels = tmp_path / "levels.csv"
    build(_corridors(), original, overrides, levels)
    assert original.read_text().startswith("pair_id,relation")
    assert levels.read_text().splitlines()[0] == "edge_ref,physical_road_id,band,cs,cm,ce,fl"
    assert len(levels.read_text().splitlines()) == 3
    assert not overrides.exists()


def test_model_returns_features_carrying_solved_levels(tmp_path):
    corridors = _corridors()
    original = tmp_path / "original.csv"
    write_pair_table(original, discover_pair_table(corridors))
    base = [{"properties": {"_type": "corridor_fill", "edge_ref": "a", "fill_color": "#123456"}}]
    result = RoadLevelModel(corridors, original, base).recalculate([], tmp_path / "levels.csv")
    fills = [f for f in result["features"] if f["properties"]["_type"] == "corridor_fill"]
    assert {f["properties"]["edge_ref"] for f in fills} == {"a", "b"}
    assert next(f for f in fills if f["properties"]["edge_ref"] == "a")["properties"]["fill_color"] == "#123456"
    assert result["summary"]["roads"] == 2

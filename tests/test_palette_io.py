"""Palette JSON I/O: serialise/deserialise palettes without losing fidelity."""
import json

from roadstyle import (
    HIGHSAT,
    PALETTES,
    RoadStyle,
    load_palette,
    palette_from_dict,
    palette_to_dict,
    save_palette,
)


def test_roadstyle_dict_round_trip():
    rs = RoadStyle("#00E5FF", 6.0, 8.0, "#007785", "#000000", dash=(4, 4), opacity=0.9)
    assert RoadStyle.from_dict(rs.to_dict()) == rs


def test_roadstyle_dash_becomes_list_in_dict():
    d = RoadStyle("#fff", 2, 4, dash=(6, 4)).to_dict()
    assert d["dash"] == [6, 4]          # JSON has no tuples
    assert isinstance(json.dumps(d), str)   # fully JSON-serialisable


def test_roadstyle_from_minimal_dict():
    rs = RoadStyle.from_dict({"fill": "#abcdef", "width": 3, "casing_width": 5})
    assert rs.fill == "#abcdef" and rs.casing_dark == "#000000" and rs.dash is None


def test_from_dict_missing_required_keys_raises():
    import pytest

    with pytest.raises(ValueError):
        RoadStyle.from_dict({"fill": "#fff"})


def test_palette_dict_round_trip_preserves_highsat():
    restored = palette_from_dict(palette_to_dict("highsat"))
    assert restored == HIGHSAT


def test_save_then_load_palette_file(tmp_path):
    path = tmp_path / "highsat.json"
    save_palette("highsat", path)
    payload = json.loads(path.read_text())
    assert payload["name"] == "highsat" and "motorway" in payload["roads"]

    loaded = load_palette(path, register=True)
    assert loaded == HIGHSAT
    assert PALETTES["highsat"] == HIGHSAT   # registered (idempotent here)


def test_load_bare_mapping(tmp_path):
    path = tmp_path / "mini.json"
    path.write_text(json.dumps({"a": {"fill": "#fff", "width": 2, "casing_width": 4}}))
    table = load_palette(path, register=False)
    assert set(table) == {"a"} and table["a"].fill == "#fff"

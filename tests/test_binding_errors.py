"""The Rust engine's errors in Python (docs/design/t4_python_binding.md, section 3): each facade error kind is its class of
roadstyle.errors, and each class is a ValueError. One bad input for each class, through the binding."""
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import roadstyle
from roadstyle import _engine

EDGES = Path(__file__).resolve().parents[1] / "rust/roadstyle-rs/tests/data/level_area/edges.parquet"
pytestmark = pytest.mark.skipif(not _engine.available(), reason="the Rust extension roadstyle._rust is not built")


def _look(args):
    return _engine.rust().resolve_look(json.dumps({"args": args}))


def test_each_kind_of_error_is_its_class_and_a_value_error():
    r, roads = _engine.rust(), pq.read_table(EDGES)
    # the data: a keyword names a column that the roads do not have (with the nearest names)
    with pytest.raises(roadstyle.DataError, match="highway_col: the roads have no column hghway .the nearest: highway"):
        r.make_style(roads, _look({"highway_col": "hghway"}), None, None, None)
    # the options: options that are not JSON, and a level area option that is not one
    with pytest.raises(roadstyle.OptionsError, match="options: not JSON"):
        r.resolve_look("{")
    with pytest.raises(roadstyle.OptionsError, match="the level area's options"):
        r.make_area(roads, "unused", json.dumps({"no_such_option": 1}))
    # the levels: a solver option that is not possible
    with pytest.raises(roadstyle.LevelsError):
        r.compute_levels(roads, "solve", ["highway", "layer", "bridge", "tunnel", "junction"], margin=0.0)
    # a file: a file that roadstyle does not have
    with pytest.raises(roadstyle.FileError):
        r.asset("no/such/file.yaml")
    # a part that the Rust engine does not draw: the binding's advice
    with pytest.raises(roadstyle.UnsupportedError, match="use engine='python'"):
        r.make_style(roads, _look({"simple": False}), None, None, None)
    for c in (roadstyle.DataError, roadstyle.OptionsError, roadstyle.LevelsError, roadstyle.FileError, roadstyle.UnsupportedError):
        assert issubclass(c, ValueError)


def test_the_look_gives_each_part_by_its_getter():
    lk = _look({"name": "x"})
    assert json.loads(lk.map())["output"]["name"] == "x"
    assert "roads" in json.loads(lk.sections()) and isinstance(lk.palette(), str)
    assert json.loads(lk.other()) == {} and isinstance(json.loads(lk.base_map_page()), dict)
    assert json.loads(lk.features()) is None and isinstance(json.loads(lk.settings()), (list, dict, type(None)))

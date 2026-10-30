"""A level area made by the Rust engine has `crossing` pair rows (a path at a node where a car road goes on: the road's head there is over the
path's fill). solve_area, and so `duckosm levels`, takes them: the Rust solver has the crossing stage, and the answer says how many it kept."""
import json
from pathlib import Path

import pytest

from roadstyle import _engine

EDGES = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-rs" / "tests" / "data" / "level_area" / "edges.parquet"
pytestmark = pytest.mark.skipif(not _engine.available(), reason="the Rust extension roadstyle._rust is not built")


def _area(tmp_path):
    import pyarrow.parquet as pq

    _engine.rust().make_area(pq.read_table(EDGES), str(tmp_path))
    return tmp_path


def test_solve_area_takes_the_crossing_rows_of_the_rust_pairs(tmp_path):
    from roadstyle.level_area import solve_area

    area = _area(tmp_path)
    rows = (area / "pairs.csv").read_text().splitlines()[1:]
    crossings = [r for r in rows if r.startswith("crossing,")]
    assert crossings, "the Monaco test area has crossings"
    solve_area(area)
    info = json.loads((area / "levels_info.json").read_text())
    assert info["crossings"] == len({tuple(r.split(",")[:4]) for r in crossings})      # one rule for each road, path and end
    assert info["crossings_not_kept"] == [] or all(len(p) == 3 for p in info["crossings_not_kept"])


def test_a_crossing_can_be_switched_off_by_an_edit(tmp_path):
    from roadstyle.level_area import solve_area

    area = _area(tmp_path)
    first = next(r for r in (area / "pairs.csv").read_text().splitlines()[1:] if r.startswith("crossing,"))
    rel, a, b, a_end, b_end = first.split(",")[:5]
    (area / "edits.csv").write_text(f"relation,a,b,a_end,b_end,enabled\n{rel},{a},{b},{a_end},{b_end},false\n")
    solve_area(area)
    assert json.loads((area / "levels_info.json").read_text())["crossings"] == len(
        {tuple(r.split(",")[:4]) for r in (area / "pairs.csv").read_text().splitlines()[1:] if r.startswith("crossing,")}) - 1


def test_the_python_engine_says_that_it_has_no_crossing_stage(tmp_path):
    from roadstyle.level_area import solve_area

    with pytest.raises(ValueError, match="crossing rows, which only the Rust engine solves"):
        solve_area(_area(tmp_path), engine="python")

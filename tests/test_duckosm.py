"""The duckOSM reader (roadstyle.duckosm, with the Rust engine's SQL, roadstyle_io::duckosm): a duckOSM file's roads are the roads that
mapstyle's render_map gives roadstyle, value for value and in the same order, plus `source` and `target` (R13). It needs a duckOSM file
with features.* and stored levels ($DUCKOSM_DB, else ../duckOSM/monaco.duckdb beside this repository) and mapstyle: skipped without
them (CI has neither)."""
import io
import os
from pathlib import Path

import pytest

DB = Path(os.environ.get("DUCKOSM_DB") or Path(__file__).resolve().parents[1].parent / "duckOSM" / "monaco.duckdb")
pytestmark = [pytest.mark.skipif(not DB.is_file(), reason=f"no duckOSM file at {DB}"),
              pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")]


@pytest.mark.parametrize("mode", ["all", "walking"])
def test_the_roads_are_mapstyles(mode):
    pd = pytest.importorskip("pandas")
    pq = pytest.importorskip("pyarrow.parquet")
    render_map = pytest.importorskip("mapstyle.map").render_map
    from roadstyle import duckosm

    got = {}
    render_map(DB, mode, layers=False, _export=lambda roads, *a: got.update(roads=roads))
    ref = got["roads"]
    roads, features, levels = duckosm.read(DB, mode, layers=False)
    assert features is None and set(levels) == {"edge_hash", "n_edges"}
    a = pq.read_table(io.BytesIO(roads)).to_pandas()
    assert len(a) == len(ref) and set(a.columns) - set(ref.columns) == {"source", "target"}
    norm = lambda n: lambda v: None if v is None or pd.isna(v) else (str(v) if n in ("edge_id", "osm_id") else v)  # noqa: E731
    for n in (c for c in ref.columns if c != "geometry"):
        assert list(map(norm(n), a[n])) == list(map(norm(n), ref[n])), n


def test_the_base_map_rows():
    pq = pytest.importorskip("pyarrow.parquet")
    from roadstyle import duckosm

    _, features, _ = duckosm.read(DB)
    t = pq.read_table(io.BytesIO(features))
    assert t.num_rows > 0 and t.schema.names[:3] == ["spec", "layer", "rid"]
    with pytest.raises(ValueError, match="unknown mode"):
        duckosm.read(DB, "boat")

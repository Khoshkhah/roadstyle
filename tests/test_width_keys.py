"""Phase 1 of docs/design/tile_contract.md: the road layer's width and offset as one table for each zoom stop, read by the piece's width key
(``__rs_wk``). The pixels do not change: every stop gives the number of the old expression for every kind, flag combination and class. The Rust
engine has the same test on the Burnaby expressions (roadstyle-engine width_key.rs)."""
import copy
import json
import warnings

import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import render_web as rw
from roadstyle.render_web import render


def test_the_tables_give_the_numbers_of_the_old_expressions(monkeypatch):
    from roadstyle.tiles import _ev
    old = {}
    real = rw._width_keys

    def spy(paint, stride):
        old["paint"], old["stride"] = copy.deepcopy(paint), stride
        return real(paint, stride)

    monkeypatch.setattr(rw, "_width_keys", spy)
    g = gpd.GeoDataFrame({"highway": ["primary", "residential"]}, geometry=[LineString([(18, 59.3), (18.001, 59.3)]), LineString([(18.001, 59.3), (18.002, 59.3)])], crs=4326)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        html = render(g, basemap="blank", tiles=True).html
    new = json.JSONDecoder().raw_decode(html, html.index("const style = ") + 14)[0]
    new = next(lyr for lyr in new["layers"] if lyr["id"] == "roads-simple")["paint"]
    stride = old["stride"]
    for prop in ("line-width", "line-offset"):
        o, n = old["paint"][prop], new[prop]
        assert len(o) == len(n) and o[3::2] == n[3::2], prop
        for i in range(4, len(o), 2):
            assert o[i][2] == n[i][2], "the live factor stays"
            for code in range(rw._WK_KINDS * 8):
                kind, pair, bridge, twoway = code // 8, code // 4 % 2 == 1, code // 2 % 2 == 1, code % 2 == 1
                for cls in range(stride):
                    p = {"__rs_k": kind, "__rs_ci": cls, **{k: True for k, on in (("__rs_pair", pair), ("__rs_bridge", bridge), ("__rs_twoway", twoway)) if on}}
                    p["__rs_wk"] = rw._wk_key(kind, pair, bridge, twoway, cls, stride)
                    assert _ev(o[i][1], p) == _ev(n[i][1], p), (prop, i, kind, pair, bridge, twoway, cls)

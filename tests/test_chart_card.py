"""The chart card from Python (docs/guides/charts.md): render_dashboard with each kind, from the map's roads and from the page's own rows (a DataFrame,
a GeoDataFrame, a list of dicts); the rows go into the page with the SQL type names, a 64-bit integer stays exact, and a wrong chart is a ValueError."""
import datetime as dt
import json

import pandas as pd
import pytest

import roadstyle as rs
from roadstyle.pages import chart_rows


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary", "residential"] * 3, "edge_id": list(range(1, 7)), "length_m": [10.0, 20, 30, 40, 50, 60]},
                            geometry=[LineString([(7.42 + i * 1e-3, 43.73), (7.42 + i * 1e-3, 43.731)]) for i in range(6)], crs=4326)


def _sections(html):
    j = html.index("{", html.index("const RS_OPTIONS = "))
    return json.JSONDecoder().raw_decode(html[j:])[0]["dashboard"]["panel"]["sections"]


def test_each_kind_goes_into_the_page_and_the_rows_keep_their_types(tmp_path):
    df = pd.DataFrame({"hour": [7, 8, 2**60 + 1], "vehicles": [820.5, None, 3.0], "busy": [True, False, True],
                       "day": [dt.date(2026, 6, 1)] * 3, "at": pd.to_datetime(["2026-06-01 08:00"] * 3), "street": ["A", "B", None]})
    cards = [{"id": k, "label": k, "part": "chart", "chart": {"kind": k, "x": "highway" if k in ("bar", "pie") else "length_m",
                                                                **({"y": "length_m"} if k == "scatter" else {})}}
             for k in ("bar", "pie", "histogram", "scatter")]
    cards.append({"id": "line", "part": "chart", "chart": {"kind": "line", "x": "hour", "y": "vehicles", "data": df}})
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"sections": cards}}).save(tmp_path / "c.html")
    secs = _sections((tmp_path / "c.html").read_text(encoding="utf-8"))
    assert [s["chart"]["kind"] for s in secs] == ["bar", "pie", "histogram", "scatter", "line"]
    data = secs[4]["chart"]["data"]
    assert data["columns"] == [{"name": "hour", "type": "BIGINT"}, {"name": "vehicles", "type": "DOUBLE"}, {"name": "busy", "type": "BOOLEAN"},
                               {"name": "day", "type": "DATE"}, {"name": "at", "type": "TIMESTAMP"}, {"name": "street", "type": "VARCHAR"}]
    assert data["rows"][0] == [7, 820.5, True, "2026-06-01", "2026-06-01 08:00:00", "A"]
    assert data["rows"][1][1] is None and data["rows"][2][5] is None
    assert data["rows"][2][0] == str(2**60 + 1)                        # a 64-bit integer as text: exact


def test_a_geodataframe_has_no_geometry_and_a_list_of_dicts_is_a_table():
    assert [c["name"] for c in chart_rows(_edges())["columns"]] == ["highway", "edge_id", "length_m"]
    assert chart_rows([{"a": "x", "b": 1}, {"a": "y"}]) == {"columns": [{"name": "a", "type": "VARCHAR"}, {"name": "b", "type": "DOUBLE"}],
                                                          "rows": [["x", 1.0], ["y", None]]}


@pytest.mark.parametrize("chart, said", [({"kind": "histogram", "x": "length_m", "y": "length_m"}, "a histogram has no `y`"),
                                         ({"kind": "bar", "x": "hour", "data": [{"h": 1}]}, "the column 'hour' is not in `data`"),
                                         ({"kind": "bar", "x": "highway", "agg": "median"}, "unknown variant")])
def test_a_wrong_chart_is_an_error(chart, said):
    with pytest.raises(ValueError, match=said):
        rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"sections": [{"id": "c", "part": "chart", "chart": chart}]}})

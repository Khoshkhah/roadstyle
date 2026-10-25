"""The page's keys of a call (sidebar, popup_mode, ...) go into page_from's `given` by one rule, roadstyle::page_options::given_of: the
look's other keywords, and name and road_popup of the call. Python's page (_engine.page_given) and the wasm page (makePage, Roads.page:
the studio) use it, so the same keywords give the same page. Before, the wasm page lost them (the studio's Dashboard and Report pages had
no sidebar)."""
import json
import os
import pathlib
import shutil
import subprocess

import pytest

from roadstyle import _engine

ROOT = pathlib.Path(__file__).parents[1]
DATA = ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "monaco_part" / "roads.parquet"
PKG = ROOT / "rust" / "roadstyle-wasm" / "pkg" / "roadstyle_wasm.js"
ARGS = {"state": "live", "basemap": "blank", "sidebar": "dashboard", "popup_mode": "panel", "find_control": True, "name": "Monaco",
        "road_popup": ["highway", "name"]}
KEYS = ("sidebar", "popup_mode", "find_control", "name", "road_popup", "basemap_switcher", "filter_control")


def _opts(html):
    return json.JSONDecoder().raw_decode(html, html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = "))[0]


@pytest.mark.skipif(not _engine.available(), reason="no roadstyle._rust")
def test_given_of_has_the_calls_page_keys():
    o = {"args": ARGS}
    lk = _engine.rust().resolve_look(json.dumps(o))
    g = json.loads(_engine.rust().given_of(lk, json.dumps(o)))
    assert {k: g.get(k) for k in ("sidebar", "popup_mode", "find_control", "name", "road_popup")} == {k: ARGS[k] for k in (
        "sidebar", "popup_mode", "find_control", "name", "road_popup")}
    assert "state" not in g, "a map option is the look's"


# CI (ROADSTYLE_REQUIRE_WASM=1) builds the wasm package: there a missing package or node is a failure, not a skip
@pytest.mark.skipif(not (_engine.available() and PKG.exists() and shutil.which("node")) and os.environ.get("ROADSTYLE_REQUIRE_WASM") != "1",
                    reason="no roadstyle._rust, node or wasm package")
def test_a_python_page_and_a_wasm_page_of_the_same_keywords_have_the_same_page_keys(tmp_path):
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    import roadstyle as rs
    script = f"""
import {{initSync, resolveLook, makePage}} from {json.dumps(PKG.as_uri())};
import {{readFileSync, writeFileSync}} from "node:fs";
initSync({{module: readFileSync({json.dumps(str(PKG.with_name("roadstyle_wasm_bg.wasm")))})}});
const options = JSON.stringify({{args: {json.dumps(ARGS)}}});
writeFileSync({json.dumps(str(tmp_path / "wasm.html"))}, makePage(readFileSync({json.dumps(str(DATA))}), resolveLook(options), options));
"""
    (tmp_path / "page.mjs").write_text(script)
    subprocess.run(["node", str(tmp_path / "page.mjs")], check=True, capture_output=True, text=True, timeout=120)
    wasm = (tmp_path / "wasm.html").read_text()
    df = pq.read_table(DATA).to_pandas(integer_object_nulls=True)
    g = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    py = rs.render_edges(g, engine="rust", **{k: v for k, v in ARGS.items() if k != "state"}).html
    assert 'id="sb"' in wasm and 'id="sb"' in py, "both pages have the dashboard's sidebar"
    a, b = _opts(wasm), _opts(py)
    missing = {"wasm page": [k for k in KEYS if k not in a], "Python page": [k for k in KEYS if k not in b]}
    assert not any(missing.values()), f"keys that a page does not have: {missing} (an extension or a wasm package of another commit?)"
    assert {k: a[k] for k in KEYS} == {k: b[k] for k in KEYS}
    assert a["popup_mode"] == "panel" and a["find_control"] is True

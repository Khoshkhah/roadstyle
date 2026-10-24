"""The two engines give the same output (docs/design/rust_library.md, phase P5): export_inline with engine="python" and with
engine="rust", for the cases of the Rust golden tests (rust/roadstyle-rs/tests/make_goldens.py): a part of Monaco, with the options of
data-driven colour and width. Skipped when the Rust extension is not built (python rust/roadstyle-py/build.py)."""
import json
import sys
from pathlib import Path

import pytest

import roadstyle as rs
from roadstyle import _engine

pytestmark = pytest.mark.skipif(not _engine.available(), reason="the Rust extension roadstyle._rust is not built")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rust" / "roadstyle-rs" / "tests" / "data"
sys.path.insert(0, str(ROOT / "rust" / "roadstyle-py"))

CASES = {
    "plain": {},
    "numeric": {"color_by": "lanes", "cmap": "YlOrRd", "vmin": 1, "vmax": 4},
    "numeric_width": {"color_by": "lanes", "cmap": "viridis", "width_by": [1.0, 6.0]},
    "categorical": {"color_by": "access", "colors": {"private": "#d62728", "destination": "#ff7f0e", "no": "#7f7f7f"}},
    "color_options": {"color_options": {"class": {}, "lanes": {"color_by": "lanes", "cmap": "Blues", "vmin": 1, "vmax": 3},
                                        "access": {"color_by": "access", "colors": {"private": "#d62728"}, "missing": "self"}},
                      "color_active": "lanes"},
    "no_legend": {"color_by": "lanes", "cmap": "magma", "legend": False},
    "color_table": "every third road: one of three colours, by its edge_id",   # made from the roads (make_goldens.py: color_table)
    # the other keywords of the style and the page metadata
    "labels_off": {"labels": False},
    "arrows_off": {"arrows": False},
    "road_fill_off": {"road_fill": False},
    "road_popup": {"road_popup": ["name", "highway"]},
    "popup_off": {"road_popup": False},
    "popup_mode": {"popup_mode": "panel"},
    "road_tooltip": {"road_tooltip": ["name"]},
    "hover_delay": {"hover_delay_ms": 450},
    "data_maxzoom": {"data_maxzoom": 16},
    "data_tolerance": {"data_tolerance": 0.5},
    "camera": {"pitch": 30, "bearing": 20, "max_pitch": 70},
    "select_color": {"select_color": "#ff00ff"},
    "hover_color": {"hover_color": "#00ff00"},
    "view_3d_off": {"view_3d": False},
    "access_col": {"access_col": "access"},
    "head_m": {"head_m": 8.0},
    "offset_zoom": {"offset_zoom": 16},
    "minzoom": {"minzoom": True},
    "minzoom_table": {"minzoom": {"residential": 15, "footway": 17}},
}


def options(case, roads):
    """The keywords of a case; color_table is made from the roads, as in make_goldens.py."""
    if case == "color_table":
        cols = ["#e41a1c", "#377eb8", "#4daf4a"]
        return {"color_table": {str(e): cols[i % 3] for i, e in enumerate(roads["edge_id"]) if i % 3 == 0}}
    return CASES[case]


@pytest.fixture(scope="module")
def part():
    """The roads of make_goldens.py, read the same way (the integers stay integers)."""
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    df = pq.read_table(DATA / "monaco_part" / "roads.parquet").to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")


@pytest.fixture(scope="module")
def keywords():
    look = json.loads((DATA / "look.json").read_text())
    return {"palette": look["palette"], "settings": look["settings"], **look["args"], "arrows": True, "labels": True}


@pytest.mark.parametrize("case", sorted(CASES))
def test_export_inline_same_style(part, keywords, case):
    # the first differences only: pytest's own diff of two styles of several MB is too slow
    from compare_engines import diff

    py = rs.export_inline(part, engine="python", **{**keywords, **options(case, part)})
    ru = rs.export_inline(part, engine="rust", **{**keywords, **options(case, part)})
    assert [lyr["id"] for lyr in ru["layers"]] == [lyr["id"] for lyr in py["layers"]]
    assert diff(ru, py) == []


# render's level step: the keywords name no level columns, so both engines compute the positions (compute_levels, method="solve")
_LEVEL_COLS = ["casing_start", "casing_level", "casing_end", "fill_level", "head_start_m", "head_end_m", "cap_start", "cap_end"]
_LEVEL_ARGS = ["casing_start_col", "casing_level_col", "casing_end_col", "fill_level_col", "head_start_m_col", "head_end_m_col",
               "cap_start_col", "cap_end_col"]


def test_export_inline_levels_computed(part, keywords):
    from compare_engines import diff

    roads = part.drop(columns=[c for c in _LEVEL_COLS if c in part.columns])
    kw = {k: v for k, v in keywords.items() if k not in _LEVEL_ARGS}
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


@pytest.mark.parametrize("drop", [["directed_col"], ["driving_col"], ["directed_col", "driving_col"]])
def test_export_inline_direction_columns_not_named(part, keywords, drop):
    # render reads directed_col and driving_col only when they are named (None by default): the roads have the columns is_directed and
    # has_arrows, and without the keywords neither engine reads them (0.25.0: the Rust engine read them by these names)
    from compare_engines import diff

    kw = {k: v for k, v in keywords.items() if k not in drop}
    assert {"is_directed", "has_arrows"} <= set(part.columns)
    py = rs.export_inline(part, engine="python", **kw)
    ru = rs.export_inline(part, engine="rust", **kw)
    assert diff(ru, py) == []


# the column keywords: the same roads with other column names give the same style, with those names
_RENAME = {"highway": "fclass", "tunnel": "tun", "bridge": "brg", "layer": "lyr", "edge_id": "eid"}


@pytest.mark.parametrize("levels", ["given", "computed"])
def test_export_inline_column_names(part, keywords, levels):
    from compare_engines import diff

    roads, kw = part, dict(keywords)
    if levels == "computed":
        roads = part.drop(columns=[c for c in _LEVEL_COLS if c in part.columns])
        kw = {k: v for k, v in kw.items() if k not in _LEVEL_ARGS}
    roads = roads.rename(columns=_RENAME)
    kw.update(highway_col="fclass", tunnel_col="tun", bridge_col="brg", layer_col="lyr", edge_id_col="eid")
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


def test_export_inline_other_highway_column(part, keywords):
    """A column named highway that is not the class column (highway_col names another one) stays data, as in Python."""
    from compare_engines import diff

    roads = part.rename(columns={"highway": "fclass"})
    roads["highway"] = "other"
    kw = {**keywords, "highway_col": "fclass"}
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


@pytest.mark.parametrize("ends", ["cap_col only", "cap_col and the end columns"])
def test_export_inline_cap_col(part, keywords, ends):
    """cap_col: a cap for both ends ("square", another true value, "round"); with the end columns too, an end's own cap wins."""
    from compare_engines import diff

    roads = part.copy()
    roads["cap"] = [("square", "flat", "round", None)[i % 4] for i in range(len(roads))]
    kw = {**keywords, "cap_col": "cap"}
    if ends == "cap_col only":
        kw = {k: v for k, v in kw.items() if k not in ("cap_start_col", "cap_end_col")}
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


@pytest.mark.parametrize("kind", ["shapely", "GeoDataFrame"])
def test_export_inline_boundary(part, keywords, kind):
    """boundary: the dashed outline of an area over the roads."""
    import geopandas as gpd
    from compare_engines import diff

    shape = part.union_all().convex_hull.buffer(0.0005)
    boundary = shape if kind == "shapely" else gpd.GeoDataFrame(geometry=[shape], crs="EPSG:4326")
    py = rs.export_inline(part, engine="python", **{**keywords, "boundary": boundary})
    ru = rs.export_inline(part, engine="rust", **{**keywords, "boundary": boundary})
    assert diff(ru, py) == []


@pytest.mark.parametrize("opts", [{}, {"casing_m": 0.3, "casing_min_px": 0.5, "width_m_zoom": 15}, {"cap_col": "cap"}],
                         ids=["defaults", "options", "flat ends (the mitre ends)"])
def test_export_inline_metre_widths(part, keywords, opts):
    """width_m_col: a road with a width in metres is drawn at that width from width_m_zoom on (3.5 m for each lane where lanes is given)."""
    from compare_engines import diff

    roads = part.copy()
    roads["width_m"] = [3.5 * n if isinstance(n, int) and n > 0 else None for n in roads["lanes"]]
    roads["cap"] = "flat"
    kw = {**keywords, "width_m_col": "width_m", **opts}
    if "cap_col" in opts:      # every end flat: the flat ends where another metre road goes on are mitred (_mitre_ends)
        kw = {k: v for k, v in kw.items() if k not in ("cap_start_col", "cap_end_col")}
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


def _overlays(part, case):
    """The keywords of an overlay case: the caller's overlays of each kind, on edges, and render's items= (two lanes per road)."""
    import geopandas as gpd

    h = part[part.geometry.length > 0.0003].head(40)
    lanes = [{"edge_id": e, "width_m": 3.0, "offset_m": side * 1.5, "color": "#cc3333" if side < 0 else "#3333cc", "order": int(side > 0),
              "dash": "2,2" if side > 0 and i % 3 == 0 else None, "pick": side > 0 and i % 5 == 0, "minzoom": 17 if side > 0 and i % 7 == 0 else None,
              "geometry": g} for i, (e, g) in enumerate(zip(h["edge_id"], h.geometry, strict=True)) for side in (-1, 1)]
    zones = rs.Overlay(h.assign(geometry=h.geometry.buffer(0.0002)), label="zones", placement="under", popup=["name"])
    pois = rs.Overlay(h.assign(geometry=h.geometry.centroid), label="pois", color="#f00", tooltip=["name"])
    lines = rs.Overlay(h[["name", "geometry"]], kind="line", dash=[2, 2], min_zoom=14, popup=[])
    text = rs.Overlay(h[["name", "geometry"]], kind="text", text_col="name", text_halo="#fff")
    per_feature = rs.Overlay(h.assign(c="#123456")[["c", "geometry"]], color_col="c", width_m=3.0)
    on_edge = rs.Overlay(h[["edge_id", "geometry"]], label="on edge", edge_col="edge_id", color="#0a0")
    in_metres = rs.Overlay(h[["edge_id", "geometry"]].assign(w=2.5), edge_col="edge_id", width_m_col="w", color="#0a0", label="lanes")
    return {"kinds": {"overlays": [zones, pois, lines]}, "text": {"overlays": [text]}, "colour column": {"overlays": [per_feature]},
            "on edges": {"overlays": [on_edge]}, "items": {"items": gpd.GeoDataFrame(lanes, crs="EPSG:4326")},
            "items and metre overlay": {"overlays": [in_metres], "items": gpd.GeoDataFrame(lanes, crs="EPSG:4326")}}[case]


@pytest.mark.parametrize("case", ["kinds", "text", "colour column", "on edges", "items", "items and metre overlay"])
def test_export_inline_overlays(part, keywords, case):
    """overlays= (the caller's rs.Overlay layers) and items= (the road's line items in the one road layer, with their mitre ends)."""
    from compare_engines import diff

    py = rs.export_inline(part, engine="python", **{**keywords, **_overlays(part, case)})
    ru = rs.export_inline(part, engine="rust", **{**keywords, **_overlays(part, case)})
    assert diff(ru, py) == []


@pytest.mark.parametrize("rename", [False, True], ids=["names", "other column names"])
def test_export_inline_decks(part, keywords, rename):
    """view_3d: the 3D bridge decks. The properties are the same, the polygons have the same shape: Python makes them with GEOS, the
    engine with its own mitre offsets, so a vertex can differ by the rounding (1e-6 deg, about 0.1 m)."""
    import shapely
    from compare_engines import diff
    from shapely.geometry import shape

    roads, kw = part, {**keywords, "view_3d": True}
    if rename:
        roads = part.rename(columns=_RENAME)
        kw.update(highway_col="fclass", tunnel_col="tun", bridge_col="brg", layer_col="lyr", edge_id_col="eid")
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    fp, fr = (s["sources"]["decks"]["data"]["features"] for s in (py, ru))
    assert len(fr) == len(fp) > 0
    for a, b in zip(fr, fp, strict=True):
        assert diff(a["properties"], b["properties"]) == []
        assert shapely.hausdorff_distance(shape(a["geometry"]), shape(b["geometry"])) < 2e-6
    for s in (py, ru):
        s["sources"]["decks"]["data"]["features"] = []
    assert diff(ru, py) == []


@pytest.mark.parametrize("fmt", ["xyz", "pmtiles"])
@pytest.mark.parametrize("case", ["plain", "numeric", "categorical", "road_popup", "view_3d", "kinds", "items and metre overlay", "other column names"])
def test_export_style(part, keywords, case, fmt, tmp_path):
    """export_style: the same style.json and the same files; each tile has the same features when decoded (compare_engines.tile_diff:
    the numbers by value, the 3D decks by shape)."""
    from compare_engines import diff, tile_diff

    kw = {k: v for k, v in keywords.items() if k not in ("basemap", "basemaps")}     # export_style: the base map comes from the app
    if case == "other column names":
        part = part.rename(columns=_RENAME)
        kw.update(highway_col="fclass", tunnel_col="tun", bridge_col="brg", layer_col="lyr", edge_id_col="eid")
    else:
        kw.update(CASES[case] if case in CASES else {"view_3d": True} if case == "view_3d" else _overlays(part, case))
    py, ru = tmp_path / "python", tmp_path / "rust"
    rs.export_style(part, py, base_url="http://x", engine="python", format=fmt, **kw)
    rs.export_style(part, ru, base_url="http://x", engine="rust", format=fmt, **kw)
    assert diff(json.loads((ru / "style.json").read_text()), json.loads((py / "style.json").read_text())) == []
    files = sorted(p.relative_to(py) for p in py.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(ru) for p in ru.rglob("*") if p.is_file())
    for f in files:
        a, b = (py / f).read_bytes(), (ru / f).read_bytes()
        if f.suffix == ".pbf" and a != b:
            assert tile_diff(b, a) == [], f
        elif f.suffix == ".pmtiles":
            ta, tb = _archive(a), _archive(b)
            for k in sorted(set(ta) | set(tb)):
                assert tile_diff(tb.get(k, b""), ta.get(k, b"")) == [], k
        else:
            assert a == b, f


def _archive(data):
    """The tiles of a PMTiles archive, gunzipped, by (z, x, y)."""
    import gzip

    from pmtiles.reader import MemorySource, all_tiles
    return {k: gzip.decompress(v) for k, v in all_tiles(MemorySource(data))}


_LIVE = {"plain": {}, "controls": {"tunnel_control": True, "filter_control": True, "access_col": "access"},
         "colors": {"color_options": {"class": {}, "lanes": {"color_by": "lanes", "cmap": "Blues", "vmin": 1, "vmax": 3}}, "color_active": "lanes"},
         "decks": {"view_3d": True}}


@pytest.mark.parametrize("case", [*_LIVE, "kinds", "text", "on edges", "items and metre overlay"])
def test_live_style_and_contract(part, keywords, case):
    """state="live" (a page with the dashboard): the style of render's page (the state in the expressions, the page's arrows), and the
    interaction contract in its metadata: roadstyle:state is the page's state, roadstyle:controls the options of rsDashboard that the page
    gets from the style (render_web.render's `page`). The base map, the page's own options and the decks' vertices are left out."""
    from compare_engines import diff

    opts = _LIVE[case] if case in _LIVE else _overlays(part, case)
    parts = rs.render_edges(part, backend="web", _parts=True, **{**keywords, **opts})
    py, page = parts["style"], parts["options"]
    lk = _engine._look_of({**keywords, "view_3d": False, **opts, "state": "live"})
    src = _engine.rust().make_sources(_engine._arrow(part), lk, None, None, None)
    src.page_arrows()           # stage 3 of the inline page (audit N2): the arrows as points
    ru = json.loads(src.style())
    meta = ru.pop("metadata")
    assert meta["roadstyle:contract"] == 1
    assert diff(meta["roadstyle:state"], {k: v["default"] for k, v in py["state"].items()}) == []
    controls = dict(meta["roadstyle:controls"])
    assert controls.pop("dashes") == (parts["simple_js"] or {}).get("dashes", [])     # the page script's dash patterns, not an option
    want = {k: page[k] for k in controls}
    want["tunnel"] = {**want["tunnel"], "bg": controls["tunnel"]["bg"]}      # the base map's canvas colour: the page's own
    assert diff(controls, want) == []
    py["sources"].pop("bm", None)
    py["layers"] = [lyr for lyr in py["layers"] if lyr["id"] not in ("bg", "basemap")]
    for st in (ru, py):
        for lyr in st["layers"]:
            lyr.pop("metadata", None)
        for k in ("name", "center", "zoom", "glyphs"):
            st.pop(k, None)
        if "decks" in st["sources"]:       # by shape: test_export_inline_decks
            st["sources"]["decks"]["data"]["features"] = []
    assert diff(ru, py) == []


_PAGES = {"plain": {}, "controls": {"tunnel_control": True, "filter_control": True, "access_col": "access"},
          "numeric": {"color_by": "lanes", "cmap": "YlOrRd", "vmin": 1, "vmax": 4}, "colors": _LIVE["colors"], "compressed": {"compress": True},
          "panel": {"road_popup": "panel"}, "base map": {"basemap": "osm", "basemaps": ["osm", "blank"]}, "classes": {"exclude": ["footway", "steps"]}}


@pytest.mark.parametrize("case", [*_PAGES, "kinds", "items and metre overlay", "decks"])
def test_render_edges_page(part, keywords, case, monkeypatch):
    """render_edges(engine="rust"): the page of the Rust engine's live style, written by Python's page writer, is the page of the Python
    engine byte for byte (with the decks: the same page but the decks' vertices, see test_export_inline_decks)."""
    monkeypatch.delenv("GOOGLE_MAPS_KEY", raising=False)
    opts = {"compress": False, **(_PAGES[case] if case in _PAGES else {"view_3d": True} if case == "decks" else _overlays(part, case))}
    py = rs.render_edges(part, backend="web", engine="python", **{**keywords, **opts}).html
    ru = rs.render_edges(part, backend="web", engine="rust", **{**keywords, **opts}).html
    if case != "decks":
        assert ru == py
        return
    from compare_engines import diff

    def cut(html):
        at = html.index("const style = ") + len("const style = ")
        st, end = json.JSONDecoder().raw_decode(html[at:])
        st["sources"]["decks"]["data"]["features"] = len(st["sources"]["decks"]["data"]["features"])
        return st, html[:at] + html[at + end:]
    (sr, hr), (sp, hp) = cut(ru), cut(py)
    assert diff(sr, sp) == [] and hr == hp


@pytest.mark.parametrize("case", ["plain", "controls", "items and metre overlay"])
def test_render_edges_tiled_page(part, keywords, case, monkeypatch):
    """render_edges(tiles=True, engine="rust"): the same page as the Python engine's, but the embedded PMTiles archive, whose tiles are the
    same when decoded (compare_engines.tile_diff); the style, the sidecar table and the rest of the page are the same byte for byte."""
    import base64
    import gzip
    import re

    from compare_engines import tile_diff
    monkeypatch.delenv("GOOGLE_MAPS_KEY", raising=False)
    opts = {"compress": False, "tiles": True, **(_PAGES[case] if case in _PAGES else _overlays(part, case))}

    def parts(html):
        pm = re.search(r'atob\("([A-Za-z0-9+/=]+)"\)', html).group(1)
        side = re.search(r'id="rs-side" type="application/json">([A-Za-z0-9+/=]+)<', html).group(1)
        return _archive(base64.b64decode(pm)), gzip.decompress(base64.b64decode(side)), html.replace(pm, "PM").replace(side, "SIDE")
    (tp, sp, hp), (tr, sr, hr) = (parts(rs.render_edges(part, backend="web", engine=e, **{**keywords, **opts}).html) for e in ("python", "rust"))
    assert hr == hp and sr == sp
    for k in sorted(set(tp) | set(tr)):
        assert tile_diff(tr.get(k, b""), tp.get(k, b"")) == [], k


@pytest.mark.parametrize("views", [{"plain": {"road_fill": False}, "bridges": {"bridges": True, "classes": ["primary"]}},
                                   {"carto": {"palette": "carto"}, "mono": {"palette": "mono", "road_fill": False}}],
                         ids=["settings", "palettes"])
def test_render_edges_views(part, keywords, views, monkeypatch):
    """render_edges(views=..., engine="rust"): the View menu, and a view's palette in the page (the colours of each palette, the state
    rs_palette): the Python engine's page byte for byte. The bundled palettes, as the fixture's own palette makes other features than they."""
    monkeypatch.delenv("GOOGLE_MAPS_KEY", raising=False)
    kw = {**{k: v for k, v in keywords.items() if k not in ("palette", "settings", "basemap", "basemaps")}, "palette": "amber", "compress": False,
          "views": views}
    assert rs.render_edges(part, engine="rust", **kw).html == rs.render_edges(part, engine="python", **kw).html


def test_the_full_look_is_the_python_engines(part, keywords, monkeypatch):
    """simple=False (the full look) is the Python engine's only (plan decision 2, 2026-10-23): with engine="rust" an error that names the
    Python engine; with ROADSTYLE_ENGINE=rust the Python engine makes it, with a warning; Python's own gives a deprecation warning."""
    kw = {**keywords, "simple": False}
    with pytest.raises(ValueError, match="use engine='python'"):
        rs.export_inline(part, engine="rust", **kw)
    with pytest.raises(ValueError, match="use engine='python'"):
        rs.render_edges(part, backend="web", engine="rust", **kw)
    monkeypatch.setenv("ROADSTYLE_ENGINE", "rust")
    with pytest.warns(UserWarning, match="the Python engine makes this one"):
        st = rs.export_inline(part, **kw)
    assert not any(lyr["id"] == "roads-simple" for lyr in st["layers"])        # the full look: a layer for each position
    with pytest.warns(DeprecationWarning, match="goes away in roadstyle 0.27.0"):
        rs.export_inline(part, engine="python", **kw)


def test_the_page_writer_gzips_by_itself(part, keywords):
    """roadstyle::page without the blobs of Python's zlib (the browser): the same page, its big sources gzipped by the crate; the same
    sources when they are read back."""
    import base64
    import gzip
    import re

    parts = rs.render_edges(part, backend="web", _parts=True, **keywords)
    py = rs.render_edges(part, backend="web", engine="python", **keywords).html
    cam = {k: parts["camera"][k] for k in ("pitch", "bearing", "max_pitch")}
    side = parts["side"]          # the road table: the crate gzips it too
    ru = _engine.rust().make_page(json.dumps(parts["style"]), json.dumps(parts["options"]), json.dumps(
        {"name": keywords.get("name") or "roadstyle", "cam": cam, "bounds": list(parts["bounds"]), "side_panel_html": None, "host_panel_width": 320,
         "compress": True, "simple_js": parts["simple_js"], "side": side}), None)
    from roadstyle.render_web import WebMap
    ru = WebMap(ru).html                  # the page's MapLibre, as the Python page has it
    blob = lambda html: {k: json.loads(gzip.decompress(base64.b64decode(v))) for k, v in json.loads(       # noqa: E731
        re.search(r'id="rs-gz" type="application/json">(.*?)</script>', html, re.S).group(1)).items()}
    assert blob(ru) == blob(py)
    table = lambda html: json.loads(gzip.decompress(base64.b64decode(re.search(r'id="rs-side" type="application/json">(.*?)</script>', html,   # noqa: E731
                                                                                re.S).group(1))))
    assert table(ru) == table(py) == side
    cut = lambda html: re.sub(r'(id="rs-(gz|side)" type="application/json">).*?(</script>)', r"\1\3", html, flags=re.S)       # noqa: E731
    assert cut(ru) == cut(py)


def test_the_pmtiles_writer_is_the_pmtiles_packages(part, keywords):
    """roadstyle_tiles::pmtiles: the archive of the Tiler's tiles has the header, the entries and the tiles that the pmtiles package's
    Writer gives for the same tiles (the gzip streams differ: its carry the time, and the two gzip libraries compress in other ways)."""
    import gzip
    import io

    from pmtiles.reader import MemorySource, Reader, all_tiles
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer

    from roadstyle.tiles import _merc, _tile_range
    lk = _engine._look_of({**keywords, "tiles": True})
    t = _engine.rust().Tiler(_engine._arrow(part), lk, None, None, "", [])
    b = [float(v) for v in part.total_bounds]
    ru = t.archive(b, ["roads", "simple", "slots"])
    buf = io.BytesIO()
    w = Writer(buf)
    (mx0, my0), (mx1, my1) = _merc(*b[:2]), _merc(*b[2:])
    for z in range(6, 16):
        x0, x1, y0, y1 = _tile_range((mx0, my0, mx1, my1), z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if d := t.tile(z, x, y):
                    w.write_tile(zxy_to_tileid(z, x, y), gzip.compress(d, 6, mtime=0))
    e7 = [int(v * 1e7) for v in b]
    w.finalize({"tile_type": TileType.MVT, "tile_compression": Compression.GZIP, "min_lon_e7": e7[0], "min_lat_e7": e7[1], "max_lon_e7": e7[2],
                "max_lat_e7": e7[3], "center_zoom": 10, "center_lon_e7": (e7[0] + e7[2]) // 2, "center_lat_e7": (e7[1] + e7[3]) // 2},
               {"vector_layers": [{"id": n, "fields": {}} for n in ("roads", "simple", "slots")]})
    py = buf.getvalue()
    head = lambda a: {k: v for k, v in Reader(MemorySource(a)).header().items() if "offset" not in k and "length" not in k}    # noqa: E731
    assert head(ru) == head(py)
    assert Reader(MemorySource(ru)).metadata() == Reader(MemorySource(py)).metadata()
    tiles = lambda a: {k: gzip.decompress(v) for k, v in all_tiles(MemorySource(a))}        # noqa: E731  (two gzip libraries: other streams)
    assert tiles(ru) == tiles(py)


@pytest.mark.parametrize("kw", [{}, {"palette": "carto"}, {"profile": "highsat", "palette": "mono"}, {"positions": [0, 1, 2], "highway_col": "fclass"}],
                         ids=["default", "carto", "highsat mono", "positions and a column"])
def test_export_look(kw):
    """export_look (the simple look for another app's data layer, the GeoLibre plugin's): the same look from both engines."""
    from compare_engines import diff
    assert diff(rs.export_look(engine="rust", **kw), rs.export_look(engine="python", **kw)) == []


LEVEL_CASES = {"solve": {}, "class": {"order": "class"}, "no_order": {"order": None}, "order_col": {"order": "rank_col"},
               "band_col": {"band_col": "layer"}, "band_dist": {"band_dist": 20.0}, "head_m": {"head_m": 10.0}, "max_level": {"max_level": 2},
               "no_min_positions": {"min_positions": False}, "near_rules": {"near_rules": True}, "margin": {"margin": 2.0}}
LEVEL_COLS = ["casing_start", "casing_level", "casing_end", "fill_level"]


def test_compute_levels_tags(part):
    """The tags rule (no optimization): the same four columns from both engines."""
    roads = part.drop(columns=[c for c in _LEVEL_COLS if c in part.columns])
    py, ru = (rs.compute_levels(roads, method="tags", engine=e) for e in ("python", "rust"))
    assert py[LEVEL_COLS].astype(int).values.tolist() == ru[LEVEL_COLS].astype(int).values.tolist()
    assert ru.attrs["levels_params"] == py.attrs["levels_params"]


@pytest.mark.parametrize("case", sorted(LEVEL_CASES))
def test_compute_levels_solve(part, case):
    """The solve with each keyword: a feasible answer (the Rust solver checks its hard rules; here no casing is over its fill). The
    two solvers can take different answers that are equally good, so the rows are not compared."""
    roads = part.drop(columns=[c for c in _LEVEL_COLS if c in part.columns])
    roads["rank_col"] = [float(i % 5) for i in range(len(roads))]
    ru = rs.compute_levels(roads, engine="rust", **LEVEL_CASES[case])
    v = ru[LEVEL_COLS].astype(int).values
    assert (v[:, :3] <= v[:, 3:]).all()


def test_compute_levels_rust_errors(part):
    with pytest.raises(ValueError, match="use method='solve'"):
        rs.compute_levels(part, method="tags", engine="rust", band_col="layer")
    with pytest.raises(ValueError, match="greater than 0"):
        rs.compute_levels(part, engine="rust", margin=0)


def test_engine_names(monkeypatch):
    monkeypatch.delenv("ROADSTYLE_ENGINE", raising=False)
    assert _engine.engine(None) == "python"
    monkeypatch.setenv("ROADSTYLE_ENGINE", "rust")
    assert _engine.engine(None) == "rust"
    with pytest.raises(ValueError, match="use one of"):
        _engine.engine("go")



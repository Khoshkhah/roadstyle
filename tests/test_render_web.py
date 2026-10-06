"""Web (MapLibre) backend: client-side recolouring via color_options + the recolour hooks."""
import json
import math
import re
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from roadstyle import Overlay, compute_levels, render_edges


def _edges():
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "primary", "residential"],
         "name": ["E18", "Main St", "Back Ln"],
         "aadt": [25000, 8000, 1500],
         "speed_kph": [70, 50, 30]},
        geometry=[LineString([(17.9, 59.37), (17.91, 59.38)]),
                  LineString([(17.91, 59.38), (17.92, 59.38)]),
                  LineString([(17.92, 59.38), (17.92, 59.39)])],
        crs=4326)


def _style(html):
    """Pull the inlined MapLibre style JSON back out of the page."""
    m = re.search(r"const style = (\{.*?\}), BASEMAPS", html, re.S)
    return json.loads(m.group(1))


def test_web_color_options_bake_variants_and_wire_recolour():
    wm = render_edges(_edges(), backend="web", palette="mono", color_options={
        "Class": {},
        "AADT": {"color_by": "aadt", "cmap": "viridis"},
        "Speed": {"color_by": "speed_kph", "cmap": "magma"},
    })
    style = _style(wm.html)
    p = style["sources"]["roads"]["data"]["features"][0]["properties"]
    # option 0 owns __rs_fill; the rest bake a distinct fill prop per edge
    assert "__rs_fill" in p and "__rs_fill__1" in p and "__rs_fill__2" in p
    # the recolour hooks + the Colour-by control are present
    for needle in ("rsSetColorField", "RS_COLOR_OPTIONS", "setPaintProperty", "co-ctrl"):
        assert needle in wm.html
    assert '"AADT"' in wm.html and '"prop": "__rs_fill__1"' in wm.html


def test_web_color_option_missing_self_keeps_nan_color():
    g = _edges()
    g.loc[2, "aadt"] = None                       # a NaN in the numeric option's column
    base = {"Class": {}, "AADT": {"color_by": "aadt", "cmap": "viridis"}}
    inherit = _style(render_edges(g, backend="web", palette="mono", color_options=base).html)
    p_i = inherit["sources"]["roads"]["data"]["features"][2]["properties"]
    assert p_i["__rs_fill__1"] == p_i["__rs_fill"]      # default: NaN inherits the base fill
    base["AADT"]["missing"] = "self"
    own = _style(render_edges(g, backend="web", palette="mono", color_options=base).html)
    p_s = own["sources"]["roads"]["data"]["features"][2]["properties"]
    assert p_s["__rs_fill__1"] == "#cccccc"             # "self": NaN keeps the styler's nan_color


def test_web_no_color_options_is_unchanged():
    wm = render_edges(_edges(), backend="web")
    style = _style(wm.html)
    p = style["sources"]["roads"]["data"]["features"][0]["properties"]
    assert "__rs_fill__1" not in p            # no variants baked
    assert "const COLOR_OPTIONS = [];" in wm.html   # picker JS present but inert (empty)


def _copts(html):
    return re.search(r"const COLOR_OPTIONS = (.+?);", html).group(1)


def test_web_color_by_bakes_its_legend():
    # the plain color_by/cmap path renders the styler's legend on the web backend (no dropdown —
    # one legend-only entry). legend=True is the default, matching folium.
    on = _copts(render_edges(_edges(), backend="web", color_by="aadt", cmap="viridis").html)
    assert '"legend"' in on and '"kind": "continuous"' in on   # continuous ramp legend baked
    # legend=False opts out
    off = _copts(render_edges(_edges(), backend="web", color_by="aadt", cmap="viridis",
                              legend=False).html)
    assert off == "[]"


def test_web_annotation_slots_alternate_names_and_arrows():
    """The annotation plan: each road chain is sliced into equal per-band slots; names take even
    slots, oneway arrows odd ones (alternating, never stacked); unnamed roads leave their name
    slots empty. One label + one arrow layer per zoom band."""
    wm = render_edges(_edges(), backend="web", arrows=True, labels=True)
    style = _style(wm.html)
    ids = [layer["id"] for layer in style["layers"]]
    assert "roads-labels" in ids and "roads-arrows" in ids
    slots = style["sources"]["slots"]["data"]["features"]
    assert slots and all({"slot", "name", "highway", "oneway"} <= set(f["properties"])
                         for f in slots)
    lab = next(l for l in style["layers"] if l["id"] == "roads-labels")
    arr = next(l for l in style["layers"] if l["id"] == "roads-arrows")
    assert json.dumps(["==", ["%", ["get", "slot"], 2], 0]) in json.dumps(lab["filter"])     # names: even slots
    # arrows: one per one-way road in the window (docs/design/one_arrow_per_road.md): points the page puts in the "arrows" source,
    # rotated along the road; every slot piece names its chain
    assert json.dumps(["==", ["get", "oneway"], 1]) in json.dumps(arr["filter"])
    assert arr["source"] == "arrows" and arr["layout"]["symbol-placement"] == "point" and arr["layout"]["icon-rotate"] == ["get", "b"]
    assert style["sources"]["arrows"]["data"]["features"] == [] and all("chain" in f["properties"] for f in style["sources"]["slots"]["data"]["features"])
    # one arrow layer per grade tier, each right beside its road tier — a bridge must cover
    # the arrows of the road it crosses, not have them float above everything
    assert ids.index("roads-arrows") == ids.index("roads-fill-sq") + 1
    assert ids.index("roads-arrows-lv1") == ids.index("roads-fill-lv1-sq") + 1     # one arrow layer per position
    assert json.dumps(["to-boolean", ["get", "name"]]) in json.dumps(lab["filter"])          # unnamed -> slot stays empty
    assert lab["layout"]["symbol-placement"] == "line-center"
    # Kaveh's standing default: label text matches the oneway-arrow grey, and NO halo
    assert lab["paint"]["text-color"] == "#5b5b5b"
    assert "text-halo-color" not in lab["paint"] and "text-halo-width" not in lab["paint"]


def _zone():
    from shapely.geometry import box
    return gpd.GeoDataFrame({"taz_id": ["Z0"], "weight": [0.5]},
                            geometry=[box(17.9, 59.37, 17.93, 59.39)], crs=4326)


def _pois():
    from shapely.geometry import Point
    return gpd.GeoDataFrame({"name": ["A", "B"], "type": ["shop", "park"]},
                            geometry=[Point(17.91, 59.38), Point(17.92, 59.385)], crs=4326)


def test_web_overlays_place_under_and_over_roads():
    from roadstyle import Overlay
    wm = render_edges(_edges(), backend="web", overlays=[
        Overlay(_zone(), placement="under", label="Zones", popup=["taz_id", "weight"]),
        Overlay(_pois(), placement="over", label="POIs", popup=["name", "type"]),
    ])
    style = _style(wm.html)
    ids = [layer["id"] for layer in style["layers"]]
    assert ids.index("ov0-fill") < ids.index("roads-fill")     # zones under the roads
    assert ids.index("ov1-circle") > ids.index("roads-fill")   # POIs on top
    assert "ov0" in style["sources"] and "ov1" in style["sources"]
    # popup fields + toggle wiring present; overlay props preserved for the popup
    assert "handleOverlayClick" in wm.html and "ov-ctrl" in wm.html
    # placement is baked into the JS meta: click precedence follows the visual stacking
    meta = json.loads(wm.html.split("const OVERLAYS = ")[1].split(";\n")[0])
    assert [m["under"] for m in meta] == [True, False]
    z = style["sources"]["ov0"]["data"]["features"][0]["properties"]
    assert z["taz_id"] == "Z0" and z["weight"] == 0.5


def test_web_overlay_kind_autodetected():
    from roadstyle import Overlay
    wm = render_edges(_edges(), backend="web", overlays=[Overlay(_pois())])  # points -> circle
    ids = [layer["id"] for layer in _style(wm.html)["layers"]]
    assert "ov0-circle" in ids


def test_web_no_overlays_is_inert():
    wm = render_edges(_edges(), backend="web")
    assert "const OVERLAYS = [];" in wm.html


# --- compress: gzip the source data, inflate in the browser -------------------------------------

def _many_edges(n=4000):
    """Enough features that the road source clears the compression threshold."""
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"highway": ["residential"] * n, "name": [f"Street {i}" for i in range(n)],
         "some_long_property_name": ["a value that repeats"] * n},
        geometry=[LineString([(i * 1e-3, 0), (i * 1e-3, 1e-3)]) for i in range(n)], crs=4326)


def _style_of(html):
    """The style object the page was built with — parsed from `const style = {...}`."""
    import json as _json
    i = html.index("const style = ") + len("const style = ")
    return _json.JSONDecoder().raw_decode(html, i)[0]


def test_compress_on_by_default_and_off_leaves_data_inline():
    from roadstyle.render_web import render
    assert "rs-gz" in render(_many_edges()).html            # default: gzipped blobs
    html = render(_many_edges(), compress=False).html       # opt-out: plain inline JSON
    assert "rs-gz" not in html
    assert _style_of(html)["sources"]["roads"]["data"]["features"]


def test_compress_empties_the_source_and_emits_a_blob():
    import base64
    import gzip
    import json as _json

    from roadstyle.render_web import render

    g = _many_edges()
    html = render(g, compress=True).html
    assert _style_of(html)["sources"]["roads"]["data"] == {"type": "FeatureCollection", "features": []}
    blobs = _json.loads(html.split('id="rs-gz" type="application/json">')[1].split("</script>")[0])
    assert "roads" in blobs                             # slots may compress too; boundary-
    assert set(blobs) <= {"roads", "slots", "casings"}             # sized sources stay inline
    fc = _json.loads(gzip.decompress(base64.b64decode(blobs["roads"])))
    assert len(fc["features"]) == len(g)                # lossless


def test_compress_is_smaller_and_otherwise_identical():
    """The page must differ ONLY in where the data lives — same layers, filters, popup wiring."""
    from roadstyle.render_web import render

    g = _many_edges()
    plain, small = render(g, compress=False).html, render(g, compress=True).html
    assert len(small) < len(plain)
    a, b = _style_of(plain), _style_of(small)
    assert [l["id"] for l in a["layers"]] == [l["id"] for l in b["layers"]]
    for k in ("__FILTER__", "__COLOR_OPTIONS__"):       # placeholders are gone; compare the results
        assert k not in plain and k not in small
    # the filter panel's class list is baked from the features either way
    assert '"classes": ["residential"]' in plain.replace("'", '"')
    assert '"classes": ["residential"]' in small.replace("'", '"')


def test_a_small_source_is_left_inline():
    """A boundary polygon is a few hundred bytes — not worth a round trip."""
    from roadstyle.render_web import _compress_sources

    style = {"sources": {"roads": {"type": "geojson", "data": {"type": "FeatureCollection",
                                                               "features": [{"x": "y" * 500000}]}},
                         "boundary": {"type": "geojson", "data": {"type": "FeatureCollection",
                                                                  "features": [{"a": 1}]}},
                         "basemap": {"type": "raster", "tiles": ["http://x/{z}/{x}/{y}.png"]}}}
    blobs = _compress_sources(style)
    assert set(blobs) == {"roads"}
    assert style["sources"]["boundary"]["data"]["features"] == [{"a": 1}]
    assert style["sources"]["basemap"]["tiles"]                      # raster untouched


# --- minzoom: hide minor classes when zoomed out --------------------------------------------------

def _road_filters(html):
    return {l["id"]: l.get("filter") for l in _style_of(html)["layers"]
            if l["id"] in ("roads-fill", "roads-casing", "roads-low-fill", "roads-bridge-fill")}


def test_minzoom_off_by_default():
    """Existing maps must be byte-identical — `track` is a width channel for some callers, and
    hiding it by class would make their data disappear."""
    from roadstyle.render_web import render
    for f in _road_filters(render(_many_edges(20)).html).values():
        assert "zoom" not in json.dumps(f)


def test_minzoom_true_uses_the_config_table():
    from roadstyle.config import DEFAULT
    from roadstyle.render_web import render

    fs = _road_filters(render(_many_edges(20), minzoom=True).html)
    assert fs, "expected road layers"
    for f in fs.values():
        blob = json.dumps(f)
        assert '"zoom"' in blob
        assert f'"residential", {float(DEFAULT.minzoom["residential"])}' in blob


def test_minzoom_dict_overrides_only_what_it_names():
    from roadstyle.config import DEFAULT
    from roadstyle.render_web import render

    blob = json.dumps(_road_filters(render(_many_edges(20), minzoom={"residential": 9}).html))
    assert '"residential", 9.0' in blob
    assert f'"service", {float(DEFAULT.minzoom["service"])}' in blob   # untouched key survives


def test_unknown_class_is_always_drawn():
    """The table hides things early; it is never a whitelist. An unlisted class must default to 0."""
    from roadstyle.render_web import _minzoom_filter

    expr = _minzoom_filter("highway", {"service": 15})
    assert expr[0] == ">=" and expr[1] == ["zoom"]
    assert expr[2][-1] == 0.0                     # the `match` default




def test_draw_order_from_layer_look_from_bridge_column():
    """The OSM `layer` decides the draw order (a layer=2 road without a bridge tag is drawn above
    the ground roads), but only the bridge column earns the bridge look (deck styling, 3D
    extrusions); a negative layer alone is below ground, not a tunnel."""
    g = _edges().assign(bridge=[True, False, False], layer=[1, 2, -1])
    style = _style(render_edges(g, backend="web").html)
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert [p["lvl"] for p in ps] == [1, 2, -1]
    assert [p["__rs_bridge"] for p in ps] == [True, False, False]
    assert [p["__rs_tunnel"] for p in ps] == [False, False, False]


def test_web_round_caps_seal_edge_connections():
    """Consecutive edges are separate LineStrings; round caps are the only rendering primitive
    that seals the seam where they connect. Network continuity outranks end-cap shape."""
    style = _style(render_edges(_edges(), backend="web").html)
    lay = {l["id"]: l for l in style["layers"]}
    assert lay["roads-fill"]["layout"]["line-cap"] == "round"
    assert lay["roads-casing"]["layout"]["line-cap"] == "round"


def test_twoway_requires_a_reverse_twin_not_just_shared_endpoints():
    """Two same-direction edges between one node pair (a street split into parallel one-way
    carriageways, e.g. Brännkyrkagatan) must NOT read as a two-way pair — that suppressed their
    arrows. Only a genuine end->start twin fans into lanes."""
    a, b = (18.063, 59.3195), (18.065, 59.3198)
    g = gpd.GeoDataFrame({"highway": ["residential"] * 4},
                         geometry=[LineString([a, (18.064, 59.3199), b]),   # A->B, northern split
                                   LineString([a, (18.064, 59.3194), b]),   # A->B, southern split
                                   LineString([b, (18.066, 59.3202)]),      # B->C
                                   LineString([(18.066, 59.3202), b])],     # C->B (real twin)
                         crs=4326)
    style = _style(render_edges(g, backend="web").html)
    tw = [f["properties"]["__rs_twoway"] for f in style["sources"]["roads"]["data"]["features"]]
    assert tw == [False, False, True, True]


def test_web_labels_and_arrows_read_style_config(monkeypatch):
    """Label paint and arrow cosmetics come from StyleConfig (data/style.json "config" +
    roadstyle.json overrides), not hardcoded paint — a partial override dict keeps the rest."""
    import dataclasses

    import roadstyle.render_web as rw

    cfg = dataclasses.replace(rw.CONFIG,
                              labels={"color": "#ff0000", "halo_color": "#000000", "halo_width": 2},
                              arrows={"color": "#123456", "opacity": 0.5})
    monkeypatch.setattr(rw, "CONFIG", cfg)
    wm = render_edges(_edges(), backend="web", arrows=True, labels=True)
    style = _style(wm.html)
    paint = next(l for l in style["layers"] if l["id"] == "roads-labels")["paint"]
    # labels inherit the arrows' opacity (same rendered grey, not just same hex);
    # a labels.opacity settings key would override it
    assert paint == {"text-color": "#ff0000", "text-halo-color": "#000000",
                     "text-halo-width": 2, "text-opacity": 0.5}
    arrow = next(l for l in style["layers"] if l["id"] == "roads-arrows")
    assert arrow["minzoom"] == 15 and arrow["paint"]["icon-opacity"] == 0.5
    assert 'fill="#123456"' in wm.html               # the chevron SVG itself is retinted


def test_web_bridge_casing_is_config_colour():
    """Bridge decks keep a solid dark casing (config.bridge_casing_color, black by default) even
    though the regular road casing defaults to light grey."""
    style = _style(render_edges(_edges().assign(bridge=["yes", None, None]), backend="web").html)
    bc = next(l for l in style["layers"] if l["id"].endswith("-bridge"))
    assert bc["paint"]["line-color"] == "#000000"


def test_webmap_notebook_repr_is_slim_but_saved_file_is_offline():
    """The inline notebook preview swaps MapLibre for CDN tags (output-size limits in notebook
    frontends were silently blanking the map); .html / .save keep the vendored copy inlined."""
    wm = render_edges(_edges(), backend="web")
    r = wm._repr_html_()
    assert "cdn.jsdelivr.net/npm/maplibre-gl" in r
    assert len(r) < len(wm.html)                      # the 800 KB vendored blob stays out
    assert "__MAPLIBRE_JS__" not in wm.html and "cdn.jsdelivr" not in wm.html


def test_web_camera_pitch_and_bearing():
    """pitch=/bearing= set the starting camera (and survive the bounds fit); defaults come from
    the `camera` settings block (0/0)."""
    flat = render_edges(_edges(), backend="web").html
    assert "pitch:0, bearing:0," in flat
    tilted = render_edges(_edges(), backend="web", pitch=55, bearing=30).html
    assert "pitch:55, bearing:30," in tilted
    assert tilted.count("pitch:55") == 2          # map init AND the fitBounds camera


def test_web_view_3d_flag():
    """view_3d=True is a perspective camera (camera settings pitch_3d) — NO terrain data: no DEM
    source, no style.terrain, no hillshade layer. Off by default."""
    wm = render_edges(_edges(), backend="web", view_3d=True)
    style = _style(wm.html)
    assert "terrain" not in style and "dem" not in style["sources"]
    assert "hillshade" not in [l["id"] for l in style["layers"]]
    assert "pitch:55" in wm.html
    flat = render_edges(_edges(), backend="web").html
    assert "pitch:0" in flat


def test_web_camera_toggle_control():
    """Every map carries the 2D/3D toggle button; its target pitch comes from terrain settings."""
    html = render_edges(_edges(), backend="web").html
    assert "const PITCH3D = 55" in html and 'b.textContent = m.getPitch()<5 ? "3D" : "2D"' in html


def test_web_3d_bridge_decks():
    """view_3d renders bridges as extruded deck ribbons (polygons floating base_m above ground)
    from bridge_decks.flat_below up; below it the classic flat bridge lines draw (full stylized
    width — a fixed deck polygon reads too narrow / vanishes zoomed out)."""
    g = _edges().assign(bridge=["yes", None, None])
    td = _style(render_edges(g, backend="web", view_3d=True).html)
    ids = [l["id"] for l in td["layers"]]
    assert "roads-bridge-decks" in ids
    # LOD swap at flat_below: flat lines capped there, deck starts there; bridge highlight split
    deck3d = next(l for l in td["layers"] if l["id"] == "roads-bridge-decks")
    assert deck3d["minzoom"] == 16.0
    # the flat bridge line (its casing layer, and the bridge edges in the position layers) ends where the deck starts
    assert next(l for l in td["layers"] if l["id"].endswith("-bridge") and l["id"].startswith("roads-casing"))["maxzoom"] == 16.0
    assert json.dumps(["<", ["zoom"], 16.0]) in json.dumps(next(l for l in td["layers"] if l["id"] == "roads-fill")["filter"])
    assert "roads-highlight-bridge" in ids
    deck = next(l for l in td["layers"] if l["id"] == "roads-bridge-decks")
    assert deck["type"] == "fill-extrusion"
    assert deck["paint"]["fill-extrusion-base"] == ["get", "__rs_base"]
    assert td["sources"]["decks"].get("generateId") is True     # hover/select feature-state
    slices = td["sources"]["decks"]["data"]["features"]
    assert all(f["geometry"]["type"] == "Polygon" for f in slices)
    # popup parity: slices carry the full edge properties, not just fills
    assert "maxspeed_kmh" in slices[0]["properties"] or "aadt" in slices[0]["properties"]
    assert all("__rs_chain" in f["properties"] for f in slices)   # whole-bridge hover unit
    assert deck["paint"]["fill-extrusion-opacity"] == 0.7    # settings-driven transparency
    bases = [f["properties"]["__rs_base"] for f in slices]
    # the deck RAMPS: grounded at the ends (connects to the road), full height mid-span
    assert min(bases) < 1.0 and max(bases) == 5.0
    flat = _style(render_edges(g, backend="web").html)
    fids = [l["id"] for l in flat["layers"]]
    assert "roads-casing-lv1-bridge" in fids and "roads-bridge-decks" not in fids
    # zoom smoothing: near-zero source simplification
    assert flat["sources"]["roads"]["tolerance"] == 0.05


def test_web_bridge_forks_stay_elevated():
    """Where bridge sections meet (a fork node), the structure is ONE bridge: no chain may ramp
    to the ground at the shared junction — only true ground ends descend."""
    a, b = (18.00, 59.30), (18.01, 59.305)
    g = gpd.GeoDataFrame(
        {"highway": ["primary"] * 3, "bridge": ["yes"] * 3},
        geometry=[LineString([a, b]),                       # A-B
                  LineString([b, (18.02, 59.31)]),          # B-C
                  LineString([b, (18.02, 59.30)])],         # B-D  -> B is a bridge fork
        crs=4326)
    style = _style(render_edges(g, backend="web", view_3d=True).html)
    slices = style["sources"]["decks"]["data"]["features"]
    # every chain touching the fork keeps full height there; grounds exist only at A/C/D
    import collections
    ends = collections.defaultdict(list)
    for f in slices:
        ends[f["properties"]["__rs_base"]].append(f)
    assert 5.0 in ends                       # plateaus exist
    grounded = [f for f in slices if f["properties"]["__rs_base"] < 0.5]
    assert grounded                          # the true ends still ramp to ground
    # no slice adjacent to the fork node is grounded: check min distance of grounded slices to B
    bx, by = 18.01, 59.305
    for f in grounded:
        cs = f["geometry"]["coordinates"][0]
        dmin = min(((x - bx) ** 2 + (y - by) ** 2) ** 0.5 for x, y in cs)
        assert dmin > 0.001                  # ~110 m: grounded slices are far from the junction


def test_web_pick_survives_missing_layers():
    """The 3D view removes roads-bridge-fill (decks replace it); the picker must filter its layer
    list to existing layers or every hover/click errors out and nothing is selectable."""
    html = render_edges(_edges(), backend="web", view_3d=True).html
    assert "PICK_LAYERS.filter(id=>map.getLayer(id))" in html
    assert "concat(RS_DECK_LAYERS)" in html.split("PICK_LAYERS")[1][:220]


def test_web_camera_max_pitch():
    """The tilt limit is a setting (camera.max_pitch, default 70: past ~72 MapLibre's horizon
    tile cover explodes on large GeoJSON sources — roads stop rendering and hover/select dies
    with them, so the camera is bounded to the regime that renders) — MapLibre's default 60 made
    the camera stop partway when tilting interactively."""
    assert "maxPitch:70" in render_edges(_edges(), backend="web").html


def test_snapshot_writes_png(tmp_path):
    """rs.snapshot: WebMap -> PNG through headless Chromium, honouring the camera args."""
    import pytest
    pytest.importorskip("playwright.sync_api")   # optional dep; the browser CI job runs this
    import roadstyle as rs

    wm = render_edges(_edges(), backend="web")
    out = tmp_path / "shot.png"
    rs.snapshot(wm, out, zoom=13, width=500, height=400, settle=1.5)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 10_000
    rs.snapshot(wm.html, out, zoom=13, width=500, height=400, scale=2, settle=1.5)  # an HTML str
    head = out.read_bytes()[16:24]                # IHDR: width, height as big-endian uint32
    assert (int.from_bytes(head[:4], "big"), int.from_bytes(head[4:], "big")) == (1000, 800)


def test_web_street_view_window():
    """street_view="window" (the default): a map button opens a floating Street View window that
    follows the clicked road; the popup link opens that window instead of a new tab."""
    import pytest
    win = render_edges(_edges(), backend="web").html                     # the default
    assert "const _svWindow = true;" in win and "const _streetView = true;" in win
    assert "window.rsSetStreetView = rsSetStreetView;" in win and "maps/embed?pb=" in win
    link = render_edges(_edges(), backend="web", street_view=True).html  # the plain link instead
    assert "const _svWindow = false;" in link and "const _streetView = true;" in link
    assert "__SV_WINDOW__" not in win
    with pytest.raises(ValueError):
        render_edges(_edges(), backend="web", street_view="windows")


def test_oneway_column_drives_arrows():
    """The data contract: an explicit `oneway` column controls the arrows (undirected networks
    included); without the column, one-way = an edge with no reverse twin."""
    a, b, c = (18.0, 59.30), (18.01, 59.305), (18.02, 59.31)
    g = gpd.GeoDataFrame(
        {"highway": ["residential"] * 2, "oneway": [True, False]},
        geometry=[LineString([a, b]), LineString([b, c])], crs=4326)
    style = _style(render_edges(g, backend="web").html)
    flags = [f["properties"]["__rs_oneway"] for f in style["sources"]["roads"]["data"]["features"]]
    assert flags == [True, False]          # column wins; no arrows on the two-way street
    slot_oneway = {f["properties"]["oneway"]
                   for f in style["sources"]["slots"]["data"]["features"]}
    assert slot_oneway == {0, 1}           # arrow slots exist only on the oneway=True chain
    # without the column: twin inference (no twin -> one-way)
    g2 = g.drop(columns="oneway")
    style2 = _style(render_edges(g2, backend="web").html)
    flags2 = [f["properties"]["__rs_oneway"] for f in style2["sources"]["roads"]["data"]["features"]]
    assert flags2 == [True, True]


def test_web_panel_popup_mode_and_select_events():
    """road_popup="panel" routes the click read-out into the full-height side panel (curated
    fields); popup_mode="panel" does the same while keeping a custom field list; rs:select /
    rs:deselect CustomEvents fire in every mode for host pages."""
    panel = render_edges(_edges(), backend="web", road_popup="panel").html
    assert '_popupMode = "panel"' in panel and 'className="rs-side"' in panel.replace("'", '"')
    custom = render_edges(_edges(), backend="web", road_popup=["name"], popup_mode="panel").html
    assert '_popupMode = "panel"' in custom and '["name"]' in custom
    default = render_edges(_edges(), backend="web").html
    assert '_popupMode = "popup"' in default
    for html in (panel, default):
        assert 'CustomEvent("rs:select"' in html and 'CustomEvent("rs:deselect"' in html


def test_render_edges_scoped_settings():
    """render_edges(..., settings=...) applies a settings override for that one render only —
    no files, no lingering global state."""
    styled = render_edges(_edges(), backend="web",
                          settings={"config": {"labels": {"color": "#123123"}}}).html
    assert '"text-color": "#123123"' in styled
    plain = render_edges(_edges(), backend="web").html
    assert '"text-color": "#5b5b5b"' in plain      # fully restored afterwards


def test_overlay_defaults_come_from_settings():
    """Overlay styling defaults live in the `overlays` settings block (per-Overlay values win)."""
    from roadstyle import Overlay
    styled = render_edges(_edges(), backend="web", overlays=[Overlay(_pois())],
                          settings={"config": {"overlays": {"color": "#112233", "radius": 11}}}).html
    assert "#112233" in styled and '"circle-radius": 11' in styled
    explicit = render_edges(_edges(), backend="web",
                            overlays=[Overlay(_pois(), color="#ffd166")],
                            settings={"config": {"overlays": {"color": "#112233"}}}).html
    assert "#ffd166" in explicit                     # per-Overlay value wins over the setting


def test_blank_basemap_is_tile_free_and_offline():
    """basemap="blank" renders on a plain background colour: no raster source at all when the
    switcher is off — a saved file makes zero network requests."""
    wm = render_edges(_edges(), backend="web", basemap="blank", basemap_switcher=False)
    style = _style(wm.html)
    assert style["layers"][0] == {"id": "bg", "type": "background",
                                  "paint": {"background-color": "#efede8"}}
    assert "bm" not in style["sources"]
    assert "cartocdn" not in wm.html and "arcgisonline" not in wm.html


def test_blank_basemap_with_switcher_precreates_hidden_raster():
    """blank active + tiled maps offered: the raster layer exists but starts hidden, so the
    dropdown can flip visibility without adding sources at runtime."""
    wm = render_edges(_edges(), backend="web", basemap="blank",
                      basemaps=["blank", "voyager"])
    style = _style(wm.html)
    raster = next(l for l in style["layers"] if l["id"] == "basemap")
    assert raster["layout"] == {"visibility": "none"}
    assert style["sources"]["bm"]["tiles"]           # voyager tiles, ready to show
    m = re.search(r"BASEMAPS = (\[.*?\]);", wm.html, re.S)
    entries = json.loads(m.group(1))
    assert entries[0]["tiles"] == [] and entries[0]["bg"] == "#efede8"


def test_basemap_maxzoom_reaches_the_page():
    """Past a provider's last level MapLibre must scale that level up. Esri's grey maps end at 16
    and answer beyond it with HTTP 200 and a placeholder image, so without maxzoom the map went
    grey from zoom 17. Switching rebuilds the source, so every switcher entry carries its own."""
    wm = render_edges(_edges(), backend="web", basemap="esri_gray",
                      basemaps=["esri_gray", "osm", "blank"])
    assert _style(wm.html)["sources"]["bm"]["maxzoom"] == 16
    entries = json.loads(re.search(r"BASEMAPS = (\[.*?\]);", wm.html, re.S).group(1))
    assert {e["key"]: e["maxzoom"] for e in entries} == {"esri_gray": 16, "osm": 19, "blank": 19}
    assert "Esri" in entries[0]["attr"] and "OpenStreetMap" in entries[1]["attr"]


def test_keyed_basemap_keeps_every_field():
    """Injecting an API key copies the base map; the copy used to re-list fields by hand."""
    from roadstyle.basemaps import BASEMAPS, get_basemap
    keyed = get_basemap("voyager", api_key="k")
    assert "key=k" in keyed.url and keyed.maxzoom == 20
    assert (keyed.bg, keyed.preview, keyed.lonboard) == (
        BASEMAPS["voyager"].bg, BASEMAPS["voyager"].preview, BASEMAPS["voyager"].lonboard)


def test_js_api_hooks_are_baked():
    """Every UI control has a window.rs* setter + rs:* event, usable from outside JS."""
    wm = render_edges(_edges(), backend="web")
    for needle in ("window.rsSetBasemap", "window.rsSetClasses", "window.rsSetOverlay",
                   "window.rsSetColorField", "rs:basemapchange", "rs:filterchange",
                   "rs:overlaychange"):
        assert needle in wm.html, needle


def test_switcher_off_with_explicit_basemaps_keeps_them_addressable():
    """basemap_switcher=False hides the dropdown but an explicit basemaps= list stays fully
    baked, so window.rsSetBasemap('key') can drive a custom UI."""
    wm = render_edges(_edges(), backend="web", basemaps=["voyager", "blank"],
                      basemap_switcher=False)
    m = re.search(r"BASEMAPS = (\[.*?\]);", wm.html, re.S)
    assert [e["key"] for e in json.loads(m.group(1))] == ["voyager", "blank"]
    assert "const BM_SWITCHER = false" in wm.html
    # without an explicit list, only the fixed backdrop is baked (nothing to switch to)
    wm2 = render_edges(_edges(), backend="web", basemap_switcher=False)
    m2 = re.search(r"BASEMAPS = (\[.*?\]);", wm2.html, re.S)
    assert len(json.loads(m2.group(1))) == 1


def test_query_id_verbs_are_baked():
    """rsQuery -> id set, then rsFilter / rsColor / rsHighlight / rsGetProps act on it."""
    wm = render_edges(_edges(), backend="web")
    for needle in ("window.rsQuery", "window.rsFilter", "window.rsColor",
                   "window.rsHighlight", "window.rsGetProps", "rs:highlightchange"):
        assert needle in wm.html, needle


def test_view3d_and_select_hooks_are_baked():
    """rsSetView3D / rsSelect / rsDeselect complete the API: every interaction has a
    programmatic twin."""
    wm = render_edges(_edges(), backend="web")
    for needle in ("window.rsSetView3D", "window.rsSelect", "window.rsDeselect",
                   "rs:viewchange"):
        assert needle in wm.html, needle


def test_focus_hook_is_baked():
    wm = render_edges(_edges(), backend="web")
    assert "window.rsFocus" in wm.html and "fitBounds" in wm.html


def test_deck_slices_carry_their_road_id():
    """Every 3D deck slice bakes __rs_edges (its OWN directed edge's road feature id), the link
    rsSelect/rsHighlight/hover use to glow the deck instead of the flat 2D line."""
    g = _edges().assign(bridge=["yes", None, None])
    wm = render_edges(g, backend="web", view_3d=True)
    style = _style(wm.html)
    feats = style["sources"]["decks"]["data"]["features"]
    slices = [f for f in feats if "__rs_casing_slab" not in f["properties"]]
    assert slices and all("__rs_edges" in s["properties"] for s in slices)
    assert "0" in slices[0]["properties"]["__rs_edges"].split(",")  # edge 0 is the bridge
    # the black casing ring: slab features + a casing-colour extrusion layer under the body
    assert any("__rs_casing_slab" in f["properties"] for f in feats)
    cas = next(l for l in style["layers"] if l["id"] == "roads-deck-casing")
    assert cas["paint"]["fill-extrusion-color"] == "#000000"


def test_dashed_path_classes_get_dash_layers():
    """footway/path/steps/cycleway carry a palette dash (__rs_dash); the web backend renders
    them as dashed sibling fill layers (butt caps — round would seal the gaps) and drops them
    from the solid fill + casing layers so the gaps show the ground."""
    g = gpd.GeoDataFrame(
        {"highway": ["footway", "cycleway", "residential"]},
        geometry=[LineString([(18.0, 59.30), (18.01, 59.305)]),
                  LineString([(18.01, 59.305), (18.02, 59.31)]),
                  LineString([(18.02, 59.31), (18.03, 59.315)])], crs=4326)
    style = _style(render_edges(g, backend="web").html)
    lay = {l["id"]: l for l in style["layers"]}
    dash_layers = [l for i, l in lay.items() if i.startswith("roads-fill-dash")]
    assert len(dash_layers) == 2               # highsat: footway 4,4 / cycleway 6,4
    assert all("line-dasharray" in l["paint"] for l in dash_layers)
    assert all(l["layout"]["line-cap"] == "butt" for l in dash_layers)
    assert "__rs_dash" in json.dumps(lay["roads-fill"]["filter"])      # solid excludes dashed
    assert "__rs_dash" in json.dumps(lay["roads-casing"]["filter"])    # no casing band either
    # z-order: dashed classes sit at the bottom of the table, so their layers draw UNDER the
    # solid casing+fill — a residential street covers a footway crossing it (osm-carto order)
    ids = [l["id"] for l in style["layers"]]
    for dl in dash_layers:
        assert ids.index(dl["id"]) < ids.index("roads-casing") < ids.index("roads-fill")




def test_stacked_bridges_order_by_osm_layer():
    """Bridges carry their OSM `layer` in lvl (min 1), so a layer=3 viaduct sorts above a
    layer=1 footbridge instead of falling back to class importance; tunnels mirror it (max -1),
    and a positive layer alone still isn't a bridge."""
    g = gpd.GeoDataFrame(
        {"highway": ["footway", "residential", "residential", "residential"],
         "bridge": ["yes", "yes", None, None],
         "tunnel": [None, None, "yes", None],
         "layer": ["1", "3", "-2", "1"]},
        geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)])
                  for i in range(4)], crs=4326)
    style = _style(render_edges(g, backend="web").html)
    lvls = {f["properties"]["highway"] + str(i): f["properties"]["lvl"]
            for i, f in enumerate(style["sources"]["roads"]["data"]["features"])}
    assert list(lvls.values()) == [1, 3, -2, 1]     # the plain layer=1 road: above ground too


def test_twoway_bridge_decks_split_per_directed_edge():
    """A two-way bridge gets TWO side-by-side half ribbons — one per directed twin — each baked
    with __rs_edges = its own road feature id, so hover/select separates the directions instead
    of lighting the whole structure."""
    a, b = (18.00, 59.30), (18.01, 59.305)
    g = gpd.GeoDataFrame(
        {"highway": ["primary", "primary"], "bridge": ["yes", "yes"]},
        geometry=[LineString([a, b]), LineString([b, a])], crs=4326)
    html = render_edges(g, backend="web", view_3d=True).html
    slices = [f for f in _style(html)["sources"]["decks"]["data"]["features"]
              if "__rs_casing_slab" not in f["properties"]]
    owners = {s["properties"]["__rs_edges"] for s in slices}
    assert owners == {"0", "1"}                    # both directions present, separately owned
    assert 'key:"e"+e' in html                     # deck hover keys on the edge, not the chain


def test_query_verbs_accept_overlay_layer_arg():
    """rsQuery/rsFilter/rsColor/rsHighlight/rsGetProps/rsFocus take an optional overlay label."""
    wm = render_edges(_edges(), backend="web")
    for needle in ("function rsQuery(test, layer)", "function rsFilter(ids, layer)",
                   "function rsColor(ids, color, layer)", "function rsHighlight(ids, layer)",
                   "function rsGetProps(ids, layer)", "function rsFocus(ids, opt, layer)"):
        assert needle in wm.html, needle


def test_bridge_deck_width_scale_setting():
    """bridge_decks.width_scale (settings) trims the 3D ribbon width."""
    g = _edges().assign(bridge=["yes", None, None])
    def deck_w(scale):
        wm = render_edges(g, backend="web", view_3d=True,
                          settings={"config": {"bridge_decks": {"width_scale": scale}}})
        ring = _style(wm.html)["sources"]["decks"]["data"]["features"][0]["geometry"]["coordinates"][0]
        xs = [c[0] for c in ring]
        ys = [c[1] for c in ring]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))
    assert deck_w(0.5) < deck_w(1.0) * 0.75


def test_web_street_view_link():
    """The road read-out carries a Google Street View link by default (heading from the clicked
    edge's direction, computed in the page); street_view=False turns it off."""
    on = render_edges(_edges(), backend="web").html
    assert "const _streetView = true;" in on and "map_action=pano" in on
    off = render_edges(_edges(), backend="web", street_view=False).html
    assert "const _streetView = false;" in off
    assert "__STREET_VIEW__" not in on + off
    # host pages whose own panel replaces the popup get the same URL on the click event
    assert on.count("streetView:_svPick(") == 2
    # the point goes onto the edge's own geometry (the road centre line), not the raw click on a
    # drawn lane, which can sit nearer an indoor photo than the road's Street View imagery...
    assert "const m=_svMeasure(f, ll), p=m==null ? null : _svAt(f, m);" in on
    # ...and a two-way edge moves into its own lane, so the two directions stand apart
    assert "const _SV_LANE_M = 2.5" in on and "f.properties.__rs_twoway" in on
    # a map marker shows where Street View stands; the step buttons walk along the edge
    assert "window.rsStreetViewStep = rsStreetViewStep;" in on and '"rs:streetviewmove"' in on
    assert "rsSetStreetViewMarker(!!on);" in on and 'data-step="15"' in on
    # the marker sits on the DRAWN lane (roads-fill's own line-offset at this zoom), not 2.5 m out,
    # which is off the road when zoomed in; and it follows zoom / rotate / pitch
    assert 'map.getPaintProperty("roads-fill", "line-offset")' in on
    assert 'map.on("move", _svMarkPlace);' in on


def test_basemap_button_is_a_map_control_in_the_top_right_column():
    html = render_edges(_edges(), backend="web", basemaps=["positron", "osm"]).html
    # added with map.addControl like 2D/3D and Street View, not appended to <body>
    assert "bm-ctrl" in html and "maplibregl-ctrl maplibregl-ctrl-group bm-ctrl" in html
    assert "document.body.appendChild(menu)" not in html
    # its placement outranks a host page's old `.bm-icon{right:...}` workaround
    assert ".maplibregl-ctrl .bm-menu{position:absolute !important" in html


def test_zoom_readout_is_on_by_default_and_can_be_turned_off():
    assert "if(true){ const zd=" in render_edges(_edges(), backend="web").html
    assert "if(false){ const zd=" in render_edges(_edges(), backend="web", zoom_readout=False).html


def test_tunnel_casing_in_two_tones():
    """A tunnel's casing is never missing: two dark shades of the road's own casing, a solid one
    (the casing colour of the low band's casing layer, baked per edge) with darker dashes on top (a
    sublayer), so connected tunnels look connected (empty dash gaps hid it) while the dash says "tunnel"."""
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "tunnel": ["yes", None]},
                         geometry=[LineString([(18.0, 59.30), (18.01, 59.30)]),
                                   LineString([(18.01, 59.30), (18.02, 59.30)])], crs=4326)
    style = _style(render_edges(g, backend="web").html)          # highsat: primary casing #bcbcbc
    lay = {l["id"]: l for l in style["layers"]}
    ids = list(lay)
    assert ids.index("roads-casing") < ids.index("roads-casing-dash") < ids.index("roads-fill")
    assert "__rs_casing_dash" in json.dumps(lay["roads-casing-dash"]["paint"]["line-color"])
    assert "__rs_tunnel" in json.dumps(lay["roads-casing-dash"]["filter"])      # only the tunnel look
    assert lay["roads-casing-dash"]["paint"]["line-dasharray"] == [2, 2]
    tun, street = (f["properties"] for f in style["sources"]["roads"]["data"]["features"])
    assert tun["__rs_casing"] == "#8d8d8d"                       # the solid tone IS the low casing's colour
    assert tun["__rs_casing_gap"] == "#8d8d8d" and tun["__rs_casing_dash"] == "#5e5e5e"  # 25 / 50 % darker
    assert street["__rs_casing"] == "#bcbcbc" and "__rs_casing_dash" not in street
    mono = _style(render_edges(g, backend="web", palette="mono").html)["sources"]["roads"]["data"]
    tun = mono["features"][0]["properties"]                     # mono primary casing #4f4f4f
    assert tun["__rs_casing"] == "#4f4f4f" and tun["__rs_casing_dash"] == "#282828"      # dark, darker





def test_rscolor_raises_painted_roads_within_their_level():
    """rsColor lifts the painted roads to the top of their level (line-sort-key +500, levels are
    1000 apart): over a street they cross, still under a bridge above them."""
    html = render_edges(_edges(), backend="web").html
    assert "function _applySort()" in html and '["case",["in",["id"],["literal",all]],500,0]' in html
    assert html.index("_applyFill();\n  _applySort();") > html.index("function rsColor(")



def _eval(e, p):
    """Evaluate the few MapLibre expression operators the road band filters use, on properties p."""
    if not isinstance(e, list):
        return e
    op, a = e[0], e[1:]
    if op == "get":
        return p.get(a[0])
    if op == "coalesce":
        return next((v for v in (_eval(x, p) for x in a) if v is not None), None)
    if op == "case":
        for i in range(0, len(a) - 1, 2):
            if _eval(a[i], p):
                return _eval(a[i + 1], p)
        return _eval(a[-1], p)
    if op == "to-boolean":
        return bool(_eval(a[0], p))
    if op == "!":
        return not _eval(a[0], p)
    if op == "all":
        return all(_eval(x, p) for x in a)
    x, y = _eval(a[0], p), _eval(a[1], p)
    return {"<": x < y, ">": x > y, "==": x == y}[op]




def test_order_and_band_survive_tiles():
    """The tiles keep every __rs_* property, so band / order work with tiles=True."""
    from roadstyle.tiles import tile_props
    props = tile_props({"highway": "footway", "__rs_band": 1, "__rs_order": 3.0, "x": 1}, {"highway"})
    assert props == {"highway": "footway", "__rs_band": 1, "__rs_order": 3.0}


def test_tunnels_toggle_like_bridges():
    """A Tunnels on/off row next to Bridges (rsSetTunnels): only when the data has tunnels; it
    hides every lvl < 0 feature (roads, names, arrows, mouths), not the bridge decks."""
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "tunnel": ["yes", None]},
                         geometry=[LineString([(18.0, 59.30), (18.01, 59.30)]),
                                   LineString([(18.01, 59.30), (18.02, 59.30)])], crs=4326)
    html = render_edges(g, backend="web").html
    assert '"tunnels": true' in html and "function rsSetTunnels(" in html and '"rs-flt-tn"' in html
    assert '[">=",["coalesce",["get","lvl"],0],0]' in html
    plain = render_edges(_edges(), backend="web").html
    assert '"tunnels": false' in plain


def test_links_draw_below_every_street_like_osm_carto():
    """Every *_link sorts below every non-link street (residential included) and above service,
    in its parent's order: a primary_link no longer covers the residential street it meets
    (docs/design/junction_order.md, step 1). A link the table doesn't list stays under its parent."""
    from roadstyle import render_web
    key = render_web._sort_key("highway")[2]                # ["match", ["get", col], c, z, ..., default]
    z = dict(zip(key[2:-1:2], key[3:-1:2], strict=True))
    links = ["motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"]
    assert all(z["pedestrian"] > z[l] > z["service"] for l in links)
    assert [z[l] for l in links] == sorted((z[l] for l in links), reverse=True)
    assert z["primary_link"] < z["residential"]
    render_web.ROAD_Z.pop("trunk_link")
    try:
        assert render_web._sort_key("highway")[2][render_web._sort_key("highway")[2].index("trunk_link") + 1] == 7.5
    finally:
        render_web._load_road_model()




# ---- two-way pairs end like one road (docs/design/twin_ends.md) ---------------------------------

def _pairs():
    """A two-way residential street (a twin pair), a one-way street, a two-way bridge, a two-way
    tunnel and a two-way (dashed) footway."""
    a, b = (18.00, 59.30), (18.00, 59.31)
    rows = [("residential", None, None, [a, b]), ("residential", None, None, [b, a]),
            ("residential", None, None, [(18.01, 59.30), (18.01, 59.31)]),
            ("primary", "yes", None, [(18.02, 59.30), (18.02, 59.31)]),
            ("primary", "yes", None, [(18.02, 59.31), (18.02, 59.30)]),
            ("primary", None, "yes", [(18.03, 59.30), (18.03, 59.31)]),
            ("primary", None, "yes", [(18.03, 59.31), (18.03, 59.30)]),
            ("footway", None, None, [(18.04, 59.30), (18.04, 59.31)]),
            ("footway", None, None, [(18.04, 59.31), (18.04, 59.30)])]
    return gpd.GeoDataFrame({"highway": [r[0] for r in rows], "bridge": [r[1] for r in rows],
                             "tunnel": [r[2] for r in rows]},
                            geometry=[LineString(r[3]) for r in rows], crs=4326)


def test_twin_pairs_get_one_end_cap_per_end():
    style = _style(render_edges(_pairs(), backend="web").html)
    pts = style["sources"]["ends"]["data"]["features"]
    # only the plain, solid two-way street: two ends, both twins' ids; no one-way, bridge, tunnel,
    # or dashed pair
    assert len(pts) == 2
    assert {(p["properties"]["__rs_road"], p["properties"]["__rs_road2"]) for p in pts} == {(0, 1)}
    assert {tuple(p["geometry"]["coordinates"]) for p in pts} == {(18.0, 59.3), (18.0, 59.31)}
    assert pts[0]["properties"]["__rs_fill"] and pts[0]["properties"]["highway"] == "residential"




def test_end_caps_follow_filters_and_recolour_and_can_be_turned_off():
    html = render_edges(_pairs(), backend="web").html
    assert 'kind==="ends"' in html and "__rs_road2" in html                  # id filters
    assert 'RS_END_LAYERS.forEach(id=>{ if(map.getLayer(id)) map.setPaintProperty(id,"circle-color",ee)' in html
    off = _style(render_edges(_pairs(), backend="web", settings={"config": {"twin_end_caps": False}}).html)
    assert "ends" not in off["sources"] and not [l for l in off["layers"] if "ends" in l["id"]]


def test_end_caps_hide_where_the_two_directions_differ():
    """A map coloured per direction (twins with different colours) keeps today's ends: the cap is
    transparent unless both lanes share a colour, so no direction's colour shows at a street's end."""
    g = _pairs().iloc[:2].assign(edge_id=["a", "b"])
    html = render_edges(g, backend="web", color_table={"a": "#ff0000", "b": "#0000ff"}).html
    style = _style(html)
    p = style["sources"]["ends"]["data"]["features"][0]["properties"]
    assert p["__rs_fill"] != p["__rs_fill__b"]
    fill = {l["id"]: l for l in style["layers"]}["roads-ends-fill"]["paint"]["circle-color"]
    assert fill[0] == "case" and fill[1] == ["==", ["get", "__rs_fill"], ["get", "__rs_fill__b"]]
    assert fill[-1] == "rgba(0,0,0,0)"
    same = _style(render_edges(_pairs().iloc[:2], backend="web").html)["sources"]["ends"]["data"]["features"][0]["properties"]
    assert same["__rs_fill"] == same["__rs_fill__b"]




def test_directed_col_draws_a_pair_as_two_lanes_only_when_both_edges_are_directed():
    """``directed_col`` false = an undirected edge (a footway stored both ways, a one-way street's
    walking-only reverse): its pair is one line, centred and full width, with no end caps.
    True / null on both = the geometry rule (two lanes); one false edge is enough for one line."""
    a, b = (18.00, 59.30), (18.00, 59.31)

    def lanes(directed, oneway=None):
        cols = {"highway": ["residential"] * 2, "is_directed": directed}
        if oneway:
            cols["oneway"] = oneway
        g = gpd.GeoDataFrame(cols, geometry=[LineString([a, b]), LineString([b, a])], crs=4326)
        st = _style(render_edges(g, backend="web", directed_col="is_directed").html)
        ps = [f["properties"] for f in st["sources"]["roads"]["data"]["features"]]
        return [p["__rs_twoway"] for p in ps], [p["__rs_oneway"] for p in ps], "ends" in st["sources"]

    assert lanes([True, True]) == ([True, True], [False, False], True)        # a two-way street
    assert lanes([None, None])[0] == [True, True]
    assert lanes([False, False]) == ([False, False], [False, False], False)   # a footway: one line, no arrows
    # a one-way street + its walking-only reverse: one line; arrows on the car edge only
    assert lanes([True, False]) == ([False, False], [True, False], False)
    assert lanes([True, False], oneway=[True, False])[1] == [True, False]     # `oneway` still rules arrows


# ---- a tunnel is an ordinary road with a tunnel style (mapstyle's junctions.md, rule 1) ----------

def _tunnel_world(cross):
    """street A -- tunnel T -- street B along one line; with ``cross``, street C crosses over the
    tunnel's middle without joining it."""
    a, b, c, d = (18.000, 59.30), (18.002, 59.30), (18.004, 59.30), (18.006, 59.30)
    rows = [("primary", None, [a, b]), ("primary", "yes", [b, c]), ("primary", None, [c, d])]
    if cross:
        rows.append(("residential", None, [(18.003, 59.299), (18.003, 59.301)]))
    return gpd.GeoDataFrame({"highway": [r[0] for r in rows], "tunnel": [r[1] for r in rows]},
                            geometry=[LineString(r[2]) for r in rows], crs=4326)


def test_a_bridge_deck_casing_shows_with_metre_widths_and_no_casing():
    """With ``width_m_col`` and ``casing_m=0`` a casing is as wide as the fill and hidden: a bridge's deck casing is at
    least ``bridge_casing_m`` each side, so the bridge look shows."""
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "bridge": ["yes", None], "w": [3.25, 3.25]},
                         geometry=[LineString([(18.0, 59.30), (18.01, 59.30)]), LineString([(18.0, 59.31), (18.01, 59.31)])],
                         crs=4326)
    st = _style(render_edges(g, backend="web", width_m_col="w", casing_m=0).html)
    lay = {l["id"]: l for l in st["layers"]}
    bc = next(l for i, l in lay.items() if i.endswith("-bridge"))["paint"]["line-width"]
    assert '["max", ["get", "__rs_cm"], 0.25]' in json.dumps(bc)
    assert '2.0' in json.dumps(bc)        # 2 * bridge_casing_px: the pixel floor
    assert "0.25" not in json.dumps(lay["roads-casing"]["paint"]["line-width"])        # a plain road's casing is untouched






def test_tunnels_get_light_dashes_on_their_fill_unless_turned_off():
    """Kaveh's pick among three samples ("light dash is ok"): over the tunnel's fill, translucent, butt-capped; not on
    a dashed class; `tunnel_fill_dash: []` turns it off."""
    st = _style(render_edges(_tunnel_world(True), backend="web").html)
    lay = {l["id"]: l for l in st["layers"]}
    ids = [l["id"] for l in st["layers"]]
    pat = lay["roads-fill-lv-1-pat"]
    assert ids.index(pat["id"]) > ids.index("roads-fill-lv-1") and pat["source"] == "roads"
    assert pat["paint"]["line-dasharray"] == [1.2, 1.2] and pat["layout"]["line-cap"] == "butt"
    assert pat["paint"]["line-color"].startswith("rgba(255,255,255")
    assert '"__rs_dash"' in json.dumps(pat["filter"]) and "__rs_tunnel" in json.dumps(pat["filter"])
    off = _style(render_edges(_tunnel_world(True), backend="web", settings={"config": {"tunnel_fill_dash": []}}).html)
    assert not any(l["id"].endswith("-pat") for l in off["layers"])


def test_colour_by_recolours_the_dashed_layers_too():
    """A footway / path / steps edge is drawn by a ``-dash<n>`` layer (line-dasharray is not data-driven): it must
    follow the active colouring, or it keeps its class colour under any "colour by"."""
    html = render_edges(_tunnel_world(True), backend="web").html
    assert 'const RS_FILL_LAYERS = ["roads-fill", "roads-fill-sq", "roads-fill-lv-1"' in html
    assert 'dashed(RS_FILL_LAYERS).forEach(id=>map.setPaintProperty(id,"line-color",e))' in html
    assert "RS_PIECE_LAYERS" not in html and "tpieces" not in html




def _metre_map(**kw):
    """Two parallel lanes 3.25 m apart (one 3.25 m wide, one without a width) and a plain road."""
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "w": [3.25, None, 5.0]},
                         geometry=[LineString([(18.00, 59.30), (18.01, 59.30)]),
                                   LineString([(18.00, 59.30003), (18.01, 59.30003)]),
                                   LineString([(18.00, 59.31), (18.01, 59.31)])], crs=4326)
    st = _style(render_edges(g, backend="web", **kw).html)
    width = {ly["id"]: ly["paint"]["line-width"] for ly in st["layers"] if "line-width" in ly.get("paint", {})}
    return st["sources"]["roads"]["data"]["features"], width


def _stop(expr, z):
    return expr[expr.index(z, 3) + 1]


def test_metre_width_is_exact_at_zoom_22():
    """docs/design/metre_widths.md: the casing is the line's width in metres, the fill that minus
    2 casings, both over cos(latitude); zoom 22 is a stop, base-2 exponential between stops."""
    feats, width = _metre_map(width_m_col="w")
    p = feats[0]["properties"]
    sec = 1 / math.cos(math.radians(59.30))
    assert abs(p["__rs_wm"] - 3.25 * sec) < 1e-3 and abs(p["__rs_cm"] - 0.15 * sec) < 1e-3
    assert "__rs_wm" not in feats[1]["properties"]          # null width -> class width
    px22 = 512 * 2 ** 22 / 40075016.686
    fill, casing = _stop(width["roads-fill"], 22), _stop(width["roads-casing"], 22)
    assert width["roads-fill"][1] == ["exponential", 2]
    assert fill[0] == "case" and fill[1] == ["has", "__rs_wm"]

    def ev(e):   # the metre width the expression multiplies: fill = width - 2 casings
        return p["__rs_wm"] - 2 * p["__rs_cm"] if e[0] == "max" else p["__rs_wm"]
    assert abs(ev(fill[2][1]) * fill[2][2] - (3.25 - 0.30) * sec * px22) < 0.05
    assert abs(ev(casing[2][1]) * casing[2][2] - 3.25 * sec * px22) < 0.05


def test_metre_width_keeps_class_widths_below_its_zoom():
    _, plain = _metre_map()
    _, metre = _metre_map(width_m_col="w", width_m_zoom=16)
    for z in (12, 15):
        assert _stop(metre["roads-fill"], z) == _stop(plain["roads-fill"], z)
    assert _stop(metre["roads-fill"], 16)[3] == _stop(plain["roads-fill"], 16)   # the null-width branch
    assert _stop(metre["roads-fill"], 22)[3] == _stop(plain["roads-fill"], 20)   # frozen past 20, as today


def test_no_metre_width_column_leaves_the_style_unchanged():
    feats, width = _metre_map()
    assert width["roads-fill"][1] == ["linear"] and not any("__rs_wm" in f["properties"] for f in feats)


def test_cap_col_gives_square_ends_to_the_edges_that_ask():
    """cap_col (docs/design/square_ends.md): an edge with a true value is drawn by the butt-capped twin of its position's
    casing and fill, and by no round layer; the others keep round ends. Nothing changes without the keyword."""
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "sq": [None, True, 0]},
                         geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(3)],
                         crs=4326)
    style = _style(render_edges(g, backend="web", cap_col="sq").html)
    lay = {l["id"]: l for l in style["layers"]}
    ids = [l["id"] for l in style["layers"]]
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert [p.get("__rs_cap") for p in ps] == [None, True, None]
    assert lay["roads-fill-sq"]["layout"]["line-cap"] == "butt" and lay["roads-fill"]["layout"]["line-cap"] == "round"
    assert [bool(_eval(lay["roads-fill"]["filter"], p)) for p in ps] == [True, False, True]       # round: not the capped edge
    assert [bool(_eval(lay["roads-fill-sq"]["filter"], p)) for p in ps] == [False, True, False]
    assert ids.index("roads-casing") < ids.index("roads-casing-sq") < ids.index("roads-fill") < ids.index("roads-fill-sq")
    plain = _style(render_edges(g.drop(columns="sq"), backend="web").html)
    assert not [l for l in plain["layers"] if l["id"].endswith("-sq")]
    assert "__rs_cap" not in json.dumps(plain["sources"]["roads"])


def test_a_tunnel_fill_has_an_opaque_underlay_so_the_casing_does_not_show_through():
    """The tunnel's fill is translucent (a faded colour); an underlay in the canvas colour sits under it in every position that
    has a tunnel, so the casing and a street's round end under it do not show through (the tunnel keeps its look)."""
    style = _style(render_edges(_tunnel_world(True), backend="web").html)
    ids = [l["id"] for l in style["layers"]]
    lay = {l["id"]: l for l in style["layers"]}
    assert ids.index("roads-casing-lv-1-dash") < ids.index("roads-fill-lv-1-under") < ids.index("roads-fill-lv-1")
    assert lay["roads-fill-lv-1-under"]["paint"]["line-color"].startswith("#") and lay["roads-fill-lv-1-under"]["layout"]["line-cap"] == "butt"
    a, b = (18.000, 59.30), (18.002, 59.30)
    plain = [l["id"] for l in _style(render_edges(gpd.GeoDataFrame({"highway": ["primary"]}, geometry=[LineString([a, b])], crs=4326),
                                                  backend="web").html)["layers"]]
    assert not [i for i in plain if i.endswith("-under")]


def test_level_columns_draw_each_position_casings_then_fills():
    """casing_level_col / fill_level_col (docs/design/level_columns.md): one casing layer and one fill layer for each position, in
    position order; an edge's casing is in the layers of its casing position and its fill in those of its fill position."""
    g = gpd.GeoDataFrame({"highway": ["residential"] * 4, "tunnel": [None, None, "yes", None],
                          "cl": [0, 0, -2, -1], "fl": [0, 1, -2, 1]},
                         geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(4)], crs=4326)
    style = _style(render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl").html)
    lay = {l["id"]: l for l in style["layers"]}
    ids = [l["id"] for l in style["layers"]]
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert [(p["__rs_cl"], p["__rs_fl"]) for p in ps] == [(0, 0), (0, 1), (-2, -2), (-1, 1)]
    for level in (-2, -1, 0, 1):                                     # a casing and a fill layer per position
        cas, fil = lay[_pos_id("roads-casing", level)], lay[_pos_id("roads-fill", level)]
        assert [bool(_eval(cas["filter"], p)) for p in ps] == [p["__rs_cl"] == level for p in ps]
        assert [bool(_eval(fil["filter"], p)) for p in ps] == [p["__rs_fl"] == level for p in ps]
    # in position order, casings before fills of the same position, and position 0 keeps its ids
    order = [_pos_id("roads-casing", l) for l in (-2, -1, 0, 1)]
    assert ids.index(order[0]) < ids.index(_pos_id("roads-fill", -2)) < ids.index(order[1]) < ids.index(_pos_id("roads-fill", -1)) \
        < ids.index("roads-casing") < ids.index("roads-fill") < ids.index(order[3]) < ids.index(_pos_id("roads-fill", 1))
    # the page recolours the fill layers of every position
    html = render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl").html
    assert '"roads-fill-lv1"' in html and '"roads-fill-lv-2"' in html


def _pos_id(root, level):
    return root if level == 0 else f"{root}-lv{level}"


def test_level_columns_keep_the_looks_and_the_dashed_classes():
    """The tunnel look and the dashed classes follow the positions."""
    g = gpd.GeoDataFrame({"highway": ["primary", "footway", "primary"], "tunnel": ["yes", None, None], "cl": [-1, 1, 0], "fl": [-1, 1, 0]},
                         geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(3)], crs=4326)
    style = _style(render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl").html)
    ids = [l["id"] for l in style["layers"]]
    lay = {l["id"]: l for l in style["layers"]}
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert "roads-casing-lv-1-dash" in ids and "roads-fill-lv-1-pat" in ids and "roads-fill-lv-1-under" in ids   # the tunnel's look at -1
    assert [bool(_eval(lay["roads-casing-lv-1-dash"]["filter"], p)) for p in ps] == [True, False, False]
    dash = [i for i in ids if i.startswith("roads-fill-lv1-dash")]                                                  # the footway's dashes at 1
    assert dash and '"__rs_fl"' in json.dumps(lay[dash[0]]["filter"]) and '"__rs_cl"' not in json.dumps(lay[dash[0]]["filter"])


def test_compute_levels_bridge_ends_tunnel_and_ground():
    """compute_levels: a bridge edge is [1, 1] between bridge edges and [0, 1] where it touches the ground, a tunnel mirrors it, ground roads stay [0, 0]."""
    import roadstyle as rs
    xs = [0, 1, 2, 3, 4, 5, 6]
    def seg(i, j):
        return LineString([(18.0 + xs[i] * 0.001, 59.3), (18.0 + xs[j] * 0.001, 59.3)])
    g = gpd.GeoDataFrame({"highway": ["residential"] * 6, "bridge": [None, "yes", "yes", "yes", None, None],
                          "tunnel": [None, None, None, None, None, "yes"], "layer": [None, 1, 1, 1, None, -1]},
                         geometry=[seg(0, 1), seg(1, 2), seg(2, 3), seg(3, 4), seg(4, 5), LineString([(18.01, 59.3), (18.01, 59.31)])], crs=4326)
    out = rs.compute_levels(g, method="tags")
    assert list(zip(out.casing_level, out.fill_level, strict=True)) == [(0, 0), (0, 1), (1, 1), (0, 1), (0, 0), (-1, -1)]




def test_compute_levels_properties_on_random_networks():
    """docs/design/levels_split_casing.md, section 10: c <= f; ground edges [0, 0]; L > 0 gives [min(N), L]; L < 0 gives [L, max(N)];
    two edges that share a node have intersecting intervals."""
    import random

    import roadstyle as rs
    rnd = random.Random(7)
    for _ in range(40):
        pts = {(i, j) for i in range(4) for j in range(4)}
        pairs = [(a, b) for a in pts for b in pts if a < b and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1]
        pairs = rnd.sample(pairs, 14)
        lv = [rnd.choice([-1, 0, 0, 1, 1, 2]) for _ in pairs]
        g = gpd.GeoDataFrame({"highway": ["residential"] * len(pairs), "layer": lv},
                             geometry=[LineString([(18 + a[0] * 1e-3, 59 + a[1] * 1e-3), (18 + b[0] * 1e-3, 59 + b[1] * 1e-3)]) for a, b in pairs], crs=4326)
        out = rs.compute_levels(g, method="tags")
        c, f = list(out.casing_level), list(out.fill_level)
        at = {}
        for (a, b), L in zip(pairs, lv, strict=True):
            at.setdefault(a, []).append(L), at.setdefault(b, []).append(L)
        N = {v: min(max(0, min(s)), max(s)) for v, s in at.items()}             # the point of [min S, max S] nearest 0
        for (a, b), L, ci, fi in zip(pairs, lv, c, f, strict=True):
            assert ci <= fi
            lo, hi = min(N[a], N[b]), max(N[a], N[b])
            assert (ci, fi) == ((0, 0) if L == 0 else (lo, L) if L > 0 else (L, hi))
        for v in at:
            ids = [i for i, p in enumerate(pairs) if v in p]
            for i in ids:
                for j in ids:
                    assert c[i] <= f[j] and c[j] <= f[i]


def test_compute_levels_solve_one_piece_bridge_gets_its_outline():
    """method="solve": a bridge in one piece over a ground road: the intervals meet every constraint, nothing is given up, and the
    bridge's casing is above the road below (which the tag rule cannot do)."""
    import pytest
    pytest.importorskip("scipy")
    import roadstyle as rs
    d = 0.001
    segs = [[(18 - 3 * d, 59), (18 - 2 * d, 59)], [(18 - 2 * d, 59), (18 - d, 59)],      # ground, then the bridge in one piece
            [(18 - d, 59), (18 + d, 59)], [(18 + d, 59), (18 + 2 * d, 59)], [(18 + 2 * d, 59), (18 + 3 * d, 59)],
            [(18, 58.998), (18, 59.002)]]                                                     # a ground road crossing under it, no node shared
    g = gpd.GeoDataFrame({"highway": ["residential"] * 6, "layer": [None, None, 1, None, None, None]},
                         geometry=[LineString(s) for s in segs], crs=4326)
    out = rs.compute_levels(g, method="solve")
    iv = list(zip(out.casing_level, out.fill_level, strict=True))
    assert out.attrs["levels_given_up"] == []
    assert iv[2][0] > iv[5][1]                                         # the bridge's casing is after the crossing road's fill
    # Merge at each shared node, on the heads: the head of one road is not after the fill of the other
    assert out.casing_start[2] <= out.fill_level[1] and out.casing_end[1] <= out.fill_level[2]       # node between road 1 and the bridge
    assert out.casing_end[2] <= out.fill_level[3] and out.casing_start[3] <= out.fill_level[2]       # node between the bridge and road 3
    tags = rs.compute_levels(g, method="tags")
    assert (tags.casing_level[2], tags.fill_level[2]) == (0, 1)        # the tag rule: casing at 0, not above the road below


def test_compute_levels_solve_band_and_order_are_in_the_optimization():
    """band_col: a sidewalk (-1) beside a street is entirely under it, a crossing (+1) that shares a node is entirely over it;
    order: at a junction the road with the higher number gets the higher fill position; equal numbers are not separated."""
    import pytest
    pytest.importorskip("scipy")
    import roadstyle as rs
    d = 0.001
    def line(*p):
        return LineString(list(p))
    # street (0), sidewalk beside it (1), crossing joined to the street's end (2)
    g = gpd.GeoDataFrame({"highway": ["residential", "footway", "footway"], "band": [0, -1, 1]},
                         geometry=[line((18, 59), (18 + d, 59)), line((18, 59.00005), (18 + d, 59.00005)), line((18 + d, 59), (18 + d, 59.001))], crs=4326)
    out = rs.compute_levels(g, method="solve", band_col="band")
    c, f = list(out.casing_level), list(out.fill_level)
    assert out.attrs["levels_given_up"] == []
    assert f[1] < c[0] and c[2] > f[0]                                  # sidewalk entirely under the street, crossing entirely over
    # order: three roads meeting at one node
    o = gpd.GeoDataFrame({"highway": ["primary", "residential", "residential"], "w": [3, 1, 1]},
                         geometry=[line((18, 59), (18 + d, 59)), line((18 + d, 59), (18 + 2 * d, 59)), line((18 + d, 59), (18 + d, 59.001))], crs=4326)
    r = rs.compute_levels(o, method="solve", order="w")
    assert r.fill_level[0] > r.fill_level[1] and r.fill_level[1] == r.fill_level[2]
    assert r.attrs["levels_info"]["order_violations"] == 0
    assert rs.compute_levels(o, method="solve", order="class").fill_level[0] > 0       # the class order: primary over residential
    try:
        rs.compute_levels(o, method="tags", order="w")
        raise AssertionError("order with method='tags' must be refused")
    except ValueError:
        pass


def test_compute_levels_on_the_bundled_sample():
    """docs/design/levels_split_casing.md, section 10, examples on the bundled Södermalm sample: the Centralbron chain (tags) and Skanstullsbron (tags and solve)."""
    import pytest

    import roadstyle as rs
    path = Path(__file__).resolve().parent.parent / "notebooks" / "data" / "sodermalm_edges.gpkg"
    if not path.exists():
        pytest.skip("sample data not present")
    g = gpd.read_file(path).to_crs(4326).reset_index(drop=True)
    t = rs.compute_levels(g, method="tags")
    chain = [2134, 828, 1558, 440, 2219, 2469, 2468]
    assert [(t.casing_level[i], t.fill_level[i]) for i in chain] == [(1, 1), (0, 1), (-1, 0), (-2, -1), (-2, -1), (-2, 0), (0, 0)]
    assert (t.casing_level[207], t.fill_level[207]) == (0, 3)                      # one edge from ground to ground: no outline over the road below
    pytest.importorskip("scipy")
    s = rs.compute_levels(g, method="solve")
    info = s.attrs["levels_info"]
    assert (info["pairs"], info["short_upper_pairs"]) == (336, 54)                  # 390 near pairs, 54 of them with an upper road shorter than 2 * head_m: not stack pairs
    under = [944, 4251, 2082, 2363]
    assert all(s.casing_level[207] > s.fill_level[i] for i in under)                # the bridge is over them, outline included
    assert s.attrs["levels_given_up"] == []                                         # nothing the solver tried is given up


def test_level_columns_put_each_positions_arrows_after_its_fill_layers():
    """Position mode: one-way arrows follow the fill position (not the lvl tag): an arrow layer per position right after that
    position's last fill layer, so a tunnel's arrows are above its own road."""
    import roadstyle as rs
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["primary"] * 3, "oneway": ["yes"] * 3, "tunnel": [None, "yes", None], "bridge": [None, None, "yes"],
                          "layer": [None, -1, 1]},
                         geometry=[LineString([(18, 59 + i * d), (18 + d, 59 + i * d)]) for i in range(3)], crs=4326)
    g = rs.compute_levels(g, method="tags")
    style = _style(render_edges(g, backend="web", casing_level_col="casing_level", fill_level_col="fill_level").html)
    ids = [l["id"] for l in style["layers"]]
    lay = {l["id"]: l for l in style["layers"]}
    for pos in (-1, 0, 1):
        arrows = "roads-arrows" if pos == 0 else f"roads-arrows-lv{pos}"
        fills = [i for i, n in enumerate(ids) if n.startswith(("roads-fill-lv-1", "roads-fill-lv1")) and (f"lv{pos}" in n)] if pos else \
            [i for i, n in enumerate(ids) if n in ("roads-fill", "roads-fill-sq", "roads-fill-under", "roads-fill-pat")]
        assert ids.index(arrows) == max(fills) + 1, arrows                       # right after the position's fill layers
        assert '"fl"' in json.dumps(lay[arrows]["filter"]) and '"lvl"' not in json.dumps(lay[arrows]["filter"])
    assert "roads-arrows-tunnel" not in ids and "roads-arrows-bridge" not in ids


def test_level_columns_put_each_positions_street_names_after_its_arrows():
    """Position mode: street names follow the fill position like the arrows: one name layer per position, right after that
    position's arrow layer, so a road at a higher position covers them."""
    import roadstyle as rs
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["primary"] * 3, "name": ["Tunnel st", "Ground st", "Bridge st"], "oneway": ["yes"] * 3,
                          "tunnel": ["yes", None, None], "bridge": [None, None, "yes"], "layer": [-1, None, 1]},
                         geometry=[LineString([(18, 59 + i * d), (18 + d, 59 + i * d)]) for i in range(3)], crs=4326)
    g = rs.compute_levels(g, method="tags")
    style = _style(render_edges(g, backend="web", casing_level_col="casing_level", fill_level_col="fill_level").html)
    ids = [l["id"] for l in style["layers"]]
    lay = {l["id"]: l for l in style["layers"]}
    for pos in (-1, 0, 1):
        arrows, names = ("roads-arrows", "roads-labels") if pos == 0 else (f"roads-arrows-lv{pos}", f"roads-labels-lv{pos}")
        assert ids.index(names) == ids.index(arrows) + 1, names
        assert '"fl"' in json.dumps(lay[names]["filter"])
    assert ids.index("roads-labels-lv-1") < ids.index("roads-fill") < ids.index("roads-labels-lv1")     # a higher position's names are above lower roads
    plain = [l["id"] for l in _style(render_edges(g, backend="web").html)["layers"]]
    assert plain.count("roads-labels") == 1 and not [i for i in plain if i.startswith("roads-labels-lv")]


def test_every_compute_levels_argument_is_in_the_algorithm_page():
    """The page and the code must agree: each argument of compute_levels is named in docs/design/levels_split_casing.md, and the page names no
    argument the function does not have."""
    import inspect

    import roadstyle as rs
    page = (Path(__file__).resolve().parent.parent / "docs" / "design" / "levels_split_casing.md").read_text()
    params = set(inspect.signature(rs.compute_levels).parameters)
    missing = [p for p in params if f"`{p}`" not in page]
    assert not missing, f"arguments not in the page: {missing}"
    for gone in ("hops", "casing_col", "fill_col"):
        assert gone not in params and f"`{gone}`" not in page, f"{gone} is not an argument any more"


def test_level_columns_draw_each_positions_end_caps_with_that_position():
    """Position mode: the end caps of two-way pairs follow the positions too. For each position the caps' casing layer is right before that
    position's casing layer and the caps' fill layer right before its fill layer, so casings come before fills at every position;
    no cap layer is outside a position."""
    d = 0.001
    a, b, c = [(18, 59), (18 + d, 59)], [(18 + d, 59), (18 + 2 * d, 59)], [(18 + d, 59), (18 + d, 59 + d)]
    rows = [(a, 0, 0), (a[::-1], 0, 0), (b, 1, 1), (b[::-1], 1, 1), (c, -1, -1), (c[::-1], -1, -1)]     # three two-way streets at three positions
    g = gpd.GeoDataFrame({"highway": ["residential"] * 6, "cl": [r[1] for r in rows], "fl": [r[2] for r in rows]},
                         geometry=[LineString(r[0]) for r in rows], crs=4326)
    html = render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl").html
    style = _style(html)
    ids = [l["id"] for l in style["layers"]]
    ends = [i for i in ids if i.startswith("roads-ends")]
    assert sorted(ends) == sorted(["roads-ends-casing", "roads-ends-fill", "roads-ends-casing-lv1", "roads-ends-fill-lv1",
                                   "roads-ends-casing-lv-1", "roads-ends-fill-lv-1"])
    for pos in (-1, 0, 1):
        sfx = "" if pos == 0 else f"-lv{pos}"
        cap_c, cap_f = f"roads-ends-casing{sfx}", f"roads-ends-fill{sfx}"
        casing, fill = f"roads-casing{sfx}", f"roads-fill{sfx}"
        assert ids.index(cap_c) + 1 == ids.index(casing), cap_c                       # the cap casing right before the position's casing layers
        assert ids.index(cap_f) < ids.index(fill) and ids.index(cap_f) > ids.index(casing), cap_f      # the cap fill after the casings, before the fills
    pts = style["sources"]["ends"]["data"]["features"]
    assert {(p["properties"]["__rs_cl"], p["properties"]["__rs_fl"]) for p in pts} == {(0, 0), (1, 1), (-1, -1)}   # a cap carries its road's positions
    assert 'const RS_END_LAYERS = ["roads-ends-fill-lv-1"' in html or '"roads-ends-fill-lv-1"' in html.split("const RS_END_LAYERS =")[1].split(";")[0]


def test_compute_levels_reversed_twin_has_its_heads_the_other_way_round():
    """casing_start belongs to the first vertex of the row's own geometry: the reversed direction of a road gets casing_start and casing_end swapped."""
    import pytest
    pytest.importorskip("scipy")
    import roadstyle as rs
    d = 0.001
    def ground(*p):
        return LineString(list(p))
    # a bridge-like long road whose two heads differ: it meets a tunnel (band -1) at one end only
    rows = [ground((18, 59), (18 + 2 * d, 59)), ground((18 + 2 * d, 59), (18, 59)),             # the road, both directions
            ground((18 - d, 59), (18, 59)),                                                      # a ground road meeting its start
            ground((18 + 2 * d, 59), (18 + 3 * d, 59))]                                          # a tunnel meeting its end
    g = gpd.GeoDataFrame({"highway": ["residential"] * 4, "layer": [None, None, None, -1], "tunnel": [None, None, None, "yes"]},
                         geometry=rows, crs=4326)
    out = rs.compute_levels(g, method="solve")
    assert (out.casing_start[0], out.casing_end[0]) == (0, -1)               # the road's end head meets the tunnel, so it is lower than its start head
    assert (out.casing_start[1], out.casing_end[1]) == (-1, 0)               # the reversed twin starts where the road ends: swapped
    assert out.casing_level[0] == out.casing_level[1] and out.fill_level[0] == out.fill_level[1]


def test_divided_casing_is_drawn_as_head_and_main_pieces():
    """casing_start_col / casing_end_col / head_m: an edge >= 2 * head_m with unequal casing numbers is cut into three casing pieces (first head_m metres,
    middle, last head_m metres), each at its own number, in their own source; the fill stays one line; a short edge is two halves, one at each head's number; an equal-numbered edge is one piece."""
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "cs": [-1, 0, -1], "cm": [0, 0, 0], "ce": [-2, 0, -2], "fl": [0, 0, 0]},
                         geometry=[LineString([(18, 59), (18 + d, 59)]),                    # about 57 m: long, numbers differ -> three pieces
                                   LineString([(18, 59.01), (18 + d, 59.01)]),             # long, numbers equal -> one piece
                                   LineString([(18, 59.02), (18 + 0.00005, 59.02)])],      # about 3 m: shorter than 2 * head_m, numbers differ -> two halves
                         crs=4326)
    html = render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0).html
    style = _style(html)
    parts = style["sources"]["casings"]["data"]["features"]
    by = {}
    for f in parts:
        by.setdefault(f["properties"]["__rs_road"], []).append(f)
    assert [len(by[i]) for i in (0, 1, 2)] == [3, 1, 2]
    assert [f["properties"]["__rs_cl"] for f in by[2]] == [-1, -2]                    # a short road keeps both heads (short_road_heads.md)
    assert [f["properties"]["__rs_cl"] for f in by[0]] == [-1, 0, -2]                 # start head, main, end head
    lengths = [LineString(f["geometry"]["coordinates"]) for f in by[0]]
    assert abs(lengths[0].length * 111320 * math.cos(math.radians(59)) - 5.0) < 0.2 and abs(lengths[2].length * 111320 * math.cos(math.radians(59)) - 5.0) < 0.2
    assert by[0][0]["geometry"]["coordinates"][0] == [18.0, 59.0]                     # the first piece starts at the edge's first vertex
    lay = {l["id"]: l for l in style["layers"]}
    assert all(l["source"] == "casings" for i, l in lay.items() if i.startswith("roads-casing") and "-lv" in i or i == "roads-casing")
    assert lay["roads-fill"]["source"] == "roads" and lay["roads-fill-lv-1"]["source"] == "roads"
    assert style["sources"]["roads"]["data"]["features"][0]["geometry"]["coordinates"][-1] == [18 + d, 59.0]       # the fill line is the whole edge
    assert 'kind==="casings"' in html
    # without the head columns nothing changes: no casing source
    assert "casings" not in _style(render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl").html)["sources"]


def test_divided_casing_main_piece_ends_flat_and_heads_round():
    """The main piece of a divided casing carries __rs_cap (flat ends: a round end would reach into the heads); the heads and an unsplit casing do not, and the
    flat-end twin layer of the casing exists and reads the casing source."""
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["residential"] * 2, "cs": [-1, 0], "cm": [0, 0], "ce": [-2, 0], "fl": [0, 0]},
                         geometry=[LineString([(18, 59), (18 + d, 59)]), LineString([(18, 59.01), (18 + d, 59.01)])], crs=4326)
    style = _style(render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0).html)
    parts = style["sources"]["casings"]["data"]["features"]
    flags = [(f["properties"]["__rs_road"], f["properties"]["__rs_cl"], bool(f["properties"].get("__rs_cap"))) for f in parts]
    assert flags == [(0, -1, False), (0, 0, True), (0, -2, False), (1, 0, False)]       # head, MAIN flat, head; the unsplit edge stays round
    lay = {l["id"]: l for l in style["layers"]}
    assert lay["roads-casing-sq"]["source"] == "casings" and lay["roads-casing-sq"]["layout"]["line-cap"] == "butt" and lay["roads-casing"]["layout"]["line-cap"] == "round"
    assert "__rs_cap" in json.dumps(lay["roads-casing"]["filter"])                   # the round layer leaves the flat pieces to the twin


def test_level_columns_draw_the_bridge_casing_look_at_each_position():
    """Position mode: a bridge edge gets the bridge look in the casing of its position: a heavier black casing with flat ends (roads-casing-bridge, per position),
    from the casing source when the casing is divided; the plain casing layer leaves bridge edges to it; no bridge edge, no such layer."""
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "bridge": ["yes", None], "layer": [None, None], "cm": [0, 0], "fl": [0, 0], "cs": [0, 0], "ce": [0, 0]},
                         geometry=[LineString([(18, 59), (18 + d, 59)]), LineString([(18, 59.01), (18 + d, 59.01)])], crs=4326)     # edge 0 is a bridge, edge 1 is plain, same position
    for kw, source in ((dict(), "roads"), (dict(casing_start_col="cs", casing_end_col="ce"), "casings")):
        style = _style(render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl", **kw).html)
        lay = {l["id"]: l for l in style["layers"]}
        ids = [l["id"] for l in style["layers"]]
        ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
        bl, plain = lay["roads-casing-bridge"], lay["roads-casing"]
        assert bl["source"] == source and bl["layout"]["line-cap"] == "butt" and plain["layout"]["line-cap"] == "round"
        assert bl["paint"]["line-color"] == "#000000" and "line-width" in bl["paint"]
        assert ids.index("roads-casing-bridge") < ids.index("roads-fill")                                  # a casing layer: before the position's fills
        assert [bool(_eval(bl["filter"], p)) for p in ps] == [True, False]                                 # the bridge layer draws the bridge edge only
        assert [bool(_eval(plain["filter"], p)) for p in ps] == [False, True]                              # the plain layer draws the plain edge only
    off = _style(render_edges(g.assign(bridge=None), backend="web", casing_level_col="cm", fill_level_col="fl").html)
    assert not [l for l in off["layers"] if l["id"].startswith("roads-casing") and l["id"].endswith("-bridge")]


def test_twin_end_cap_ring_uses_the_head_number_and_flat_pairs_get_none():
    """Position mode: the casing ring of a twin end cap is painted at the head number of the lane that ends there (casing_start / casing_end), the fill circle at the
    road's fill; a pair drawn flat with cap_col gets no cap."""
    d = 0.001
    a, b = (18, 59), (18 + d, 59)
    rows = [(a, b, -1, -2), (b, a, -2, -1)]                                  # a two-way pair: the lane A->B has start head -1, end head -2; its twin has them the other way round
    g = gpd.GeoDataFrame({"highway": ["residential"] * 2, "cs": [r[2] for r in rows], "ce": [r[3] for r in rows], "cm": [0, 0], "fl": [0, 0], "flat": [False, False]},
                         geometry=[LineString([r[0], r[1]]) for r in rows], crs=4326)
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce")
    style = _style(render_edges(g, **kw).html)
    caps = {tuple(f["geometry"]["coordinates"]): f["properties"] for f in style["sources"]["ends"]["data"]["features"]}
    assert caps[(18.0, 59.0)]["__rs_cl"] == -1 and caps[(18 + d, 59.0)]["__rs_cl"] == -2          # the head numbers at the two nodes
    assert caps[(18.0, 59.0)]["__rs_fl"] == 0                                                      # the fill circle: the road's fill number
    assert "roads-ends-casing-lv-1" in {l["id"] for l in style["layers"]} and "roads-ends-casing-lv-2" in {l["id"] for l in style["layers"]}
    flat = _style(render_edges(g.assign(flat=[True, True]), cap_col="flat", **kw).html)
    assert "ends" not in flat["sources"]                                                           # a pair drawn flat with cap_col gets no cap


def test_compute_levels_lp_stages():
    """The real LP (docs/design/levels_split_casing.md, section 7): nothing to violate is one LP (stage 0); a stack deeper than the range (max_level) is infeasible, so the
    stages 1-3 run with slacks, one pair is given up and a warning is raised; the margin only scales the numbers; the numbers stay integers with the default margin."""
    import pytest
    pytest.importorskip("scipy")
    import warnings as _w

    import roadstyle as rs
    d = 0.001
    rows = [LineString([(18 - 2 * d, 59), (18 + 2 * d, 59)]), LineString([(18, 58.998), (18, 59.002)]),
            LineString([(18 - 2 * d, 58.998), (18 + 2 * d, 59.002)]), LineString([(18 - 2 * d, 59.002), (18 + 2 * d, 58.998)])]     # four long roads crossing at one point
    g = gpd.GeoDataFrame({"highway": ["primary"] * 4, "band": [0, 1, 2, 3]}, geometry=rows, crs=4326)
    ok = rs.compute_levels(g, method="solve", band_col="band")
    assert ok.attrs["levels_info"]["solves"] == 1 and ok.attrs["levels_given_up"] == [] and list(ok.fill_level) == [0, 1, 2, 3]
    half = rs.compute_levels(g, method="solve", band_col="band", margin=0.5)                  # another margin: the same order
    assert list(half.fill_level) == [0, 1, 2, 3] and half.attrs["levels_given_up"] == []
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        tight = rs.compute_levels(g, method="solve", band_col="band", max_level=1)          # three positions only: a stack of four cannot fit
    assert tight.attrs["levels_info"]["solves"] == 4 and len(tight.attrs["levels_given_up"]) == 1
    assert any("could not be satisfied" in str(w.message) for w in caught)
    assert all(isinstance(v, int) for v in tight.fill_level)
    fits = rs.compute_levels(g, method="solve", band_col="band", max_level=1, margin=0.5)    # a smaller margin: the same range holds four positions
    assert fits.attrs["levels_given_up"] == [] and list(fits.fill_level) == [0, 1, 2, 3]
    for bad in (dict(margin=0), dict(max_level=0), dict(margin=-1)):
        with pytest.raises(ValueError):
            rs.compute_levels(g, method="solve", band_col="band", **bad)


def test_levels_are_saved_in_a_visualization_schema_and_read_back():
    """docs/design/levels_split_casing.md, section 11: save_levels writes visualization.edge_levels and edge_levels_meta; load_levels reads them back for the same
    parameters and the same edges, in any row order; other parameters, other edges, duplicate ids or a missing table stop with a message."""
    import pytest
    pytest.importorskip("scipy")
    duckdb = pytest.importorskip("duckdb")
    import roadstyle as rs
    d = 0.001
    rows = [LineString([(18 - 2 * d, 59), (18 + 2 * d, 59)]), LineString([(18, 58.998), (18, 59.002)]),
            LineString([(18 - 2 * d, 58.998), (18 + 2 * d, 59.002)])]
    g = gpd.GeoDataFrame({"edge_id": [9000000000000000001, 12, 345], "highway": ["primary"] * 3, "band": [0, 1, 2]}, geometry=rows, crs=4326)
    levels = rs.compute_levels(g, method="solve", band_col="band")
    con = duckdb.connect(":memory:")
    with pytest.raises(ValueError, match="no visualization.edge_levels_meta"):
        rs.load_levels(con, band_col="band")
    rs.save_levels(con, levels)
    assert {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'visualization'").fetchall()} == {"edge_levels", "edge_levels_meta"}
    assert str(con.execute("DESCRIBE visualization.edge_levels").df().set_index("column_name").loc["edge_id", "column_type"]) == "BIGINT"
    meta = con.execute("SELECT * FROM visualization.edge_levels_meta").df().iloc[0]
    assert (meta["band_source"], meta["head_m"], meta["n_edges"]) == ("band", 5.0, 3) and meta["roadstyle_version"]
    back = rs.load_levels(con, g.iloc[::-1].reset_index(drop=True), band_col="band")                 # the edges in another order
    assert list(back["edge_id"]) == [345, 12, 9000000000000000001]
    for c in ("casing_start", "casing_level", "casing_end", "fill_level"):
        assert list(back[c]) == list(levels[c].iloc[::-1])
    table = rs.load_levels(con, band_col="band")
    assert len(table) == 3 and list(table.columns) == ["edge_id", "casing_start", "casing_level", "casing_end", "fill_level"]
    with pytest.raises(ValueError, match="other parameters"):
        rs.load_levels(con, band_col="band", head_m=1.0)
    with pytest.raises(ValueError, match="other parameters"):
        rs.load_levels(con)                                                                           # the stored band came from a column, not the tags
    with pytest.raises(ValueError, match="not the edges"):
        rs.load_levels(con, g.iloc[:2], band_col="band")
    with pytest.raises(ValueError, match="unique"):
        rs.load_levels(con, g.assign(edge_id=[1, 1, 2]), band_col="band")
    with pytest.raises(ValueError, match="carries the parameters"):
        rs.save_levels(con, g)                                                                        # not the result of compute_levels


def test_render_computes_the_positions_itself_and_refuses_what_is_gone():
    """No level columns: render_edges computes them (the solver, class order) and draws by them; order_col is refused;
    a road with no class takes no part in the class order (docs/design/levels_split_casing.md, section 8)."""
    g = _tunnel_world(True)
    style = _style(render_edges(g, backend="web").html)
    assert [p["properties"]["__rs_cl"] for p in style["sources"]["roads"]["data"]["features"]][3] > [
        p["properties"]["__rs_cl"] for p in style["sources"]["roads"]["data"]["features"]][1]       # the crossing street over the tunnel
    with pytest.raises(ValueError, match="order_col"):
        render_edges(g, backend="web", order_col="o")
    a, b, c = (18.000, 59.30), (18.001, 59.30), (18.001, 59.301)                 # a primary and a service road meet at b: the primary road is painted later
    pair = gpd.GeoDataFrame({"highway": ["primary", "service"]}, geometry=[LineString([a, b]), LineString([b, c])], crs=4326)
    assert compute_levels(pair, method="solve", order="class").attrs["levels_info"]["order_pairs"] == 1
    none = compute_levels(pair.assign(highway=["primary", None]), method="solve", order="class")      # a road with no class: no wish for it
    assert none.attrs["levels_info"]["order_pairs"] == 0


def test_stage_0_flow_has_the_optimum_of_the_lp():
    """Stage 0 as a minimum-cost flow (docs/design/levels_split_casing.md, 7.5): same cost as HiGHS on a difference system, integer numbers that satisfy every row; None for a system without solution."""
    import numpy as np
    import scipy.sparse as sp
    from scipy.optimize import linprog

    from roadstyle.levels import _difference_lp
    rng = np.random.default_rng(3)
    n, m = 40, 120
    ii, jj = rng.integers(0, n, m), rng.integers(0, n, m)
    keep = ii != jj
    ring_i, ring_j = np.arange(n), (np.arange(n) + 1) % n                           # a ring both ways keeps the problem bounded without the box
    ii, jj = np.r_[ii[keep], ring_i, ring_j], np.r_[jj[keep], ring_j, ring_i]
    w = np.r_[rng.integers(0, 4, keep.sum()), np.full(2 * n, 3)].astype(float)
    A = sp.csr_matrix((np.r_[np.ones(len(ii)), -np.ones(len(ii))], (np.r_[np.arange(len(ii)), np.arange(len(ii))], np.r_[ii, jj])), shape=(len(ii), n))
    c = np.zeros(n)
    touched = np.unique(np.r_[ii, jj])
    c[touched[:5]], c[touched[5:10]] = 1.0, -1.0
    x = _difference_lp(c, A, w, 200)
    ref = linprog(c, A_ub=A, b_ub=w, bounds=(0, 200), method="highs")
    assert x is not None and np.allclose(x, np.round(x)) and (A @ x <= w + 1e-9).all()
    assert abs(c @ x - ref.fun) < 1e-6
    assert _difference_lp(c, A, w, x.max() - 1) is None                  # the range above the bound: the caller solves the LP with its bounds
    ring = sp.csr_matrix(([1.0, -1.0, 1.0, -1.0], ([0, 0, 1, 1], [0, 1, 1, 0])), shape=(2, 2))     # x0 - x1 <= -1 and x1 - x0 <= -1
    free = sp.csr_matrix(([1.0, -1.0], ([0, 0], [0, 1])), shape=(1, 3))                              # variable 2 is in no row but has a cost
    assert _difference_lp(np.array([1.0, 0.0, -1.0]), free, np.array([0.0]), 5) is None
    assert _difference_lp(np.array([1.0, -1.0]), ring, np.array([-1.0, -1.0]), 5) is None


def test_the_solver_used_is_reported():
    """levels_info["solver"] is "flow" when stage 0 is solved as a flow, "highs" when the slack stages are needed."""
    g = _tunnel_world(True)
    assert compute_levels(g, method="solve", order="class").attrs["levels_info"]["solver"] == "flow"


def test_the_example_of_the_design_document_7_5_1():
    """An upper road u over a lower road l: a_u <= b_u, a_l <= b_l, b_l + 1 <= a_u; the numbers are a_u = b_u = 1, a_l = b_l = 0 (docs/design/levels_split_casing.md, 7.5.1)."""
    import numpy as np
    import scipy.sparse as sp

    from roadstyle.levels import _difference_lp
    A = sp.csr_matrix(([1.0, -1.0, 1.0, -1.0, 1.0, -1.0], ([0, 0, 1, 1, 2, 2], [0, 1, 2, 3, 3, 0])), shape=(3, 4))      # variables a_u, b_u, a_l, b_l
    x = _difference_lp(np.array([-1.0, 1.0, -1.0, 1.0]), A, np.array([0.0, 0.0, -1.0]), 40)
    assert x.tolist() == [1.0, 1.0, 0.0, 0.0]


def test_min_positions_keeps_the_requirements_and_never_uses_more_positions():
    """docs/design/levels_split_casing.md, 7.3.1: the span term has a lower priority than a stack or an order wish, so nothing more is given up; the positions are never more than
    without it; stage 0 is still a flow; the option is part of the stored parameters; the slack stages work with it."""
    import warnings as _w

    import numpy as np
    from shapely.geometry import LineString as LS

    cols = ("casing_start", "casing_level", "casing_end", "fill_level")
    for seed in range(4):
        r = np.random.default_rng(seed)
        pts = r.random((60, 2)) * 0.004 + [18.0, 59.3]
        g = gpd.GeoDataFrame({"highway": r.choice(["primary", "residential", "service", "secondary"], 60), "layer": r.choice([None, "1", "-1", "2"], 60, p=[.6, .15, .15, .1])},
                             geometry=[LS([pts[i], pts[(i * 7 + 3) % 60]]) for i in range(60)], crs=4326)
        a, b = compute_levels(g, order="class", min_positions=False), compute_levels(g, order="class")        # the option is on by default
        assert len({v for c in cols for v in b[c]}) <= len({v for c in cols for v in a[c]})
        assert b.attrs["levels_info"]["solver"] == "flow" and not b.attrs["levels_given_up"]
        assert b.attrs["levels_info"]["order_violations"] == a.attrs["levels_info"]["order_violations"] == 0
    assert b.attrs["levels_params"]["min_positions"] is True and a.attrs["levels_params"]["min_positions"] is None
    assert compute_levels(g, method="tags").attrs["levels_params"]["min_positions"] is None            # it does not apply to the tags method
    d = 0.001
    rows = [LS([(18 - 2 * d, 59), (18 + 2 * d, 59)]), LS([(18, 58.998), (18, 59.002)]),
            LS([(18 - 2 * d, 58.998), (18 + 2 * d, 59.002)]), LS([(18 - 2 * d, 59.002), (18 + 2 * d, 58.998)])]       # four roads crossing at one point, as in test_compute_levels_lp_stages
    cross = gpd.GeoDataFrame({"highway": ["primary"] * 4, "band": [0, 1, 2, 3]}, geometry=rows, crs=4326)
    assert list(compute_levels(cross, band_col="band").fill_level) == [0, 1, 2, 3]
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        tight = compute_levels(cross, band_col="band", max_level=1)      # the range is too small: the slack stages, with the span term in stage 3
    assert tight.attrs["levels_info"]["solves"] == 4 and len(tight.attrs["levels_given_up"]) == 1


def test_stored_levels_remember_min_positions(tmp_path):
    """save_levels / load_levels with the option: the stored parameters say it, and a reader that does not expect it is refused."""
    duckdb = pytest.importorskip("duckdb")
    g = _tunnel_world(True).assign(edge_id=[1, 2, 3, 4])
    out = compute_levels(g, order="class")                                  # on by default
    con = duckdb.connect(str(tmp_path / "x.duckdb"))
    from roadstyle import load_levels, save_levels
    save_levels(con, out)
    assert len(load_levels(con, g, order="class")) == 4
    with pytest.raises(ValueError, match="min_positions"):
        load_levels(con, g, order="class", min_positions=False)


def _edge_world():
    """A tunnel (edge 12) under a crossing street (edge 13), joined to two ground roads (edges 11, 14): four edges with an edge_id column."""
    g = _tunnel_world(True)
    return g.assign(edge_id=[11, 12, 14, 13])           # the order of _tunnel_world: ground, tunnel, ground, crossing street


def _edge_features(ids, order=None, color=None):
    """One small square at each edge's start, as an overlay table with edge_id (and order, color)."""
    from shapely.geometry import Point
    g = gpd.GeoDataFrame({"edge_id": ids}, geometry=[Point(18.0 + 0.0001 * i, 59.30) for i, _ in enumerate(ids)], crs=4326)
    if order is not None:
        g["order"] = order
    if color is not None:
        g["color"] = color
    return g


def test_overlays_attached_to_edges_are_drawn_at_their_edge_fill_number(monkeypatch):
    """docs/design/edge_overlays.md: a feature is drawn at the fill number of its edge, after the fills of that position and before its arrows, by order, then by
    the order of the overlays; a feature of an edge at a higher fill number is in a later layer."""
    g = _edge_world()
    pts = _edge_features([12, 13, 11, 12], order=[1, 0, 0, 0])                  # two orders at the tunnel's position, one at the crossing street's, one on the ground road
    first = Overlay(pts, edge_col="edge_id", order_col="order", kind="circle", label="first")
    second = Overlay(_edge_features([12]), edge_col="edge_id", kind="circle", label="second")
    style = _style(render_edges(g, backend="web", overlays=[first, second]).html)
    ids = [l["id"] for l in style["layers"]]
    feats = {int(f["properties"]["edge_id"]): f["properties"] for f in style["sources"]["roads"]["data"]["features"]}
    fl = {e: feats[e]["__rs_fl"] for e in (11, 12, 13)}
    assert fl[12] < fl[13]                                                       # the crossing street is over the tunnel
    mine = [i for i in ids if i.startswith("ov0-circle-lv") or i.startswith("ov1-circle-lv")]
    expect = sorted({(fl[12], 0, 0), (fl[12], 1, 0), (fl[13], 0, 0), (fl[11], 0, 0), (fl[12], 0, 1)})          # (fill number, order, overlay): one layer for each
    got = [(int(i.split("-lv")[1].split("-o")[0]), int(i.split("-o")[-1]), int(i[2])) for i in mine]
    assert sorted(got) == expect and len(mine) == len(expect)
    assert [(a, b) for a, b, c in got] == sorted(((a, b) for a, b, c in got))   # in the stack: by fill number, then order
    for lid in mine:                                                             # after the fills of its position, before the arrows of its position
        p = int(lid.split("-lv")[1].split("-o")[0])
        fill = "roads-fill" if p == 0 else f"roads-fill-lv{p}"
        arrows = "roads-arrows" if p == 0 else f"roads-arrows-lv{p}"
        assert ids.index(fill) < ids.index(lid) and (arrows not in ids or ids.index(lid) < ids.index(arrows))
    same = [i for i in mine if f"-lv{fl[12]}-o0" in i]                          # the same fill number and order: the overlay that comes first in the list is first
    assert same == [f"ov0-circle-lv{fl[12]}-o0", f"ov1-circle-lv{fl[12]}-o0"]
    lay = {l["id"]: l for l in style["layers"]}
    one = lay[f"ov0-circle-lv{fl[13]}-o0"]
    assert one["filter"] == ["all", ["==", ["get", "__rs_fl"], fl[13]], ["==", ["get", "__rs_ord"], 0]]
    baked = {(f["properties"]["edge_id"], f["properties"]["__rs_fl"], f["properties"]["__rs_ord"]) for f in style["sources"]["ov0"]["data"]["features"]}
    assert baked == {(12, fl[12], 1), (13, fl[13], 0), (11, fl[11], 0), (12, fl[12], 0)}
    plain = _style(render_edges(g, backend="web", overlays=[Overlay(pts, kind="circle")]).html)             # without edge_col: as before, over all roads
    pids = [l["id"] for l in plain["layers"]]
    assert "ov0-circle" in pids and pids.index("ov0-circle") > max(n for n, i in enumerate(pids) if i.startswith("roads-fill")) and not [i for i in pids if i.startswith("ov0-circle-lv")]

def test_edge_overlay_errors_and_colours():
    """An edge id that is not among the roads is an error that says how many and which; so is a roads table without its id column; color_col is read from the property."""
    g = _edge_world()
    with pytest.raises(ValueError, match=r"2 feature\(s\).*not an edge"):
        render_edges(g, backend="web", overlays=[Overlay(_edge_features([12, 99, 98]), edge_col="edge_id", kind="circle")])
    with pytest.raises(ValueError, match="edge_id_col"):
        render_edges(g.drop(columns="edge_id"), backend="web", overlays=[Overlay(_edge_features([12]), edge_col="edge_id", kind="circle")])
    st = _style(render_edges(g, backend="web", overlays=[Overlay(_edge_features([12, 13], color=["#ff0000", None]), edge_col="edge_id", color_col="color", kind="circle")]).html)
    circle = next(l for l in st["layers"] if l["id"].startswith("ov0-circle-lv"))
    assert '["coalesce", ["get", "color"]' in json.dumps(circle["paint"]["circle-color"])
    other = render_edges(g.assign(my_id=g.edge_id), backend="web", edge_id_col="my_id",
                         overlays=[Overlay(_edge_features([12]).rename(columns={"edge_id": "e"}), edge_col="e", kind="circle")])      # the roads' id column is a setting
    assert "ov0-circle-lv" in other.html


def test_arrows_and_street_names_belong_to_an_edge(monkeypatch):
    """docs/design/edge_overlays.md: every slot (the piece of road that carries an arrow or a name) carries the edge under its middle point (__rs_road, and __rs_road2 for the
    twin of a two-way street) and the fill number of that edge."""
    a, b, c = (18.000, 59.300), (18.003, 59.300), (18.003, 59.303)
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "name": ["Main", "Main", "Side"], "oneway": [False, False, True]},
                         geometry=[LineString([a, b]), LineString([b, a]), LineString([b, c])], crs=4326)       # a two-way street (two twins) and a one-way street
    style = _style(render_edges(g, backend="web", arrows=True, labels=True).html)
    roads = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    slots = [f["properties"] for f in style["sources"]["slots"]["data"]["features"]]
    assert slots and all("__rs_road" in s for s in slots)
    for s in slots:
        assert 0 <= s["__rs_road"] < len(roads) and s.get("fl", 0) == roads[s["__rs_road"]]["__rs_fl"]
    two_way = [s for s in slots if s["name"] == "Main"]
    assert two_way and all({s["__rs_road"], s["__rs_road2"]} == {0, 1} for s in two_way)       # the pair: its two twins
    one_way = [s for s in slots if s["name"] == "Side"]
    assert one_way and all(s["__rs_road"] == 2 and "__rs_road2" not in s for s in one_way)


def test_road_fill_false_draws_the_casing_but_not_the_fill():
    """docs/design/edge_overlays.md, three ways to use it: road_fill=False keeps the casing layers and makes the fill layers (and the end caps' fills) invisible; the default is unchanged."""
    g = _edge_world()
    on = _style(render_edges(g, backend="web").html)["layers"]
    off = _style(render_edges(g, backend="web", road_fill=False).html)["layers"]
    assert [lyr["id"] for lyr in on] == [lyr["id"] for lyr in off]                     # the same layers: the fills stay for clicks and hovers
    for a, b in zip(on, off, strict=True):
        if a["id"].startswith("roads-fill"):
            assert b["paint"]["line-opacity"] == 0 and a["paint"].get("line-opacity") != 0
        elif a["id"].startswith("roads-ends-fill"):
            assert b["paint"]["circle-opacity"] == 0
        else:
            assert a == b                                                               # the casings, arrows, names: untouched
    with_items = _style(render_edges(g, backend="web", road_fill=False, overlays=[Overlay(_edge_features([12]), edge_col="edge_id", kind="circle")]).html)
    assert any(lyr["id"].startswith("ov0-circle-lv") for lyr in with_items["layers"])


_STYLES = {"config": {"overlays": {"styles": {
    "divider": {"kind": "line", "color": "#ffffff", "width_m": 0.12, "min_zoom": 16},
    "dashed": {"kind": "line", "color": "#eeeeee", "width_m": 0.12, "dash": [3, 3], "min_zoom": 16, "max_zoom": 21},
    "street_name": {"kind": "text", "text_col": "label", "text_size": 13, "text_color": "#444444", "text_halo": "#ffffff", "min_zoom": 14}}}}}


def _line_overlay_data():
    from shapely.geometry import LineString as LS
    return gpd.GeoDataFrame({"edge_id": [11, 12], "label": ["Main", None]}, geometry=[LS([(18.0, 59.3), (18.002, 59.3)]), LS([(18.002, 59.3), (18.004, 59.3)])], crs=4326)


def test_overlay_styles_come_from_the_settings_and_an_argument_wins():
    """docs/design/overlay_styles.md: a style named in the settings fills the fields the overlay does not give; an argument of the Overlay wins; an unknown style or field is an error."""
    g = _edge_world()
    st = _style(render_edges(g, backend="web", settings=_STYLES, overlays=[Overlay(_line_overlay_data(), style="divider", label="d"), Overlay(_line_overlay_data(), style="divider", color="#ff0000", label="e")]).html)
    lay = {lyr["id"]: lyr for lyr in st["layers"]}
    assert lay["ov0-line"]["paint"]["line-color"][-1] == "#ffffff" and lay["ov1-line"]["paint"]["line-color"][-1] == "#ff0000"        # the argument wins (the last branch of the hover / select case)
    assert lay["ov0-line"]["minzoom"] == 16.0
    with pytest.raises(ValueError, match=r"not in the settings.*divider"):
        render_edges(g, backend="web", settings=_STYLES, overlays=[Overlay(_line_overlay_data(), style="nope")])
    with pytest.raises(ValueError, match="not in the settings"):
        render_edges(g, backend="web", overlays=[Overlay(_line_overlay_data(), style="divider")])                        # roadstyle ships no styles
    bad = {"config": {"overlays": {"styles": {"x": {"colour": "#fff"}}}}}
    with pytest.raises(ValueError, match="unknown field"):
        render_edges(g, backend="web", settings=bad, overlays=[Overlay(_line_overlay_data(), style="x")])


def test_overlay_metre_width_dash_zoom_range_and_text():
    """width_m is exact in metres from min_zoom (the width doubles with each zoom); dash and the zoom range are on the layer; kind text is a symbol layer along the line that reads text_col."""
    st = _style(render_edges(_edge_world(), backend="web", settings=_STYLES, overlays=[
        Overlay(_line_overlay_data(), style="divider", label="a"), Overlay(_line_overlay_data(), style="dashed", label="b"),
        Overlay(_line_overlay_data(), style="street_name", label="c")]).html)
    lay = {lyr["id"]: lyr for lyr in st["layers"]}
    w = lay["ov0-line"]["paint"]["line-width"]
    assert w[:3] == ["interpolate", ["exponential", 2], ["zoom"]] and w[3] == 16.0 and w[5] == 22.0 and w[4][1] == ["get", "__rs_wm"]
    px = lambda z: 512 * 2 ** z / 40075016.686                                    # noqa: E731
    assert abs(w[4][2] - px(16)) < 1e-6 and abs(w[6][2] - px(22)) < 1e-6 and abs(w[6][2] / w[4][2] - 64) < 1e-3          # exact: 64 times wider after 6 zooms
    feats = st["sources"]["ov0"]["data"]["features"]
    assert abs(feats[0]["properties"]["__rs_wm"] - 0.12 / math.cos(math.radians(59.3))) < 1e-9
    dashed = lay["ov1-line"]
    assert dashed["paint"]["line-dasharray"] == [3.0, 3.0] and dashed["layout"]["line-cap"] == "butt" and dashed["minzoom"] == 16.0 and dashed["maxzoom"] == 21.0
    text = lay["ov2-text"]
    assert text["type"] == "symbol" and text["layout"]["text-field"] == ["get", "label"] and text["layout"]["symbol-placement"] == "line-center"
    assert text["paint"]["text-halo-color"] == "#ffffff" and text["layout"]["text-size"] == 13 and st["glyphs"]
    with pytest.raises(ValueError, match="text_col"):
        render_edges(_edge_world(), backend="web", overlays=[Overlay(_line_overlay_data(), kind="text")])


def test_overlay_styles_work_for_overlays_attached_to_edges():
    """Attached to edges, each style is drawn at the position of its edge: a dashed line, a text and a metre-wide line each get their layers per (fill number, order)."""
    g = _edge_world()
    data = _line_overlay_data().assign(order=[1, 3])
    st = _style(render_edges(g, backend="web", road_fill=False, settings=_STYLES, overlays=[
        Overlay(data, edge_col="edge_id", order_col="order", style="dashed", label="a"), Overlay(data, edge_col="edge_id", order_col="order", style="street_name", label="b")]).html)
    ids = [lyr["id"] for lyr in st["layers"]]
    assert any(i.startswith("ov0-line-lv") and "-o1" in i for i in ids) and any(i.startswith("ov1-text-lv") and "-o3" in i for i in ids)
    one = next(lyr for lyr in st["layers"] if lyr["id"].startswith("ov0-line-lv"))
    assert one["paint"]["line-dasharray"] == [3.0, 3.0] and one["filter"][0] == "all"


def test_a_theme_can_be_a_file_and_an_unreadable_settings_file_is_an_error(tmp_path):
    """settings= is a dict or the address of a JSON or YAML file with the same shape; a file that is missing or cannot be read is an error that names it, not skipped, and the settings stay as they were."""
    yaml = pytest.importorskip("yaml")
    path = tmp_path / "theme.json"
    path.write_text(json.dumps(_STYLES))
    ypath = tmp_path / "theme.yaml"
    ypath.write_text(yaml.safe_dump(_STYLES))
    for f in (path, ypath):
        st = _style(render_edges(_edge_world(), backend="web", settings=str(f), overlays=[Overlay(_line_overlay_data(), style="divider")]).html)
        assert any(lyr["id"] == "ov0-line" and lyr.get("minzoom") == 16.0 for lyr in st["layers"])
    with pytest.raises(ValueError, match="settings file"):
        render_edges(_edge_world(), backend="web", settings=str(tmp_path / "missing.json"))
    for name, text in (("bad.json", "{not json"), ("bad.yaml", "- a\n- list"), ("worse.yml", "a: [unclosed")):
        bad = tmp_path / name
        bad.write_text(text)
        with pytest.raises(ValueError, match=name):
            render_edges(_edge_world(), backend="web", settings=str(bad))
    render_edges(_edge_world(), backend="web")                                  # and the failed calls did not leave the settings changed


def test_the_numpy_cutter_is_shapelys_substring():
    """_part (the casing pieces and the annotation slots) cuts a polyline exactly as shapely.ops.substring does, without building geometries."""
    import numpy as np
    from shapely.geometry import LineString as LS
    from shapely.ops import substring

    from roadstyle.render_web import _cum_lengths, _part
    rng = np.random.default_rng(1)
    for _ in range(300):
        xy = np.cumsum(rng.normal(size=(int(rng.integers(2, 9)), 2)) * 5, axis=0)
        cum = _cum_lengths(xy)
        a = float(rng.uniform(0, cum[-1] * 0.7))
        b = float(rng.uniform(a + 1e-3, cum[-1]))
        assert np.allclose(_part(xy, cum, a, b), np.asarray(substring(LS(xy), a, b).coords), atol=1e-9)


def test_one_arrow_per_one_way_road_in_the_window(tmp_path):
    """docs/design/one_arrow_per_road.md (Kaveh 2026-10-06): a one-way road in the window has one arrow, in its visible part; the arrow stays
    where it is while it is in the window (a small pan keeps it), and a road whose arrow left the window gets one again. None below zoom 15."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "arrows.html"
    pts = [(18.0 + i * 0.001, 59.3) for i in range(41)]                       # one straight one-way street, about 2.3 km, many slots
    g = gpd.GeoDataFrame({"highway": ["primary"], "name": ["Long St"], "oneway": [True]}, geometry=[LineString(pts)], crs=4326)
    render_edges(g, backend="web", basemap="blank").save(path)
    arrows = "map.getSource('arrows')._data.features.map(f => f.geometry.coordinates)"
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded()", timeout=30_000)
        def at(lon, zoom):
            page.evaluate(f"map.jumpTo({{center: [{lon}, 59.3], zoom: {zoom}}})")
            page.wait_for_function("map.loaded()", timeout=30_000)
            page.wait_for_timeout(300)
            return page.evaluate(arrows)
        far = at(18.02, 14)
        first = at(18.02, 16)
        nudged = at(18.0203, 16)
        moved = at(18.035, 16)
        browser.close()
    assert errors == [] and far == []
    assert len(first) == 1 and abs(first[0][0] - 18.02) < 0.004                 # one arrow, in the middle of what is seen
    assert nudged == first                                                        # a small pan keeps it
    assert len(moved) == 1 and moved != first                                     # its old place left the window: a new one


def test_arrows_are_thinned(tmp_path):
    """docs/design/one_arrow_per_road.md, thinning (Kaveh 2026-10-06): below zoom 17 only the main classes get an arrow; arrows stay 150 px
    apart (two parallel one-way roads a few metres apart show one)."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "thin.html"
    row = lambda y: [(18.0 + i * 0.001, y) for i in range(41)]                 # noqa: E731
    g = gpd.GeoDataFrame({"highway": ["residential", "primary", "primary"], "name": ["Side", "Main N", "Main S"], "oneway": [True] * 3},
                         geometry=[LineString(row(59.31)), LineString(row(59.3)), LineString(row(59.30005))], crs=4326)
    render_edges(g, backend="web", basemap="blank").save(path)
    names = "map.getSource('arrows')._data.features.map(f => f.properties.name).sort()"
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded()", timeout=30_000)
        def at(lat, zoom):
            page.evaluate(f"map.jumpTo({{center: [18.02, {lat}], zoom: {zoom}}})")
            page.wait_for_function("map.loaded()", timeout=30_000)
            page.wait_for_timeout(300)
            return page.evaluate(names)
        side16, side17, mains16 = at(59.31, 16), at(59.31, 17), at(59.3, 16)
        browser.close()
    assert side16 == [] and side17 == ["Side"]                                  # residential: from zoom 17
    assert len(mains16) == 1                                                       # 5 m apart: one arrow

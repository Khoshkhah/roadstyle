"""Web (MapLibre) backend: client-side recolouring via color_options + the recolour hooks."""
import copy
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
    wm = render_edges(_edges(), backend="web", arrows=True, labels=True, simple=False)
    style = _style(wm.html)
    ids = [layer["id"] for layer in style["layers"]]
    assert "roads-labels" in ids and "roads-arrows" in ids
    slots = style["sources"]["slots"]["data"]["features"]
    assert slots and all({"slot", "name", "highway", "oneway"} <= set(f["properties"])
                         for f in slots)
    lab = next(l for l in style["layers"] if l["id"] == "roads-labels")
    arr = next(l for l in style["layers"] if l["id"] == "roads-arrows")
    assert json.dumps(["==", ["%", ["get", "slot"], 2], 0]) in json.dumps(lab["filter"])     # names: even slots
    # arrows: one per one-way road in the window (docs/design/arrows_and_names.md): points the page puts in the "arrows" source,
    # rotated along the road; every slot piece names its chain
    assert json.dumps(["==", ["get", "oneway"], 1]) in json.dumps(arr["filter"])
    assert arr["source"] == "arrows" and arr["layout"]["symbol-placement"] == "point" and arr["layout"]["icon-rotate"] == ["get", "b"]
    assert style["sources"]["arrows"]["data"]["features"] == [] and all("chain" in f["properties"] for f in style["sources"]["slots"]["data"]["features"])
    # one arrow layer per grade tier, each right beside its road tier — a bridge must cover
    # the arrows of the road it crosses, not have them float above everything
    assert ids.index("roads-arrows") == ids.index("roads-fill") + 1
    assert ids.index("roads-arrows-lv1") == ids.index("roads-fill-lv1") + 1     # one arrow layer per position, after the fill layers it has
    assert json.dumps(["to-boolean", ["get", "name"]]) in json.dumps(lab["filter"])          # unnamed -> slot stays empty
    assert lab["layout"]["symbol-placement"] == "line-center"
    # The standing default: label text matches the oneway-arrow grey, and NO halo
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
    html = render(g, compress=True, simple=False).html
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
    from roadstyle.render_web import _seam_filter, render
    seam = json.dumps(_seam_filter())   # only the casing seams (round from z17) and laps (flat below z17)
    for f in _road_filters(render(_many_edges(20)).html).values():
        assert "zoom" not in json.dumps(f).replace(seam, "")


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
    style = _style(render_edges(_edges(), backend="web", simple=False).html)
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
    """Bridge decks keep a solid dark casing (config.bridge_casing_color, slate #64748b by default) even
    though the regular road casing defaults to light grey."""
    style = _style(render_edges(_edges().assign(bridge=["yes", None, None]), backend="web", simple=False).html)
    bc = next(l for l in style["layers"] if l["id"].endswith("-bridge"))
    assert bc["paint"]["line-color"] == "#64748b"


def test_webmap_notebook_repr_is_slim_but_saved_file_is_offline():
    """The inline notebook preview swaps MapLibre for CDN tags (output-size limits in notebook
    frontends were silently blanking the map); .html / .save keep the vendored copy inlined."""
    wm = render_edges(_edges(), backend="web")
    r = wm._repr_html_()
    assert "cdn.jsdelivr.net/npm/maplibre-gl" in r
    assert len(r) < len(wm.html)                      # the 800 KB vendored blob stays out
    assert "__MAPLIBRE_JS__" not in wm.html and "cdn.jsdelivr" not in wm.html


def test_notebook_cdn_maplibre_is_the_vendored_version():
    """The preview's CDN MapLibre is the vendored one: simple mode needs >= 5.22, and below 5.20
    a srcdoc iframe (origin "null") never loads a source."""
    import re
    from roadstyle.render_web import _MAPLIBRE_CDN, _asset
    vendored = re.search(r"maplibre-gl-js/blob/v([\d.]+)/", _asset("maplibre-gl.js")[:400]).group(1)
    assert f"maplibre-gl@{vendored}/" in _MAPLIBRE_CDN


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
    td = _style(render_edges(g, backend="web", view_3d=True, simple=False).html)
    ids = [l["id"] for l in td["layers"]]
    assert "roads-bridge-decks" in ids
    # LOD swap at flat_below: flat lines capped there, deck starts there; bridge highlight split
    deck3d = next(l for l in td["layers"] if l["id"] == "roads-bridge-decks")
    assert deck3d["minzoom"] == 16.0
    # the flat bridge line (its casing layer, and the bridge edges in the position layers) ends where the deck starts
    assert next(l for l in td["layers"] if l["id"].endswith("-bridge") and l["id"].startswith("roads-casing"))["maxzoom"] == 16.0
    assert json.dumps(["<", ["zoom"], 16.0]) in json.dumps(next(l for l in td["layers"] if l["id"] == "roads-fill")["filter"])
    assert "roads-highlight-bridge" not in ids          # a bridge is drawn (and highlighted) by the layers of its positions
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
    flat = _style(render_edges(g, backend="web", simple=False).html)
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
    assert 0 in slices[0]["properties"]["__rs_edges"]  # edge 0 is the bridge
    # the dark casing ring: slab features + a casing-colour extrusion layer under the body
    assert any("__rs_casing_slab" in f["properties"] for f in feats)
    cas = next(l for l in style["layers"] if l["id"] == "roads-deck-casing")
    assert cas["paint"]["fill-extrusion-color"] == "#64748b"


def test_dashed_path_classes_get_dash_layers():
    """footway/path/steps/cycleway carry a palette dash (__rs_dash); the web backend renders
    them as dashed sibling fill layers (butt caps — round would seal the gaps) and drops them
    from the solid fill + casing layers so the gaps show the ground."""
    g = gpd.GeoDataFrame(
        {"highway": ["footway", "cycleway", "residential"]},
        geometry=[LineString([(18.0, 59.30), (18.01, 59.305)]),
                  LineString([(18.01, 59.305), (18.02, 59.31)]),
                  LineString([(18.02, 59.31), (18.03, 59.315)])], crs=4326)
    style = _style(render_edges(g, backend="web", simple=False).html)
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
    owners = {s["properties"]["__rs_edges"][0] for s in slices}
    assert owners == {0, 1}                    # both directions present, separately owned
    assert 'key:"e"+e[0]' in html                     # deck hover keys on the edge, not the chain


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


def test_tunnel_casing_is_the_dash_layer_alone():
    """docs/design/tunnel_look.md, as v2: a tunnel's casing is drawn by the dash sublayer only, slate dashes (#94a3b8, 1:1) with empty gaps;
    the other casing layers leave the tunnel out (transparent), so the gaps are empty. A street's casing is unchanged."""
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "tunnel": ["yes", None]},
                         geometry=[LineString([(18.0, 59.30), (18.01, 59.30)]),
                                   LineString([(18.01, 59.30), (18.02, 59.30)])], crs=4326)
    style = _style(render_edges(g, backend="web", palette="highsat", simple=False).html)          # highsat: primary casing #bcbcbc
    lay = {l["id"]: l for l in style["layers"]}
    ids = list(lay)
    assert ids.index("roads-casing") < ids.index("roads-casing-dash") < ids.index("roads-fill")
    assert lay["roads-casing-dash"]["paint"]["line-color"] == "#94a3b8" and lay["roads-casing-dash"]["paint"]["line-dasharray"] == [1, 1]
    from roadstyle.render_web import _plus_px

    assert _plus_px(["interpolate", ["linear"], ["zoom"], 12, 1, 18, ["get", "w"]], 3) == ["interpolate", ["linear"], ["zoom"], 12, ["+", 1, 3], 18, ["+", ["get", "w"], 3]]
    assert "__rs_tunnel" in json.dumps(lay["roads-casing-dash"]["filter"])      # only the tunnel look
    tun, street = (f["properties"] for f in style["sources"]["roads"]["data"]["features"])
    assert _eval(lay["roads-casing"]["paint"]["line-color"], tun) == "rgba(0,0,0,0)"
    assert _eval(lay["roads-casing"]["paint"]["line-color"], street) == street["__rs_casing"]
    for stop in (4, 6):                                       # the casing layer (the gap colour) is as wide as the dash layer for a tunnel only
        dash_w, case_w = lay["roads-casing-dash"]["paint"]["line-width"][stop], lay["roads-casing"]["paint"]["line-width"][stop]
        assert case_w == ["case", ["to-boolean", ["get", "__rs_tunnel"]], dash_w, dash_w[1]]      # dash: ["+", w, 3]


def test_rscolor_raises_painted_roads_within_their_level():
    """rsColor lifts the painted roads to the top of their level (line-sort-key +500, levels are
    1000 apart): over a street they cross, still under a bridge above them."""
    html = render_edges(_edges(), backend="web").html
    assert "function _applySort()" in html and '["case",["any",_has(["id"],all),_has(["get","__rs_edge2"],all)],500,0]' in html and "function _has(expr, ids)" in html
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
    if op == "any":
        return any(_eval(x, p) for x in a)
    if op == "zoom":
        return p.get("$zoom", 22)                                   # a street zoom unless the test says otherwise
    x, y = _eval(a[0], p), _eval(a[1], p)
    return {"==": x == y, "<": x < y if op == "<" else None, ">": x > y if op == ">" else None, ">=": x >= y if op == ">=" else None}[op]




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
    assert '[">=",["coalesce",["get",lvl],0],0]' in html                     # lvl: the piece's level, or an attached item's baked __rs_lvl
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
    style = _style(render_edges(_pairs(), backend="web", simple=False, settings={"config": {"twin_casing": "each"}}).html)
    pts = style["sources"]["ends"]["data"]["features"]
    # only the plain, solid two-way street: two ends, both twins' ids; no one-way, bridge, tunnel,
    # or dashed pair
    assert len(pts) == 2
    assert {(p["properties"]["__rs_edge"], p["properties"]["__rs_edge2"]) for p in pts} == {(0, 1)}
    assert {tuple(p["geometry"]["coordinates"]) for p in pts} == {(18.0, 59.3), (18.0, 59.31)}
    assert pts[0]["properties"]["__rs_fill"] and pts[0]["properties"]["highway"] == "residential"




def _roads_of(html):
    return [f["properties"] for f in _style(html)["sources"]["roads"]["data"]["features"]]


def test_two_way_footway_is_one_full_width_line_and_a_street_keeps_its_lanes():
    """single_line_classes: a reverse pair of a footway is drawn once (the later edge draws nothing), full width (no lane offset), no arrows;
    both edges name each other (the popup shows both directions); a residential pair still fans into lanes."""
    for simple in (True, False):
        html = render_edges(_pairs(), backend="web", simple=simple).html
        ps = _roads_of(html)
        foot, street = ps[7:9], ps[0:2]
        assert [p["__rs_twoway"] for p in foot] == [False, False] and [p["__rs_oneway"] for p in foot] == [False, False]
        assert [p.get("__rs_dup") for p in foot] == [None, True] and (foot[0]["__rs_edge2"], foot[1]["__rs_edge2"]) == (8, 7)
        assert all(p["__rs_twoway"] and "__rs_dup" not in p for p in street)
        style = _style(html)
        if simple:
            pieces = style["sources"]["simple"]["data"]["features"]
            assert {f["properties"]["__rs_edge"] for f in pieces if f["properties"]["highway"] == "footway"} == {7}
        else:
            nd = ["!", ["to-boolean", ["get", "__rs_dup"]]]
            assert all(l["filter"] == nd or l["filter"][-1] == nd for l in style["layers"] if l.get("source") in ("roads", "casings", "halves"))
        assert "_both(" in html and "function _twinDetail" in html


def test_single_line_classes_is_a_setting():
    off = _roads_of(render_edges(_pairs(), backend="web", settings={"config": {"single_line_classes": []}}).html)
    assert all(p["__rs_twoway"] for p in off[7:9]) and not any("__rs_dup" in p for p in off)
    street = _roads_of(render_edges(_pairs(), backend="web", settings={"config": {"single_line_classes": ["residential"]}}).html)
    assert street[1].get("__rs_dup") and not street[0]["__rs_twoway"] and street[7]["__rs_twoway"]


def _twin(rows):
    """A two-way primary (two reverse edges) and a one-way street: rows of (edge_id, start, end, casing start / main / end, fill, cap_start,
    cap_end); the points are a = (18, 59.30), b = (18, 59.301)."""
    pt = {"a": (18.0, 59.30), "b": (18.0, 59.301), "c": (18.001, 59.30), "d": (18.001, 59.301)}
    cols = ["edge_id", "s", "e", "cs", "cm", "ce", "fl", "cap_s", "cap_e"]
    t = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
    return gpd.GeoDataFrame({"highway": "primary", **{c: t[c] for c in cols if c not in ("s", "e")}},
                            geometry=[LineString([pt[r[1]], pt[r[2]]]) for r in rows], crs=4326)


_TWIN_KW = dict(backend="web", casing_start_col="cs", casing_level_col="cm", casing_end_col="ce", fill_level_col="fl",
                cap_start_col="cap_s", cap_end_col="cap_e", head_m=5.0)


def _num(e, p):
    """A width or offset stop on a feature's properties (+, * and what render_web._ev reads)."""
    from roadstyle.render_web import _ev
    if isinstance(e, list) and e and e[0] in ("+", "*"):
        a, b = (_num(x, p) for x in e[1:])
        return a + b if e[0] == "+" else a * b
    if isinstance(e, list) and e and e[0] in ("case", "match"):
        if e[0] == "case":
            for c, o in zip(e[1:-1:2], e[2:-1:2], strict=True):
                if _ev(c, p):
                    return _num(o, p)
            return _num(e[-1], p)
        v = _ev(e[1], p)
        for lab, o in zip(e[2:-1:2], e[3:-1:2], strict=True):
            if v == lab or (isinstance(lab, list) and v in lab):
                return _num(o, p)
        return _num(e[-1], p)
    return _ev(e, p)


def test_a_two_way_pair_has_one_casing_and_a_fill_per_direction():
    """twin_casing "one" (the default, 2026-10-08): a two-way road given as two directed edges has ONE casing, the first edge's pieces,
    unshifted and as wide as both directions together (a direction's casing + twice its offset: the outer edge of the two lanes, as the
    end caps' radius); the second edge has no casing piece; each direction keeps its own fill, shifted, as before. Simple mode, the bridge
    shadow and the tunnel's two casing pieces too, and the full look; no end blobs (each piece has its own cap)."""
    from roadstyle.render_web import _end_radius_expr, _ZSTOPS
    g = _twin([(1, "a", "b", 0, 0, 0, 0, None, None), (2, "b", "a", 0, 0, 0, 0, None, None), (3, "c", "d", 0, 0, 0, 0, None, None)])
    for extra in ({}, {"bridge": "yes"}, {"tunnel": "yes"}):
        style = _style(render_edges(g.assign(**extra), **_TWIN_KW).html)
        feats = [f["properties"] for f in style["sources"]["simple"]["data"]["features"]]
        casing = [(p["__rs_edge"], p["__rs_k"], p.get("__rs_pair"), p.get("__rs_edge2")) for p in feats if p["__rs_k"] != 1]
        assert {c[0] for c in casing} == {0, 2} and all(c[2:] == (True, 1) for c in casing if c[0] == 0)
        assert all(c[2:] == (None, None) for c in casing if c[0] == 2)                    # the one-way street: as before
        ks = {c[1] for c in casing if c[0] == 0}
        assert ks == ({0, 2} if extra.get("bridge") else {3, 4} if extra.get("tunnel") else {0})       # its shadow, its tunnel pieces
        fills = [p for p in feats if p["__rs_k"] == 1]
        assert sorted(p["__rs_edge"] for p in fills) == [0, 1, 2] and not any(p.get("__rs_pair") for p in fills)
        lyr = next(l for l in style["layers"] if l["id"] == "roads-simple")
        z = _ZSTOPS.index(18)
        width, offset = lyr["paint"]["line-width"], lyr["paint"]["line-offset"]
        pair = next(p for p in feats if p.get("__rs_pair") and p["__rs_k"] in (0, 3))
        fill = next(p for p in fills if p["__rs_edge"] == 0)
        lane = {**pair, "__rs_pair": None}                                                # the same piece as one direction's casing
        assert _num(offset[4 + 2 * z], pair) == 0 and _num(offset[4 + 2 * z], fill) > 0
        assert _num(width[4 + 2 * z], pair) == pytest.approx(_num(width[4 + 2 * z], lane) + 2 * _num(offset[4 + 2 * z], fill))
        if not extra:
            outer = _num(_end_radius_expr("highway", casing=True)[4 + 2 * z], pair)       # the pair's outer half-width at zoom 18
            assert _num(width[4 + 2 * z], pair) == pytest.approx(2 * outer, abs=0.01)
    full = _style(render_edges(g, simple=False, **_TWIN_KW).html)
    pieces = [f["properties"] for f in full["sources"]["casings"]["data"]["features"]]
    assert sorted((p["__rs_edge"], p.get("__rs_pair")) for p in pieces) == [(0, True), (2, None)] and "ends" not in full["sources"]
    cas = next(l for l in full["layers"] if l["id"] == "roads-casing")
    assert cas["source"] == "casings" and "__rs_pair" in json.dumps(cas["paint"]["line-width"]) and "__rs_pair" in json.dumps(cas["paint"]["line-offset"])


def test_a_two_way_pairs_casing_takes_each_end_its_own_cap():
    """The one casing is cut from the first edge of the pair, with its own heads and caps; the second edge runs the other way, so its start
    is the first one's end. A flat start at a and a square end at b come out at a and at b whichever direction comes first; each fill keeps
    its own caps."""
    a, b = (18.0, 59.30), (18.0, 59.301)
    along = (1, "a", "b", 0, 0, 0, 0, "yes", "square")
    back = (2, "b", "a", 0, 0, 0, 0, "square", "yes")
    for rows in ([along, back], [back, along]):
        feats = _style(render_edges(_twin(rows), **_TWIN_KW).html)["sources"]["simple"]["data"]["features"]
        heads = [f for f in feats if f["properties"]["__rs_k"] == 0 and not f["properties"].get("__rs_main") and not f["properties"].get("__rs_seam")]
        assert {f["properties"]["__rs_edge"] for f in heads} == {0}
        at = {}
        for f in heads:
            c = [tuple(x) for x in f["geometry"]["coordinates"]]
            at[a if a in (c[0], c[-1]) else b] = f["properties"].get("__rs_cap")
        assert at == {a: True, b: "square"}
        fills = [f for f in feats if f["properties"]["__rs_k"] == 1]               # two different ends: each fill in two halves, its own caps
        ends = sorted((f["properties"]["__rs_edge"], a in [tuple(x) for x in f["geometry"]["coordinates"]], f["properties"].get("__rs_cap")) for f in fills)
        assert ends == [(0, False, "square"), (0, True, True), (1, False, "square"), (1, True, True)]


def _twin_caps(g, simple=True, **kw):
    """(casing cap at a, at b, fill caps by (edge, point)) of a drawn pair: a = (18, 59.30), b = (18, 59.301); a piece's cap counts at each of
    its end points that are a or b (a whole piece: both ends, a half: its own). The full look reads the casing pieces and the halves."""
    a, b = (18.0, 59.30), (18.0, 59.301)
    style = _style(render_edges(g, **{**_TWIN_KW, "simple": simple, **kw}).html)
    src = style["sources"]["simple" if simple else "casings"]["data"]["features"]
    hv = style["sources"]["halves"]["data"]["features"] if "halves" in style["sources"] else []
    cas, fills = {}, {}
    for f in src + hv:
        p, c = f["properties"], [tuple(x) for x in f["geometry"]["coordinates"]]
        into = fills if p.get("__rs_k") == 1 or f in hv else cas
        if into is cas and (p.get("__rs_edge") != 0 or p.get("__rs_main") or p.get("__rs_seam")):
            continue
        for pt in {c[0], c[-1]} & {a, b}:
            into[(p["__rs_edge"], pt) if into is fills else pt] = p.get("__rs_cap")
    return cas, fills


def test_a_two_way_pairs_dead_end_is_square_without_given_caps():
    """twin_casing "one": a pair's dead end gets "square" (casing and both fills) when the data gives that end no cap; a junction end (another
    edge's end point there) stays round; a line crossing mid-line is no junction; a given cap wins; "each" and a one-way road are unchanged."""
    a, b = (18.0, 59.30), (18.0, 59.301)
    pair = [(1, "a", "b", 0, 0, 0, 0, None, None), (2, "b", "a", 0, 0, 0, 0, None, None)]
    for simple in (True, False):
        cas, fills = _twin_caps(_twin(pair + [(3, "c", "d", 0, 0, 0, 0, None, None)]), simple)     # c-d runs by, touching nothing
        assert cas == {a: "square", b: "square"}
        # a one-way edge ending at b: b is a junction, a is still a dead end
        g = _twin(pair + [(3, "c", "b", 0, 0, 0, 0, None, None)])
        cas, fills = _twin_caps(g, simple)
        assert cas == {a: "square", b: None}
        assert {k: v for k, v in fills.items() if k[0] in (0, 1)} == {(0, a): "square", (0, b): None, (1, a): "square", (1, b): None}
        # a given cap wins (round included); the other end is still automatic
        cas, fills = _twin_caps(_twin([(1, "a", "b", 0, 0, 0, 0, "round", None), (2, "b", "a", 0, 0, 0, 0, None, "round")]), simple)
        assert cas == {a: None, b: "square"}
        assert fills[(0, a)] is None and fills[(1, a)] is None and fills[(0, b)] == "square" and fills[(1, b)] == "square"
    # a line crossing mid-line (a point inside it, not an end point at b) is no junction
    x = _twin(pair)
    cross = gpd.GeoDataFrame({"highway": "primary", "edge_id": [3], "cs": [0], "cm": [0], "ce": [0], "fl": [0], "cap_s": [None], "cap_e": [None]},
                             geometry=[LineString([(17.999, 59.301), b, (18.001, 59.301)])], crs=4326)
    assert _twin_caps(gpd.GeoDataFrame(__import__('pandas').concat([x, cross], ignore_index=True), crs=4326))[0] == {a: "square", b: "square"}
    # "each" keeps today's blob look (no squares); a one-way road keeps round
    assert _twin_caps(_twin(pair), settings={"config": {"twin_casing": "each"}})[1] == {(0, a): None, (0, b): None, (1, a): None, (1, b): None}
    one = _twin([(1, "a", "b", 0, 0, 0, 0, None, None)])
    assert _twin_caps(one)[0] == {a: None, b: None}


def test_twin_casing_each_is_todays_look():
    """twin_casing "each": every direction draws its own casing, shifted, half the width; no __rs_pair anywhere, the end blobs as before."""
    g = _twin([(1, "a", "b", 0, 0, 0, 0, None, None), (2, "b", "a", 0, 0, 0, 0, None, None)])
    each = {"settings": {"config": {"twin_casing": "each"}}}
    html = render_edges(g, **_TWIN_KW, **each).html
    feats = [f["properties"] for f in _style(html)["sources"]["simple"]["data"]["features"]]
    assert "__rs_pair" not in html and "__rs_twin" not in html
    assert sorted((p["__rs_edge"], p["__rs_k"]) for p in feats) == [(0, 0), (0, 1), (1, 0), (1, 1)]
    one = _style(render_edges(g, **_TWIN_KW).html)
    drop = lambda p: {k: v for k, v in p.items() if k not in ("__rs_pair", "__rs_twin", "__rs_edge2", "__rs_cap")}           # noqa: E731
    assert [drop(f["properties"]) for f in one["sources"]["simple"]["data"]["features"] if f["properties"]["__rs_edge"] == 0] == \
        [drop(p) for p in feats if p["__rs_edge"] == 0]                         # the first edge's pieces: the same, flagged
    assert "ends" in _style(render_edges(g, **{**_TWIN_KW, "simple": False}, **each).html)["sources"]
    with pytest.raises(ValueError, match="twin_casing"):
        render_edges(g, **_TWIN_KW, settings={"config": {"twin_casing": "both"}})


def test_a_two_way_pair_that_disagrees_is_named_in_a_warning():
    """The pair's casing is the first edge's: the twins must agree, reversed (casing numbers, heads, caps). One that does not is named."""
    import warnings
    ok = _twin([(1, "a", "b", -1, 0, 1, 1, "yes", None), (2, "b", "a", 1, 0, -1, 1, None, "yes")])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        render_edges(ok, **_TWIN_KW, edge_id_col="edge_id")
    for bad in (ok.assign(ce=[1, 0]), ok.assign(cap_e=[None, None])):
        with pytest.warns(UserWarning, match=r"twin_casing: 1 two-way pair.*: 1 / 2"):
            render_edges(bad, **_TWIN_KW, edge_id_col="edge_id")


def test_end_caps_follow_filters_and_recolour_and_can_be_turned_off():
    html = render_edges(_pairs(), backend="web").html
    assert '["any",_has(["get","__rs_edge"],_qIds),_has(["get","__rs_edge2"],_qIds)]' in html     # id filters: a cap shows while either twin does
    assert 'RS_END_LAYERS.forEach(id=>{ if(map.getLayer(id)) map.setPaintProperty(id,"circle-color",ee)' in html
    off = _style(render_edges(_pairs(), backend="web", settings={"config": {"twin_end_caps": False}}).html)
    assert "ends" not in off["sources"] and not [l for l in off["layers"] if "ends" in l["id"]]


def test_end_caps_hide_where_the_two_directions_differ():
    """A map coloured per direction (twins with different colours) keeps today's ends: the cap is
    transparent unless both lanes share a colour, so no direction's colour shows at a street's end."""
    g = _pairs().iloc[:2].assign(edge_id=["a", "b"])
    html = render_edges(g, backend="web", color_table={"a": "#ff0000", "b": "#0000ff"}, simple=False, settings={"config": {"twin_casing": "each"}}).html
    style = _style(html)
    p = style["sources"]["ends"]["data"]["features"][0]["properties"]
    assert p["__rs_fill"] != p["__rs_fill__b"]
    fill = {l["id"]: l for l in style["layers"]}["roads-ends-fill"]["paint"]["circle-color"]
    assert fill[0] == "case" and fill[1] == ["==", ["get", "__rs_fill"], ["get", "__rs_fill__b"]]
    assert fill[-1] == "rgba(0,0,0,0)"
    same = _style(render_edges(_pairs().iloc[:2], backend="web", simple=False, settings={"config": {"twin_casing": "each"}}).html)["sources"]["ends"]["data"]["features"][0]["properties"]
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
        st = _style(render_edges(g, backend="web", directed_col="is_directed", simple=False, settings={"config": {"twin_casing": "each"}}).html)
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
    st = _style(render_edges(g, backend="web", width_m_col="w", casing_m=0, simple=False).html)
    lay = {l["id"]: l for l in st["layers"]}
    bc = next(l for i, l in lay.items() if i.endswith("-bridge"))["paint"]["line-width"]
    assert '["max", ["get", "__rs_cm"], 0.25]' in json.dumps(bc)
    assert '2.0' in json.dumps(bc)        # 2 * bridge_casing_px: the pixel floor
    assert "0.25" not in json.dumps(lay["roads-casing"]["paint"]["line-width"])        # a plain road's casing is untouched






def test_tunnels_get_light_dashes_on_their_fill_only_when_asked():
    """Light dashes on a tunnel's fill: off by default since v2's tunnel look (2026-10-06); `tunnel_fill_dash: [1.2, 1.2]` (his pick of
    2026-09-30 among three samples) draws them over the fill, translucent, butt-capped, not on a dashed class."""
    assert not any(l["id"].endswith("-pat") for l in _style(render_edges(_tunnel_world(True), backend="web", simple=False).html)["layers"])
    st = _style(render_edges(_tunnel_world(True), backend="web", settings={"config": {"tunnel_fill_dash": [1.2, 1.2]}}, simple=False).html)
    lay = {l["id"]: l for l in st["layers"]}
    ids = [l["id"] for l in st["layers"]]
    pat = lay["roads-fill-lv1-pat"]                 # the tunnel's position: over the streets it joins, under the one crossing it (docs/design/level_input.md)
    assert ids.index(pat["id"]) > ids.index("roads-fill-lv1") and pat["source"] == "roads"
    assert pat["paint"]["line-dasharray"] == [1.2, 1.2] and pat["layout"]["line-cap"] == "butt"
    assert pat["paint"]["line-color"].startswith("rgba(255,255,255")
    assert '"__rs_dash"' in json.dumps(pat["filter"]) and "__rs_tunnel" in json.dumps(pat["filter"])


def test_colour_by_recolours_the_dashed_layers_too():
    """A footway / path / steps edge is drawn by a ``-dash<n>`` layer (line-dasharray is not data-driven): it must
    follow the active colouring, or it keeps its class colour under any "colour by"."""
    html = render_edges(_tunnel_world(True), backend="web").html
    assert 'const RS_FILL_LAYERS = ["roads-fill", "roads-fill-sq", "roads-fill-sx", "roads-fill-h", "roads-fill-hsq", "roads-fill-hsx", "roads-fill-lv1"' in html          # the tunnel at position 1: over the streets it joins
    assert 'dashed(RS_FILL_LAYERS).forEach(id=>map.setPaintProperty(id,"line-color",e))' in html
    assert "RS_PIECE_LAYERS" not in html and "tpieces" not in html




def _metre_map(**kw):
    """Two parallel lanes 3.25 m apart (one 3.25 m wide, one without a width) and a plain road."""
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "w": [3.25, None, 5.0]},
                         geometry=[LineString([(18.00, 59.30), (18.01, 59.30)]),
                                   LineString([(18.00, 59.30003), (18.01, 59.30003)]),
                                   LineString([(18.00, 59.31), (18.01, 59.31)])], crs=4326)
    st = _style(render_edges(g, backend="web", simple=False, **kw).html)
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
    style = _style(render_edges(g, backend="web", cap_col="sq", simple=False).html)
    lay = {l["id"]: l for l in style["layers"]}
    ids = [l["id"] for l in style["layers"]]
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert [p.get("__rs_cap") for p in ps] == [None, True, None]
    assert lay["roads-fill-sq"]["layout"]["line-cap"] == "butt" and lay["roads-fill"]["layout"]["line-cap"] == "round"
    assert [bool(_eval(lay["roads-fill"]["filter"], p)) for p in ps] == [True, False, True]       # round: not the capped edge
    assert [bool(_eval(lay["roads-fill-sq"]["filter"], p)) for p in ps] == [False, True, False]
    assert ids.index("roads-casing") < ids.index("roads-casing-sq") < ids.index("roads-fill") < ids.index("roads-fill-sq")
    assert "roads-fill-sx" not in lay                                                              # no "square" value: no square twin
    sx = _style(render_edges(g.assign(sq=[None, True, "square"]), backend="web", cap_col="sq", simple=False).html)     # "square": flat, as long as round
    lay = {l["id"]: l for l in sx["layers"]}
    ps = [f["properties"] for f in sx["sources"]["roads"]["data"]["features"]]
    assert lay["roads-fill-sx"]["layout"]["line-cap"] == "square"
    assert [[bool(_eval(lay[i]["filter"], p)) for p in ps] for i in ("roads-fill", "roads-fill-sq", "roads-fill-sx")] == \
        [[True, False, False], [False, True, False], [False, False, True]]                         # each edge in exactly one
    plain = _style(render_edges(g.drop(columns="sq"), backend="web", simple=False).html)
    assert not [l for l in plain["layers"] if l["id"].endswith("-sq")]
    assert "__rs_cap" not in json.dumps(plain["sources"]["roads"])


def _tunnel_conf(html):
    return json.loads(re.search(r"const TUNNEL = (\{.*?\});\n", html).group(1))


def test_the_tunnel_look_is_v2s_slider():
    """docs/design/tunnel_look.md: at tunnel_strength (60) everything on a tunnel moves toward the same colour (Sand): its fill, its street names,
    its arrows (an SDF icon of their own) and every item attached to it (one fade, however an item was added); the page gets each
    colour without the look and the dash layers. A map without tunnels has no look and no Tunnels box; an unknown palette
    is an error."""
    from roadstyle.render_web import _TUN_TO, _tun_mix
    ov = Overlay(_edge_features([12, 11]), edge_col="edge_id", kind="circle", color="#ff0000")
    html = render_edges(_edge_world().assign(name=["A", "T", "B", "C"]), backend="web", basemap="blank", overlays=[ov], tunnel_control=True, simple=False).html
    style, conf = _style(html), _tunnel_conf(html)
    assert _tunnel_conf(render_edges(_edge_world(), backend="web", basemap="blank", simple=False).html)["control"] is False   # the box is off by default
    lay = {l["id"]: l for l in style["layers"]}
    assert conf["strength"] == 60 and conf["palette"] == "Graphite + silver" and conf["control"] is True and conf["ratio"] == [1, 1]
    assert conf["dash"] and all(i.startswith("roads-casing") and i.endswith("-dash") for i in conf["dash"])
    for lid, entries in conf["layers"].items():
        for k, base, to in entries:
            assert lay[lid]["paint"][k] == _tun_mix(base, {**_TUN_TO, "fill": "#d6cfc4"}[to], 60)
    kinds = {(i.split("-lv")[0].rstrip("-"), k, to) for i, entries in conf["layers"].items() for k, _, to in entries}
    assert {("roads-fill", "line-color", "fill"), ("roads-labels", "text-color", "fill"),
            ("roads-arrows", "icon-color", "fill")} <= {(a.replace("-tunnel", "").replace("-bridge", ""), b, c) for a, b, c in kinds}
    assert {to for entries in conf["layers"].values() for _, _, to in entries} == {"fill"}       # one target for everything
    arrows = [l for l in style["layers"] if l["id"].startswith("roads-arrows")]
    assert arrows and all(l["layout"]["icon-image"] == "oneway" and "icon-color" in l["paint"] for l in arrows)
    slots = style["sources"]["slots"]["data"]["features"]
    assert any(f["properties"].get("__rs_tunnel") for f in slots) and not all(f["properties"].get("__rs_tunnel") for f in slots)
    items = style["sources"]["ov0"]["data"]["features"]
    assert [f["properties"].get("__rs_tunnel") for f in items] == [True, None]           # edge 12 is the tunnel
    assert any(i.startswith("ov0-") for i in conf["layers"])                            # the item fades like the rest
    a, b = (18.000, 59.30), (18.002, 59.30)
    plain = render_edges(gpd.GeoDataFrame({"highway": ["primary"]}, geometry=[LineString([a, b])], crs=4326), backend="web", simple=False).html
    assert _tunnel_conf(plain)["layers"] == {} and _tunnel_conf(plain)["control"] is False
    with pytest.raises(ValueError):
        render_edges(_edge_world(), backend="web", settings={"config": {"tunnel_palette": "Pink"}}, simple=False)


def test_the_tunnel_moves_toward_a_chosen_colour():
    """docs/design/tunnel_look.md (2026-10-08): tunnel_toward is a name in tunnel_towards or a #rrggbb (default Slate); the slider starts at 50;
    an unknown name or a bad colour is an error naming the choices."""
    from roadstyle.render_web import _tun_mix
    cfg = lambda **c: {"config": c}
    base = _tunnel_conf(render_edges(_edge_world(), backend="web", basemap="blank").html)
    assert base["toward"] == "Sand" and base["to"]["fill"] == "#d6cfc4" and base["strength"] == 60 and base["towards"]["Dark"] == "#14181d"
    assert list(base["towards"]) == ["Slate", "Dark", "Light", "Graphite", "Navy", "Stone", "Sand", "Teal"]
    for toward, hexc in (("Dark", "#14181d"), ("#123456", "#123456")):
        html = render_edges(_edge_world(), backend="web", basemap="blank", settings=cfg(tunnel_toward=toward, tunnel_strength=60)).html
        conf, lay = _tunnel_conf(html), {l["id"]: l for l in _style(html)["layers"]}
        assert conf["toward"] == toward and conf["to"]["fill"] == hexc and conf["strength"] == 60
        for lid, entries in conf["layers"].items():
            for k, b0, to in entries:
                assert lay[lid]["paint"][k] == _tun_mix(b0, hexc, 60)
    for bad in ("Pink", "#12345", 7):
        with pytest.raises(ValueError, match="tunnel_toward.*Slate"):
            render_edges(_edge_world(), backend="web", basemap="blank", settings=cfg(tunnel_toward=bad))
    with pytest.raises(ValueError, match="tunnel_towards"):
        render_edges(_edge_world(), backend="web", basemap="blank", settings=cfg(tunnel_towards={"Slate": "grey"}))


def test_the_tunnel_target_is_chosen_in_the_browser(tmp_path):
    """The Tunnels box colour list and rsSetTunnelStyle({toward}) in a real page: a name or a colour rebuilds the expressions; a bad value throws;
    one slider of nine steps for every colour."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "toward.html"
    from roadstyle import compute_levels
    from roadstyle.render_web import _level_id
    g = _edge_world()
    fill = _level_id("roads-fill", int(compute_levels(g).fill_level[1]))
    render_edges(g, backend="web", basemap="blank_dark", tunnel_control=True, simple=False).save(path)
    get = f'() => JSON.stringify(map.getPaintProperty("{fill}", "line-color"))'
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && document.getElementById('tn-toward')", timeout=30_000)
        slate = page.evaluate(get)
        steps = page.evaluate("Array.from(document.getElementById('tn-pre').options).map(o => o.value).join()")
        opts = page.evaluate("Array.from(document.getElementById('tn-toward').options).map(o => o.value).join()")
        page.evaluate("document.getElementById('tn-toward').value = 'Dark'; document.getElementById('tn-toward').onchange()")
        dark = page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({toward: '#123456'})")
        mine = page.evaluate(get)
        bad = page.evaluate("() => { try { rsSetTunnelStyle({toward: 'x'}); return ''; } catch(e) { return e.message; } }")
        browser.close()
    assert errors == []
    assert steps == "0,25,50,55,60,65,70,75,100" and opts.startswith("Slate,Dark,Light") and opts.endswith("Teal")
    assert "#d6cfc4" in slate and "#14181d" in dark and "#d6cfc4" not in dark and "#123456" in mine and "Slate" in bad


def test_the_tunnels_box_moves_the_look_in_the_browser(tmp_path):
    """The Tunnels box and rsSetTunnelStyle in a real page: the strength moves every tunnel colour, the casing too. The casing is two layers with
    MapLibre's dash, no image: a palette's gap colour on the position's casing layer (transparent for One colour) and its dash colour on the
    dash layer, both moved toward slate; Colour by keeps the look."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "tunnels.html"
    g = _edge_world().assign(aadt=[1, 2, 3, 4])
    from roadstyle import compute_levels
    from roadstyle.render_web import _level_id
    lv = compute_levels(g)                                                       # the tunnel (row 1)'s positions, as the page computes them
    fill, casing = _level_id("roads-fill", int(lv.fill_level[1])), _level_id("roads-casing", int(lv.casing_level[1]))
    render_edges(g, backend="web", basemap="blank", color_options={"Class": {}, "AADT": {"color_by": "aadt", "cmap": "viridis"}}, tunnel_control=True,
                 settings={"config": {"tunnel_toward": "Slate"}}, simple=False).save(path)
    get = f"""() => ({{fill: JSON.stringify(map.getPaintProperty("{fill}", "line-color")),
                    pattern: map.getPaintProperty("{casing}-dash", "line-pattern") || null,
                    dash: map.getPaintProperty("{casing}-dash", "line-dasharray") || null,
                    dash_color: map.getPaintProperty("{casing}-dash", "line-color"),
                    gap: JSON.stringify(map.getPaintProperty("{casing}-sq", "line-color")),     // the tunnel's casing ends flat
                    slider: document.getElementById("tn-str").value, pal: document.getElementById("tn-pal").value}})"""
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" or "Cannot mix SDF" in m.text else None)
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && document.getElementById('tn-str')", timeout=30_000)
        page.evaluate("document.addEventListener('rs:tunnelchange', e => window._ev = e.detail)")
        opened = page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({strength: 70, palette: 'Teal + mint', ratio: [4, 3]})")
        moved, ev = page.evaluate(get), page.evaluate("window._ev")
        page.evaluate("rsSetColorField('AADT')")
        coloured = page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({strength: 0})")
        zero = page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({palette: 'One colour', strength: 100})")
        one = page.evaluate(get)
        browser.close()
    assert errors == []
    assert opened["pattern"] is None and opened["dash"] == [1, 1] and opened["slider"] == "4" and opened["pal"] == "Graphite + silver"
    assert "rgba(0,0,0,0)" not in opened["gap"]                                           # two colours by default: the gaps are the second colour
    assert moved["slider"] == "6"                                                        # nine steps: 0 25 50 55 60 65 70 75 100
    assert "70" in moved["fill"] and moved["pal"] == "Teal + mint" and moved["dash"] == [4, 3] and moved["pattern"] is None
    teal70, mint70 = "#547384", "#76919f"                                                 # #2f6f73, #9fd3cf 70 % toward #64748b (JS rounds .5 up)
    assert moved["dash_color"] == teal70 and mint70 in moved["gap"]
    assert ev == {"strength": 70, "palette": "Teal + mint", "ratio": [4, 3], "toward": "Slate"}
    assert "__rs_fill__1" in coloured["fill"] and "interpolate" in coloured["fill"]          # Colour by keeps the look
    assert zero["dash_color"] == "#2f6f73" and "#9fd3cf" in zero["gap"]                  # at 0 the palette as it is
    assert one["dash_color"] == "#64748b" and "rgba(0,0,0,0)" in one["gap"]               # One colour at 100: slate dashes, empty gaps


def test_level_columns_draw_each_position_casings_then_fills():
    """casing_level_col / fill_level_col (docs/design/level_columns.md): one casing layer and one fill layer for each position, in
    position order; an edge's casing is in the layers of its casing position and its fill in those of its fill position."""
    g = gpd.GeoDataFrame({"highway": ["residential"] * 4, "tunnel": [None, None, "yes", None],
                          "cl": [0, 0, -2, -1], "fl": [0, 1, -2, 1]},
                         geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(4)], crs=4326)
    style = _style(render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl", simple=False).html)
    lay = {l["id"]: l for l in style["layers"]}
    ids = [l["id"] for l in style["layers"]]
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert [(p["__rs_cl"], p["__rs_fl"]) for p in ps] == [(0, 0), (0, 1), (-2, -2), (-1, 1)]
    for root, key, have in (("roads-casing", "__rs_cl", (-2, -1, 0)), ("roads-fill", "__rs_fl", (-2, 0, 1))):   # a layer per position it has
        for level in (-2, -1, 0, 1):
            if level not in have:
                assert _pos_id(root, level) not in lay                    # no casing at 1, no fill at -1: no layer
                continue
            assert [bool(_eval(lay[_pos_id(root, level)]["filter"], p)) for p in ps] == [p[key] == level for p in ps]
    # in position order, casings before fills of the same position, and position 0 keeps its ids
    assert ids.index("roads-casing-lv-2") < ids.index("roads-fill-lv-2") < ids.index("roads-casing-lv-1") \
        < ids.index("roads-casing") < ids.index("roads-fill") < ids.index("roads-fill-lv1")
    # the page recolours the fill layers of every position
    html = render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl", simple=False).html
    assert '"roads-fill-lv1"' in html and '"roads-fill-lv-2"' in html


def _pos_id(root, level):
    return root if level == 0 else f"{root}-lv{level}"


def test_level_columns_keep_the_looks_and_the_dashed_classes():
    """The tunnel look and the dashed classes follow the positions."""
    g = gpd.GeoDataFrame({"highway": ["primary", "footway", "primary"], "tunnel": ["yes", None, None], "cl": [-1, 1, 0], "fl": [-1, 1, 0]},
                         geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(3)], crs=4326)
    style = _style(render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl", simple=False).html)
    ids = [l["id"] for l in style["layers"]]
    lay = {l["id"]: l for l in style["layers"]}
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert "roads-casing-lv-1-dash" in ids and "roads-fill-lv-1-pat" not in ids and "roads-fill-lv-1-under" not in ids   # no light fill dashes by default   # the tunnel's look at -1 (no underlay: an opaque fill, docs/design/tunnel_look.md)
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
    out = rs.compute_levels(g, method="solve", band_col="band", near_rules=True)      # the sidewalk only runs beside the street: a near part
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


def test_compute_levels_priority_order():
    """order="priority" (2026-10-06): where roads of one band meet, a roundabout's fill is over a tunnel's, a tunnel's over a bridge's, a bridge's
    over the class order; "class" keeps the class order alone. The band is not changed: all five are in band 0 here."""
    pytest.importorskip("scipy")
    d = 0.001
    ends = [(d, 0), (-d, 0), (0, d), (0, -d), (d, d)]
    g = gpd.GeoDataFrame({"highway": ["residential", "residential", "residential", "primary", "residential"],
                          "junction": ["roundabout", None, None, None, None], "tunnel": [None, "yes", None, None, None],
                          "bridge": [None, None, "yes", None, None], "band": [0] * 5},
                         geometry=[LineString([(18, 59), (18 + x, 59 + y)]) for x, y in ends], crs=4326)
    ring, tunnel, bridge, primary, plain = compute_levels(g, method="solve", band_col="band", order="priority").fill_level
    assert ring > tunnel > bridge > primary > plain
    cls = compute_levels(g, method="solve", band_col="band", order="class").fill_level
    assert cls[3] > cls[0] == cls[1] == cls[2] == cls[4]                                  # primary over the residential roads, whatever their tags


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
    s = rs.compute_levels(g, method="solve", near_rules=True)
    info = s.attrs["levels_info"]
    assert info["pairs"] == 268                                                     # stack pairs (docs/design/level_input.md: roads of different bands that only meet take the order)
    under = [944, 4251, 2082, 2363]
    assert all(s.casing_level[207] > s.fill_level[i] for i in under)                # the bridge is over them, outline included
    assert s.attrs["levels_given_up"] == []                                         # every real crossing kept (docs/design/level_input.md)
    near = s.attrs["levels_near"]                                                     # rules on parts that only come near: last, a warning when broken
    col = {"start": "casing_start", "main": "casing_level", "end": "casing_end"}
    assert near and all(s[col[h]][u] <= s.fill_level[l] for u, l, h in near)


def test_level_columns_put_each_positions_arrows_after_its_fill_layers():
    """Position mode: one-way arrows follow the fill position (not the lvl tag): an arrow layer per position right after that
    position's last fill layer, so a tunnel's arrows are above its own road."""
    import roadstyle as rs
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["primary"] * 3, "oneway": ["yes"] * 3, "tunnel": [None, "yes", None], "bridge": [None, None, "yes"],
                          "layer": [None, -1, 1]},
                         geometry=[LineString([(18, 59 + i * d), (18 + d, 59 + i * d)]) for i in range(3)], crs=4326)
    g = rs.compute_levels(g, method="tags")
    style = _style(render_edges(g, backend="web", casing_level_col="casing_level", fill_level_col="fill_level", simple=False).html)
    ids = [l["id"] for l in style["layers"]]
    lay = {l["id"]: l for l in style["layers"]}
    for pos in (-1, 0, 1):
        arrows = "roads-arrows" if pos == 0 else f"roads-arrows-lv{pos}"
        fills = [i for i, n in enumerate(ids) if n.startswith(("roads-fill-lv-1", "roads-fill-lv1")) and (f"lv{pos}" in n)] if pos else \
            [i for i, n in enumerate(ids) if n in ("roads-fill", "roads-fill-sq", "roads-fill-pat")]
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
    style = _style(render_edges(g, backend="web", casing_level_col="casing_level", fill_level_col="fill_level", simple=False).html)
    ids = [l["id"] for l in style["layers"]]
    lay = {l["id"]: l for l in style["layers"]}
    for pos in (-1, 0, 1):
        arrows, names = ("roads-arrows", "roads-labels") if pos == 0 else (f"roads-arrows-lv{pos}", f"roads-labels-lv{pos}")
        assert ids.index(names) == ids.index(arrows) + 1, names
        assert '"fl"' in json.dumps(lay[names]["filter"])
    assert ids.index("roads-labels-lv-1") < ids.index("roads-fill") < ids.index("roads-labels-lv1")     # a higher position's names are above lower roads
    plain = [l["id"] for l in _style(render_edges(g, backend="web", simple=False).html)["layers"]]
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
    html = render_edges(g, backend="web", casing_level_col="cl", fill_level_col="fl", simple=False, settings={"config": {"twin_casing": "each"}}).html
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
    g = gpd.GeoDataFrame({"highway": ["residential"] * 4, "layer": [None, None, None, -1], "tunnel": [None, None, None, "yes"],
                          "band": [0, 0, 0, -1]}, geometry=rows, crs=4326)
    out = rs.compute_levels(g, method="solve", band_col="band", near_rules=True)             # the caller's bands: under its end even where they only meet
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
    html = render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0, simple=False).html
    style = _style(html)
    parts = [f for f in style["sources"]["casings"]["data"]["features"] if not f["properties"].get("__rs_seam")]     # the pieces, not the seams
    by = {}
    for f in parts:
        by.setdefault(f["properties"]["__rs_edge"], []).append(f)
    assert [len(by[i]) for i in (0, 1, 2)] == [3, 1, 2]
    assert [f["properties"]["__rs_cl"] for f in by[2]] == [-1, -2]                    # a short road keeps both heads (short_road_heads.md)
    assert [f["properties"]["__rs_cl"] for f in by[0]] == [-1, 0, -2]                 # start head, main, end head
    lengths = [LineString(f["geometry"]["coordinates"]) for f in by[0]]
    assert abs(lengths[0].length * 111320 * math.cos(math.radians(59)) - 5.0) < 0.2 and abs(lengths[2].length * 111320 * math.cos(math.radians(59)) - 5.0) < 0.2
    assert by[0][0]["geometry"]["coordinates"][0] == [18.0, 59.0]                     # the first piece starts at the edge's first vertex
    lay = {l["id"]: l for l in style["layers"]}
    assert all(l["source"] == "casings" for i, l in lay.items() if i.startswith("roads-casing") and "-lv" in i or i == "roads-casing")
    assert lay["roads-fill"]["source"] == "roads" and "roads-fill-lv-1" not in lay        # every fill is at 0
    assert style["sources"]["roads"]["data"]["features"][0]["geometry"]["coordinates"][-1] == [18 + d, 59.0]       # the fill line is the whole edge
    assert '_has(["get","__rs_edge"],_qIds)' in html                       # the pieces follow rsFilter by their edge
    # without the head columns nothing changes: no casing source
    assert "casings" not in _style(render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl", simple=False).html)["sources"]


def test_divided_casing_main_piece_ends_flat_and_heads_round():
    """The main piece of a divided casing carries __rs_cap (flat ends: a round end would reach into the heads); the heads and an unsplit casing do not, and the
    flat-end twin layer of the casing exists and reads the casing source."""
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["residential"] * 2, "cs": [-1, 0], "cm": [0, 0], "ce": [-2, 0], "fl": [0, 0]},
                         geometry=[LineString([(18, 59), (18 + d, 59)]), LineString([(18, 59.01), (18 + d, 59.01)])], crs=4326)
    style = _style(render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0, simple=False).html)
    parts = [f for f in style["sources"]["casings"]["data"]["features"] if not f["properties"].get("__rs_seam")]     # the pieces, not the seams
    flags = [(f["properties"]["__rs_edge"], f["properties"]["__rs_cl"], bool(f["properties"].get("__rs_cap"))) for f in parts]
    assert flags == [(0, -1, False), (0, 0, True), (0, -2, False), (1, 0, False)]       # head, MAIN flat, head; the unsplit edge stays round
    lay = {l["id"]: l for l in style["layers"]}
    assert lay["roads-casing-sq"]["source"] == "casings" and lay["roads-casing-sq"]["layout"]["line-cap"] == "butt" and lay["roads-casing"]["layout"]["line-cap"] == "round"
    assert "__rs_cap" in json.dumps(lay["roads-casing"]["filter"])                   # the round layer leaves the flat pieces to the twin


def test_level_columns_draw_the_bridge_casing_look_at_each_position():
    """Position mode: a bridge edge gets the bridge look in the casing of its position: a heavier black casing (roads-casing-bridge, per position),
    with the end shapes of the plain casing (a twin of each: round, flat -sq-bridge for the divided casing's main piece), from the casing source
    when the casing is divided; the plain casing layer leaves bridge edges to it; no bridge edge, no such layer."""
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "bridge": ["yes", None], "layer": [None, None], "cm": [0, 0], "fl": [0, 0], "cs": [0, 0], "ce": [0, 0]},
                         geometry=[LineString([(18, 59), (18 + d, 59)]), LineString([(18, 59.01), (18 + d, 59.01)])], crs=4326)     # edge 0 is a bridge, edge 1 is plain, same position
    for kw, source in ((dict(), "roads"), (dict(casing_start_col="cs", casing_end_col="ce"), "casings")):
        style = _style(render_edges(g, backend="web", casing_level_col="cm", fill_level_col="fl", **kw, simple=False).html)
        lay = {l["id"]: l for l in style["layers"]}
        ids = [l["id"] for l in style["layers"]]
        ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
        bl, plain = lay["roads-casing-bridge"], lay["roads-casing"]
        assert bl["source"] == source and bl["layout"]["line-cap"] == "round" and plain["layout"]["line-cap"] == "round"
        assert bl["paint"]["line-color"] == "#64748b" and "line-width" in bl["paint"]
        assert ids.index("roads-casing-bridge") < ids.index("roads-fill")                                  # a casing layer: before the position's fills
        assert [bool(_eval(bl["filter"], p)) for p in ps] == [True, False]                                 # the bridge layer draws the bridge edge only
        assert [bool(_eval(plain["filter"], p)) for p in ps] == [False, True]                              # the plain layer draws the plain edge only
    off = _style(render_edges(g.assign(bridge=None), backend="web", casing_level_col="cm", fill_level_col="fl", simple=False).html)
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
    style = _style(render_edges(g, **kw, simple=False, settings={"config": {"twin_casing": "each"}}).html)
    caps = {tuple(f["geometry"]["coordinates"]): f["properties"] for f in style["sources"]["ends"]["data"]["features"]}
    assert caps[(18.0, 59.0)]["__rs_cl"] == -1 and caps[(18 + d, 59.0)]["__rs_cl"] == -2          # the head numbers at the two nodes
    assert caps[(18.0, 59.0)]["__rs_fl"] == 0                                                      # the fill circle: the road's fill number
    assert "roads-ends-casing-lv-1" in {l["id"] for l in style["layers"]} and "roads-ends-casing-lv-2" in {l["id"] for l in style["layers"]}
    flat = _style(render_edges(g.assign(flat=[True, True]), cap_col="flat", **kw, simple=False, settings={"config": {"twin_casing": "each"}}).html)
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
    assert tight.attrs["levels_info"]["solves"] == 3 and len(tight.attrs["levels_given_up"]) == 1      # no near rules: no stage 3
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
        assert len(b.attrs["levels_given_up"]) == len(a.attrs["levels_given_up"])                # nothing more given up for fewer positions (random lines
        assert b.attrs["levels_info"]["order_violations"] == a.attrs["levels_info"]["order_violations"]   # cross near each other's heads: loops, docs/design/level_input.md)
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
    assert tight.attrs["levels_info"]["solves"] == 3 and len(tight.attrs["levels_given_up"]) == 1      # no near rules: no stage 3


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
    style = _style(render_edges(g, backend="web", overlays=[first, second], simple=False).html)
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
    plain = _style(render_edges(g, backend="web", overlays=[Overlay(pts, kind="circle")], simple=False).html)             # without edge_col: as before, over all roads
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



def test_an_attached_item_selects_its_road_or_itself():
    """Overlay(select=...): "road" (default) or "item" (docs/design/edge_items.md), anything else is an error; the page learns it per overlay,
    and an item selected itself takes the highlight (in the page's select colour) even without popup fields."""
    with pytest.raises(ValueError, match="select must be 'road' or 'item'"):
        Overlay(_edge_features([12]), edge_col="edge_id", select="lane")
    html = render_edges(_edge_world(), backend="web", select_color="#123456",
                        overlays=[Overlay(_edge_features([12]), edge_col="edge_id", kind="circle"),
                                  Overlay(_edge_features([13]), edge_col="edge_id", kind="circle", select="item", popup=[])]).html
    meta = json.loads(html.split("const OVERLAYS = ")[1].split(";\n")[0])
    assert [m["select"] for m in meta] == ["road", "item"]
    circle = next(l for l in _style(html)["layers"] if l["id"].startswith("ov1-circle-lv"))
    assert '["case", ["boolean", ["feature-state", "select"], false], "#123456"' in json.dumps(circle["paint"]["circle-color"])

def test_arrows_and_street_names_belong_to_an_edge(monkeypatch):
    """docs/design/edge_overlays.md: every slot (the piece of road that carries an arrow or a name) carries the edge under its middle point (__rs_edge, and __rs_edge2 for the
    twin of a two-way street) and the fill number of that edge."""
    a, b, c = (18.000, 59.300), (18.003, 59.300), (18.003, 59.303)
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "name": ["Main", "Main", "Side"], "oneway": [False, False, True]},
                         geometry=[LineString([a, b]), LineString([b, a]), LineString([b, c])], crs=4326)       # a two-way street (two twins) and a one-way street
    style = _style(render_edges(g, backend="web", arrows=True, labels=True).html)
    roads = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    slots = [f["properties"] for f in style["sources"]["slots"]["data"]["features"]]
    assert slots and all("__rs_edge" in s for s in slots)
    for s in slots:
        assert 0 <= s["__rs_edge"] < len(roads) and s.get("fl", 0) == roads[s["__rs_edge"]]["__rs_fl"]
    two_way = [s for s in slots if s["name"] == "Main"]
    assert two_way and all({s["__rs_edge"], s["__rs_edge2"]} == {0, 1} for s in two_way)       # the pair: its two twins
    one_way = [s for s in slots if s["name"] == "Side"]
    assert one_way and all(s["__rs_edge"] == 2 and "__rs_edge2" not in s for s in one_way)


def test_road_fill_false_draws_the_casing_but_not_the_fill():
    """docs/design/edge_overlays.md, three ways to use it: road_fill=False keeps the casing layers and makes the fill layers (and the end caps' fills) invisible; the default is unchanged."""
    g = _edge_world()
    on = _style(render_edges(g, backend="web", simple=False).html)["layers"]
    off = _style(render_edges(g, backend="web", road_fill=False, simple=False).html)["layers"]
    assert [lyr["id"] for lyr in on] == [lyr["id"] for lyr in off]                     # the same layers: the fills stay for clicks and hovers
    for a, b in zip(on, off, strict=True):
        if a["id"].endswith("-pat"):
            assert a == b                                                               # the tunnel pattern stays visible, over the items
        elif a["id"].startswith("roads-fill"):
            assert b["paint"]["line-opacity"] == 0 and a["paint"].get("line-opacity") != 0
        elif a["id"].startswith("roads-ends-fill"):
            assert b["paint"]["circle-opacity"] == 0
        else:
            assert a == b                                                               # the casings, arrows, names: untouched
    with_items = _style(render_edges(g, backend="web", road_fill=False, overlays=[Overlay(_edge_features([12]), edge_col="edge_id", kind="circle")], simple=False).html)
    assert any(lyr["id"].startswith("ov0-circle-lv") for lyr in with_items["layers"])


_CO = {"Class": {}, "AADT": {"color_by": "aadt", "cmap": "viridis"}}


def _marks():
    return gpd.GeoDataFrame({"n": [1]}, geometry=[LineString([(17.9, 59.37), (17.91, 59.38)]).centroid], crs=4326)


def test_views_are_baked_and_checked():
    """docs/design/core_model_and_views.md, views: each view is baked with its settings; a setting that is not known, or that names something
    the page does not have, is an error (no view is silently half applied)."""
    html = render_edges(_edges(), backend="web", color_options=_CO, overlays=[Overlay(_marks(), label="marks")],
                        views={"Flow": {"color": "AADT", "overlays": {"marks": False}}, "Casing": {"road_fill": False}}).html
    views = json.loads(re.search(r"const VIEWS = (\[.*?\]);\n", html).group(1))
    assert views == [{"name": "Flow", "set": {"color": "AADT", "overlays": {"marks": False}}},
                     {"name": "Casing", "set": {"road_fill": False}}]
    fill = json.loads(re.search(r"const RS_ROAD_FILL = (\{.*?\});\n", html).group(1))
    assert fill["on"] is True and "roads-fill" in fill["paint"] and not any(k.endswith("-pat") for k in fill["paint"])
    assert "const VIEWS = [];" in render_edges(_edges(), backend="web").html                 # no views: no menu
    for bad in ({"colour": "AADT"}, {"color": "Speed"}, {"road_fill": 1}, {"overlays": {"lanes": True}},
                {"classes": ["trunk"]}, {"basemap": "nowhere"}):
        with pytest.raises(ValueError):
            render_edges(_edges(), backend="web", color_options=_CO, views={"V": bad})


def test_views_switch_in_the_browser(tmp_path):
    """The View menu and rsSetView in a real page: the first view on open, then each view sets the colour option, the road fill and the
    overlays it names, and leaves the rest as it is."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "views.html"
    render_edges(_edges(), backend="web", basemap="blank", color_options=_CO, road_fill=False,
                 overlays=[Overlay(_marks(), label="marks")],
                 views={"Roads": {"color": "Class", "road_fill": True, "overlays": {"marks": False}},
                        "Flow": {"color": "AADT"},
                        "Casing": {"road_fill": False, "overlays": {"marks": True}}}, simple=False).save(path)
    state = """() => ({opacity: map.getPaintProperty("roads-fill", "line-opacity"), color: JSON.stringify(map.getPaintProperty("roads-fill", "line-color")),
                       marks: map.getLayoutProperty(RS_OVERLAYS[0].layers[0], "visibility"), menu: document.getElementById("vw-select").value,
                       colour_menu: document.getElementById("co-select").value})"""
    errors, events = [], []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && document.getElementById('vw-select')", timeout=30_000)
        page.evaluate("document.addEventListener('rs:viewselect', e => window._ev = e.detail.view)")
        opened = page.evaluate(state)
        page.evaluate("rsSetView('Flow')")
        flow = page.evaluate(state)
        events.append(page.evaluate("window._ev"))
        page.evaluate("rsSetView(2)")
        casing = page.evaluate(state)
        browser.close()
    assert errors == []
    assert opened["opacity"] is None and opened["marks"] == "none" and "__rs_fill\"" in opened["color"] and opened["menu"] == "0"   # Roads, on open
    assert flow["opacity"] is None and flow["marks"] == "none" and "__rs_fill__1" in flow["color"]                                # only the colour changed
    assert flow["menu"] == "1" and flow["colour_menu"] == "1" and events == ["Flow"]
    assert casing["opacity"] == 0 and casing["marks"] == "visible" and "__rs_fill__1" in casing["color"] and casing["menu"] == "2"


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


def test_level_input_and_solve_levels():
    """docs/design/level_input.md (2026-10-06): roads of different bands that only meet (a tunnel mouth) take the priority order, roads
    that cross take the band; with band_col the caller's bands decide everywhere; edits switch a pair off or add one; ids may name either
    direction of a road."""
    pytest.importorskip("scipy")
    import pandas as pd

    import roadstyle as rs
    g = _edge_world()                                  # ground 11 - tunnel 12 - ground 14 in a line, street 13 crossing over the tunnel's middle
    roads, pairs = rs.level_input(g)
    assert list(roads["road"]) == ["11", "12", "14", "13"] and list(roads["band"]) == [0, -1, 0, 0]
    rel = {(r.relation, r.a, r.b) for r in pairs.itertuples()}
    assert {("order", "12", "11"), ("order", "12", "14"), ("stack", "13", "12")} <= rel           # mouths: priority; the crossing: band
    assert not {("stack", "11", "12"), ("stack", "14", "12")} & rel
    fl = dict(zip(roads["road"], rs.solve_levels(roads, pairs)["fill_level"], strict=True))
    assert fl["12"] > fl["11"] and fl["12"] > fl["14"] and fl["13"] > fl["12"]                   # the tunnel over its mouths, under the crossing street
    edits = pd.DataFrame([{"relation": "order", "a": "12", "b": "11", "enabled": "false"},           # switch the mouth's wish off ...
                          {"relation": "stack", "a": "11", "b": "12", "a_end": "main", "enabled": "true"}])   # ... and put the ground road's main part over the tunnel
    fl2 = dict(zip(roads["road"], rs.solve_levels(roads, pairs, edits=edits)["fill_level"], strict=True))
    assert fl2["11"] > fl2["12"]
    with pytest.raises(ValueError):
        rs.solve_levels(roads, pairs, edits=pd.DataFrame([{"relation": "order", "a": "99", "b": "11", "enabled": "false"}]))
    _, kept = rs.level_input(g.assign(band=[0, -1, 0, 0]), band_col="band", near_rules=True)       # the caller's bands: over / under everywhere
    assert {("near", "11", "12", "main"), ("near", "14", "12", "main")} <= {(r.relation, r.a, r.b, r.a_end) for r in kept.itertuples()}   # they only meet: near


def test_render_edges_takes_no_band_or_order():
    """docs/design/level_input.md: the band and the order are inputs of the level step; the renderer only draws the levels it is given (or
    computes them with the level step's defaults). Passing them is an error, not a silently ignored keyword."""
    for k, v in (("band_col", "band"), ("order", "class")):
        with pytest.raises(ValueError, match="compute the levels first"):
            render_edges(_edges(), backend="web", **{k: v})


def test_roadstyle_levels_make_and_solve(tmp_path):
    """roadstyle-levels make SOURCE FOLDER, then solve FOLDER: roads.parquet, pairs.csv and an empty edits.csv, then levels.csv with one row
    per edge and its ends; make again keeps your edits.csv."""
    pytest.importorskip("scipy")
    import pandas as pd

    from roadstyle.level_area import main
    src, area = tmp_path / "edges.geojson", tmp_path / "area"
    _edge_world().to_file(src)
    main(["make", str(src), str(area)])
    assert {p.name for p in area.iterdir()} == {"roads.parquet", "pairs.csv", "edits.csv"}
    (area / "edits.csv").write_text("relation,a,b,a_end,b_end,enabled\norder,12,11,,,true\n")
    main(["make", str(src), str(area)])
    assert "order,12,11" in (area / "edits.csv").read_text()                       # yours: never written by make
    main(["solve", str(area)])
    lv = pd.read_csv(area / "levels.csv")
    assert len(lv) == len(_edge_world()) and {"casing_level", "fill_level", "head_start_m", "cap_end"} <= set(lv.columns)


def test_an_area_of_a_database_writes_its_result_into_it(tmp_path):
    """make_area(edges, folder, db=...): every solve (solve_area, the editor's too) writes levels.csv into the database
    (visualization.edge_levels, with the ends); load_area_levels reads it back for the same edges and refuses other edges."""
    pytest.importorskip("scipy")
    duckdb = pytest.importorskip("duckdb")

    import roadstyle as rs
    from roadstyle.level_area import area_db, make_area, solve_area
    edges = _edge_world().assign(edge_id=[101, 102, 103, 104])
    db, area = tmp_path / "area.duckdb", tmp_path / "area.levels"
    duckdb.connect(str(db)).close()
    make_area(edges, area, db=db, id_col="edge_id")
    assert area_db(area) == db.resolve()
    solve_area(area)
    con = duckdb.connect(str(db), read_only=True)
    got = rs.load_area_levels(con, edges)
    assert list(got["edge_id"]) == [101, 102, 103, 104] and got["fill_level"].notna().all() and set(got["cap_start"]) <= {"round", "square", "flat"}
    with pytest.raises(ValueError, match="not the edges"):
        rs.load_area_levels(con, edges.iloc[:3])
    con.close()


def test_heads_and_caps_may_name_either_direction_of_a_road(tmp_path):
    """heads.csv / caps.csv rows name a road by any of its edges, as edits.csv does: an edge running against its road swaps start and end;
    a row naming no road is an error, never left out."""
    import pandas as pd

    from roadstyle.level_area import own
    roads = pd.DataFrame({"road": ["1"], "edges": [["1"]], "reversed": [["2"]]})
    (tmp_path / "heads.csv").write_text("road,start_m,end_m\n2,3.0,\n")
    (tmp_path / "caps.csv").write_text("road,start,end\n1,flat,round\n")
    heads, caps = own(tmp_path, roads)
    assert heads == {"1": ("", "3.0")} and caps == {"1": ("flat", "round")}
    (tmp_path / "caps.csv").write_text("road,start,end\n9,flat,\n")
    with pytest.raises(ValueError, match="no road of this area"):
        own(tmp_path, roads)


def test_the_priority_order_warns_without_a_junction_column():
    """order="priority" puts a roundabout on top where roads meet; edges with no junction column get a warning that says so (2026-10-07: a
    caller that left the column out lost every roundabout silently)."""
    import warnings

    import roadstyle as rs
    with pytest.warns(UserWarning, match="no 'junction' column"):
        rs.level_input(_edge_world())
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        rs.level_input(_edge_world().assign(junction=None))                            # the column, even empty: no warning


def test_roads_on_the_same_line_are_one_road_only_if_they_are_the_same_kind():
    """Both directions of a segment are one road; a footway lying exactly on a tunnel's piece is not (2026-10-07: it took the tunnel's place)."""
    import roadstyle as rs
    m = 1 / 111320.0
    a = LineString([(18.0, 59.3), (18.0, 59.3 + 20 * m)])
    g = gpd.GeoDataFrame({"edge_id": [1, 2, 3], "highway": ["tertiary", "tertiary", "footway"], "tunnel": ["yes", "yes", None]},
                         geometry=[a, LineString(list(a.coords)[::-1]), a], crs=4326)
    roads, _ = rs.level_input(g)
    by = {r: (list(e), list(b), h) for r, e, b, h in zip(roads["road"], roads["edges"], roads["reversed"], roads["highway"], strict=True)}
    assert by == {"1": (["1"], ["2"], "tertiary"), "3": (["3"], [], "footway")}


def test_a_road_keeps_the_modes_of_all_its_edges():
    """level_input keeps a modes column: the modes of both directions together (a one-way street's reverse is walking only)."""
    import roadstyle as rs
    m = 1 / 111320.0
    a = LineString([(18.0, 59.3), (18.0, 59.3 + 20 * m)])
    g = gpd.GeoDataFrame({"edge_id": [1, 2], "highway": ["residential"] * 2, "modes": ["driving + walking", "walking + cycling"]},
                         geometry=[a, LineString(list(a.coords)[::-1])], crs=4326)
    roads, _ = rs.level_input(g)
    assert list(roads["modes"]) == ["driving + walking + cycling"]


def test_rsfilter_and_rscolor_by_ids_in_the_browser(tmp_path):
    """rsFilter / rsColor take an id set as a lookup (_has: a "match"), not a list scanned per feature (a filter of thousands of ids froze
    the page, 2026-10-07): in a real page they show only those roads, paint them, and reset."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "f.html"
    render_edges(_edges().assign(c0="round", c1="flat"), backend="web", basemap="blank", cap_start_col="c0", cap_end_col="c1", simple=False).save(path)   # two ends: fill halves
    shown = "() => new Set(map.queryRenderedFeatures().filter(f => f.source === 'roads').map(f => f.id)).size"
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded()", timeout=30_000)
        every = page.evaluate(shown)
        drawn = page.evaluate("() => map.queryRenderedFeatures().filter(f => f.source === 'halves').length")
        page.evaluate("rsFilter([0, 0])")
        page.wait_for_function("map.loaded()")
        one = page.evaluate(shown)
        page.evaluate("rsFilter([])")
        page.wait_for_function("map.loaded()")
        none = page.evaluate(shown)
        halves = page.evaluate("() => map.queryRenderedFeatures().filter(f => f.source === 'halves').length")
        page.evaluate("rsFilter(null); rsColor([1], '#ff0000')")
        page.wait_for_function("map.loaded()")
        back = page.evaluate(shown)
        browser.close()
    assert errors == [] and every > 1 and one == 1 and none == 0 and back == every and drawn > 0 and halves == 0   # the fill halves go with their road


def test_a_footway_on_a_street_the_other_way_round_is_no_lane_of_it():
    """Two edges on one line in opposite directions are a two-way street's lanes only when they are the same class: a footway lying on a
    street the other way round left the street drawn as one narrow, shifted lane (2026-10-07)."""
    from roadstyle import render_web as rw
    m = 1 / 111320.0
    a = LineString([(18.0, 59.3), (18.0, 59.3 + 20 * m)])
    g = gpd.GeoDataFrame({"highway": ["tertiary", "footway", "residential", "residential"]},
                         geometry=[a, LineString(list(a.coords)[::-1]), LineString([(18.001, 59.3), (18.001, 59.3 + 20 * m)]),
                                   LineString([(18.001, 59.3 + 20 * m), (18.001, 59.3)])], crs=4326)
    geo = rw.fc_dict(g)
    rw._mark_twoway(geo, None, "highway")
    assert [f["properties"]["__rs_twoway"] for f in geo["features"]] == [False, False, True, True]


def test_the_road_tooltip_waits_for_the_mouse_to_rest():
    """hover_delay_ms (300 by default): the page waits this long before the road tooltip shows; 0 shows it at once."""
    assert "const _TIP_DELAY = 300;" in render_edges(_edge_world(), backend="web", road_tooltip=True).html
    assert "const _TIP_DELAY = 0;" in render_edges(_edge_world(), backend="web", road_tooltip=True, hover_delay_ms=0).html


def test_the_last_solver_stage_at_its_time_limit_keeps_its_best_numbers(monkeypatch):
    """The last stage (cost, fewest positions) stopped by its time limit with numbers in hand: they are kept, with a warning and
    levels_info status TIME_LIMIT (a GitHub build of an all-modes area failed there, 2026-10-07); any other failure is still an error."""
    pytest.importorskip("scipy")
    import scipy.optimize as so

    import roadstyle as rs
    roads, pairs = rs.level_input(_edge_world())
    first = rs.solve_levels(roads, pairs)
    fixed = {first["road"].iloc[0]: tuple(int(first[c].iloc[0]) for c in ("casing_start", "casing_level", "casing_end", "fill_level"))}
    real = so.milp

    def at_limit(*a, **k):
        r = real(*a, **k)
        r.status, r.message = 1, "Time limit reached."
        return r
    monkeypatch.setattr(so, "milp", at_limit)
    with pytest.warns(UserWarning, match="time limit"):
        out = rs.solve_levels(roads, pairs, fixed=fixed)                  # held numbers: HiGHS, not the flow
    assert out.attrs["levels_info"]["status"] == "TIME_LIMIT" and out["fill_level"].notna().all()

    def failed(*a, **k):
        r = real(*a, **k)
        r.status, r.x, r.message = 4, None, "Other."
        return r
    monkeypatch.setattr(so, "milp", failed)
    with pytest.raises(RuntimeError, match="status 4"):
        rs.solve_levels(roads, pairs, fixed=fixed)


def test_level_editor_saves_only_what_the_solver_takes(tmp_path):
    """The level editor (roadstyle.level_editor): the pairs between two roads (by any edge id), an edit the solver refuses is not written, a
    taken one is written with the file before it kept as edits.csv.bak, and levels.csv follows."""
    pytest.importorskip("scipy")
    import pandas as pd

    from roadstyle.level_area import make_area
    from roadstyle.level_editor import Area
    make_area(_edge_world(), tmp_path)
    (tmp_path / "edits.csv").unlink()                                   # as before: no edits.csv yet
    area = Area(tmp_path)
    got = area.relations("12", "11")
    assert {(r["relation"], r["a"], r["b"]) for r in got["rows"] if r["section"] == "found"} >= {("order", "12", "11")}
    assert not [r for r in got["rows"] if r["section"] != "found"] and set(got["roads"]) >= {"11", "12"}
    before = (tmp_path / "edits.csv").read_text()
    with pytest.raises(ValueError):
        area.change(pd.DataFrame([{"relation": "stack", "a": "999", "b": "11", "a_end": "main", "b_end": "", "enabled": "true"}]))
    assert (tmp_path / "edits.csv").read_text() == before
    area.change(pd.DataFrame([{"relation": "order", "a": "12", "b": "11", "a_end": "", "b_end": "", "enabled": "false"}]))
    assert area.said.startswith("solved the whole area") and area.full                    # every road of this tiny area is around the change
    assert "false" in (tmp_path / "edits.csv").read_text() and (tmp_path / "edits.csv.bak").read_text() == before
    new = [r for r in area.relations("11", "12")["rows"] if r["section"] == "new"]
    assert len(new) == 1 and (tmp_path / "levels.csv").exists()                  # added in this session: "new", not "saved"
    assert len(area.relations("12")["rows"]) >= 3                                # one road: everything about it, in both tables
    gu = area.given_up()                                                          # the solver's given-up pairs, with the parts that broke
    assert [(r["a"], r["b"]) for r in gu["rows"]] == [tuple(p) for p in area.stats["given_up"]] and set(gu["roads"]) >= {x for r in gu["rows"] for x in (r["a"], r["b"])}
    assert [f["road"] for f in area.find(" 12 ")] == ["12"] and area.find("") == []                 # search: an edge id ...
    ref = area.facts["12"]["edge_ref"] = "120113158#1f"
    assert area.find(ref.upper())[0]["road"] == "12" and area.find("0113158")[0]["road"] == "12"   # ... or (a part of) an edge_ref
    stack = {"relation": "stack", "a": "11", "b": "14", "a_end": "start", "b_end": "end", "enabled": "true"}
    first = area.edits().iloc[0].to_dict()
    with pytest.raises(ValueError):                                               # a delete of a row that is not as the page saw it
        area.apply([{"op": "delete", "index": 0, "row": {**first, "enabled": "true"}}])
    area.apply([{"op": "add", "body": stack}, {"op": "delete", "index": 0, "row": first}])     # the page's waiting changes, in one solve
    assert area.edits()[["relation", "a_end", "b_end"]].values.tolist() == [["stack", "start", ""]]     # a stack keeps its part
    for bad in ([{"op": "add", "body": {**stack, "a_end": "middle"}}], [{"op": "delete", "index": 5, "row": first}], []):
        with pytest.raises(ValueError):
            area.apply(bad)
    assert len(area.edits()) == 1                                                 # nothing saved
    with pytest.raises(ValueError, match="already in edits.csv"):                 # an exact copy of a rule already there (2026-10-08: copies kept
        area.apply([{"op": "add", "body": stack}])                                # a rule working after one copy was deleted)
    assert len(area.edits()) == 1
    area.apply([{"op": "cap", "road": "12", "end": "start", "cap": "square"}, {"op": "cap", "road": "12", "end": "end", "cap": "square"}])   # caps.csv
    assert (tmp_path / "caps.csv").read_text().split() == ["road,start,end", "12,square,square"] and area.facts["12"]["caps"] == ["square", "square"]
    area.apply([{"op": "cap", "road": "12", "end": "start", "cap": ""}, {"op": "cap", "road": "12", "end": "end", "cap": ""}])     # the default again
    assert (tmp_path / "caps.csv").read_text().split() == ["road,start,end"] and area.facts["12"]["caps"] == ["", ""]
    with pytest.raises(ValueError):
        area.apply([{"op": "cap", "road": "12", "end": "start", "cap": "pointy"}])
    area.apply([{"op": "head", "road": "12", "end": "end", "m": "12.5"}])                 # a head's length: heads.csv, the solver and the drawing
    assert (tmp_path / "heads.csv").read_text().split() == ["road,start_m,end_m", "12,,12.5"] and area.facts["12"]["heads"] == [area.facts["12"]["heads_auto"][0], 12.5]
    lv = pd.read_csv(tmp_path / "levels.csv", dtype={"edge": str}).set_index("edge")        # levels.csv has each edge's ends as drawn
    assert lv.loc["12", "head_end_m"] == 12.5 and set(lv["cap_start"]) <= {"round", "square", "flat"}
    with pytest.raises(ValueError):
        area.apply([{"op": "head", "road": "12", "end": "end", "m": "-3"}])
    L = area.facts["12"]["length_m"]                                                       # one longer, the other shorter, in one change: checked together
    area.apply([{"op": "head", "road": "12", "end": "start", "m": str(round(L - 1, 1))}, {"op": "head", "road": "12", "end": "end", "m": "0.5"}])
    area.apply([{"op": "head", "road": "12", "end": "start", "m": "0.5"}, {"op": "head", "road": "12", "end": "end", "m": str(round(L - 1, 1))}])
    with pytest.raises(ValueError):                                                       # both heads together cannot be more than the road
        L = area.facts["12"]["length_m"]
        area.apply([{"op": "head", "road": "12", "end": "start", "m": str(L)}, {"op": "head", "road": "12", "end": "end", "m": "1"}])


def test_the_editor_never_solves_for_a_head_change(tmp_path, monkeypatch):
    """2026-10-08: the solver works from the tables only, so a head change (even heads over the whole road) is saved and drawn without a solve."""
    pytest.importorskip("scipy")
    from roadstyle import level_editor
    from roadstyle.level_area import make_area
    from roadstyle.level_editor import Area
    make_area(_edge_world(), tmp_path)
    area = Area(tmp_path)
    solved = area.solved
    L = area.facts["12"]["length_m"]
    with monkeypatch.context() as m:
        m.setattr(level_editor, "solve_local", lambda *a, **k: pytest.fail("solved"))
        area.apply([{"op": "head", "road": "12", "end": "end", "m": "12.5"}])
        assert area.said == "not solved again (heads and caps are drawing only)" and area.solved is solved
        area.apply([{"op": "head", "road": "12", "end": "start", "m": str(L)}, {"op": "head", "road": "12", "end": "end", "m": "0.049"}])   # no main part
        assert area.solved is solved
    assert (tmp_path / "heads.csv").read_text().split() == ["road,start_m,end_m", f"12,{L},0.049"] and area.facts["12"]["heads"][1] == 0.049


def test_the_editor_updates_the_open_page_with_the_features_a_whole_page_has(tmp_path, monkeypatch):
    """After an Apply the editor sends the features of the roads that changed (level_editor.Area.update), built by render's own code: for a
    cap, a head and a level change they are the features of those roads in the whole page built again (the roads, their simple-mode
    pieces, the slots when a fill number changed). More changed roads than PARTIAL_MAX: no update, the page reloads and says why."""
    pytest.importorskip("scipy")
    import pandas as pd

    from roadstyle import level_editor
    from roadstyle.level_area import make_area
    from roadstyle.level_editor import Area
    make_area(_edge_world(), tmp_path)
    area = Area(tmp_path)
    js = lambda x: json.loads(json.dumps(x, default=str))                                  # noqa: E731 - as the page gets them
    order = pd.DataFrame([{"relation": "order", "a": "12", "b": "11", "a_end": "", "b_end": "", "enabled": "false"}])
    for change in ([{"op": "cap", "road": "12", "end": "start", "cap": "square"}], [{"op": "head", "road": "12", "end": "end", "m": "12.5"}], order):
        levels = {r: f["levels"] for r, f in area.facts.items()}
        if isinstance(change, list):
            area.apply(change)
        else:
            area.change(change)
            assert {r for r, f in area.facts.items() if f["levels"] != levels[r]}            # the levels changed
        u = js(area.update)
        assert u["roads"] and u["features"]["simple"] and area.reload is None and set(u["facts"]) == set(u["roads"])
        src = _style_of(area.page)["sources"]
        idx = [f["id"] for f in u["features"]["roads"]]
        assert [f["properties"]["road"] for f in u["features"]["roads"]] == u["roads"]
        assert u["features"]["roads"] == [src["roads"]["data"]["features"][i] for i in idx]
        assert u["features"]["simple"] == [f for f in src["simple"]["data"]["features"] if f["properties"]["__rs_edge"] in idx]
        assert ("slots" in u["features"]) == (change is order) and u["features"].get("slots", src["slots"]["data"]["features"]) == src["slots"]["data"]["features"]
    monkeypatch.setattr(level_editor, "PARTIAL_MAX", 0)
    area.apply([{"op": "cap", "road": "12", "end": "start", "cap": ""}])
    assert area.update is None and area.reload == "1 roads changed, more than 0: the whole page again"


def test_the_editor_draws_and_updates_both_directions_of_a_road(tmp_path):
    """A two-way road in the level editor (2026-10-08): its two edges are one road (picked, found and shown by either: the card lists each
    direction's edge id and edge_ref), the map draws them as the final map does (one edge per direction: the pair's one casing, a fill
    each, the other direction running the road's line backwards with its heads and caps swapped), and the update in place after an Apply
    carries both edges and all their pieces, as the whole page has them."""
    pytest.importorskip("scipy")
    import pandas as pd
    from shapely import reverse

    from roadstyle.level_area import make_area
    from roadstyle.level_editor import Area
    g = _edge_world().assign(edge_ref=["11f", "12f", "14f", "13f"])
    back = g[g["edge_id"] == 12].assign(edge_id=22, edge_ref="12r")
    back = back.set_geometry(reverse(back.geometry.to_numpy()), crs=g.crs)
    make_area(gpd.GeoDataFrame(pd.concat([g, back], ignore_index=True), crs=g.crs), tmp_path)
    area = Area(tmp_path)
    f = area.facts["12"]
    assert f["two_way"] and f["directions"] == [{"edge": "12", "edge_ref": "12f", "way": "along"}, {"edge": "22", "edge_ref": "12r", "way": "against"}]
    assert [h["road"] for h in area.find("22")] == ["12"] and [h["road"] for h in area.find("12r")] == ["12"]
    js = lambda x: json.loads(json.dumps(x, default=str))                                  # noqa: E731 - as the page gets them
    area.apply([{"op": "cap", "road": "22", "end": "start", "cap": "square"}])             # by the other direction's id: the road's start
    assert area.facts["12"]["caps"] == ["square", ""]
    rows = area.draw[area.draw["road"] == "12"]
    assert rows["edge"].tolist() == ["12", "22"] and rows["cap_start"].tolist()[0] == rows["cap_end"].tolist()[1] == "square"
    assert list(rows.geometry.iloc[1].coords) == list(rows.geometry.iloc[0].coords)[::-1]
    u = js(area.update)
    assert u["roads"] == ["12"] and sorted(r["properties"]["edge"] for r in u["features"]["roads"]) == ["12", "22"]
    src = _style_of(area.page)["sources"]
    idx = [r["id"] for r in u["features"]["roads"]]
    assert u["features"]["simple"] == [x for x in src["simple"]["data"]["features"] if x["properties"]["__rs_edge"] in idx]
    kinds = sorted((src["roads"]["data"]["features"][x["properties"]["__rs_edge"]]["properties"]["edge"], x["properties"]["__rs_k"], bool(x["properties"].get("__rs_pair")))
                   for x in u["features"]["simple"] if not x["properties"].get("__rs_seam"))
    assert ("12", 1, False) in kinds and ("22", 1, False) in kinds                          # a fill each
    assert {k for k in kinds if k[1] != 1} and all(k[0] == "12" and k[2] for k in kinds if k[1] != 1)   # one casing, the first edge's


def test_the_editor_re_solves_only_the_roads_around_a_change():
    """level_area.solve_local (the editor's Apply): the roads around a change are solved again with the same rules, every other road keeps its
    numbers; a local result that breaks what the previous one kept is not used: the whole area is solved, and the result says so and why."""
    pytest.importorskip("scipy")
    import pandas as pd

    import roadstyle as rs
    from roadstyle.level_area import LEVELS, around, solve, solve_local
    roads, pairs = rs.level_input(_edge_world())       # ground 11 - tunnel 12 - ground 14 in a line, street 13 crossing over the tunnel's middle
    prev = solve(roads, pairs, None, {}, {})[0]
    assert around(roads, pairs, None, ["13"], 1) == {"13", "12"} and around(roads, pairs, None, ["13"], 2) == {"11", "12", "13", "14"}
    row = lambda **k: pd.DataFrame([{"relation": "stack", "a_end": p, "b_end": "", "enabled": "true", **k} for p in ("start", "main", "end")])   # noqa: E731
    off = pd.DataFrame([{"relation": "order", "a": "12", "b": "14", "a_end": "", "b_end": "", "enabled": "false"}])
    out = solve_local(roads, pairs, off, {}, {}, prev, ["12", "14"], hops=0)[0]
    lv = out.set_index("road")[LEVELS]
    assert out.attrs["levels_info"]["resolve"]["how"] == "local" and out.attrs["levels_info"]["resolve"]["free"] == 2
    was = prev.set_index("road")[LEVELS]
    assert (lv.loc[["11", "13"]] == was.loc[["11", "13"]]).all().all()                  # held exactly as they were (no shift of the whole)
    assert min(lv.loc["13"]) > lv.loc["12", "fill_level"] > lv.loc["11", "fill_level"]                  # the rules: 13 over 12, the wish 12 after 11
    out = solve_local(roads, pairs, row(a="11", b="13"), {}, {}, prev, ["11"], hops=0)[0]   # 11 over 13 with 13 held over the tunnel 11's head joins:
    r = out.attrs["levels_info"]["resolve"]                                                # locally a crossing given up: the whole area instead
    assert r["how"] == "full" and "given up that were kept" in r["why"]
    full = solve(roads, pairs, row(a="11", b="13"), {}, {})[0]
    assert (out[LEVELS] == full[LEVELS]).all().all() and out.attrs["levels_given_up"] == full.attrs["levels_given_up"]
    assert solve_local(roads, pairs, row(a="11", b="13"), {}, {}, prev, ["11"])[0].attrs["levels_info"]["resolve"]["why"] == "every road is around the change"


def test_a_local_re_solve_keeps_the_fixed_roads_numbers_exactly():
    """level_area._keep_fixed (2026-10-08): a local result shifted as a whole (the solver's ground moved) is shifted back so the fixed roads
    keep exactly their numbers, the free ones moving with them; fixed roads that moved by different amounts are an error."""
    pytest.importorskip("scipy")
    import roadstyle as rs
    from roadstyle.level_area import LEVELS, _keep_fixed, solve
    roads, pairs = rs.level_input(_edge_world())
    prev = solve(roads, pairs, None, {}, {})[0]
    was = prev.set_index("road")[LEVELS]
    fixed = {r: tuple(int(x) for x in was.loc[r]) for r in ("11", "13")}
    out = prev.copy()
    out[LEVELS] = out[LEVELS] + 2                                  # as if the ground moved by two
    _keep_fixed(out, fixed)
    assert (out.set_index("road")[LEVELS] == was).all().all()      # every road back, the free ones (12, 14) with them
    out.loc[out["road"] == "13", "fill_level"] += 1
    with pytest.raises(RuntimeError, match="different amounts"):
        _keep_fixed(out, fixed)


def test_edits_name_either_direction_of_a_road():
    """solve_levels: a meet edit naming the edge that runs against its road has its end turned to the road's way; a meet is the same pair in
    either order (switching one off works whichever road is named first)."""
    pytest.importorskip("scipy")
    import pandas as pd

    import roadstyle as rs
    a, b, c = (18.0, 59.3), (18.002, 59.3), (18.004, 59.3)
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "edge_id": [1, 2, 3]},
                         geometry=[LineString([a, b]), LineString([b, a]), LineString([b, c])], crs=4326)     # road 1 both ways, road 3 from its end
    roads, pairs = rs.level_input(g)
    assert list(roads["road"]) == ["1", "3"] and list(roads["reversed"].iloc[0]) == ["2"]
    off = pd.DataFrame([{"relation": "meet", "a": "3", "b": "2", "a_end": "start", "b_end": "start", "enabled": "false"}])     # edge 2's start = road 1's end
    rs.solve_levels(roads, pairs, edits=off)                    # found as (1 end, 3 start): switched off, no error
    with pytest.raises(ValueError):
        rs.solve_levels(roads, pairs, edits=off.assign(b_end="end"))   # edge 2's end is road 1's start: no such meet


def test_every_part_of_the_upper_casing_is_after_the_lower_fill():
    """2026-10-06 (Monaco 95449780#1f over 4229327#1f): A over B lifts the parts of A's casing that cross B, its heads too (2026-10-08: the
    stack rows of pairs.csv name them), and its fill, after B's fill. Before, only A's main part was: A's start head, held under the fill of
    the road it lands on, could sit under the fill of the street B passing under it close to A's start, and B's fill hid A's outline there."""
    pytest.importorskip("scipy")
    import pandas as pd

    import roadstyle as rs
    d = 0.0001                                                             # about 6 m east-west at 59.3
    g = gpd.GeoDataFrame({"highway": ["secondary"] * 3, "bridge": ["yes", None, None], "layer": [1, None, None], "edge_id": [1, 2, 3]},
                         geometry=[LineString([(18.0, 59.3), (18.0 + 3.5 * d, 59.3)]),                    # A: the bridge, about 20 m
                                   LineString([(18.0 + d / 2, 59.2998), (18.0 + d / 2, 59.3002)]),       # B: the street under it, 3 m from its start
                                   LineString([(18.0 - 2.5 * d, 59.3), (18.0, 59.3)])], crs=4326)         # J: the road A's start head lands on
    roads, pairs = rs.level_input(g)
    assert pairs.loc[pairs.relation == "stack", "a_end"].tolist() == ["start"]                          # the crossing is in A's start head
    held = pd.DataFrame([{"relation": "order", "a": "2", "b": "3", "enabled": "true"}])                  # B's fill after J's: J holds A's head low
    out = rs.solve_levels(roads, pairs, edits=held).set_index("road")
    assert out.loc["1", "casing_start"] > out.loc["2", "fill_level"]                                    # A's start head over B's fill
    assert out.loc["1", "fill_level"] > out.loc["2", "fill_level"]
    assert out.attrs["levels_given_up"] == []                                                           # the wish gave way, not the stack pair


def test_stack_edits_can_name_a_part_of_the_upper_road():
    """solve_levels: a stack edit's a_end names a part of A (start / main / end). Added, that casing part is after B's fill; switched off, that
    row of pairs.csv is left out; switching off a row that is not there is an error, and so is a stack with no part (2026-10-08)."""
    pytest.importorskip("scipy")
    import pandas as pd

    import roadstyle as rs
    g = _edge_world()                                  # ground 11 - tunnel 12 - ground 14 in a line, street 13 crossing over the tunnel's middle
    roads, pairs = rs.level_input(g)
    row = lambda **k: pd.DataFrame([{"relation": "stack", "a_end": "", "b_end": "", "enabled": "true", **k}])     # noqa: E731
    out = rs.solve_levels(roads, pairs, edits=row(a="11", b="14", a_end="start")).set_index("road")
    assert out.loc["11", "casing_start"] > out.loc["14", "fill_level"]                      # an added part: that head over B's fill
    out = rs.solve_levels(roads, pairs, edits=row(a="11", b="14", a_end="end")).set_index("road")
    assert out.loc["11", "casing_end"] > out.loc["14", "fill_level"]
    rs.solve_levels(roads, pairs, edits=row(a="13", b="12", a_end="main", enabled="false"))    # the found row 13 (main) over 12: switched off
    for bad in (row(a="13", b="12", a_end="start", enabled="false"),                            # no such row (13's start head does not cross 12)
                row(a="11", b="14", a_end="start", enabled="false"), row(a="11", b="14", a_end="middle"), row(a="11", b="14")):   # no part: no whole road
        with pytest.raises(ValueError):
            rs.solve_levels(roads, pairs, edits=bad)


def test_cap_start_and_end_cols_set_one_end_each():
    """cap_start_col / cap_end_col (docs/design/square_ends.md): an edge whose two ends differ is left out of the whole-edge fill layers and
    drawn as two fill halves (source "halves"), each with its end's cap, and its casing heads take their end's cap; equal ends stay one
    edge; without level columns too (render_edges computes them)."""
    g = gpd.GeoDataFrame({"highway": ["residential"] * 2, "cl": [0, 0], "fl": [0, 0], "s": ["flat", "square"], "e": [None, "square"]},
                         geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(2)], crs=4326)
    kw = dict(casing_level_col="cl", fill_level_col="fl", cap_start_col="s", cap_end_col="e")
    style = _style(render_edges(g, backend="web", **kw, simple=False).html)
    lay = {l["id"]: l for l in style["layers"]}
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert ps[0].get("__rs_split") and ps[1].get("__rs_cap") == "square"                       # flat / round differ; square / square: one edge
    halves = [f["properties"] for f in style["sources"]["halves"]["data"]["features"]]
    assert [h.get("__rs_cap") for h in halves] == [True, None]                                   # start half flat, end half round
    assert [h["__rs_edge"] for h in halves] == [0, 0]                                            # its edge's id, for the recolouring
    assert style["sources"]["halves"]["tolerance"] == style["sources"]["casings"]["tolerance"] == style["sources"]["roads"]["tolerance"]   # one line
    assert [bool(_eval(lay["roads-fill"]["filter"], p)) for p in ps] == [True, False]            # the split edge stays in its fill layer,
    assert [_eval(lay["roads-fill"]["paint"]["line-opacity"], p) for p in ps[:1]] == [0]          # transparent (clicks find the edge), the halves paint it
    assert [bool(_eval(lay["roads-fill-sx"]["filter"], p)) for p in ps] == [False, True]
    assert [[bool(_eval(lay[i]["filter"], h)) for h in halves] for i in ("roads-fill-hsq", "roads-fill-h")] == [[True, False], [False, True]]
    assert lay["roads-fill-hsq"]["layout"]["line-cap"] == "butt" and lay["roads-fill-h"]["source"] == "halves"
    heads = [f["properties"] for f in style["sources"]["casings"]["data"]["features"] if f["properties"]["__rs_edge"] == 0 and not f["properties"].get("__rs_seam")]
    assert [h.get("__rs_cap") for h in heads] == [True, True, None]                              # start head flat, main flat (cut), end head round
    auto = _style(render_edges(g.drop(columns=["cl", "fl"]), backend="web", cap_start_col="s", cap_end_col="e", simple=False).html)     # levels computed here
    assert len(auto["sources"]["halves"]["data"]["features"]) == 2


def test_head_metre_cols_set_where_the_casing_is_cut():
    """head_start_m_col / head_end_m_col: an edge's own head lengths (null = head_m); a road shorter than its two heads is cut in their ratio."""
    import numpy as np
    m = 1 / 111320.0                                                                     # a degree of latitude in metres, near enough
    g = gpd.GeoDataFrame({"highway": ["residential"] * 2, "cs": [-1, -1], "cl": [0, 0], "ce": [-1, -1], "fl": [0, 0], "hs": [20.0, 9.0], "he": [None, 3.0]},
                         geometry=[LineString([(18.0, 59.30), (18.0, 59.30 + 100 * m)]), LineString([(18.01, 59.30), (18.01, 59.30 + 8 * m)])], crs=4326)
    style = _style(render_edges(g, backend="web", casing_start_col="cs", casing_level_col="cl", casing_end_col="ce", fill_level_col="fl",
                                head_start_m_col="hs", head_end_m_col="he", simple=False).html)
    def lengths(road):
        out = []
        for f in (f for f in style["sources"]["casings"]["data"]["features"] if not f["properties"].get("__rs_seam")):
            if f["properties"]["__rs_edge"] == road:
                c = np.asarray(f["geometry"]["coordinates"])
                out.append(round(float(np.abs(np.diff(c[:, 1])).sum() / m), 1))
        return out
    assert lengths(0) == [20.0, 75.0, 5.0]                                                # 20 m start head, the default 5 m end head
    assert lengths(1) == [6.0, 2.0]                                                       # 8 m < 9 + 3: cut 3 : 1


def test_near_rules_give_way_to_order_wishes_and_real_crossings_do_not():
    """A stack rule on a part that only comes near the lower road is kept last (after the order wishes) and reported as a warning, not a
    given-up pair; the same rule on a crossing part is kept before the wishes (docs/design/level_input.md)."""
    pytest.importorskip("scipy")
    from roadstyle.levels import _solve_intervals
    parts = [(0, 1, h) for h in "sme"]                                  # road 0 over road 1, but a wish: road 1's fill after road 0's
    _, given, info = _solve_intervals(["0", "1"], [], [], [(1, 0)], 30, 20, 1.0, near=parts)
    assert given == [] and info["order_violations"] == 0 and len(info["near_parts"]) == 3     # the near rule gives way: a warning
    _, given, info = _solve_intervals(["0", "1"], [], parts, [(1, 0)], 30, 20, 1.0)
    assert given == [] and info["order_violations"] == 1                                          # a real crossing is kept, the wish is not
    assert info["orders_not_kept"] == [(1, 0)]                                                     # which wish: road 1's fill after road 0's


def test_auto_ends_fit_heads_and_caps_to_the_joins():
    """rs.auto_ends (docs/design/level_input.md): a head reaches as far as the drawings overlap (a right angle: about the two half widths;
    a narrow merge: longer), a dead end has the least; a wide road ending on a narrower one gets a flat end, others round."""
    import math

    import pandas as pd

    import roadstyle as rs
    m = 1 / 111320.0
    k = 1 / (111320.0 * math.cos(math.radians(59.3)))
    o = (18.0, 59.3)
    P = lambda x, y: (o[0] + x * k, o[1] + y * m)                                  # noqa: E731  metres east / north of o
    g = gpd.GeoDataFrame({"highway": ["residential", "residential", "primary", "residential"], "edge_id": [1, 2, 3, 4]},
                         geometry=[LineString([P(-60, 0), P(0, 0)]), LineString([P(0, 0), P(60, 0)]),       # a straight street in two pieces
                                   LineString([P(0, 60), P(0, 0)]),                                         # a primary ending on it, square on
                                   LineString([P(60, 0), P(120, 12)])], crs=4326)                          # the street going on, a bend
    g = pd.concat([g, gpd.GeoDataFrame({"highway": ["primary"], "edge_id": [5]}, geometry=[LineString([P(-40, -8), P(-60, 0)])], crs=4326)])
    roads, pairs = rs.level_input(g.reset_index(drop=True))
    e = rs.auto_ends(roads, pairs).set_index("road")
    assert 2.5 < e.loc["3", "end_m"] < 6 and e.loc["3", "start_m"] == 0.5          # a right angle: about the two half widths; a dead end: the least
    assert e.loc["5", "end_m"] > e.loc["3", "end_m"]                               # a narrow merge (about 22°) overlaps for longer
    assert e.loc["5", "cap_end"] == "flat" and e.loc["3", "cap_end"] == "flat"     # a primary ending on a narrower street: its round end spills over
    assert e.loc["1", "cap_start"] == "round" and e.loc["4", "cap_start"] == "round"  # a dead end, the street going on round a bend: round


def test_two_way_dead_end_is_square_by_default():
    """A two-way road's end that meets no road is square (one casing around both directions: two half round ends left a notch); a one-way
    road's dead end is round, a two-way end that meets a road keeps the rule, and your own cap (caps.csv) wins."""
    import pandas as pd

    import roadstyle as rs
    from roadstyle.level_area import defaults, ends
    P = lambda x, y: (674000 + x, 6580000 + y)                                         # noqa: E731
    line = lambda *p: LineString([P(*q) for q in p])                                   # noqa: E731
    g = gpd.GeoDataFrame({"highway": ["residential"] * 5, "edge_id": [1, 2, 3, 4, 5]},
                         geometry=[line((0, 0), (60, 0)), line((60, 0), (0, 0)),       # a two-way street: dead end at x=0, meets road 3 at x=60
                                   line((60, 0), (120, 0)),                            # one-way, going on: its far end is a dead end
                                   line((0, 50), (60, 50)), line((60, 50), (0, 50))], crs=3006)   # a two-way street meeting nothing
    roads, pairs = rs.level_input(g)
    d = defaults(roads, pairs).set_index("road")
    two = roads.set_index("road")
    two_way = [r for r in two.index if len(two.loc[r, "reversed"])]
    one_way = [r for r in two.index if not len(two.loc[r, "reversed"])]
    assert len(two_way) == 2 and len(one_way) == 1
    met = {r for r in two_way if (pairs[["a", "b"]] == r).any(axis=None)}
    assert len(met) == 1
    for r in two_way:
        a, b = d.loc[r, "cap_start"], d.loc[r, "cap_end"]
        assert sorted([a, b]) == (["round", "square"] if r in met else ["square", "square"])    # the end that meets road 3 keeps round
    assert d.loc[one_way[0], ["cap_start", "cap_end"]].tolist() == ["round", "round"]
    assert (rs.auto_ends(roads, pairs).set_index("road").loc[two_way, ["cap_start", "cap_end"]] == d.loc[two_way, ["cap_start", "cap_end"]]).all(axis=None)
    r = [x for x in two_way if x not in met][0]
    assert ends(d.reset_index(), {}, {r: ("round", "")}).set_index("road").loc[r, ["cap_start", "cap_end"]].tolist() == ["round", "square"]


def test_heads_over_the_whole_road_leave_no_main_part():
    """casing_parts: heads that cover the road (to within 5 cm, as the editor's "no main part" sets them) leave no main part."""
    import pandas as pd

    import roadstyle as rs
    g = gpd.GeoDataFrame({"highway": ["residential"], "edge_id": [1]}, geometry=[LineString([(674000, 6580000), (674010, 6580000)])], crs=3006)
    roads, _ = rs.level_input(g)
    heads = lambda s, e: pd.DataFrame([{"road": "1", "start_m": s, "end_m": e}])          # noqa: E731
    assert rs.casing_parts(roads, 5.0, heads("6", "3.97"))["1"][1] is None
    assert rs.casing_parts(roads, 5.0, heads("6", "3.8"))["1"][1] is not None



def test_near_rules_are_off_by_default():
    """2026-10-08: a part that only comes near is no row of pairs.csv; level_input(near_rules=True) writes it as a near row, lifted last."""
    pytest.importorskip("scipy")
    import roadstyle as rs
    P = lambda x, y: (674000 + x, 6580000 + y)                                         # noqa: E731
    g = gpd.GeoDataFrame({"highway": ["residential"] * 2, "bridge": ["yes", None], "layer": [1, None], "edge_id": [1, 2]},
                         geometry=[LineString([P(0, 0), P(60, 0)]), LineString([P(0, 5), P(60, 5)])], crs=3006)   # a bridge beside a street, 5 m apart
    _, pairs = rs.level_input(g)
    assert not pairs["relation"].isin(["stack", "near"]).any()
    roads, pairs = rs.level_input(g, near_rules=True)
    assert sorted(pairs.loc[pairs.relation == "near", "a_end"]) == ["end", "main", "start"]
    assert rs.solve_levels(roads, pairs).attrs["levels_near"] == []                    # kept: nothing against them


def test_a_stack_of_yours_is_never_only_near_and_wishes_let_go_are_named():
    """solve_levels (2026-10-06): a stack edit counts as a real crossing even where the two roads only come near (the found ones are
    "near" there, kept last), so it wins over an order wish; the wishes the solver let go are in attrs["levels_orders_not_kept"]."""
    pytest.importorskip("scipy")
    import pandas as pd

    import roadstyle as rs
    P = lambda x, y: (674000 + x, 6580000 + y)                                         # noqa: E731
    g = gpd.GeoDataFrame({"highway": ["residential"] * 2, "edge_id": [1, 2]},
                         geometry=[LineString([P(0, 0), P(60, 0)]), LineString([P(0, 5), P(60, 5)])], crs=3006)   # side by side, 5 m apart
    roads, pairs = rs.level_input(g)
    row = lambda **k: {"a_end": "", "b_end": "", "enabled": "true", **k}               # noqa: E731
    edits = pd.DataFrame([row(relation="stack", a="1", b="2", a_end="main"), row(relation="order", a="2", b="1")])   # 1 over 2, but wish 2's fill after 1's
    out = rs.solve_levels(roads, pairs, edits=edits)
    assert out.attrs["levels_near"] == [] and out.attrs["levels_given_up"] == []
    assert out.set_index("road").loc["1", "fill_level"] > out.set_index("road").loc["2", "fill_level"]   # your stack won
    assert out.attrs["levels_orders_not_kept"] == [("2", "1")]                                          # and the wish it beat is named


def test_a_divided_casing_has_a_round_seam_at_each_cut():
    """_casing_parts (2026-10-06): at each cut inside an edge a tiny round piece of casing at the lower of the two pieces' numbers, so two
    pieces ending flat at a cut on a curve leave no wedge open in the outline."""
    m = 1 / 111320.0
    g = gpd.GeoDataFrame({"highway": ["primary"], "cs": [-1], "cl": [1], "ce": [0], "fl": [1], "cap": ["flat"]},
                         geometry=[LineString([(18.0, 59.3), (18.0, 59.3 + 50 * m), (18.0 + 0.001, 59.3 + 90 * m)])], crs=4326)
    style = _style(render_edges(g, backend="web", casing_start_col="cs", casing_level_col="cl", casing_end_col="ce", fill_level_col="fl",
                                cap_col="cap", simple=False).html)
    pieces = [f["properties"] for f in style["sources"]["casings"]["data"]["features"]]
    seams = [p for p in pieces if p.get("__rs_seam") and not p.get("__rs_lap")]                           # (the laps: test_a_lap_closes_the_cut_below_zoom_17)
    assert sorted(p["__rs_cl"] for p in seams) == [-1, 0] and all("__rs_cap" not in p for p in seams)     # round, at the lower number
    assert sorted(p["__rs_cl"] for p in pieces if not p.get("__rs_seam")) == [-1, 0, 1]
    lay = {l["id"]: l for l in style["layers"]}
    assert '["zoom"], 17' in json.dumps(lay["roads-casing"]["filter"]).replace(" ", "").replace(",", ", ")   # seams only from zoom 17: no bump on a flat end below


def test_a_bridge_shadow_is_at_each_parts_casing_number(monkeypatch):
    """Position mode (2026-10-06): the bridge shadow is an extra casing: each part of the bridge (start head, main part, end head) at its
    own casing number, the parts at one number joined into one line, lines meeting end to end (flat ends); none over the last 3 m where the
    bridge comes down; blurred and shifted down-right (lit from the top left), just before the bridge's casing at that position; off with
    bridge_shadow."""
    import dataclasses

    from roadstyle import render_web
    m = 1 / 111320.0
    pts = [(18.0, 59.3 + k * 20 * m) for k in range(4)]                                       # a bridge of three 20 m edges, then a street
    g = gpd.GeoDataFrame({"highway": ["primary"] * 4, "bridge": ["yes", "yes", "yes", None], "cs": [1, 2, 2, 0], "cm": [2, 3, 2, 0],
                          "ce": [2, 2, 1, 0], "fl": [2, 3, 2, 0]},
                         geometry=[LineString([pts[k], pts[k + 1]]) for k in range(3)] + [LineString([pts[3], (18.0, 59.3 + 90 * m)])], crs=4326)
    kw = dict(backend="web", casing_start_col="cs", casing_level_col="cm", casing_end_col="ce", fill_level_col="fl")
    style = _style(render_edges(g, **kw, simple=False).html)
    sh = style["sources"]["shadows"]["data"]["features"]
    span = lambda f: round((max(c[1] for c in f["geometry"]["coordinates"]) - min(c[1] for c in f["geometry"]["coordinates"])) / m)   # noqa: E731
    assert sorted((f["properties"]["__rs_cl"], span(f)) for f in sh) == [(1, 2), (1, 2), (2, 20), (2, 20), (3, 10)]   # each part at its own number:
    #   start heads 3-5 m (1), 5-25 m (2), the middle main part 25-35 m (3), 35-55 m (2), the end head 55-57 m (1); 3 m off each end
    lay = {l["id"]: l for l in style["layers"]}
    ids = [l["id"] for l in style["layers"]]
    s2 = lay["roads-casing-lv2-bridge-shadow"]
    assert s2["source"] == "shadows" and s2["paint"]["line-blur"] == 4.0 and s2["paint"]["line-translate"] == [2, 2]
    assert s2["layout"]["line-cap"] == "butt"                                                  # lines meet end to end: no darker disc
    assert ids.index("roads-casing-lv2-bridge-shadow") < ids.index("roads-casing-lv2-bridge") < ids.index("roads-fill-lv2")

    monkeypatch.setattr(render_web, "CONFIG", dataclasses.replace(render_web.CONFIG, bridge_shadow=False))
    off = _style(render_edges(g, **kw, simple=False).html)
    assert "shadows" not in off["sources"] and not [l for l in off["layers"] if l["id"].endswith("-shadow")]


def test_hiding_the_bridges_hides_their_shadow(tmp_path):
    """rsSetBridges(false) hides the bridge shadows with the bridges (2026-10-06: the shadow stayed, its lines carry no lvl)."""
    pw = pytest.importorskip("playwright.sync_api")
    m = 1 / 111320.0
    g = gpd.GeoDataFrame({"highway": ["primary"] * 2, "bridge": ["yes", None], "layer": [1, None]},
                         geometry=[LineString([(18.0, 59.3), (18.0, 59.3 + 60 * m)]), LineString([(18.0, 59.3 + 60 * m), (18.0, 59.3 + 90 * m)])], crs=4326)
    path = tmp_path / "bridge.html"
    render_edges(g, backend="web", basemap="blank", simple=False).save(path)
    shown = """() => map.getStyle().layers.filter(l => l.source === "shadows")
                 .map(l => map.queryRenderedFeatures({layers: [l.id]}).length).reduce((a, b) => a + b, 0)"""
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded()", timeout=30_000)
        on = page.evaluate(shown)
        page.evaluate("rsSetBridges(false)")
        page.wait_for_function("map.loaded()")
        off = page.evaluate(shown)
        page.evaluate("rsSetBridges(true)")
        page.wait_for_function("map.loaded()")
        back = page.evaluate(shown)
        browser.close()
    assert on > 0 and off == 0 and back == on


def test_a_branching_bridge_shadow_is_cut_only_at_the_bridge_ends():
    """_bridge_shadows (2026-10-06): where bridge edges branch the lines meet with no cut; only where the bridge comes down is it cut."""
    from roadstyle import render_web as rw
    m = 1 / 111320.0
    o = (18.0, 59.3)
    P = lambda x, y: (o[0] + x * m * 2, o[1] + y * m)                                    # noqa: E731  (about metres at 60 N)
    g = gpd.GeoDataFrame({"highway": ["primary"] * 3, "bridge": ["yes"] * 3},
                         geometry=[LineString([P(0, 0), P(0, 50)]), LineString([P(0, 50), P(0, 100)]), LineString([P(0, 50), P(40, 80)])], crs=4326)
    geo = rw.fc_dict(g)
    rw._mark_lvl(geo, "tunnel", "bridge", "layer")
    for ft in geo["features"]:
        ft["properties"]["__rs_cl"] = ft["properties"]["__rs_fl"] = 1
    sh = rw._bridge_shadows(geo, None, "highway", 5.0)
    pts = {tuple(round(v, 7) for v in c) for s in sh for c in s["geometry"]["coordinates"]}
    assert tuple(round(v, 7) for v in P(0, 50)) in pts                                    # the branch point is reached: no gap there
    assert tuple(round(v, 7) for v in P(0, 0)) not in pts and tuple(round(v, 7) for v in P(0, 100)) not in pts   # the real ends are cut
    h = gpd.GeoDataFrame({"highway": ["primary"] * 2, "bridge": ["yes"] * 2},                  # one edge that another one joins in its middle:
                         geometry=[LineString([P(0, 0), P(0, 100)]), LineString([P(0, 30), P(40, 60)])], crs=4326)   # both lines of it keep their shadow
    geo = rw.fc_dict(h)
    rw._mark_lvl(geo, "tunnel", "bridge", "layer")
    for ft in geo["features"]:
        ft["properties"]["__rs_cl"] = ft["properties"]["__rs_fl"] = 1
    import shapely
    sh = shapely.unary_union([shapely.LineString(s["geometry"]["coordinates"]) for s in rw._bridge_shadows(geo, None, "highway", 5.0)])
    assert sh.intersection(shapely.LineString([P(0, 0), P(0, 100)]).buffer(1e-9)).length / (100 * m) > 0.89   # all but the two 5 m ends


def test_bridge_shadow_goes_straight_through_a_junction_and_each_line_keeps_its_own_number():
    """_bridge_shadows (2026-10-06): where three bridge edges meet, the two going on straight are one line; the third is its own line,
    at the lowest casing number of its own edges (not of the whole connected bridge: a bridge crossing over a lower bridge it is joined to
    casts its shadow on it)."""
    from roadstyle import render_web as rw
    m = 1 / 111320.0
    P = lambda x, y: (18.0 + x * m * 2, 59.3 + y * m)                                    # noqa: E731  about metres at 60 N
    g = gpd.GeoDataFrame({"highway": ["primary"] * 3, "bridge": ["yes"] * 3, "edge_id": [1, 2, 3]},
                         geometry=[LineString([P(0, 0), P(0, 50)]), LineString([P(0, 50), P(0, 100)]), LineString([P(0, 50), P(60, 50)])], crs=4326)
    geo = rw.fc_dict(g)
    rw._mark_lvl(geo, "tunnel", "bridge", "layer")
    for ft, n in zip(geo["features"], (1, 1, 3), strict=True):
        ft["properties"].update({"__rs_cs": n, "__rs_cl": n, "__rs_ce": n, "__rs_fl": n})
    sh = rw._bridge_shadows(geo, None, "highway", 5.0)
    by = sorted((f["properties"]["__rs_cl"], len(f["geometry"]["coordinates"])) for f in sh)
    assert [lv for lv, _ in by] == [1, 3]                                                 # two lines: the straight one through the junction, the branch
    straight = next(f for f in sh if f["properties"]["__rs_cl"] == 1)
    ys = [c[1] for c in straight["geometry"]["coordinates"]]
    assert abs((max(ys) - min(ys)) / m - 90) < 0.5                                         # 0-100 m, less the 5 m passed in at each end where it comes down


def test_street_names_fit_their_road_and_tiny_ones_are_left_out():
    """Street names (2026-10-07): 9/10 of the road's fill width, at most the old 10 -> 14 px; none where that is under 8 px."""
    from roadstyle import render_web as rw
    assert rw._label_px("primary", 18) == 14.0                                             # a wide road: as before
    assert abs(rw._label_px("residential", 17) - 0.9 * rw.class_width_px("residential", 17, casing=False)) < 1e-9 < rw._label_px("residential", 17) - 8
    assert rw._label_px("service", 18) < 8                                                 # 5 px wide: no name at z18
    style = _style(render_edges(_edges(), backend="web").html)
    lab = next(l for l in style["layers"] if l["id"].startswith("roads-labels"))
    assert lab["layout"]["text-size"][0] == "interpolate" and lab["layout"]["text-size"][4][0] == "match"
    first = dict(zip(*[iter(rw._label_readable_filter()[2][2:-1])] * 2, strict=True))
    assert first["residential"] == 17 and first["tertiary"] == 17 and first["secondary"] == 16 and first["service"] > 18 and first["primary"] <= 15
    assert json.dumps(rw._label_readable_filter()) in json.dumps(lab["filter"])


def test_a_bridge_shadow_is_not_on_its_own_road_at_a_joint():
    """2026-10-06 ("shadow on its own road"): at a joint with a lower piece of the bridge, the shadow of the higher piece's head is at the
    head's number, at or under the lower piece's fill; the main part, over what it crosses, keeps its own higher number."""
    m = 1 / 111320.0
    P = lambda x, y: (18.0 + x * m * 2, 59.3 + y * m)                                    # noqa: E731  about metres at 60 N
    g = gpd.GeoDataFrame({"highway": ["primary"] * 2, "bridge": ["yes"] * 2, "cs": [2, 1], "cl": [2, 1], "ce": [1, 1], "fl": [2, 1]},
                         geometry=[LineString([P(0, 0), P(0, 50)]), LineString([P(0, 50), P(0, 100)])], crs=4326)   # A (high), then B (low)
    style = _style(render_edges(g, backend="web", casing_start_col="cs", casing_level_col="cl", casing_end_col="ce", fill_level_col="fl", simple=False).html)
    sh = style["sources"]["shadows"]["data"]["features"]
    ys = lambda f: sorted(round((c[1] - 59.3) / m) for c in f["geometry"]["coordinates"])               # noqa: E731
    by = sorted((f["properties"]["__rs_cl"], ys(f)[0], ys(f)[-1]) for f in sh)
    assert by == [(1, 45, 97), (2, 3, 45)]                                                    # A's end head joins B's shadow at 1, under B's fill


def test_one_arrow_per_one_way_road_in_the_window(tmp_path):
    """docs/design/arrows_and_names.md (2026-10-06): a one-way road in the window has one arrow, in its visible part; the arrow stays
    where it is while it is in the window (a small pan keeps it), and a road whose arrow left the window gets one again. None below zoom 15."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "arrows.html"
    pts = [(18.0 + i * 0.001, 59.3) for i in range(41)]                       # one straight one-way street, about 2.3 km, many slots
    g = gpd.GeoDataFrame({"highway": ["primary"], "name": ["Long St"], "oneway": [True]}, geometry=[LineString(pts)], crs=4326)
    render_edges(g, backend="web", basemap="blank").save(path)
    arrows = "map.getSource('arrows')._data.geojson.features.map(f => f.geometry.coordinates)"
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
        odd = page.evaluate("map.getSource('arrows')._data.geojson.features.map(f => f.properties.slot % 2)")
        nudged = at(18.0203, 16)
        moved = at(18.035, 16)
        browser.close()
    assert errors == [] and far == []
    assert len(first) == 1 and abs(first[0][0] - 18.02) < 0.004                 # one arrow, in the middle of what is seen
    assert odd == [1]                                                             # on an odd slot: between two street names
    assert nudged == first                                                        # a small pan keeps it
    assert len(moved) == 1 and moved != first                                     # its old place left the window: a new one


def test_arrows_are_thinned(tmp_path):
    """docs/design/arrows_and_names.md, thinning (2026-10-06): below zoom 17 only the main classes get an arrow; arrows stay 150 px
    apart (two parallel one-way roads a few metres apart show one)."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "thin.html"
    row = lambda y: [(18.0 + i * 0.001, y) for i in range(41)]                 # noqa: E731
    g = gpd.GeoDataFrame({"highway": ["residential", "primary", "primary"], "name": ["Side", "Main N", "Main S"], "oneway": [True] * 3},
                         geometry=[LineString(row(59.31)), LineString(row(59.3)), LineString(row(59.30005))], crs=4326)
    render_edges(g, backend="web", basemap="blank").save(path)
    names = "map.getSource('arrows')._data.geojson.features.map(f => f.properties.name).sort()"
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


def test_an_arrow_that_would_touch_a_name_is_left_out():
    """docs/design/arrows_and_names.md (2026-10-06): the page's arrows collide with the names (placed first, a later layer) and are
    dropped where they would touch one; they never push a name away."""
    g = gpd.GeoDataFrame({"highway": ["primary"], "name": ["Long St"], "oneway": [True]},
                         geometry=[LineString([(18.0, 59.3), (18.01, 59.3)])], crs=4326)
    style = _style(render_edges(g, backend="web", basemap="blank").html)
    arrows = [l for l in style["layers"] if l["id"].startswith("roads-arrows")]
    assert arrows and all(l["layout"]["icon-allow-overlap"] is False and l["layout"]["icon-ignore-placement"] is True for l in arrows)
    ids = [l["id"] for l in style["layers"]]
    assert ids.index("roads-arrows") < ids.index("roads-labels")                      # names placed first


def test_every_piece_of_a_road_names_its_edge():
    """docs/design/edge_items.md step 1: every feature of every source that draws a road (all but base maps, overlays and the boundary, so a
    source added later without the label fails here) carries ``__rs_edge``, the index of its edge in ``roads`` (``__rs_edge2`` too for a
    two-way pair's shared pieces); the shadow lines and 3D decks carry ``__rs_edges``, the list of their edges. Step 2: an item attached with
    ``Overlay(edge_col=...)`` carries ``__rs_edge`` too, the index of the road whose ``edge_id_col`` is its ``edge_col``, and that road's class and level.
    And every piece carries ``__rs_cls``, the class the class filter reads: its road's ``filter_col`` value (a name or an arrow slot carries the
    chain's ``highway``, not ``filter_col``); shadows and decks, which cover several edges, are decided per edge in the page."""
    from shapely.geometry import Point
    ln = lambda *c: LineString(c)                                                       # noqa: E731
    g = gpd.GeoDataFrame(
        {"highway": ["residential"] * 2 + ["primary"] * 4, "name": ["Main", "Main", "Side", "Bridge", "Bridge", "Bridge"],
         "oneway": [False, False, True, False, False, True],
         "cs": [0, 0, -1, 0, 0, 0], "cl": [0, 0, 0, 1, 1, 1], "ce": [0, 0, -2, 0, 0, 0], "fl": [0] * 3 + [1] * 3,
         "capa": [None, None, "flat", None, None, None], "capb": [None, None, "square", None, None, None],
         "bridge": [None, None, None, "yes", "yes", "yes"], "edge_id": [50, 51, 52, 53, 54, 55], "fc": ["A", "A", "B", "C", "C", "D"]},
        geometry=[ln((18.000, 59.300), (18.004, 59.300)), ln((18.004, 59.300), (18.000, 59.300)),            # a two-way street (two twins)
                  ln((18.004, 59.300), (18.004, 59.304)),                                                    # a one-way street with two different end caps
                  ln((18.010, 59.300), (18.012, 59.300)), ln((18.012, 59.300), (18.010, 59.300)),            # a two-way bridge
                  ln((18.012, 59.300), (18.014, 59.300))], crs=4326)                                         # a one-way bridge going on from it
    kw = dict(backend="web", arrows=True, labels=True, view_3d=True, casing_start_col="cs", casing_level_col="cl", casing_end_col="ce",
              fill_level_col="fl", cap_start_col="capa", cap_end_col="capb", bridge_col="bridge", filter_col="fc",
              overlays=[Overlay(gpd.GeoDataFrame({"edge_id": [55, 50, 52], "highway": ["crossing"] * 3},       # its own highway is not its road's class
                                                 geometry=[Point(18.013, 59.3), Point(18.001, 59.3), Point(18.004, 59.302)], crs=4326),
                                edge_col="edge_id", kind="circle", label="items")])
    seen = set()
    for extra in ({}, {"tiles": False}):
        style = _style(render_edges(g, **kw, **extra, simple=False, settings={"config": {"twin_casing": "each"}}).html)
        n = len(style["sources"]["roads"]["data"]["features"])
        assert all(f["properties"]["__rs_edge"] == i for i, f in enumerate(style["sources"]["roads"]["data"]["features"]))      # the generateId index
        roads = style["sources"]["roads"]["data"]["features"]
        assert all(f["properties"]["__rs_cls"] == f["properties"]["fc"] for f in roads)
        for name, src in style["sources"].items():
            if name == "ov0":                                                            # the attached items
                roads = style["sources"]["roads"]["data"]["features"]
                for f in src["data"]["features"]:
                    p, r = f["properties"], roads[f["properties"]["__rs_edge"]]["properties"]
                    assert (r["edge_id"], r["fc"], r["lvl"]) == (p["edge_id"], p["__rs_cls"], p["__rs_lvl"]), p
                seen.add(name)
            if src["type"] != "geojson" or name in ("boundary", "roads", "arrows") or name.startswith("ov"):     # arrows: filled by the page
                continue
            feats = src["data"]["features"]
            assert feats, name
            seen.add(name)
            for f in feats:
                p = f["properties"]
                if name in ("shadows", "decks"):
                    assert p["__rs_edges"] and all(isinstance(e, int) and 0 <= e < n for e in p["__rs_edges"]), (name, p)
                else:
                    assert isinstance(p["__rs_edge"], int) and 0 <= p["__rs_edge"] < n, (name, p)
                    assert p["__rs_cls"] == roads[p["__rs_edge"]]["properties"]["fc"], (name, p)
                    if "__rs_edge2" in p:
                        assert isinstance(p["__rs_edge2"], int) and 0 <= p["__rs_edge2"] < n, (name, p)
    assert all("__rs_edge2" in f["properties"] for f in style["sources"]["ends"]["data"]["features"])       # a cap belongs to both twins
    assert {"casings", "halves", "ends", "slots", "shadows", "decks", "ov0"} <= seen           # the page really had every kind of piece


def _at_zoom(e, z):
    return z if e == ["zoom"] else [_at_zoom(x, z) for x in e] if isinstance(e, list) else e


@pytest.mark.parametrize("make", [
    lambda: render_edges(_edges().assign(bridge=["yes", None, None], oneway=[1, 0, 1]), backend="web", simple=False, arrows=True, labels=True),
    lambda: render_edges(_edge_world(), backend="web", simple=False, minzoom=True),
    lambda: render_edges(_edges().assign(bridge=["yes", None, None]), backend="web", simple=False, view_3d=True),
    lambda: render_edges(_edge_world(), backend="web", simple=False, tiles=True),
])
def test_a_page_has_no_road_layer_that_draws_nothing(monkeypatch, make):
    """A road layer is made only where some feature can be drawn by it (MapLibre walks every layer on every frame): a position without a
    bridge has no bridge layers, and every layer that draws a feature at some zoom is still there, in the same order."""
    from roadstyle import render_web as rw
    seen = []
    real = rw._drop_empty_layers
    monkeypatch.setattr(rw, "_drop_empty_layers", lambda layers, feats: seen.append((copy.deepcopy(layers), feats, copy.deepcopy(real(layers, feats)))) or real(layers, feats))
    make()
    full, feats, lean = seen[0]
    assert len(lean) < len(full)
    ids = [l["id"] for l in lean]
    assert [l["id"] for l in full if l["id"] in set(ids)] == ids                # the same order
    for l in full:                                                              # a layer that draws some feature at some zoom stays
        if l["id"].startswith("roads-") and l.get("filter") and l.get("source") in feats:
            draws = []
            for ft in feats[l["source"]]:
                for z in range(0, 25):
                    v = rw._ev(_at_zoom(l["filter"], z), ft.get("properties") or {})
                    assert v is not rw._MAYBE, (l["id"], l["filter"])         # every operator of the filters is read
                    draws.append(bool(v))
            assert any(draws) == (l["id"] in ids) or l["id"] == "roads-fill", l["id"]
    for l in lean:                                                              # a bridge layer only at a bridge's casing position
        if l["id"].startswith("roads-casing") and l["id"].endswith("-bridge"):
            pos = int(re.search(r"-lv(-?\d+)", l["id"]).group(1)) if "-lv" in l["id"] else 0
            assert any(ft["properties"].get("__rs_bridge") and (ft["properties"].get("__rs_cl") or 0) == pos for ft in feats[l["source"]]), l["id"]
    if any(ft["properties"].get("__rs_bridge") for ft in feats["roads"]):
        assert len([i for i in ids if i.endswith("-bridge")]) < len([l for l in full if l["id"].endswith("-bridge")])


def _simple_world():
    """Three roads with divided casings (as test_divided_casing_is_drawn_as_head_and_main_pieces), one a bridge, one a tunnel, one a footway (a dashed class)."""
    d = 0.001
    return gpd.GeoDataFrame({"highway": ["residential", "primary", "footway"], "bridge": [None, "yes", None], "tunnel": ["yes", None, None],
                             "cs": [-1, 0, 0], "cm": [0, 1, 0], "ce": [-2, 2, 0], "fl": [0, 2, 1]},
                            geometry=[LineString([(18, 59), (18 + d, 59)]), LineString([(18, 59.01), (18 + d, 59.01)]),
                                      LineString([(18, 59.02), (18 + d, 59.02)])], crs=4326)


def test_simple_draws_every_road_piece_in_one_layer_in_the_full_order():
    """simple=True: one road line layer (source "simple": the casing pieces as the full look cuts them, then the fills), a transparent roads-fill on the
    roads source for picking, the highlight, one arrow and one name layer; the line-sort-key is 2 * position (a bridge's casing + 0.25), a fill
    2 * position + 1 (a dashed class's - 0.5, before the casings, and no casing); every piece names its edge."""
    from roadstyle.render_web import _TIE
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0)
    full = _style(render_edges(_simple_world(), simple=False, **kw).html)
    html = render_edges(_simple_world(), **kw).html
    style = _style(html)
    lines = [l for l in style["layers"] if l["id"].startswith("roads-") and l["type"] == "line"]
    assert [l["id"] for l in lines] == ["roads-simple", "roads-fill", "roads-highlight"]
    assert lines[0]["source"] == "simple" and lines[0]["layout"]["line-sort-key"] == ["get", "__rs_s"] and lines[0]["layout"]["line-cap"][-1] == "round"
    assert lines[1]["paint"]["line-opacity"] == 0 and lines[1]["source"] == "roads"
    assert {"casings", "halves", "shadows", "ends"}.isdisjoint(style["sources"])
    feats = [f["properties"] for f in style["sources"]["simple"]["data"]["features"]]
    assert all("__rs_edge" in p and "__rs_cls" in p for p in feats)
    casings = [(p["__rs_edge"], p["__rs_cl"], p["__rs_s"]) for p in feats if p["__rs_k"] in (0, 3)]     # a tunnel's casing: its gap piece (3), the dashes (4) on top
    # the same pieces as the full look's casing source, seams too (a tunnel's casing is its dashes alone: no seam dots), the footway none
    full_pieces = [(p["__rs_edge"], p["__rs_cl"]) for p in (f["properties"] for f in full["sources"]["casings"]["data"]["features"])
                   if not (p.get("__rs_seam") and p["__rs_edge"] == 0) and p["__rs_edge"] != 2]
    assert [c[:2] for c in casings] == full_pieces
    assert [c[:2] for c in casings if c[0] == 0] == [(0, -1), (0, 0), (0, -2)] and {c[:2] for c in casings if c[0] == 1} == {(1, 0), (1, 1), (1, 2)}
    assert [c[2] for c in casings] == [2 * c[1] + (0.25 if c[0] == 1 else 0) + c[0] * _TIE for c in casings]     # + the edge's tie-breaker
    fills = [(p["__rs_edge"], p["__rs_s"]) for p in feats if p["__rs_k"] == 1]
    assert fills == [(0, 1), (1, 5 + _TIE), (2, 1.5 + 2 * _TIE)]
    assert all(max(c[2] for c in casings if c[0] == e) < s for e, s in fills if e != 2)      # an edge's fill over its own casing
    # the bridge's shadow: one copy of its main casing piece, just under it, with every piece's labels; blurred, wider than the casing
    shadows = [p for p in feats if p["__rs_k"] == 2]
    assert [(p["__rs_edge"], p["__rs_cl"], p["__rs_s"]) for p in shadows] == [(1, 1, 2.15 + _TIE)] and "__rs_cls" in shadows[0]
    paint = lines[0]["paint"]
    # both bridge additions grow with the zoom: none at 14 and below, full at 17 and above (zoom at the top, the cases inside)
    assert paint["line-blur"][:3] == ["interpolate", ["linear"], ["zoom"]] and paint["line-blur"][3:5] == [14, 0] and paint["line-blur"][5] == 17 and paint["line-blur"][6][0] == "case"
    op = paint["line-opacity"]
    assert op[:3] == ["interpolate", ["linear"], ["zoom"]] and op[3] == 14 and op[4][:3] == ["case", ["==", ["get", "__rs_k"], 2], 0] and op[5] == 17
    stops = dict(zip(paint["line-width"][3::2], paint["line-width"][4::2], strict=True))
    extra = lambda z: stops[z][4][2]                                # the bridge casing's extra px at a stop: (case, shadow cond, shadow, bridge cond, bridge, ...)
    assert extra(14) == 0.0 and extra(15) == 1.0 and extra(17) == 3.0 and extra(20) == 3.0
    assert paint["line-color"][1:3] == [["==", ["get", "__rs_k"], 2], "rgba(0,0,0,0.25)"]
    w = paint["line-width"][4]                                       # the first zoom stop: shadow, bridge casing, ... cases
    assert w[0] == "case" and w[1] == ["==", ["get", "__rs_k"], 2]
    assert "const RS_SIMPLE = " in html and "_applyFill=function" in html


def test_simple_tunnels_move_toward_the_chosen_tunnel_colour():
    """A tunnel in simple mode takes the tunnel look toward ``tunnel_toward`` at ``tunnel_strength`` from the start, as the full look
    (it moved toward slate until the page recoloured, 2026-10-08)."""
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0, simple=True)
    color = json.dumps(next(l for l in _style(render_edges(_simple_world(), **kw).html)["layers"] if l["id"] == "roads-simple")["paint"]["line-color"])
    assert '100, "#d6cfc4"' in color and '100, "#64748b"' not in color and "60.0" in color      # Sand at 60, the defaults (slate: only the bridge casing)
    navy = render_edges(_simple_world(), settings={"config": {"tunnel_toward": "Navy", "tunnel_strength": 75}}, **kw).html
    color = json.dumps(next(l for l in _style(navy)["layers"] if l["id"] == "roads-simple")["paint"]["line-color"])
    assert '"#1e293b"' in color and "75.0" in color


def test_simple_is_the_default_and_simple_false_is_the_full_look():
    """No ``simple=`` draws simple mode; simple=False is the full look, without the simple-mode script."""
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0)
    assert render_edges(_simple_world(), **kw).html == render_edges(_simple_world(), simple=True, **kw).html
    html = render_edges(_simple_world(), simple=False, **kw).html
    assert "RS_SIMPLE" not in html and "roads-simple" not in html


def test_simple_has_the_tunnels_box_with_the_palette_and_dash_selects():
    html = render_edges(_edge_world(), backend="web", basemap="blank", tunnel_control=True).html
    assert '"control": true' in html and "TUNNEL.simple" not in html and "rsSetTunnelStyle=function" in html


def test_simple_same_key_pieces_keep_their_order_after_an_update_in_place():
    """Two roads at one position have pieces with the same base key; MapLibre draws equal keys in feature order, and updateData puts a
    redrawn road's pieces last. The per-edge tie-breaker (2026-10-08) makes the order the same as in the whole page built again."""
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["residential", "residential"]},
                         geometry=[LineString([(18, 59), (18 + d, 59)]), LineString([(18 + d / 2, 58.999), (18 + d / 2, 59.001)])], crs=4326)
    order = lambda fs: [(f["properties"]["__rs_edge"], f["properties"]["__rs_k"]) for f in sorted(fs, key=lambda f: f["properties"]["__rs_s"])]  # noqa: E731 - stable, as MapLibre
    page = _style(render_edges(g, backend="web").html)["sources"]["simple"]["data"]["features"]
    new = render_edges(g, backend="web", _edges=[0])["simple"]                                          # road 0 redrawn in place:
    patched = [f for f in page if f["properties"]["__rs_edge"] != 0] + new                              # updateData puts it last
    assert len({f["properties"]["__rs_s"] for f in page}) == len(page) and order(patched) == order(page)
    with pytest.raises(ValueError, match="more than 1,000,000 edges"):
        from roadstyle.render_web import _simple_pieces
        _simple_pieces({"features": []}, [{"geometry": None, "properties": {"__rs_cl": 0, "__rs_cs": 0, "__rs_ce": 0, "__rs_edge": 1_000_000}}], ())


def test_simple_tunnel_casing_is_a_gap_piece_and_a_dash_piece():
    """A tunnel's casing in simple mode: a solid piece in the palette's gap colour, then a piece on top in the dash colour with the tunnel_casing_dash
    dasharray (butt ends), both 3 px wider than a casing, the dashes a little above the gap and under the fill; "One colour": a clear gap."""
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0)
    style = _style(render_edges(_simple_world(), settings={"config": {"tunnel_casing_dash": [2, 3]}}, **kw).html)
    feats = [f["properties"] for f in style["sources"]["simple"]["data"]["features"]]
    gap, dash = [p for p in feats if p["__rs_k"] == 3], [p for p in feats if p["__rs_k"] == 4]
    assert len(gap) == len(dash) == 3 and all(p["__rs_edge"] == 0 for p in gap + dash)            # the tunnel's three pieces (heads and main), no plain casing
    assert not [p for p in feats if p["__rs_k"] == 0 and p["__rs_edge"] == 0]
    assert [round(d["__rs_s"] - g["__rs_s"], 6) for g, d in zip(gap, dash, strict=True)] == [0.1] * 3 and all(d["__rs_s"] < 1 for d in dash)   # under the fill (key 1)
    layer = next(l for l in style["layers"] if l["id"] == "roads-simple")
    color = layer["paint"]["line-color"]
    from roadstyle import render_web as rw
    dash_c, gap_c = rw.CONFIG.tunnel_palettes["Graphite + silver"]
    gap_e, dash_e = (color[color.index(["==", ["get", "__rs_k"], k]) + 1] for k in (3, 4))
    assert gap_e[0] == "interpolate" and gap_e[4] == gap_c and dash_e[4] == dash_c                    # each moved toward the tunnel colour by the strength
    da = layer["paint"]["line-dasharray"]
    assert da[:2] == ["case", ["==", ["get", "__rs_k"], 4]] and da[2] == ["literal", [2.0, 3.0]]
    assert layer["layout"]["line-cap"][:4] == ["case", ["to-boolean", ["get", "__rs_dash"]], "butt", ["==", ["get", "__rs_k"], 4]]
    w = json.dumps(layer["paint"]["line-width"])
    assert w.count('"__rs_k"], 3]') >= 1 and "+" in w
    one = _style(render_edges(_simple_world(), settings={"config": {"tunnel_palette": "One colour"}}, **kw).html)
    color = next(l for l in one["layers"] if l["id"] == "roads-simple")["paint"]["line-color"]
    assert color[color.index(["==", ["get", "__rs_k"], 3]) + 1] == "rgba(0,0,0,0)"


def test_simple_dashed_class_fill_has_the_full_looks_dasharray():
    """The footway's fill (``__rs_dash`` "4,4" from the palette) is dashed per feature, butt ended; a solid road gets [1, 0]."""
    style = _style(render_edges(_simple_world(), backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce").html)
    layer = next(l for l in style["layers"] if l["id"] == "roads-simple")
    foot = next(f["properties"] for f in style["sources"]["simple"]["data"]["features"] if f["properties"]["__rs_edge"] == 2)
    da = layer["paint"]["line-dasharray"]
    by = da[3]
    assert by[0] == "match" and foot["__rs_dash"] in by and by[by.index(foot["__rs_dash"]) + 1] == ["literal", [float(v) for v in foot["__rs_dash"].split(",")]]
    assert by[-1] == ["literal", [1, 0]]
    plain = render_edges(_edges(), backend="web").html
    assert "line-dasharray" not in json.dumps(next(l for l in _style(plain)["layers"] if l["id"] == "roads-simple")["paint"])      # no dash, no tunnel: nothing set


def test_simple_line_cap_per_piece_from_the_ends():
    """cap_col / cap_start_col / cap_end_col in simple mode: ``__rs_cap`` per piece (round none, True flat, "square"); as in the full look a casing's
    main piece ends flat with a round seam dot at each cut (a round main piece reached past a short head into the junction, 2026-10-08);
    an edge with two different ends has two fill halves, each with its end's cap, and casing heads with theirs."""
    d = 0.001
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "cs": [0, 0, 0], "cm": [0, 0, 0], "ce": [0, 0, 0], "fl": [0, 0, 0],
                          "cap": [None, "square", True], "c0": [None, None, "square"], "c1": [None, None, None]},
                         geometry=[LineString([(18, 59 + i / 100), (18 + d, 59 + i / 100)]) for i in range(3)], crs=4326)
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0, cap_col="cap")
    feats = [f["properties"] for f in _style(render_edges(g.drop(columns=["c0", "c1"]), **kw).html)["sources"]["simple"]["data"]["features"]]
    caps = {(p["__rs_k"], p["__rs_edge"]): p.get("__rs_cap") for p in feats}
    assert caps == {(0, 0): None, (1, 0): None, (0, 1): "square", (1, 1): "square", (0, 2): True, (1, 2): True}
    split = _style(render_edges(g.iloc[:1].assign(cap=None, c0="square", c1="flat"), cap_start_col="c0", cap_end_col="c1", **{**kw, "cap_col": None}).html)
    feats = [f["properties"] for f in split["sources"]["simple"]["data"]["features"]]
    fills = [p.get("__rs_cap") for p in feats if p["__rs_k"] == 1]
    assert fills == ["square", True]                                                                # the start half, the end half
    heads = [(p["__rs_cl"], p.get("__rs_cap"), p.get("__rs_main")) for p in feats if p["__rs_k"] == 0 and not p.get("__rs_lap")]
    assert heads[:3] == [(0, "square", None), (0, True, True), (0, True, None)]                       # head, main (flat), head
    assert heads[3:] == [(0, None, None)] * 2 and all(p.get("__rs_seam") for p in feats if p["__rs_k"] == 0 and not p.get("__rs_cap"))   # the two seams, round
    assert [p.get("__rs_cap") for p in feats if p.get("__rs_lap")] == [True, True]                  # and the two laps, flat (below zoom 17)


def test_the_tunnels_box_recolours_the_one_road_layer_in_the_browser(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "simple_tunnels.html"
    render_edges(_edge_world(), backend="web", basemap="blank", tunnel_control=True).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && document.getElementById('tn-str')", timeout=30_000)
        get = 'JSON.stringify(map.getPaintProperty("roads-simple", "line-color"))'
        before = page.evaluate(get)
        dash = 'JSON.stringify(map.getPaintProperty("roads-simple", "line-dasharray"))'
        assert page.evaluate("!!document.getElementById('tn-pal') && !!document.getElementById('tn-ratio')")
        d0 = page.evaluate(dash)
        page.evaluate("rsSetTunnelStyle({strength: 100, toward: 'Navy'})")
        after = page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({ratio: [3, 1], palette: 'One colour'})")
        assert page.evaluate(dash) != d0 and "[3,1]" in page.evaluate(dash) and "rgba(0,0,0,0)" in page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({strength: 0})")
        browser.close()
    assert before != after and "#1e293b" in after and not errors, errors


def test_simple_puts_the_items_of_edges_above_the_road_layer():
    """Overlay(edge_col=...) in simple mode: the items after the one road layer, before the arrows / names / highlight."""
    g = _edge_world()
    pts = _edge_features([12, 13], order=[0, 0])
    style = _style(render_edges(g, backend="web", simple=True, overlays=[Overlay(pts, edge_col="edge_id", order_col="order", kind="circle", label="i")]).html)
    ids = [l["id"] for l in style["layers"]]
    item = next(i for i, l in enumerate(style["layers"]) if l.get("source", "").startswith("ov"))
    assert ids.index("roads-fill") < item < ids.index("roads-highlight")


def _stack_world(junction=False, v=False):
    """A bridge A (edge 1, 60 m) over a street B (edge 2): B crosses A's main part (at 30 m), or with ``v`` crosses it twice, at 4 m (A's start
    head) and 8 m (its main part); with ``junction`` B crosses at 3 m and a street J (edge 3) joins B's end to A's start."""
    P = lambda x, y: (674000 + x, 6580000 + y)                                         # noqa: E731
    b = [P(3, -20), P(3, 20)] if junction else [P(2, -20), P(6, 20), P(10, -20)] if v else [P(30, -20), P(30, 20)]
    lines = [LineString([P(0, 0), P(60, 0)]), LineString(b)] + ([LineString([P(3, 20), P(0, 0)])] if junction else [])
    n = len(lines)
    return gpd.GeoDataFrame({"highway": ["residential"] * n, "bridge": ["yes"] + [None] * (n - 1), "layer": [1] + [None] * (n - 1),
                             "junction": [None] * n, "edge_id": list(range(1, n + 1))}, geometry=lines, crs=3006)


def test_make_writes_one_stack_row_per_part_that_crosses():
    """2026-10-08: level_input writes a stack as one row per part of the upper road that crosses the lower one, worked out once with the
    heads of that time: a crossing in the main part is one main row; a crossing over a head and the main part two rows; a head that joins the
    lower road (here through J) none."""
    import roadstyle as rs
    rows = lambda g, **k: sorted((r.a, r.b, r.a_end) for r in rs.level_input(g, **k)[1].itertuples() if r.relation == "stack")   # noqa: E731
    assert rows(_stack_world()) == [("1", "2", "main")]
    assert rows(_stack_world(v=True)) == [("1", "2", "main"), ("1", "2", "start")]
    assert rows(_stack_world(v=True), head_m=10.0) == [("1", "2", "start")]          # longer heads at make: both crossings in the start head
    assert rows(_stack_world(junction=True)) == []                                    # A's start head joins J, which joins B: a junction
    assert rows(_stack_world(junction=True).iloc[:2]) == [("1", "2", "start")]         # without J: the start head crosses B


def test_stack_rows_union_and_switch_off_exactly_one_row():
    """Rows union: an edit adds a part to the found ones; an edit with enabled false takes out exactly that row (pair and part)."""
    pytest.importorskip("scipy")
    import pandas as pd

    import roadstyle as rs
    from roadstyle.levels import merged_relations
    roads, pairs = rs.level_input(_stack_world(v=True))                               # found: A's start and main over B
    row = lambda p, on="true": {"relation": "stack", "a": "1", "b": "2", "a_end": p, "b_end": "", "enabled": on}   # noqa: E731
    parts = lambda e: sorted(k[3] for k in merged_relations(roads, pairs, e) if k[0] == "stack")   # noqa: E731
    assert parts(None) == ["main", "start"]
    assert parts(pd.DataFrame([row("end")])) == ["end", "main", "start"]
    assert parts(pd.DataFrame([row("main", "false")])) == ["start"]
    assert parts(pd.DataFrame([row(p, "false") for p in ("start", "main")] + [row("end")])) == ["end"]     # override: all found off, your own on
    out = rs.solve_levels(roads, pairs, edits=pd.DataFrame([row("end")])).set_index("road")
    assert min(out.loc["1", ["casing_start", "casing_level", "casing_end"]]) > out.loc["2", "fill_level"]


def test_a_head_change_after_make_changes_nothing_in_the_solve(tmp_path):
    """The solver works from the tables only (2026-10-08): heads.csv changed after make gives the same levels; make again reads it."""
    pytest.importorskip("scipy")
    import pandas as pd

    from roadstyle.level_area import make_area, solve_area
    make_area(_stack_world(v=True), tmp_path)
    cols = ["casing_start", "casing_level", "casing_end", "fill_level"]
    before = solve_area(tmp_path)[cols]
    (tmp_path / "heads.csv").write_text("road,start_m,end_m\n1,10,30\n")
    assert solve_area(tmp_path)[cols].equals(before)
    _, pairs = make_area(_stack_world(v=True), tmp_path)                                # make again: the heads of heads.csv
    assert pairs.loc[pairs.relation == "stack", "a_end"].tolist() == ["start"]
    assert pd.read_csv(tmp_path / "heads.csv").shape == (1, 3)                         # yours: kept


def test_an_old_pairs_table_with_whole_road_stacks_is_an_error():
    """A pairs.csv made before 2026-10-08 (a stack row with no part) is not read as something else: make the area again."""
    import pandas as pd

    import roadstyle as rs
    roads, pairs = rs.level_input(_stack_world())
    old = pd.concat([pairs[pairs.relation != "stack"], pd.DataFrame([{"relation": "stack", "a": "1", "b": "2"}])], ignore_index=True)
    with pytest.raises(ValueError, match="make the area again|Make the area again"):
        rs.solve_levels(roads, old)


def test_rule_conflicts_finds_duplicates_and_loops():
    """The editor's guard (levels.rule_conflicts): a duplicate, a two-rule contradiction, a three-rule loop and a rule with no conflict, from
    the solver's own rules (no geometry)."""
    import roadstyle as rs
    from roadstyle.levels import rule_conflicts
    roads, pairs = rs.level_input(_edge_world())       # meets 11-12, 12-14; stack 13 (main) over 12; orders 12 after 11 and 14
    stack = lambda a, b, p="main": {"relation": "stack", "a": a, "b": b, "a_end": p, "b_end": "", "enabled": "true"}   # noqa: E731
    order = lambda a, b: {"relation": "order", "a": a, "b": b, "a_end": "", "b_end": "", "enabled": "true"}            # noqa: E731
    said = lambda rows: [(why, [(r["relation"], r["a"], r["b"]) for r in w]) for _, why, w in rule_conflicts(roads, pairs, None, rows)]   # noqa: E731
    assert said([stack("13", "12")]) == [("duplicate", [("stack", "13", "12")])]
    assert said([stack("12", "13")]) == [("loop", [("stack", "13", "12")])]              # 12 over 13 against 13 over 12
    assert said([order("12", "13")]) == [("loop", [("stack", "13", "12")])]              # 12's fill after 13's against 13 over 12
    assert said([order("11", "13")]) == [("loop", [("stack", "13", "12"), ("order", "12", "11")])]   # 13 < 11 < 12 < 13
    assert said([order("14", "11")]) == [] and said([stack("13", "12", "start")]) == []
    assert said([order("14", "11"), order("11", "14")]) == [("loop", [("order", "14", "11")])]       # the rows before count too


def test_a_seam_is_long_enough_to_keep_its_direction():
    """A seam reaches 0.5 m each way from its cut (a quarter of the shorter piece at most): a 2 cm seam fell on one or two steps of the
    map's tile grid above zoom 18 and was drawn as a square block out of the outline (2026-10-08)."""
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0)
    feats = _style(render_edges(_simple_world(), **kw).html)["sources"]["simple"]["data"]["features"]
    seams = [f["geometry"]["coordinates"] for f in feats if f["properties"].get("__rs_seam") and not f["properties"].get("__rs_lap")]
    assert seams
    for c in seams:
        (x0, y0), (x1, y1) = c[0][:2], c[-1][:2]
        metres = math.hypot((x1 - x0) * 111320 * math.cos(math.radians(y0)), (y1 - y0) * 111320)
        assert 0.9 < metres < 1.01                                   # 1 m (my metre conversion is approximate)


def test_simple_seams_only_from_zoom_17_as_the_full_look():
    """A seam (a round dot at a casing cut) is drawn from zoom 17 only, as in the full look: below it a bridge's seams were dark dots at every head."""
    style = _style(render_edges(_simple_world(), backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce").html)
    flt = json.dumps(next(l for l in style["layers"] if l["id"] == "roads-simple")["filter"])
    seam, lap = ["to-boolean", ["get", "__rs_seam"]], ["to-boolean", ["get", "__rs_lap"]]
    assert json.dumps(["any", ["!", seam], ["all", ["!", lap], [">=", ["zoom"], 17]], ["all", lap, ["<", ["zoom"], 17]]]) in flt


def test_a_lap_closes_the_cut_below_zoom_17():
    """Below zoom 17 a flat lap lies across each casing cut at the lower number, up to 2 m each way and half of either piece: the two flat
    ends at a cut take their directions from the map's tile grid (22 cm at zoom 14), stood a few degrees apart and left a thin gap across a
    bridge's outline (2026-10-08). Both looks."""
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0)
    for simple, src in ((True, "simple"), (False, "casings")):
        style = _style(render_edges(_simple_world(), simple=simple, **kw).html)
        feats = style["sources"][src]["data"]["features"]
        laps = [f for f in feats if f["properties"].get("__rs_lap")]
        seams = [f for f in feats if f["properties"].get("__rs_seam") and not f["properties"].get("__rs_lap")]
        solid = [f for f in seams if not (f["properties"].get("__rs_dash") or f["properties"].get("__rs_tunnel"))]   # (none on dashes)
        assert laps and len(laps) == len(solid) and not any(f["properties"].get("__rs_tunnel") for f in laps)
        for lap, seam in zip(laps, solid):
            p = lap["properties"]
            assert p["__rs_cap"] is True and p["__rs_seam"] and (p["__rs_edge"], p["__rs_cl"]) == (seam["properties"]["__rs_edge"], seam["properties"]["__rs_cl"])   # flat, at the seam's number
            (x0, y0), (x1, y1) = lap["geometry"]["coordinates"][0][:2], lap["geometry"]["coordinates"][-1][:2]
            assert math.hypot((x1 - x0) * 111320 * math.cos(math.radians(y0)), (y1 - y0) * 111320) <= 4.0 + 0.01
        for lyr in (l for l in style["layers"] if l.get("source") == src and not l["id"].endswith("-dash")):
            assert '["all", ["to-boolean", ["get", "__rs_lap"]], ["<", ["zoom"], 17]]' in json.dumps(lyr["filter"])


def test_an_unclassed_two_way_pair_pairs_and_the_warning_names_it():
    """Both directions of a road with no class (an area outline taken as a road) are a pair: one casing, a fill per direction (NaN != NaN
    made them two roads). render_edges warns once, with the count and the edge ids."""
    a, b = (18.00, 59.30), (18.00, 59.31)
    g = gpd.GeoDataFrame({"highway": [None, float("nan")], "edge_ref": ["w#2f", "w#2r"]},
                         geometry=[LineString([a, b]), LineString([b, a])], crs=4326)
    with pytest.warns(UserWarning, match=r"2 edges have no 'highway' value.*w#2f, w#2r"):
        html = render_edges(g, **_TWIN_KW).html
    feats = [f["properties"] for f in _style(html)["sources"]["simple"]["data"]["features"]]
    assert {p["__rs_edge"] for p in feats if p["__rs_k"] != 1} == {0}                  # one casing, the first edge's
    assert all(p.get("__rs_twoway", True) for p in feats) and sorted(p["__rs_edge"] for p in feats if p["__rs_k"] == 1) == [0, 1]

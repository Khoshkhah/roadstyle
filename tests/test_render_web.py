import pandas as pd
"""Web (MapLibre) backend: client-side recolouring via color_options + the recolour hooks."""
import json
import math
import re

import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import render_edges


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
    assert ["==", ["%", ["get", "slot"], 2], 0] in lab["filter"]     # names: even slots
    # arrows: every one-way slot, repeated along the line (odd-slots-only left short
    # one-way chains — most of a city grid — with no arrow in the viewport)
    assert ["==", ["get", "oneway"], 1] in arr["filter"]
    assert arr["layout"]["symbol-placement"] == "line" and arr["layout"]["symbol-spacing"]
    # one arrow layer per grade tier, each right beside its road tier — a bridge must cover
    # the arrows of the road it crosses, not have them float above everything
    assert ids.index("roads-arrows") == ids.index("roads-fill") + 1
    assert ids.index("roads-arrows-tunnel") == ids.index("roads-low-fill") + 1     # after the below-ground band
    assert ids.index("roads-arrows-bridge") == ids.index("roads-bridge-fill") + 1
    assert ["to-boolean", ["get", "name"]] in lab["filter"]          # unnamed -> slot stays empty
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
    assert set(blobs) <= {"roads", "slots"}             # sized sources stay inline
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
            if l["id"] in ("roads-fill", "roads-casing", "roads-tunnel-fill", "roads-bridge-fill")}


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


def test_minzoom_keeps_the_grade_separation_filters_intact():
    """The clause is AND-ed on; tunnel/surface/bridge must still be distinguished, or grade
    separation collapses into one layer."""
    from roadstyle.render_web import render

    fs = _road_filters(render(_many_edges(20), minzoom=True).html)
    assert "lvl" in json.dumps(fs["roads-fill"])
    assert fs["roads-fill"] != fs["roads-tunnel-fill"] != fs["roads-bridge-fill"]

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
    style = _style(render_edges(_edges(), backend="web").html)
    bc = next(l for l in style["layers"] if l["id"] == "roads-bridge-casing")
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
    flat3d = next(l for l in td["layers"] if l["id"] == "roads-bridge-fill")
    deck3d = next(l for l in td["layers"] if l["id"] == "roads-bridge-decks")
    assert flat3d["maxzoom"] == 16.0 and deck3d["minzoom"] == 16.0
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
    assert "roads-bridge-casing" in fids and "roads-bridge-decks" not in fids
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


def test_dashed_bridge_gets_deck_underlay_and_casing():
    """A footway/cycleway BRIDGE still reads as a bridge: the black bridge casing keeps dashed
    classes, and a solid underlay (the class's light casing colour) sits beneath the dashes —
    so a path crossing UNDER it can't show through the gaps (the osm-carto footbridge look)."""
    g = gpd.GeoDataFrame(
        {"highway": ["footway", "residential"], "bridge": ["yes", None]},
        geometry=[LineString([(18.0, 59.30), (18.01, 59.305)]),
                  LineString([(18.0, 59.305), (18.01, 59.30)])], crs=4326)
    style = _style(render_edges(g, backend="web").html)
    lay = {l["id"]: l for l in style["layers"]}
    ids = [l["id"] for l in style["layers"]]
    assert "__rs_dash" not in json.dumps(lay["roads-bridge-casing"]["filter"])  # casing kept
    deck = lay["roads-bridge-fill-deck0"]
    dash = lay["roads-bridge-fill-dash0"]
    assert "__rs_casing" in json.dumps(deck["paint"]["line-color"])    # solid deck underlay
    assert "line-dasharray" not in deck["paint"]
    assert ids.index("roads-bridge-fill-deck0") < ids.index("roads-bridge-fill-dash0")
    assert "line-dasharray" in dash["paint"]


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
    with darker dashes on top, so connected tunnel pieces look connected (empty dash gaps hid it)
    while the dash says "tunnel"."""
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "tunnel": ["yes", None]},
                         geometry=[LineString([(18.0, 59.30), (18.01, 59.30)]),
                                   LineString([(18.01, 59.30), (18.02, 59.30)])], crs=4326)
    style = _style(render_edges(g, backend="web").html)          # highsat: primary casing #bcbcbc
    lay = {l["id"]: l for l in style["layers"]}
    ids = list(lay)
    assert ids.index("roads-tunnel-casing") < ids.index("roads-tunnel-casing-dash") < ids.index("roads-tunnel-fill")
    assert "__rs_casing_gap" in json.dumps(lay["roads-tunnel-casing"]["paint"]["line-color"])
    assert lay["roads-tunnel-casing-dash"]["paint"]["line-dasharray"] == [2, 2]
    tun, street = (f["properties"] for f in style["sources"]["roads"]["data"]["features"])
    assert tun["__rs_casing"] == "#bcbcbc"
    assert tun["__rs_casing_gap"] == "#8d8d8d" and tun["__rs_casing_dash"] == "#5e5e5e"  # 25 / 50 % darker
    assert "__rs_casing_dash" not in street and "__rs_casing_gap" not in street
    mono = _style(render_edges(g, backend="web", palette="mono").html)["sources"]["roads"]["data"]
    tun = mono["features"][0]["properties"]                     # mono primary casing #4f4f4f
    assert tun["__rs_casing_gap"] == "#4f4f4f" and tun["__rs_casing_dash"] == "#282828"  # dark, darker


def test_raised_and_lowered_roads_without_a_structure_tag():
    """A raised walkway (layer=1, no bridge tag) draws in the above-ground band with the plain
    look (roads-high-*, before the bridges); a road with a negative layer and no tunnel tag in the
    below-ground band, plain (roads-low-*, after the tunnels). Untagged bridges / tunnels default
    to 1 / -1; a tunnel tagged layer=1 goes above ground."""
    g = gpd.GeoDataFrame(
        {"highway": ["footway", "service", "primary", "primary", "service", "residential"],
         "layer": ["1", "-1", None, None, "1", None],
         "bridge": [None, None, "yes", None, None, None],
         "tunnel": [None, None, None, "yes", "yes", None]},
        geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(6)],
        crs=4326)
    style = _style(render_edges(g, backend="web").html)
    assert [f["properties"]["lvl"] for f in style["sources"]["roads"]["data"]["features"]] == [1, -1, 1, -1, 1, 0]
    ids = [l["id"] for l in style["layers"]]
    order = ["roads-tunnel-fill", "roads-low-casing", "roads-low-fill", "roads-casing", "roads-fill",
             "roads-high-casing", "roads-high-fill", "roads-bridge-casing", "roads-bridge-fill"]
    assert [ids.index(i) for i in order] == sorted(ids.index(i) for i in order)
    lay = {l["id"]: l for l in style["layers"]}
    assert "__rs_bridge" in json.dumps(lay["roads-high-fill"]["filter"])      # not a bridge
    assert "__rs_tunnel" in json.dumps(lay["roads-low-fill"]["filter"])       # not a tunnel


def test_rscolor_raises_painted_roads_within_their_level():
    """rsColor lifts the painted roads to the top of their level (line-sort-key +500, levels are
    1000 apart): over a street they cross, still under a bridge above them."""
    html = render_edges(_edges(), backend="web").html
    assert "function _applySort()" in html and '["case",["in",idE,["literal",all]],500,0]' in html
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


def test_band_col_moves_plain_edges_between_bands():
    """band_col: -1 draws an edge (casing + fill) in the low band under the ground roads, 1 in the
    high band over them, 0 or null as the level says; a tunnel or bridge keeps its band
    (docs/design/draw_order_per_edge.md)."""
    g = gpd.GeoDataFrame(
        {"highway": ["residential", "residential", "residential", "residential", "primary", "residential"],
         "band": [-1, 1, None, 0, 1, -1],
         "bridge": [None, None, None, None, "yes", None],
         "layer": [None, None, None, "1", None, None]},
        geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(6)],
        crs=4326)
    style = _style(render_edges(g, backend="web", band_col="band").html)
    lay = {l["id"]: l for l in style["layers"]}
    feats = style["sources"]["roads"]["data"]["features"]
    where = []
    for f in feats:
        p = f["properties"]
        hit = [b for b in ("roads-low-fill", "roads-fill", "roads-high-fill", "roads-bridge-fill")
               if _eval(lay[b]["filter"], p)]
        where.append(hit)
    # (solid classes: a dashed one is drawn by the -dash sibling layers, same band filters)
    # -1 -> low, 1 -> high, null -> ground, explicit 0 on a raised plain edge -> ground,
    # a bridge keeps its band
    assert where == [["roads-low-fill"], ["roads-high-fill"], ["roads-fill"], ["roads-fill"],
                     ["roads-bridge-fill"], ["roads-low-fill"]]
    assert "__rs_band" not in feats[4]["properties"]                 # the bridge: not moved
    assert _eval(lay["roads-low-casing"]["filter"], feats[0]["properties"])   # casing moves too


def test_order_col_sets_the_order_inside_a_band_and_clamps():
    g = gpd.GeoDataFrame(
        {"highway": ["footway", "primary", "residential"], "order": [9.5, None, 1000]},
        geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(3)],
        crs=4326)
    style = _style(render_edges(g, backend="web", order_col="order").html)
    lay = {l["id"]: l for l in style["layers"]}
    key = lay["roads-fill"]["layout"]["line-sort-key"]
    ps = [f["properties"] for f in style["sources"]["roads"]["data"]["features"]]
    assert [p.get("__rs_order") for p in ps] == [9.5, None, 400.0]      # null: class order; clamped
    assert "__rs_order" in json.dumps(key) and key[0] == "+"            # lvl * 1000 + the order


def test_order_and_band_change_nothing_when_not_asked():
    """Without order_col / band_col the style is exactly today's (no __rs_band / __rs_order)."""
    g = _edges().assign(order=[1, 2, 3], band=[1, -1, 0])
    plain = _style(render_edges(g, backend="web").html)
    asked_none = _style(render_edges(g, backend="web", order_col=None, band_col=None).html)
    assert plain == asked_none
    assert "__rs_band" not in json.dumps(plain) and "__rs_order" not in json.dumps(plain)


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
    z = dict(zip(key[2:-1:2], key[3:-1:2]))
    links = ["motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"]
    assert all(z["pedestrian"] > z[l] > z["service"] for l in links)
    assert [z[l] for l in links] == sorted((z[l] for l in links), reverse=True)
    assert z["primary_link"] < z["residential"]
    render_web.ROAD_Z.pop("trunk_link")
    try:
        assert render_web._sort_key("highway")[2][render_web._sort_key("highway")[2].index("trunk_link") + 1] == 7.5
    finally:
        render_web._load_road_model()


def test_every_road_fill_layer_is_clickable():
    """A road in the low / high bands (a raised walkway with layer=1 and no bridge tag, a sidewalk
    or crossing moved by band_col) must be clickable and hoverable like any other: every road fill
    layer, dashed siblings included, matches the page's pick pattern (Kaveh: footway
    5552170400133534207 in Monaco could not be selected)."""
    g = gpd.GeoDataFrame(
        {"highway": ["residential", "footway", "residential", "residential", "residential"],
         "layer": [None, "1", "-1", None, None], "bridge": [None, None, None, "yes", None],
         "tunnel": [None, None, None, None, "yes"]},
        geometry=[LineString([(18.0 + i * 0.01, 59.30), (18.0 + i * 0.01, 59.31)]) for i in range(5)],
        crs=4326)
    html = render_edges(g, backend="web").html
    pattern = re.search(r"\.filter\(id=>/(\^roads-[^/]+)/\.test\(id\)\)", html).group(1)
    fills = [l["id"] for l in _style(html)["layers"]
             if re.match(r"roads-(tunnel-|low-|high-|bridge-)?fill", l["id"])]
    assert {"roads-low-fill", "roads-high-fill", "roads-high-fill-dash0"} <= set(fills)
    assert [f for f in fills if not re.match(pattern, f)] == []


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


def test_end_caps_sit_under_their_band_and_match_the_lanes_width():
    from roadstyle import render_web as rw
    style = _style(render_edges(_pairs(), backend="web").html)
    ids = [l["id"] for l in style["layers"]]
    for band in ("low-", "", "high-"):
        order = [f"roads-ends-{band}casing", f"roads-{band}casing", f"roads-ends-{band}fill", f"roads-{band}fill"]
        assert [ids.index(i) for i in order] == sorted(ids.index(i) for i in order), band
    lay = {l["id"]: l for l in style["layers"]}
    assert lay["roads-ends-fill"]["paint"]["circle-pitch-alignment"] == "map"
    # the cap's radius = the lanes' offset + half a lane, at every zoom stop (residential)
    rad = lay["roads-ends-fill"]["paint"]["circle-radius"]
    off, fw = rw._offset_expr("highway"), rw._width_expr("highway")
    for k, z in enumerate(rw._ZSTOPS):
        r = dict(zip(rad[4 + 2 * k][2:-1:2], rad[4 + 2 * k][3:-1:2]))["residential"]
        o = off[4 + 2 * k][2]
        o = dict(zip(o[2:-1:2], o[3:-1:2]))["residential"]
        m = fw[4 + 2 * k]
        m = m[1] if m[0] == "*" else m                    # the two-way split wraps the class match
        w = dict(zip(m[2:-1:2], m[3:-1:2]))["residential"]
        split = 1.0 if z <= 15 else (0.6 if z >= 17 else 1 - 0.4 * (z - 15) / 2)
        assert abs(r - (o + w * split / 2)) < 0.01, z


def test_end_caps_follow_filters_and_recolour_and_can_be_turned_off():
    html = render_edges(_pairs(), backend="web").html
    assert 'l.source==="ends"' in html and "__rs_road2" in html                  # id filters
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


def test_fill_only_end_cap_where_a_road_in_a_lower_band_meets():
    """A cap's casing ring would cross a road drawn under it (a plain layer=-1 road, a tunnel, a
    sidewalk moved by band_col), so that end gets a fill-only cap (__rs_nocase: no casing circle);
    the other end keeps its full cap (Kaveh's screenshots: a ring across the continuing road, then
    the lanes' bump-dip-bump at a tunnel mouth)."""
    a, b, c = (18.00, 59.30), (18.00, 59.31), (18.01, 59.32)
    g = gpd.GeoDataFrame({"highway": ["secondary"] * 3, "layer": [None, None, "-1"], "band": [None, None, -1]},
                         geometry=[LineString([a, b]), LineString([b, a]), LineString([b, c])], crs=4326)
    style = _style(render_edges(g, backend="web", band_col="band").html)
    pts = {tuple(p["geometry"]["coordinates"]): p["properties"] for p in style["sources"]["ends"]["data"]["features"]}
    assert set(pts) == {a, b} and pts[b].get("__rs_nocase") and not pts[a].get("__rs_nocase")
    lay = {l["id"]: l for l in style["layers"]}
    assert not _eval(lay["roads-ends-casing"]["filter"], pts[b])     # no ring across the lower road
    assert _eval(lay["roads-ends-casing"]["filter"], pts[a])
    assert _eval(lay["roads-ends-fill"]["filter"], pts[b])           # but the dip is still filled
    # a layer=-1 road that passes under nothing is drawn with the ground roads (junctions.md,
    # rule 1): a full cap
    assert not any(p["properties"].get("__rs_nocase")
                   for p in _style(render_edges(g, backend="web").html)["sources"]["ends"]["data"]["features"])
    # a road in a HIGHER band (layer=1) covers the cap anyway: both ends keep a full cap
    g.loc[2, "layer"] = "1"
    assert not any(p["properties"].get("__rs_nocase")
                   for p in _style(render_edges(g, backend="web").html)["sources"]["ends"]["data"]["features"])


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


def test_a_tunnel_under_nothing_is_one_ground_stretch():
    """It draws with the ground roads in the tunnel style, so both mouths join like a road
    continuing; the edge itself stays in `roads`, invisible, as the click / selection target."""
    style = _style(render_edges(_tunnel_world(False), backend="web").html)
    pcs = style["sources"]["tpieces"]["data"]["features"]
    assert [(f["properties"]["__rs_road"], f["properties"]["__rs_piece"]) for f in pcs] == [(1, "ground")]
    t = style["sources"]["roads"]["data"]["features"][1]["properties"]
    assert t["__rs_gstart"] and t["__rs_gend"]
    assert pcs[0]["properties"]["__rs_tfill"] != pcs[0]["properties"]["__rs_fill"]   # faded, opaque
    lay = {l["id"]: l for l in style["layers"]}
    ids = [l["id"] for l in style["layers"]]
    assert lay["roads-tunnel-fill"]["paint"]["line-opacity"] == 0          # pick target only
    assert (ids.index("roads-casing") < ids.index("roads-tunnelgr-casing") < ids.index("roads-tunnelgr-fill")
            < ids.index("roads-fill"))
    assert lay["roads-tunnelgr-fill"]["layout"]["line-cap"] == "butt"


def test_a_tunnel_under_a_street_is_cut_into_ground_under_ground():
    """Only the stretch under the crossing street (4 m either side) is in the lower band."""
    style = _style(render_edges(_tunnel_world(True), backend="web").html)
    pcs = [f for f in style["sources"]["tpieces"]["data"]["features"] if f["properties"]["__rs_road"] == 1]
    assert [f["properties"]["__rs_piece"] for f in pcs] == ["ground", "under", "ground"]
    xs = [f["geometry"]["coordinates"] for f in pcs]
    k = 111320.0 * math.cos(math.radians(59.30))
    assert abs((xs[1][-1][0] - xs[1][0][0]) * k - 8.0) < 0.5             # 4 m either side of 18.003
    # a road joined to the tunnel at its mouth is not one it passes under
    assert style["sources"]["roads"]["data"]["features"][1]["properties"]["__rs_gstart"]


def test_a_shallow_crossing_keeps_the_tunnel_under_while_it_is_within_4_m():
    """Kaveh, 2026-09-30 (Monaco 6383643885887187607 over 1494951369778192963): a street crossing a
    tunnel at a shallow angle is near it for much longer than 4 m either side of the crossing
    point; a ground stretch there would paint its casing over the street's."""
    g = pd.concat([_tunnel_world(False), gpd.GeoDataFrame(
        {"highway": ["residential"], "tunnel": [None]},
        geometry=[LineString([(18.0024, 59.29995), (18.0036, 59.30005)])], crs=4326)],   # ~1.5 m off per 10 m
        ignore_index=True)
    pcs = [f for f in _style(render_edges(g, backend="web").html)["sources"]["tpieces"]["data"]["features"]
           if f["properties"]["__rs_road"] == 1]
    assert [f["properties"]["__rs_piece"] for f in pcs] == ["ground", "under", "ground"]
    k = 111320.0 * math.cos(math.radians(59.30))
    under = (pcs[1]["geometry"]["coordinates"][-1][0] - pcs[1]["geometry"]["coordinates"][0][0]) * k
    assert under > 40                                    # the whole stretch within 4 m, not 8 m


def test_a_plain_layer_road_acts_like_a_tunnel_with_the_plain_look():
    """junctions.md rule 1, for a ``layer`` tag alone (Kaveh: Boulevard Charles III, a layer=-1
    tunnel approach, looked cut off from the roundabout it joins): across nothing, it is a ground
    road, whole; a raised walkway over a street is cut, over the street in the high band, the rest
    with the ground roads, and its own edge stays the (invisible) click target."""
    a, b, c = (18.000, 59.30), (18.002, 59.30), (18.004, 59.30)
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "layer": [None, "-1"]},
                         geometry=[LineString([a, b]), LineString([b, c])], crs=4326)
    st = _style(render_edges(g, backend="web").html)
    p = st["sources"]["roads"]["data"]["features"][1]["properties"]
    assert p["__rs_band"] == 0 and "tpieces" not in st["sources"]
    lay = {l["id"]: l for l in st["layers"]}
    assert _eval(lay["roads-casing"]["filter"], p) and not _eval(lay["roads-low-casing"]["filter"], p)

    w = gpd.GeoDataFrame({"highway": ["footway", "footway", "residential"], "layer": [None, "1", None]},
                         geometry=[LineString([a, b]), LineString([b, c]),
                                   LineString([(18.003, 59.299), (18.003, 59.301)])], crs=4326)
    st = _style(render_edges(w, backend="web").html)
    pcs = [f["properties"]["__rs_piece"] for f in st["sources"]["tpieces"]["data"]["features"]]
    assert pcs == ["ground", "over", "ground"]
    p = st["sources"]["roads"]["data"]["features"][1]["properties"]
    assert p["__rs_pieced"] and p["__rs_gstart"] and p["__rs_gend"]
    lay = {l["id"]: l for l in st["layers"]}
    ids = [l["id"] for l in st["layers"]]
    assert not _eval(lay["roads-high-casing"]["filter"], p)                  # drawn by its stretches
    assert lay["roads-high-fill"]["paint"]["line-opacity"] == ["case", ["to-boolean", ["get", "__rs_pieced"]], 0, 1]
    assert (ids.index("roads-casing") < ids.index("roads-plaingr-casing") < ids.index("roads-plaingr-fill")
            < ids.index("roads-fill") < ids.index("roads-highp-casing") < ids.index("roads-highp-fill"))
    assert 'RS_PIECE_LAYERS = ["roads-tunnel-under-fill","roads-lowp-fill","roads-plaingr-fill","roads-highp-fill"]' \
        in render_edges(w, backend="web").html


def test_dashed_classes_keep_their_dashes_in_tunnel_and_plain_stretches():
    """line-dasharray can't vary per feature: every stretch fill layer gets the dashed sibling
    layers the whole-edge fills have (a dashed tunnel stretch was drawn solid, or not at all)."""
    a, b, c = (18.000, 59.30), (18.002, 59.30), (18.004, 59.30)
    g = gpd.GeoDataFrame({"highway": ["footway", "footway", "residential"], "tunnel": [None, "yes", None]},
                         geometry=[LineString([a, b]), LineString([b, c]),
                                   LineString([(18.003, 59.299), (18.003, 59.301)])], crs=4326)
    ids = [l["id"] for l in _style(render_edges(g, backend="web", palette="highsat").html)["layers"]]   # dashed footways
    assert {"roads-tunnel-under-fill-dash0", "roads-tunnelgr-fill-dash0"} <= set(ids)
    assert ids.index("roads-tunnelgr-fill-dash0") < ids.index("roads-casing")   # under street casings


def test_tunnels_get_light_dashes_on_their_fill_unless_turned_off():
    """Kaveh's pick among three samples ("light dash is ok"): over the fill of both stretch kinds,
    translucent, butt-capped; not on a dashed class; `tunnel_fill_dash: []` turns it off."""
    st = _style(render_edges(_tunnel_world(True), backend="web").html)
    lay = {l["id"]: l for l in st["layers"]}
    ids = [l["id"] for l in st["layers"]]
    for base in ("roads-tunnel-under-fill", "roads-tunnelgr-fill"):
        pat = lay[base + "-pat"]
        assert ids.index(pat["id"]) == ids.index(base) + 1 and pat["source"] == "tpieces"
        assert pat["paint"]["line-dasharray"] == [1.2, 1.2] and pat["layout"]["line-cap"] == "butt"
        assert pat["paint"]["line-color"].startswith("rgba(255,255,255")
        assert '"__rs_dash"' in json.dumps(pat["filter"])                      # dashed classes: none
    off = _style(render_edges(_tunnel_world(True), backend="web",
                              settings={"config": {"tunnel_fill_dash": []}}).html)
    assert not any(l["id"].endswith("-pat") for l in off["layers"])


def test_tunnel_stretches_follow_ids_recolour_and_order():
    html = render_edges(_tunnel_world(True), backend="web").html
    assert 'l.source==="tpieces"' in html and 'RS_PIECE_LAYERS = ["roads-tunnel-under-fill","roads-lowp-fill","roads-plaingr-fill","roads-highp-fill"]' in html
    assert '"roads-tunnelgr-fill","line-color",ge' in html                # faded colour kept by default
    plain = _style(render_edges(_edges(), backend="web").html)            # no tunnels: no stretches
    assert "tpieces" not in plain["sources"]


def test_end_cap_at_a_tunnel_mouth_is_full_when_the_tunnel_starts_at_ground():
    """A two-way street meeting a tunnel whose first stretch is ground gets its full cap (the ring
    lies under the tunnel's casing); a tunnel that dives under a road right at the mouth still
    ranks lower there (fill-only cap)."""
    a, b, c = (18.000, 59.30), (18.002, 59.30), (18.004, 59.30)
    g = gpd.GeoDataFrame({"highway": ["primary"] * 3, "tunnel": [None, None, "yes"]},
                         geometry=[LineString([a, b]), LineString([b, a]), LineString([b, c])], crs=4326)
    pts = {tuple(p["geometry"]["coordinates"]): p["properties"]
           for p in _style(render_edges(g, backend="web").html)["sources"]["ends"]["data"]["features"]}
    assert not pts[b].get("__rs_nocase")
    g2 = pd.concat([g, gpd.GeoDataFrame({"highway": ["residential"], "tunnel": [None]},
                                        geometry=[LineString([(18.00205, 59.299), (18.00205, 59.301)])], crs=4326)],   # 2.8 m in: within the 4 m clearance
                   ignore_index=True)
    pts = {tuple(p["geometry"]["coordinates"]): p["properties"]
           for p in _style(render_edges(gpd.GeoDataFrame(g2, crs=4326), backend="web").html)["sources"]["ends"]["data"]["features"]}
    assert pts[b].get("__rs_nocase")


def test_a_footway_over_a_tunnel_does_not_make_it_an_underpass():
    """Only roads make a tunnel go to the lower band, not paths: a footway crossing over it is
    drawn on top of its ground stretch (80 of Monaco's 109 'under at the mouth' cases)."""
    g = _tunnel_world(True)
    g.loc[3, "highway"] = "footway"
    pcs = [f["properties"]["__rs_piece"] for f in _style(render_edges(g, backend="web").html)
           ["sources"]["tpieces"]["data"]["features"] if f["properties"]["__rs_road"] == 1]
    assert pcs == ["ground"]

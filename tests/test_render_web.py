"""Web (MapLibre) backend: client-side recolouring via color_options + the recolour hooks."""
import json
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
    assert ["==", ["%", ["get", "slot"], 2], 1] in arr["filter"]     # arrows: odd slots
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


def test_compress_off_by_default_leaves_data_inline():
    from roadstyle.render_web import render
    html = render(_many_edges()).html
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
    plain, small = render(g).html, render(g, compress=True).html
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
    tw = [f["properties"]["twoway"] for f in style["sources"]["roads"]["data"]["features"]]
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
    assert paint == {"text-color": "#ff0000", "text-halo-color": "#000000", "text-halo-width": 2}
    arrow = next(l for l in style["layers"] if l["id"] == "roads-arrows")
    assert arrow["minzoom"] == 14 and arrow["paint"]["icon-opacity"] == 0.5
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
    and drops the flat bridge line layers; flat maps keep the classic flat bridge treatment."""
    g = _edges().assign(bridge=["yes", None, None])
    td = _style(render_edges(g, backend="web", view_3d=True).html)
    ids = [l["id"] for l in td["layers"]]
    assert "roads-bridge-decks" in ids
    assert "roads-bridge-casing" not in ids and "roads-bridge-fill" not in ids
    deck = next(l for l in td["layers"] if l["id"] == "roads-bridge-decks")
    assert deck["type"] == "fill-extrusion"
    assert deck["paint"]["fill-extrusion-base"] == ["get", "__rs_base"]
    assert td["sources"]["decks"].get("generateId") is True     # hover/select feature-state
    slices = td["sources"]["decks"]["data"]["features"]
    assert all(f["geometry"]["type"] == "Polygon" for f in slices)
    # popup parity: slices carry the full edge properties, not just fills
    assert "maxspeed_kmh" in slices[0]["properties"] or "aadt" in slices[0]["properties"]
    assert all("__rs_chain" in f["properties"] for f in slices)   # whole-bridge hover unit
    assert deck["paint"]["fill-extrusion-opacity"] == 0.7        # settings-driven transparency
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
    assert '"roads-bridge-decks"' in html.split("PICK_LAYERS")[1][:120]


def test_web_camera_max_pitch():
    """The tilt limit is a setting (camera.max_pitch, default 85) — MapLibre's default 60 made
    the camera stop partway when tilting interactively."""
    assert "maxPitch:85" in render_edges(_edges(), backend="web").html


def test_snapshot_writes_png(tmp_path):
    """rs.snapshot: WebMap -> PNG through headless Chromium, honouring the camera args."""
    import roadstyle as rs

    wm = render_edges(_edges(), backend="web")
    out = tmp_path / "shot.png"
    rs.snapshot(wm, out, zoom=13, width=500, height=400, settle=1.5)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 10_000


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
    """road_popup="panel" routes the click read-out into a docked side panel (curated fields);
    rs:select / rs:deselect CustomEvents fire in every mode for host pages."""
    panel = render_edges(_edges(), backend="web", road_popup="panel").html
    assert '_popupMode = "panel"' in panel and 'className="rs-info"' in panel.replace("'", '"')
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

"""Web (MapLibre) backend: client-side recolouring via color_options + the recolour hooks."""
import json
import math
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from light import light
from shapely.geometry import LineString

from roadstyle import Overlay, compute_levels, render_edges

_KEY_UNIT = 100_000_000      # the pieces' sort keys: one drawing position


def _in(needle, html):
    """A JSON fragment in a page, in either engine's spacing: Python's json.dumps (", ", ": ") or serde_json's compact text."""
    return needle in html or needle.replace(": ", ":").replace(", ", ",") in html


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
    """Pull the inlined MapLibre style JSON back out of the page, with the page's road table as ``_roads`` (road_table.roads_of)."""
    from road_table import roads_of
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + len("const style = "))[0]
    style["_roads"] = roads_of(html)
    return style


def _stages(gdf, **kw):
    """The page's style with every stage value on its features (R1: the page writes only the properties that are read): render's build
    just before the page (its _palette_copy hook), with the roads and their stage values as ``_roads``."""
    out = render_edges(gdf, **{"backend": "web", **kw}, _palette_copy=True)
    out["style"]["_roads"] = out["geo"]
    return out["style"]


def _opt(html, key):
    """One option of the page's rsDashboard call (RS_OPTIONS in static/web_template.html), as a Python value."""
    at = html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = ")
    return json.JSONDecoder().raw_decode(html, at)[0][key]


def test_web_color_options_bake_variants_and_wire_recolour():
    wm = render_edges(_edges(), backend="web", palette="mono", color_options={
        "Class": {},
        "AADT": {"color_by": "aadt", "cmap": "viridis"},
        "Speed": {"color_by": "speed_kph", "cmap": "magma"},
    })
    style = _style(wm.html)
    p = style["_roads"]["features"][0]["properties"]
    # option 0 owns __rs_fill; the rest bake a distinct fill prop per edge
    assert "__rs_fill" in p and "__rs_fill__1" in p and "__rs_fill__2" in p
    # the recolour hooks + the Colour-by control are present
    for needle in ("rsSetColorField", "RS_COLOR_OPTIONS", "setPaintProperty", "co-ctrl"):
        assert needle in wm.html
    assert '"AADT"' in wm.html and _in('"prop": "__rs_fill__1"', wm.html)


def test_web_color_option_missing_self_keeps_nan_color():
    g = _edges()
    g.loc[2, "aadt"] = None                       # a NaN in the numeric option's column
    base = {"Class": {}, "AADT": {"color_by": "aadt", "cmap": "viridis"}}
    inherit = _style(render_edges(g, backend="web", palette="mono", color_options=base).html)
    p_i = inherit["_roads"]["features"][2]["properties"]
    assert p_i["__rs_fill__1"] == p_i["__rs_fill"]      # default: NaN inherits the base fill
    base["AADT"]["missing"] = "self"
    own = _style(render_edges(g, backend="web", palette="mono", color_options=base).html)
    p_s = own["_roads"]["features"][2]["properties"]
    assert p_s["__rs_fill__1"] == "#cccccc"             # "self": NaN keeps the styler's nan_color


def test_web_no_color_options_is_unchanged():
    wm = render_edges(_edges(), backend="web")
    style = _style(wm.html)
    p = style["_roads"]["features"][0]["properties"]
    assert "__rs_fill__1" not in p            # no variants baked
    assert _opt(wm.html, "color_options") == []   # picker JS present but inert (empty)


def _copts(html):
    return json.dumps(_opt(html, "color_options"))


def test_web_color_by_bakes_its_legend():
    # the plain color_by/cmap path renders the styler's legend on the web backend (no dropdown —
    # one legend-only entry). legend=True is the default, matching folium.
    on = _copts(render_edges(_edges(), backend="web", color_by="aadt", cmap="viridis").html)
    assert '"legend"' in on and _in('"kind": "continuous"', on)   # continuous ramp legend baked
    assert _opt(render_edges(_edges(), backend="web", color_by="aadt", cmap="viridis").html, "legend") is True
    # legend=False is the page's option: the style keeps the legend data, the page hides the box (N32 step 2)
    off = render_edges(_edges(), backend="web", color_by="aadt", cmap="viridis", legend=False).html
    assert _copts(off) == on and _opt(off, "legend") is False




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
    assert ids.index("ov0-fill") < ids.index("roads-simple")     # zones under the roads
    assert ids.index("ov1-circle") > ids.index("roads-simple")   # POIs on top
    assert "ov0" in style["sources"] and "ov1" in style["sources"]
    # popup fields + toggle wiring present; overlay props preserved for the popup
    assert "handleOverlayClick" in wm.html and "ov-ctrl" in wm.html
    # placement is baked into the JS meta: click precedence follows the visual stacking
    meta = _opt(wm.html, "overlays")
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
    assert _opt(wm.html, "overlays") == []


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
    return _style(html)










# --- minzoom: hide minor classes when zoomed out --------------------------------------------------

def _road_filters(html):
    return {l["id"]: l.get("filter") for l in _style_of(html)["layers"]
            if l["id"] in ("roads-simple", "roads-fill", "roads-casing", "roads-low-fill", "roads-bridge-fill")}






def test_the_filter_panel_names_each_class_first_zoom():
    """roadstyle:controls.filter.minzoom (2026-10-25): the first zoom of each class of the panel that the class minzoom hides below a zoom,
    so the Roads box dims it; a dict's change is in it; None with minzoom=False."""
    from roadstyle.config import DEFAULT
    flt = _opt(render_edges(_many_edges(20), backend="web", minzoom={"residential": 9}).html, "filter")
    assert flt["minzoom"]["residential"] == 9 and set(flt["minzoom"]) <= set(flt["classes"]), flt
    assert all(flt["minzoom"].get(c) == DEFAULT.minzoom[c] for c in flt["classes"] if c != "residential" and DEFAULT.minzoom.get(c))
    assert _opt(render_edges(_many_edges(20), backend="web", minzoom=False).html, "filter")["minzoom"] is None












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
    tw = [f["properties"]["__rs_twoway"] for f in style["_roads"]["features"]]
    assert tw == [False, False, True, True]






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
    assert (_opt(flat, "camera")["pitch"], _opt(flat, "camera")["bearing"]) == (0, 0)
    tilted = render_edges(_edges(), backend="web", pitch=55, bearing=30).html
    assert (_opt(tilted, "camera")["pitch"], _opt(tilted, "camera")["bearing"]) == (55, 30)
    assert "pitch:cam.pitch, bearing:cam.bearing" in tilted and tilted.count("pitch:cam.pitch") == 2    # map init AND the fitBounds camera


def test_web_view_3d_flag():
    """view_3d=True is a perspective camera (camera settings pitch_3d) — NO terrain data: no DEM
    source, no style.terrain, no hillshade layer. Off by default."""
    wm = render_edges(_edges(), backend="web", view_3d=True)
    style = _style(wm.html)
    assert "terrain" not in style and "dem" not in style["sources"]
    assert "hillshade" not in [l["id"] for l in style["layers"]]
    assert _opt(wm.html, "camera")["pitch"] == 55
    flat = render_edges(_edges(), backend="web").html
    assert _opt(flat, "camera")["pitch"] == 0


def test_web_camera_toggle_control():
    """Every map carries the 2D/3D toggle button; its target pitch comes from terrain settings."""
    html = render_edges(_edges(), backend="web").html
    assert _opt(html, "pitch_3d") == 55 and 'b.textContent = map.getPitch()<5 ? "3D" : "2D"' in html




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
    assert "O.pick.map(id=>RS_PREFIX+id)" in html and _opt(html, "pick") == ["roads-simple"]   # the page gives the pick layers (R7)


def test_web_camera_max_pitch():
    """The tilt limit is a setting (camera.max_pitch, default 70; max_pitch= on a render call). Up to 60 deg
    MapLibre loads every tile at one zoom, so a road has one width on the whole screen. Above it the tiles get
    different zooms: a width that depends on zoom and feature is baked per tile, so it can step where two zooms
    meet, and past ~72 the tile cover explodes on large GeoJSON sources (roads stop rendering and hover/select
    dies with them). So 70 is the most a page tilts by default, and max_pitch=60 is the option that keeps the width exact."""
    html = render_edges(_edges(), backend="web").html
    assert _opt(html, "camera")["max_pitch"] == 70
    assert _opt(render_edges(_edges(), backend="web", max_pitch=60).html, "camera")["max_pitch"] == 60
    assert "calculateTileZoom=z=>z" in html                              # one tile zoom on the whole screen: a road has one width in a tilted view
    from roadstyle.config import StyleConfig as _C
    assert _C().camera["max_pitch"] == 70


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
    assert _opt(win, "street_view") == "window" and '_svWindow = O.street_view==="window"' in win
    assert "window.rsSetStreetView = rsSetStreetView;" in win and "maps/embed?pb=" in win
    link = render_edges(_edges(), backend="web", street_view=True).html  # the plain link instead
    assert _opt(link, "street_view") is True and "_streetView = !!O.street_view" in link
    assert "__STREET_VIEW__" not in win
    with pytest.raises(ValueError):
        render_edges(_edges(), backend="web", street_view="windows")


def test_google_3d_window_needs_the_key(monkeypatch):
    """google_3d=True: a map button and a floating Google 3D window with the Street View key; off by default, and an error without a key."""
    import pytest
    monkeypatch.delenv("GOOGLE_MAPS_KEY", raising=False)
    assert _opt(render_edges(_edges(), backend="web").html, "google_3d") is False
    h = render_edges(_edges(), backend="web", google_3d=True, street_view_key="AIzaTEST").html
    assert _opt(h, "google_3d") is True and _opt(h, "street_view_key") == "AIzaTEST" and "window.rsSetGoogle3D = rsSetGoogle3D;" in h
    assert "__GOOGLE_3D__" not in h and "__SELECT_COLOR__" not in h
    assert "elevation-tiles-prod/terrarium/" in h and "heights: Mapzen" in h     # the ground height under Google's center, credited
    with pytest.raises(ValueError, match="google_3d=True needs"):
        render_edges(_edges(), backend="web", google_3d=True)




def test_web_panel_search_always_reads_the_id():
    """The panel search finds a road by its id even when road_popup lists other fields: the id
    column (edge_id_col) and edge_ref are always searched (a custom list used to hide the id)."""
    html = render_edges(_edges(), backend="web", road_popup=["name"], popup_mode="panel").html
    assert '__EDGE_ID_COL__' not in html
    assert _opt(html, "edge_id_col") == "edge_id" and '_ID_KEYS = [...new Set([O.edge_id_col, "edge_ref"])]' in html
    assert '_popupFields.concat(_ID_KEYS' in html
    other = render_edges(_edges().assign(eid=[1, 2, 3]), backend="web", edge_id_col="eid", popup_mode="panel").html
    assert _opt(other, "edge_id_col") == "eid"


def test_web_panel_popup_mode_and_select_events():
    """road_popup="panel" routes the click read-out into the full-height side panel (curated
    fields); popup_mode="panel" does the same while keeping a custom field list; rs:select /
    rs:deselect CustomEvents fire in every mode for host pages."""
    panel = render_edges(_edges(), backend="web", road_popup="panel").html
    assert _opt(panel, "popup_mode") == "panel" and 'className="rs-side"' in panel.replace("'", '"')
    custom = render_edges(_edges(), backend="web", road_popup=["name"], popup_mode="panel").html
    assert _opt(custom, "popup_mode") == "panel" and _opt(custom, "road_popup") == ["name"]
    default = render_edges(_edges(), backend="web").html
    assert _opt(default, "popup_mode") == "popup"
    for html in (panel, default):
        assert '_emit("rs:select"' in html and '_emit("rs:deselect"' in html          # the page sends both events (core.js, _emit)


def test_render_edges_scoped_settings():
    """render_edges(..., settings=...) applies a settings override for that one render only —
    no files, no lingering global state."""
    styled = render_edges(_edges(), backend="web",
                          settings={"config": {"labels": {"color": "#123123"}}}).html
    assert _in('"#123123"]', styled)              # the light colour, the else of the theme's case (a live page has a dark colour beside it)
    plain = render_edges(_edges(), backend="web").html
    assert _in('"#5b5b5b"]', plain)      # fully restored afterwards


def test_overlay_defaults_come_from_settings():
    """Overlay styling defaults live in the `overlays` settings block (per-Overlay values win)."""
    from roadstyle import Overlay
    styled = render_edges(_edges(), backend="web", overlays=[Overlay(_pois())],
                          settings={"config": {"overlays": {"color": "#112233", "radius": 11}}}).html
    assert "#112233" in styled and _in('"circle-radius": 11', styled)
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
    assert "basemaps.cartocdn.com" not in wm.html and "arcgisonline" not in wm.html        # no tile URL (the dashboard's own code names the provider)


def test_blank_basemap_with_switcher_precreates_hidden_raster():
    """blank active + tiled maps offered: the raster layer exists but starts hidden, so the
    dropdown can flip visibility without adding sources at runtime."""
    wm = render_edges(_edges(), backend="web", basemap="blank",
                      basemaps=["blank", "voyager"])
    style = _style(wm.html)
    raster = next(l for l in style["layers"] if l["id"] == "basemap")
    assert raster["layout"] == {"visibility": "none"}
    assert style["sources"]["bm"]["tiles"]           # voyager tiles, ready to show
    entries = _opt(wm.html, "basemaps")
    assert entries[0]["tiles"] == [] and entries[0]["bg"] == "#efede8"


def test_basemap_maxzoom_reaches_the_page():
    """Past a provider's last level MapLibre must scale that level up. Esri's grey maps end at 16
    and answer beyond it with HTTP 200 and a placeholder image, so without maxzoom the map went
    grey from zoom 17. Switching rebuilds the source, so every switcher entry carries its own."""
    wm = render_edges(_edges(), backend="web", basemap="esri_gray",
                      basemaps=["esri_gray", "osm", "blank"])
    assert _style(wm.html)["sources"]["bm"]["maxzoom"] == 16
    entries = _opt(wm.html, "basemaps")
    assert {e["key"]: e["maxzoom"] for e in entries if e["key"] in ("esri_gray", "osm", "blank")} == {"esri_gray": 16, "osm": 19, "blank": 19}
    assert {"esri_dark_gray", "blank_dark"} <= {e["key"] for e in entries}                   # a map with a dark twin brings the twin (the theme switches to it)
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
    assert [e["key"] for e in _opt(wm.html, "basemaps")] == ["voyager", "blank", "blank_dark"]       # blank brings its dark twin
    assert _opt(wm.html, "basemap_switcher") is False
    # without an explicit list, only the fixed backdrop is baked (nothing to switch to)
    wm2 = render_edges(_edges(), backend="web", basemap_switcher=False)
    assert len(_opt(wm2.html, "basemaps")) == 1


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
            for i, f in enumerate(style["_roads"]["features"])}
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
    assert _opt(on, "street_view") == "window" and "map_action=pano" in on
    off = render_edges(_edges(), backend="web", street_view=False).html
    assert _opt(off, "street_view") is False
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
    assert 'const lay=RS_LEAN || RS_PREFIX+"roads-fill"' in on and 'map.getPaintProperty(lay, "line-offset")' in on
    assert 'map.on("move", _svMarkPlace);' in on


def test_basemap_button_is_a_map_control_in_the_top_right_column():
    html = render_edges(_edges(), backend="web", basemaps=["positron", "osm"]).html
    # added with map.addControl like 2D/3D and Street View, not appended to <body>
    assert "bm-ctrl" in html and "maplibregl-ctrl maplibregl-ctrl-group bm-ctrl" in html
    assert "document.body.appendChild(menu)" not in html
    # its placement outranks a host page's old `.bm-icon{right:...}` workaround
    assert ".maplibregl-ctrl .bm-menu{position:absolute !important" in html


def test_zoom_readout_is_on_by_default_and_can_be_turned_off():
    assert _opt(render_edges(_edges(), backend="web").html, "zoom_readout") is True
    assert _opt(render_edges(_edges(), backend="web", zoom_readout=False).html, "zoom_readout") is False







def _eval(e, p):
    """Evaluate the few MapLibre expression operators the road band filters and the state expressions use, on properties p; the page state
    (global-state) is p["$state"]."""
    if not isinstance(e, list):
        return e
    op, a = e[0], e[1:]
    if op == "global-state":
        return p.get("$state", {}).get(a[0])
    if op == "get":
        obj = _eval(a[1], p) if len(a) > 1 else p
        return (obj or {}).get(_eval(a[0], p))
    if op == "has":
        return _eval(a[0], p) in ((_eval(a[1], p) if len(a) > 1 else p) or {})
    if op == "to-string":
        v = _eval(a[0], p)
        return "" if v is None else str(v)
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
    if op == "literal":
        return a[0]
    if op == "at":
        lst = _eval(a[1], p)
        return lst[int(_eval(a[0], p))]
    if op == "match":                                               # the class minzoom (on by default since 2026-10-25)
        x = _eval(a[0], p)
        for lab, v in zip(a[1:-1:2], a[2:-1:2], strict=True):
            if x in (lab if isinstance(lab, list) else [lab]):
                return _eval(v, p)
        return _eval(a[-1], p)
    x, y = _eval(a[0], p), _eval(a[1], p)
    return {"==": x == y, "<": x < y if op == "<" else None, ">": x > y if op == ">" else None, ">=": x >= y if op == ">=" else None}[op]






def test_tunnels_toggle_like_bridges():
    """A Tunnels on/off row next to Bridges (rsSetTunnels): only when the data has tunnels; it
    hides every lvl < 0 feature (roads, names, arrows, mouths), not the bridge decks."""
    g = gpd.GeoDataFrame({"highway": ["primary", "primary"], "tunnel": ["yes", None]},
                         geometry=[LineString([(18.0, 59.30), (18.01, 59.30)]),
                                   LineString([(18.01, 59.30), (18.02, 59.30)])], crs=4326)
    html = render_edges(g, backend="web").html
    assert _in('"tunnels": true', html) and "function rsSetTunnels(" in html
    assert '[">=",["coalesce",["get",lvl],0],0]' in html                     # lvl: the piece's level, or an attached item's baked __rs_lvl
    plain = render_edges(_edges(), backend="web").html
    assert _in('"tunnels": false', plain)






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






def _roads_of(html):
    return [f["properties"] for f in _style(html)["_roads"]["features"]]




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


def _bare(e):
    """A zoom curve without the width factor of N8 in its stops (each ``["*", stop, rs_w]``: no feature state set, the factor is 1)."""
    from roadstyle.render_web import _RS_W
    return [x[1] if isinstance(x, list) and len(x) == 3 and x[0] == "*" and x[2] == _RS_W else x for x in e] if isinstance(e, list) else e


def _num(e, p):
    """A width or offset stop on a feature's properties (+, * and what render_web._ev reads; no feature state set)."""
    from roadstyle.render_web import _ev
    if isinstance(e, list) and e and e[0] == "coalesce":
        for x in e[1:]:
            if isinstance(x, list) and x and x[0] == "feature-state":
                continue
            v = _num(x, p)
            if v is not None:
                return v
        return None
    if isinstance(e, list) and e and e[0] in ("+", "*", "-", "max"):
        v = [_num(x, p) for x in e[1:]]
        return {"+": sum(v), "*": v[0] * v[1] if len(v) == 2 else None, "-": v[0] - v[1] if len(v) == 2 else -v[0], "max": max(v)}[e[0]]
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










def _twin_caps(g, **kw):
    """(casing cap at a, at b, fill caps by (edge, point)) of a drawn pair: a = (18, 59.30), b = (18, 59.301); a piece's cap counts at each of
    its end points that are a or b (a whole piece: both ends, a half: its own)."""
    a, b = (18.0, 59.30), (18.0, 59.301)
    style = _style(render_edges(g, **{**_TWIN_KW, **kw}).html)
    src = style["sources"]["simple"]["data"]["features"]
    hv = style["sources"]["halves"]["data"]["features"] if "halves" in style["sources"] else []
    cas, fills = {}, {}
    for f in src + hv:
        p, c = f["properties"], [tuple(x) for x in f["geometry"]["coordinates"]]
        into = fills if p.get("__rs_k") == 1 or f in hv else cas
        if into is cas and (f["id"] != 0 or p.get("__rs_main") or p.get("__rs_seam")):
            continue
        for pt in {c[0], c[-1]} & {a, b}:
            into[(f["id"], pt) if into is fills else pt] = p.get("__rs_cap")
    return cas, fills








def test_label_size_stops_from_the_settings():
    """2026-10-10: config labels.size [[zoom, px], ...] sets the names' size at every zoom, for every class; halo from the same settings."""
    st = _style(render_edges(_pairs().assign(name="Main Street"), backend="web", settings={"config": {"labels": {"size": [[20, 16], [16, 11]], "halo_color": "#fff", "halo_width": 1.5}}}).html)
    lab = next(l for l in st["layers"] if l.get("layout", {}).get("text-size") and l["layout"].get("symbol-placement") == "line-center")
    assert lab["layout"]["text-size"] == ["interpolate", ["linear"], ["zoom"], 16.0, 11.0, 20.0, 16.0]
    assert light(lab["paint"]["text-halo-color"]) == "#fff" and lab["paint"]["text-halo-width"] == 1.5




def test_a_two_way_pair_that_disagrees_is_named_in_a_warning():
    """The pair's casing is the first edge's: the twins must agree, reversed (casing numbers, heads, caps). One that does not is named."""
    import warnings
    ok = _twin([(1, "a", "b", -1, 0, 1, 1, "yes", None), (2, "b", "a", 1, 0, -1, 1, None, "yes")])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings("ignore", message="CARTO base map requested with no API key")    # CI has no key: not the twins' warning
        render_edges(ok, **_TWIN_KW, edge_id_col="edge_id")
    for bad in (ok.assign(ce=[1, 0]), ok.assign(cap_e=[None, None])):
        with pytest.warns(UserWarning, match=r"twin_casing: 1 two-way pair.*: 1 / 2"):
            render_edges(bad, **_TWIN_KW, edge_id_col="edge_id")












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














def _metre_map(**kw):
    """Two parallel lanes 3.25 m apart (one 3.25 m wide, one without a width) and a plain road."""
    g = gpd.GeoDataFrame({"highway": ["residential"] * 3, "w": [3.25, None, 5.0]},
                         geometry=[LineString([(18.00, 59.30), (18.01, 59.30)]),
                                   LineString([(18.00, 59.30003), (18.01, 59.30003)]),
                                   LineString([(18.00, 59.31), (18.01, 59.31)])], crs=4326)
    st = _stages(g, simple=False, **kw)
    width = {ly["id"]: ly["paint"]["line-width"] for ly in st["layers"] if "line-width" in ly.get("paint", {})}
    return st["_roads"]["features"], width


def _stop(expr, z):
    return expr[expr.index(z, 3) + 1]










def _tunnel_conf(html):
    return _opt(html, "tunnel")












def _pos_id(root, level):
    return root if level == 0 else f"{root}-lv{level}"




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












def test_compute_levels_lp_stages():
    """Python's solver (HiGHS, its stages and time limit), so engine="python". The real LP (docs/design/levels_split_casing.md, section 7): nothing to violate is one LP (stage 0); a stack deeper than the range (max_level) is infeasible, so the
    stages 1-3 run with slacks, one pair is given up and a warning is raised; the margin only scales the numbers; the numbers stay integers with the default margin."""
    import pytest
    pytest.importorskip("scipy")
    import warnings as _w

    import roadstyle as rs
    d = 0.001
    rows = [LineString([(18 - 2 * d, 59), (18 + 2 * d, 59)]), LineString([(18, 58.998), (18, 59.002)]),
            LineString([(18 - 2 * d, 58.998), (18 + 2 * d, 59.002)]), LineString([(18 - 2 * d, 59.002), (18 + 2 * d, 58.998)])]     # four long roads crossing at one point
    g = gpd.GeoDataFrame({"highway": ["primary"] * 4, "band": [0, 1, 2, 3]}, geometry=rows, crs=4326)
    ok = rs.compute_levels(g, engine="python", method="solve", band_col="band")
    assert ok.attrs["levels_info"]["solves"] == 1 and ok.attrs["levels_given_up"] == [] and list(ok.fill_level) == [0, 1, 2, 3]
    half = rs.compute_levels(g, engine="python", method="solve", band_col="band", margin=0.5)                  # another margin: the same order
    assert list(half.fill_level) == [0, 1, 2, 3] and half.attrs["levels_given_up"] == []
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        tight = rs.compute_levels(g, engine="python", method="solve", band_col="band", max_level=1)          # three positions only: a stack of four cannot fit
    assert tight.attrs["levels_info"]["solves"] == 3 and len(tight.attrs["levels_given_up"]) == 1      # no near rules: no stage 3
    assert any("could not be satisfied" in str(w.message) for w in caught)
    assert all(isinstance(v, int) for v in tight.fill_level)
    fits = rs.compute_levels(g, engine="python", method="solve", band_col="band", max_level=1, margin=0.5)    # a smaller margin: the same range holds four positions
    assert fits.attrs["levels_given_up"] == [] and list(fits.fill_level) == [0, 1, 2, 3]
    for bad in (dict(margin=0), dict(max_level=0), dict(margin=-1)):
        with pytest.raises(ValueError):
            rs.compute_levels(g, engine="python", method="solve", band_col="band", **bad)


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
    """Python's solver (HiGHS, its stages and time limit), so engine="python". levels_info["solver"] is "flow" when stage 0 is solved as a flow, "highs" when the slack stages are needed."""
    g = _tunnel_world(True)
    assert compute_levels(g, engine="python", method="solve", order="class").attrs["levels_info"]["solver"] == "flow"


def test_the_example_of_the_design_document_7_5_1():
    """An upper road u over a lower road l: a_u <= b_u, a_l <= b_l, b_l + 1 <= a_u; the numbers are a_u = b_u = 1, a_l = b_l = 0 (docs/design/levels_split_casing.md, 7.5.1)."""
    import numpy as np
    import scipy.sparse as sp

    from roadstyle.levels import _difference_lp
    A = sp.csr_matrix(([1.0, -1.0, 1.0, -1.0, 1.0, -1.0], ([0, 0, 1, 1, 2, 2], [0, 1, 2, 3, 3, 0])), shape=(3, 4))      # variables a_u, b_u, a_l, b_l
    x = _difference_lp(np.array([-1.0, 1.0, -1.0, 1.0]), A, np.array([0.0, 0.0, -1.0]), 40)
    assert x.tolist() == [1.0, 1.0, 0.0, 0.0]


def test_min_positions_keeps_the_requirements_and_never_uses_more_positions():
    """Python's solver (HiGHS, its stages and time limit), so engine="python". docs/design/levels_split_casing.md, 7.3.1: the span term has a lower priority than a stack or an order wish, so nothing more is given up; the positions are never more than
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
        a, b = compute_levels(g, engine="python", order="class", min_positions=False), compute_levels(g, engine="python", order="class")        # the option is on by default
        assert len({v for c in cols for v in b[c]}) <= len({v for c in cols for v in a[c]})
        assert len(b.attrs["levels_given_up"]) == len(a.attrs["levels_given_up"])                # nothing more given up for fewer positions (random lines
        assert b.attrs["levels_info"]["order_violations"] == a.attrs["levels_info"]["order_violations"]   # cross near each other's heads: loops, docs/design/level_input.md)
    assert b.attrs["levels_params"]["min_positions"] is True and a.attrs["levels_params"]["min_positions"] is None
    assert compute_levels(g, engine="python", method="tags").attrs["levels_params"]["min_positions"] is None            # it does not apply to the tags method
    d = 0.001
    rows = [LS([(18 - 2 * d, 59), (18 + 2 * d, 59)]), LS([(18, 58.998), (18, 59.002)]),
            LS([(18 - 2 * d, 58.998), (18 + 2 * d, 59.002)]), LS([(18 - 2 * d, 59.002), (18 + 2 * d, 58.998)])]       # four roads crossing at one point, as in test_compute_levels_lp_stages
    cross = gpd.GeoDataFrame({"highway": ["primary"] * 4, "band": [0, 1, 2, 3]}, geometry=rows, crs=4326)
    assert list(compute_levels(cross, engine="python", band_col="band").fill_level) == [0, 1, 2, 3]
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        tight = compute_levels(cross, engine="python", band_col="band", max_level=1)      # the range is too small: the slack stages, with the span term in stage 3
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
    meta = _opt(html, "overlays")
    assert [m["select"] for m in meta] == ["road", "item"]
    circle = next(l for l in _style(html)["layers"] if l["id"].startswith("ov1-circle-lv"))
    assert '["case", ["boolean", ["feature-state", "select"], false], "#123456"' in json.dumps(circle["paint"]["circle-color"])





_CO = {"Class": {}, "AADT": {"color_by": "aadt", "cmap": "viridis"}}


def _marks():
    return gpd.GeoDataFrame({"n": [1]}, geometry=[LineString([(17.9, 59.37), (17.91, 59.38)]).centroid], crs=4326)


def test_views_are_baked_and_checked():
    """docs/design/core_model_and_views.md, views: each view is baked with its settings; a setting that is not known, or that names something
    the page does not have, is an error (no view is silently half applied)."""
    html = render_edges(_edges(), backend="web", color_options=_CO, overlays=[Overlay(_marks(), label="marks")],
                        views={"Flow": {"color": "AADT", "overlays": {"marks": False}}, "Casing": {"road_fill": False}}).html
    views = _opt(html, "views")
    assert views == [{"name": "Flow", "set": {"color": "AADT", "overlays": {"marks": False}}},
                     {"name": "Casing", "set": {"road_fill": False}}]
    fill = _opt(html, "road_fill")
    assert fill["on"] is True and not any(k.endswith("-pat") for k in fill["paint"])     # simple mode: roads-simple reads rs_fill_on
    assert _opt(render_edges(_edges(), backend="web").html, "views") == []                 # no views: no menu
    for bad in ({"colour": "AADT"}, {"color": "Speed"}, {"road_fill": 1}, {"overlays": {"lanes": True}},
                {"classes": ["trunk"]}, {"basemap": "nowhere"}):
        with pytest.raises(ValueError):
            render_edges(_edges(), backend="web", color_options=_CO, views={"V": bad})




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
    own = lambda c: light(c[-1][-1] if c[0] == "coalesce" else c[-1])    # noqa: E731 - inside the rsColor state: the hover / select case
    assert own(lay["ov0-line"]["paint"]["line-color"]) == "#ffffff" and own(lay["ov1-line"]["paint"]["line-color"]) == "#ff0000"   # the argument wins
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
    assert light(text["paint"]["text-halo-color"]) == "#ffffff" and text["layout"]["text-size"] == 13 and st["glyphs"]
    with pytest.raises(ValueError, match="text_col"):
        render_edges(_edge_world(), backend="web", overlays=[Overlay(_line_overlay_data(), kind="text")])


def test_overlay_styles_work_for_overlays_attached_to_edges():
    """Attached to edges, each style is drawn at the position of its edge: a dashed line, a text and a metre-wide line each get their layers per (fill number, order)."""
    g = _edge_world()
    data = _line_overlay_data().assign(order=[1, 3])
    st = _style(render_edges(g, backend="web", road_fill=False, settings=_STYLES, overlays=[
        Overlay(data, edge_col="edge_id", order_col="order", style="dashed", label="a"), Overlay(data, edge_col="edge_id", order_col="order", style="street_name", label="b")], tiles=False).html)
    ids = [lyr["id"] for lyr in st["layers"]]
    assert any(i.startswith("ov0-line-lv") and "-o1" in i for i in ids) and any(i.startswith("ov1-text-lv") and "-o3" in i for i in ids)
    one = next(lyr for lyr in st["layers"] if lyr["id"].startswith("ov0-line-lv"))
    assert one["filter"][0] == "all"      # simple mode: the line items are drawn in the road layer, their dash a text on the pieces
    assert {f["properties"].get("__rs_dash") for f in st["sources"]["simple"]["data"]["features"] if f["properties"]["__rs_k"] == 5} == {"3,3"}


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




def test_level_input_and_solve_levels():
    """docs/design/level_input.md (2026-10-06): roads of different bands that only meet (a tunnel mouth) take the priority order, roads
    that cross take the band; with band_col the caller's bands decide everywhere; edits switch a pair off or add one; ids may name either
    direction of a road."""
    pytest.importorskip("scipy")

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


def test_an_area_keeps_its_edits_heads_and_caps_in_the_database(tmp_path):
    """Each solve of a database's area stores edits.csv / heads.csv / caps.csv in visualization.level_*; a new folder of that database
    gets them back, the text as it was (2026-10-20: one file holds everything)."""
    pytest.importorskip("scipy")
    duckdb = pytest.importorskip("duckdb")

    from roadstyle.level_area import make_area, solve_area
    edges = _edge_world().assign(edge_id=[101, 102, 103, 104])
    db, area = tmp_path / "area.duckdb", tmp_path / "area.levels"
    duckdb.connect(str(db)).close()
    make_area(edges, area, db=db, id_col="edge_id")
    (area / "heads.csv").write_text("road,start_m,end_m\n101,6.8,\n")
    (area / "caps.csv").write_text("road,start,end\n102,flat,\n")
    solve_area(area)
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT road, start_m, end_m FROM visualization.level_heads").fetchall() == [(101, "6.8", "")]
    assert {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'visualization'").fetchall()} >= {
        "level_edits", "level_heads", "level_caps"}
    con.close()
    again = tmp_path / "again.levels"
    make_area(edges, again, db=db, id_col="edge_id")
    for f in ("edits.csv", "heads.csv", "caps.csv"):
        assert (again / f).read_text() == (area / f).read_text()


def test_heads_and_caps_may_name_either_direction_of_a_road(tmp_path):
    """heads.csv / caps.csv rows name a road by any of its edges, as edits.csv does: an edge running against its road swaps start and end;
    a row naming no road is an error, never left out."""

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
    roads, _ = rs.level_input(g.assign(lanes=[2, 1]))
    assert list(roads["modes"]) == ["driving + walking + cycling"]
    # and each edge's own, for the editor (2026-10-10: a one-way street's walking-only reverse showed every mode and the street's lanes)
    assert [list(roads[c][0]) for c in ("edges_modes", "reversed_modes", "edges_lanes", "reversed_lanes")] == [["driving + walking"], ["walking + cycling"], [2], [1]]








def test_the_road_tooltip_waits_for_the_mouse_to_rest():
    """hover_delay_ms (300 by default): the page waits this long before the road tooltip shows; 0 shows it at once."""
    assert _opt(render_edges(_edge_world(), backend="web", road_tooltip=True).html, "hover_delay_ms") == 300
    assert _opt(render_edges(_edge_world(), backend="web", road_tooltip=True, hover_delay_ms=0).html, "hover_delay_ms") == 0


def test_data_maxzoom_sets_the_last_cut_zoom_of_every_geojson_source():
    """data_maxzoom: every GeoJSON source of the page is cut into tiles up to that zoom only (above it MapLibre reuses them); default: MapLibre's own."""
    style = _style(render_edges(_edges(), backend="web", basemap="blank", data_maxzoom=17, tiles=False).html)
    geo = [s for s in style["sources"].values() if s["type"] == "geojson"]
    assert geo and all(s["maxzoom"] == 17 for s in geo)
    assert all("maxzoom" not in s for s in _style(render_edges(_edges(), backend="web", basemap="blank", tiles=False).html)["sources"].values() if s["type"] == "geojson")


def test_data_tolerance_sets_the_simplification_of_the_road_tile_sources():
    """data_tolerance: the GeoJSON sources that carry a tolerance (the roads) take it; default None keeps roadstyle's 0.05."""
    style = _style(render_edges(_edges(), backend="web", basemap="blank", data_tolerance=1, tiles=False).html)
    tol = [s["tolerance"] for s in style["sources"].values() if s["type"] == "geojson" and "tolerance" in s]
    assert tol and all(t == 1.0 for t in tol)
    base = _style(render_edges(_edges(), backend="web", basemap="blank", tiles=False).html)
    assert all(s["tolerance"] == 0.05 for s in base["sources"].values() if s["type"] == "geojson" and "tolerance" in s)


def test_the_last_solver_stage_at_its_time_limit_keeps_its_best_numbers(monkeypatch):
    """Python's solver (HiGHS, its stages and time limit), so engine="python". The last stage (cost, fewest positions) stopped by its time limit with numbers in hand: they are kept, with a warning and
    levels_info status TIME_LIMIT (a GitHub build of an all-modes area failed there, 2026-10-07); any other failure is still an error."""
    pytest.importorskip("scipy")
    import scipy.optimize as so

    import roadstyle as rs
    roads, pairs = rs.level_input(_edge_world())
    first = rs.solve_levels(roads, pairs, engine="python")
    fixed = {first["road"].iloc[0]: tuple(int(first[c].iloc[0]) for c in ("casing_start", "casing_level", "casing_end", "fill_level"))}
    real = so.milp

    def at_limit(*a, **k):
        r = real(*a, **k)
        r.status, r.message = 1, "Time limit reached."
        return r
    monkeypatch.setattr(so, "milp", at_limit)
    with pytest.warns(UserWarning, match="time limit"):
        out = rs.solve_levels(roads, pairs, fixed=fixed, engine="python")                  # held numbers: HiGHS, not the flow
    assert out.attrs["levels_info"]["status"] == "TIME_LIMIT" and out["fill_level"].notna().all()

    def failed(*a, **k):
        r = real(*a, **k)
        r.status, r.x, r.message = 4, None, "Other."
        return r
    monkeypatch.setattr(so, "milp", failed)
    with pytest.raises(RuntimeError, match="status 4"):
        rs.solve_levels(roads, pairs, fixed=fixed, engine="python")


def test_a_solver_stage_at_its_time_limit_without_an_answer_keeps_the_answer_of_the_stage_before(monkeypatch):
    """Python's solver (HiGHS, its stages and time limit), so engine="python". There is always an answer: a stage stopped by its time limit before it found one keeps the answer of the stage before (it holds every
    row so far), with a warning naming the stage and levels_info status TIME_LIMIT (a GitHub test run of Monaco failed there, 2026-10-08)."""
    pytest.importorskip("scipy")
    import scipy.optimize as so

    import roadstyle as rs
    d = 0.001
    rows = [LineString([(18 - 2 * d, 59), (18 + 2 * d, 59)]), LineString([(18, 58.998), (18, 59.002)]),
            LineString([(18 - 2 * d, 58.998), (18 + 2 * d, 59.002)]), LineString([(18 - 2 * d, 59.002), (18 + 2 * d, 58.998)])]
    g = gpd.GeoDataFrame({"highway": ["primary"] * 4, "band": [0, 1, 2, 3]}, geometry=rows, crs=4326)
    kw = dict(method="solve", band_col="band", max_level=1)                  # a stack of four in three positions: the staged solve
    real, calls = so.milp, []
    monkeypatch.setattr(so, "milp", lambda *a, **k: calls.append(1) or real(*a, **k))
    ok = rs.compute_levels(g, engine="python", **kw)
    n = len(calls)
    seen = []

    def at_limit(*a, **k):
        seen.append(1)
        r = real(*a, **k)
        if len(seen) >= stop:
            r.status, r.x, r.fun, r.message = 1, None, None, "Time limit reached."
        return r
    monkeypatch.setattr(so, "milp", at_limit)
    stop = n                                                                 # the last stage: the answer of the stage before is kept
    with pytest.warns(UserWarning, match="time limit"):
        out = rs.compute_levels(g, engine="python", **kw)
    assert out.attrs["levels_info"]["status"] == "TIME_LIMIT" and out["fill_level"].notna().all()
    assert len(out.attrs["levels_given_up"]) >= len(ok.attrs["levels_given_up"])
    seen.clear()
    stop = 2                                                                 # the first stage (after the plain solve): no answer to keep
    with pytest.raises(RuntimeError, match="Time limit"):
        rs.compute_levels(g, engine="python", **kw)












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
















def test_one_arrow_per_one_way_road_in_the_window(tmp_path):
    """docs/design/arrows_and_names.md (2026-10-06): a one-way road in the window has one arrow, in its visible part; the arrow stays
    where it is while it is in the window (a small pan keeps it), and a road whose arrow left the window gets one again. None below zoom 15."""
    pw = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "arrows.html"
    pts = [(18.0 + i * 0.001, 59.3) for i in range(41)]                       # one straight one-way street, about 2.3 km, many slots
    g = gpd.GeoDataFrame({"highway": ["primary"], "name": ["Long St"], "oneway": [True]}, geometry=[LineString(pts)], crs=4326)
    render_edges(g, backend="web", basemap="blank", tiles=False).save(path)
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
    render_edges(g, backend="web", basemap="blank", tiles=False).save(path)
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
    style = _style(render_edges(g, backend="web", basemap="blank", tiles=False).html)
    arrows = [l for l in style["layers"] if l["id"].startswith("roads-arrows")]
    assert arrows and all(l["layout"]["icon-allow-overlap"] is False and l["layout"]["icon-ignore-placement"] is True for l in arrows)
    ids = [l["id"] for l in style["layers"]]
    assert ids.index("roads-arrows") < ids.index("roads-labels")                      # names placed first




def _at_zoom(e, z):
    return z if e == ["zoom"] else [_at_zoom(x, z) for x in e] if isinstance(e, list) else e




def _simple_world():
    """Three roads with divided casings (as test_divided_casing_is_drawn_as_head_and_main_pieces), one a bridge, one a tunnel, one a footway (a dashed class)."""
    d = 0.001
    return gpd.GeoDataFrame({"highway": ["residential", "primary", "footway"], "bridge": [None, "yes", None], "tunnel": ["yes", None, None],
                             "cs": [-1, 0, 0], "cm": [0, 1, 0], "ce": [-2, 2, 0], "fl": [0, 2, 1]},
                            geometry=[LineString([(18, 59), (18 + d, 59)]), LineString([(18, 59.01), (18 + d, 59.01)]),
                                      LineString([(18, 59.02), (18 + d, 59.02)])], crs=4326)




def test_simple_tunnels_move_toward_the_chosen_tunnel_colour():
    """A tunnel in simple mode takes the tunnel look toward ``tunnel_toward`` at ``tunnel_strength`` from the start, as the full look
    (it moved toward slate until the page recoloured, 2026-10-08)."""
    kw = dict(backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", head_m=5.0)
    st = _style(render_edges(_simple_world(), **kw).html)
    color = json.dumps(next(l for l in st["layers"] if l["id"] == "roads-simple")["paint"]["line-color"])
    assert '"rs_tun_toward"' in color and '"rs_tun_strength"' in color                                 # the look reads the page state
    assert st["state"]["rs_tun_toward"]["default"] == "#d6cfc4" and st["state"]["rs_tun_strength"]["default"] == 60   # Sand at 60, the defaults
    navy = _style(render_edges(_simple_world(), settings={"config": {"tunnel_toward": "Navy", "tunnel_strength": 75}}, **kw).html)["state"]
    assert navy["rs_tun_toward"]["default"] == "#1e293b" and navy["rs_tun_strength"]["default"] == 75




def test_simple_has_the_tunnels_box_with_the_palette_and_dash_selects():
    html = render_edges(_edge_world(), backend="web", basemap="blank", tunnel_control=True).html
    assert _in('"control": true', html) and "TUNNEL.simple" not in html and "rsSetTunnelStyle=function" not in html     # one rsSetTunnelStyle: it sets state






def test_simple_dashed_class_fill_has_the_full_looks_dasharray():
    """The footway's fill (``__rs_dash`` "4,4" from the palette) is dashed per feature, butt ended, in the dash layer; a solid road has no
    dash (2f: only the dashed pieces are in a layer with line-dasharray)."""
    style = _style(render_edges(_simple_world(), backend="web", casing_level_col="cm", fill_level_col="fl", casing_start_col="cs", casing_end_col="ce", tiles=False).html)
    layer = next(l for l in style["layers"] if l["id"] == "roads-simple-dash")
    assert "line-dasharray" not in next(l for l in style["layers"] if l["id"] == "roads-simple")["paint"]
    foot = next(f["properties"] for f in style["sources"]["simple"]["data"]["features"] if f["id"] == 2)
    da = layer["paint"]["line-dasharray"]
    by = da[3]
    assert by[0] == "match" and foot["__rs_dash"] in by and by[by.index(foot["__rs_dash"]) + 1] == ["literal", [float(v) for v in foot["__rs_dash"].split(",")]]
    assert by[-1] == ["literal", [1, 0]]
    plain = render_edges(_edges(), backend="web", tiles=False).html
    assert "line-dasharray" not in json.dumps(next(l for l in _style(plain)["layers"] if l["id"] == "roads-simple")["paint"])      # no dash, no tunnel: nothing set




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
        get = "map.getGlobalState()"
        before = page.evaluate(get)
        assert page.evaluate("!!document.getElementById('tn-pal') && !!document.getElementById('tn-ratio')")
        page.evaluate("rsSetTunnelStyle({strength: 100, toward: 'Navy'})")
        after = page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({ratio: [3, 1], palette: 'One colour'})")
        last = page.evaluate(get)
        page.evaluate("rsSetTunnelStyle({strength: 0})")
        browser.close()
    assert before["rs_tun_strength"] == 60 and after["rs_tun_strength"] == 100 and after["rs_tun_toward"] == "#1e293b" and not errors, errors
    assert last["rs_tun_ratio"] == [3, 1] and last["rs_tun_two"] is False


def test_simple_puts_the_items_of_edges_above_the_road_layer():
    """Overlay(edge_col=...) in simple mode: the items after the one road layer, before the arrows / names / highlight."""
    g = _edge_world()
    pts = _edge_features([12, 13], order=[0, 0])
    style = _style(render_edges(g, backend="web", overlays=[Overlay(pts, edge_col="edge_id", order_col="order", kind="circle", label="i")]).html)
    ids = [l["id"] for l in style["layers"]]
    item = next(i for i, l in enumerate(style["layers"]) if l.get("source", "").startswith("ov"))
    assert ids.index("roads-simple") < item and all(ids.index(a) > item for a in ("roads-arrows", "roads-labels") if a in ids)


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
    feats = _style(render_edges(_simple_world(), **kw, tiles=False).html)["sources"]["simple"]["data"]["features"]
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




def test_an_unclassed_two_way_pair_pairs_and_the_warning_names_it():
    """Both directions of a road with no class (an area outline taken as a road) are a pair: one casing, a fill per direction (NaN != NaN
    made them two roads). render_edges warns once, with the count and the edge ids."""
    a, b = (18.00, 59.30), (18.00, 59.31)
    g = gpd.GeoDataFrame({"highway": [None, float("nan")], "edge_ref": ["w#2f", "w#2r"], "cs": 0, "cm": 0, "ce": 0, "fl": 0,
                          "cap_s": None, "cap_e": None}, geometry=[LineString([a, b]), LineString([b, a])], crs=4326)   # _TWIN_KW's columns
    with pytest.warns(UserWarning, match=r"2 edges have no 'highway' value.*w#2f, w#2r"):
        html = render_edges(g, **_TWIN_KW, tiles=False).html
    feats = _style(html)["sources"]["simple"]["data"]["features"]
    assert {f["id"] for f in feats if f["properties"]["__rs_k"] != 1} == {0}                  # one casing, the first edge's
    assert all(f["properties"].get("__rs_twoway", True) for f in feats) and sorted(f["id"] for f in feats if f["properties"]["__rs_k"] == 1) == [0, 1]


def _slots_of(lines, oneway=False):
    import json as _j

    import geopandas as gpd
    from shapely.geometry import LineString

    from roadstyle.render_web import _annotation_slots
    gdf = gpd.GeoDataFrame({"highway": [h for _, h, _ in lines], "name": [n for n, _, _ in lines]},
                           geometry=[LineString(c) for _, _, c in lines], crs=4326)
    g = _j.loads(gdf.to_json())
    for f in g["features"]:
        f["properties"]["__rs_oneway"] = oneway
    return _annotation_slots(g, 100)["features"]


def _x(f):
    c = f["geometry"]["coordinates"]
    return min(p[0] for p in c), max(p[0] for p in c)


_K43 = 111320.0 * math.cos(math.radians(43.7))








def test_name_layer_is_line_center_with_a_sort_key():
    style = _style(render_edges(_edges(), backend="web", arrows=True, labels=True).html)
    lab = next(l for l in style["layers"] if l["id"] == "roads-labels")
    assert lab["layout"]["symbol-placement"] == "line-center" and lab["layout"]["symbol-sort-key"][:2] == ["*", -1]


def _two_rules_edges():
    """Four streets, each an edge and its reverse (OSM-like columns: oneway from the driving network, driving, cycling): E the example
    (oneway=yes, oneway:bicycle=no: bikes both ways, cars one), T a two-way street, F a footway, W a one-way street whose reverse is for
    walking only."""
    ys = {"E": 59.300, "T": 59.310, "F": 59.320, "W": 59.330}
    hw = {"E": "residential", "T": "residential", "F": "footway", "W": "residential"}
    rows = [("E_f", True, True, True), ("E_r", False, False, True), ("T_f", False, True, True), ("T_r", False, True, True),
            ("F_f", False, False, False), ("F_r", False, False, False), ("W_f", True, True, True), ("W_r", False, False, False)]
    geo = [LineString([(18.003, ys[r[0][0]]), (18.000, ys[r[0][0]])] if r[0].endswith("_r") else [(18.000, ys[r[0][0]]), (18.003, ys[r[0][0]])])
           for r in rows]
    g = gpd.GeoDataFrame({"edge_id": [str(i) for i in range(len(rows))], "highway": [hw[r[0][0]] for r in rows], "ref": [r[0] for r in rows],
                          "oneway": [r[1] for r in rows], "driving": [r[2] for r in rows], "cycling": [r[3] for r in rows]}, geometry=geo, crs=4326)
    return g


def _two_rules_seen(m, refs):
    """What a page draws of each edge (two directions / one line) and where its arrows go: ({ref: two directions}, {ref of an arrow's
    edge: its slot's line, the way the arrow points})."""
    st = _style(m.html)
    ps = [f["properties"] for f in st["_roads"]["features"]]
    two = {refs[i]: bool(p.get("__rs_twoway")) for i, p in enumerate(ps)}
    arrows = {refs[f["id"]]: f["geometry"]["coordinates"]
              for f in st["sources"]["slots"]["data"]["features"] if f["properties"]["oneway"] and f["properties"]["slot"] % 2}
    return two, arrows






def _crossing_with_lanes(n=3, dash=False, **kw):
    """A road (edge 1) under a bridge (edge 2), each with ``n`` lane items (lines, metres), and the render's style."""
    from shapely.geometry import LineString

    from roadstyle import Overlay
    a, b = LineString([(18.060, 59.315), (18.064, 59.315)]), LineString([(18.062, 59.3135), (18.062, 59.3165)])
    roads = gpd.GeoDataFrame({"edge_id": [1, 2], "highway": ["residential"] * 2, "bridge": ["no", "yes"], "layer": [0, 1],
                              "oneway": ["yes", "yes"]}, geometry=[a, b], crs=4326)
    if not n:
        return render_edges(roads, backend="web", **{"tiles": False, **kw})
    lanes = gpd.GeoDataFrame([{"edge_id": e, "order": k, "w": 3.25, "off": k * 3.0, "c": "#00ff00", "geometry": g}
                              for e, g in ((1, a), (2, b)) for k in range(n)], crs=4326)
    if dash:
        lanes["d"] = [[2, 4] if k == 0 else None for k in lanes["order"]]
    ov = Overlay(lanes, edge_col="edge_id", order_col="order", color_col="c", width_m_col="w", offset_m_col="off", dash_col="d" if dash else None)
    return render_edges(roads, backend="web", overlays=[ov], **{"tiles": False, **kw})


def test_line_items_are_pieces_of_the_one_road_layer_at_their_edge_fill():
    """2026-10-09: in simple mode the line items attached to edges are drawn in the road layer at their edge's fill, by order: the lower road's
    lanes stay under the bridge's casing, each edge's items above its fill; road_fill=False hides the fills, not the items."""
    st = _style(_crossing_with_lanes(road_fill=False).html)
    plain = _style(_crossing_with_lanes(n=0).html)["sources"]["simple"]["data"]["features"]
    assert sum(f["properties"]["__rs_k"] == 1 for f in plain) == 2      # no items: both edges keep their fill
    fs = st["sources"]["simple"]["data"]["features"]
    key = lambda e, k: sorted(f["properties"]["r"] * 2 ** 32 + f["id"] for f in fs if f["id"] == e and f["properties"]["__rs_k"] == k)  # noqa: E731
    lo, hi = (min(f["id"] for f in fs), max(f["id"] for f in fs))
    assert len(key(lo, 5)) == len(key(hi, 5)) == 3
    assert len(key(lo, 1)) == len(key(hi, 1)) == 1    # an edge with items keeps its fill, under them
    assert max(key(lo, 1)) < min(key(lo, 5)) and max(key(hi, 1)) < min(key(hi, 5))
    assert max(key(lo, 5)) < min(key(hi, 0)) < min(key(hi, 5))
    item = next(f["properties"] for f in fs if f["properties"]["__rs_k"] == 5)
    assert item["__rs_ic"] == "#00ff00" and item["__rs_iwm"] > 3.25 and "lvl" in item and "__rs_cls" in item
    lyr = next(l for l in st["layers"] if l["id"] == "roads-simple")
    op = lyr["paint"]["line-opacity"][6]
    assert op == ["case", ["all", ["!", ["global-state", "rs_fill_on"]], ["==", ["get", "__rs_k"], 1]], 0, 1] and st["state"]["rs_fill_on"]["default"] is False   # the fills hidden, the items (__rs_k 5) drawn
    w = json.dumps(lyr["paint"]["line-width"])
    assert '["*", ["coalesce", ["get", "__rs_iwm"], 0], ' + str(round(512 * 2 ** 18 / 40075016.686, 6)) + "]" in w   # metres -> px at zoom 18
    assert lyr["paint"]["line-width"][:3] == ["interpolate", ["exponential", 2], ["zoom"]] and lyr["paint"]["line-width"][-2] == 22   # exact at every zoom
    assert "__rs_iom" in json.dumps(lyr["paint"]["line-offset"]) and "__rs_ic" in json.dumps(lyr["paint"]["line-color"])
    hits = [l for l in st["layers"] if l.get("source") == "ov0"]      # the item's own layers: the pick and the highlight only
    assert hits and all(l["paint"]["line-opacity"][0] == "case" for l in hits)


def _road_with_items():
    """One road (edge 1) with two lane items of render(items=...): a picked, unseen lane and a lane line."""
    from shapely.geometry import LineString
    a = LineString([(18.060, 59.315), (18.064, 59.315)])
    roads = gpd.GeoDataFrame({"edge_id": [1], "highway": ["residential"], "oneway": ["yes"]}, geometry=[a], crs=4326)
    items = gpd.GeoDataFrame([{"edge_id": 1, "order": 0, "width_m": 3.0, "color": "rgba(0,0,0,0)", "pick": True, "lane_id": "1_1", "geometry": a},
                              {"edge_id": 1, "order": 1, "width_m": 0.15, "color": "#ffffff", "pick": False, "lane_id": "x", "geometry": a}], crs=4326)
    return roads, items


def test_road_items_are_pieces_of_the_road_layer_with_no_source_of_their_own():
    """2026-10-10: render(items=...) puts the road's own items (lanes, lines, marks) in the one road layer only: no overlay source or layer;
    a picked item keeps its own fields (the popup), the others only what the layer reads; items need simple mode."""
    roads, items = _road_with_items()
    html = render_edges(roads, backend="web", items=items, items_popup=["lane_id"], tiles=False).html
    st = _style(html)
    assert not [k for k in st["sources"] if k.startswith("ov")] and not [l for l in st["layers"] if l["id"].startswith("ov")]
    k5 = [f["properties"] for f in sorted((f for f in st["sources"]["simple"]["data"]["features"] if f["properties"]["__rs_k"] == 5),
                                          key=lambda f: (f["properties"]["r"], f["id"]))]
    assert [p.get("__rs_pick") for p in k5] == [True, None] and k5[0]["lane_id"] == "1_1" and "lane_id" not in k5[1]
    assert sum(f["properties"]["__rs_k"] == 1 for f in st["sources"]["simple"]["data"]["features"]) == 1        # the road keeps its fill
    assert _opt(html, "items") == {"label": "items", "popup": ["lane_id"], "layer": "roads-simple"}
    assert "feature-state" in json.dumps(next(l for l in st["layers"] if l["id"] == "roads-simple")["paint"]["line-color"])
    with pytest.raises(ValueError, match="simple"):
        render_edges(roads, backend="web", items=items, simple=False, tiles=False)


def test_a_click_on_a_road_item_selects_the_item_in_the_browser(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    roads, items = _road_with_items()
    path = tmp_path / "items.html"
    render_edges(roads, backend="web", basemap="blank", items=items, items_popup=["lane_id"], tiles=False).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded()", timeout=30_000)
        page.evaluate("map.jumpTo({center:[18.062, 59.315], zoom: 18})")
        page.wait_for_function("map.loaded()", timeout=30_000)
        page.evaluate("window._got=null; document.addEventListener('rs:select', e=>{ window._got=e.detail; })")
        pt = page.evaluate("(()=>{const q=map.project([18.062, 59.315]); return [q.x, q.y];})()")
        page.mouse.click(*pt)
        page.wait_for_function("window._got", timeout=10_000)
        got = page.evaluate("({item: _got.item && _got.item.properties.lane_id, road: _got.id, "
                            "sel: map.queryRenderedFeatures(map.project([18.062, 59.315]), {layers:['roads-simple'], filter:['to-boolean',['get','__rs_pick']]})"
                            ".map(f=>map.getFeatureState({source:'simple', id:f.id}).select)})")
        browser.close()
    assert got["item"] == "1_1" and got["road"] == 0 and got["sel"] == [True] and not errors, (got, errors)


def test_a_road_drawn_over_another_roads_lanes_is_what_a_click_finds(tmp_path):
    """2026-10-09 (Allée Lazare Sauvaigo over Tunnel Dorsale): where a road is drawn over another road's unseen, picked lanes, a hover or
    click finds the road on top, not the lane under it; away from it, the lane is still found."""
    pw = pytest.importorskip("playwright.sync_api")
    from shapely.geometry import LineString
    roads, items = _road_with_items()                                       # edge 1: a road with an unseen picked lane, at level 0
    over = LineString([(18.062, 59.314), (18.062, 59.316)])
    roads = gpd.GeoDataFrame(pd.concat([roads, gpd.GeoDataFrame({"edge_id": [2], "highway": ["pedestrian"], "oneway": ["no"]}, geometry=[over], crs=4326)],
                                       ignore_index=True), crs=4326)
    for c, v in (("cs", [0, 1]), ("cm", [0, 1]), ("ce", [0, 1]), ("fl", [0, 1])):
        roads[c] = v
    path = tmp_path / "over.html"
    render_edges(roads, backend="web", basemap="blank", items=items, items_popup=["lane_id"], casing_start_col="cs", casing_level_col="cm",
                 casing_end_col="ce", fill_level_col="fl").save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded()", timeout=30_000)
        page.evaluate("map.jumpTo({center:[18.062, 59.315], zoom: 18})")
        page.wait_for_function("map.loaded()", timeout=30_000)
        page.evaluate("new Promise(r => { map.once('idle', r); map.triggerRepaint(); setTimeout(r, 3000); })")
        at = lambda lng: page.evaluate(f"(()=>{{const f = pick(map.project([{lng}, 59.315])); return f && [f.id, !!f.item];}})()")   # noqa: E731
        crossing, beside = at(18.062), at(18.0605)
        browser.close()
    assert crossing == [1, False] and beside == [0, True], (crossing, beside)      # the pedestrian road (feature 1); the lane of road 0


def test_only_clickable_items_are_picked():
    """A non-interactive item (popup=[], no select="item": lanestyle's lane lines, arrows) is not a pick layer, so a click on it reaches the
    lane or road under it (2026-10-10: a click on a lane arrow selected the road, not the lane)."""
    html = render_edges(_edges(), backend="web").html
    assert "OVERLAYS.filter(o=>o.base && (o.interactive || o.select===\"item\"))" in html






def test_a_saved_rule_that_is_not_kept_names_its_loop():
    """2026-10-09 (Allée Lazare Sauvaigo): a rule already in edits.csv that the solver cannot keep is "not kept", with the rules of its loop,
    not only "already there"; one that holds is a duplicate. A over B, B over C as stacks, C's fill after A's as an order: the order loops."""

    from roadstyle.levels import rule_conflicts
    roads = pd.DataFrame({"road": ["A", "B", "C"], "edges": [[], [], []], "reversed": [[], [], []]})
    pairs = pd.DataFrame([{"relation": "stack", "a": "A", "b": "B", "a_end": p, "b_end": ""} for p in ("start", "main", "end")]
                         + [{"relation": "stack", "a": "B", "b": "C", "a_end": p, "b_end": ""} for p in ("start", "main", "end")])
    wish = {"relation": "order", "a": "C", "b": "A", "a_end": "", "b_end": "", "enabled": "true"}
    ((_, why, rules),) = rule_conflicts(roads, pairs, pd.DataFrame([wish]), [wish])
    assert why == "not kept" and {r["relation"] for r in rules} == {"stack"} and {(r["a"], r["b"]) for r in rules} == {("A", "B"), ("B", "C")}
    kept = {"relation": "order", "a": "A", "b": "C", "a_end": "", "b_end": "", "enabled": "true"}
    ((_, why, _),) = rule_conflicts(roads, pairs, pd.DataFrame([kept]), [kept])
    assert why == "duplicate"




def test_a_road_item_with_a_minzoom_shows_from_that_zoom():
    """items= ``minzoom`` (2026-10-10, zebra stripes): baked as ``__rs_imz`` and kept out of the one road layer below that zoom; no item with one:
    no such filter."""
    roads, items = _road_with_items()
    plain = next(l for l in _style(render_edges(roads, backend="web", items=items, tiles=False).html)["layers"] if l["id"] == "roads-simple")
    assert "__rs_imz" not in json.dumps(plain.get("filter"))
    st = _style(render_edges(roads, backend="web", items=items.assign(minzoom=[None, 17.0]), tiles=False).html)
    lyr = next(l for l in st["layers"] if l["id"] == "roads-simple")
    assert ["any", ["!", ["has", "__rs_imz"]], [">=", ["zoom"], ["get", "__rs_imz"]]] in lyr["filter"]
    assert [f["properties"].get("__rs_imz") for f in st["sources"]["simple"]["data"]["features"] if f["properties"]["__rs_k"] == 5] == [None, 17.0]


def test_a_solve_never_deletes_the_tables_of_your_edits(tmp_path):
    """The tables are the master (2026-10-20): a folder that has no heads.csv (a new one, or one that lost it) leaves level_heads in the database."""
    pytest.importorskip("scipy")
    duckdb = pytest.importorskip("duckdb")

    from roadstyle.level_area import make_area, solve_area
    edges = _edge_world().assign(edge_id=[101, 102, 103, 104])
    db, area = tmp_path / "area.duckdb", tmp_path / "area.levels"
    duckdb.connect(str(db)).close()
    make_area(edges, area, db=db, id_col="edge_id")
    (area / "heads.csv").write_text("road,start_m,end_m\n101,6.8,\n")
    solve_area(area)
    (area / "heads.csv").unlink()
    solve_area(area)                                                           # the folder has no heads.csv now
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT road, start_m FROM visualization.level_heads").fetchall() == [(101, "6.8")]
    con.close()


def test_stored_levels_can_be_read_for_some_of_the_edges(tmp_path):
    """load_area_levels(subset=True): a map of one mode of the file reads the order that was solved for all of them."""
    pytest.importorskip("scipy")
    duckdb = pytest.importorskip("duckdb")

    import roadstyle as rs
    from roadstyle.level_area import make_area, solve_area
    edges = _edge_world().assign(edge_id=[101, 102, 103, 104])
    db, area = tmp_path / "area.duckdb", tmp_path / "area.levels"
    duckdb.connect(str(db)).close()
    make_area(edges, area, db=db, id_col="edge_id")
    solve_area(area)
    con = duckdb.connect(str(db), read_only=True)
    full = rs.load_area_levels(con, edges)
    part = rs.load_area_levels(con, edges.iloc[[3, 1]], subset=True)
    assert list(part["edge_id"]) == [104, 102]
    assert list(part["fill_level"]) == [full["fill_level"][3], full["fill_level"][1]]               # the same numbers, in the order asked
    with pytest.raises(ValueError, match="not edges the stored levels were solved for"):
        rs.load_area_levels(con, edges.iloc[:2].assign(edge_id=[101, 999]), subset=True)
    with pytest.raises(ValueError, match="not the edges"):                                             # without subset: as before
        rs.load_area_levels(con, edges.iloc[:3])
    con.close()


def test_the_version_is_the_one_of_a_source_tree():
    """roadstyle imported from a checkout says the version of its pyproject.toml, not that of another installed copy."""
    import roadstyle as rs
    root = Path(rs.__file__).resolve().parents[2]
    if not (root / "pyproject.toml").is_file():
        pytest.skip("not a source tree")
    assert rs._source_version() == re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(), re.M).group(1)
    assert rs.__version__ == rs._source_version()

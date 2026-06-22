"""Web/JSON output layer: to_spec / to_geojson / to_html / to_iframe / save / save_spec."""
import json

import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import (
    load_spec,
    save,
    save_spec,
    to_geojson,
    to_html,
    to_iframe,
    to_spec,
)


def _edges():
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "primary", "residential"],
         "congestion": ["low", "moderate", "heavy"],
         "aadt": [25000, 8000, 1500]},
        geometry=[LineString([(17.9, 59.37), (17.91, 59.38)]),
                  LineString([(17.91, 59.38), (17.92, 59.38)]),
                  LineString([(17.92, 59.38), (17.92, 59.39)])],
        crs=4326)


def test_to_spec_shape_and_json_serialisable():
    spec = to_spec(_edges(), theme="dark")
    assert spec["roadstyle"].startswith("spec/")
    assert spec["crs"] == "EPSG:4326"
    assert spec["theme"] == "dark"
    assert spec["geojson"]["type"] == "FeatureCollection"
    assert len(spec["geojson"]["features"]) == 3
    json.dumps(spec)   # must be fully serialisable (raises if not)


def test_spec_features_carry_rs_props():
    spec = to_spec(_edges())
    p = spec["geojson"]["features"][0]["properties"]
    for key in ("__rs_fill", "__rs_w", "__rs_op", "__rs_casing", "__rs_cw", "__rs_class"):
        assert key in p
    assert p["__rs_fill"] == "#00E5FF"      # motorway, highsat
    assert p["__rs_class"] == "motorway"


def test_spec_carries_basemap_switcher_set():
    spec = to_spec(_edges(), theme="dark")
    # active base map + the full selectable set for the in-map switcher
    assert spec["basemap"]["key"] == "dark_matter"
    keys = [b["key"] for b in spec["basemaps"]]
    assert len(keys) > 1 and spec["basemap"]["key"] in keys
    assert all({"key", "label", "url", "is_dark"} <= set(b) for b in spec["basemaps"])


def test_spec_explicit_basemaps_include_active():
    # an explicit set that omits the active base map still gets it (prepended), so the switcher
    # can always show what's currently rendered
    spec = to_spec(_edges(), theme="dark", basemaps=["positron", "osm"])
    keys = [b["key"] for b in spec["basemaps"]]
    assert keys[0] == "dark_matter"            # active, prepended
    assert "positron" in keys and "osm" in keys


def test_spec_bakes_both_casings():
    # both light/dark casings are baked so the switcher can re-pick without rebuilding the spec
    spec = to_spec(_edges(), theme="dark")
    p = spec["geojson"]["features"][0]["properties"]   # motorway, highsat
    assert p["__rs_casing_light"] == "#007785"
    assert p["__rs_casing_dark"] == "#000000"
    assert p["__rs_casing"] == p["__rs_casing_dark"]   # active = dark theme's casing


def test_to_html_enables_basemap_switcher():
    html = to_html(_edges())
    assert "basemap:true" in html                      # widget on by default
    assert "_renderBaseMapSwitcher" in html and "L.control.layers" in html


def test_spec_numeric_legend():
    spec = to_spec(_edges(), color_by="aadt", cmap="viridis", vmin=0, vmax=25000)
    lg = spec["legend"]
    assert lg["kind"] == "continuous" and lg["vmin"] == 0 and lg["vmax"] == 25000
    assert len(lg["ramp"]) >= 2


def test_spec_categorical_legend():
    spec = to_spec(_edges(), color_by="congestion",
                   colors={"low": "#11D68F", "moderate": "#FFCF43", "heavy": "#F24E42"})
    assert spec["legend"]["kind"] == "categorical"
    labels = [e[0] for e in spec["legend"]["entries"]]
    assert "low" in labels and "heavy" in labels


def test_to_geojson():
    gj = to_geojson(_edges(), color_by="aadt", cmap="magma")
    assert gj["type"] == "FeatureCollection"
    assert "__rs_fill" in gj["features"][0]["properties"]


def test_to_html_full_and_fragment():
    page = to_html(_edges(), color_by="aadt", cmap="viridis", full=True)
    assert page.lstrip().startswith("<!DOCTYPE")
    assert "leaflet" in page and "L.geoJSON" in page
    frag = to_html(_edges(), color_by="aadt", cmap="viridis", full=False)
    assert frag.lstrip().startswith("<div")
    assert "<!DOCTYPE" not in frag


def test_to_iframe():
    ifr = to_iframe(_edges())
    assert ifr.startswith("<iframe") and "srcdoc=" in ifr


def test_save_and_load_spec_roundtrip(tmp_path):
    p = tmp_path / "spec.json"
    save_spec(_edges(), p, color_by="aadt", cmap="viridis")
    loaded = load_spec(p)
    assert loaded["roadstyle"].startswith("spec/")
    assert len(loaded["geojson"]["features"]) == 3
    # passing a prebuilt spec also works
    spec = to_spec(_edges())
    p2 = tmp_path / "spec2.json"
    save_spec(spec, p2)
    assert load_spec(p2)["theme"] == spec["theme"]


def test_save_html(tmp_path):
    p = tmp_path / "map.html"
    save(_edges(), p, color_by="congestion",
         colors={"low": "#11D68F", "moderate": "#FFCF43", "heavy": "#F24E42"})
    assert p.exists()
    assert "<!DOCTYPE" in p.read_text()


def test_spec_html_comparable_weight_to_folium():
    # Neither output double-embeds the geometry, so the stack-agnostic spec page — which inlines the
    # full roadstyle.js renderer (legend + filter + basemap switcher + selection) — stays within a
    # small factor of folium's full output (the folium InteractiveRoads layer embeds the GeoJSON
    # once, same as the spec). A regression that double-embedded would blow past ~2x.
    n = 400
    g = gpd.GeoDataFrame(
        {"highway": ["primary"] * n, "aadt": list(range(n))},
        geometry=[
            LineString([(17.9 + i * 1e-4, 59.3), (17.9 + i * 1e-4, 59.31)]) for i in range(n)
        ],
        crs=4326,
    )
    spec_html = to_html(g, color_by="aadt", cmap="viridis")
    from roadstyle import render_edges
    folium_html = render_edges(g, color_by="aadt", cmap="viridis", backend="folium").get_root().render()
    assert len(spec_html) <= len(folium_html) * 1.2


def test_to_html_inlines_canonical_renderer():
    # Single source of truth: to_html must inline the bundled static/roadstyle.js (the same file
    # used for standalone embeds), not a hand-written copy of the rendering logic.
    from roadstyle.emit import _asset

    js = _asset("roadstyle.js")
    assert "RoadStyleMap" in js
    assert "onSelect" in js and "getSelection" in js   # selection-result API present
    assert "_pinTooltip" in js                         # click-to-pin tooltip behaviour present
    html = to_html(_edges())
    # the exact canonical renderer is inlined, with any literal </script> neutralised (see below)
    assert js.replace("</script", "<\\/script") in html
    assert "new RoadStyleMap(" in html     # bootstrapped against the embedded spec


def test_to_html_neutralises_nested_script_close():
    # roadstyle.js's header has a usage example containing </script>; inlined raw it closes the
    # page's <script> early and the renderer spills onto the page as text (blank/broken map).
    from roadstyle.emit import _asset

    js = _asset("roadstyle.js")
    assert 'roadstyle.js"></script>' in js                 # the hazardous sequence is real
    html = to_html(_edges())
    assert 'roadstyle.js"></script>' not in html           # ...and is neutralised on inlining
    assert 'roadstyle.js"><\\/script>' in html             # escaped form present (renderer runs)

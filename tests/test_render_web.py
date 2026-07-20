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


def test_web_no_color_options_is_unchanged():
    wm = render_edges(_edges(), backend="web")
    style = _style(wm.html)
    p = style["sources"]["roads"]["data"]["features"][0]["properties"]
    assert "__rs_fill__1" not in p            # no variants baked
    assert "const COLOR_OPTIONS = [];" in wm.html   # picker JS present but inert (empty)


def test_web_arrows_and_labels_layers_present():
    wm = render_edges(_edges(), backend="web", arrows=True, labels=True)
    ids = [layer["id"] for layer in _style(wm.html)["layers"]]
    assert "roads-arrows" in ids and "roads-labels" in ids


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
    assert set(blobs) == {"roads"}                      # boundary-sized sources stay inline
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

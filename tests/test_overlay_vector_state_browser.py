"""The hover and the select look of an overlay on a vector-tile source: the feature state needs the source layer (MapLibre does not set a state on a
vector source without it), and the ids repeat in the layers of one source. The host page of test_host_page_gaps_browser; the tile is built here.
Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_host_page_gaps_browser import PNG, SQUARE, host  # noqa: E402, F401


def _var(n):
    out = bytearray()
    while n > 0x7F:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    return bytes(out + bytes([n]))


def _field(num, wire, body):
    return _var(num << 3 | wire) + (_var(len(body)) + body if wire == 2 else body)


def _square(x0, y0, x1, y1):
    zz = lambda v: v << 1 if v >= 0 else (-v << 1) - 1  # noqa: E731
    g = [9, zz(x0), zz(y0), 26, zz(x1 - x0), 0, 0, zz(y1 - y0), zz(x0 - x1), 0, 15]      # move, 3 lines, close (clockwise: an exterior ring)
    return b"".join(_var(v) for v in g)


def _tile():
    """One source layer, `ov0` (Studio: a source layer for each overlay), with two squares: ids 0 and 8."""
    feats = b"".join(_field(2, 2, _field(1, 0, _var(i)) + _field(3, 0, _var(3)) + _field(4, 2, _square(*box)))
                     for i, box in ((0, (500, 1000, 1500, 2000)), (8, (2500, 1000, 3500, 2000))))
    return _field(3, 2, _field(15, 0, _var(2)) + _field(1, 2, b"ov0") + feats + _field(5, 0, _var(4096)))


_AT = """([tx, ty]) => { const z = 14, n = 2 ** z, x = Math.floor((18.005 + 180) / 360 * n);
  const la = 59.305 * Math.PI / 180, y = Math.floor((1 - Math.log(Math.tan(la) + 1 / Math.cos(la)) / Math.PI) / 2 * n);
  const lng = (x + tx / 4096) / n * 360 - 180, lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * (y + ty / 4096) / n))) * 180 / Math.PI;
  map.jumpTo({center: [lng, lat], zoom: z}); const p = map.project([lng, lat]), r = map.getCanvas().getBoundingClientRect(); return [r.left + p.x, r.top + p.y]; }"""
_FS = "id => map.getFeatureState({source: 'rs-tiles', sourceLayer: 'ov0', id})"


_CASE = ["case", ["boolean", ["feature-state", "select"], False], "#7c4dff", ["boolean", ["feature-state", "hover"], False], "#b388ff", "#e5e2df"]


def _violet(page, xy):
    """The picture at a point: how much more blue than green it is (a grey building is about 0, a lit one is above 60)."""
    from io import BytesIO

    from PIL import Image
    r, g, b = Image.open(BytesIO(page.screenshot(clip={"x": xy[0], "y": xy[1], "width": 1, "height": 1}))).convert("RGB").getpixel((0, 0))
    return b - g


@pytest.mark.parametrize("three_d", [False, True])
def test_hover_and_select_set_the_state_with_the_source_layer(host, three_d):          # noqa: F811
    base, _ = host
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("http://rs.test/**", lambda r: r.fulfill(content_type="application/x-protobuf", body=_tile()) if r.request.url.endswith(".pbf")
                   else r.fulfill(content_type="image/png", body=PNG) if ".png" in r.request.url else r.fulfill(content_type="application/json", body="{}"))
        page.goto(base + "/page.html")
        page.wait_for_function("window.ready === true", timeout=60_000)
        # Studio's layout: the layers of an overlay (its entry names the source `ov0`) draw a source with another name, shared by all the overlays,
        # a source layer for each; a second source is for the low zooms
        style = {"version": 8, "sources": {"roadsrc": {"type": "geojson", "data": SQUARE},
                                          "tiles": {"type": "vector", "tiles": ["http://rs.test/v/{z}/{x}/{y}.pbf"], "maxzoom": 14},
                                          "low": {"type": "vector", "tiles": ["http://rs.test/l/{z}/{x}/{y}.pbf"], "maxzoom": 8}}, "metadata": {
            "roadstyle:controls": {"overlays": [{"label": "buildings", "source": "ov0", "layers": ["ov0-fill", "ov0-fill-low"], "interactive": True,
                                                 "popup": [], "tooltip": None, "color": "#f4f4f4"}]}},
            "layers": [{"id": "roads", "type": "line", "source": "roadsrc", "paint": {"line-width": 2}},
                       {"id": "ov0-fill-low", "type": "fill", "source": "low", "source-layer": "ov0", "maxzoom": 10, "paint": {"fill-color": "#39c"}},
                       {"id": "ov0-fill", "type": "fill", "source": "tiles", "source-layer": "ov0", "minzoom": 10, "paint": {"fill-color": _CASE}}]}
        if three_d:        # the 3D layer covers the fill: it has the same states (the engine gives it the case of the fill)
            style["layers"].append({"id": "ov0-3d", "type": "fill-extrusion", "source": "tiles", "source-layer": "ov0",
                                    "paint": {"fill-extrusion-color": _CASE, "fill-extrusion-height": 20, "fill-extrusion-opacity": 0.9}})
        page.evaluate("s => addStyle(s)", style)
        a = page.evaluate(_AT, [1000, 1500])
        page.wait_for_function("map.loaded() && map.queryRenderedFeatures({layers: ['rs-ov0-fill']}).length > 0", timeout=30_000)
        b = [a[0] + 2000 / 4096 * 512, a[1]]                                  # 512-px tiles at zoom 14: 1 tile unit = 512 / 4096 px
        page.mouse.move(1, 1)
        page.wait_for_timeout(500)
        rest = _violet(page, a)
        page.mouse.move(a[0] + 1, a[1])
        page.mouse.move(*a)
        page.wait_for_timeout(900)                                            # past the hover delay
        assert page.evaluate(_FS, 0).get("hover") is True and not page.evaluate(_FS, 8).get("hover"), (page.evaluate(_FS, 0), page.evaluate(_FS, 8))
        assert _violet(page, a) > rest + 60, (rest, _violet(page, a))        # the building looks lit, in 2D and under the 3D layer
        page.mouse.move(b[0] + 1, b[1])
        page.mouse.move(*b)
        page.wait_for_timeout(900)
        assert not page.evaluate(_FS, 0).get("hover") and page.evaluate(_FS, 8).get("hover") is True        # the ids 0 and 8 are not mixed up
        page.mouse.click(*b)
        page.wait_for_timeout(300)
        assert page.evaluate(_FS, 8).get("select") is True and not page.evaluate(_FS, 0).get("select")
        page.mouse.click(*a)
        page.wait_for_timeout(300)
        assert page.evaluate(_FS, 0).get("select") is True and not page.evaluate(_FS, 8).get("select")
        browser.close()
    assert not errors, errors

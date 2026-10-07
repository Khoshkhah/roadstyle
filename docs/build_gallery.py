"""Build the gallery thumbnails (docs/img/gallery/*.png) — one screenshot per signature look.

Renders the bundled Södermalm driving sample in each look and snapshots it headlessly via
:func:`rs.snapshot` (needs Playwright + Chromium); the hero and the two Street View shots go
through :func:`served_shot` instead (served over http, a road selected). Re-run after a visual
change (build ui/dashboard and ui/report first; not the studio shot, which is taken by hand)::

    python docs/build_gallery.py
"""
from __future__ import annotations

from pathlib import Path

import roadstyle as rs

EDGES = Path(__file__).resolve().parents[1] / "ui" / "studio" / "samples" / "sodermalm_driving.geojson"
OUT = Path(__file__).resolve().parent / "img" / "gallery"
OVERVIEW = dict(center=(18.065, 59.314), zoom=13.3)
BRIDGE = dict(center=(18.076, 59.304), zoom=16.4, pitch=58, bearing=-25)

LOOKS = [
    ("amber_voyager", "Amber palette on Voyager (the defaults)",
     dict(), OVERVIEW),
    ("highsat_voyager", "High-saturation palette on Voyager",
     dict(palette="highsat"), OVERVIEW),
    ("carto_positron", "OSM-Carto palette on Positron",
     dict(palette="carto", basemap="positron"), OVERVIEW),
    ("amber_dark", "Dark Matter base",
     dict(basemap="dark_matter"), OVERVIEW),
    ("mono_blank", "Mono palette on the blank (tile-less, offline) canvas",
     dict(palette="mono", basemap="blank", basemap_switcher=False), OVERVIEW),
    ("satellite", "Satellite imagery base",
     dict(basemap="satellite"), OVERVIEW),
    ("speed_datadriven", "Data-driven: coloured by maxspeed (plasma) with a legend",
     dict(color_by="maxspeed_kmh", cmap="plasma", legend=True, basemap="positron"), OVERVIEW),
    ("bridges_3d", "3D view: extruded, ramped, cased bridge decks",
     dict(view_3d=True), BRIDGE),
]


def main() -> None:
    if not EDGES.exists():
        raise SystemExit(f"sample not found: {EDGES}")
    OUT.mkdir(parents=True, exist_ok=True)
    import geopandas as gpd
    edges = gpd.read_file(EDGES)
    for name, _title, kw, cam in LOOKS:
        wm = rs.render_edges(edges, backend="web", **kw)
        rs.snapshot(wm, OUT / f"{name}.png", width=960, height=640, settle=4.0, **cam)
        print("wrote", name)
    hero(edges)
    street_view_shots(edges)
    print("wrote hero, street_view_window, street_view_side")
    # the sidebar templates (ui/dashboard, ui/report) — shot as pages, not WebMaps. Build them
    # first (their build.py writes the .html) so the shots reflect the current sidebars.
    root = Path(__file__).resolve().parents[1]
    for tmpl, png in (("dashboard", "dashboard"), ("report", "report")):
        page = root / "ui" / tmpl / f"{tmpl}.html"
        if page.exists():
            rs.snapshot(page, OUT / f"{png}.png", width=960, height=640, settle=4.0)
            print("wrote", png)


# Hornsgatan, where Google has car imagery: the camera, and the edge to select (by rsQuery order)
HORNSGATAN = """map.jumpTo({center: [18.0520, 59.3172], zoom: 15.6});"""
SELECT = """const ids = rsQuery(p => p.name === "Hornsgatan"); rsSelect(ids[30 % ids.length]);"""


def served_shot(html: str, png: Path, setup_js: str, width: int, height: int, scale: int = 1,
                camera: str = HORNSGATAN) -> None:
    """Screenshot a page with Street View in it.

    Not rs.snapshot: Street View loads only in a page served over http(s), and the shot needs
    clicks (select a road, open the window). ANGLE/SwiftShader because the default software GL of
    a GPU-less machine paints Google's WebGL panorama a second time, displaced, as a white box.
    Attribution (OSM, CARTO, Google) stays visible: their terms. Needs a CARTO key in the env.
    """
    import functools
    import http.server
    import tempfile
    import threading

    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "page.html").write_text(html, encoding="utf-8")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(channel="chromium", args=[
                    "--use-angle=swiftshader", "--use-gl=angle", "--enable-unsafe-swiftshader"])
                pg = b.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
                pg.goto(f"http://127.0.0.1:{srv.server_port}/page.html")
                pg.wait_for_function("window.map && map.loaded()", timeout=40000)
                pg.evaluate("localStorage.clear()")
                pg.evaluate(camera)
                pg.wait_for_timeout(1500)
                pg.evaluate("() => {" + setup_js + "}")
                pg.wait_for_timeout(8000)                 # the panorama and its tiles
                pg.screenshot(path=str(png))
                b.close()
        finally:
            srv.shutdown()


HIDE = "<style>.maplibregl-ctrl-bottom-left,.rs-zoom{display:none!important}</style></head>"


def hero(edges) -> None:
    """The README hero: the Street View window open on Hornsgatan, 1200x600 at 2x, as a JPEG."""
    from PIL import Image
    html = rs.render_edges(edges, filter_control=False, basemap_switcher=False, tunnel_control=False,
                           road_popup=False).html.replace("</head>", HIDE, 1)
    png = OUT / "hero.png"
    served_shot(html, png, SELECT + """rsSetStreetView(true);
        Object.assign(document.querySelector(".rs-svw").style,
                      {left: "610px", top: "215px", width: "560px", height: "355px"});""",
                1200, 600, scale=2)
    Image.open(png).convert("RGB").save(OUT.parent / "hero.jpg", quality=85, optimize=True)
    png.unlink()


def street_view_shots(edges) -> None:
    """Gallery: the Street View window (the default) and the side-by-side page."""
    served_shot(rs.render_edges(edges, road_popup=False).html, OUT / "street_view_window.png",
                SELECT + """rsSetStreetView(true);
        Object.assign(document.querySelector(".rs-svw").style,
                      {left: "400px", top: "250px", width: "500px", height: "330px"});""", 960, 640)
    served_shot(rs.render_street_view(edges, resizable=False, layout="below").html,
                OUT / "street_view_below.png", SELECT, 960, 640,
                camera="map.jumpTo({center: [18.0495, 59.3169], zoom: 15.6});")
    served_shot(rs.render_street_view(edges, resizable=False).html, OUT / "street_view_side.png",
                SELECT, 960, 640, camera="map.jumpTo({center: [18.0495, 59.3169], zoom: 15.6});")


if __name__ == "__main__":
    main()

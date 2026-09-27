"""Build the gallery thumbnails (docs/img/gallery/*.png) — one screenshot per signature look.

Renders the bundled Södermalm driving sample in each look and snapshots it headlessly via
:func:`rs.snapshot` (needs Playwright + Chromium). Re-run after a visual change::

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
    ("highsat_voyager", "High-saturation palette on Voyager (the defaults)",
     dict(), OVERVIEW),
    ("carto_positron", "OSM-Carto palette on Positron",
     dict(palette="carto", basemap="positron"), OVERVIEW),
    ("highsat_dark", "Dark Matter base",
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
    print("wrote hero")
    # the sidebar templates (ui/dashboard, ui/report) — shot as pages, not WebMaps. Build them
    # first (their build.py writes the .html) so the shots reflect the current sidebars.
    root = Path(__file__).resolve().parents[1]
    for tmpl, png in (("dashboard", "dashboard"), ("report", "report")):
        page = root / "ui" / tmpl / f"{tmpl}.html"
        if page.exists():
            rs.snapshot(page, OUT / f"{png}.png", width=960, height=640, settle=4.0)
            print("wrote", png)


def hero(edges) -> None:
    """The README hero: the map with the floating Street View window open on Hornsgatan, at 2x.

    Not rs.snapshot: Street View loads only in a page served over http(s), and the shot needs
    clicks (select a road, open the window). ANGLE/SwiftShader because the default software GL of
    a GPU-less machine paints Google's WebGL panorama a second time, displaced, as a white box.
    Attribution (OSM, CARTO, Google) stays visible: their terms. Needs a CARTO key in the env.
    """
    import functools
    import http.server
    import tempfile
    import threading

    from PIL import Image
    from playwright.sync_api import sync_playwright

    hide = "<style>.maplibregl-ctrl-bottom-left,.rs-zoom{display:none!important}</style></head>"
    page = rs.render_edges(edges, street_view="window", filter_control=False,
                           basemap_switcher=False, road_popup=False).html.replace("</head>", hide, 1)
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "hero.html").write_text(page, encoding="utf-8")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(channel="chromium", args=[
                    "--use-angle=swiftshader", "--use-gl=angle", "--enable-unsafe-swiftshader"])
                pg = b.new_page(viewport={"width": 1200, "height": 600}, device_scale_factor=2)
                pg.goto(f"http://127.0.0.1:{srv.server_port}/hero.html")
                pg.wait_for_function("window.map && map.loaded()", timeout=40000)
                pg.evaluate("map.jumpTo({center: [18.0520, 59.3172], zoom: 15.6})")
                pg.wait_for_timeout(1500)
                pg.evaluate("""() => { const ids = rsQuery(p => p.name === "Hornsgatan");
                                       rsSelect(ids[30 % ids.length]); rsSetStreetView(true);
                                       Object.assign(document.querySelector(".rs-svw").style,
                                         {left: "610px", top: "215px", width: "560px", height: "355px"}); }""")
                pg.wait_for_timeout(8000)                 # the panorama and its tiles
                png = OUT / "hero.png"
                pg.screenshot(path=str(png))
                b.close()
        finally:
            srv.shutdown()
    Image.open(png).convert("RGB").save(OUT.parent / "hero.jpg", quality=85, optimize=True)
    png.unlink()


if __name__ == "__main__":
    main()

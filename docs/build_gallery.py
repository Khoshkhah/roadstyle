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
    # the README hero: 2x pixel density, panels and buttons off (attribution stays: licence)
    hero = rs.render_edges(edges, view_3d=True, filter_control=False, basemap_switcher=False)
    hide = ("<style>.maplibregl-ctrl-top-right,.maplibregl-ctrl-bottom-left,.rs-zoom"
            "{display:none!important}</style></head>")
    png = OUT / "hero.png"
    rs.snapshot(hero.html.replace("</head>", hide, 1), png, width=1200, height=600, scale=2,
                settle=5.0, center=(18.074, 59.306), zoom=15.4, pitch=60, bearing=-20)
    from PIL import Image  # a JPEG is ~5x smaller than the PNG
    Image.open(png).convert("RGB").save(OUT.parent / "hero.jpg", quality=85, optimize=True)
    png.unlink()
    print("wrote hero")
    # the sidebar templates (ui/dashboard, ui/report) — shot as pages, not WebMaps. Build them
    # first (their build.py writes the .html) so the shots reflect the current sidebars.
    root = Path(__file__).resolve().parents[1]
    for tmpl, png in (("dashboard", "dashboard"), ("report", "report")):
        page = root / "ui" / tmpl / f"{tmpl}.html"
        if page.exists():
            rs.snapshot(page, OUT / f"{png}.png", width=960, height=640, settle=4.0)
            print("wrote", png)


if __name__ == "__main__":
    main()

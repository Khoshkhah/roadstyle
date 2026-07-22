"""Build the gallery thumbnails (docs/img/gallery/*.png) — one screenshot per signature look.

Renders the Södermalm driving network (duckOSM) in each look and snapshots it headlessly via
:func:`rs.snapshot` (needs Playwright + Chromium). Re-run after a visual change::

    python docs/build_gallery.py
"""
from __future__ import annotations

from pathlib import Path

import roadstyle as rs

DB = Path("/home/kaveh/projects/duckOSM/data/db/sodermalm.duckdb")
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
    if not DB.exists():
        raise SystemExit(f"DuckDB not found: {DB}")
    OUT.mkdir(parents=True, exist_ok=True)
    edges = rs.from_duckosm(DB)
    for name, _title, kw, cam in LOOKS:
        wm = rs.render_edges(edges, backend="web", **kw)
        rs.snapshot(wm, OUT / f"{name}.png", width=960, height=640, settle=4.0, **cam)
        print("wrote", name)
    # the sidebar-dashboard template (ui/dashboard) — shot as a page, not a WebMap
    dash = Path(__file__).resolve().parents[1] / "ui" / "dashboard" / "dashboard.html"
    if dash.exists():
        rs.snapshot(dash, OUT / "dashboard.png", width=960, height=640, settle=4.0)
        print("wrote dashboard")


if __name__ == "__main__":
    main()

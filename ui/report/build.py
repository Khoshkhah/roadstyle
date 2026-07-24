"""Build a working report page.

Thin wrapper over the packaged :func:`roadstyle.render_report` — the map with a stats-forward
sidebar (headline counts, a by-class breakdown + legend, search, and a selected-road read-out)
injected, wired entirely through the public ``window.rs*`` API. Point it at your own data::

    python build.py [edges.gpkg | edges.geojson] [--tiles]

``--tiles`` packs the roads as an embedded-PMTiles vector tileset (big networks stay
responsive; needs ``pip install "roadstyle[tiles]"``) — the sidebar works identically, it
only ever talks through the ``rs*`` API (its stats read every edge via the sidecar).
"""
from __future__ import annotations

import sys
from pathlib import Path

import roadstyle as rs

HERE = Path(__file__).resolve().parent
DEFAULT = HERE.parent / "studio" / "samples" / "sodermalm_driving.geojson"


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--tiles"]
    tiles = "--tiles" in sys.argv[1:]
    src = Path(args[0]) if args else DEFAULT
    if not src.exists():
        raise SystemExit(f"data source not found: {src}")
    import geopandas as gpd
    edges = gpd.read_file(src)

    # render_report injects the packaged report sidebar (which owns colour-by, the legend, and the
    # layer/road-type filter); the base map keeps its own on-map switcher (basemap_switcher=True by
    # default). color_options are BAKED (Python precomputes each option's per-edge colours); the
    # sidebar's "Colour by" select switches between them and shows the active legend, and its filter
    # reads RS_CLASSES / RS_CLASS_COL / RS_CLASS_COLORS / RS_OVERLAYS.
    m = rs.render_report(
        edges, basemap="voyager", view_3d=True,
        basemaps=["voyager", "positron", "dark_matter", "osm", "satellite", "blank"],
        color_options={"Class": {},
                       "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"},
                       "Lanes": {"color_by": "lanes", "cmap": "viridis"}},
        tiles=tiles)
    out = HERE / "report.html"
    m.save(out)
    print(f"wrote {out} — open it in a browser (no server needed)")


if __name__ == "__main__":
    main()

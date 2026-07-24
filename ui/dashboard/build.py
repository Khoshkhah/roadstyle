"""Build a working dashboard page.

Thin wrapper over the packaged :func:`roadstyle.render_dashboard` — the map with every built-in
control off and the bundled dashboard sidebar (query box, colour-by, class filter + legend, table)
injected, wired through the public ``window.rs*`` API. Point it at your own data::

    python build.py [edges.gpkg | edges.geojson] [--tiles]

``--tiles`` packs the roads as an embedded-PMTiles vector tileset (big networks stay
responsive; needs ``pip install "roadstyle[tiles]"``) — the sidebar works identically,
it only ever talks through the ``rs*`` API.
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

    # render_dashboard turns the built-in controls off and injects the packaged sidebar; the
    # explicit basemaps= list keeps all entries addressable for the sidebar's own base-map select
    # (rsSetBasemap). view_3d bakes the extruded bridge decks (needs a `bridge` column) and opens
    # tilted. color_options are BAKED (Python precomputes each option's per-edge colours); the
    # sidebar's "Colour by" select switches between them. Adjust to your columns.
    m = rs.render_dashboard(
        edges, basemap="voyager", view_3d=True,
        basemaps=["voyager", "positron", "dark_matter", "osm", "satellite", "blank"],
        color_options={"Class": {},
                       "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"},
                       "Lanes": {"color_by": "lanes", "cmap": "viridis"}},
        tiles=tiles)
    out = HERE / "dashboard.html"
    m.save(out)
    print(f"wrote {out} — open it in a browser (no server needed)")


if __name__ == "__main__":
    main()

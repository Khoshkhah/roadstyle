"""Build the report-sidebar template into a working page.

Renders the road network with **every built-in control off** and injects ``sidebar.html``
before ``</body>`` — a stats-forward sidebar (headline counts, a by-class breakdown, search,
and a selected-road read-out) wired entirely through the public ``window.rs*`` API. Point it
at your own data::

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

    # built-in controls off — the sidebar IS the UI. color_options are BAKED here (Python
    # precomputes each option's per-edge colours); the sidebar's "Colour by" select switches
    # between them, and its by-class bars read RS_CLASSES / RS_CLASS_COL / RS_CLASS_COLORS.
    m = rs.render_edges(edges, backend="web", basemap="voyager", view_3d=True,
                        basemaps=["voyager", "positron", "dark_matter", "osm", "satellite",
                                  "blank"],
                        color_options={"Class": {},
                                       "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"},
                                       "Lanes": {"color_by": "lanes", "cmap": "viridis"}},
                        basemap_switcher=False, filter_control=False, road_popup=False,
                        tiles=tiles, name="Roads report")
    ui = (HERE / "sidebar.html").read_text()
    out = HERE / "report.html"
    out.write_text(m.html.replace("</body>", ui + "</body>", 1))
    print(f"wrote {out} — open it in a browser (no server needed)")


if __name__ == "__main__":
    main()

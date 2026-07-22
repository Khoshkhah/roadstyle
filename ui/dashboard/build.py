"""Build the sidebar-dashboard template into a working page.

Renders the road network with **every built-in control off** and injects ``sidebar.html``
before ``</body>`` — the sidebar is the whole UI, wired through the public ``window.rs*``
API. Point it at your own data::

    python build.py [path/to/duckosm.duckdb | edges.gpkg]
"""
from __future__ import annotations

import sys
from pathlib import Path

import roadstyle as rs

DEFAULT_DB = Path("/home/kaveh/projects/duckOSM/data/db/sodermalm.duckdb")
HERE = Path(__file__).resolve().parent


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    if not src.exists():
        raise SystemExit(f"data source not found: {src}")
    if src.suffix == ".duckdb":
        edges = rs.from_duckosm(src)
    else:
        import geopandas as gpd
        edges = gpd.read_file(src)

    # built-in controls off — the sidebar IS the UI; the explicit basemaps= list keeps all
    # entries addressable for the sidebar's own select (rsSetBasemap). view_3d bakes the
    # extruded bridge decks (needs a `bridge` column) and opens tilted; the sidebar's 2D/3D
    # button (rsSetView3D) switches views.
    # color_options are BAKED here (Python precomputes each option's per-edge colours);
    # the sidebar's "Colour by" select just switches between them. Adjust to your columns.
    m = rs.render_edges(edges, backend="web", basemap="voyager", view_3d=True,
                        basemaps=["voyager", "positron", "dark_matter", "satellite", "blank"],
                        color_options={"Class": {},
                                       "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"},
                                       "Lanes": {"color_by": "lanes", "cmap": "viridis"}},
                        basemap_switcher=False, filter_control=False, road_popup=False,
                        name="Roads dashboard")
    ui = (HERE / "sidebar.html").read_text()
    out = HERE / "dashboard.html"
    out.write_text(m.html.replace("</body>", ui + "</body>", 1))
    print(f"wrote {out} — open it in a browser (no server needed)")


if __name__ == "__main__":
    main()

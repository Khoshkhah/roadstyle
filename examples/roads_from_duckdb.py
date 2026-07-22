"""Roads in DuckDB → roadstyle — the ``from_duckdb`` input path.

Loads the bundled Södermalm driving sample into an in-memory DuckDB table (spatial
extension), then renders a styled, interactive map straight from a SQL query. The same
two lines work against any DuckDB table/view with road geometries — swap the query for
your own schema (a WHERE clause, a join, a Parquet scan…).

The geometry is a native DuckDB ``GEOMETRY`` column, so we select it as WKB with
``ST_AsWKB`` for a clean round-trip. The sample is a directed graph — a street can appear
as a forward and a reverse half-edge — and we render **every** edge as-is (no dedup, no
direction filter), so nothing is dropped.

Run::

    python examples/roads_from_duckdb.py

Needs the ``duckdb`` extra:  ``pip install "roadstyle[duckdb]"``.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

import roadstyle as rs

HERE = Path(__file__).resolve().parent          # generated maps land next to this script (gitignored)
SAMPLE = HERE.parent / "ui" / "studio" / "samples" / "sodermalm_driving.geojson"


def main() -> None:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial")
    con.execute(f"CREATE TABLE roads AS SELECT * FROM ST_Read('{SAMPLE}')")

    edges = rs.from_duckdb(
        con,
        "SELECT edge_id, highway, name, maxspeed_kmh, ST_AsWKB(geom) AS geom FROM roads",
        geometry="geom", crs=4326)
    print(f"from_duckdb → {len(edges):,} driving edges from {SAMPLE.name}")

    tooltip = ["edge_id", "highway", "name", "maxspeed_kmh"]
    folium_out = HERE / "sodermalm_driving.html"
    web_out = HERE / "sodermalm_driving_web.html"

    # high-saturation palette on the dark base map; hover tooltips from the data columns
    rs.render_edges(edges, basemap="dark_matter", tooltip=tooltip).save(str(folium_out))
    # the portable web spec — legend + filter + base-layer switcher baked into the page by to_html
    rs.save(edges, str(web_out), basemap="dark_matter", tooltip=tooltip)

    print(f"wrote {folium_out.name} (folium) and {web_out.name} (roadstyle.js) in {HERE}")


if __name__ == "__main__":
    main()

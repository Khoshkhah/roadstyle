"""Södermalm (Stockholm) driving roads — DuckDB → roadstyle.

Reads the **driving** road network straight out of the duckOSM project's ``sodermalm.duckdb``
(schema ``driving``, table ``edges``) and renders a styled, interactive map — the canonical
``roadstyle.from_duckdb`` input path.

The geometry is a native DuckDB ``GEOMETRY`` column, so we select it as WKB with ``ST_AsWKB`` (after
``LOAD spatial``) for a clean round-trip. The graph is directed — each street appears once forward
and once reversed — so ``WHERE NOT is_reverse`` keeps one line per street.

Run inside the project env (created from ``environment.yml``)::

    conda activate roadstyle
    python examples/sodermalm_duckdb_driving.py

Needs the ``duckdb`` extra:  ``pip install "roadstyle[duckdb]"``.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

import roadstyle as rs

# The driving-network DuckDB built by the duckOSM project (read-only — we never mutate it).
SODERMALM_DB = Path("/home/kaveh/projects/duckOSM/data/db/sodermalm.duckdb")

HERE = Path(__file__).resolve().parent   # write generated maps next to this script (gitignored)


def load_driving_edges(db: Path) -> rs.RoadEdges:
    """Read the driving edges from ``driving.edges`` into canonical :class:`roadstyle.RoadEdges`."""
    con = duckdb.connect(str(db), read_only=True)
    con.execute("LOAD spatial;")                       # geometry is a native GEOMETRY → ST_AsWKB
    # The graph is directed: each street can appear as a forward and/or a reverse half-edge, each
    # with its own geometry. Dedup on the *undirected* identity (same OSM way + node pair, either
    # direction) so we draw one line per street — and never drop a street that exists only as a
    # reverse edge (a plain `WHERE NOT is_reverse` silently loses ~1500 one-way streets here).
    query = (
        "SELECT DISTINCT ON (osm_id, LEAST(source, target), GREATEST(source, target)) "
        "       highway, name, maxspeed_kmh, length_m, ST_AsWKB(geometry) AS geom "
        "FROM driving.edges "
        "ORDER BY osm_id, LEAST(source, target), GREATEST(source, target), is_reverse"
    )
    # DuckDB carries no CRS; the data is OSM lon/lat, so crs=4326. Pass connection + query.
    return rs.from_duckdb(con, query, geometry="geom", crs=4326)


def main() -> None:
    if not SODERMALM_DB.exists():
        raise SystemExit(f"DuckDB not found: {SODERMALM_DB} — adjust SODERMALM_DB to your path.")

    edges = load_driving_edges(SODERMALM_DB)
    print(f"from_duckdb → {len(edges):,} driving edges from {SODERMALM_DB.name}")

    tooltip = ["highway", "name", "maxspeed_kmh"]
    folium_out = HERE / "sodermalm_driving.html"
    web_out = HERE / "sodermalm_driving_web.html"

    # high-saturation dark theme; hover tooltips from the data columns
    rs.render_edges(edges, theme="dark", tooltip=tooltip).save(str(folium_out))
    # the portable web spec — legend + filter + base-layer switcher baked into the page by to_html
    rs.save(edges, str(web_out), theme="dark", tooltip=tooltip)

    print(f"wrote {folium_out.name} (folium) and {web_out.name} (roadstyle.js) in {HERE}")


if __name__ == "__main__":
    main()

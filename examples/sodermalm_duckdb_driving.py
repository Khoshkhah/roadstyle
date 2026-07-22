"""Södermalm (Stockholm) driving roads — DuckDB → roadstyle.

Reads the **driving** road network straight out of the duckOSM project's ``sodermalm.duckdb``
(schema ``driving``, table ``edges``) and renders a styled, interactive map — the canonical
``roadstyle.from_duckdb`` input path.

The geometry is a native DuckDB ``GEOMETRY`` column, so we select it as WKB with ``ST_AsWKB`` (after
``LOAD spatial``) for a clean round-trip. The graph is directed — a street can appear as a forward
and a reverse half-edge — and we render **every** edge as-is (no dedup, no direction filter), so
nothing is dropped (both halves of a pair and both carriageways of a divided road are drawn).

Run inside the project env (created from ``environment.yml``)::

    conda activate roadstyle
    python examples/sodermalm_duckdb_driving.py

Needs the ``duckdb`` extra:  ``pip install "roadstyle[duckdb]"``.
"""
from __future__ import annotations

from pathlib import Path

import roadstyle as rs

# The driving-network DuckDB built by the duckOSM project (read-only — we never mutate it).
SODERMALM_DB = Path("/home/kaveh/projects/duckOSM/data/db/sodermalm.duckdb")

HERE = Path(__file__).resolve().parent   # write generated maps next to this script (gitignored)


def load_driving_edges(db: Path) -> rs.RoadEdges:
    """One line: the canonical duckOSM bridge selects the right columns (grade separation,
    oneway, lanes, text-cast edge_id) so nothing is silently dropped or corrupted."""
    return rs.from_duckosm(db)


def main() -> None:
    if not SODERMALM_DB.exists():
        raise SystemExit(f"DuckDB not found: {SODERMALM_DB} — adjust SODERMALM_DB to your path.")

    edges = load_driving_edges(SODERMALM_DB)
    print(f"from_duckosm → {len(edges):,} driving edges from {SODERMALM_DB.name}")

    tooltip = ["edge_id", "osm_id", "highway", "name", "maxspeed_kmh"]
    folium_out = HERE / "sodermalm_driving.html"
    web_out = HERE / "sodermalm_driving_web.html"

    # high-saturation palette on the dark base map; hover tooltips from the data columns
    rs.render_edges(edges, basemap="dark_matter", tooltip=tooltip).save(str(folium_out))
    # the portable web spec — legend + filter + base-layer switcher baked into the page by to_html
    rs.save(edges, str(web_out), basemap="dark_matter", tooltip=tooltip)

    print(f"wrote {folium_out.name} (folium) and {web_out.name} (roadstyle.js) in {HERE}")


if __name__ == "__main__":
    main()

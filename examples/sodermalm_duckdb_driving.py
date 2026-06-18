"""Södermalm (Stockholm) driving roads — DuckDB → roadstyle.

End-to-end sample of the DuckDB input path (`roadstyle.from_duckdb`):

1. fetch the *driving* road network for Södermalm from the OSM Overpass API,
2. load it into a DuckDB table with the geometry stored as **WKB**,
3. read it back out with ``rs.from_duckdb`` (canonical ``RoadEdges``), and
4. render a styled, interactive map.

Run inside the project env (created from ``environment.yml``)::

    conda activate roadstyle
    python examples/sodermalm_duckdb_driving.py

Only needs the ``duckdb`` extra on top of roadstyle:  ``pip install "roadstyle[duckdb]"``.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb
import geopandas as gpd
from shapely.geometry import LineString

import roadstyle as rs

HERE = Path(__file__).resolve().parent   # write generated maps next to this script (gitignored)

# Södermalm bounding box (S, W, N, E) — the island district in central Stockholm.
SODERMALM_BBOX = (59.301, 18.035, 59.323, 18.106)

# "Driving" = the OSM classes a car routes over (mirrors OSMnx network_type="drive";
# no footway / cycleway / path / pedestrian / service).
DRIVING = [
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "living_street",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
]

# Overpass is free + rate-limited; try the main endpoint then mirrors, with a short retry.
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "roadstyle-example/0.1 (sodermalm duckdb sample)"


def _overpass(query: str) -> list[dict]:
    """POST a query to Overpass, falling back across mirrors; return the ``elements`` list."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for url in OVERPASS_MIRRORS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url, data=body, headers={"User-Agent": USER_AGENT}
                )
                with urllib.request.urlopen(req, timeout=90) as resp:
                    return json.load(resp)["elements"]
            except Exception as err:                  # rate limit / mirror down → back off, retry
                last = err
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Overpass request failed on all mirrors: {last}")


def fetch_driving_edges(bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Download the driving road network in ``bbox`` from Overpass as a GeoDataFrame (EPSG:4326)."""
    s, w, n, e = bbox
    classes = "|".join(DRIVING)
    query = (
        "[out:json][timeout:60];"
        f'way["highway"~"^({classes})$"]({s},{w},{n},{e});'
        "out geom;"
    )
    elements = _overpass(query)

    rows, geoms = [], []
    for el in elements:
        geom = el.get("geometry")
        if el.get("type") != "way" or not geom or len(geom) < 2:
            continue
        rows.append({
            "highway": el["tags"]["highway"],
            "name": el["tags"].get("name"),
            "maxspeed": el["tags"].get("maxspeed"),
        })
        geoms.append(LineString([(p["lon"], p["lat"]) for p in geom]))   # (x=lon, y=lat)
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=4326)


def load_into_duckdb(edges: gpd.GeoDataFrame) -> duckdb.DuckDBPyConnection:
    """Insert the edges into an in-memory DuckDB table, geometry stored as WKB BLOBs."""
    con = duckdb.connect()
    con.execute("CREATE TABLE roads (highway VARCHAR, name VARCHAR, maxspeed VARCHAR, geom BLOB)")
    con.executemany(
        "INSERT INTO roads VALUES (?, ?, ?, ?)",
        [(r.highway, r["name"], r.maxspeed, r.geometry.wkb)
         for _, r in edges.iterrows()],
    )
    return con


def main() -> None:
    edges = fetch_driving_edges(SODERMALM_BBOX)
    print(f"fetched {len(edges):,} Södermalm driving edges")

    con = load_into_duckdb(edges)

    # The DuckDB input path: a connection + a query selecting geometry as WKB. DuckDB carries no
    # CRS, so crs=4326 says what the coordinates are in (here already WGS84). Returns RoadEdges.
    e = rs.from_duckdb(
        con,
        "SELECT highway, name, maxspeed, geom FROM roads",
        geometry="geom",
        crs=4326,
    )
    print(f"from_duckdb → {len(e):,} edges, class column {e.class_col!r}")

    # Render the high-saturation dark theme, hover tooltips from the data columns.
    folium_out = HERE / "sodermalm_driving.html"
    web_out = HERE / "sodermalm_driving_web.html"
    rs.render_edges(e, theme="dark", tooltip=["highway", "name", "maxspeed"]).save(str(folium_out))
    # Same data as a portable, stack-agnostic web spec (legend + filter + base-layer switcher baked
    # into the page by to_html).
    rs.save(e, str(web_out), theme="dark", tooltip=["highway", "name", "maxspeed"])

    print(f"wrote {folium_out.name} (folium) and {web_out.name} (roadstyle.js) in {HERE}")


if __name__ == "__main__":
    main()

"""Generate the live demo maps embedded in the docs **manual** (docs/manual.md).

Run from the repo root::

    python docs/build_maps.py        # writes docs/maps/*.html

These are committed so the GitHub Pages build (which does **not** run roadstyle) can serve them.
Each is a self-contained map the manual embeds in an ``<iframe>``. They use the bundled sample
edges (``notebooks/data/sodermalm_edges.gpkg``) with a couple of seeded columns so the data-driven
demos look real.
"""
from __future__ import annotations

import random
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, box

import roadstyle as rs

REPO = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "maps"
OUT.mkdir(exist_ok=True)

g = gpd.read_file(REPO / "notebooks" / "data" / "sodermalm_edges.gpkg").to_crs(4326)
random.seed(7)
g["aadt"] = [random.randint(200, 24000) for _ in range(len(g))]
g["speed_kph"] = [random.choice([30, 40, 50, 60, 70]) for _ in range(len(g))]

# 1 — a first map: the default web backend (Voyager base, the settings default)
rs.render_edges(g, backend="web", name="roadstyle — first map").save(OUT / "first_map.html")

# 2 — dynamic recolour: a neutral mono base + a "Colour by" picker (Class / AADT / Speed)
rs.render_edges(
    g, backend="web", palette="mono",
    color_options={
        "Class": {},
        "AADT": {"color_by": "aadt", "cmap": "viridis"},
        "Speed": {"color_by": "speed_kph", "cmap": "magma"},
    },
    name="roadstyle — colour by your data",
).save(OUT / "recolor.html")

# 3 — extra overlay layers: synthetic TAZ zones (under) + POIs (over), both clickable
minx, miny, maxx, maxy = g.total_bounds
random.seed(3)
zones = []
for ix in range(2):
    for iy in range(2):
        x0, x1 = minx + (maxx - minx) * ix / 2, minx + (maxx - minx) * (ix + 1) / 2
        y0, y1 = miny + (maxy - miny) * iy / 2, miny + (maxy - miny) * (iy + 1) / 2
        zones.append({"taz_id": f"Z{ix}{iy}", "name": f"Zone {ix}-{iy}",
                      "weight": round(random.uniform(0.2, 1.0), 2), "geometry": box(x0, y0, x1, y1)})
taz = gpd.GeoDataFrame(zones, crs=4326)
random.seed(9)
kinds = ["school", "shop", "hospital", "park"]
pois = gpd.GeoDataFrame(
    [{"name": f"POI {i}", "type": random.choice(kinds),
      "geometry": Point(random.uniform(minx, maxx), random.uniform(miny, maxy))} for i in range(6)],
    crs=4326)
rs.render_edges(
    g, backend="web", palette="mono",
    overlays=[
        rs.Overlay(taz, kind="fill", placement="under", color="#6aa9ff", opacity=0.14,
                   outline="#6aa9ff", label="TAZ zones", popup=["taz_id", "name", "weight"]),
        rs.Overlay(pois, kind="circle", placement="over", color="#ff5d5d", radius=7,
                   label="POIs", popup=["name", "type"]),
    ],
    name="roadstyle — overlay layers",
).save(OUT / "overlays.html")

for f in sorted(OUT.glob("*.html")):
    print(f"wrote {f.relative_to(REPO)} ({f.stat().st_size // 1024} KB)")

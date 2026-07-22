"""Sample: extra overlay layers on the web backend — zone polygons + POI circles.

Run it::

    python examples/overlays_web.py        # writes examples/web_overlays_sample.html

Each ``Overlay`` is the caller's own geometry with the caller's own style; roadstyle draws it as
its own MapLibre layer(s) under or over the roads, makes it clickable (a popup of the listed
fields), and adds a *Layers* toggle. Here: synthetic TAZ zones (translucent fill, under the roads)
and a handful of POIs (circles, on top).
"""
from __future__ import annotations

import random
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, box

import roadstyle as rs

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# roads
g = gpd.read_file(REPO / "notebooks" / "data" / "sodermalm_edges.gpkg").to_crs(4326)
minx, miny, maxx, maxy = g.total_bounds

# 1. synthetic TAZ zones — a 2x2 grid of boxes over the network extent, each with some attributes
random.seed(3)
zones, nx, ny = [], 2, 2
for ix in range(nx):
    for iy in range(ny):
        x0 = minx + (maxx - minx) * ix / nx
        x1 = minx + (maxx - minx) * (ix + 1) / nx
        y0 = miny + (maxy - miny) * iy / ny
        y1 = miny + (maxy - miny) * (iy + 1) / ny
        zones.append({"taz_id": f"Z{ix}{iy}", "name": f"Zone {ix}-{iy}",
                      "weight": round(random.uniform(0.2, 1.0), 2),
                      "geometry": box(x0, y0, x1, y1)})
taz = gpd.GeoDataFrame(zones, crs=4326)

# 2. synthetic POIs — a few points with a name/type
random.seed(9)
kinds = ["school", "shop", "hospital", "park"]
pois = gpd.GeoDataFrame(
    [{"name": f"POI {i}", "type": random.choice(kinds),
      "geometry": Point(random.uniform(minx, maxx), random.uniform(miny, maxy))}
     for i in range(6)], crs=4326)

# 3. render with both overlays — zones under the roads, POIs on top
wm = rs.render_edges(
    g, backend="web", basemap="dark_matter", palette="mono",
    arrows=True, labels=True,
    overlays=[
        rs.Overlay(taz, kind="fill", placement="under", color="#6aa9ff", opacity=0.14,
                   outline="#6aa9ff", label="TAZ zones", popup=["taz_id", "name", "weight"]),
        rs.Overlay(pois, kind="circle", placement="over", color="#ff5d5d", radius=7,
                   label="POIs", popup=["name", "type"]),
    ],
    name="roadstyle — overlays",
)

out = HERE / "web_overlays_sample.html"
out.write_text(wm.html, encoding="utf-8")
print("wrote", out, "(%d KB)" % (len(wm.html) // 1024))

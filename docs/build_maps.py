"""Generate the live demo maps embedded in the docs (get-started.md and the guides).

Run from the repo root::

    python docs/build_maps.py        # writes docs/maps/*.html

They are not committed: the docs workflow (.github/workflows/docs.yml) builds them before
``mkdocs build``, with the Google key from the secret ``GOOGLE_MAPS_KEY`` (the live map's
Google 3D window, Street View's Linked mode). Locally, set ``GOOGLE_MAPS_KEY`` first. Each is a self-contained map the manual embeds in an ``<iframe>``. They use the bundled sample
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

# 1 — a first map: the default web backend (OpenFreeMap Positron base, the settings default)
rs.render_edges(g, backend="web", name="roadstyle — first map").save(OUT / "first_map.html")

# 2 — dynamic recolour: a neutral mono base + a "Colour by" picker (Class / AADT / Speed)
rs.render_edges(
    g, backend="web", palette="mono",
    color_options={                      # the first one shows on open: the data, not grey
        "AADT": {"color_by": "aadt", "cmap": "viridis"},
        "Speed": {"color_by": "speed_kph", "cmap": "magma"},
        "Class": {},
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

# the map and Google Street View side by side; the demo opens on Götgatan, zoomed in
OPEN_ON = """<script>(function () {
  function start() {
    const ids = rsQuery(p => p.name === "Götgatan");
    if (ids.length) { const id = ids[Math.floor(ids.length / 2)]; rsSelect(id); rsFocus(id, {maxZoom: 16}); }
  }
  if (map.loaded()) start(); else map.once("load", start);
})();</script>"""
html = rs.render_street_view(g, name="Roads and Street View").html
(OUT / "street_view.html").write_text(html.replace("</body>", OPEN_ON + "</body>", 1), encoding="utf-8")
# the floating window on an ordinary map, opened on Götgatan (the demo of street_view="window")
OPEN_WINDOW = OPEN_ON.replace("rsFocus(id, {maxZoom: 16}); }", "rsFocus(id, {maxZoom: 16}); rsSetStreetView(true); }")
html = rs.render_edges(g, name="roadstyle: the Street View window", road_popup=False).html
(OUT / "street_view_window.html").write_text(html.replace("</body>", OPEN_WINDOW + "</body>", 1),
                                             encoding="utf-8")
html = rs.render_street_view(g, name="Roads and Street View", layout="below").html
(OUT / "street_view_below.html").write_text(html.replace("</body>", OPEN_ON + "</body>", 1),
                                               encoding="utf-8")

# the live map (README and the docs home link to it): the sample's own columns only, every control on,
# Google 3D too (it needs GOOGLE_MAPS_KEY: without it, render_edges stops with an error)
live = gpd.read_file(REPO / "notebooks" / "data" / "sodermalm_edges.gpkg").to_crs(4326)
x0, y0, x1, y1 = live.total_bounds
mx, my = (x1 - x0) * 0.15, (y1 - y0) * 0.15          # a margin round the data
# the map stays inside Södermalm (and cannot zoom out past it); the Google 3D camera takes the same box
KEEP_IN = f"<script>map.setMaxBounds([[{x0 - mx:.5f}, {y0 - my:.5f}], [{x1 + mx:.5f}, {y1 + my:.5f}]]);</script>"
html = rs.render_edges(
    live, backend="web", google_3d=True,
    color_options={
        "Road class": {},
        "Speed limit": {"color_by": "maxspeed_kmh", "cmap": "plasma", "vmin": 20, "vmax": 60},
        "Lanes": {"color_by": "lanes", "cmap": "viridis", "vmin": 1, "vmax": 4},
    },
    name="roadstyle: live map of Södermalm",
).html
(OUT / "live.html").write_text(html.replace("</body>", KEEP_IN + "</body>", 1), encoding="utf-8")

for f in sorted(OUT.glob("*.html")):
    print(f"wrote {f.relative_to(REPO)} ({f.stat().st_size // 1024} KB)")

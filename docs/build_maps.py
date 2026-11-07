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

# 0 - the roads of the live editors (docs/copy_parts.py puts them in site/live/area/): the design editor reads this GeoParquet
g.to_parquet(OUT / "sodermalm.parquet")
# ... and the level area of the live level editor (the files of `roadstyle levels make` and `solve`), with empty heads.csv and caps.csv
from roadstyle import level_area  # noqa: E402

AREA = OUT / "levels_area"
level_area.make_area(g, AREA)
level_area.solve_area(AREA)
for name, head in (("heads.csv", "road,start_m,end_m\n"), ("caps.csv", "road,start,end\n")):
    (AREA / name).write_text(head, encoding="utf-8")

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

# the testbed of the dashboard manual: every `javascript` block of docs/guides/dashboard-manual/javascript.md runs on it.
# tests/test_dashboard_manual.py runs the same blocks on a small page with the same keywords. The blank base map needs no key.
rs.render_dashboard(
    g, basemap="blank", live_data=True, name="Testbed", boundary=g.union_all().convex_hull, boundary_limit=True,
    color_options={"Road class": {}, "Speed limit": {"color_by": "maxspeed_kmh", "cmap": "plasma", "vmin": 20, "vmax": 60}},
    views={"Normal": {"road_fill": True}, "Casing only": {"road_fill": False}},
).save(OUT / "dashboard_testbed.html")

# the maps of docs/guides/dashboards.md: every python block that saves a page makes the map under it.
# The blocks run one after another in one namespace (the first one imports roadstyle), with the sample's edges, in docs/maps.
import os
import re
import textwrap
manual = (REPO / "docs" / "guides" / "dashboards.md").read_text(encoding="utf-8")
env = {"edges": g}
os.chdir(OUT)
for block in re.findall(r"```python\n(.*?)```", manual, re.S):
    exec(textwrap.dedent(block), env)      # a block in a content tab is indented
os.chdir(REPO)

# the live map (README and the docs home link to it): the dashboard (panel and toolbox) on the sample's own columns,
# with the OpenFreeMap Positron base map and Google 3D (it needs GOOGLE_MAPS_KEY: without it, render_dashboard stops with an error)
live = gpd.read_file(REPO / "notebooks" / "data" / "sodermalm_edges.gpkg").to_crs(4326)
x0, y0, x1, y1 = live.total_bounds
mx, my = (x1 - x0) * 2, (y1 - y0) * 2                      # a margin of two data sizes on each side: the data can be dragged out of the window
# the camera stays near Södermalm (two data sizes beyond it, and no zoom-out past that); the Google 3D camera takes the same box
KEEP_IN = f"<script>map.setMaxBounds([[{x0 - mx:.5f}, {y0 - my:.5f}], [{x1 + mx:.5f}, {y1 + my:.5f}]]);</script>"
html = rs.render_dashboard(
    live, basemap="ofm_positron", google_3d=True,
    color_options={
        "Road class": {},
        "Speed limit": {"color_by": "maxspeed_kmh", "cmap": "plasma", "vmin": 20, "vmax": 60},
        "Lanes": {"color_by": "lanes", "cmap": "viridis", "vmin": 1, "vmax": 4},
    },
    name="roadstyle: live map of Södermalm",
).html
(OUT / "live.html").write_text(html.replace("</body>", KEEP_IN + "</body>", 1), encoding="utf-8")

# the data dock, live (data-dock.md): DuckDB in the page (duckdb-wasm) holds the roads of sodermalm.parquet as the table `edges`, and the
# dock (site/live/dashboard/data/data_dock.js, docs/copy_parts.py) runs its SQL there
DOCK = """<script type="module">
import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.33.1-dev57.0/+esm";
import {dataDock} from "../live/dashboard/data/data_dock.js";
const conn = (async () => {
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  const url = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], {type: "text/javascript"}));
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(url));
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  await db.registerFileURL("roads.parquet", new URL("sodermalm.parquet", location.href).href, duckdb.DuckDBDataProtocol.HTTP, false);
  const c = await db.connect();
  await c.query("CREATE TABLE edges AS SELECT * EXCLUDE (geometry) FROM 'roads.parquet'");
  return c;
})();
// a result as the dock takes it: {columns: [{name, type}], rows: [[...]]} (a BIGINT is a BigInt)
async function query(sql){
  const t = await (await conn).query(sql), f = t.schema.fields;
  return {columns: f.map((x) => ({name: x.name, type: String(x.type)})), rows: t.toArray().map((r) => f.map((x) => r[x.name]))};
}
window.data = dataDock({query, ready: conn,
  schema: async () => ({tables: [{name: "main.edges", rows: Number((await query("SELECT count(*) AS n FROM edges")).rows[0][0]),
    about: "The roads of Södermalm: one row is one direction of a road (edge_id), with its OpenStreetMap tags, length_m, and two made-up columns, aadt and speed_kph."}]}),
  sql: "SELECT edge_id, name, highway, length_m FROM edges WHERE highway = 'primary' ORDER BY length_m DESC"});
window.data.open();
window.data.run();                                   // the first query at once: the table and its roads on the map
document.addEventListener("click", (e) => { const b = e.target.closest("[data-sql]"); if(b) window.data.run(b.dataset.sql); });
</script>"""
EXAMPLES = [
    ("Primary roads, the longest first", "SELECT edge_id, name, highway, length_m FROM edges WHERE highway = 'primary' ORDER BY length_m DESC"),
    ("Bridges and tunnels", "SELECT edge_id, name, highway, bridge, tunnel FROM edges WHERE bridge IS NOT NULL OR tunnel = 'yes'"),
    ("Busy roads (made-up aadt)", "SELECT edge_id, name, aadt, speed_kph FROM edges WHERE aadt > 20000 ORDER BY aadt DESC"),
    ("Kilometres by road class", "SELECT highway, round(sum(length_m) / 1000, 2) AS km FROM edges GROUP BY highway ORDER BY km DESC"),
]
TRY = ("<p>Write one <code>SELECT</code> in the line under the map and press <b>Run</b> (or Ctrl+Enter). The roads of the result light on "
       "the map. The table is <code>edges</code>. Or click a query:</p><div class=\"rs-opts\">"
       + "".join(f'<button type="button" class="rs-opt" style="text-align:left;width:100%" data-sql="{q}"><span><b>{t}</b><small>{q}</small></span></button>' for t, q in EXAMPLES)
       + "</div>")
html = rs.render_dashboard(
    g, basemap="ofm_positron", color_options={"Road class": {}}, name="The data dock",
    dashboard={"panel": {"sections": [
        {"id": "try", "label": "Try SQL", "html": TRY},
        {"id": "road", "label": "Selected road", "part": "road_card", "fields": ["name", "highway", "length_m", "aadt", "speed_kph"]},
    ]}},
).html
(OUT / "data_dock.html").write_text(html.replace("</body>", DOCK + "</body>", 1), encoding="utf-8")

for f in sorted(OUT.glob("*.html")):
    print(f"wrote {f.relative_to(REPO)} ({f.stat().st_size // 1024} KB)")

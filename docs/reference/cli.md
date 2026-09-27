# Command line

<p class="lead">The <code>roadstyle</code> command turns a road file into a map, a page or a JSON spec, without writing Python.</p>

```bash
roadstyle INPUT [options]          # INPUT: GPKG, GeoJSON, Shapefile, … with a road-class column
roadstyle studio [streamlit args]  # the Studio workbench
```

Each styling flag mirrors a Python keyword ([Every parameter](parameters.md)); a flag you leave out
keeps the keyword's default and your [settings](settings.md).

## Output

| flag | default | what |
|---|---|---|
| `-o`, `--output PATH` | input name + the format's extension | output file |
| `-f`, `--format FMT` | `web` | see [Formats](#formats) |
| `--version` | | print the version |
| `-h`, `--help` | | print every flag |

## Formats

| `-f` | writes | extension | Python equivalent |
|---|---|---|---|
| `web` | a self-contained MapLibre map | `.html` | `render_edges(g).save(...)` |
| `folium` | a folium (Leaflet) map | `.html` | `render_edges(g, backend="folium").save(...)` |
| `rsjs` | a standalone roadstyle.js page | `.html` | `rs.save(g, ...)` |
| `spec` | the JSON spec for your own frontend | `.json` | `rs.save_spec(g, ...)` |
| `geojson` | the styled FeatureCollection | `.geojson` | `rs.to_geojson(g)` |

Only the styling, filtering and data-colour flags apply to every format; the web flags below need
`-f web`.

## Flags

| flag | Python keyword | what |
|---|---|---|
| **Input** | | |
| `--highway-col COL` | `highway_col` | road-class column (default `highway`) |
| `--layer NAME` | `load_edges(layer=)` | layer of a multi-layer file, e.g. a GPKG |
| **Styling** | | |
| `--palette {highsat,carto,mono}` | `palette` | class palette (default `highsat`) |
| `--basemap KEY` | `basemap` | base map (default from settings: `voyager`) |
| `--tooltip COL [COL …]` | `tooltip` | columns in the hover tooltip |
| **Filtering** | | |
| `--include TYPE [TYPE …]` | `include` | keep only these classes |
| `--exclude TYPE [TYPE …]` | `exclude` | drop these classes |
| **Colour by data** | | |
| `--color-by COL` | `color_by` | colour by this column |
| `--colors JSON` | `colors` | categorical map, e.g. `'{"a":"#f00"}'` |
| `--cmap NAME` | `cmap` | numeric ramp, e.g. `viridis` |
| `--vmin N`, `--vmax N` | `vmin`, `vmax` | ramp range |
| `--width-by MIN MAX` | `width_by` | width in px follows the numeric `--color-by` |
| **Web map (`-f web`)** | | |
| `--page {dashboard,report,street-view}` | `render_dashboard` / `render_report` / `render_street_view` | a ready-made page instead of the plain map |
| `--view-3d` | `view_3d=True` | tilted camera and 3D bridge decks |
| `--pitch DEG`, `--bearing DEG` | `pitch`, `bearing` | starting camera |
| `--no-arrows` | `arrows=False` | no one-way arrows |
| `--no-labels` | `labels=False` | no street names |
| `--no-filter` | `filter_control=False` | no road-class filter panel |
| `--no-basemap-switcher` | `basemap_switcher=False` | no base-map button |
| `--tiles` | `tiles=True` | embedded PMTiles, for big networks (needs `roadstyle[tiles]`) |
| `--no-compress` | `compress=False` | plain JSON data instead of gzip |

## `--page`

| page | builds |
|---|---|
| `dashboard` | the map + a query sidebar |
| `report` | the map + a stats sidebar |
| `street-view` | the map + Google Street View of the clicked road |

`--page` needs `-f web`. For `street-view` only:

| flag | keyword | what |
|---|---|---|
| `--layout {beside,below}` | `layout` | Street View right of the map (default) or under it |
| `--panel-width PCT` | `panel_width` | Street View's share of the window, 20-80 (default 42) |
| `--no-resize` | `resizable=False` | no draggable divider |

Street View needs the page served over http(s): `python -m http.server`, then open
`http://localhost:8000/map.html`. See [Google Street View](../guides/street-view.md).

## `roadstyle studio`

Opens the [Studio](../studio.md) workbench in the browser. Everything after `studio` goes to
`streamlit run`, e.g. `roadstyle studio --server.port 8502`. Needs `pip install "roadstyle[studio]"`.

## Examples

```bash
roadstyle edges.gpkg -o map.html --basemap dark_matter
roadstyle edges.gpkg --include motorway trunk primary -o major.html
roadstyle edges.gpkg --color-by maxspeed_kmh --cmap viridis --width-by 1 6
roadstyle edges.gpkg --page street-view --layout below --panel-width 50
roadstyle edges.gpkg --page dashboard -o dashboard.html
roadstyle edges.gpkg -f spec -o map_data.json
```

**See also:** [Every parameter](parameters.md) · [Get started](../get-started.md)

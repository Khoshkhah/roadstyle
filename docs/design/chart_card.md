# The chart card: a chart in the panel, from Python with no JavaScript

Kaveh (2026-11-06): "did you create a full template and design for those charts that anyone can use it easily?" Today `rs.chart(el, spec)`
([A chart](../guides/dashboard-parts.md#a-chart)) needs JavaScript. A Python user of `render_dashboard` cannot add a chart. This design adds a
typed part of the panel, `part: "chart"`, as the parts `query` and `road_card` are, and a guide with a picture of each kind.

## What a user writes

```python
import roadstyle as rs

rs.render_dashboard(gdf, dashboard={"panel": {"sections": [
    # the map's own roads: the roads for each road class (no data to give)
    {"id": "classes", "label": "Roads by class", "part": "chart", "chart": {"kind": "pie", "x": "highway"}},
    # the map's roads: km for each road class (the sum of a column)
    {"id": "km", "label": "km by class", "part": "chart", "chart": {"kind": "bar", "x": "highway", "y": "length_m", "agg": "sum", "scale": 0.001}},
    # the page's own data: a DataFrame, or a list of dicts
    {"id": "flow", "label": "Vehicles per hour", "part": "chart", "chart": {"kind": "line", "x": "hour", "y": "vehicles", "data": counts_df}},
]}})
```

The same from JavaScript: `rs.sections.add({id, label, part: "chart", chart: {...}})`.

## The options of `chart`

| Option | Default | What it is |
|---|---|---|
| `kind` | (necessary) | `bar`, `line`, `histogram`, `scatter` or `pie`, as `rs.chart` |
| `x` | (necessary) | A column: the groups (bar, pie), the order (line), the numbers (histogram, scatter) |
| `y` | none | A number column, or a list of up to 3 (bar, line). None: the count of rows. Not for a histogram |
| `agg` | `"sum"` | How the rows of one value of `x` join, when the source is the map's roads or `x` has a value more than once: `sum`, `mean`, `min`, `max` or `count` |
| `scale` | `1` | A factor for `y` (`0.001`: metres to km) |
| `data` | none: the map's roads | The page's own rows. Python: a pandas DataFrame, a GeoDataFrame (its geometry is left out) or a list of dicts. JavaScript: `{columns, rows}` or a list of objects. They are written into the page |
| `title` | the card's `label` | The chart's title. A card with a label shows no second title |
| `height` | `220` | The height of the chart in pixels |
| `follow` | `false` | Map roads only: `true` draws the chart again for the roads that the map shows now (the filter of the roads box, the classes) |

- **The source.** With no `data`, the chart reads the map's own road table (the rows that the page has for its popup and its colours), so
  `x` and `y` are road columns. With `data`, it reads those rows. The two never mix.
- **Groups.** A bar or a pie joins the rows of each value of `x` with `agg` (the count of rows when there is no `y`). A number `x` with more
  than 40 values is put in ranges, as in the data dock. A pie has at most 6 slices (the rest is "Other").
- **The look** is the look of `rs.chart`: the 8 chart colours, the title and the count, compact ticks, hover, a legend for two or more series,
  the light and the dark theme. The card has the card standard (one width, the edge, `fold`, `background`).
- **A click** on a bar or a slice of the map's roads lights those roads (the highlight set `chart`, in the chart's colour); a second click, or
  a click on another mark, changes or ends the light. With `data`, a click calls the event `rs:chartpick` (`id`, `row`), so a page can act.

## Where it goes

| Part | Change |
|---|---|
| `rust/roadstyle/src/dashboard.rs` | `Part::Chart`; `Section.chart: Option<ChartSpec>` (`kind`, `x`, `y`, `agg`, `scale`, `data`, `title`, `height`, `follow`); the checks: a known `kind`, `x` given, `y` not for a histogram, `chart` only with `part: "chart"`; with `data`, `x` and `y` are its columns |
| The Python binding (`render_dashboard`) | `chart.data`: a DataFrame or a list of dicts to `{columns: [{name, type}], rows}` (the SQL type names of the dock: VARCHAR, DOUBLE, BIGINT, DATE, TIMESTAMP, BOOLEAN); a 64-bit integer as text, as the road ids |
| `dashboard/sections.js` | the part `chart` in `_SEC_PARTS`: it groups the rows (from the road table, or `data`) and calls `rs.chart` |
| `index.d.ts`, `docs/reference/javascript.md`, `docs/reference/parameters.md` | the part and its options; the event `rs:chartpick` |

## The guide

A new page, **Charts** (`docs/guides/charts.md`), in the site's menu after "The data dock":

1. A chart card from Python, in three lines (the example above), with its picture.
2. **One picture of each kind** (bar, horizontal bar, line, histogram, scatter, pie), each with the spec that made it. A script
   (`docs/images/charts/make.py`) draws them from a Monaco page in Playwright, in the light theme, so they can be made again.
3. The options table, the two sources, groups and ranges, a click, and the same from JavaScript (`rs.sections.add`, `rs.chart`).
4. Links: the data dock's Table | Chart, and Ask's `draw_chart`, which use the same chart.

## Tests

- Rust: the checks of `chart` (a wrong kind, no `x`, `y` with a histogram, `chart` without the part, a column that is not in `data`).
- Python: `render_dashboard` with each kind, from the map's roads and from a DataFrame; the rows in the page; a 64-bit integer stays exact.
- Browser (`tests/test_chart_card_browser.py`): each kind in the panel in both themes and at 390 px; the roads by class equal a count of the
  road table; `follow` after a filter of the roads box; a click lights the roads of a bar; `rs:chartpick` with `data`.

## Not in this step

- A chart in the bottom dock from Python (the dock is for the data dock now).
- A chart of a SQL query from Python: the page has no database; the data dock does that with its host.

# One chart for every page: what SonoFlow needs from `rs.chart`

Status: **design, for Kaveh's review** (2026-11-06). No code yet.

Kaveh (2026-11-06): "we have a chart in sonoflow project, check it and make it as templete consistent with your design and style", and
"it is an example of downstream project that want to use your design of cards". SonoFlow is the test case: a downstream project with
six dashboard pages. When `rs.chart` can draw all its charts, it can draw the charts of other projects too.

This design adds layers and two parts to `rs.chart` ([A chart](../guides/dashboard-parts.md#a-chart)) and to the chart card
([chart_card.md](chart_card.md)). It does not add a chart library to SonoFlow.

## What SonoFlow draws today (main 87e7d0f)

SonoFlow has no `rs.chart`: its pages are older. Each page draws its charts by hand with SVG strings or `rs.svg`.

| Form | Drawings | Pages |
|---|---|---|
| A likely-range band, an estimate line, counts as dots, a chosen-hour line | 4 | `daily.py` `draw`, `model.py` `weekChart`, `validation.py` `firstNight` (2) |
| Bars, and a histogram, with a reference line (80 %, 5 %) | 6 | `validation.py` `vbars` |
| A line with a crosshair | 3 | `validation.py` `lines` (one with the diagonal y = x) |
| Horizontal bars with their values | 1 | `validation.py` `hbars` |
| A scatter with the diagonal, a colour for each point | 1 | `validation.py` |
| A heat grid (hours × years, around 80 %) | 2 | `validation.py` `heat` (SVG), `cusum_streets.py` (an HTML table, months × years) |
| Dot-range rows (one row for each visit) | 1 | `cusum_streets.py` `visitChart` |
| A sparkline with a marker | 1 | `daily.py` `spark` |
| A bar in a table row (a share, a value, more or less than expected) | 3 | `daily.py`, `cusum_streets.py`, `study_places.py` |
| A key under a chart, in HTML | about 12 | all pages with charts |

The four band charts are the same chart with four looks. They have different blues (#38a3dc, #0284c7), a different x scale (on the hour,
or the middle of the hour), different ticks (each 6 h, each 3 h, 0/6/12/18/23) and different margins. The key of `daily.py` has
swatches that are not the colours of its marks. Only `--rs-chart-band`, `--rs-chart-grid` and `--rs-chart-miss` are shared.

## The changes to `rs.chart`

### 1. Layers on a line, a bar and a scatter

| Option | What it draws | SonoFlow |
|---|---|---|
| `band: ["lo", "hi"]` | The range between two columns, behind the series, in `--rs-chart-band` with the edge `--rs-chart-band-line`. `bandLabel` names it in the key (default "range"). | the likely range |
| `points: "col"` | The column as dots over the line, in `--ink`. A `null` has no dot. | the counts |
| `pointsIn: true` | With `band`: a dot in the band and a dot out of it get two colours (`--rs-chart-in`, `--rs-chart-out`) and two names in the key. | `validation.py` inside / outside |
| `dash: ["col"]` | That series is a dashed line. | the forecast |
| `ref: [{y: 0.8, label: "promise"}, {diagonal: true}]` | Reference lines, dashed, in `--mut`, with a short label at the right end. | 80 %, 5 %, y = x |
| `mark: {x, label}` | A vertical line at `x`, in `--rs-chart-mark`. `c.set({mark: {x: 14}})` moves it with no new drawing. | the chosen hour |
| `color: "col"` | A colour for each bar or point from a column of colours (the page's own data colours). | coverage colours |

- **A gap.** A `null` in a series breaks the line. A row with `null` in all series gets a small stub on the base line in
  `--rs-chart-miss`, so the person sees "no data", not zero.
- **The hover on a line** is a crosshair: one guide line at the nearest `x` and one box with each series, the band and the dot at that `x`.
  `onPick(row)` is a click at that `x`, so a page can choose an hour.
- **The key** comes from the layers: each series, the band, the dots, the dashed series and the mark, with swatches that are the marks
  themselves. A page writes no key. A chart with one series and no layer has no key, as today.

The band chart of `daily.py` is then one call:

```javascript
const c = rs.chart(el, {kind: "line", x: "hour", y: ["estimate", "forecast"], dash: ["forecast"],
  band: ["lo", "hi"], bandLabel: "likely range", points: "counted", mark: {x: h, label: "chosen hour"},
  columns, rows, onPick: (r) => setHour(rows[r][0])});
c.set({mark: {x: 15}});
```

### 2. An x axis of hours and of dates

- `xTicks: "hours"` puts the 24 hours on the hour (00:00, 06:00, 12:00, 18:00), the same on every page.
- A `DATE` or `TIMESTAMP` column of `x` gets ticks of days, months or years, from the range of the dates.

### 3. The kind `heat`

`{kind: "heat", x: "hour", y: "year", value: "coverage", mid: 0.8}` draws a grid of cells. A `mid` gives a diverging scale: two hues
with a grey middle at `mid` (the dataviz rule: no hue at the middle). No `mid` gives one hue, light to dark. The hover shows the cell's
values, and the key is a ramp with its end values. This replaces `heat` in `validation.py` and the month table of `cusum_streets.py`.

### 4. The kind `range`

`{kind: "range", y: "visit", lo: "min", hi: "max", mid: "median", band: [-0.2, 0.2], ref: [{x: 0}]}` draws one row for each item: a dot at
`mid` on a line from `lo` to `hi`, over a grey normal range. This is the visit chart of `cusum_streets.py` (one use; it is in this design
because a forest plot is a common form, and a page must not draw it by hand).

### 5. A sparkline

`small: true` exists. With `band` and `mark` it is the sparkline of `daily.py`: no axes, no labels and no hover.

## Two parts with no chart

- **A bar in a row**: `rs.bar(value, {max, mid})` gives the HTML of a short bar for a table cell, in `--accent` on a `--line` track. With
  `mid`, it grows to the left or to the right of the middle (less or more than expected). This replaces the three hand-made bars.
- **Number tiles**: `rs.kpi` exists. `daily.py` must use it in place of its own `card()`.

## New tokens

`--rs-chart-in`, `--rs-chart-out` (a dot in or out of the band) and `--rs-chart-mark` (the chosen x), for the light and the dark theme,
checked with the dataviz validator against both surfaces, as the 8 series colours are. The two dots also differ in shape (a full and a
hollow dot), so the colour is not the only sign.

## The chart card from Python

The chart card ([chart_card.md](chart_card.md)) gets the same options, with the same names: `band`, `points`, `pointsIn`, `dash`, `ref`,
`mark`, `color`, `xTicks`, and the kinds `heat` and `range`. A SonoFlow page can then give its charts in Python with its data
(`"data": df`), and the page's JavaScript only moves the mark or changes the rows (`rs.sections.get(id).chart.set(...)`).

## SonoFlow after this

A plan for SonoFlow's own session, not a change in this repository: each page moves one chart at a time to `rs.chart` and deletes its
own code (`frame`, `vbars`, `hbars`, `lines`, `heat`, `firstNight`, `weekChart`, `draw`, `visitChart`, the keys and the swatch CSS).
About 600 lines of JavaScript go. The data and the meaning stay; the look becomes roadstyle's.

## Where it goes

| Part | Change |
|---|---|
| `dashboard/chart.js` | the layers, the crosshair, the key from the layers, `xTicks`, the date ticks, the kinds `heat` and `range` |
| `dashboard/bar.js` (new) and `api.js` | `rs.bar` |
| `dashboard.css` | the three tokens, the key, the cells of `heat`, the row bar |
| `rust/roadstyle/src/dashboard.rs`, the Python binding | the chart card's new options and their checks |
| `index.d.ts`, `docs/guides/charts.md`, `docs/guides/dashboard-parts.md`, `skills/roadstyle/SKILL.md` | the options, a picture of each form |

## Tests

- `tests/test_chart_browser.py`: each layer and each new kind in both themes and at 390 px; the key has one swatch for each layer; a
  `null` makes a gap and a stub; `mark` moves with `set`; the crosshair box has each series at one `x`.
- A copy of each SonoFlow chart, with SonoFlow-like rows (24 hours, a band, counts with gaps), drawn from the spec only, as a picture in
  `docs/guides/charts.md`.

## The order

The chart card ([chart_card.md](chart_card.md)) is in progress. This work starts on top of it, after Kaveh approves this design.

## Not in this design

- A second y axis. A page with two measures of a different scale draws two charts (the dataviz rule).
- Changes in SonoFlow. They are for SonoFlow's own session, from the plan above.

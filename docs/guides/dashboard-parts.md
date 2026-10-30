# Dashboard parts

A dashboard page looks the same on every project when every page uses the same parts. This page lists them. **Use a part when one exists. Do not write CSS or
JavaScript for the same thing in a page**: a copy of a part drifts, and it forgets the dark theme.

The panel's tokens change with the theme: `--ink` (text), `--mut` (muted text), `--line`, `--card`, `--accent`. The accent is one colour for the whole dashboard, the Sonocount teal
(`#0e7c8e` for text in the light theme, a little darker than the logo's `#0E7F91` for 4.6:1 on the cards, and a lighter teal of the same hue in the dark theme, 8.5:1 on the panel); a page does not set its own. A filled control (a selected tab, a primary button)
uses `--accent-fill`, the logo teal `#0E7F91`, which takes white text (4.71:1) in both themes. Details and code for each part: [Add to the panel](dashboard-panel.md).

| Part | What it is | Use it for |
|---|---|---|
| `rs.help.set({title, intro, terms, note})` | the "i" button in the panel title and its window | "How to read this page" |
| `rs.hover.show(html, event)`, `rs.hover.on(node, html)` | the hover box, in the look of the popup | words over a chart or a map layer |
| `class="rs-tabs"` + `rs.tabs.use(nav, onChange)` | tabs, and `rs-seg` for a two-way switch | the parts of a page, a mode |
| `class="rs-sec-box"` | a card; an `h3` and the paragraph after it are its title and description | one block of a page |
| `rs.kpi(title, value, sub, color)` in `class="rs-kpis"` | a number tile (a grid of three) | the numbers of a page |
| `class="rs-cap"`, `class="rs-callout"` | a small capital caption, an answer box with a coloured edge | headings of tiles, the answer |
| `class="rs-scroll"` + `class="rs-table"` | a scroll area and a table with a fixed header | a list of streets |
| `rs.svg(parent, tag, attrs)` + `--rs-chart-*` | one SVG element that reads `var(--x)`, and the chart colours | charts |
| `<input>`, `<select>`, `<button>`, `class="rs-chip"`, `class="rs-dot"` | the panel's own look, a small label, a colour mark | forms, labels |
| `rs.ready(fn)` | runs `fn` when the page is ready | the start of a page script |
| `rs.classify(values, method, k, pivot=..., palette=...)` | the cuts and the colours for discrete road classes | `color_options` |

## The rules

- **Width.** The panel is 400 px by default. Fit the content to the panel; do not widen the panel for it. A table that needs more room drops a column or
  shortens a line.
- **Colours.** No colour literal for text, lines, cards or chart furniture: use the tokens. A colour that is the page's own *data* (a coverage band, a class) can
  be a literal, but a theme-aware one is better.
- **Both themes.** Look at the page in the light and in the dark theme, with the bar at two edges and at phone width, before you commit it.
- **Scroll.** A list that can be long goes in `rs-scroll`; the panel body already scrolls.
- **Transparency.** The three layers (bar and panel, boxes, card behind the text) are set by the person in the settings box. A part reads them with the
  tokens `--rs-tb-bg`, `--rs-box-bg` and `--rs-card-bg`; a page never sets an opacity.

## Colour classes

```python
cls = rs.classify(gdf["coverage"], method="natural", k=5, pivot=0.8, palette="rdylgn", fmt="{:.0%}")
gdf["cov_class"] = cls.labels
rs.render_dashboard(gdf, color_options={"Coverage": cls.option("cov_class")})
```

`natural` (Fisher-Jenks) puts the cuts in the gaps of the data, so the classes have different widths and sizes. `quantile` gives each class the same number of
roads, `equal` the same width, `fixed` your own `breaks`. A `pivot` (the promised 80 %, zero) is always one of the cuts. A missing value gets its own grey class.
The JavaScript `rs.naturalBreaks(values, k)` gives the same cuts for a page with live data.

# Dashboard parts

A dashboard page looks the same on every project when every page uses the same parts. This page lists the shared pieces and shows the code for each one. **Use a part when one exists. Do not write CSS or
JavaScript for the same thing in a page**: a copy of a part drifts, and it forgets the dark theme.

The panel starts empty. Two parts are whole sections that roadstyle writes: the `query` part and the `road_card` part. They are in [Add to the panel](dashboard-panel.md). The pieces below are for the page's own HTML in a section.

Two parts use the whole panel: the level editor ([Edit the levels in a dashboard](levels.md#edit-the-levels-in-a-dashboard)) and the design panel ([Edit the design of a map](design-panel.md)).

| Part | What it is | Use it for |
|---|---|---|
| [`rs.help.set({title, intro, terms, note})`](#a-help-window) | the "?" button in the panel title and its window | "How to read this page" |
| [`rs.help.button(el, {title, ...})`, `rs.help.open({title, ...})`](#a-help-window) | one more "?" button with its own words, and the same window opened from a link | a card, a label, a section |
| [`rs.sections.add({..., label, fold, background})`](dashboard-panel.md#cards-the-panel-standard) | a card: with or without a background, that folds or not; one button in the title row folds all the cards that fold, and the state is kept | the page's cards |
| [`class="rs-card-title"`](dashboard-panel.md#cards-the-panel-standard) | the title row of a card in the page's own HTML: the same row as the title of a section's card | the first row in an `rs-sec-box` |
| [`--rs-card-gap`, `--rs-card-pad`, `--rs-panel-bottom`](dashboard-panel.md#cards-the-panel-standard) | the space between cards (12 px), inside a card (14 px), under the last card (28 px) | a page that needs other numbers, set on `:root` |
| [`rs.hover.show(html, event)`, `rs.hover.on(node, html)`](#a-hover-box) | the hover box, in the look of the popup | words over a chart or a map layer |
| [`class="rs-tabs"` + `rs.tabs.use(nav, onChange)`](#tabs-and-a-two-way-switch) | tabs (the selected tab is filled), and `rs-seg` for a two-way switch (the selected segment is a light chip) | tabs: the sections of a page. Switch: a mode or a setting |
| [`rs.days.use(el, {days, value, onChange})`](#a-day-picker) | the day picker: a "Day" label, a field that opens a calendar of the days with data, the day before and after, "Latest" | the day of a page with one day of data at a time |
| [`class="rs-sec-box"`](#cards-number-tiles-and-a-callout) | a card; an `h3` and the paragraph after it are its title and description | one block of a page |
| [`rs.kpi(title, value, sub, color)` in `class="rs-kpis"`](#cards-number-tiles-and-a-callout) | a number tile (a grid of three) | the numbers of a page |
| [`class="rs-cap"`, `class="rs-callout"`](#cards-number-tiles-and-a-callout) | a small capital caption, an answer box with a colored edge | headings of tiles, the answer |
| [`class="rs-scroll"` + `class="rs-table"`](#a-list-or-a-table-that-scrolls) | a scroll area and a table with a fixed header | a list of streets |
| [`rs.svg(parent, tag, attrs)` + `--rs-chart-*`](#charts) | one SVG element that reads `var(--x)`, and the chart colors | charts |
| [`<input>`, `<select>`, `<button>`, `class="rs-chip"`, `class="rs-dot"`](#buttons-text-boxes-chips-and-a-dot) | the panel's own look, a small label, a color mark | forms, labels |
| `rs.ready(fn)` | runs `fn` when the page is ready | the start of a page script |
| [`rs.classify(values, method, k, pivot=..., palette=...)`](#colour-classes) | the cuts and the colors for discrete road classes | `color_options` |

## The accent color and the theme tokens

The page has a light and a dark theme. Every part of the dashboard and your HTML must follow them. Plain text, links, tables, `hr`, inputs and buttons already do. For your own colors, use the theme's tokens and not fixed colors. The tokens are set for the whole page, so they work in the panel, in a box of the toolbox, in a window and in the popup:

| Token | Use |
|---|---|
| `var(--ink)`, `var(--mut)` | text, muted text |
| `var(--bg)`, `var(--card)` | the background of the panel, a box in it |
| `var(--line)` | thin lines |
| `var(--accent)` | links and buttons |
| `var(--accent-fill)` | a filled control (a selected tab, a primary button) |

The accent is one color for the whole dashboard, the Sonocount teal. A page does not set its own. `--accent` is `#0e7c8e` for text in the light theme (a little darker than the logo's `#0E7F91`, for 4.6:1 on the cards) and a lighter teal of the same hue in the dark theme (8.5:1 on the panel). `--accent-fill` is the logo teal `#0E7F91`, which takes white text (4.71:1) in both themes. The tokens are defined once in `dashboard.css`. A selected tab, a primary button, a link, and the mode and follow buttons of the Street View and Google 3D windows use them, in the panel and in the floating windows.

`.sb-note` is small, muted text and `.rs-sec-box` is a box. Both have a contrast of 4.5 or more in the two themes. The rows of the legend follow the theme too.

`tests/test_dashboard_themes_browser.py` opens each part of a dashboard in the light and the dark theme. It fails on a text with a contrast under 4.5 and on a light surface or line in the dark theme. A new part must pass it.

## A help window

```js
rs.help.set({title: "How to read this page", intro: "What the page shows.",
             terms: [["Inside the range", "How often the promise held."]], note: "A short note."});
```

A "?" button appears in the title of the panel (`anchor: element` puts it in another element, for example in the title of a panel that a module draws). A page with more to explain puts a "?" button with its own words beside the title of a card or a label, and all the buttons open the one window:

```js
rs.help.button(document.querySelector("#card-3 h2"), {title: "About step 3", intro: "What it does.", html: "<p>Words of the page's own.</p>", button: "About step 3"});
rs.help.button(rs.sections.get("tabs"), {title: "About the tabs"});   // a section: the "?" goes in its title
rs.help.open({title: "Opened by a link", intro: "No button."});     // the same window, from a link or a key
```

To put a "?" in the title of a card, give the section's box (`rs.sections.get(id)`). The button goes at the right end of the title row: before the chevron of a card that folds (the chevron is last), and at the end of the `.rs-card-title` of a card in the page's own HTML. A click on the "?" opens the window and does not fold the card.

The words are `{title, intro, terms, note, html}`. `html` is HTML of the page's own, shown after the intro. `button` is the name of the button for a screen reader and its tooltip. `rs.help.button` gives the button back.

The window opens inside the screen. On a phone it is a sheet at the bottom of the screen. `rs.help.get()` gives the words that are set now, and `rs.help.clear()` takes the window and the button away. The window is roadstyle's own: it has the card token, the blur and the border of the other windows, so it is the same in both themes and on every page. The words can have HTML (`<b>`). Call `rs.help.set` again to replace them. `rs.help.open()` and `rs.help.close()` open and close the window.

## Cards, number tiles and a callout

```html
<div class="rs-callout" style="--rs-callout:#16a34a"><b>Yes, the promise holds.</b> On 80 % of hours the traffic was inside the range.</div>
<div class="rs-cap">All counted hours</div>
<div class="rs-kpis" id="k"></div>
<div class="rs-sec-box"><h3>By hour of the day</h3><p>How often the range held, hour by hour.</p><svg>...</svg></div>
```

```js
document.getElementById("k").innerHTML = rs.kpi("Inside the range", "80.4%", "promised 80 %", "#15803d") + rs.kpi("Typical miss", "10 %", "on one hour");
```

In the dark theme the colour of a number (the fourth argument of `rs.kpi`) is mixed with the theme's text colour, so any colour stays readable. A card is `.rs-sec-box`: an `h3` is its title and the paragraph right after it is its short muted description. An `svg` in it fills the width. `rs-kpis` is a grid of three tiles (`--rs-kpi-cols` changes the number). All of them use the tokens of the panel, so they follow the light and the dark theme.

## Buttons, text boxes, chips and a dot

A plain `<button>` and `<button class="sb-primary">` in the panel have their style already, and so have a `<select>` and a text `<input>` or `<textarea>`: write no class for them. `<span class="rs-chip">road type</span>` is a small label, `rs-chip accent` tints it with the page's `--accent`, and `<span class="rs-dot" style="background:#15803d"></span>` is a color mark before a word.

## Charts

```js
const s = document.querySelector("#chart");
rs.svg(s, "line", {x1: 0, x2: 300, y1: 40, y2: 40, stroke: "var(--rs-chart-grid)"});
rs.svg(s, "polygon", {points: "...", fill: "var(--rs-chart-band)", stroke: "var(--rs-chart-band-line)"});
rs.svg(s, "text", {x: 4, y: 12, fill: "var(--mut)", "font-size": 9}, "0");
```

`rs.svg` makes one SVG element. An SVG attribute does not read `var(--x)`, so a value that starts with `var(` goes to the style. The chart then follows the theme with no code of its own. The colors that charts share are `--rs-chart-band`, `--rs-chart-band-line`, `--rs-chart-grid` and `--rs-chart-miss`. For text and lines use the tokens `--ink`, `--mut`, `--line` and `--card`. A canvas cannot read a variable: draw it again on the event `rs:themechange`.

## Tabs and a two-way switch

```html
<nav class="rs-tabs"><button class="rs-tab on" data-tab="a">Overview</button><button class="rs-tab" data-tab="b">Streets</button></nav>
<div data-pane="a">...</div><div data-pane="b" hidden>...</div>
<div class="rs-seg" id="mode"><button class="on" data-v="all">Every day</button><button data-v="first">First day</button></div>
```

```js
const tabs = rs.tabs.use(document.querySelector(".rs-tabs"), id => console.log(id));    // tabs.select("b") opens a tab from the code
rs.tabs.use(document.getElementById("mode"), v => redraw(v));
```

A click or an arrow key selects. The chosen button has `on` and `aria-selected`. The panes beside the tabs (the siblings with `data-pane`) show the one with the same id. The selected tab uses `--accent-fill`.

The two parts look different, because they do different jobs:

| | Tabs (`rs-tabs`) | Two-way switch (`rs-seg`) |
|---|---|---|
| Look | A flat row with a line under it. The text is muted | A grey track with a rounded button for each value |
| Selected | Filled with `--accent-fill`, white text | The card color, `--accent` text, a soft shadow |
| Use it for | The sections (panes) of a page: the content below changes | A mode or a setting with two or a few values: the same content is drawn in a different way |

Tabs change the pane. A switch changes a setting. Do not use one for the job of the other.

```html
<!-- tabs: "Overview" and "Streets" are two panes -->
<nav class="rs-tabs"><button class="rs-tab on" data-tab="a">Overview</button><button class="rs-tab" data-tab="b">Streets</button></nav>
<!-- a switch: the same chart, with two ways to count -->
<div class="rs-seg"><button class="on" data-v="all">Every day</button><button data-v="first">First day</button></div>
```

## A day picker

Use the day picker on a page that shows one day of data at a time. Give an empty element and the days that have data:

```html
<div id="day"></div>
```

```js
const day = rs.days.use(document.getElementById("day"), {
  days: ["2026-10-01", "2026-10-04", "2026-10-05"],   // the days with data, "YYYY-MM-DD"
  value: "2026-10-05",                                // the day at the start (default: the latest)
  label: "Day",                                       // the label above the field (default: "Day")
  onChange: d => fetch(`daily_${d}.json`).then(r => r.json()).then(draw),
});
day.value();              // "2026-10-05"
day.set("2026-10-04");    // as a click: calls onChange
day.set("2026-10-04", true);   // quiet: does not call onChange
```

The field shows the day ("Mon 5 Oct 2026") with a calendar icon and a "v", and a click opens a calendar. In the calendar, only the days in `days` are buttons. "‹" and "›" go to the day before and the day after in `days`, so they skip a day with no data. "Latest" goes to the last day.

If `onChange` gives a promise, the field pulses and the buttons wait until the promise ends. If the promise fails, the picker goes back to the old day, and a line under the row says "Could not load Mon 5 Oct 2026." A day that is not in `days` is an error.

The field has a border and the page's background, and its icons are `--accent`. On hover and while the calendar is open, it has an `--accent` border, a light accent fill and an accent ring. The calendar is a box like the help window.

## A hover box

```js
rs.hover.on(chartNode, ev => "<b>Saturday</b><br>24 hours");     // the text, or a function of the event; null hides
rs.hover.show("<b>A street</b>", mapEvent.originalEvent);         // by hand, over a map layer
rs.hover.hide();
```

The box has the look of the popup and follows the pointer. It flips to the other side at the edge of the page and never takes the pointer. The words can have HTML.

## A list or a table that scrolls

```html
<div class="rs-scroll"><table class="rs-table"><thead><tr><th data-sort="desc">Street</th><th>Hours</th></tr></thead><tbody>...</tbody></table></div>
```

`rs-scroll` gives the area the scroll rules of the panel body: a thin scrollbar that shows only over the area or while it scrolls, a fade at the bottom edge while there is more below, and a scroll that never goes on to the map. The height is `--rs-scroll-h` (default: the smaller of 520 px and 60 % of the window). `rs-table` keeps the header row in view, lines up the numbers (the first column is text) and tints the row under the pointer. Put `data-sort="asc"` or `"desc"` on the `th` of the sorted column.

Every scroll area of the dashboard has these rules, not only `rs-scroll`: the help window, the boxes of the toolbox, the panel's own select list and the query part's list. A whole box has no fade, because the fade would also take its border. `tests/test_dashboard_scroll_browser.py` checks each area.

## The rules

- **Width.** Fit the content to the panel. Do not widen the panel for it (the width is `panel.width_px`: [Dashboard options](../reference/parameters.md#dashboard-options)). A table that needs more room drops a column or shortens a line.
- **Colors.** No color literal for text, lines, cards or chart furniture: use the tokens. A color that is the page's own *data* (a coverage band, a class) can be a literal, but a theme-aware one is better.
- **Both themes.** Look at the page in the light and in the dark theme, with the bar at two edges and at phone width, before you commit it.
- **Scroll.** A list that can be long goes in `rs-scroll`. The panel body already scrolls.
- **Transparency.** The person sets three layers (bar and panel, boxes, card behind the text) in the settings box. A part reads them with the tokens `--rs-tb-bg`, `--rs-box-bg` and `--rs-card-bg`. A page never sets an opacity.

## Colour classes

```python
cls = rs.classify(gdf["coverage"], method="natural", k=5, pivot=0.8, palette="rdylgn", fmt="{:.0%}")
gdf["cov_class"] = cls.labels
rs.render_dashboard(gdf, color_options={"Coverage": cls.option("cov_class")})
```

`natural` (Fisher-Jenks) puts the cuts in the gaps of the data, so the classes have different widths and sizes. `quantile` gives each class the same number of
roads, `equal` the same width, `fixed` your own `breaks`. A `pivot` (the promised 80 %, zero) is always one of the cuts. A missing value gets its own grey class.
The JavaScript `rs.naturalBreaks(values, k)` gives the same cuts for a page with live data.

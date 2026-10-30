# Add to the panel

<p class="lead">A page adds its own blocks to the dashboard's side panel, hides some of the panel's blocks, and adds rows to the legend. No edit of the template's HTML is necessary. The toolbox, the navigate button and the phone form are in [Dashboard layout](dashboard-layout.md).</p>

## The panel's sections

The panel has five sections, in this order: `base_map`, `colour_by`, `legend`, `query`, `selected_road`. The first three are hidden at the
start, because the toolbox has boxes for them. Show one with `"hide": []`. A section of your page goes at the end of the panel, or `after` or `before` any section.

```python
rs.render_dashboard(edges, google_3d=True, dashboard={
    "panel": {
        "sections": [
            {"id": "notes", "label": "Notes", "after": "legend",
             "html": '<p>Your text</p><p class="sb-note">Small print</p><div class="rs-sec-box">In a box</div>'},
        ],
        "hide": ["base_map", "colour_by", "legend", "query"],      # this list replaces the default list
    },
    "legend": {"rows": [{"color": "#ff0066", "label": "Events"}, {"color": "#16a34a", "label": "Sensors", "shape": "circle"}]},
})
```

A wrong `id`, an `after` or `before` that is not a section, or a name in `hide` that is not a section is an error.

The rows of `legend` show in the legend box of the toolbox, after the rows of the colour option. They show in the panel's legend section too, when you show that section. A row has a colour, a label and a shape (`square`, `circle` or `line`). A wrong shape is an error.

## The same from JavaScript

| Call | What it does |
|---|---|
| `rs.sections.add({id, html, el, label, after, before})` | adds a section; it returns its box |
| `rs.sections.list()` / `get(id)` | the ids in order; the box of a section (move it into your own tab) |
| `rs.sections.hide(id)` / `show(id)` / `remove(id)` | hide or show any section; remove only your own |
| `rs.legend.add({id, color, label, shape})` or `{id, html}` | a row of the legend; `shape` is the mark of what the page draws in this colour: `square` (default), `circle` or `line`. `remove(id)`, `list()` |

The event `rs:sectionchange` has `detail.id` and `detail.state`.

## A help window

```js
rs.help.set({title: "How to read this page", intro: "What the page shows.",
             terms: [["Inside the range", "How often the promise held."]], note: "A short note."});
```

An "i" button appears in the panel's title. The window is roadstyle's own: it has the card token, the blur and the border of the other windows, so it is the same in both themes and on every page. The words can have HTML (`<b>`). Call `rs.help.set` again to replace them; `rs.help.open()` and `rs.help.close()` open and close the window.

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

A card is `.rs-sec-box`: an `h3` is its title and the paragraph right after it is its short muted description. An `svg` in it fills the width. `rs-kpis` is a grid of three tiles (`--rs-kpi-cols` changes the number). All of them use the panel's tokens, so they follow the light and the dark theme.

## Buttons, text boxes, chips and a dot

A plain `<button>` and `<button class="sb-primary">` in the panel are styled already, and so are a `<select>` and a text `<input>` or `<textarea>`: write no class for them. `<span class="rs-chip">road type</span>` is a small label, `rs-chip accent` tints it with the page's `--accent`, and `<span class="rs-dot" style="background:#15803d"></span>` is a colour mark before a word.

## Charts

```js
const s = document.querySelector("#chart");
rs.svg(s, "line", {x1: 0, x2: 300, y1: 40, y2: 40, stroke: "var(--rs-chart-grid)"});
rs.svg(s, "polygon", {points: "...", fill: "var(--rs-chart-band)", stroke: "var(--rs-chart-band-line)"});
rs.svg(s, "text", {x: 4, y: 12, fill: "var(--mut)", "font-size": 9}, "0");
```

`rs.svg` makes one SVG element. An SVG attribute does not read `var(--x)`, so a value that starts with `var(` goes to the style. The chart then follows the theme with no code of its own. The colours that charts share are `--rs-chart-band`, `--rs-chart-band-line`, `--rs-chart-grid` and `--rs-chart-miss`; for text and lines use the panel's `--ink`, `--mut`, `--line` and `--card`. What is drawn on a canvas cannot read a variable: redraw it on the event `rs:themechange`.

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

A click or an arrow key selects. The chosen button has `on` and `aria-selected`; the panes beside the tabs (the siblings with `data-pane`) show the one with the same id. The selected one is in `--accent`: set it for the page with `#sb{--accent:#0E7F91}` in `page_style`.

## A hover box

```js
rs.hover.on(chartNode, ev => "<b>Saturday</b><br>24 hours");     // the text, or a function of the event; null hides
rs.hover.show("<b>A street</b>", mapEvent.originalEvent);         // by hand, over a map layer
rs.hover.hide();
```

The box has the popup's look and follows the pointer. It flips to the other side at the edge of the page and never takes the pointer. The words can have HTML.

## A list or a table that scrolls

```html
<div class="rs-scroll"><table class="rs-table"><thead><tr><th data-sort="desc">Street</th><th>Hours</th></tr></thead><tbody>...</tbody></table></div>
```

`rs-scroll` gives the area the panel body's scroll rules: a thin scrollbar that shows only over the area or while it scrolls, a fade at the bottom edge while there is more below, and a scroll that never goes on to the map. The height is `--rs-scroll-h` (default: the smaller of 520 px and 60 % of the window). `rs-table` keeps the header row in view, lines up the numbers (the first column is text) and tints the row under the pointer. Put `data-sort="asc"` or `"desc"` on the `th` of the sorted column.

## Both themes

The panel has a light and a dark theme. Your HTML must follow them. Plain text, links, tables, `hr`, inputs and buttons
already do. For your own colours, use the panel's variables, and not fixed colours:

| Variable | Use |
|---|---|
| `var(--ink)`, `var(--mut)` | text, muted text |
| `var(--bg)`, `var(--card)` | the panel's background, a box in it |
| `var(--line)` | thin lines |
| `var(--accent)` | links and buttons |

`.sb-note` is small, muted text and `.rs-sec-box` is a box. Both have a contrast of 4.5 or more in the two themes. The rows of
`legend` follow the theme too.

## Scrolling

The panel's title stays, and only the body scrolls. The scrollbar is at the outer edge of the panel: at the left of a left panel,
at the right of a right panel. It shows only when you point at the panel or scroll. A soft fade at the bottom edge shows that more
content is below. The scrollbar has a contrast of 3:1 or more in both themes. Your sections scroll with the rest, and you do not need CSS for it.

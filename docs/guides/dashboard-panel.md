# Add to the panel

<p class="lead">A page adds its own blocks to the dashboard's side panel, hides some of the panel's blocks, and adds rows to the legend. No edit of the template's HTML is necessary.</p>

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

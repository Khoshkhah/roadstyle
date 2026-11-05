# Add to the panel

<p class="lead">The panel of a dashboard starts empty. A page adds what it needs: a part of roadstyle (the query box, the road card) or its own HTML. No edit of the HTML of the template is necessary. The frame, the toolbox and the phone form are in [Dashboard layout](dashboard-layout.md).</p>

## The panel starts empty

The panel has only its frame: the title (the page's `name`), the theme button and the hide button. It has no section of its own. The base map, the color and the legend are tools of the toolbox, not sections of the panel.

A page adds sections with `dashboard={"panel": {"sections": [...]}}`, in their order. A section holds one of these:

- **A part of roadstyle** (`part`):
    - `"query"`: a WHERE clause over the columns of the roads, with *Run*, *Filter*, *Colour* and *Reset*, and the list of the matching roads. `text` is the start text (none: an empty box).
    - `"road_card"`: the fields of the selected road. It fills on the event `rs:select` and empties on `rs:deselect`. `fields` is the list of columns that it shows (none: every column).
- **The page's own HTML** (`html`). Build it from the [shared parts](dashboard-parts.md) of a dashboard.

A section with a `label` is a card, and the label is its title ([Cards: the panel standard](#cards-the-panel-standard)). `fold: true` makes the card fold, `note` is one line of state under the title, and `background: false` takes its colour away. `after` or `before` is the id of an earlier section. The keys, with their defaults, are in [Dashboard options](../reference/parameters.md#dashboard-options).

```python
rs.render_dashboard(edges, dashboard={
    "panel": {"sections": [
        {"id": "q", "part": "query", "label": "Query", "text": "p.maxspeed_kmh >= 50"},
        {"id": "road", "part": "road_card", "label": "Selected road", "fields": ["name", "highway", "lanes"]},
        {"id": "notes", "label": "Notes", "before": "road",
         "html": '<p>Your text</p><p class="sb-note">Small print</p>'},
    ]},
})
```

## The errors

These are errors:

- an `id` that is empty or used twice;
- a section with both `html` and `part`, or with neither;
- an unknown `part`;
- `text` on a part that is not `query`, and `fields` on a part that is not `road_card`;
- an `after` or `before` that is not an earlier section, or both of them;
- `fold: true`, `note` or `background: false` without a `label`.

There is no `hide`, because the panel has nothing of its own to hide. A page that gives `hide` gets an error that says what to do.

## A click on a road: the popup, the card, or both

A click on a road selects it, and the page sends the event `rs:select` with the fields of the road. The map of a dashboard is the map of a map page, with the same defaults, so a click opens the popup (`road_popup=True`). The road card is a second way to show the same click. Use one of them or both:

| You want | Give |
|---|---|
| the popup only | nothing (the default) |
| the card in the panel only | a section `{"part": "road_card"}` and `road_popup=False` |
| both | a section `{"part": "road_card"}` |
| your own | `road_popup=False`, and a listener of `rs:select` in `page_script` |

Hover, select and tooltip are separate switches: `road_tooltip` shows a tooltip, and `hover_color` lights the road.

## The same from JavaScript

`rs.sections` does the same from the page's script, after the page is ready:

```js
rs.ready(() => {
  rs.sections.add({id: "q", part: "query", label: "Query", text: "p.highway == 'primary'"});
  rs.sections.add({id: "notes", label: "Notes", html: "<p>Text of the page</p>", fold: true});
  document.addEventListener("rs:sectionchange", e => console.log(e.detail.id, e.detail.state));
});
```

### A card that opens something

When the only work of a card is to open your own panel, editor or dialog, give it `open` (a function) in place of `fold` and a body. The card is then one button: a click anywhere on it, or Enter on its title, runs the function. Its row ends with a pencil in place of the chevron, its background has a light tint of the accent colour, it never folds, and "Collapse all" leaves it. Its `note` tells the state, and `rs.sections.note(id, text)` changes it. `open` is JavaScript only, because it is a function. A card with `open` and `fold` gets an error.

```js
rs.sections.add({id: "design", label: "Edit design", note: "Light (Liberty)", open: () => myPanel.open()});
rs.sections.note("design", "Your theme");
```

To keep a card from opening (a step that is not ready), disable its title button: `rs.sections.get(id).querySelector(".rs-sec-title").disabled = true`.

All calls (`add`, `get`, `list`, `hide`, `show`, `remove`, `fold`, `foldAll`, `folded`, `note`) and the event `rs:sectionchange` are in the [JavaScript API](../reference/javascript.md#the-rs-object). The legend has `rs.legend`, which is in the same table.

## Cards: the panel standard

A section with a `label` is a card. Two options choose which of four kinds of card it is:

| | `background` (default) | `background: false` |
|---|---|---|
| does not fold (default) | `{"id", "label", "html"}` | `{"id", "label", "html", "background": False}` |
| `fold: true` | `{"id", "label", "html", "fold": True}` | `{"id", "label", "html", "fold": True, "background": False}` |

Each kind has the same title row, the same 12 px corners and the same padding (`--rs-card-pad`). A card with `background: false` has no colour behind it. In a card that folds, the title is a button, the row has a chevron, and the body opens inside the same card. An open card that folds has a thin accent ring inside its edge and an accent title, so that it shows in a long panel. The ring does not change the size of the card. A "?" of [`rs.help.button(rs.sections.get(id), ...)`](dashboard-parts.md#a-help-window) is at the right end of the title row. In a card that folds, it is before the chevron, and the chevron is last. A card that opens something ([`open`](#a-card-that-opens-something)) has a pencil in the place of the chevron, and a light tint of the accent colour.

A section without a `label` is not a card. It is a block of the page's own HTML, with no title, no padding and no background, for content that has its own layout: tabs with their panes, a row of number tiles, or the page's own cards. It is as wide as the cards and has `--rs-card-gap` above and below, as a card has. Its first card and its last card do not add a second gap, because their margins join the block's margin.

Do not write your own spacing, padding or corner radius: the panel sets them, and every dashboard then looks the same. Use the parts below:

| What | Use | Result |
|---|---|---|
| A card | a section with a `label` (the table above) | The four kinds of card |
| A card in the page's own HTML (in a tab, or several in one block) | `<div class="rs-sec-box"><div class="rs-card-title">Title</div>...</div>` in a section without a `label` | The same card: 12 px corners, `--rs-card-pad` inside, `--rs-card-gap` to the next card |
| A number tile | `rs.kpi(...)` in `class="rs-kpis"` | A tile in a grid of three |

Three CSS variables hold the numbers. A page can set them on `:root` to change them for all cards at once:

| Variable | Default | Meaning |
|---|---|---|
| `--rs-card-gap` | `12px` | The space between two cards, and between a card and a section without a label |
| `--rs-card-pad` | `14px` | The padding inside a card |
| `--rs-panel-bottom` | `28px` | The space under the last card, at the end of the panel |

A card that is closed shows only its title row. It is 14 + 16 + 14 = 44 px high with the default padding, and it is as wide as all other cards.

```python
rs.render_dashboard(edges, dashboard={"panel": {"sections": [
    {"id": "find", "label": "Find", "html": '<input placeholder="Street">'},                      # a card
    {"id": "notes", "label": "Notes", "fold": True, "html": "<p>Text of the page</p>"},           # a card that folds
    {"id": "tiles", "label": "Today", "background": False, "html": '<div class="rs-kpis" id="k"></div>'},   # a card with no background
    {"id": "tabs", "html": '<nav class="rs-tabs">...</nav><div data-pane="a">...</div>'},           # no label: the page's own block
]}})
```

Rules:

- Do not put an `rs-sec-box` inside a section with a `label`. The section is already a card, and a box in it makes a card in a card. Put the content directly in `html`.
- The buttons in the title row of the panel are in a fixed order: "collapse all" (`#rs-fold-all`) is at the left of "hide the panel" (`#sb-hide`). The panel does this by itself.
- Use `var(--accent-fill)` (`#0E7F91`) with white text for a filled control (a selected tab, a primary button). Use `var(--accent)` for links and marks. Do not use another teal.

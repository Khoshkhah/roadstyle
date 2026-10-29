# Add to the panel

<p class="lead">A page adds its own blocks to the dashboard's side panel, hides some of the panel's blocks, and adds rows to the legend. No edit of the template's HTML is necessary.</p>

## The panel's sections

The panel has five sections, in this order: `base_map`, `colour_by`, `legend`, `query`, `selected_road`. A section of your page
goes at the end of the panel, or `after` or `before` any section.

```python
rs.render_dashboard(edges, google_3d=True, dashboard={
    "panel": {
        "sections": [
            {"id": "notes", "label": "Notes", "after": "legend",
             "html": '<p>Your text</p><p class="sb-note">Small print</p><div class="rs-sec-box">In a box</div>'},
        ],
        "hide": ["base_map"],                  # the toolbox has the base map
    },
    "legend": {"rows": [{"color": "#ff0066", "label": "Events"}]},
})
```

A wrong `id`, an `after` or `before` that is not a section, or a name in `hide` that is not a section is an error.

## The same from JavaScript

| Call | What it does |
|---|---|
| `rs.sections.add({id, html, el, label, after, before})` | adds a section; it returns its box |
| `rs.sections.list()` / `get(id)` | the ids in order; the box of a section (move it into your own tab) |
| `rs.sections.hide(id)` / `show(id)` / `remove(id)` | hide or show any section; remove only your own |
| `rs.legend.add({id, color, label})` or `{id, html}` | a row of the legend; `remove(id)`, `list()` |

The event `rs:sectionchange` has `detail.id` and `detail.state`.

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

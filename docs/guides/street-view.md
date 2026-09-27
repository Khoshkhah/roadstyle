# Google Street View

<p class="lead">Click a road and see it in Google Street View, looking the way the road runs. No API key needed.</p>

<div class="grid cards" markdown>

-   :material-dock-window:{ .lg .middle } **The floating window**

    ---

    On every map by default: a Street View button opens a small window over the map.

    [:octicons-arrow-right-24: The floating window](#the-floating-window)

-   :material-view-split-vertical:{ .lg .middle } **Side by side**

    ---

    A page with the map and Street View next to each other, beside or below, with a divider you
    can drag.

    [:octicons-arrow-right-24: Side by side](#side-by-side)

</div>

!!! warning "Serve the page"
    Street View only loads in a page served over http(s). Opened from disk (`file://`) it stays
    grey and the page offers a link instead. Serve the folder with `python -m http.server` and
    open `http://localhost:8000/map.html`.

## The floating window

Press the **Street View** button (the person, under the 3D button) and click a road. The window
follows each new click. Drag its title bar to move it and its corner to resize it. The page
remembers whether it was open, and where.

<iframe src="../../maps/street_view_window.html" loading="lazy" title="A map with the Street View window open" class="rs-demo"></iframe>

```python
rs.render_edges(edges)                       # street_view="window": the button and window (default)
rs.render_edges(edges, street_view=True)     # a Street View link in the road popup instead
rs.render_edges(edges, street_view=False)    # no Street View
```

## Side by side

A page of its own: the map and Street View share the screen. Click a road and Street View shows it.

**Beside the map**

<iframe src="../../maps/street_view.html" loading="lazy" title="The map with Google Street View beside it" class="rs-demo"></iframe>

**Below the map**

<iframe src="../../maps/street_view_below.html" loading="lazy" title="The map with Google Street View below it" class="rs-demo tall"></iframe>

=== "Python"

    ```python
    rs.render_street_view(edges).save("street_view.html")                  # beside
    rs.render_street_view(edges, layout="below").save("street_view.html")  # below
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg --page street-view -o street_view.html
    roadstyle edges.gpkg --page street-view --layout below -o street_view.html
    ```

| option | default | does | command line |
|---|---|---|---|
| `layout` | `"beside"` | `"beside"` or `"below"` the map | `--layout below` |
| `panel_width` | `42` | Street View's share of the width (of the height when below), 20-80 % | `--panel-width 60` |
| `resizable` | `True` | a divider the viewer can drag; `False` fixes the size | `--no-resize` |

Every `render_edges` keyword also works here. On a phone, Street View sits under the map.

## Where it looks

- Street View stands on the clicked road's centre line, at the point nearest the click, and looks
  the way the edge runs.
- On a two-way road each direction stands 2.5 m to its right, in its own lane, so the two
  directions look opposite ways.
- A **marker** (a dot and a cone) on the map shows where Street View stands and which way it looks.
- The **◀ ▶** buttons walk 15 m back or forward along the road.

Google shows the nearest panorama it has. Where it has no car imagery, that can be a photo someone
uploaded.

**Privacy:** nothing is sent to Google until Street View is opened (side by side: until a road is
clicked). The request carries only the position and the heading.

From your own page: `rsSetStreetView(true)` opens the window, `rsStreetViewStep(15)` steps, and
the `rs:select` event carries the Street View URL. See the [JavaScript API](../reference/javascript.md).

**See also:** [Every parameter](../reference/parameters.md) · [Command line](../reference/cli.md) · [Dashboards & JavaScript](dashboards.md)

# Dashboards & JavaScript

<p class="lead">Get a finished dashboard page in one call, or put your own panel next to the map and drive it from JavaScript.</p>

To learn each part, with the result in view, open the [Dashboard manual](dashboard-manual/index.md): the [Python SDK](dashboard-manual/python.md) and [JavaScript](dashboard-manual/javascript.md).

=== "Python"

    ```python
    import roadstyle as rs

    rs.render_dashboard(edges, color_options={
        "Road class": {},
        "Speed": {"color_by": "maxspeed_kmh", "cmap": "plasma"},
    }).save("dashboard.html")
    rs.render_street_view(edges).save("street_view.html")
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg --page dashboard -o dashboard.html
    roadstyle edges.gpkg --page street-view -o street_view.html
    ```

## Ready-made pages

| call | what you get |
|---|---|
| `rs.render_dashboard` | the map, a toolbox, and a panel that starts empty |
| `rs.render_street_view` | Google Street View beside or below the map ([Google Street View](street-view.md)) |

Each takes every `render_edges` keyword and returns the same map object (`.save()`, `.html`).
`color_options` fills the *Colour by* list in the toolbox. `name=` sets the page title.

![The dashboard on a desktop: the panel at the left, the toolbox at the right edge, and Monaco's roads](../img/dashboard-desktop.png)

The picture shows Monaco, made with `rs.render_dashboard(edges, name="Monaco", basemap="ofm_positron")` at 1400 by 900.

## What a dashboard has

A dashboard has three things, in the same places on every page. You do not build them. You change them with the one option `dashboard={...}`.

- **The map** is the map of a map page, with the same defaults: the base map `ofm_positron` (OpenFreeMap, no key), `road_popup=True`, and the `minzoom` of the profile. The template sets no map keyword. Give any keyword of `render_edges` to change the map.
- **The toolbox** is one bar of tools at the edge of the window: theme, navigate, Street View, Google 3D, base map, roads, 3D buildings, colour and legend, settings and credits. A tool that the page cannot use is greyed out. You can add tools of your own with `rs.tools`. The tools, the frame and the phone form are in [Dashboard layout](dashboard-layout.md).
- **The panel** starts empty. The page adds sections to it: the query box, the road card, or its own HTML built from the [shared parts](dashboard-parts.md). See [Add to the panel](dashboard-panel.md).

```python
rs.render_dashboard(edges, dashboard={
    "toolbar": {"position": "left"},
    "panel": {"side": "right", "sections": [{"id": "q", "part": "query"}]},
})
```

Every key of `dashboard=`, with its default, is in [Dashboard options](../reference/parameters.md#dashboard-options). The calls to build your own panel and tools from JavaScript (`rs.sections`, `rs.legend`, `rs.tools`) are in the [JavaScript API](../reference/javascript.md#the-rs-object).

## Views: several settings in one menu

`views=` adds a *View* menu above *Colour by* on a map page (`render_edges`). A view is a name and the settings that it sets together. The page opens with the first one.

```python
rs.render_edges(edges, color_options={"Class": {}},
                views={"Normal":      {"color": "Class", "road_fill": True},
                       "Casing only": {"road_fill": False},
                       "Main roads":  {"classes": ["motorway", "trunk", "primary", "secondary", "tertiary"]}})
```

A page with the toolbox (the dashboard) hides the View menu. Call `rsSetView(name)` from your own control there. The settings of a view and the traps are in [Every parameter](../reference/parameters.md#render_edges) (the keyword `views`).

## Drive the map from your own page

`m.html` is the saved page as a string. You can put your own panel before `</body>` and drive the map through the `window.rs*` functions and the `rs:*` events. The example, and the traps of a host page (the ids past 2**53, a fixed side panel that covers the map), are in the [JavaScript API](../reference/javascript.md#drive-the-map-from-your-own-page).

**See also:** [Dashboard manual](dashboard-manual/index.md) · [JavaScript API](../reference/javascript.md) · [Command line](../reference/cli.md) · [Every parameter](../reference/parameters.md)

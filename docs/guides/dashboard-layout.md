# Dashboard layout

A dashboard is a map with a side panel. `render_dashboard` makes it from your road data. It starts with a blank map (no key), the panel and the toolbox at the left, and no scale box.

```python
import roadstyle as rs

rs.render_dashboard(edges, color_options={"Road class": {}}).save("dashboard.html")
```

## The form

There is one template with a panel: `dashboard`. A future template follows its style. `layout` changes the frame:

| Keyword | What you get |
|---|---|
| `layout="overlay"` (default) | The map fills the window. The panel floats over it, at the left, with the toolbox next to it |
| `layout="dock"` | The panel is docked at the left and takes its own space. No toolbox: the tools are the MapLibre buttons |

`template="map"` is the map only (the default of `render_edges`). There is no `classic` and no report page: use `render_dashboard`.

## The toolbox

The bar has one button for each tool: theme, zoom in, zoom out, compass, 2D/3D, Street View, Google 3D, base map, 3D buildings,
colour and legend, settings, attribution. The toolbox is fixed: a tool that the page cannot use stays in its place, greyed out, and its tooltip says why.

A button that opens a box opens it toward the map. One box is open at a time. A click outside the box, or the Escape key, closes it.

The panel scrolls under its title. Your own blocks and legend rows: [Add to the panel](dashboard-panel.md). An older script? [Move a dashboard](migrating-dashboard.md).

To add a tool of your own, use `rs.tools`:

```javascript
rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => save()});
```

To hide the bar until your tools are in, use `dashboard={"toolbar": {"hold": True}}` and call `rs.tools.ready()` (the bar shows after 6 s at the latest).
`dashboard=` changes any option of the template, for example the bar's `position` or the panel's `look`.

## The settings

The gear button opens the settings. They are kept in the browser, not in the page file.

- **Layout.** The bar can be at the left, the top, the right or the bottom. The panel can be at the left or the right,
  as a frame (default) or as a card. The scale and zoom box can be shown.
- **Transparency.** Three sliders: the bar and the panel, the boxes with the popup and the tooltip, and the card behind the text.
- **Keys.** A Google Maps key (Street View and Google 3D) and a CARTO key. A key that you save is used instead of the key of the page.
  A page with a toolbox needs no Google key at build time: the person adds it.

## The windows

Street View and Google 3D open in the middle of the free part of the map. The panel and the bar do not cover them.
A window keeps the size that you give it. Google 3D has a view switch, **Imagery** or **Map**, and **Follow** is on at the start.

## A phone

At 700 px or less, the bar is at the top. The panel is a bottom sheet with three heights: closed, 40 % and full.
A window is a bottom sheet too. Only one sheet is open at a time.

## The area boundary

`boundary=` (GeoJSON, or a shapely geometry) is an input of the page: the map shows a dashed line along it. `boundary_dim=True` shades the
outside. `boundary_limit=True` keeps the camera near it. Both are off by default, because a page can show a general map.

## Style

Every part uses the same tokens and works in both themes. The rules are in `docs/design/dashboard_templates.md`, section 3.4.

# Dashboard layout

A dashboard is a map with a side panel. `render_dashboard` makes it from your road data.

```python
import roadstyle as rs

rs.render_dashboard(edges, color_options={"Road class": {}}).save("dashboard.html")
```

## The form

There is one template with a panel: `dashboard`. A future template follows its style. `layout` changes the frame:

| Keyword | What you get |
|---|---|
| `layout="overlay"` (default) | The map fills the window. The panel floats over it. The toolbox is a bar at the right |
| `layout="dock"` | The panel is docked at the right and takes its own space. No toolbox: the tools are the MapLibre buttons |

`template="map"` is the map only (the default of `render_edges`). There is no `classic` and no report page: use `render_dashboard`.

## The toolbox

The bar has one button for each tool, in this order: theme, zoom in, zoom out, compass, 2D/3D, Street View,
Google 3D, base map, 3D buildings, colour and legend, settings, attribution. A tool that the page does not use is not on the bar.

A button that opens a box (base map, colour and legend, settings, attribution) opens it toward the map. One box is open at a time.
A click outside the box, or the Escape key, closes it.

An older script? See [Move a dashboard to the new version](migrating-dashboard.md).

To add a tool of your own, use `rs.tools`:

```javascript
rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => save()});
```

To hide the bar until your tools are in, use `dashboard={"toolbar": {"hold": True}}` and call `rs.tools.ready()` when they are added (the bar
shows after 6 s at the latest). The keyword `dashboard=` changes any option of the template, for example the bar's `position` or the panel's `look`.

## The settings

The gear button opens the settings. They are kept in the browser. They are not in the page file.

- **Layout.** The bar can be at the left, the top, the right or the bottom. The panel can be at the left or the right,
  as a frame (default) or as a card. The scale and zoom box can be hidden.
- **Transparency.** Three sliders: the bar and the panel, the boxes with the popup and the tooltip, and the card behind the text.
- **Keys.** A Google Maps key (Street View and Google 3D) and a CARTO key. A key that you save is used instead of the key of the page.
  A page with a toolbox can be built with no Google key. The person who opens it adds the key in the settings.

## The windows

Street View and Google 3D open in the middle of the free part of the map. The panel and the bar do not cover them.
A window keeps the size that you give it. Google 3D has a view switch, **Imagery** or **Map**, and **Follow** is on at the start.

## A phone

At 700 px or less, the bar is at the top. The panel is a bottom sheet with three heights: closed, 40 % and full.
A window is a bottom sheet too. Only one sheet is open at a time.

## The area boundary

If the page has a `boundary` (a polygon), the map shows a line along it and shades the outside.
The camera stays near it, and you can still zoom out and move the whole area off the screen.
Give the polygon with `boundary=` (GeoJSON, or a shapely geometry).

## Style

Every part uses the same tokens and works in the light and the dark theme. The rules are in
`docs/design/dashboard_templates.md`, section 3.4.

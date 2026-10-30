# Dashboard layout

A dashboard is a map with a side panel. `render_dashboard` makes it from your road data. It starts with a blank map (no key), the panel at the left, the toolbox at the right edge, and no scale box. Every road class shows at every zoom, but service roads and living streets (from zoom 14), steps, platforms, corridors, roads and private roads (from 15); `minzoom=False` shows all.

```python
import roadstyle as rs

rs.render_dashboard(edges, color_options={"Road class": {}}).save("dashboard.html")
```

## The form

There is one template with a panel: `dashboard`. A future template follows its style. `layout` changes the frame:

| Keyword | What you get |
|---|---|
| `layout="overlay"` (default) | The map fills the window. The panel floats over it, at the left. The toolbox is a column at the right edge (`dashboard={"toolbar": {"position": "left"}}` moves it); its boxes open to its left |
| `layout="dock"` | The panel is docked at the left and takes its own space. No toolbox: the tools are the MapLibre buttons |

`template="map"` is the map only (the default of `render_edges`). There is no `classic` and no report page: use `render_dashboard`.

## The toolbox

The bar has one button for each tool: theme, navigate, Street View, Google 3D, base map, roads, 3D buildings,
colour and legend, settings, attribution. The toolbox is fixed: a tool that the page cannot use is greyed out, and its tooltip says why.
**One button** (the compass needle) navigates the map: a click opens a zoom, turn and tilt box; Ctrl + drag on the map turns and tilts it.
`"navigation": "buttons"` brings the old buttons back (+, -, compass, 2D/3D). **Roads** filters the road types (check box and count for each class; All, None; a click on a name shows only it). The credits button is in the bottom corner, with the scale and zoom number.

A box opens toward the map; one box is open at a time. A click outside it, or Escape, closes it.

Your own blocks and legend rows: [Add to the panel](dashboard-panel.md). Older script? [Move a dashboard](migrating-dashboard.md).

To add a tool of your own, use `rs.tools`:

```javascript
rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => save()});
```

To hide the bar until your tools are in, use `dashboard={"toolbar": {"hold": True}}` and call `rs.tools.ready()` (after 6 s at the latest the bar shows).
`dashboard=` changes any option, for example the bar's `position`.

## The settings

The gear button opens the settings; the browser keeps them.

- **Layout.** The bar: left, top, right or bottom. The panel: left or right, as a frame (default) or a card. The scale box can show.
- **Transparency.** Three sliders: the bar and the panel, the boxes with the popup and the tooltip, and the card behind the text.
- **Keys.** A Google Maps key (Street View, Google 3D) and a CARTO key. A saved key replaces the page's key. A page needs no Google key at build time.

## The windows

Street View and Google 3D open in the free part of the map. A window keeps its size. Google 3D has a view switch, **Imagery** or **Map**, and **Follow** is on at the start.

## A phone

At 700 px or less, the bar is at the top and the panel is a bottom sheet (closed, 40 % or full). A window is a bottom sheet too; one sheet is open at a time.

## The area boundary

`boundary=` (GeoJSON or a shapely geometry) is an input of the page: a dashed line shows it. `boundary_dim=True` shades the outside; `boundary_limit=True` keeps the camera near it.

## Style

Every part uses the same tokens in both themes (rules: `docs/design/dashboard_templates.md`, 3.4).

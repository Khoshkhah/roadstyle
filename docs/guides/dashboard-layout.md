# Dashboard layout

A dashboard is a map with a side panel. `render_dashboard` makes it from your road data. It starts with a blank map (no key), the panel and the toolbox at the left, and no scale box. Every road class shows at every zoom (`minzoom=True` hides the minor ones when zoomed out).

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

The bar has one button for each tool: theme, navigate, Street View, Google 3D, base map, 3D buildings,
colour and legend, settings, attribution. The toolbox is fixed: a tool that the page cannot use is greyed out, and its tooltip says why.
The map is navigated with **one button** (the compass needle): a click opens a box with a zoom, a turn and a tilt slider, and Ctrl + drag on the map turns and tilts it.
`dashboard={"toolbar": {"navigation": "buttons"}}` brings the buttons back (+, -, compass, 2D/3D). The credits button is in the bottom corner, with the scale and the zoom number.

A box opens toward the map; one box is open at a time. A click outside it, or Escape, closes it.

Your own blocks and legend rows: [Add to the panel](dashboard-panel.md). An older script? [Move a dashboard](migrating-dashboard.md).

To add a tool of your own, use `rs.tools`:

```javascript
rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => save()});
```

To hide the bar until your tools are in, use `dashboard={"toolbar": {"hold": True}}` and call `rs.tools.ready()` (after 6 s at the latest the bar shows).
`dashboard=` changes any option, for example the bar's `position`.

## The settings

The gear button opens the settings. The browser keeps them, not the page file.

- **Layout.** The bar: left, top, right or bottom. The panel: left or right, as a frame (default) or a card. The scale box can show.
- **Transparency.** Three sliders: the bar and the panel, the boxes with the popup and the tooltip, and the card behind the text.
- **Keys.** A Google Maps key (Street View, Google 3D) and a CARTO key. A saved key replaces the page's key. A page needs no Google key at build time.

## The windows

Street View and Google 3D open in the free part of the map. A window keeps the size that you give it. Google 3D has a view switch, **Imagery** or **Map**, and **Follow** is on at the start.

## A phone

At 700 px or less, the bar is at the top and the panel is a bottom sheet (closed, 40 % or full). A window is a bottom sheet too; one sheet is open at a time.

## The area boundary

`boundary=` (GeoJSON or a shapely geometry) is an input of the page: a dashed line shows it. `boundary_dim=True` shades the outside, `boundary_limit=True` keeps the camera near it (both off by default).

## Style

Every part uses the same tokens and works in both themes (rules: `docs/design/dashboard_templates.md`, 3.4).

# The dashboard layout

<p class="lead">Two options of <code>render_dashboard</code> change how the page is laid out: the panels float over a full-size map, and the map's controls sit on one bar.</p>

```python
rs.render_dashboard(edges)                                      # the default: the panels take their own space
rs.render_dashboard(edges, layout="overlay", toolbar="right")   # the overlay layout and a bar at the right edge
```

## layout

| Value | Result |
|---|---|
| `"dock"` | The default. The panels take their own space, and the map is the rest of the window. |
| `"overlay"` | The map fills the window. The panels float over it, with a solid background and a shadow. |

In the overlay layout, a panel that opens or closes never resizes the map and never moves the camera, a window, a marker or a control. A hidden right panel shows a 32 px chevron at the top right of the map. An open panel has its own hide button in its header.

The overlay layout also sets the rules of the floating windows (Google 3D and Street View):

- A window stays inside the map at every drag and resize.
- A drag of a window never moves the map. The page sets `window.rsWindowRecentre = false`.
- A window opens in the visible part of the map: right of an open left panel, left of an open right panel.
- The window remembers its position and its size.

The Google 3D camera follows the map at all times. See [The Google 3D camera link](google-3d-camera.md).

## toolbar

| Value | Result |
|---|---|
| `False` | The default. The controls stay in roadstyle's plain column. |
| `"right"` | A vertical bar at the right edge, centred, 44 px wide. |
| `"left"` | The same at the left edge. |
| `"top"` | A horizontal bar at the top, centred, 44 px high. |
| `"bottom"` | The same at the bottom. |

The bar is half transparent: white at 70 %, with a slight blur, a 1 px border and rounded corners. It is 8 px from the edge. It holds the buttons only, in this order: zoom in, zoom out, compass, 2D/3D, Street View, Google 3D, base map and the controls that the page adds. Each button is a 32 px flat square with a tooltip.

The bar never changes its size. The scale bar, the zoom level and the attribution stay where roadstyle puts them.

A panel on the same side as the bar never covers it: when the panel opens, the bar slides 8 px beside it (150 ms), and it slides back when the panel closes. The list of base maps opens toward the centre of the map.

The chevron of a hidden right panel is not a control of the bar. It stays at the top right corner of the map.

## Check it

The tests are in `tests/test_dashboard_layout.py`. They check that the default page does not change, that the overlay adds its style and script, and that each of the four positions adds its rules. A browser test of a page that uses these options is `tools/test_map.py` in the simready repository.

## OpenFreeMap base maps

The base-map list offers three vector styles with no key: "OpenFreeMap Liberty", "OpenFreeMap Bright" and "OpenFreeMap Positron". The page merges the style under the roads. Its extruded buildings draw after the roads in 3D, and its flat buildings show in 2D. `window.rsBuildings(false)` hides the buildings, and `window.rsBuildings(true)` shows them. The event `rs:basemapready` tells the page that the style is in, so the page can put its own top layers back on top.

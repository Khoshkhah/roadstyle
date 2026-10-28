# Google 3D

<p class="lead">See the roads in Google's photorealistic 3D view, next to the map. The two cameras move together.</p>

!!! note "A key is necessary"
    The Google 3D window needs a Google Maps JavaScript API key. See
    [Set up a Google key](google-key.md). The page must be served from an address in the key's
    Websites list, not opened from disk.

```python
rs.render_edges(edges, google_3d=True)                        # the key from GOOGLE_MAPS_KEY
rs.render_edges(edges, google_3d=True, street_view_key=KEY)   # or this key
```

Without a key, `google_3d=True` stops with an error. The default is `google_3d=False`.

## The window

Press the **Google 3D** button (the cube, under the Street View button). A window opens in the
bottom-left corner of the map. Drag its title bar to move it and its corner to change its size. The
page remembers if the window was open, and where. While the window is open, the center of the map
moves to the middle of the free part of the map, so the window does not cover the clicked road. Google's 3D view loads only when the window
opens, and the page removes it when you close the window.

## The two cameras move together

For the four links, the range, and a check, see [The Google 3D camera link](google-3d-camera.md).

When you move, turn, tilt or zoom the map, the 3D view moves to the same camera. When you do
this in the 3D view, the map follows.

| Map | Google 3D |
|---|---|
| center | center |
| bearing (turn) | heading |
| pitch (tilt) | tilt |
| zoom | range: the distance from the camera to the center, in metres |

Google puts its camera above sea level, and the map is on the ground. So the page reads the
height of the ground under the center from the free
[Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/) (Mapzen, no key), and gives it to
Google. Without it, the 3D view on a hill (Monaco: 120 m) was much closer than the map. The window
bar shows the credit **heights: Mapzen**. If the heights do not load, the bar shows
**⚠ no ground heights**: then the 3D view can be too close on a hill.

The map has the last word. If you move the 3D view to a place where the map cannot go, the map stops
at its limit and the 3D view goes back to the map's camera. This keeps the two views the same when the
page keeps the map inside a box (`map.setMaxBounds(...)`), and when you tilt more than the map can.

Some differences stay:

- The tilt stops at 70° in the two views (the map's setting `camera.max_pitch`).
- The window is smaller than the map, so it shows the same view at a smaller size. If the window has a
  different shape, it shows less on the sides.

## Click a road

When you click a road, the 3D view draws the road in the selection color and the camera flies to
the middle of the road and looks along it. The map follows the camera.

## From JavaScript

| Call or event | What it does |
|---|---|
| `rsSetGoogle3D(true)` / `rsSetGoogle3D(false)` | opens / closes the window |
| `rs:google3dchange` | fires when the window opens or closes; `e.detail.open` |

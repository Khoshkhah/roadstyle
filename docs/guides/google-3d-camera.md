# The Google 3D camera link

<p class="lead">How the map camera and the Google 3D camera follow each other, and how to check it.</p>

## 1. The four links

When the map moves, the 3D camera gets these values. When the 3D camera moves, the map gets them back.

| Map | Google 3D | Rule |
|---|---|---|
| Center | Center | The same longitude and latitude. |
| Bearing | Heading | The same angle, from 0 to 360 degrees. |
| Pitch | Tilt | The same angle. 0 is a view straight down. |
| Zoom | Range | The distance from the camera to the center. See section 3. |

## 2. The ground height

Google's camera measures its center height above sea level. The map center lies on the ground. On a hill, a center at 0 m is under the ground.

The page reads the ground height from the free Terrain Tiles on AWS (Terrarium PNG files, zoom 14). The height is `R * 256 + G + B / 256 - 32768` metres, from the red, green and blue values of the pixel under the center. The sea counts as 0 m.

If a tile does not load, the window title bar shows the warning "no ground heights", and the last height found stays. A page can serve the tiles from its own server. Simready does this.

## 3. The range

The rule: the 3D window covers the same vertical ground extent as the map canvas.

The map camera has a vertical field of view of 36.87 degrees. By default, the range is:

`range = canvas_height_px * metres_per_pixel / 2 / tan(36.87 / 2)`

`metres_per_pixel = 40075016.686 * cos(latitude) / (512 * 2^zoom)`

Google's camera has a narrower field of view, so the window showed less ground than the map. A page can set `window.rsG3dFov`, the vertical field of view of Google's camera in degrees. The range then uses this value in place of 36.87.

The measured value is 25.4 degrees. It was measured on 2026-10-27 at Monaco. The 3D window showed about 500 m of ground at range 773 m at tilt 0. Landmarks on the OpenStreetMap map gave the ground width. The angle is `2 * atan((ground_height / 2) / range)`. A second check agreed within 10 %: the Palais Princier lay at 78 % of the height in both views.

The option is not set by default. Without it, the range is unchanged.

If the window is narrower than the map, it shows less ground at the sides. The vertical extent stays the same.

## 4. One camera

The 3D camera follows the map at all times. A page that wants this rule must never fly the 3D camera alone. In the simready review page, a click on a road flies the map to the road, and the 3D view follows.

By default, roadstyle moves the map center to the free part of the map while the window is open. The option `window.rsWindowRecentre = false` switches this off. The map then never moves when the window opens, closes, or is dragged.

A review page sets this option to false, because a drag of a window or a toggle of a panel must not move the map.

One owner leads each gesture. While the pointer is down in the 3D window, the 3D view leads. The map follows with one `jumpTo` per frame, and the map's moves do not go back to the 3D view. While the map is dragged, the map leads. The page releases the owner one frame after the pointer goes up, and then makes the two cameras equal once. This stops the map from shaking in a swipe.

## 5. Check the link in a browser

The simready page has a debug line. Open the page with `?debug=1` and open the Google 3D window. The line shows:

- the map center, zoom, bearing, pitch, canvas size and the width of ground in metres;
- the 3D center, altitude, range, heading, tilt and window size;
- the range that the page sets, and the distance in metres between the two centres.

To check the link in ten minutes:

1. Open the page on a screen, with a key that allows the address.
2. Set the zoom to 15.8, 16.8 and 17.8. Keep the tilt at 0.
3. At each zoom, read the width of ground in the map and in the 3D window. Use two landmarks near the sides of each view.
4. Compare the vertical extents. They must agree within 10 %.
5. Read the distance between the centres. It must be less than 5 m.

## 6. The limits

- A difference under 10 % is normal.
- The map limits the tilt. Where the map cannot follow, it stops at its limit, and Google goes back to the map camera.
- The window shows the same view as the map, but smaller.
- A headless browser does not draw Google 3D. Use a browser with a screen.
- The "Labels" switch of the base-map box rules the 3D view too: on gives Google's HYBRID mode (labels and pins), off gives SATELLITE. Without that switch the view has no labels.
- The 3D view always shows Google's photorealistic imagery (SATELLITE or HYBRID). If Google reports an error, the window says "Google 3D imagery did not load".
- A selected road is drawn by its level: on the ground (level 0), at its deck height (a bridge, 6 m a level unless `window.rsG3dDeckM(props, level)` says otherwise), or dashed on the surface above it with a note in the bar (a tunnel).

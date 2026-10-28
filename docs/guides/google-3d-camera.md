# The Google 3D camera link

<p class="lead">How the map camera sets the Google 3D camera, one way only, and how to check it.</p>

## 1. The four links

When the map moves, the 3D camera gets these values. The map never gets values from the 3D camera.

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

## 4. The map leads, one way only

Google moves its own camera by hidden rules: its limits, the mesh under its target, and inertia. It does not report them. A link in both directions made an echo, jumps and mismatches. So the link goes one way.

- On every map move, the page sets the 3D camera from the map. It coalesces the moves to one set per frame.
- No code path moves the map from the 3D camera. A change of the 3D camera of any kind, with input or without, never changes the map.
- The 3D window is a viewer. The reviewer can drag, turn and zoom in it. That moves only the 3D view.
- The window bar has a "Follow" button: "Following" (filled) when it is on, "Follow the map" (outlined) when it is off. It is on by default. A drag in the picture (the pointer moves more than 6 px while down), a second finger, a wheel or a key turns it off. A plain click, a click on Google's own controls (the view switch, the compass, the expand button) and input on the title bar do not. While it is off, the map does not set the 3D camera.
- A click on the "Follow" button turns it on and sets the 3D camera to the map once. A road selection and a Guide step also turn it on. The window turns it on when it opens.
- Google's own view switch changes only the picture, and the map does not move. With Follow on, the page sets the 3D camera to the map's once, 300 ms after the switch (also after the Labels switch). With Follow off it sets nothing.
- A click on a road never flies the 3D camera alone. The page flies the map, and the 3D view follows the map while Follow is on.

By default, roadstyle moves the map center to the free part of the map while the window is open. The option `window.rsWindowRecentre = false` switches this off. A review page sets it to false, because a drag of a window or a toggle of a panel must not move the map.

`window.rsG3dCount` holds `m2g` (the number of sets of the 3D camera) and `follow`. `window.rsG3dFollow(on)` sets the Follow state from the page.

## 5. Check the link in a browser

The simready page has a debug line. Open the page with `?debug=1` and open the Google 3D window. The line shows:

- the map center, zoom, bearing, pitch, canvas size and the width of ground in metres;
- the 3D center, altitude, range, heading, tilt and window size;
- the range that the page sets, the distance in metres between the two centres, the Follow state, and the number of sets of the 3D camera per second.

To check the link in ten minutes:

1. Open the page on a screen, with a key that allows the address.
2. Set the zoom to 15.8, 16.8 and 17.8. Keep the tilt at 0.
3. At each zoom, read the width of ground in the map and in the 3D window. Use two landmarks near the sides of each view.
4. Compare the vertical extents. They must agree within 10 %.
5. Read the distance between the centres. It must be less than 5 m.

## 6. The limits

- A difference under 10 % is normal.
- The map limits the tilt. The 3D camera gets the map's value, so it stops at the same limit.
- The window shows the same view as the map, but smaller.
- A headless browser does not draw Google 3D. Use a browser with a screen.
- The "Labels" switch of the base-map box rules the 3D view too: on gives Google's HYBRID mode (labels and pins), off gives SATELLITE. Without that switch the view has no labels.
- The page sets the mode of the 3D view only when the window opens and when the Labels switch changes (SATELLITE, or HYBRID with labels). Google's own toggle (the round thumbnail at the top right of the window, imagery or Google's stylised 3D map) is allowed, and the page leaves it alone. A choice of the stylised map is kept for the next opening, and the selected road is drawn again after a change of mode. If Google reports an error, the window says "Google 3D imagery did not load".
- A selected road lies on Google's photorealistic mesh (`RELATIVE_TO_MESH`, 0.5 m, a vertex every 5 m, 4 px wide), not on its terrain model. A tunnel (level below 0) is dashed, with a note in the bar.
- Google's drawn 3D map (the dark-blue blocks, mode ROADMAP) keeps its camera much farther away than over the imagery, whatever the range the page sets. Over the imagery the title bar shows a note when the camera is lower than 80 m above the ground (`MIN_ALT`, or `window.rsG3dMinAlt`). In the drawn map it shows a note when the map's zoom is above 17 (`MIN_ZOOM_DRAWN`, or `window.rsG3dMinZoomDrawn`; a first value from one screenshot). The debug line of a review page shows the limit of the mode that is on.
- Google's own limits are shown, not fought. The note in the title bar says when the 3D view shows more than the map.

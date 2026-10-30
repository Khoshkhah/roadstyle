# The dark theme of the style's layers

Date: 2026-10-30. A host page (the duckOSM page) makes the roads style once and shows it on a light or on a dark base map. Before this
change, only the base map and its buildings turned dark: the area's own layers (land, parks, water, buildings, the casing of the
roads) kept the light colours, so the map was half dark.

## The design

A live style (a look with `state: "live"`, the style of every page with the dashboard) holds **two colours** for each layer colour. The
global state `rs_theme` (`"light"` or `"dark"`) picks one, as `["case", ["==", ["global-state", "rs_theme"], "dark"], <dark>, <light>]`.
The dashboard's theme switch (`rsSetTheme`, `theme.js`) sets `rs_theme`, at the start (when the style is loaded) and at each change.
No new style and no new tile: the tiles have the pieces of the roads, not their colours.

A style that is not live (`state: "static"`) has no dark colours and no state: its expressions do not change.

## The rule: the look's `dark` block

The dark colour is the light colour turned by one rule, in one place: the profile's `dark:` block (`data/profiles/default.yaml`,
`roadstyle_look::sections::DarkLook`; a look file made before has the same values by default). Each band places the colour's lightness
(0 black to 1 white) between two numbers and multiplies its saturation; the hue stays.

| band | what | default |
|------|------|---------|
| `area` | the fills and the 3D buildings of the base map's layers (land, parks, water, buildings, paved, parking) | lightness 0.08 to 0.24, saturation x 0.30 |
| `line` | their lines and outlines (waterways, railways, the outline of a fill) | 0.28 to 0.60, x 0.50 |
| `point` | their points and their icons | 0.30 to 0.80, x 1.0 |
| `casing` | the casing of the roads (**the fill of a road keeps its colour**, so a road stays readable on the dark map) | 0.12 to 0.42, x 0.85 |
| `label` | the names, the arrows and their halos (the first number is above the second: the lightness turns over, so grey becomes light and a white halo becomes dark) | 0.92 to 0.30, x 1.0 |

The selection and hover colours stay. The values were chosen on Monaco (Fiord and the blank dark base map) at zoom 15 and 16.5 on a
desktop and a phone screen; a different look can change the numbers in its own profile.

## What the engine writes (`roadstyle-engine/src/dark.rs`)

- A colour text of a layer's colour property (`"#rrggbb"`, `"#rgb"`, `rgb(...)`, `rgba(...)`) becomes the `case` above, in the band of the layer's
  type (fill, line, circle, text). A list of colours that an expression looks up (`["literal", [...]]`, the roads' casing table) has a dark list.
- The road layer `roads-simple*`: the casing table and the branch of the casing pieces. The fill table and the shadows stay.
- The textures of the land (`ms-pat-*`, PNG images of one colour) and the icons of the points (`ms-icon-*`, SVG) get a twin image
  `<name>-dark`, made at the build with the `area` and `point` bands. A layer names its image by the same `case`. A host adds every image of
  `roadstyle:images`, so it adds the twins too.
- `roadstyle:state` has `rs_theme: "light"` as the start value; a host that sets the state first keeps its own.

## What it costs (Monaco, the style of a live look)

The expressions grow by 9.0 KB (+11.5 %) and the 18 image twins add 7.1 KB: 16.5 KB in all (+18.8 % of a 88 KB style). Each of the 405 colour
literals has a twin, and the `case` wraps each. A style that is not live does not grow.

## Not covered

- A road's casing colour that comes from the data (a colour table, `__rs_casing` baked into the pieces) stays light.
- The arrow image of a map with no tunnels is a baked image, not an SDF one, so only its `icon-color` (the SDF case) follows the theme.
- A tiled style makes the boundary a tile layer; the dashboard's boundary shade needs a GeoJSON source (unchanged).

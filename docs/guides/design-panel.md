# Edit the design of a map

The code came from the "Edit design" panel of the duckOSM page (duckosm-rust, `crates/duckosm-wasm/www/app/`) on 2026-11-05.

The design panel lets a person change the style of a map in the page: a ready theme, the colours and widths of the road classes, the
street names, the one-way arrows, the layers, the ground and the colours of the base map. Each change shows on the map after 0.5 s.
The person can save a design as a theme of their own, download it as a file and load it again.

The panel is a part of the dashboard, the same way as [the level editor](levels.md#edit-the-levels-in-a-dashboard): it draws into the
host's standard panel (`#sb`), it hides the host's body while it is open, and `close()` shows the host's body again. It has no frame of
its own.

## Add the panel to a page

```js
import {designPanel} from "./dashboard/design/design_panel.js";

const design = await designPanel({
  panel: document.getElementById("sb"),     // the host's dashboard panel: .sb-card with .sb-top and .sb-body
  dashboard: rs,                            // the page's dashboard (rsDashboard)
  look: JSON.parse(lookText),               // the look that the map has now (a version 2 look)
  setLook: async (text) => live.setLook(Look.fromJson(text), "mlt"),   // the same tiles: a style, or undefined
  redraw: async (text) => { await drawAgain(text); return "A new map."; },   // new tiles: the host draws the map again
  storageKey: "mypage",                     // localStorage: mypage.design and mypage.themes
});
document.getElementById("open-design").onclick = () => design.open();
design.addEventListener("change", (e) => saveSomewhere(e.detail.text));
```

The panel has four tabs: **Theme**, **Roads**, **Text** and **Layers**. A host can add its own tabs (see [Host tabs](#host-tabs)).

## The options

| Option | Default | What it is |
|---|---|---|
| `panel` | (necessary) | The host's dashboard panel. The panel uses its `.sb-top` and `.sb-body`, as the level editor does. |
| `dashboard` | `window.rs` | The page's dashboard. The panel uses it to show a new style (`rs.restyle`) and to find the road layers (`rs.prefix`). |
| `map` | `window.map` | The page's MapLibre map. The panel paints the ground and the road layers on it. |
| `look` | (necessary) | The look of the map now, as an object. The defaults of every value come from it. |
| `setLook(text)` | none | Gives the new look to the host's `LiveMap.setLook` (or to the worker that holds it). It gives a style when the tiles stay right, else `undefined`. |
| `restyle` | `{}` | The options of `rs.restyle` (`also`, `imagePrefix`). The duckOSM page gives `{also: ["rs-low-"], imagePrefix: "rs-"}`. |
| `redraw(text, draw)` | (necessary) | The host draws the map again with the look `text` (`null`: the host's own look). With `draw: false`, the host only keeps the look for its next draw. It gives a note for the panel's bar, or throws an error. |
| `backLabel` | `"Steps"` | The text of the back button. `null`: no back button. |
| `storageKey` | `"roadstyle"` | The start of the localStorage keys: `<key>.design` (the design now) and `<key>.themes` (the person's themes). |
| `boundary` | none | A function that paints the host's area boundary: `boundary(b)` with `b` = `{show, color, width, dash, fill, fillOpacity, fillOnRoads}`. Without it, the Layers tab has no boundary section. |
| `link` | none | One link in the bar: `{label, onClick}`. The duckOSM page has "Export →". |
| `tabs` | `[]` | The host's own tabs (see [Host tabs](#host-tabs)). |

## A change of the style

After 0.5 s with no new change, the panel writes the design into a copy of `look` (`applyToLook`) and gives it to the host:

1. If the host gave `setLook`, the panel calls it. A style means that the tiles stay right. The panel then shows the style on the same
   tiles with `rs.restyle(style)`. The live colours of the roads (`rs.setData`, `rsColor`) stay.
2. If `setLook` gives `undefined` or throws an error (the panel writes it to the console), or the host gave no `setLook`, the panel calls
   `redraw(text, true)`.

`rs.restyle(style, {also})` is new in the dashboard. It is the duckOSM page's `restyleRoads`, moved into roadstyle. It gives each road
layer the new paint, layout and filter, adds the style's images again and reads the new style (`rs.setStyle`). `also` is a list of
more id prefixes for copies of the road layers (the duckOSM page has `["rs-low-"]`, its overview layers). It gives `false` when the
new style has other layers: then the host must draw again.

Some values are not in the look, so a change of them draws no new map. The panel paints them on the map at once, with roadstyle's own
calls:

| Value | How the panel paints it |
|---|---|
| The layers (`visible`) | `rsSetClasses`, `rsSetBridges`, `rsSetTunnels`, `rsSetArrows`, `rsSetOverlay`, `rsSetBuildings3D` and the names layer. The panel listens to the events of roadstyle's Layers box, so the two show one state. |
| The ground (`ground`) | The opacity of the layer `bg`. |
| The road opacity, the casing as an outline, the halo and arrow opacity | The paint of the road layers (`roadOpacity`, `roadOutline`). |
| The base map under the map ("Preview on") | `rsSetBasemap`. The checkerboard is the class `rs-checker` on the map's container. |
| The area boundary | The host's `boundary(b)`. |

The panel paints them again after each new style. For this, `rs.setStyle` sends the new event `rs:stylechange`.

## The methods and the events

`designPanel` gives an `EventTarget` with these methods:

| Method | What it does |
|---|---|
| `open(tab?)`, `close()`, `isOpen()` | Show the panel in the host's panel, or show the host's body again. |
| `get()`, `text()` | The design now, as an object or as the text of a design file. |
| `set(design)` | Use this design (it is completed from the look) and draw it. |
| `load(text, {draw})` | Use the design of a file text. It gives `false` for a bad text, and the design stays. `draw: false` only gives the look to the host (`redraw(text, false)`). |
| `setHost(key, value)` | A change of a host value from outside the panel (the duckOSM Export card changes the tile profile). |
| `refresh()` | Read the base map again (the "Preview on" control). |
| `flush()` | Draw the change that waits now, and wait for the end of the draw. For tests. |
| `base()`, `state()` | The design of the look, and the text of the bar. |
| `restored` | `true` when the panel started from the design that this browser kept (`<storageKey>.design`). The host then has the look of that design already (`redraw(text, false)`). |

| Event | `detail` | When |
|---|---|---|
| `change` | `{design, text}` | After each change. The host keeps the text (the duckOSM page keeps it with the saved area). |
| `back` | none | The person clicks the back button. The host calls `close()` and shows its steps. |

## Host tabs

A host tab holds a value that only the host knows, for example the tile profile of the duckOSM page. The panel keeps the value in the
design (`design[key]`), in the design file and in the person's themes. A ready theme and **Reset** do not change it.

```js
tabs: [{id: "tiles", name: "Tiles", key: "profile",
        make: () => defaultProfile(),              // the value at the start
        normalize: (v) => normalizeProfile(v),     // a value of a file, completed and in range
        draw: (el, value, put, controls) => { ... },   // the host writes the tab's HTML into el; put(newValue) tells the panel of a change
        keep: "Keep the tile profile in the theme"}]   // the check box of "Your themes"; without it, a theme never keeps the value
```

`controls` has the panel's own HTML parts, so a host tab looks like the other tabs: `sec(title, body, note)` (a section), `color`, `range`,
`number` and `check` (a label and a control), and `esc` (HTML text). The panel does not read the events in a host tab: the host listens
to its own controls.

## The design file

A design file is JSON with `"format": "roadstyle-design"` and `"version": 1`. It holds every value, not only the changes, so it does
not depend on the look that it was made from. The panel reads the old format `"duckosm-design"` too. The themes file has the format
`"roadstyle-themes"`, and the panel reads `"duckosm-themes"` too.

## Where the code is

| File | What it holds |
|---|---|
| `dashboard/design/design.js` | The design model: `defaultsOf(look)`, `normalize`, `applyToLook`, `makeTheme`, the road opacity expressions, the design file. No page code. |
| `dashboard/design/user_themes.js` | The person's themes: save, rename, delete, the themes file. No page code. |
| `dashboard/design/design_panel.js` | The panel: the content of its tabs and its bar. |
| `dashboard/frame.js` | The editor frame (`editorFrame`, also `rs.frame`): the title line, the head row with the tabs, the body that scrolls and the bar. The panel draws into it ([An editor in the panel](dashboard-parts.md#an-editor-in-the-panel)). |
| `dashboard/design/themes.json` | The ready themes. A colour is a style value, so it is in a data file, not in the code. It is in the dashboard folder, because a host copies that folder (duckosm-rust). |
| `dashboard/dashboard.css` | The panel's CSS, with the theme tokens, in the light and the dark theme. |

The panel is a module that a page imports, as the level editor is. It is not in every page (`files.txt`): the panel and its themes
are about 60 KB. A page that `render_edges` writes does not have it.

The ready themes that copy a roadstyle palette or base-map theme (Google like, Grey, roadstyle, OSM Carto, Amber roads, Carto roads,
High saturation, Mono roads) keep their colours in `themes.json`. `tests/test_design_themes.py` compares them with the files in `data/palettes/` and
`data/basemap/`, so a change of a palette shows as a failed test.

The tests: `tests/test_design_panel_browser.py` (the checks of the design model in `tests/design_units.js`, the panel on a dashboard page,
and a phone) and `tests/test_dashboard_themes_browser.py` (the panel in the light and the dark theme).

## What stays in the host

| Host part | Why |
|---|---|
| The tile profile and the Tiles tab | Only the duckOSM page makes tile files (the Export card). It is a host tab. |
| The area boundary layers | The duckOSM page draws its own area layers. The panel calls `boundary(b)`. |
| Where the design is kept with an area | The host listens to `change`. |
| How the map is drawn again | `setLook` and `redraw`. |

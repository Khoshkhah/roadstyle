# Edit the design of a map

The design panel lets a person change the style of a map in the page: a ready theme, the colours and widths of the road classes, the street names, the one-way arrows, the layers, the ground and the colours of the base map. Each change shows on the map after 0.5 s. The person can save a design as a theme of their own, download it as a file and load it again.

It is a JavaScript module that the host page imports. It draws into the host's standard panel (`#sb`), as [the level editor](levels.md#edit-the-levels-in-a-dashboard) does. It has four tabs: **Theme**, **Roads**, **Text** and **Layers**. Each item below has the same form: a box with **Use it for** and **From Python**, the code in tabs, and **Details** that open on a click.

| Group | Item | From Python | Use it for |
|---|---|---|---|
| Use it | [Add the panel to a page](#add-the-panel-to-a-page) | no | the panel in your dashboard |
| Use it | [The options](#the-options) | no | what `designPanel` takes |
| Use it | [The methods and the events](#the-methods-and-the-events) | no | to drive the panel and to keep the design |
| How it works | [A change of the style](#a-change-of-the-style) | no | how a change reaches the map |
| How it works | [The design file](#the-design-file) | no | to keep and to load a design |
| Extend it | [Host tabs](#host-tabs) | no | a value that only the host knows |
| Extend it | [What stays in the host](#what-stays-in-the-host) | no | the parts that you write |
| Extend it | [Where the code is](#where-the-code-is) | no | the files of the module |

## Use it { .rs-group }

### Add the panel to a page { .rs-part }

**Use it for:** the design panel in a dashboard page. It hides the host's body while it is open, and `close()` shows the body again.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

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

### The options { .rs-part }

**Use it for:** what `designPanel({...})` takes. `panel`, `look` and `redraw` are necessary.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

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

### The methods and the events { .rs-part }

**Use it for:** to open the panel, to read and set the design, and to keep it. `designPanel` gives an `EventTarget`.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

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

## How it works { .rs-group }

### A change of the style { .rs-part }

**Use it for:** to know how a change reaches the map. After 0.5 s with no new change, the panel writes the design into a copy of `look` (`applyToLook`) and gives it to the host.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    1. If the host gave `setLook`, the panel calls it. A style means that the tiles stay right. The panel then shows the style on the same tiles with `rs.restyle(style)`. The live colours of the roads (`rs.setData`, `rsColor`) stay.
    2. If `setLook` gives `undefined` or throws an error (the panel writes it to the console), or the host gave no `setLook`, the panel calls `redraw(text, true)`.

    `rs.restyle(style, {also})` is the duckOSM page's `restyleRoads`, moved into roadstyle. It gives each road layer the new paint, layout and filter, adds the style's images again and reads the new style (`rs.setStyle`). `also` is a list of more id prefixes for copies of the road layers (the duckOSM page has `["rs-low-"]`, its overview layers). It gives `false` when the new style has other layers: then the host must draw again.

    Some values are not in the look, so a change of them draws no new map. The panel paints them on the map at once, with roadstyle's own calls, and again after each new style. For this, `rs.setStyle` sends the event `rs:stylechange`.

    | Value | How the panel paints it |
    |---|---|
    | The layers (`visible`) | `rsSetClasses`, `rsSetBridges`, `rsSetTunnels`, `rsSetArrows`, `rsSetOverlay`, `rsSetBuildings3D` and the names layer. The panel listens to the events of roadstyle's Layers box, so the two show one state. |
    | The ground (`ground`) | The opacity of the layer `bg`. |
    | The road opacity, the casing as an outline, the halo and arrow opacity | The paint of the road layers (`roadOpacity`, `roadOutline`). |
    | The base map under the map ("Preview on") | `rsSetBasemap`. The checkerboard is the class `rs-checker` on the map's container. |
    | The area boundary | The host's `boundary(b)`. |

### The design file { .rs-part }

**Use it for:** to keep a design and to load it again. The person downloads it, and `load(text)` reads it.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - A design file is JSON with `"format": "roadstyle-design"` and `"version": 1`. It holds every value, not only the changes, so it does not depend on the look that it was made from.
    - The panel reads the old format `"duckosm-design"` too. The themes file has the format `"roadstyle-themes"`, and the panel reads `"duckosm-themes"` too.
    - The ready themes that copy a roadstyle palette or base-map theme (Google like, Grey, roadstyle, OSM Carto, Amber roads, Carto roads, High saturation, Mono roads) keep their colours in `themes.json`.

## Extend it { .rs-group }

### Host tabs { .rs-part }

**Use it for:** a value that only the host knows, for example the tile profile of the duckOSM page. The panel keeps it in the design (`design[key]`), in the design file and in the person's themes.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```js
    tabs: [{id: "tiles", name: "Tiles", key: "profile",
            make: () => defaultProfile(),              // the value at the start
            normalize: (v) => normalizeProfile(v),     // a value of a file, completed and in range
            draw: (el, value, put, controls) => { ... },   // the host writes the tab's HTML into el; put(newValue) tells the panel of a change
            keep: "Keep the tile profile in the theme"}]   // the check box of "Your themes"; without it, a theme never keeps the value
    ```

??? info "Details"

    - A ready theme and **Reset** do not change the value.
    - `controls` has the panel's own HTML parts, so a host tab looks like the other tabs: `sec(title, body, note)` (a section), `color`, `range`, `number` and `check` (a label and a control), and `esc` (HTML text).
    - The panel does not read the events in a host tab: the host listens to its own controls.

### What stays in the host { .rs-part }

**Use it for:** to know which parts you write. The panel does not do them.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    | Host part | Why |
    |---|---|
    | The tile profile and the Tiles tab | Only the duckOSM page makes tile files (the Export card). It is a host tab. |
    | The area boundary layers | The duckOSM page draws its own area layers. The panel calls `boundary(b)`. |
    | Where the design is kept with an area | The host listens to `change`. |
    | How the map is drawn again | `setLook` and `redraw`. |

### Where the code is { .rs-part }

**Use it for:** the files of the module. The panel is not in every page (`files.txt`): the panel and its themes are about 60 KB. A page that `render_edges` writes does not have it.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    | File | What it holds |
    |---|---|
    | `dashboard/design/design.js` | The design model: `defaultsOf(look)`, `normalize`, `applyToLook`, `makeTheme`, the road opacity expressions, the design file. No page code. |
    | `dashboard/design/user_themes.js` | The person's themes: save, rename, delete, the themes file. No page code. |
    | `dashboard/design/design_panel.js` | The panel: the content of its tabs and its bar. |
    | `dashboard/frame.js` | The editor frame (`editorFrame`, also `rs.frame`): the title line, the head row with the tabs, the body that scrolls and the bar. The panel draws into it ([An editor in the panel](dashboard-parts.md#an-editor-in-the-panel)). |
    | `dashboard/design/themes.json` | The ready themes. A colour is a style value, so it is in a data file, not in the code. It is in the dashboard folder, because a host copies that folder (duckosm-rust). |
    | `dashboard/dashboard.css` | The panel's CSS, with the theme tokens, in the light and the dark theme. |

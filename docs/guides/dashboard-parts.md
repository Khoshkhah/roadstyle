# Dashboard parts

A dashboard page looks the same on every project when every page uses the same parts. This page shows each shared part live, tells when to use it, and gives its code. **Use a part when one exists. Do not write CSS or JavaScript for the same thing in a page**: a copy of a part drifts, and it forgets the dark theme.

Each panel box on this page is the real part. It runs the dashboard's own `dashboard.css` and JavaScript modules, which the docs build copies from `rust/roadstyle-assets/files/static/dashboard/` (`docs/copy_parts.py`). Click it, type in it, fold it: it works as it does on a dashboard page. The parts follow the light and the dark theme of this site. On a phone they have the phone look. [All the parts in one panel](../parts/gallery.html) has a switch for the theme and a switch for a phone width of 390 px.

The panel starts empty. Three parts are whole sections that roadstyle writes: the `query` part, the `road_card` part and the `chart` part. They are in [Add to the panel](dashboard-panel.md) and [Charts](charts.md). The parts below are for the page's own HTML in a section.

Two parts use the whole panel: the level editor ([Edit the levels in a dashboard](levels.md#edit-the-levels-in-a-dashboard)) and the design panel ([Edit the design of a map](design-panel.md)). An editor of your own uses the same frame: [An editor in the panel](#an-editor-in-the-panel).

| Part | What it is | Use it for |
|---|---|---|
| [`class="rs-tabs"` + `rs.tabs.use(nav, onChange)`](#tabs) | tabs: the selected tab is filled | the sections (panes) of a page |
| [`class="rs-seg"` + `rs.tabs.use(el, onChange)`](#a-two-way-switch) | a two-way switch: the selected segment is a light chip | a mode or a setting |
| [`<select>` in the panel](#a-select-box) | the select box: a button and a list in the look of the boxes | a choice of one of many |
| [`rs.days.use(el, {days, value, onChange})`](#a-day-picker) | the day picker: a "Day" label, a field that opens a calendar of the days with data, the day before and after, "Latest" | the day of a page with one day of data at a time |
| [`rs.sections.add({..., label, fold, background})`](#cards) | a card: with or without a background, that folds or not; one button in the title row folds all the cards that fold, and the browser keeps the state | the page's cards |
| [`rs.sections.add({..., open})`](#a-card-that-opens-something) | a card that is one button | a card that opens an editor or a dialog |
| [`rs.frame({panel, title, back, tabs})`](#an-editor-in-the-panel) | the frame of an editor that uses the whole panel: a title line with "← back", a tab row, one body that scrolls and a bar at the bottom edge | an editor, as Edit design |
| [`class="rs-sec-box"`, `class="rs-card-title"`](#a-card-in-the-pages-own-html) | a card in the page's own HTML: the same card as a section | one block of a page, a card in a tab |
| [`rs.help.set({title, intro, terms, note})`](#a-help-window) | the "?" button in the panel title and its window | "How to read this page" |
| [`rs.help.button(el, {title, ...})`, `rs.help.open({title, ...})`](#a-help-window) | one more "?" button with its own words, and the same window opened from a link | a card, a label, a section |
| [`rs.hover.show(html, event)`, `rs.hover.on(node, html)`](#a-hover-box) | the hover box, in the look of the popup | words over a chart or a map layer |
| [`title="..."` on a button](#a-button-tip) | the tip of an icon button | an icon with no text |
| [`<button>`, `class="sb-primary"`](#buttons) | the panel's buttons, and the filled button | an action |
| [`<input>`, `<textarea>`, check box, radio](#a-text-box-a-check-box-and-a-radio-button) | the panel's own fields | a form |
| [`class="rs-chip"`, `class="rs-dot"`](#chips-and-a-dot) | a small label, a color mark | labels |
| [`rs.kpi(title, value, sub, color)` in `class="rs-kpis"`, `class="rs-cap"`](#number-tiles) | a number tile (a grid of three), a small capital caption | the numbers of a page |
| [`class="rs-callout"`](#a-callout) | an answer box with a colored edge | the answer of a page |
| [`class="rs-name"`, `class="rs-kv"`](#rows-of-fields) | a name and rows of a field and its value | the fields of one item |
| [`class="rs-qrow"`](#list-rows) | a row of a list: a name and a muted detail | a list of results |
| [`rs.svg(parent, tag, attrs)` + `--rs-chart-*`](#charts) | one SVG element that reads `var(--x)`, and the chart colors | a chart of your own |
| [`rs.chart(el, {kind, x, y, columns, rows})`](#a-chart) | a bar, line, histogram, scatter or pie chart of rows | a chart of a result |
| [`class="rs-scroll"` + `class="rs-table"`](#a-list-or-a-table-that-scrolls) | a scroll area and a table with a fixed header | a list of streets |
| [`rs.dock.add({id, label, el})`, `rs.dock.table({columns, rows})`](#the-bottom-dock) | the bottom dock under the map and its table | a wide table of roads |
| [`--rs-card-gap`, `--rs-card-pad`, `--rs-panel-bottom`](dashboard-panel.md#cards-the-panel-standard) | the space between cards (12 px), inside a card (14 px), under the last card (28 px) | a page that needs other numbers, set on `:root` |
| `rs.ready(fn)` | runs `fn` when the page is ready | the start of a page script |
| [`rs.classify(values, method, k, pivot=..., palette=...)`](#colour-classes) | the cuts and the colors for discrete road classes | `color_options` |

## The accent color and the theme tokens

The page has a light and a dark theme. Every part of the dashboard and your HTML must follow them. Plain text, links, tables, `hr`, inputs and buttons already do. For your own colors, use the theme's tokens and not fixed colors. The tokens are set for the whole page, so they work in the panel, in a box of the toolbox, in a window and in the popup:

| Token | Use |
|---|---|
| `var(--ink)`, `var(--mut)` | text, muted text |
| `var(--bg)`, `var(--card)` | the background of the panel, a box in it |
| `var(--line)` | thin lines |
| `var(--accent)` | links and buttons |
| `var(--accent-fill)` | a filled control (a selected tab, a primary button) |
| `var(--rs-hover-bg)` | the tint behind a control under the pointer (`--accent` at 12 %) |

The accent is one color for the whole dashboard, the Sonocount teal. A page does not set its own. `--accent` is `#0e7c8e` for text in the light theme (a little darker than the logo's `#0E7F91`, for 4.6:1 on the cards) and a lighter teal of the same hue in the dark theme (8.5:1 on the panel). `--accent-fill` is the logo teal `#0E7F91`, which takes white text (4.71:1) in both themes. The tokens are defined once in `dashboard.css`. A selected tab, a primary button, a link, and the mode and follow buttons of the Street View and Google 3D windows use them, in the panel and in the floating windows.

`.sb-note` is small, muted text and `.rs-sec-box` is a box. Both have a contrast of 4.5 or more in the two themes. The rows of the legend follow the theme too.

The theme changes with `rsSetTheme("dark")` or `rsSetTheme("light")`. It sets `data-rs-theme` on `<html>` and `data-theme` on `#sb`, and it sends the event `rs:themechange` (`detail.theme`).

`tests/test_dashboard_themes_browser.py` opens each part of a dashboard in the light and the dark theme. It fails on a text with a contrast under 4.5 and on a light surface or line in the dark theme. A new part must pass it.

## Tabs

<iframe class="rs-live" src="../../parts/gallery.html?part=tabs" title="Tabs, live" loading="lazy"></iframe>

Use tabs for the sections of a page: a click shows another pane, and the content below changes. To draw the same content in another way, use [a two-way switch](#a-two-way-switch).

```html
<nav class="rs-tabs"><button class="rs-tab on" data-tab="a">Overview</button><button class="rs-tab" data-tab="b">Streets</button></nav>
<div data-pane="a">...</div><div data-pane="b" hidden>...</div>
```

```js
const tabs = rs.tabs.use(document.querySelector(".rs-tabs"), id => console.log(id));
tabs.select("b");      // as a click: calls onChange
tabs.select("b", true);   // quiet: does not call onChange
tabs.current();        // "b"
```

- A click or an arrow key (left, right) selects a tab. The chosen button has the class `on` and `aria-selected="true"`. The `nav` gets `role="tablist"` and each button `role="tab"`.
- The panes are the siblings of the `nav` with `data-pane`. The pane with the id of the selected tab shows. The others get `hidden`.
- The first button with `on` is selected at the start, else the first button. The start does not call `onChange`.
- The selected tab uses `--accent-fill` with white text. The other tabs have muted text on a flat row with a line under it.
- There is no DOM event. `onChange(id)` is the only callback.

## A two-way switch

<iframe class="rs-live" src="../../parts/gallery.html?part=switch" title="A two-way switch, live" loading="lazy"></iframe>

Use a switch for a mode or a setting with two or a few values: the same content is drawn in a different way. To show another pane, use [tabs](#tabs).

```html
<div class="rs-seg" id="mode"><button class="on" data-v="all">Every day</button><button data-v="first">First day</button></div>
```

```js
const mode = rs.tabs.use(document.getElementById("mode"), v => redraw(v));
```

`rs.tabs.use` wires the switch the same way as tabs, with `data-v` in place of `data-tab`, `role="radiogroup"`, `role="radio"` and `aria-checked`. A switch has no panes. It gives `{select(v, quiet), current()}` too.

The two parts look different, because they do different jobs:

| | Tabs (`rs-tabs`) | Two-way switch (`rs-seg`) |
|---|---|---|
| Look | A flat row with a line under it. The text is muted | A grey track with a rounded button for each value |
| Selected | Filled with `--accent-fill`, white text | The card color, `--accent` text, a soft shadow |
| Use it for | The sections (panes) of a page: the content below changes | A mode or a setting with two or a few values: the same content is drawn in a different way |

Tabs change the pane. A switch changes a setting. Do not use one for the job of the other.

## A select box

<iframe class="rs-live" src="../../parts/gallery.html?part=select" title="A select box, live" loading="lazy"></iframe>

Use a `<select>` for a choice of one value of many, for example "Colour by". For two or three values that the person changes often, a [two-way switch](#a-two-way-switch) shows all of them at once.

```html
<label>Colour by</label>
<select id="by"><option value="class">Road class</option><option value="speed">Speed limit</option></select>
```

```js
document.getElementById("by").addEventListener("change", e => recolour(e.target.value));
```

The browser draws its own list, with the system's corners and colors. roadstyle keeps the `<select>` in the page, hidden, and puts a button and a list in its place (`selectbox.js`). The list is in the look of the boxes, outside the panel, so the scroll of the panel does not cut it.

- Your code reads and sets the select as usual: `value`, `selectedIndex`, `disabled`, the options and the `change` event. The button follows `value` and `disabled` when your code sets them.
- The keys: Down or Up opens the list. In the list, Down and Up move, Enter or Space picks, Escape and Tab close.
- One list is open at a time. It opens upward when there is no room below. It closes when its button goes out of view.
- On a card (a section with a label) the button has a thin line around it, as a text box has.
- The select box comes to each `<select>` in `#sb`, `.rs-side` and `.rs-host` when the page starts, to each select of a section that `rs.sections.add` adds, and to each select in an [editor frame](#an-editor-in-the-panel). A select that your code puts in the panel in another way, after the start, keeps the browser's list.

## A day picker

<iframe class="rs-live" src="../../parts/gallery.html?part=days" title="A day picker, live" loading="lazy"></iframe>

Use the day picker on a page that shows one day of data at a time. Give an empty element and the days that have data:

```html
<div id="day"></div>
```

```js
const day = rs.days.use(document.getElementById("day"), {
  days: ["2026-10-01", "2026-10-04", "2026-10-05"],   // the days with data, "YYYY-MM-DD"
  value: "2026-10-05",                                // the day at the start (default: the latest)
  label: "Day",                                       // the label above the field (default: "Day")
  onChange: d => fetch(`daily_${d}.json`).then(r => r.json()).then(draw),
});
day.value();              // "2026-10-05"
day.set("2026-10-04");    // as a click: calls onChange
day.set("2026-10-04", true);   // quiet: does not call onChange
```

The field shows the day ("Mon 5 Oct 2026") with a calendar icon and a "v", and a click opens a calendar. In the calendar, only the days in `days` are buttons. "‹" and "›" go to the day before and the day after in `days`, so they skip a day with no data. "Latest" goes to the last day. Escape or a click outside closes the calendar.

If `onChange` gives a promise, the field pulses and the buttons wait until the promise ends. If the promise fails, the picker goes back to the old day, and a line under the row says "Could not load Mon 5 Oct 2026." A `value` that is not in `days` is an error.

The field has a border and the page's background, and its icons are `--accent`. On hover and while the calendar is open, it has an `--accent` border, a light accent fill and an accent ring. The calendar is a box like the help window.

## Cards

<iframe class="rs-live" src="../../parts/gallery.html?part=cards" title="Cards, live" loading="lazy"></iframe>

A section with a `label` is a card. Use a card for each block of the panel. Two options choose its kind: `fold: true` makes it fold, and `background: false` takes its color away.

```js
rs.sections.add({id: "card", label: "A card", html: "<p>Text</p>"});
rs.sections.add({id: "notes", label: "A card that folds", fold: true, note: "Click the title row", html: "<p>Text</p>"});
rs.sections.add({id: "tiles", label: "No background", background: false, html: '<div class="rs-kpis" id="k"></div>'});
rs.help.button(rs.sections.get("card"), {title: "About this card"});      // a "?" at the right end of the title row
rs.sections.fold("notes", false);                                          // open it from the code
```

- In a card that folds, a click on the title row folds or opens the card. The browser keeps the state of each card. The **Collapse all** button (`#rs-fold-all`) comes in the panel's title row with the first card that folds.
- `note` is one line of state under the title. `rs.sections.note(id, text)` changes it.
- The event `rs:sectionchange` comes with `detail.id` and `detail.state`: `add`, `remove`, `hide`, `show`, `fold` or `unfold`.
- A section without a `label` is not a card. It is a block of the page's own HTML with no box. The tabs above are in such a block.

The look of each kind, the spacing and the rules are in [Cards: the panel standard](dashboard-panel.md#cards-the-panel-standard). The option `dashboard={"panel": {"sections": [...]}}` adds the same cards from Python.

## A card that opens something

<iframe class="rs-live" src="../../parts/gallery.html?part=open" title="A card that opens something, live" loading="lazy"></iframe>

When the only work of a card is to open your own panel, editor or dialog, give it `open` (a function) in place of `fold` and a body. The card is then one button. Its row ends with a pencil in place of the chevron. The **Edit roads** card above opens the [editor frame](#an-editor-in-the-panel), and **Ask** counts the clicks in its note.

```js
rs.sections.add({id: "edit", label: "Edit roads", note: "Opens the editor frame", open: () => frame.open("tags")});
rs.sections.add({id: "ask", label: "Ask", note: "A question about the data", icon: "ask", background: true, open: () => ask.open()});
```

`icon` is `"edit"` (the default), `"ask"` or your own `<svg>`. `background: true` gives the light accent tint, so that one card stands out. To keep a card from opening, disable its title button: `rs.sections.get(id).querySelector(".rs-sec-title").disabled = true`. A card with `open` and `fold` is an error. The full text is in [A card that opens something](dashboard-panel.md#a-card-that-opens-something).

## An editor in the panel

<iframe class="rs-live" src="../../parts/gallery.html?part=frame" title="The editor frame, live" loading="lazy"></iframe>

An editor that uses the whole panel (Edit design, a form with tabs) gets its frame from roadstyle. Do not make the frame in the page: a frame of your own gets the browser's scrollbar, a bar that scrolls with the form, or tabs in another look. Click **Open the editor frame** above, change the tab, and click "← Parts" to close it.

```javascript
const fr = rs.frame({panel: document.getElementById("sb"), title: "Edit roads", back: "Steps", id: "ed",
                     tabs: [["tags", "Tags"], ["geometry", "Geometry"], ["notes", "Notes"]]});
fr.body.innerHTML = "<p>The form of the tab Tags.</p>";
fr.bar.innerHTML = "<b>2 changes</b> <button type='button'>Apply</button>";
fr.addEventListener("tab", (e) => { fr.body.innerHTML = formOf(e.detail.tab); });
fr.addEventListener("back", () => fr.close());
fr.open("tags");
```

A panel with no tabs and a row of its own tools under the title (the Ask panel: the name of the provider, **Key** and **New**):

```javascript
const tools = document.createElement("div");
tools.innerHTML = "<b>Provider</b> <button type='button'>Key</button> <button type='button'>New</button>";
const ask = rs.frame({panel: document.getElementById("sb"), title: "Ask", back: null, head: tools, id: "ask"});
ask.open();
```

`panel` is the host's standard panel: `#sb` with `.sb-card`, and in it `.sb-top` (the title first, then the hide button) and `.sb-body`. A module page that does not have `window.rs` imports the same function: `import {editorFrame} from "./dashboard/frame.js"`.

`open(tab)` hides the host's title, its body and the **Collapse all** button (`#rs-fold-all`), and shows the frame:

- **The title line** (`top`) goes into `.sb-top`, before the host's hide button: "← `back`" and the `title`. With `back: null`, the line has no back button. You can add more to the line, for example the name of the item that you edit.
- **The head row** (`head`) is under the title line, with a line under it. It does not scroll. `tabs` puts roadstyle's tab row (`rs-tabs`) in it. A click on a tab selects it and sends the event `tab` (`detail.tab`). The frame does not change the body: draw the tab's content in the body when the event comes. `tab(name)` selects a tab with no event, and `tab()` gives the selected tab. A panel with no tabs can put its own row in it: give the option `head` (an element), or add to `frame.head` before `open()`. An empty head row does not show.
- **The body** (`body`) is the one area that scrolls. It has the class `rs-pbody`, so it has the scroll protocol of the panel: a thin scrollbar that shows only over the body or while it scrolls, a line under the tab row while the body is scrolled, a fade at the bottom edge while there is more below, and a fade at the top edge while there is more above.
- **The bar** (`bar`) is under the body and outside it, at the bottom edge of the panel. Nothing scrolls under it, so it has the color of the panel. Put the state and the buttons of the editor in it. An empty bar does not show.

`close()` removes the frame and shows the host's title, body and **Collapse all** again, with the body at its old scroll position. `isOpen()` tells whether the frame is open. The back button sends the event `back`: the host then calls `close()`. `id` is the start of the ids of the frame's elements (`<id>-back`, `<id>-head`, `<id>-tabs`, `<id>-tab-<tab>`, `<id>-body`; default `rs-frame`). The classes are `rs-frame`, `rs-frame-title`, `rs-frame-back`, `rs-frame-head`, `rs-frame-body` and `rs-frame-bar`. Use them to find the elements, not to change the frame.

Each `<select>` in the frame (in the head row, the body or the bar, also one that you add after `open()`) gets roadstyle's [select box](#a-select-box).

On a phone the panel is a bottom sheet, and the frame fills it: `open()` puts the sheet at its full height, and `close()` gives back the height that it had. The bar is at the bottom of the sheet, and the back button and the tabs are 44 px high. The tab row is one row that scrolls sideways, and the selected tab comes into view. The colors are the theme's tokens, so the frame has the look of the panel in the light and the dark theme. `tests/test_editor_frame_browser.py` checks the frame in both themes and at 390 px, with tabs and with a head row of its own.

## A card in the page's own HTML

<iframe class="rs-live" src="../../parts/gallery.html?part=page-card" title="A card in the page's own HTML, live" loading="lazy"></iframe>

Use `rs-sec-box` for a card inside a section without a label: a card in a tab pane, or several cards in one block. In a section with a label, do not add a box: the section is a card already.

```html
<div class="rs-sec-box"><div class="rs-card-title">By hour of the day</div><p>Text</p></div>
<div class="rs-sec-box"><h3>By hour of the day</h3><p>How often the range held, hour by hour.</p><svg>...</svg></div>
```

`rs-card-title` is the same title row as the title of a section's card. An `h3` is a smaller title, and the paragraph right after it is its short, muted description. An `svg` in the box fills the width. `rs.help.button(box.querySelector(".rs-card-title"), {...})` puts a "?" at the right end of the title.

## A help window

<iframe class="rs-live" src="../../parts/gallery.html?part=help" title="A help window, live" loading="lazy"></iframe>

Use the help window for "How to read this page": the words that explain the page, out of the way until the person asks.

```js
rs.help.set({title: "How to read this page", intro: "What the page shows.",
             terms: [["Inside the range", "How often the promise held."]], note: "A short note."});
```

A "?" button appears in the title of the panel (`anchor: element` puts it in another element, for example in the title of a panel that a module draws). A page with more to explain puts a "?" button with its own words beside the title of a card or a label, and all the buttons open the one window:

```js
rs.help.button(document.querySelector("#card-3 h2"), {title: "About step 3", intro: "What it does.", html: "<p>Words of the page's own.</p>", button: "About step 3"});
rs.help.button(rs.sections.get("tabs"), {title: "About the tabs"});   // a section: the "?" goes in its title
rs.help.open({title: "Opened by a link", intro: "No button."});     // the same window, from a link or a key
```

To put a "?" in the title of a card, give the section's box (`rs.sections.get(id)`). The button goes at the right end of the title row: before the chevron of a card that folds (the chevron is last), and at the end of the `.rs-card-title` of a card in the page's own HTML. A click on the "?" opens the window and does not fold the card.

The words are `{title, intro, terms, note, html}`. `html` is HTML of the page's own, shown after the intro. `button` is the name of the button for a screen reader and its tooltip. `rs.help.button` gives the button back.

The window opens inside the screen. On a phone it is a sheet at the bottom of the screen. Escape, the ✕ and a click outside the box close it. `rs.help.get()` gives the words that are set now, and `rs.help.clear()` takes the window and the button away. The window is roadstyle's own: it has the card token, the blur and the border of the other windows, so it is the same in both themes and on every page. The words can have HTML (`<b>`). Call `rs.help.set` again to replace them. `rs.help.open()` and `rs.help.close()` open and close the window. The event `rs:helpchange` comes with `detail.open` (and `detail.title` when it opens).

## A hover box

<iframe class="rs-live" src="../../parts/gallery.html?part=hover" title="A hover box, live" loading="lazy"></iframe>

Use the hover box for the words of a point under the pointer: a bar of your own chart, a feature of your own map layer. A [chart](#a-chart) of `rs.chart` has it already. For the explanation of a button, use [a button tip](#a-button-tip).

```js
rs.hover.on(chartNode, ev => "<b>Saturday</b><br>24 hours");     // the text, or a function of the event; null hides
rs.hover.show("<b>A street</b>", mapEvent.originalEvent);         // by hand, over a map layer
rs.hover.hide();
```

The box has the look of the popup and follows the pointer. It flips to the other side at the edge of the page and never takes the pointer. The words can have HTML. `rs.hover.on` listens to `mousemove` and `mouseleave` of the node.

## A button tip

<iframe class="rs-live" src="../../parts/gallery.html?part=tip" title="A button tip, live" loading="lazy"></iframe>

Give an icon button a `title`. Point at the magnifier above: after 350 ms a tip in the look of the dashboard comes, not the browser's tooltip.

```html
<button type="button" title="Zoom to the area" aria-label="Zoom to the area"><svg>...</svg></button>
<button type="button" title="Build the networks of the area">Build →</button>
```

- The tip comes for a `title` in the panel (`#sb`), the toolbox, its boxes, the Street View and Google 3D windows and the show buttons of the panels. A `title` in another place keeps the browser's tooltip.
- A button or a link with a text of its own (2 characters or more) shows no tip, because its text says what it does. Its `title` becomes its `aria-description`. A button of the toolbox always has a tip.
- The tip opens on the side of the button that faces the center of the map, and never over the button. Keyboard focus shows it too. A touch shows no tip.
- roadstyle moves the `title` to `data-rs-tip`. An icon button with no `aria-label` gets the `title` as its `aria-label`.

## Buttons

<iframe class="rs-live" src="../../parts/gallery.html?part=buttons" title="Buttons, live" loading="lazy"></iframe>

A plain `<button>` and `<button class="sb-primary">` in the panel have their look already: write no class for a plain button. Use `sb-primary` for the one main action of a card (**Run**, **Apply**). Use a plain button for the other actions. A `disabled` button is grey and does not react.

```html
<div class="sb-actions"><button type="button" class="sb-primary">Run</button><button type="button">Reset</button></div>
```

`sb-actions` is a row of buttons with a gap of 6 px that wraps. The look of a plain `<button>`, a `<select>` and a `<label>` in the panel is in `dashboard.css`, so a host page with its own panel (`#sb`) and no dashboard template gets it too. A disabled button, also a primary one, is dimmed.

**Hover.** Every control of the dashboard reacts under the pointer and on keyboard focus, in one of three looks by its kind:

| Kind | Hover | Examples |
|---|---|---|
| Not filled | the tint `--rs-hover-bg` behind it, and its text or icon in `--accent`; a border, if it has one, is `--accent` too | the toolbox's buttons, the rows of its boxes, a plain button, a chip, a tab, a summary, ✕ |
| Filled | brighter (`filter: brightness(1.1)`) | a primary button, the open tab, a selected day |
| A link | underlined (a link in the panel, the help window or a window has no underline until then) | "How to set up the key ↗" |

A disabled control does not react. Keyboard focus has the same look and a 2 px `--accent` ring. A card's title row has the card's own hover (see [Cards](dashboard-panel.md)). Your own controls get the look when they are a `<button>`, a `<summary>` or a link in the panel. For a control of your own in another place, use `background: var(--rs-hover-bg); color: var(--accent)`. `tests/test_dashboard_hover_browser.py` puts the pointer on every control of the panel, the toolbox and its boxes, the help window and the day picker, in both themes, and fails on a control with no hover.

## A text box, a check box and a radio button

<iframe class="rs-live" src="../../parts/gallery.html?part=inputs" title="Text boxes, check boxes and radio buttons, live" loading="lazy"></iframe>

A text `<input>` (no `type`, `text`, `search`, `number` or `url`) and a `<textarea>` in the panel have the card color, round corners and an accent ring on focus. A check box and a radio button are 16 px. They and a range slider have the accent color. Write no class for them.

```html
<label>Street</label><input placeholder="Götgatan">
<label>Note</label><textarea rows="3"></textarea>
<input type="checkbox" checked> Bridges
<input type="radio" name="count" checked> Every day <input type="radio" name="count"> First day
```

Use a check box for an on and off value that the person sets once, and a [two-way switch](#a-two-way-switch) for a mode that changes the view at once.

## Option rows

<iframe class="rs-live" src="../../parts/gallery.html?part=opt" title="Option rows, live" loading="lazy"></iframe>

An option row is a setting with a check box or a radio button and a short note, or one choice of a list. A button at the end of a row is a plain button.

```html
<div class="rs-opts">
  <label class="rs-opt"><input type="checkbox" checked><span><b>Layers</b><small>Water, land use, buildings and more.</small></span></label>
  <label class="rs-opt"><input type="radio" name="x"><span><b>Monaco</b><small>2 km²</small></span><button type="button">Get</button></label>
</div>
<div class="rs-opts rs-opts-row">
  <label class="rs-opt"><input type="checkbox" checked><span>Driving</span></label><label class="rs-opt"><input type="checkbox"><span>Walking</span></label>
</div>
```

`rs-opts` is a list, one row under the other. `rs-opts rs-opts-row` puts the rows side by side, as chips. A row has the light edge of a card. Under the pointer it has the hover tint and the accent edge. A checked row has the accent tint and the accent edge, and it is darker under the pointer.

Use option rows when each value has a note or when more than one value can be on. Use a [two-way switch](#a-two-way-switch) for one value of a setting.

## Chips and a dot

<iframe class="rs-live" src="../../parts/gallery.html?part=chips" title="Chips and a dot, live" loading="lazy"></iframe>

```html
<span class="rs-chip">road type</span> <span class="rs-chip accent">primary</span>
<span class="rs-dot" style="background:#15803d"></span>inside the range
```

`rs-chip` is a small label, and `rs-chip accent` tints it with `--accent`. A chip is not a button: use it for a value, not for an action. `rs-dot` is a color mark of 8 px before a word. Without a color it is `--mut`.

## Number tiles

<iframe class="rs-live" src="../../parts/gallery.html?part=kpi" title="Number tiles, live" loading="lazy"></iframe>

Use number tiles for the few numbers that a page is about. For many numbers, use [a table](#a-list-or-a-table-that-scrolls).

```html
<div class="rs-cap">All counted hours</div>
<div class="rs-kpis" id="k"></div>
```

```js
document.getElementById("k").innerHTML = rs.kpi("Inside the range", "80.4%", "promised 80 %", "#15803d") + rs.kpi("Typical miss", "10 %", "on one hour");
```

`rs.kpi(title, value, sub, color)` gives the HTML of one tile: a small title, a big number and a line under it. `rs-kpis` is a grid of three tiles (`--rs-kpi-cols` changes the number). In the dark theme the color of a number (the fourth argument) is mixed with the theme's text color, so any color stays readable. `rs-cap` is a small capital caption over the tiles.

## A callout

<iframe class="rs-live" src="../../parts/gallery.html?part=callout" title="A callout, live" loading="lazy"></iframe>

Use a callout for the answer of a page, in one box at the top.

```html
<div class="rs-callout" style="--rs-callout:#16a34a"><b>Yes, the promise holds.</b> On 80 % of hours the traffic was inside the range.</div>
```

The edge has the color of `--rs-callout`, or `--accent` when the page gives none. The box has the card color and the theme's line.

## Rows of fields

<iframe class="rs-live" src="../../parts/gallery.html?part=kv" title="Rows of fields, live" loading="lazy"></iframe>

Use rows of fields for the fields of one item: one road, one sensor. roadstyle draws the road information of the panel with them.

```html
<div class="rs-name">Götgatan</div>
<div class="rs-kv"><span>highway</span><b>primary</b></div>
<div class="rs-kv"><span>lanes</span><b>2</b></div>
```

The name of the field is muted at the left. The value is at the right, and a long value breaks. In the panel the rows take the theme's colors.

## List rows

<iframe class="rs-live" src="../../parts/gallery.html?part=list" title="List rows, live" loading="lazy"></iframe>

The find box uses list rows for its results: a name and a muted detail in one row, with a hover.

```html
<div class="rs-qrow"><b>Götgatan</b><span>highway: primary</span></div>
```

The detail is cut with "…" when the row is too narrow. For a list that can be long, put the rows in [`rs-scroll`](#a-list-or-a-table-that-scrolls). The lines between the rows and the muted detail have fixed light colors: in the dark theme the lines are too bright.

## Charts

<iframe class="rs-live" src="../../parts/gallery.html?part=svg" title="A chart of your own, live" loading="lazy"></iframe>

Use `rs.svg` for a chart that [`rs.chart`](#a-chart) does not draw, for example a band of a forecast.

```js
const s = document.querySelector("#chart");
rs.svg(s, "line", {x1: 0, x2: 300, y1: 40, y2: 40, stroke: "var(--rs-chart-grid)"});
rs.svg(s, "polygon", {points: "...", fill: "var(--rs-chart-band)", stroke: "var(--rs-chart-band-line)"});
rs.svg(s, "text", {x: 4, y: 12, fill: "var(--mut)", "font-size": 9}, "0");
```

`rs.svg(parent, tag, attrs, text)` makes one SVG element and gives it back. An SVG attribute does not read `var(--x)`, so a value that starts with `var(` goes to the style. The chart then follows the theme with no code of its own. The colors that charts share are `--rs-chart-band`, `--rs-chart-band-line`, `--rs-chart-grid` and `--rs-chart-miss`. For text and lines use the tokens `--ink`, `--mut`, `--line` and `--card`. A canvas cannot read a variable: draw it again on the event `rs:themechange`.

## A chart

<iframe class="rs-live" src="../../parts/gallery.html?part=chart" title="A chart, live" loading="lazy"></iframe>

`rs.chart(el, spec)` draws a chart of a table of rows in an element: bar, line, histogram, scatter or pie. It is SVG with the theme's tokens, so it follows the theme. The data dock uses it for its **Chart** view ([The data dock](data-dock.md)), and the chart card uses it in the panel ([Charts](charts.md): a chart from Python, with no JavaScript). Above, the switch calls `set` with another kind, and a click on a bar calls `onPick`.

```js
const c = rs.chart(document.getElementById("km"), {kind: "bar", x: "highway", y: "km",
  columns: [{name: "highway", type: "VARCHAR"}, {name: "km", type: "DOUBLE"}],
  rows: [["residential", 30.5], ["primary", 12.5], ["secondary", 8.25]],
  onPick: (i) => console.log("row", i)});
c.set({kind: "pie"});        // the same data, another kind
```

| Kind | `x` | `y` | What it draws |
|---|---|---|---|
| `bar` | a column of labels | one number column, or a list of up to 3 | one bar for each row, at most 40; horizontal when a label is longer than 8 characters |
| `line` | a number, a date or a time | one number column, or a list | one line through the rows in the order of `x` |
| `histogram` | a number column | none | the rows in each of 20 equal ranges; `values` (all the numbers) can give more rows than `rows` |
| `scatter` | a number column | a number column | one point for each row, at most 5000 |
| `pie` | a column of labels | one number column of 0 or more | one slice for each row, largest first, at most 6: the rest is "Other" |

- The series have the colours `--rs-chart-1` to `--rs-chart-8`, in this order: the dashboard's teal first (one series has it), then orange, blue, yellow, pink, green, violet and red, checked for colour vision deficiency in both themes. The marks are a little see-through, and the mark under the pointer has its full colour. Two or more series, and a pie, have a legend.
- The chart has a title (`title`, else from the kind and the columns: "km by highway"; `false`: no title) and the number of rows under it (`count`: your own text, for example "13 298 roads"). The axis ticks are compact (0, 2.5K, 5K) on hairline grid lines over a darker base line. A scatter has its axis titles outside the plot: the `y` name over the `y` ticks, the `x` name under the `x` ticks. While the pointer is on a mark, the other marks fade.
- Value labels: a bar of one series has its value at its tip, of each bar up to 15 bars, else of the largest only. A single line has a soft wash under it. It has a value over each point only when all of them fit: at most 15 points, and each label is narrower than the space to the next point. Else the line has no value labels, and the pointer on a point shows its value. Two or more lines have no value labels.
- The chart fits its box, and draws again when the box changes its width or its height. A bar is at most 24 px thick. Horizontal bars get thinner to fit the height, down to a row of 12 px (a bar of 4 px for each series). Past that minimum, the box scrolls: on a desktop it has a thin scrollbar, on a phone a fade at its bottom edge while there is more below. A pie is the largest circle that fits in the box with its legend: above the pie, or in a column beside it when that gives a larger pie (a wide, low box).
- The pointer on a bar, a point or a slice shows its values. A click on it calls `onPick(row)`.
- A kind that does not fit the columns shows a line in place of the chart, for example "A pie chart needs a text column and one number column of 0 or more."
- `small: true` draws a copy with no labels and no hover (the card of an Ask answer). A small pie keeps its legend: the pie at the left at its full height, the legend at its right.
- `head: el` puts the chart's title line into another element (the data dock gives an element that is not on the page, so its chart has no title line).
- `set(change)` draws again with a change of the spec; `spec()` gives the spec, `svg()` gives the SVG element, and `destroy()` removes the chart.
- `rs.chart.ranges(numbers, parts)` puts many numbers in about `parts` ranges: `{n, of(v), label(k)}`. The data dock and the chart card use it for a bar (12) or a pie (6) of a number `x` with more than 40 values.

`tests/test_chart_browser.py` checks each kind in both themes and at 390 px, the fit of the bars and the pie, the axis titles of a scatter and the value labels of a line.

## A list or a table that scrolls

<iframe class="rs-live" src="../../parts/gallery.html?part=scroll" title="A table that scrolls, live" loading="lazy"></iframe>

```html
<div class="rs-scroll"><table class="rs-table"><thead><tr><th data-sort="desc">Street</th><th>Hours</th></tr></thead><tbody>...</tbody></table></div>
```

`rs-scroll` gives the area the scroll rules of the panel body: a thin scrollbar that shows only over the area or while it scrolls, a fade at the bottom edge while there is more below, and a scroll that never goes on to the map. The height is `--rs-scroll-h` (default: the smaller of 520 px and 60 % of the window). `rs-table` keeps the header row in view, lines up the numbers (the first column is text) and tints the row under the pointer. Put `data-sort="asc"` or `"desc"` on the `th` of the sorted column. The table does not sort: your code sorts the rows. For a wide table of many columns, use [the bottom dock](#the-bottom-dock).

Every scroll area of the dashboard has these rules, not only `rs-scroll`: the help window, the boxes of the toolbox, the panel's own select list and the query part's list. A whole box has no fade, because the fade would also take its border. `tests/test_dashboard_scroll_browser.py` checks each area.

## Parts that need the map

These parts work only on a page with a map and `rsDashboard`. The box below is a small host page: MapLibre, `dashboard.css` and `rsDashboard` on the page's own map and panel, with three roads and no tiles. The box is 700 px wide or less, so the dashboard has its phone form: the toolbox is a row at the top and the panel is a sheet at the bottom. [Open the page alone](../parts/host.html) to see the desktop form.

### The bottom dock

<iframe class="rs-live rs-live-map" src="../../parts/host.html" title="The bottom dock on a map, live" loading="lazy"></iframe>

Use the bottom dock for a wide table, a chart or a list that does not fit in the panel. Click **Show the table** above, drag the grip, click a header to sort.

```javascript
const t = rs.dock.table({columns: [{name: "edge_id", type: "BIGINT"}, {name: "name", type: "VARCHAR"}], rows: [[8121729169906061189n, "Götgatan"]]});
rs.dock.add({id: "roads", label: "Roads", el: t.el, note: "1 row"});
rs.dock.open("roads");
```

The calls are `add`, `remove`, `open`, `close`, `isOpen`, `show`, `note`, `height`, `list` and `table`. The event `rs:dockchange` comes when the dock opens, closes, changes its content or changes its height. The full text is in [The bottom dock](dashboard-layout.md#the-bottom-dock).

### The data dock and Ask

The data dock runs one SQL line on the host's own database and shows the result in the bottom dock. Ask is an editor frame that sends a question to a model provider with the person's own key. Both need a database of the host, so this page does not show them live. See [The data dock](data-dock.md) and [Ask](ask.md).

## Parts that roadstyle does not have yet

These parts are planned. Until they come, write the control with the parts above, or ask for the part.

- A date range, week or month picker: planned.
- An hour or hour-range picker: planned.
- A slider with its value, and a range slider with two handles: planned.
- A number field with a unit and steppers: planned.
- A colour picker: planned.
- An on and off toggle: planned.
- A search field with a clear button, an end button and suggestions: planned.
- A file drop zone: planned.
- A progress bar and a busy button: planned.
- A status line or a toast: planned.
- A confirm dialog: planned.
- A menu of actions: planned.
- A count badge and a "not saved" dot on a tab: planned.
- Numbered steps with a done mark: planned.
- A row of icon tools in the panel: planned.
- An empty state: planned.
- "Show more" or paging: planned.

## The rules

- **Width.** Fit the content to the panel. Do not widen the panel for it (the width is `panel.width_px`: [Dashboard options](../reference/parameters.md#dashboard-options)). A table that needs more room drops a column or shortens a line.
- **Colors.** No color literal for text, lines, cards or chart furniture: use the tokens. A color that is the page's own *data* (a coverage band, a class) can be a literal, but a theme-aware one is better.
- **Both themes.** Look at the page in the light and in the dark theme, with the bar at two edges and at phone width, before you commit it.
- **Scroll.** A list that can be long goes in `rs-scroll`. The panel body already scrolls.
- **Transparency.** The person sets three layers (bar and panel, boxes, card behind the text) in the settings box. A part reads them with the tokens `--rs-tb-bg`, `--rs-box-bg` and `--rs-card-bg`. A page never sets an opacity.

## Colour classes

```python
cls = rs.classify(gdf["coverage"], method="natural", k=5, pivot=0.8, palette="rdylgn", fmt="{:.0%}")
gdf["cov_class"] = cls.labels
rs.render_dashboard(gdf, color_options={"Coverage": cls.option("cov_class")})
```

`natural` (Fisher-Jenks) puts the cuts in the gaps of the data, so the classes have different widths and sizes. `quantile` gives each class the same number of
roads, `equal` the same width, `fixed` your own `breaks`. A `pivot` (the promised 80 %, zero) is always one of the cuts. A missing value gets its own grey class.
The JavaScript `rs.naturalBreaks(values, k)` gives the same cuts for a page with live data.

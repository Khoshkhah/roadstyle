# Dashboard parts

Every dashboard page is made of the same parts. Each box on this page is the real part: click it, type in it, fold it. **Use a part when one exists. Do not write CSS or JavaScript of your own for it**, because a copy does not follow the dark theme.

Each part has the same form: the live part, a box with **Use it for** and **From Python**, and the code in tabs, always in the order **Python**, **HTML**, **JavaScript**. **Details** opens on a click.

- **Python**: a section of `rs.render_dashboard(gdf, dashboard={"panel": {"sections": [...]}})`.
- **HTML**: the `html` of a section, from Python or JavaScript.
- **JavaScript**: code in `page_script`, inside `rs.ready(() => {...})`.

[All the parts in one panel](../parts/gallery.html) has a theme switch and a phone width.

| Group | Part | From Python | Use it for |
|---|---|---|---|
| Layout | [Cards](#cards) | yes | the blocks of the panel |
| Layout | [A card in the page's own HTML](#a-card-in-the-pages-own-html) | HTML | a card inside a tab or a block |
| Layout | [A card that opens something](#a-card-that-opens-something) | no | a card that opens an editor |
| Layout | [Tabs](#tabs) | yes | the sections of a page |
| Layout | [An editor in the panel](#an-editor-in-the-panel) | no | an editor that needs the whole panel |
| Layout | [A list or a table that scrolls](#a-list-or-a-table-that-scrolls) | HTML | a long list |
| Inputs | [Buttons](#buttons) | HTML | an action |
| Inputs | [A two-way switch](#a-two-way-switch) | no | a mode or a setting |
| Inputs | [A select box](#a-select-box) | HTML | one value of many |
| Inputs | [A text box, a check box and a radio button](#a-text-box-a-check-box-and-a-radio-button) | HTML | a form |
| Inputs | [A colour picker](#a-colour-picker) | HTML | a colour that the person chooses |
| Inputs | [Option rows](#option-rows) | HTML | settings with a note |
| Inputs | [A day picker](#a-day-picker) | no | one day of data at a time |
| Inputs | [The query part](#the-query-part) | yes | a question about the roads |
| Showing data | [Number tiles](#number-tiles) | yes | the few numbers of a page |
| Showing data | [Rows of fields](#rows-of-fields) | HTML | the fields of one item |
| Showing data | [List rows](#list-rows) | HTML | a list of results |
| Showing data | [Chips and a dot](#chips-and-a-dot) | HTML | a label, a colour mark |
| Showing data | [The road card](#the-road-card) | yes | the clicked road |
| Showing data | [A chart](#a-chart) | yes | a chart of rows |
| Showing data | [Charts of your own](#charts) | no | a chart that `rs.chart` does not draw |
| Showing data | [Colour classes](#colour-classes) | yes | classes for a colour menu |
| Status | [A callout](#a-callout) | HTML | the answer of a page |
| Status | [Status colours](#status-colours) | HTML | an error, a warning, a good result |
| Help | [A help window](#a-help-window) | yes | "How to read this page" |
| Help | [A hover box](#a-hover-box) | no | words under the pointer |
| Help | [A button tip](#a-button-tip) | HTML | the name of an icon button |
| Map | [The bottom dock](#the-bottom-dock) | no | a wide table under the map |

**yes**: a Python option, no JavaScript. **HTML**: write the HTML in a section's `html`. **no**: JavaScript only.

## Foundations { .rs-group }

### The accent color and the theme tokens { .rs-part }

**Use it for:** your own colours. The tokens change with the theme.<br>
**From Python:** CSS, in a `<style>` of a section's `html`
{ .rs-facts }

| Token | Use |
|---|---|
| `var(--ink)`, `var(--mut)` | text, muted text |
| `var(--bg)`, `var(--card)` | the panel, a box in it |
| `var(--line)` | thin lines |
| `var(--accent)`, `var(--accent-fill)` | links; a filled control |
| `var(--rs-err)`, `var(--rs-warn)`, `var(--rs-ok)` | [status colours](#status-colours) |

??? info "Details"

    - The accent is one teal for the whole dashboard. A page does not set its own. `--accent` is `#0e7c8e` in the light theme and a lighter teal in the dark theme. `--accent-fill` is `#0E7F91` and takes white text in both themes.
    - `var(--rs-hover-bg)` is the tint behind a control under the pointer.
    - `rsSetTheme("dark")` or `rsSetTheme("light")` changes the theme and sends the event `rs:themechange`.
    - `tests/test_dashboard_themes_browser.py` opens each part in both themes. It fails on a text with a contrast under 4.5 and on a light surface or line in the dark theme.

### The rules { .rs-part }

- **Width.** Fit the content to the panel. Do not make the panel wider.
- **Colours.** Use the tokens, not fixed colours. A colour of your data can be fixed.
- **Both themes.** Look at the page in the light and the dark theme, and at phone width.
- **Scroll.** Put a long list in `rs-scroll`.
- **Transparency.** The person sets it in the settings box. A page never sets an opacity.

## Layout: cards, tabs and frames { .rs-group }

### Cards { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=cards" title="Cards, live" loading="lazy"></iframe>

**Use it for:** each block of the panel. A section with a `label` is a card.<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    {"id": "notes", "label": "Notes", "html": "<p>Text</p>"}
    {"id": "more", "label": "More", "fold": True, "note": "Click the title", "html": "<p>Text</p>"}
    {"id": "flat", "label": "No background", "background": False, "html": "<p>Text</p>"}
    ```

=== "JavaScript"

    ```js
    rs.sections.add({id: "more", label: "More", fold: true, html: "<p>Text</p>"});
    rs.sections.note("more", "3 roads");      // the line under the title
    rs.sections.fold("more", false);          // open it
    ```

<a id="cards-the-panel-standard"></a>

??? info "Details"

    - A card that folds keeps its state in the browser. **Collapse all** in the panel title folds all of them.
    - The event `rs:sectionchange` has `detail.id` and `detail.state` (`add`, `remove`, `hide`, `show`, `fold`, `unfold`).
    - A section without a `label` is the page's HTML with no box. It has no title, no padding and no background. Use it for content with its own layout: tabs, a row of number tiles, or the page's own cards. It is as wide as the cards and has `--rs-card-gap` above and below.

    **The panel standard.** Two options choose one of four kinds of card:

    | | `background` (default) | `background: false` |
    |---|---|---|
    | does not fold (default) | `{"id", "label", "html"}` | `{"id", "label", "html", "background": False}` |
    | `fold: true` | `{"id", "label", "html", "fold": True}` | `{"id", "label", "html", "fold": True, "background": False}` |

    - Each kind has the same title row, the same 12 px corners and the same padding.
    - A card that folds has a chevron, and its title is a button. A closed card has a thin gray edge (`--rs-card-edge`). An open card has a thin accent ring and an accent title. The edge and the ring are inside the card, so they do not change its size. The edge has a contrast of 3:1 or more on the card and on the panel, in both themes.
    - A "?" of [`rs.help.button`](#a-help-window) is at the right end of the title row, before the chevron. The chevron is last.
    - A closed card is 14 + 16 + 14 = 44 px high with the default padding.
    - The buttons in the panel title are in a fixed order: "collapse all" (`#rs-fold-all`) is at the left of "hide the panel" (`#sb-hide`).
    - Do not write your own spacing, padding or corner radius. The panel sets them.
    - Do not put an `rs-sec-box` inside a section with a `label`. The section is already a card, and a box in it makes a card in a card. Put the content directly in `html`.
    - Use `var(--accent-fill)` (`#0E7F91`) with white text for a filled control. Use `var(--accent)` for links and marks. Do not use another teal.

    Three CSS variables on `:root` hold the numbers for all cards:

    | Variable | Default | Meaning |
    |---|---|---|
    | `--rs-card-gap` | `12px` | The space between two cards, and between a card and a section without a label |
    | `--rs-card-pad` | `14px` | The padding inside a card |
    | `--rs-panel-bottom` | `28px` | The space under the last card, at the end of the panel |

### A card in the page's own HTML { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=page-card" title="A card in the page's own HTML, live" loading="lazy"></iframe>

**Use it for:** a card inside a tab, a block or an [editor frame](#an-editor-in-the-panel). A section with a `label` is a card already.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-sec-box"><div class="rs-card-title">By hour of the day</div><p>Text</p></div>
    <div class="rs-sec-box"><h3>By hour</h3><p>A short, muted description.</p><svg>...</svg></div>
    ```

### A card that opens something { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=open" title="A card that opens something, live" loading="lazy"></iframe>

**Use it for:** a card whose only job is to open an editor or a dialog. The card is one button.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```js
    rs.sections.add({id: "edit", label: "Edit roads", note: "Opens the editor", open: () => frame.open("tags")});
    rs.sections.add({id: "ask", label: "Ask", icon: "ask", background: true, open: () => ask.open()});
    ```

??? info "Details"

    - The card is one button: a click anywhere on it, or Enter on its title, runs `open`. `open` is JavaScript only, because it is a function.
    - The card never folds, and "Collapse all" leaves it. It has no background and a thin edge. Under the pointer it gets a light tint of the accent colour.
    - `note` tells the state. `rs.sections.note(id, text)` changes it.
    - `icon` changes the mark at the end of the row: `"edit"` (the pencil, the default), `"ask"` (a speech bubble with a question mark) or your own `<svg>`. It does not depend on the background.
    - `background: true` gives the light accent tint, so that one card stands out from the others. The edge stays.
    - To keep a card from opening (a step that is not ready), disable its title button: `rs.sections.get(id).querySelector(".rs-sec-title").disabled = true`.
    - A card with `open` and `fold` is an error.

### Tabs { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=tabs" title="Tabs, live" loading="lazy"></iframe>

**Use it for:** the sections of a page: a click shows another pane. To draw the same content in another way, use a [two-way switch](#a-two-way-switch).<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    {"id": "streets", "label": "Streets", "tabs": [
        {"id": "a", "label": "Overview", "html": "<p>...</p>"},
        {"id": "b", "label": "Hours", "html": "<p>...</p>"}]}
    ```

=== "HTML"

    ```html
    <nav class="rs-tabs"><button class="rs-tab on" data-tab="a">Overview<span class="rs-count">12</span></button><button class="rs-tab" data-tab="b">Hours</button></nav>
    <div data-pane="a">...</div><div data-pane="b" hidden>...</div>
    ```

=== "JavaScript"

    ```js
    const tabs = rs.tabs.use(document.querySelector(".rs-tabs"), id => console.log(id));
    tabs.select("b");   // as a click
    ```

??? info "Details"

    - `rs-count` is a count after the words of a tab. Add `err` or `warn` only when the count needs attention.
    - A click or the left and right keys select a tab. The selected button has `on` and `aria-selected="true"`.
    - The panes are the siblings of the `nav` with `data-pane`. Only the selected one shows.
    - `tabs.select("b", true)` selects with no call of `onChange`. `tabs.current()` gives the selected tab.

### An editor in the panel { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=frame" title="The editor frame, live" loading="lazy"></iframe>

**Use it for:** an editor that needs the whole panel, as Edit design and the level editor do. Click **Open the editor frame** above.<br>
**From Python:** no
{ .rs-facts }

| Area | Where | What to put in it | Scrolls |
|---|---|---|---|
| `top` | the panel's title line | "← back" and the title | no |
| `head` | under the title line | the tab row, or a row of your own | no |
| `body` | the middle | the form of the selected tab | yes |
| `bar` | the bottom edge | the state and the main buttons | no |

=== "JavaScript"

    ```javascript
    const fr = rs.frame({panel: document.getElementById("sb"), title: "Edit roads", back: "Steps", id: "ed",
                         tabs: [["tags", "Tags"], ["notes", "Notes"]]});
    fr.addEventListener("tab", (e) => { fr.body.innerHTML = formOf(e.detail.tab); });
    fr.addEventListener("back", () => fr.close());
    fr.bar.innerHTML = "<b>2 changes</b> <button type='button' class='sb-primary'>Apply</button>";
    fr.open("tags");
    ```

??? info "Details"

    | Option | Default | What it does |
    |---|---|---|
    | `panel` | (needed) | the host's panel: `#sb` with `.sb-card`, `.sb-top` and `.sb-body` |
    | `title` | (needed) | the title |
    | `back` | `null` | the words of the back button; `null`: no button |
    | `tabs` | `[]` | `[[id, name], ...]`: the tab row |
    | `head` | `null` | an element for the head row (the Ask panel: no tabs, a row of its own) |
    | `id` | `"rs-frame"` | the start of the ids: `<id>-back`, `<id>-tabs`, `<id>-tab-<tab>`, `<id>-body` |

    | Method or event | What it does |
    |---|---|
    | `open(tab)` | hides the host's panel content and shows the frame |
    | `close()` | removes the frame and shows the host's panel again |
    | `tab(name)`, `tab()` | selects a tab with no event; gives the selected tab |
    | `isOpen()` | `true` while the frame is open |
    | event `tab` | a click on a tab (`e.detail.tab`) |
    | event `back` | a click on the back button: call `close()` |

    - The frame does not draw the body: draw it when the event `tab` comes.
    - A count on a tab: add a `<span class="rs-count">` to the tab's button (`#<id>-tab-<tab>`) after `open()`.
    - The parts of this page work in the body. Each `<select>` becomes the [select box](#a-select-box).
    - On a phone the frame fills the sheet, and the tabs scroll sideways.
    - A module page without `window.rs`: `import {editorFrame} from "./dashboard/frame.js"`.

### A list or a table that scrolls { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=scroll" title="A table that scrolls, live" loading="lazy"></iframe>

**Use it for:** a long list or table in the panel. For a wide table, use [the bottom dock](#the-bottom-dock).<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-scroll"><table class="rs-table"><thead><tr><th data-sort="desc">Street</th><th>Hours</th></tr></thead><tbody>...</tbody></table></div>
    ```

??? info "Details"

    - The area has a thin scrollbar and a fade at the bottom while there is more below. Its height is `--rs-scroll-h` (default: 520 px or 60 % of the window, the smaller).
    - The header row stays in view, and the numbers line up. `data-sort` on a `th` shows the sort arrow. The table does not sort: your code sorts the rows.

## Inputs { .rs-group }

### Buttons { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=buttons" title="Buttons, live" loading="lazy"></iframe>

**Use it for:** an action. `sb-primary` is the one main action of a card. `rs-link` is a small action in a line of text.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="sb-actions"><button type="button" class="sb-primary">Run</button><button type="button">Reset</button></div>
    <button type="button" class="rs-link">clear</button>
    ```

??? info "Details"

    | Kind | Hover |
    |---|---|
    | Not filled | the tint `--rs-hover-bg` and the accent colour |
    | Filled | brighter |
    | A link | underlined |

    - A `disabled` button is faded and does not react. Keyboard focus has an accent ring.
    - The look of a plain `<button>` in the panel comes from the dashboard template. A host page with no template gets it only in an editor frame.

### A two-way switch { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=switch" title="A two-way switch, live" loading="lazy"></iframe>

**Use it for:** a mode or a setting with a few values: the same content is drawn in another way. To show another pane, use [tabs](#tabs).<br>
**From Python:** no
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-seg" id="mode"><button class="on" data-v="all">Every day</button><button data-v="first">First day</button></div>
    ```

=== "JavaScript"

    ```js
    rs.tabs.use(document.getElementById("mode"), v => redraw(v));
    ```

### A select box { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=select" title="A select box, live" loading="lazy"></iframe>

**Use it for:** one value of many, for example "Colour by". Write a plain `<select>`: roadstyle gives it its look.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <label>Colour by</label>
    <select id="by"><option value="class">Road class</option><option value="speed">Speed limit</option></select>
    ```

=== "JavaScript"

    ```js
    document.getElementById("by").addEventListener("change", e => recolour(e.target.value));
    ```

??? info "Details"

    - Your code reads and sets the `<select>` as usual (`value`, `disabled`, the `change` event). The button follows.
    - The keys: Down or Up opens the list, Enter picks, Escape closes.
    - In a card, the select box has a thin line around it, as a text box has.

### A text box, a check box and a radio button { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=inputs" title="Text boxes, check boxes and radio buttons, live" loading="lazy"></iframe>

**Use it for:** a form. Write no class.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <label>Street</label><input placeholder="Götgatan">
    <label>Note</label><textarea rows="3"></textarea>
    <input type="checkbox" checked> Bridges
    <input type="radio" name="count" checked> Every day
    ```

### A colour picker { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=color" title="A colour picker, live" loading="lazy"></iframe>

**Use it for:** a colour that the person chooses. Write a plain `<input type="color">`: roadstyle gives it its look.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <label>Road fill</label><input type="color" id="fill" value="#b8d986">
    ```

=== "JavaScript"

    ```js
    document.getElementById("fill").addEventListener("input", e => preview(e.target.value));   // while the person drags
    document.getElementById("fill").addEventListener("change", e => save(e.target.value));     // when the person is done
    ```

??? info "Details"

    - The box has a square for the saturation and the lightness, a hue bar, the colour before and the new colour, a hex field, the colours used last on the page, and an eyedropper where the browser has one.
    - Your code reads and sets `value` and `disabled` as usual. The swatch follows. `input` comes while the person drags, `change` when the box closes with a new colour.
    - Escape closes the box and puts back the colour before. A click on the old colour does the same and keeps the box open. Enter or a click outside keeps the new colour.
    - The arrow keys move the dot in the square (with Shift: ten times as far) and the hue on the bar.
    - It comes to each `<input type="color">` in the panel at the start, in a section that `rs.sections.add` adds, and in an [editor frame](#an-editor-in-the-panel).

### Option rows { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=opt" title="Option rows, live" loading="lazy"></iframe>

**Use it for:** settings with a short note, or a choice of a list. `rs-opts-row` puts the rows side by side.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-opts">
      <label class="rs-opt"><input type="checkbox" checked><span><b>Layers</b><small>Water, land use, buildings.</small></span></label>
      <label class="rs-opt"><input type="radio" name="x"><span><b>Monaco</b><small>2 km²</small></span><button type="button">Get</button></label>
    </div>
    ```

### A day picker { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=days" title="A day picker, live" loading="lazy"></iframe>

**Use it for:** a page that shows one day of data at a time.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```js
    const day = rs.days.use(document.getElementById("day"), {
      days: ["2026-10-01", "2026-10-04", "2026-10-05"],      // the days with data
      onChange: d => fetch(`daily_${d}.json`).then(r => r.json()).then(draw),
    });
    ```

??? info "Details"

    - `value` is the day at the start (default: the latest). `label` is the label (default: "Day").
    - `day.value()` gives the day. `day.set("2026-10-04")` changes it; `day.set(d, true)` does not call `onChange`.
    - Only the days in `days` can be picked. "‹" and "›" skip the days with no data. "Latest" goes to the last day.
    - When `onChange` gives a promise, the field waits for it. When the promise fails, the picker goes back to the old day and shows a line.

### The query part { .rs-part }

**Use it for:** a question about the roads: a WHERE line with **Run**, **Filter**, **Colour** and the list of the roads that match.<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    {"id": "q", "label": "Query", "part": "query", "text": "p.lanes >= 2"}
    ```

`text` is the start text (none: an empty box). More: [Dashboards](dashboards.md#the-panel-starts-empty).

## Showing data { .rs-group }

### Number tiles { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=kpi" title="Number tiles, live" loading="lazy"></iframe>

**Use it for:** the few numbers that a page is about. For many numbers, use [a table](#a-list-or-a-table-that-scrolls).<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    {"id": "tiles", "kpis": [
        {"title": "Inside the range", "value": "80.4%", "sub": "promised 80 %", "color": "#15803d"},
        {"title": "Hours", "value": 1412}]}
    ```

=== "HTML"

    ```html
    <div class="rs-cap">All hours</div>
    <div class="rs-kpis" id="k"></div>
    ```

=== "JavaScript"

    ```js
    document.getElementById("k").innerHTML = rs.kpi("Inside the range", "80.4%", "promised 80 %", "#15803d") + rs.kpi("Hours", "1412");
    ```

??? info "Details"

    - A row has three tiles. `--rs-kpi-cols` changes the number.
    - In the dark theme the colour of a value is mixed with the text colour, so it stays readable.

### Rows of fields { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=kv" title="Rows of fields, live" loading="lazy"></iframe>

**Use it for:** the fields of one item: one road, one sensor.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-name">Götgatan</div>
    <div class="rs-kv"><span>highway</span><b>primary</b></div>
    <div class="rs-kv"><span>lanes</span><b>2</b></div>
    ```

### List rows { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=list" title="List rows, live" loading="lazy"></iframe>

**Use it for:** a list of results: a name and a muted detail. Put a long list in [`rs-scroll`](#a-list-or-a-table-that-scrolls).<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-qrow"><b>Götgatan</b><span>highway: primary</span></div>
    ```

### Chips and a dot { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=chips" title="Chips and a dot, live" loading="lazy"></iframe>

**Use it for:** a small label of a value (not an action), and a colour mark before a word.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <span class="rs-chip">road type</span> <span class="rs-chip accent">primary</span>
    <span class="rs-dot" style="background:#15803d"></span>inside the range
    ```

### The road card { .rs-part }

**Use it for:** the fields of the road that the person clicked.<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    {"id": "road", "label": "Selected road", "part": "road_card", "fields": ["name", "highway", "lanes"]}
    ```

`fields` are the columns to show (none: every column). The road card and the popup can be on the same page: [A click on a road](dashboards.md#a-click-on-a-road-the-popup-the-card-or-both).

### A chart { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=chart" title="A chart, live" loading="lazy"></iframe>

**Use it for:** a chart of rows: bar, line, histogram, scatter or pie.<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    {"id": "km", "label": "km by class", "part": "chart",
     "chart": {"kind": "bar", "x": "highway", "y": "length_m", "scale": 0.001}}
    ```

=== "JavaScript"

    ```js
    const c = rs.chart(document.getElementById("km"), {kind: "bar", x: "highway", y: "km",
      columns: [{name: "highway", type: "VARCHAR"}, {name: "km", type: "DOUBLE"}],
      rows: [["residential", 30.5], ["primary", 12.5]], onPick: (i) => console.log("row", i)});
    c.set({kind: "pie"});      // the same rows, another kind
    ```

??? info "Details"

    | Kind | `x` | `y` | What it draws |
    |---|---|---|---|
    | `bar` | labels | one number column, or up to 3 | one bar for each row, at most 40 |
    | `line` | a number, a date or a time | one number column, or a list | one line in the order of `x` |
    | `histogram` | a number column | none | the rows in 20 equal ranges |
    | `scatter` | a number column | a number column | one point for each row, at most 5000 |
    | `pie` | labels | one number column of 0 or more | at most 6 slices; the rest is "Other" |

    - The series colours are `--rs-chart-1` to `--rs-chart-8`, checked for colour vision deficiency in both themes.
    - `title` (or `false`), `count`, `small`, `head`; `set(change)`, `spec()`, `svg()`, `destroy()`.
    - The pointer on a mark shows its values. A click calls `onPick(row)`.

    **A chart card from Python**

    A chart card is a section with `part: "chart"` and its options in `chart`. It reads the map's roads or rows that you give, and it follows the dark theme. A click on a bar lights its roads on the map.

    ```python
    import roadstyle as rs

    rs.render_dashboard(edges, dashboard={"panel": {"sections": [
        # the map's roads: the number of roads of each class
        {"id": "classes", "label": "Roads by class", "part": "chart", "chart": {"kind": "pie", "x": "highway"}},
        # the map's roads: the km of each class (the sum of a column, times 0.001)
        {"id": "km", "label": "km by class", "part": "chart", "chart": {"kind": "bar", "x": "highway", "y": "length_m", "scale": 0.001}},
        # your own rows: a DataFrame, or a list of dicts
        {"id": "flow", "label": "Vehicles per hour", "part": "chart", "chart": {"kind": "line", "x": "hour", "y": "vehicles", "data": counts_df}},
    ]}}).save("dashboard.html")
    ```

    ![Three chart cards in the panel: a pie of the roads by class, a bar of the km by class, and a line of the vehicles per hour](../img/charts/panel.png){ width="340" }

    **The options of `chart`**

    | Option | Default | What it is |
    |---|---|---|
    | `kind` | (necessary) | `bar`, `line`, `histogram`, `scatter` or `pie` |
    | `x` | (necessary) | A column: the groups (bar, pie), the order (line), the numbers (histogram, scatter) |
    | `y` | none | A number column, or a list of up to 3 (bar, line). None: the count of rows. A histogram has no `y`. A scatter needs one |
    | `agg` | `"sum"` | How the rows of one value of `x` join: `sum`, `mean`, `min`, `max` or `count` |
    | `scale` | `1` | A factor for the values of `y` (`0.001`: metres to km) |
    | `data` | none: the map's roads | Your own rows. Python: a pandas DataFrame, a GeoDataFrame (its geometry is not used) or a list of dicts. JavaScript: `{columns, rows}` or a list of objects. The rows are written into the page |
    | `title` | the card's `label` | The title of the chart. A card with a `label` shows no second title |
    | `height` | `220` | The height of the chart in pixels (80 or more) |
    | `follow` | `false` | The map's roads only: `true` draws the chart again for the roads that the map shows now |

    The section has the keys of each card: `label`, `fold`, `note`, `background`, `after` and `before` ([Dashboards](dashboards.md#the-panel-starts-empty)).

    **The two sources**

    - **The map's roads.** With no `data`, the chart reads the road table of the page: the columns that the popup and the colours read. `x` and `y` are columns of the roads. The count line under the title gives the number of roads.
    - **Your own rows.** With `data`, the chart reads those rows. `x` and `y` must be columns of `data`. The two sources do not mix.

    Python writes `data` into the page as `{"columns": [{"name", "type"}], "rows": [[...]]}`. The types are the SQL type names of the data dock: `VARCHAR`, `DOUBLE`, `BIGINT`, `DATE`, `TIMESTAMP` and `BOOLEAN`. An integer of 2^53 or more is text, so a 64-bit id stays exact. A date is `YYYY-MM-DD` and a time is `YYYY-MM-DD HH:MM:SS`.

    **Groups and ranges**

    - A bar, a line or a pie joins the rows of each value of `x` with `agg`. With no `y`, the value is the number of rows.
    - A bar or a pie whose `x` is a number with more than 40 values (a length, say) puts the rows in ranges of `x`: about 12 bars or 6 slices. The data dock uses the same rule (`rs.chart.ranges`).
    - The order: ranges, numbers and dates go from small to large. The map's roads go from the largest value to the smallest. Your own rows keep their order.

    **A click**

    - **The map's roads.** A click on a bar, a slice or a point lights its roads on the map, in the colour of the mark (the highlight set `chart`). A second click on the same mark ends the light. A click on another mark moves the light.
    - **Your own rows.** A click sends the event `rs:chartpick` with `{id, row, rows}`: the id of the section, the values of the mark (`{hour: 7, vehicles: 820}`) and the indices of the rows of `data` in it. A page can act on it:

    ```js
    document.addEventListener("rs:chartpick", (e) => console.log(e.detail.id, e.detail.row));
    ```

    **The errors**

    `render_dashboard` gives a `ValueError` for:

    - an unknown `kind` or `agg`, or no `x`;
    - `y` for a histogram, no `y` for a scatter, more than one `y` for a pie or a scatter, or more than 3;
    - a column of `x` or `y` that is not in `data`;
    - `follow` with `data`;
    - `chart` on a section that is not `part: "chart"`, or `part: "chart"` with no `chart`.

??? info "One chart of each kind"

    Each picture shows one card and the `chart` that made it.

    **Bar**

    ```python
    {"kind": "bar", "x": "day", "y": "vehicles", "data": days_df}
    ```

    ![A bar chart of the vehicles on each day of the week](../img/charts/bar.png){ width="300" }

    **Horizontal bar**

    A bar chart is horizontal when a label of `x` is longer than 8 characters. The bars get thinner to fit the card; only a list that is too long for its minimum (a row of 12 px) scrolls in the card.

    ```python
    {"kind": "bar", "x": "highway", "y": "length_m", "scale": 0.001, "height": 300}
    ```

    ![A horizontal bar chart of the km of each road class](../img/charts/bar-horizontal.png){ width="300" }

    **Line**

    `y` can be a list of up to 3 columns. Two or more series have a legend.

    ```python
    {"kind": "line", "x": "hour", "y": ["vehicles", "trucks"], "data": hours_df}
    ```

    ![A line chart of the vehicles and the trucks for each hour](../img/charts/line.png){ width="300" }

    **Histogram**

    A histogram counts the values of `x` in 20 equal ranges. It has no `y`.

    ```python
    {"kind": "histogram", "x": "speed_kmh", "data": speeds_df}
    ```

    ![A histogram of 400 speeds](../img/charts/histogram.png){ width="300" }

    **Scatter**

    A scatter chart has one point for each row: `x` and `y` are two number columns.

    ```python
    {"kind": "scatter", "x": "flow", "y": "speed_kmh", "data": speeds_df}
    ```

    ![A scatter chart of the speed against the flow](../img/charts/scatter.png){ width="300" }

    **Pie**

    A pie has at most 6 slices. The smaller values are one slice, "Other".

    ```python
    {"kind": "pie", "x": "highway"}
    ```

    ![A pie of the roads by class](../img/charts/pie.png){ width="300" }

### Charts { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=svg" title="A chart of your own, live" loading="lazy"></iframe>

**Use it for:** a chart that [`rs.chart`](#a-chart) does not draw, for example the band of a forecast.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```js
    const s = document.querySelector("#chart");
    rs.svg(s, "line", {x1: 0, x2: 300, y1: 40, y2: 40, stroke: "var(--rs-chart-grid)"});
    rs.svg(s, "polygon", {points: "...", fill: "var(--rs-chart-band)", stroke: "var(--rs-chart-band-line)"});
    ```

??? info "Details"

    - `rs.svg` puts a `var(--x)` value in the style, so the chart follows the theme with no code of its own.
    - The shared chart colours are `--rs-chart-band`, `--rs-chart-band-line`, `--rs-chart-grid` and `--rs-chart-miss`.

### Colour classes { .rs-part }

**Use it for:** road classes of a number, for a colour menu.<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    cls = rs.classify(gdf["coverage"], method="natural", k=5, pivot=0.8, palette="rdylgn", fmt="{:.0%}")
    gdf["cov_class"] = cls.labels
    rs.render_dashboard(gdf, color_options={"Coverage": cls.option("cov_class")})
    ```

=== "JavaScript"

    ```js
    const cuts = rs.naturalBreaks(values, 5);    // the same cuts, for a page with live data
    ```

??? info "Details"

    - `method` is `natural`, `quantile`, `equal` or `fixed` (your own `breaks`).
    - A `pivot` (the promised 80 %, zero) is always a cut. A missing value gets its own grey class.

## Status and feedback { .rs-group }

### A callout { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=callout" title="A callout, live" loading="lazy"></iframe>

**Use it for:** the answer of a page, in one box at the top.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-callout" style="--rs-callout:#16a34a"><b>Yes, the promise holds.</b> On 80 % of hours the traffic was inside the range.</div>
    ```

??? info "Details"

    - The colour is `--rs-callout` (default: the accent). For a status, use a [status colour](#status-colours).
    - The mark is "i". `--rs-mark` gives another one, for example `style="--rs-mark:'✓'"`.

### Status colours { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=status" title="Status colours, live" loading="lazy"></iframe>

**Use it for:** something that is wrong (`err`), needs a look (`warn`) or is good (`ok`), on a callout, a chip or a [count](#tabs).<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <div class="rs-callout err"><b>Given up.</b> The solver could not keep 2 crossings.</div>
    <div class="rs-callout warn"><b>Check this.</b> Choose which road is on top.</div>
    <span class="rs-chip err">given up</span> <span class="rs-chip ok">kept</span>
    ```

??? info "Details"

    - A callout gets the mark ✕, ! or ✓, so the status is clear without the colour.
    - For your own status text, use `color: var(--rs-err)`, `var(--rs-warn)` or `var(--rs-ok)`. They have a light and a dark value.

## Help and hints { .rs-group }

### A help window { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=help" title="A help window, live" loading="lazy"></iframe>

**Use it for:** "How to read this page": a "?" in the panel title, or in a card title, opens the words.<br>
**From Python:** yes
{ .rs-facts }

=== "Python"

    ```python
    rs.render_dashboard(gdf, dashboard={"panel": {
        "help": {"title": "How to read this page", "intro": "What the page shows.",
                 "terms": [["Flow", "Cars in one hour."]], "note": "A short note."},
        "sections": [{"id": "s", "label": "Streets", "html": "...",
                      "help": {"title": "About the streets"}}]}})    # a "?" in the card title
    ```

=== "JavaScript"

    ```js
    rs.help.set({title: "How to read this page", intro: "What the page shows.", terms: [["Flow", "Cars in one hour."]]});
    rs.help.button(rs.sections.get("s"), {title: "About the streets"});    // a "?" in the card title
    rs.help.open({title: "Opened by a link"});                              // the same window, with no button
    ```

??? info "Details"

    - The words are `{title, intro, terms, note}`, and in JavaScript also `html` and `button` (the name of the button). The words can have HTML.
    - Escape, the ✕ and a click outside close the window. On a phone it is a sheet at the bottom.
    - `rs.help.get()` gives the words, `rs.help.clear()` takes the window away. The event `rs:helpchange` has `detail.open`.

### A hover box { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=hover" title="A hover box, live" loading="lazy"></iframe>

**Use it for:** the words of the point under the pointer: a bar of your own chart, a feature of your own map layer.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```js
    rs.hover.on(chartNode, ev => "<b>Saturday</b><br>24 hours");     // the words, or a function of the event
    rs.hover.show("<b>A street</b>", mapEvent.originalEvent);         // by hand
    rs.hover.hide();
    ```

### A button tip { .rs-part }

<iframe class="rs-live" src="../../parts/gallery.html?part=tip" title="A button tip, live" loading="lazy"></iframe>

**Use it for:** the name of an icon button. Give the button a `title`.<br>
**From Python:** HTML
{ .rs-facts }

=== "HTML"

    ```html
    <button type="button" title="Zoom to the area" aria-label="Zoom to the area"><svg>...</svg></button>
    ```

??? info "Details"

    - A button with words of its own shows no tip. A touch shows no tip.
    - The tip comes in the panel, the toolbox, its boxes and the windows. In another place, the browser shows its own tooltip.

## Parts that need the map { .rs-group }

These parts work only on a page with a map. The box below is a small page with three roads, at phone width. [Open it alone](../parts/host.html) to see the desktop form.

### The bottom dock { .rs-part }

<iframe class="rs-live rs-live-map" src="../../parts/host.html" title="The bottom dock on a map, live" loading="lazy"></iframe>

**Use it for:** a wide table, a chart or a list that does not fit in the panel. Click **Show the table** above.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    const t = rs.dock.table({columns: [{name: "edge_id", type: "BIGINT"}, {name: "name", type: "VARCHAR"}], rows: [[8121729169906061189n, "Götgatan"]]});
    rs.dock.add({id: "roads", label: "Roads", el: t.el, note: "1 row"});
    rs.dock.open("roads");
    ```

??? info "Details"

    - **A desktop.** The dock has the left and the right edge of the map. In `layout="overlay"` it goes from edge to edge of the window, with round top corners. The map ends at the top of the dock. With the card look the map goes on under the dock, and the dock is the glass of the panel's card. The panel, the toolbox, its boxes and a bar along the bottom end above the dock, and the camera fits the roads above it. The box with the scale and the credits hides while the dock is open.
    - **The height.** Drag the grip on the top edge. The height is 120 px to 70 % of the window. A double click on the grip closes the dock or opens it again. A closed dock is its title row (32 px). The browser keeps the height and the open state for each page.
    - **The title row.** With one content, the row shows its label. With two or more, it shows tabs. After the label: the content's `note` ("12 rows"), its `actions` (an element: buttons of the content), the arrow that closes or opens the dock, and ✕ for a content with `closable: true`.
    - **A phone.** The dock is a bottom sheet of 40 % of the screen. A tap on its grip goes to the full height and back. A drag down closes it. One sheet is open at a time: when the dock opens, the panel's sheet goes down and Street View and Google 3D close, and when one of them opens, the dock closes. A closed dock is a round button with its label and note.
    - **The calls.** `add({id, label, el, note, actions, closable})`, `open(id)`, `close()`, `show(id)`, `note(id, text)`, `height(px)`, `list()`, `isOpen()` and `remove(id)`. The event `rs:dockchange` (`open`, `id`, `height`) comes when the dock opens, closes, changes its content or changes its height.
    - **The table.** `rs.dock.table({columns, rows, idColumn, more, onSort})` gives `{el, set({columns, rows, more}), rows(), sort()}`: a table in the same look on every page.
        - The box is as wide as its columns and has the height of the dock. Its two scrollbars are always visible. The header row stays at the top, and the first column stays in view when the table scrolls sideways.
        - A header shows the column's name and, under it, its type (`type`). Its tooltip is the column's `about`. A number column is at the right.
        - A 64-bit id (a `BigInt`) shows exactly. `null` shows as a muted "null". A cell is at most 320 px wide. A longer text ends with "…", and the full text is in its tooltip.
        - A click on a header sorts by that column: rising, falling, then the order of the rows again. With `more: true` (the rows are not all the rows) and `onSort(column, dir)`, the host sorts all its rows and gives `{rows}` back.
        - With `idColumn`, a click on a row selects that road and zooms to it.
        - A table of more than 1000 rows draws only the rows in view, so 50 000 rows stay fast.
    - `rs.holdPopup(key, on)` holds the road popup while a part that shows the road's facts is in view (the data dock's road card). The popup comes back when no key holds it. `rs.fade(ids, {opacity})` fades the other roads (`rs.fade(null)` ends it).

### The data dock and Ask { .rs-part }

**Use it for:** SQL on the host's database, with the result in the bottom dock (the data dock), and a question to a model with the person's own key (Ask).<br>
**From Python:** no
{ .rs-facts }

Both need a database of the host, so this page does not show them live: see [The data dock](data-dock.md) and [Ask](ask.md).

## Parts that roadstyle does not have yet { .rs-group }

Until a part comes, make it with the parts above, or ask for it.

| Group | Planned parts |
|---|---|
| Layout | numbered steps with a done mark; "Show more" or paging |
| Inputs | a date range, week or month picker; an hour picker; a slider with its value, and a range slider; a number field with a unit; an on and off toggle; a search field with suggestions; a file drop zone; a menu of actions; a row of icon tools |
| Status | a progress bar and a busy button; a toast; a confirm dialog; a "not saved" dot on a tab; an empty state |

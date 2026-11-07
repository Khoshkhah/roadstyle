# Dashboard parts 2: the controls that pages drew themselves

Status: built, 2026-11-06. Kaveh accepted the looks on 2026-11-06.

## The problem

duckOSM Studio and the duckOSM fixes editor draw some controls themselves: the place search, the file drop, the step cards, the toasts and the
tool rows. A copy of a control in a page does not get the dark theme, the phone layout or the one hover look. Kaveh's rule: a missing dashboard
part is a roadstyle part. This note gives roadstyle the 20 parts that pages need and do not have (17 from Kaveh's list of 2026-11-06, 3 from the duckOSM Studio session, the panel's fixed bar, and 3 from duckOSM's fixes editor).

## The rules for each part

- **Tokens only.** Each colour comes from a token of the theme (`--ink`, `--mut`, `--bg`, `--card`, `--line`, `--accent`, `--accent-fill`,
  `--rs-hover-bg`, `--rs-card-bg`, `--rs-tb-*`, `--rs-pop-*`). Five new tokens, light and dark, in `dashboard.css`: `--rs-warn`, `--rs-ok`,
  `--rs-unsaved` (the amber dot), `--rs-danger-fill` (a red button with white text, 6.5:1) and `--rs-accent-text` (the accent as text on an accent tint:
  the accent mixed with the text colour, 4.5:1 or more). The red text token `--rs-err` is there already. A state edge (the kind of a toast, a step, a pressed
  toggle) is an inner shadow, not a border, as the open card's ring is.
- **The one hover.** A control that is not filled gets `--rs-hover-bg` and the accent. A filled control gets brighter. Focus has a 2 px accent ring.
- **The field look.** A field that opens something (the date range, the colour, the search, the number) has the look of the day picker's field: a
  border, the page's background, and on hover an accent border, an accent tint and a ring.
- **The box look.** A box that opens under a control (the menu, the colour box, the search list, the calendar) has the look of the select list:
  `--rs-card-bg` with blur, round corners, a shadow. It stays inside the window, and goes above the control when there is no room below it.
- **The phone.** On a phone each control is 40 px high or more. The hour grid has 6 columns. A toast goes to the top of the screen (the sheet is at
  the bottom). The confirm dialog is a sheet at the bottom with two 44 px buttons.
- **The keyboard.** Each part works with the keys (see the table).
- **Scope.** The rules are `:is(#sb,body) .rs-…`, so a part works in the panel, in an editor frame, in the dock and in a page of its own.
- **Native first.** A switch is a check box, a slider is the browser's range input, a dialog is the browser's `<dialog>` (it keeps the focus in it,
  and Escape is Cancel), "More…" opens the colour box of `colorpick.js` (PR 67): the dashboard has one colour box, and no browser dialog.

## The parts

| # | Part | How a page uses it | Keys |
|---|---|---|---|
| 1 | Date range, week, month | `rs.days.range(el, {unit: "day" \| "week" \| "month", value: [from, to], min, max, days, onChange})`: the day picker's field and a calendar. "day": the first click sets the first day, the second click the last day; the days between are tinted, the pointer shows the range before the click. "week": a click takes Monday to Sunday ("Week 45 · 2–8 Nov 2026"). "month": a grid of 12 months. ‹ › go to the period before and after. `set`, `value`, `unit(u)` | the calendar's buttons, Escape |
| 2 | Hour picker | `rs.hours.use(el, {value: 8 \| [7, 9], range, hours, onChange})`, in the look of the day picker (Kaveh chose it on 2026-11-06: not a grid of 24 buttons). One hour: "‹ [08:00 – 09:00 🕒 ▾] ›"; a click on the field opens a list of the hours that scrolls to the chosen one, with a tick at it. A range: "From [07:00 ▾] To [10:00 ▾] 3 h", each field with its list; To is the end of the last hour and is later than From. An hour not in `hours` is dimmed in the list | ↓ opens the list; ↓ ↑ Home End walk it, Enter picks, Escape closes |
| 3 | Slider | `rs.slider(el, {label, min, max, step, value, unit, format, onInput, onChange})`. `value: [a, b]` gives two handles; the fill is the chosen part, the value is at the right of the label | the browser's: arrows, Home, End |
| 4 | Number field | `rs.number(el, {label, min, max, step, value, unit, onChange})`: "−", the number, the unit, "+" in one box; a value out of range is set to the nearest limit | arrows (the browser's) |
| 5 | Colour picker | `rs.colorPick(el, {label, value, palette, onChange})`: a field with the swatch and the hex. Its box: the palette (default: the 8 chart colours), a hex field and "More…" (the colour box of `colorpick.js`) | arrows in the palette, Enter in the hex field |
| 6 | On/off switch | `<label class="rs-switch"><input type="checkbox" role="switch"><span>Show bridges</span></label>`: no JavaScript | Space |
| 7 | Search field | `rs.search(el, {placeholder, button, suggest(q), onPick(item), onSubmit(q), onClear})`: the magnifier, the text, "×", an optional filled button at the end; `suggest` gives `{label, sub, value}` rows (or a promise of them), and a ring turns while it waits | ↓ ↑ walk the list, Enter picks or submits, Escape closes, a second Escape clears |
| 8 | File drop zone | `rs.drop(el, {accept, multiple, text, hint, onFiles, onClear})`: a dashed box; a file over it fills it with the accent; after the pick, a row with the name, the size and "×" | Enter or Space opens the file window |
| 9 | Progress and busy | `rs.progress(el, {label, value})` gives `set(fraction \| null, text)`: a label, the value and a bar; `null` moves a part of the bar (no known value). `rs.busy(button, promise)` puts a turning ring before the text and stops the clicks until the promise ends. `<span class="rs-spinner">` is the ring alone | none |
| 10 | Toast and status line | `rs.toast(html, {kind: "info" \| "ok" \| "warn" \| "error", ms, action: {label, onClick}})`: over the middle of the free map, at the bottom; it goes after 4 s (info, ok), 6 s (warn) or 8 s (error); `ms: 0` keeps it. It stays while the pointer is on it. `<div class="rs-status warn">` is the same look in a card, with the icon of the kind | Tab to "×" |
| 11 | Confirm dialog | `await rs.confirm({title, text, ok, cancel, danger})` gives `true` or `false`, in place of the browser's `confirm()`. `danger: true` makes the OK button red, and Enter is then Cancel | Tab, Enter, Escape |
| 12 | Action menu | `rs.menu(button, items)` or `rs.menu.button(items)` (a new "⋯" button). An item is `{label, icon, danger, disabled, onClick}`, and `"-"` is a line | ↓ ↑ Home End, Enter, Escape |
| 13 | Count badge, "not saved" dot | `<span class="rs-badge">12</span>` and `<span class="rs-unsaved" role="img" aria-label="Not saved"></span>` in a tab or a button. On a filled tab or button the badge is white on the fill | none |
| 14 | Steps | `<ol class="rs-steps">` with `<li class="rs-step done \| on \| wait">`, `<span class="rs-step-n">1</span>` and `<div class="rs-step-b"><b>Title</b><p>…</p></div>`. Done: a check mark. On: a filled number and an accent edge. Wait: dimmed, with `<span class="rs-step-note">After step 2</span>` | none (the page puts its own buttons in a step) |
| 15 | Tool row | `<div class="rs-toolrow">` with icon buttons (`data-v`, a `title`); `rs.tabs.use(row, onChange)` makes one of them pressed. A row of toggles uses `aria-pressed` on each button | the arrows (`rs.tabs.use`) |
| 16 | Empty state | `<div class="rs-empty">` with an optional icon, a line (`<b>` for the first words) and an optional button: anywhere, not only in the old side panel | none |
| 17 | Show more | `rs.more(el, {items, page, noun, render})`: the first page of rows, and a line "8 of 134 roads · Show 8 more" | Tab to the button |
| 18 | Selectable rows | `<div class="rs-rows">` with `<button class="rs-row" data-v="12"><span class="rs-row-i">svg</span><b>Title</b><small>A line</small><span class="rs-row-v">2 tags</span></button>`; `rs.tabs.use(list, onChange)` selects one row (no check box). The selected row has the accent tint and an accent bar at its left. For the fixes editor's change list and its wall, door and turn rows | ↓ ↑ (and → ←) walk and select |
| 19 | Toggle button | `rs.toggle(button, onChange)`: a plain button that stays pressed (`aria-pressed`) until the next click; pressed, it has the accent tint, edge and text. It gives `{set(on, quiet), value()}`. For Studio's "What is here?" | Space, Enter |
| 20 | Icon button in a title row | `rs.sections.button(id, {icon, title, onClick})` puts an `rs-icon-btn` after the card's title; its click does not fold or open the card. In a card of the page's own HTML: `<button class="rs-icon-btn">` in the `.rs-card-title`. For Studio's "Zoom to the area" | Tab, Enter |
| 21 | The panel's fixed bar | `rs.panel.bar()` gives a bar at the bottom edge of the normal panel, under the cards and outside the part that scrolls, in the look of the editor frame's bar (Kaveh asked for it on 2026-11-06). Empty, it does not show; while an editor frame is open, the frame's own bar takes its place. On a phone it is at the bottom of the sheet | the keys of its own buttons |
| 22 | A select box in an editor frame | the select box of a form in `rs.frame` has the thin edge of a field, as on a card (the fixes editor asked for it) | as the select box |
| 23 | A field error and a warning | `aria-invalid="true"` on a field gives a red edge; `<p class="rs-field-msg">` (red) or `rs-field-msg warn` (amber) is the line under it, with an icon; empty, it does not show | none |
| 24 | A row with a control | a row of `rs-rows` that holds a select box or a button: `<div class="rs-row" data-v tabindex="0">`; the control is at its end, a click in it does not select the row, Enter or Space selects the row | Enter, Space, ↓ ↑ |

The functions give back an object with `value()` and `set(v, quiet)` where the part has a value. `onChange` does not come for a `set(v, true)`.

## The files

- `dashboard.css`: one block "DASHBOARD PARTS 2" at the end, with the four tokens.
- `days.js`: `rs.days.range` beside `rs.days.use` (the same field and calendar).
- `tabs.js`: `rs.tabs.use` also takes a list of rows (`rs-rows`, with the up and down arrows), and `rs.toggle`.
- `sections.js`: `rs.sections.button`.
- New modules, one line each in `files.txt`: `menu.js` (the action menu, and the three helpers of a box that opens under a control: place,
  close, keys), `hours.js`, `fields.js` (slider, number, colour), `search.js`, `drop.js`, `notice.js` (toast, confirm, progress, busy), `more.js`.
- `api.js`: the functions on `rs`.
- `index.d.ts`, `docs/reference/javascript.md`, `docs/guides/dashboard-manual/javascript.md`, `docs/guides/dashboard-parts.md` and the gallery.

## The tests

- `tests/test_dashboard_parts2_browser.py`: each part in a real dashboard page: the keys, the events, the values, `set(v, true)`, the phone
  layout at 390 px (no part wider than the panel, a control 40 px high or more).
- `tests/test_dashboard_themes_browser.py`: each part in both themes (contrast 4.5 or more, no light surface in the dark theme).
- `tests/test_dashboard_hover_browser.py`: the hover of each new control.
- `tests/test_dashboard_scroll_browser.py` and `_PS_AREAS`: the menu, the colour box and the search list scroll.

## The fixes of the parts that are there (a PR of its own, before this one)

- The looks of the panel's label, select box and plain button move from the dashboard template to `dashboard.css`, so a host page with its own
  panel gets them. A disabled button is dimmed (also a primary one).
- `.rs-sec-box` has its look in the whole panel and in an editor frame. A box in a card has the card's thin edge in place of a fill.
- `.rs-qrow` and `.rs-qmore` use the tokens: before, the line was a fixed light grey, which is near white and looks thicker on the dark panel.
- `rsSetTheme` does not throw on a page with no map.
- The dark theme's title row, while the panel is scrolled: a black shadow did not show on the dark panel. The row is a little lighter, with a
  lighter line and a deeper shadow, so it has the depth of the light theme.

## What is not in this design

- The option rows (`rs-opt`, `rs-opts`, `rs-opts-row`): PR #62.
- Paging from a server (a page that loads the next rows): `rs.more` takes a list in memory. A page with server paging can use the `.rs-more`
  line and its own button.
- A choice of the unit by the person (day, week or month in one control): a page puts an `rs-seg` beside the field and calls `unit(u)`.

## The gaps of 2026-11-07

duckOSM Studio used the parts and found six gaps. Each is closed with a small option, and none changes a part that was in use.

1. `rs.search(el, {end: button})`: an element that goes inside `.rs-search-box`, after the clear button and before the end button `button`. It has the look of the clear button.
2. `rs.number`: the option `disabled` and the handle's `disabled(on)` switch off the input and both buttons. `set()` and the limits use one function, so they do not switch the buttons on again while the field is off.
3. `.rs-status:empty{display:none}`, as `.rs-field-msg:empty` has.
4. `rs.sections.add({step: 3})` puts a round badge (`rs-sec-n`) before the title. `rs.sections.done(id, on)` sets `data-rs-done` on the card: the badge shows a check mark in place of the number, as `rs-step.done` does. A card with no `step` gets the mark alone.
5. `rs.mapBusy(text)` and `rs.mapBusy(null)` (`notice.js`): `#rs-mapbusy` is a fixed veil that the script puts on `rs.freeArea()` (a `ResizeObserver` on the panel, the bar and the side box follows them). The veil is `--bg` at 40 % through `color-mix` (no `rgba`), the pill uses `--rs-pop-bg` and `--rs-pop-ink`, and the pointer goes through it.
6. `rs.number`: the option `snap`. **The default stays `true`**: a typed value goes to the nearest `step`, as before, so no page that uses the field changes. `snap: false` keeps the typed value and the buttons add or take one `step`. The note says only that a value out of range goes to the nearest limit, and it says nothing of rounding, so the new option is a choice of the page and not a new rule.

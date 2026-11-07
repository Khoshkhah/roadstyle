"""The dashboard parts of docs/design/dashboard_parts_2.md in a real dashboard page: the date range, the hour picker, the slider, the number field, the
colour picker, the switch, the search field, the file drop zone, the progress bar and the busy button, the toast, the confirm dialog, the action menu,
the badge, the steps, the tool row, the empty state, "show more", the rows that a click selects, the toggle button, the icon button of a title row
and the panel's fixed bar. Each with its keys and its values, and at phone width. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

_HTML = """<div id="range"></div><div id="week"></div><div id="month"></div><div id="hour"></div><div id="hours"></div><div id="sl"></div><div id="sl2"></div>
<div id="num"></div><div id="col"></div><label class="rs-switch"><input type="checkbox" role="switch" id="sw"><span>Show bridges</span></label>
<div id="q"></div><div id="drop"></div><div id="prog"></div><button type="button" id="busy">Load</button><button type="button" id="dots">Open</button>
<nav class="rs-tabs"><button class="rs-tab on" data-tab="a">Fixes<span class="rs-badge">12</span></button><button class="rs-tab" data-tab="b">Tags<span class="rs-unsaved" role="img" aria-label="Not saved"></span></button></nav>
<ol class="rs-steps"><li class="rs-step done"><span class="rs-step-n">1</span><div class="rs-step-b"><b>Area</b><p>Monaco</p></div></li>
<li class="rs-step on"><span class="rs-step-n">2</span><div class="rs-step-b"><b>Build</b></div></li><li class="rs-step wait"><span class="rs-step-n">3</span><div class="rs-step-b"><b>Edit</b><span class="rs-step-note">After step 2</span></div></li></ol>
<div class="rs-toolrow" id="tools"><button data-v="pan" aria-label="Move">M</button><button data-v="pen" aria-label="Draw">D</button></div>
<div class="rs-empty"><span><b>No fixes yet.</b> Click a road.</span><button type="button">Add a fix</button></div><div id="more"></div>
<div class="rs-rows" id="rows"><button class="rs-row" data-v="1"><b>Wall</b><small>barrier=wall</small><span class="rs-row-v">new</span></button>
<button class="rs-row" data-v="2"><b>Door</b><small>entrance=yes</small></button></div><button type="button" id="tog">What is here?</button>
<div class="rs-status warn">3 fixes are not saved.</div>
<div class="rs-rows" id="rows2"><div class="rs-row" data-v="w1" tabindex="0"><b>Wall 1</b><small>42 m</small><select><option>wall</option><option>door</option></select></div>
<div class="rs-row" data-v="w2" tabindex="0"><b>Wall 2</b><small>12 m</small><select><option>wall</option></select></div></div>
<div id="q2"></div><button type="button" id="endb" aria-label="What is here?">?</button><div id="num2"></div><div id="num3"></div><div class="rs-status" id="st"></div>
<input id="bad" aria-invalid="true" value="0"><p class="rs-field-msg" id="bad-msg">Lanes is 1 or more.</p><p class="rs-field-msg warn" id="warn-msg">A speed in km/h.</p>"""
_SETUP = """() => { window.got = {}; const $ = id => document.getElementById(id), log = k => v => { (got[k] = got[k] || []).push(v); };
  window.P = {
    range: rs.days.range($('range'), {days: ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08'], value: ['2026-10-05', '2026-10-06'], onChange: log('range')}),
    week: rs.days.range($('week'), {unit: 'week', min: '2026-09-01', max: '2026-11-06', onChange: log('week')}),
    month: rs.days.range($('month'), {unit: 'month', min: '2026-01-01', max: '2026-11-06', onChange: log('month')}),
    hour: rs.hours.use($('hour'), {value: 8, hours: [6, 7, 8, 10, 11], onChange: log('hour')}),
    hours: rs.hours.use($('hours'), {value: [7, 9], range: true, onChange: log('hours')}),
    sl: rs.slider($('sl'), {label: 'Speed', min: 0, max: 130, step: 10, value: 50, unit: 'km/h', onChange: log('sl')}),
    sl2: rs.slider($('sl2'), {label: 'Flow', min: 0, max: 100, value: [20, 60], onChange: log('sl2')}),
    num: rs.number($('num'), {label: 'Lanes', min: 1, max: 3, value: 2, onChange: log('num')}),
    col: rs.colorPick($('col'), {label: 'Fill', value: '#0e7f91', palette: ['#0e7f91', '#eb6834', '#2a78d6'], onChange: log('col')}),
    q: rs.search($('q'), {placeholder: 'Find a place', button: 'Go', suggest: t => ['Monaco', 'Monte Carlo', 'Tartu'].filter(n => n.toLowerCase().startsWith(t.toLowerCase())).map(n => ({label: n, sub: 'x', value: n})),
                          onPick: it => log('pick')(it.value), onSubmit: log('submit')}),
    drop: rs.drop($('drop'), {accept: '.pbf', onFiles: f => log('files')(f.map(x => x.name)), onClear: log('clear')}),
    prog: rs.progress($('prog'), {label: 'Build', value: 0.25}),
    menu: rs.menu($('dots'), [{label: 'Edit', onClick: () => log('menu')('edit')}, {label: 'Export', disabled: true}, '-', {label: 'Delete', danger: true, onClick: () => log('menu')('delete')}]),
    more: rs.more($('more'), {items: Array.from({length: 23}, (_, i) => 'Road ' + i), page: 10, noun: 'roads', render: r => '<div class="rs-qrow"><b>' + r + '</b></div>'}),
    tog: rs.toggle($('tog'), log('tog')),
  };
  rs.tabs.use($('tools'), log('tools')); rs.tabs.use($('rows'), log('rows')); rs.tabs.use($('rows2'), log('rows2'));
}"""


@pytest.fixture(scope="module")
def page_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("parts2") / "p.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}},
                        dashboard={"panel": {"sections": [{"id": "parts", "label": "Parts", "html": _HTML}, {"id": "zoom", "label": "Area", "fold": True, "html": "<p>Monaco</p>"}]}}).save(path)
    return path


@pytest.fixture
def page(page_path):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        pg = browser.new_page(viewport={"width": 1280, "height": 1000})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(page_path.resolve().as_uri())
        pg.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        pg.evaluate(_SETUP)
        yield pg
        browser.close()
        assert errors == []


def _got(page, key):
    return page.evaluate(f"got[{key!r}] || []")


def test_the_date_range_a_week_and_a_month(page):
    assert page.inner_text("#range .rs-day-text") == "5–6 Oct 2026"
    page.click("#range .rs-day-step[data-step='1']")                   # the next 2 days
    assert page.evaluate("P.range.value()") == ["2026-10-07", "2026-10-08"]
    page.click("#range .rs-day-field")
    assert page.locator(".rs-range-cal:not([hidden]) .rs-day-cd[data-d='2026-10-03']").is_disabled()    # a day with no data
    page.click(".rs-range-cal:not([hidden]) [data-d='2026-10-02']")
    page.click(".rs-range-cal:not([hidden]) [data-d='2026-10-06']")
    assert page.evaluate("P.range.value()") == ["2026-10-02", "2026-10-06"] and page.locator(".rs-range-cal:not([hidden])").count() == 0
    assert page.inner_text("#week .rs-day-text").startswith("Week 45 · 2–8 Nov")
    page.click("#week .rs-day-step[data-step='-1']")
    assert page.evaluate("P.week.value()") == ["2026-10-26", "2026-11-01"]
    assert page.inner_text("#month .rs-day-text") == "November 2026" and page.locator("#month .rs-day-step[data-step='1']").is_disabled()
    page.evaluate("P.month.set(['2026-03-15'], true)")
    assert page.evaluate("P.month.value()") == ["2026-03-01", "2026-03-31"]
    assert len(_got(page, "range")) == 2 and len(_got(page, "week")) == 1 and _got(page, "month") == []      # a quiet set calls no onChange


def test_the_hour_picker_one_hour_and_a_range(page):
    assert page.inner_text("#hour .rs-day-text") == "08:00 – 09:00"
    page.click("#hour .rs-day-step[data-step='1']")                    # the next hour that can be chosen: 10
    assert page.evaluate("P.hour.value()") == 10
    page.click("#hour .rs-hours-field")
    lst = ".rs-hours-list:not([hidden])"
    assert page.locator(f"{lst} [data-v='9']").is_disabled() and page.locator(f"{lst} .rs-menu-item.on").inner_text().startswith("10:00")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.evaluate("P.hour.value()") == 11 and page.locator(lst).count() == 0
    assert [page.inner_text(s) for s in ("#hours .rs-hours-field >> nth=0", "#hours .rs-hours-field >> nth=1", "#hours .rs-hours-n")] == ["07:00", "10:00", "3 h"]
    page.click("#hours .rs-hours-field >> nth=1")
    assert page.locator(f"{lst} [data-v='6']").is_disabled()            # To is later than From
    page.click(f"{lst} [data-v='11']")
    page.click("#hours .rs-hours-field >> nth=0")
    page.click(f"{lst} [data-v='13']")                                  # a From after To: To moves with it
    assert page.evaluate("P.hours.value()") == [13, 13] and _got(page, "hours") == [[7, 11], [13, 13]]


def test_the_slider_the_number_and_the_colour(page):
    assert page.inner_text("#sl .rs-slider-v") == "50 km/h"
    page.focus("#sl input")
    page.keyboard.press("ArrowRight")
    assert page.inner_text("#sl .rs-slider-v") == "60 km/h" and _got(page, "sl") == [60]
    page.evaluate("const [a, b] = document.querySelectorAll('#sl2 input'); a.value = 80; a.dispatchEvent(new Event('input'))")
    assert page.evaluate("P.sl2.value()") == [60, 60]                    # the handles do not cross
    page.click("#num .rs-num-st[data-d='1']")
    assert page.evaluate("P.num.value()") == 3 and page.locator("#num .rs-num-st[data-d='1']").is_disabled()
    page.fill("#num input", "9")
    page.keyboard.press("Tab")
    assert page.evaluate("P.num.value()") == 3 and page.input_value("#num input") == "3"    # out of range: the nearest limit
    page.click("#col .rs-color-btn")
    page.click(".rs-color-box:not([hidden]) [data-c='#eb6834']")
    assert page.evaluate("P.col.value()") == "#eb6834" and page.inner_text("#col .rs-color-hex") == "#eb6834"
    page.click("#col .rs-color-btn")
    page.fill(".rs-color-box:not([hidden]) .rs-color-in", "#12")
    assert page.evaluate("P.col.value()") == "#eb6834"                  # not a colour: no change
    page.fill(".rs-color-box:not([hidden]) .rs-color-in", "#123456")
    assert _got(page, "col") == ["#eb6834", "#123456"]
    # "More…" opens the one colour box of colorpick.js at the field (no browser dialog), and its hex field sets the value
    assert page.locator(".rs-color-box input[type=color]").count() == 0
    page.click(".rs-color-box:not([hidden]) .rs-color-more")
    assert page.locator(".rs-color-box:not([hidden])").count() == 0 and page.locator(".rs-cp-box").count() == 1
    assert page.evaluate("document.querySelector('#col .rs-cp-btn').offsetParent") is None     # its own swatch is not shown
    box, btn = page.locator(".rs-cp-box").bounding_box(), page.locator("#col .rs-color-btn").bounding_box()
    assert abs(box["y"] - (btn["y"] + btn["height"] + 6)) < 2 or abs(box["y"] + box["height"] + 6 - btn["y"]) < 2   # at the field, not at 0, 0
    page.fill(".rs-cp-box .rs-cp-hex", "#2a78d6")
    assert page.evaluate("P.col.value()") == "#2a78d6" and page.inner_text("#col .rs-color-hex") == "#2a78d6"
    page.keyboard.press("Escape")                                        # back to the colour before the box opened
    assert page.locator(".rs-cp-box").count() == 0 and page.evaluate("P.col.value()") == "#123456"
    assert page.evaluate("document.activeElement.classList.contains('rs-color-btn')")


def test_the_switch_and_the_search(page):
    page.click("label.rs-switch")
    assert page.evaluate("document.getElementById('sw').checked")
    assert page.evaluate("getComputedStyle(document.getElementById('sw')).width") == "34px"
    page.click("#q input")
    page.keyboard.type("mo")
    page.wait_for_selector(".rs-search-list:not([hidden]) .rs-search-opt")
    assert page.locator(".rs-search-list:not([hidden]) .rs-search-opt").count() == 2
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert _got(page, "pick") == ["Monte Carlo"] and page.input_value("#q input") == "Monte Carlo"
    page.keyboard.press("Escape")                                       # no list: the text goes
    assert page.input_value("#q input") == ""
    page.keyboard.type("zz")
    page.wait_for_selector(".rs-search-list:not([hidden]) .rs-search-note")
    page.click("#q .rs-search-go")
    assert _got(page, "submit") == ["zz"]


def test_the_six_gaps_that_duckosm_studio_found(page):
    """PR parts-gaps: an end button in the search field, a number field that is off, an empty status line, the step and done mark of a card, the veil of a busy
    map, and a number field that keeps a typed value."""
    # 1. rs.search `end`: a button inside the field, after the clear button and before the end button; its click does not submit
    page.evaluate("""() => { const $ = id => document.getElementById(id);
      window.E = rs.toggle($('endb'), v => { (got.end = got.end || []).push(v); });
      P.q2 = rs.search($('q2'), {placeholder: 'Find', button: 'Go', end: $('endb'), onSubmit: v => { (got.submit2 = got.submit2 || []).push(v); }});
      try { rs.search(document.createElement('div'), {end: 'x'}); } catch(e) { window.endErr = String(e); } }""")
    kids = page.evaluate("[...document.querySelector('#q2 .rs-search-box').children].map(e => e.id || e.className.split(' ')[0] || e.tagName)")
    assert kids == ["rs-search-i", "INPUT", "rs-search-x", "endb", "rs-search-go"], kids
    box, end = page.locator("#q2 .rs-search-box").bounding_box(), page.locator("#endb").bounding_box()
    assert box["x"] < end["x"] and end["x"] + end["width"] < box["x"] + box["width"] and 24 <= end["height"] <= 40     # inside the field, an icon button
    page.click("#endb")
    assert page.get_attribute("#endb", "aria-pressed") == "true" and _got(page, "end") == [True] and _got(page, "submit2") == []
    assert "end is an element" in page.evaluate("window.endErr")
    # 2. rs.number `disabled`: the box and both buttons; set() does not turn the buttons on again
    page.evaluate("""() => { const $ = id => document.getElementById(id);
      P.num2 = rs.number($('num2'), {label: 'Buffer', min: 0, max: 500, step: 50, value: 100, unit: 'm', disabled: true, onChange: v => { (got.num2 = got.num2 || []).push(v); }});
      P.num3 = rs.number($('num3'), {label: 'Buffer', min: 0, max: 500, step: 50, value: 100, snap: false, onChange: v => { (got.num3 = got.num3 || []).push(v); }}); }""")
    assert page.evaluate("[...document.querySelectorAll('#num2 input, #num2 button')].every(e => e.disabled)")
    page.evaluate("P.num2.set(200, true)")
    assert page.evaluate("[...document.querySelectorAll('#num2 input, #num2 button')].every(e => e.disabled)") and page.input_value("#num2 input") == "200"
    page.evaluate("P.num2.disabled(false)")
    assert page.evaluate("[...document.querySelectorAll('#num2 input, #num2 button')].every(e => !e.disabled)")
    page.evaluate("P.num2.set(500, true)")
    assert page.locator("#num2 .rs-num-st[data-d='1']").is_disabled() and page.locator("#num2 .rs-num-st[data-d='-1']").is_enabled()    # the limit still turns a button off
    page.evaluate("P.num2.disabled(true)")
    assert page.evaluate("[...document.querySelectorAll('#num2 .rs-num-st')].every(e => e.disabled)")
    assert float(page.evaluate("getComputedStyle(document.querySelector('#num2 .rs-num-box')).opacity")) < 1     # it looks off
    # 6. `snap`: the default rounds a typed value to the step; `snap: false` keeps it, and the buttons still add and take one step
    page.evaluate("P.num2.disabled(false)")
    page.evaluate("P.num2.set(0, true)")
    page.fill("#num2 input", "120")
    page.keyboard.press("Tab")
    assert page.evaluate("P.num2.value()") == 100 and page.input_value("#num2 input") == "100"       # default: snap
    page.fill("#num3 input", "120")
    page.keyboard.press("Tab")
    assert page.evaluate("P.num3.value()") == 120 and page.input_value("#num3 input") == "120" and _got(page, "num3") == [120]
    page.click("#num3 .rs-num-st[data-d='1']")
    assert page.evaluate("P.num3.value()") == 170
    page.fill("#num3 input", "9999")
    page.keyboard.press("Tab")
    assert page.evaluate("P.num3.value()") == 500                                                  # a limit still holds
    # 3. an empty status line does not show; one with text does
    assert page.evaluate("getComputedStyle(document.getElementById('st')).display") == "none"
    page.evaluate("document.getElementById('st').textContent = 'Reading the area.'")
    assert page.evaluate("getComputedStyle(document.getElementById('st')).display") == "flex"
    page.evaluate("document.getElementById('st').textContent = ''")
    assert page.evaluate("getComputedStyle(document.getElementById('st')).display") == "none"
    # 4. a card with a step: the number before the title, a check mark in place of it after done()
    page.evaluate("""() => { rs.sections.add({id: 'draw', label: 'Draw the area', step: 3, html: '<p>x</p>'}); rs.sections.add({id: 'plain', label: 'No step', html: '<p>y</p>'});
      try { rs.sections.add({id: 'nolabel', step: 1, html: 'z'}); } catch(e) { window.stepErr = String(e); } }""")
    assert "needs a label" in page.evaluate("window.stepErr") and page.evaluate("rs.sections.get('nolabel')") is None
    badge = "[data-rs-section=draw] > .rs-sec-hd > .rs-sec-n"
    assert page.inner_text(badge) == "3" and page.get_attribute(badge, "aria-label") == "Step 3"
    assert page.evaluate(f"document.querySelector('{badge}').nextElementSibling.classList.contains('rs-sec-title')")        # before the title
    assert page.evaluate(f"getComputedStyle(document.querySelector('{badge}')).fontSize") != "0px"
    page.evaluate("rs.sections.done('draw', true)")
    assert page.evaluate("rs.sections.get('draw').dataset.rsDone") == "1" and page.get_attribute(badge, "aria-label") == "Step 3, done"
    assert page.evaluate(f"getComputedStyle(document.querySelector('{badge}')).fontSize") == "0px"                      # the check mark is drawn in place of the number
    assert page.evaluate(f"getComputedStyle(document.querySelector('{badge}'), '::after').content") == '""'
    page.evaluate("rs.sections.done('draw', false)")
    assert page.evaluate("rs.sections.get('draw').dataset.rsDone") is None and page.get_attribute(badge, "aria-label") == "Step 3"
    page.evaluate("rs.sections.done('plain')")                                                         # a card with no step gets the mark alone
    assert page.locator("[data-rs-section=plain] > .rs-sec-hd > .rs-sec-n").count() == 1
    # 5. rs.mapBusy: a veil over the free part of the map, the pointer goes through it; null takes it away
    page.evaluate("rs.mapBusy('Reading the roads…')")
    def veil():
        return page.evaluate("""() => { const e = document.getElementById('rs-mapbusy'), r = e.getBoundingClientRect(), f = rs.freeArea();
          return {hidden: e.hidden, text: e.innerText, lo: Math.abs(r.left - f.lo), hi: Math.abs(r.right - f.hi), top: Math.abs(r.top - f.top), bottom: Math.abs(r.bottom - f.bottom),
                  ring: getComputedStyle(e.querySelector('.rs-mapbusy-pill'), '::before').animationName === 'rs-spin', role: e.getAttribute('role'),
                  through: document.elementFromPoint((f.lo + f.hi) / 2, (f.top + f.bottom) / 2).closest('#rs-mapbusy') === null}; }""")
    v = veil()
    assert not v["hidden"] and v["text"] == "Reading the roads…" and v["ring"] and v["role"] == "status" and v["through"]
    assert max(v["lo"], v["hi"], v["top"], v["bottom"]) < 1.5, v
    page.evaluate("rs.mapBusy('Building…')")
    assert page.inner_text("#rs-mapbusy .rs-mapbusy-t") == "Building…" and page.locator("#rs-mapbusy").count() == 1
    page.click("#sb-hide")                                                                              # the panel goes: the veil follows
    page.wait_for_timeout(300)
    v = veil()
    assert max(v["lo"], v["hi"], v["top"], v["bottom"]) < 1.5, v
    page.evaluate("rs.mapBusy(null)")
    assert veil()["hidden"]


def test_the_drop_zone_the_progress_and_the_busy_button(page, tmp_path):
    f = tmp_path / "monaco.osm.pbf"
    f.write_bytes(b"x" * 2048)
    page.set_input_files("#drop input[type=file]", str(f))
    assert _got(page, "files") == [["monaco.osm.pbf"]] and page.inner_text("#drop .rs-drop-file").startswith("monaco.osm.pbf")
    assert "2 KB" in page.inner_text("#drop .rs-drop-file")
    page.click("#drop .rs-drop-x")
    assert page.locator("#drop .rs-drop-files").is_hidden() and len(_got(page, "clear")) == 1
    assert page.inner_text("#prog .rs-progress-v") == "25 %" and page.get_attribute("#prog [role=progressbar]", "aria-valuenow") == "25"
    page.evaluate("P.prog.set(null)")
    assert page.evaluate("document.getElementById('prog').classList.contains('rs-progress-wait')")
    page.evaluate("() => { rs.busy(document.getElementById('busy'), new Promise(ok => setTimeout(ok, 300))); }")       # no promise back: evaluate would wait for it
    assert page.locator("#busy").is_disabled() and page.get_attribute("#busy", "aria-busy") == "true"
    page.wait_for_function("!document.getElementById('busy').disabled")


def test_the_toast_and_the_confirm_dialog(page):
    page.evaluate("rs.toast('Saved.', {kind: 'ok', ms: 300}); rs.toast('Stopped.', {kind: 'error', ms: 0})")
    assert page.locator("#rs-toasts .rs-toast.ok[role=status]").count() == 1 and page.locator("#rs-toasts .rs-toast.error[role=alert]").count() == 1
    page.wait_for_timeout(700)
    assert page.locator("#rs-toasts .rs-toast").count() == 1            # ms: 0 stays until it is closed
    page.click("#rs-toasts .rs-toast-x")
    page.wait_for_timeout(300)
    assert page.locator("#rs-toasts .rs-toast").count() == 0
    page.evaluate("() => { rs.confirm({title: 'Delete 3 fixes?', ok: 'Delete', danger: true}).then(a => { window.answer = a; }); }")
    assert page.evaluate("document.activeElement.textContent") == "Cancel"      # Enter is never the danger action
    page.keyboard.press("Escape")
    page.wait_for_function("window.answer !== undefined")
    assert page.evaluate("window.answer") is False
    page.evaluate("delete window.answer")
    page.evaluate("() => { rs.confirm({title: 'Build?', ok: 'Build'}).then(a => { window.answer = a; }); }")
    page.click(".rs-dialog .sb-primary")
    page.wait_for_function("window.answer !== undefined")
    assert page.evaluate("window.answer") is True and page.locator(".rs-dialog").count() == 0


def test_the_menu_the_tool_row_the_rows_and_the_toggle(page):
    page.click("#dots")
    assert page.get_attribute("#dots", "aria-expanded") == "true"
    page.keyboard.press("ArrowDown")                                    # Export is disabled: the walk goes past it
    page.keyboard.press("Enter")
    assert _got(page, "menu") == ["delete"] and page.evaluate("document.activeElement.id") == "dots"
    b = page.evaluate("(() => { const b = rs.menu.button([{label: 'A'}]); document.body.append(b); return [b.className, b.getAttribute('aria-haspopup')]; })()")
    assert b == ["rs-more-btn", "menu"]
    page.click("#tools [data-v=pen]")
    page.keyboard.press("ArrowLeft")
    assert _got(page, "tools") == ["pen", "pan"]
    assert page.locator("#rows [aria-selected=true]").count() == 0      # a list starts with no row selected
    page.focus("#rows [data-v='1']")
    page.keyboard.press("ArrowDown")
    assert _got(page, "rows") == ["1"]                                   # no row selected: the first arrow selects the first row
    page.click("#rows [data-v='1']")
    assert page.get_attribute("#rows [data-v='1']", "aria-selected") == "true"
    page.click("#tog")
    page.click("#tog")
    assert _got(page, "tog") == [True, False] and page.get_attribute("#tog", "aria-pressed") == "false"


def test_show_more_the_icon_button_and_the_fixed_bar(page):
    assert page.locator("#more .rs-qrow").count() == 10 and page.inner_text("#more .rs-more-n") == "10 of 23 roads"
    page.click("#more .rs-more-b")
    page.click("#more .rs-more-b")
    assert page.locator("#more .rs-qrow").count() == 23 and page.inner_text("#more .rs-more-n") == "All 23 roads" and page.locator("#more .rs-more-b").count() == 0
    page.evaluate("window.zoomed = 0; rs.sections.button('zoom', {icon: '<svg></svg>', title: 'Zoom to the area', onClick: () => zoomed++})")
    folded = page.evaluate("rs.sections.get('zoom').classList.contains('folded')")
    page.click("[data-rs-section=zoom] .rs-sec-hd .rs-icon-btn")
    assert page.evaluate("zoomed") == 1 and page.evaluate("rs.sections.get('zoom').classList.contains('folded')") == folded   # the card does not fold
    bar = page.evaluate("""(() => { const b = rs.panel.bar(); const empty = getComputedStyle(b).display; b.innerHTML = '<span>3 fixes</span><button>Build</button>';
      const r = b.getBoundingClientRect(), body = document.querySelector('#sb .sb-body').getBoundingClientRect(), sb = document.getElementById('sb').getBoundingClientRect();
      return {empty, same: rs.panel.bar() === b, under: r.top >= body.bottom - 1, bottom: sb.bottom - r.bottom}; })()""")
    assert bar["empty"] == "none" and bar["same"] and bar["under"] and bar["bottom"] < 20, bar
    page.evaluate("const f = rs.frame({panel: document.getElementById('sb'), title: 'Edit', back: 'Steps'}); f.bar.textContent = 'x'; f.open()")
    assert page.locator("#sb .rs-panel-bar").is_hidden()                 # the frame's own bar is there


def test_a_field_error_rows_with_a_select_box_and_a_select_box_in_a_frame(page):
    out = page.evaluate("""() => { const err = getComputedStyle(document.getElementById('sb')).getPropertyValue('--rs-err').trim(), t = document.createElement('i');
      t.style.color = err; document.body.append(t); const want = getComputedStyle(t).color; t.remove();
      return {edge: getComputedStyle(document.getElementById('bad')).borderTopColor, want, msg: getComputedStyle(document.getElementById('bad-msg')).color,
              warn: getComputedStyle(document.getElementById('warn-msg')).color}; }""")
    assert out["edge"] == out["want"] and out["msg"] == out["want"] and out["warn"] != out["want"], out
    page.click("#rows2 [data-v=w1] .rs-sel-btn")                        # a control in a row does its own work: the row is not selected
    page.keyboard.press("Escape")
    assert _got(page, "rows2") == []
    page.focus("#rows2 [data-v=w2]")
    page.keyboard.press("Enter")
    page.click("#rows2 [data-v=w1] small")
    assert _got(page, "rows2") == ["w2", "w1"] and page.get_attribute("#rows2 [data-v=w1]", "aria-selected") == "true"
    edge = page.evaluate("""() => { const f = rs.frame({panel: document.getElementById('sb'), title: 'Edit', back: 'Steps', id: 'fx'});
      f.body.innerHTML = '<select><option>primary</option><option>secondary</option></select>'; f.open();
      return new Promise(ok => setTimeout(() => ok(getComputedStyle(f.body.querySelector('.rs-sel-btn')).borderTopWidth), 100)); }""")
    assert edge == "1px"                                                 # a select box in a frame has the edge of a field


def test_the_parts_fit_a_phone(page_path):
    """390 px: no part is wider than the panel, and each control that a finger hits is 40 px high or more."""
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        pg = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(page_path.resolve().as_uri())
        pg.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        pg.evaluate(_SETUP)
        pg.evaluate("rs.sheet(2)")
        pg.wait_for_timeout(300)
        out = pg.evaluate("""() => {
          const body = document.querySelector('#sb .sb-body').getBoundingClientRect();
          const wide = [...document.querySelectorAll('[data-rs-section=parts] .rs-sec-body > *')].filter(e => e.getBoundingClientRect().right > body.right + 0.5).map(e => e.id || e.className);
          const small = [...document.querySelectorAll('#range .rs-day-field, #hour .rs-hours-field, #hours .rs-hours-field, #hour .rs-day-step, #num .rs-num-box, #col .rs-color-btn, #q .rs-search-box, #tools button, .rs-more-btn')]
            .filter(e => e.getBoundingClientRect().height < 40).map(e => e.className + ' ' + Math.round(e.getBoundingClientRect().height));
          return {wide, small, page: document.documentElement.scrollWidth - innerWidth}; }""")
        pg.evaluate("rs.toast('On a phone.')")
        top = pg.evaluate("document.querySelector('#rs-toasts').getBoundingClientRect().top")
        browser.close()
    assert errors == []
    assert out["wide"] == [] and out["small"] == [] and out["page"] <= 0, out
    assert top < 100                                                     # a toast is at the top of a phone: the sheet is at the bottom

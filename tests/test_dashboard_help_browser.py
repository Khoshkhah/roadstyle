"""The help window of a page (`rs.help`): the "i" button in the panel's title, the window that it opens, and the two ways to close it. The window takes
the colours of the page's theme (the card token), in the light and in the dark theme. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402

_HELP = {"title": "How to read this page", "intro": "A <b>bold</b> word.", "terms": [["Term one", "Its text."], ["Term two", "More text."]], "note": "A note."}


def _run(tmp_path, body):
    path = tmp_path / "h.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.evaluate("h => rs.help.set(h)", _HELP)
            body(page)
        finally:
            browser.close()
    assert errors == []


def test_the_button_opens_the_window_and_both_ways_close_it(tmp_path):
    def body(page):
        assert page.locator("#sb .sb-top h2 #rs-help-btn").count() == 1
        assert page.locator("#rs-help").is_hidden()
        page.click("#rs-help-btn")
        assert page.locator("#rs-help").is_visible()
        assert page.locator("#rs-help .rs-help-terms dt").count() == 2
        page.keyboard.press("Escape")
        assert page.locator("#rs-help").is_hidden()
        page.click("#rs-help-btn")
        page.click("#rs-help .rs-help-x")
        assert page.locator("#rs-help").is_hidden()
    _run(tmp_path, body)


def test_the_window_follows_the_theme(tmp_path):
    def body(page):
        page.click("#rs-help-btn")
        def bg():
            return page.evaluate("getComputedStyle(document.querySelector('#rs-help .rs-help-box')).backgroundColor")
        light = bg()
        page.evaluate("document.documentElement.setAttribute('data-rs-theme', 'dark')")
        page.wait_for_timeout(300)
        assert bg() != light
    _run(tmp_path, body)


def test_set_again_replaces_the_words(tmp_path):
    def body(page):
        page.evaluate("rs.help.set({title: 'Second', terms: []})")
        page.evaluate("rs.help.open()")
        assert page.locator("#rs-help .rs-help-ttl").inner_text() == "Second"
        assert page.locator("#sb #rs-help-btn").count() == 1
    _run(tmp_path, body)


def test_the_attribution_names_the_map_data_and_blurs_the_map(tmp_path):
    def body(page):
        page.click("[data-rs-tool=attribution]")
        rows = page.locator("#rs-attr-box .rs-attr-row").all_inner_texts()
        assert any("OpenStreetMap" in r for r in rows) and any("MapLibre" in r for r in rows), rows
        # the glass: no ancestor of the box has a backdrop filter of its own (it would stop the blur short of the map)
        blurred = page.evaluate("""() => { const out = []; for(let e = document.getElementById('rs-attr-box').parentElement; e && e !== document.documentElement; e = e.parentElement)
                                          if(getComputedStyle(e).backdropFilter !== 'none') out.push(e.id || e.className); return out; }""")
        assert blurred == [], blurred
        assert page.evaluate("getComputedStyle(document.getElementById('rs-attr-box')).backdropFilter") == "blur(6px)"
    _run(tmp_path, body)


def test_the_hover_box_follows_the_pointer_and_stays_in_the_page(tmp_path):
    def body(page):
        page.evaluate("rs.hover.show('<b>Hello</b>', {clientX: 20, clientY: 20})")
        box = page.locator("#rs-hover")
        assert box.is_visible() and box.inner_text() == "Hello"
        r = box.bounding_box()
        assert r["x"] >= 8 and r["y"] >= 8
        page.evaluate("rs.hover.show('Near the corner', {clientX: innerWidth - 4, clientY: innerHeight - 4})")
        r = box.bounding_box()
        assert r["x"] + r["width"] <= 1280 and r["y"] + r["height"] <= 800        # flipped to the other side
        page.evaluate("rs.hover.hide()")
        assert box.is_hidden()
        assert page.evaluate("getComputedStyle(document.getElementById('rs-hover')).pointerEvents") == "none"
    _run(tmp_path, body)


def test_a_scroll_area_keeps_its_header_and_marks_more_below(tmp_path):
    def body(page):
        page.evaluate("""() => { const d = document.createElement('div'); d.className = 'rs-scroll'; d.id = 't'; d.style.setProperty('--rs-scroll-h', '120px');
            d.innerHTML = '<table class="rs-table"><thead><tr><th data-sort="asc">A</th><th>B</th></tr></thead><tbody>' + Array.from({length: 40}, (_, i) => '<tr><td>r' + i + '</td><td>' + i + '</td></tr>').join('') + '</tbody></table>';
            document.querySelector('#sb .sb-body').appendChild(d); }""")
        page.wait_for_function("document.getElementById('t').dataset.rsScroll === '1'")
        assert page.evaluate("document.getElementById('t').hasAttribute('data-more')")
        assert page.evaluate("document.getElementById('t').getBoundingClientRect().height") <= 121
        page.evaluate("document.getElementById('t').scrollTop = 99999")
        page.wait_for_timeout(200)
        assert not page.evaluate("document.getElementById('t').hasAttribute('data-more')")
        assert page.evaluate("getComputedStyle(document.querySelector('#t th')).position") == "sticky"
        assert page.evaluate("getComputedStyle(document.getElementById('t')).overscrollBehaviorY") == "contain"
    _run(tmp_path, body)


def test_tabs_select_by_click_and_arrow_and_the_switch_has_no_panes(tmp_path):
    def body(page):
        page.evaluate("""() => { const d = document.createElement('div'); d.id = 'w';
            d.innerHTML = '<nav class="rs-tabs" id="tb"><button class="rs-tab on" data-tab="a">A</button><button class="rs-tab" data-tab="b">B</button></nav>'
              + '<div data-pane="a">pane a</div><div data-pane="b" hidden>pane b</div>'
              + '<div class="rs-seg" id="sg"><button class="on" data-v="x">X</button><button data-v="y">Y</button></div>';
            document.querySelector('#sb .sb-body').appendChild(d);
            window.seen = []; window.T = rs.tabs.use(document.getElementById('tb'), id => seen.push('t' + id)); rs.tabs.use(document.getElementById('sg'), v => seen.push('s' + v)); }""")
        assert page.locator("[data-pane=a]").is_visible() and page.locator("[data-pane=b]").is_hidden()
        page.click("[data-tab=b]")
        assert page.locator("[data-pane=b]").is_visible() and page.locator("[data-pane=a]").is_hidden()
        assert page.get_attribute("[data-tab=b]", "aria-selected") == "true" and page.get_attribute("[data-tab=a]", "aria-selected") == "false"
        page.focus("[data-tab=b]")
        page.keyboard.press("ArrowRight")                 # wraps to the first
        assert page.evaluate("T.current()") == "a" and page.locator("[data-pane=a]").is_visible()
        page.evaluate("T.select('b')")                                                 # from the code
        assert page.locator("[data-tab=b]").evaluate("e => e.classList.contains('on')")
        page.click("[data-v=y]")
        assert page.locator("[data-v=y]").evaluate("e => e.classList.contains('on')") and not page.locator("[data-v=x]").evaluate("e => e.classList.contains('on')")
        assert page.locator("[data-pane=b]").is_visible()                              # the switch touches no pane
        assert page.evaluate("seen") == ["tb", "ta", "tb", "sy"]
        page.mouse.move(1, 1)
        # a tab is a label, not a button: the selected one has the accent text and a line under it, and no fill (the switch's look is another)
        look = "s => { const c = getComputedStyle(document.querySelector(s)); return [c.color, c.borderBottomColor, c.borderBottomWidth, c.backgroundColor]; }"
        on, off = page.evaluate(look, "[data-tab=b]"), page.evaluate(look, "[data-tab=a]")
        assert on[0] != off[0] and on[1] != off[1] and on[2] == off[2] and float(on[2][:-2]) >= 2, (on, off)       # 2.5 px: 2 px at a pixel ratio of 1
        assert on[3] == off[3] == "rgba(0, 0, 0, 0)", (on, off)
    _run(tmp_path, body)


def test_the_options_of_a_tab_row(tmp_path):
    """The options of rs-tabs (tabs.js, docs/guides/dashboard-parts.md "Tabs"): icons from data-icon or the tab's own svg, the icon over the label
    (top), tabs that share the row's width (fill), a tint behind the selected tab (tint); an unknown icon is an error that names the icons."""
    def body(page):
        page.evaluate("""() => { const d = document.createElement('div'); d.id = 'w'; d.style.width = '360px';
            const row = (id, attrs) => '<nav class="rs-tabs" id="' + id + '"' + attrs + '><button class="rs-tab on" data-tab="a" data-icon="car">Traffic flow</button>'
              + '<button class="rs-tab" data-tab="b" data-icon="gauge">Speed<span class="rs-count">3</span></button>'
              + '<button class="rs-tab" data-tab="c"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/></svg>Own</button></nav>';
            d.innerHTML = row('plain', '') + row('ic', ' data-icons') + row('top', ' data-icons="top" data-fill') + row('ft', ' data-fill data-tint');
            document.querySelector('#sb .sb-body').appendChild(d);
            for(const id of ['plain', 'ic', 'top', 'ft']) rs.tabs.use(document.getElementById(id), () => {}); }""")
        box = "s => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }"
        assert page.evaluate("document.querySelectorAll('#plain .rs-tab-ic').length") == 0                  # off by default: no icon
        assert page.evaluate("document.querySelectorAll('#ic .rs-tab-ic').length") == 3                     # two of the set and the tab's own svg
        assert page.evaluate("document.querySelector('#ic [data-tab=b] .rs-tab-lb').textContent") == "Speed3"
        ic, lb = page.evaluate(box, "#ic [data-tab=a] .rs-tab-ic"), page.evaluate(box, "#ic [data-tab=a] .rs-tab-lb")
        assert ic[0] + ic[2] <= lb[0] and abs((ic[1] + ic[3] / 2) - (lb[1] + lb[3] / 2)) < 2                 # inline: before the label, on its line
        ic, lb = page.evaluate(box, "#top [data-tab=b] .rs-tab-ic"), page.evaluate(box, "#top [data-tab=b] .rs-tab-lb")
        assert ic[1] + ic[3] <= lb[1]                                                                        # top: over the label and its count
        widths = [page.evaluate(box, f"#top [data-tab={t}]")[2] for t in "abc"]
        assert max(widths) - min(widths) < 1 and abs(sum(widths) - page.evaluate(box, "#top")[2]) < 1          # fill: equal widths, the whole row
        tint = "s => getComputedStyle(document.querySelector(s)).backgroundColor"
        assert page.evaluate(tint, "#ft [data-tab=a]") != "rgba(0, 0, 0, 0)" and page.evaluate(tint, "#plain [data-tab=a]") == "rgba(0, 0, 0, 0)"
        err = page.evaluate("""() => { const n = document.createElement('nav'); n.className = 'rs-tabs'; n.dataset.icons = '';
            n.innerHTML = '<button class="rs-tab" data-tab="a" data-icon="boat">A</button>';
            try { rs.tabs.use(n); return null; } catch(e) { return e.message; } }""")
        assert "no icon 'boat'" in err and "gauge" in err
        assert page.evaluate("""() => { const n = document.createElement('nav'); n.className = 'rs-tabs';
            n.innerHTML = '<button class="rs-tab" data-tab="a" data-icon="map">A</button>';
            rs.tabs.use(n, null, {icons: 'top', fill: true}); return [n.dataset.icons, n.hasAttribute('data-fill'), n.querySelectorAll('.rs-tab-ic').length]; }""") == ["top", True, 1]
    _run(tmp_path, body)


def test_cards_and_number_tiles(tmp_path):
    def body(page):
        page.evaluate("""() => { const d = document.createElement('div'); d.id = 'c'; d.className = 'sb-sec';
            d.innerHTML = '<div class="rs-callout">Answer</div><div class="rs-kpis" id="k"></div><div class="rs-sec-box"><h3>Title</h3><p>Muted words</p></div>';
            document.querySelector('#sb .sb-body').appendChild(d);
            document.getElementById('k').innerHTML = rs.kpi('Inside', '80.4%', 'promised', '#15803d') + rs.kpi('Miss', '10 %') + rs.kpi('Bad', '1', '', 'red;x:y'); }""")
        assert page.locator(".rs-kpi").count() == 3
        assert page.locator(".rs-kpi-val").first.evaluate("e => e.style.getPropertyValue('--rs-kpi-c')") != ""     # the page's colour, mixed in the dark theme
        assert page.locator(".rs-kpi-val").nth(2).get_attribute("style") is None        # a colour with a ; is not taken
        assert page.evaluate("getComputedStyle(document.getElementById('k')).gridTemplateColumns.split(' ').length") == 3
        muted, ink = (page.evaluate("s => getComputedStyle(document.querySelector(s)).color", s) for s in (".rs-sec-box h3 + p", ".rs-sec-box h3"))
        assert muted != ink
        assert page.evaluate("[getComputedStyle(document.querySelector('.rs-callout')).borderRadius, getComputedStyle(document.querySelector('.rs-callout'), '::before').content]") == ["10px", '"i"']   # round corners and the round mark (2026-11-06: no bar)
    _run(tmp_path, body)


def test_a_chart_follows_the_theme_with_rs_svg(tmp_path):
    def body(page):
        page.evaluate("""() => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.id = 'ch'; document.querySelector('#sb .sb-body').appendChild(s);
            rs.svg(s, 'polygon', {points: '0,0 9,0 9,9', fill: 'var(--rs-chart-band)', stroke: 'var(--rs-chart-band-line)', 'stroke-width': 1});
            rs.svg(s, 'text', {x: 1, y: 1}, 'T'); }""")
        assert page.evaluate("document.querySelector('#ch polygon').getAttribute('stroke-width')") == "1"
        assert page.evaluate("document.querySelector('#ch polygon').getAttribute('fill')") is None        # the variable went to the style
        assert page.evaluate("document.querySelector('#ch text').textContent") == "T"
        def fill():
            return page.evaluate("getComputedStyle(document.querySelector('#ch polygon')).fill")
        light = fill()
        assert light != "none" and light != ""
        page.evaluate("rsSetTheme('dark')")
        assert fill() != light
    _run(tmp_path, body)


def test_inputs_chips_and_dots_use_the_panel_tokens(tmp_path):
    def body(page):
        page.evaluate("""() => { const d = document.createElement('div'); d.className = 'sb-sec'; d.id = 'f';
            d.innerHTML = '<input id="i" placeholder="Find"><textarea id="t"></textarea><span class="rs-chip" id="c1">a</span><span class="rs-chip accent" id="c2">b</span><span class="rs-dot" id="d"></span>';
            document.querySelector('#sb .sb-body').appendChild(d); }""")
        def st(sel, prop):
            return page.evaluate("([s, p]) => getComputedStyle(document.querySelector(s))[p]", [sel, prop])
        assert st("#i", "borderRadius") == "8px" and st("#i", "width") == st("#t", "width")
        assert st("#c1", "backgroundColor") != st("#c2", "backgroundColor") and st("#c1", "borderRadius") == "10px"
        assert st("#d", "width") == "8px"
        light = st("#i", "backgroundColor")
        page.evaluate("rsSetTheme('dark')")
        assert st("#i", "backgroundColor") != light
    _run(tmp_path, body)


def test_ready_runs_now_when_the_page_is_ready(tmp_path):
    def body(page):
        assert page.evaluate("(() => { let n = 0; rs.ready(() => n++); return n; })()") == 1
    _run(tmp_path, body)

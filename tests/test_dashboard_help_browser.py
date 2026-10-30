"""The help window of a page (`rs.help`): the "i" button in the panel's title, the window that it opens, and the two ways to close it. The window takes
the colours of the page's theme (the card token), in the light and in the dark theme. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402
from test_dashboard_sections_browser import _edges, _open  # noqa: E402

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
        bg = lambda: page.evaluate("getComputedStyle(document.querySelector('#rs-help .rs-help-box')).backgroundColor")
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
        r = box.bounding_box(); assert r["x"] >= 8 and r["y"] >= 8
        page.evaluate("rs.hover.show('Near the corner', {clientX: innerWidth - 4, clientY: innerHeight - 4})")
        r = box.bounding_box(); assert r["x"] + r["width"] <= 1280 and r["y"] + r["height"] <= 800        # flipped to the other side
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
        page.evaluate("document.getElementById('t').scrollTop = 99999"); page.wait_for_timeout(200)
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
        page.focus("[data-tab=b]"); page.keyboard.press("ArrowRight")                 # wraps to the first
        assert page.evaluate("T.current()") == "a" and page.locator("[data-pane=a]").is_visible()
        page.evaluate("T.select('b')")                                                 # from the code
        assert page.locator("[data-tab=b]").evaluate("e => e.classList.contains('on')")
        page.click("[data-v=y]")
        assert page.locator("[data-v=y]").evaluate("e => e.classList.contains('on')") and not page.locator("[data-v=x]").evaluate("e => e.classList.contains('on')")
        assert page.locator("[data-pane=b]").is_visible()                              # the switch touches no pane
        assert page.evaluate("seen") == ["tb", "ta", "tb", "sy"]
        on = lambda: page.evaluate("getComputedStyle(document.querySelector('[data-tab=b]')).backgroundColor")
        off = page.evaluate("getComputedStyle(document.querySelector('[data-tab=a]')).backgroundColor")
        assert on() != off
    _run(tmp_path, body)

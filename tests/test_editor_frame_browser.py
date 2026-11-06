"""The editor frame (dashboard/frame.js, docs/guides/dashboard-parts.md, "An editor in the panel"): a frame with three tabs, a long body and a bar, in a
dashboard page, in the light and the dark theme, on a desktop and at 390 px. The body scrolls by the panel's protocol, the bar is outside the body at the
bottom edge of the panel in the panel's color, the tabs switch, and open and close hide and show the host's panel. Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402
from test_dashboard_themes_browser import _PROBE  # noqa: E402
from test_design_panel_browser import _ARGS, _edges  # noqa: E402

_OPEN = """() => {
  rs.sections.add({id: 'f', label: 'A card that folds', fold: true, html: '<p>x</p>'});
  window.got = []; window.hostTitle = document.querySelector('#sb .sb-top').firstElementChild;
  window.fr = rs.frame({panel: document.getElementById('sb'), title: 'Edit things', back: 'Steps', id: 'ef',
                        tabs: [['a', 'First'], ['b', 'Second'], ['c', 'Third']]});
  fr.addEventListener('tab', (e) => got.push(e.detail.tab));
  fr.addEventListener('back', () => got.push('back'));
  fr.body.innerHTML = Array.from({length: 60}, (_, i) => `<p>Line ${i} of the body</p>`).join('');
  fr.bar.innerHTML = '<b>3 changes</b> <button type="button">Apply</button>';
  fr.open('a');
}"""
_MEASURE = """() => {
  const card = document.querySelector('#sb .sb-card'), c = card.getBoundingClientRect(), cs = getComputedStyle(card);
  const b = fr.body, bar = fr.bar.getBoundingClientRect(), nav = document.getElementById('ef-tabs');
  b.scrollTop = 0;
  let painter = fr.bar;                                                 // the first element at or above the bar that paints a background
  while (painter && getComputedStyle(painter).backgroundColor === 'rgba(0, 0, 0, 0)') painter = painter.parentElement;
  const all = [fr.head, fr.root, ...fr.head.querySelectorAll('*'), ...fr.root.querySelectorAll('*')].filter((e) => e.offsetParent);
  return {
    pbody: b.classList.contains('rs-pbody') && b.dataset.rsScroll === '1', thin: getComputedStyle(b).scrollbarWidth, scrolls: b.scrollHeight > b.clientHeight + 100,
    outside: !b.contains(fr.bar) && fr.bar.parentElement === fr.root && fr.root.lastElementChild === fr.bar,
    gap: Math.round(c.bottom - parseFloat(cs.borderBottomWidth) - bar.bottom), barShown: bar.height > 20,
    painter: painter === card || painter === document.getElementById('sb'),
    edge: parseFloat(getComputedStyle(nav).borderBottomWidth) > 0 && nav.getBoundingClientRect().bottom <= b.getBoundingClientRect().top + 1,
    wide: all.filter((e) => e.getBoundingClientRect().right > c.right + 1).map((e) => e.id || e.className || e.tagName).slice(0, 4),
    over: b.scrollWidth - b.clientWidth, page: document.documentElement.scrollWidth - innerWidth,
    hostHidden: [getComputedStyle(hostTitle).display, getComputedStyle(document.querySelector('#sb .sb-body')).display,
                 getComputedStyle(document.getElementById('rs-fold-all')).display],
    title: document.querySelector('#sb .sb-top .rs-frame-title .t').textContent,
  };
}"""


@pytest.mark.parametrize("theme,width", [("light", 1280), ("dark", 1280), ("light", 390), ("dark", 390)])
def test_the_frame_has_one_scrolling_body_a_bar_at_the_bottom_edge_and_tabs(tmp_path, theme, width):
    path = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank", name="Frame").save(path)
    phone = width < 700
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": width, "height": 844 if phone else 900}, has_touch=phone, is_mobile=phone)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate(f"rsSetTheme({json.dumps(theme)})")
        if phone:
            page.evaluate("rs.sheet(2)")
        page.evaluate(_OPEN)
        page.wait_for_timeout(400)
        m = page.evaluate(_MEASURE)
        assert m["pbody"] and m["thin"] == "thin" and m["scrolls"], m                                  # the panel's scroll protocol, not the browser's scrollbar
        assert m["outside"] and m["barShown"] and abs(m["gap"]) <= 1 and m["painter"], m              # the bar: outside the body, at the bottom edge, the panel's color
        assert m["edge"] and m["wide"] == [] and m["over"] <= 1 and m["page"] <= 1, m
        assert m["hostHidden"] == ["none", "none", "none"] and m["title"] == "Edit things", m
        found = page.evaluate(_PROBE, ["#sb .rs-frame, #sb .rs-frame-title", theme == "dark"])
        assert not found, found
        # the tabs: a click selects the tab and sends "tab"; tab(name) selects with no event
        page.click("#ef-tab-b")
        on = "() => [...document.querySelectorAll('#ef-tabs .rs-tab')].map(b => [b.dataset.tab, b.classList.contains('on'), b.getAttribute('aria-selected')])"
        assert page.evaluate(on) == [["a", False, "false"], ["b", True, "true"], ["c", False, "false"]]
        page.evaluate("fr.tab('c')")
        assert page.evaluate("[fr.tab(), fr.body.getAttribute('aria-labelledby')]") == ["c", "ef-tab-c"]
        page.click("#ef-back")
        assert page.evaluate("window.got") == ["b", "back"]
        # close: the host's title, body and "Collapse all" show again
        page.evaluate("fr.close()")
        assert page.evaluate("""[fr.isOpen(), !!document.querySelector('#sb .rs-frame'), getComputedStyle(document.querySelector('#sb .sb-body')).display !== 'none',
          getComputedStyle(hostTitle).display !== 'none', getComputedStyle(document.getElementById('rs-fold-all')).display !== 'none']""") \
            == [False, False, True, True, True]
        browser.close()
    assert not errors, errors

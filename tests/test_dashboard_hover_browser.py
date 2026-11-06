"""One hover for the whole dashboard (docs/design/ask_and_data_dock.md, "One hover for the whole dashboard"): the pointer goes onto every
control of the panel, the toolbox and each of its boxes, the help window and the day picker, in the light and the dark theme. Each one
reacts in one of three looks: a tint behind it (not filled), brighter (filled) or underlined (a link). A disabled control does not react.
Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402

# the parts that a page can put in the panel, all in one card
_PARTS = """rs.sections.add({id: 'parts', label: 'Parts', html:
  '<nav class="rs-tabs"><button class="rs-tab on" data-tab="a">Overview</button><button class="rs-tab" data-tab="b">Streets</button></nav>' +
  '<div data-pane="a"><div class="rs-seg" id="h-seg"><button class="on" data-v="1">Every day</button><button data-v="2">First day</button></div>' +
  '<p><button class="rs-chip">A chip</button> <a href="#x">A link</a></p><div id="h-day"></div>' +
  '<details><summary>More</summary>text</details>' +
  '<p><button>Plain</button> <button class="sb-primary">Primary</button> <button disabled>Off</button> <select><option>One</option></select></p></div>' +
  '<div data-pane="b" hidden>b</div>'});
  rs.tabs.use(document.querySelector('#sb .rs-tabs')); rs.tabs.use(document.getElementById('h-seg'));
  rs.days.use(document.getElementById('h-day'), {days: ['2026-10-01', '2026-10-04', '2026-10-05']});
  rs.sections.add({id: 'folds', label: 'A card that folds', fold: true, html: '<p>x</p>'});
  rs.sections.add({id: 'opens', label: 'A card that opens', note: 'opens something', open: () => {}});
  rs.help.set({title: 'How to read this page', intro: 'Test. <a href="#y">a link</a>'});"""

# every visible control that the pointer can reach, at most two of each kind in each place
_CONTROLS = """(() => {
  const vis = e => { const r = e.getBoundingClientRect(); if(r.width < 4 || r.height < 4 || e.closest('[hidden]')) return false;
    const c = getComputedStyle(e); if(c.visibility === 'hidden' || c.display === 'none' || +c.opacity === 0) return false;
    const t = document.elementFromPoint(Math.min(innerWidth - 1, r.left + r.width / 2), Math.min(innerHeight - 1, r.top + r.height / 2));
    return !!t && (t === e || e.contains(t)); };
  document.querySelectorAll('[data-hv]').forEach(e => delete e.dataset.hv);      // the numbers of an earlier state
  const seen = {}, out = [];
  for(const e of document.querySelectorAll('button, a[href], summary, select')){
    if(!vis(e) || e.closest('.maplibregl-ctrl-attrib, .maplibregl-ctrl-bottom-right, .maplibregl-ctrl-bottom-left')) continue;
    if(e.matches('.rs-sec-title')) continue;          // a card's title row: the card rules give its hover (the card, not the button)
    const where = e.closest('[id]')?.id || 'page', cls = String(e.className).replace(/\\b(on|open)\\b/g, '').trim();
    const kind = where + '|' + e.tagName + '|' + cls; seen[kind] = (seen[kind] || 0) + 1; if(seen[kind] > 2) continue;
    e.dataset.hv = String(out.length);
    const r = e.getBoundingClientRect();
    out.push({kind, hv: e.dataset.hv, x: r.left + r.width / 2, y: r.top + r.height / 2, disabled: e.disabled === true,
              label: (e.getAttribute('aria-label') || e.title || e.textContent || '').trim().slice(0, 30)});
  }
  return out; })()"""
_LOOK = """(hv => { const e = document.querySelector('[data-hv="' + hv + '"]'), c = getComputedStyle(e);
  return {bg: c.backgroundColor, filter: c.filter, line: c.textDecorationLine}; })"""


def _looks(page, seen):
    """The look that each control not yet seen takes under the pointer: "tint", "brighter", "underline", or None."""
    out = []
    for c in page.evaluate(_CONTROLS):
        if c["kind"] in seen:
            continue
        seen.add(c["kind"])
        page.mouse.move(1, 799)
        page.wait_for_timeout(30)
        a = page.evaluate(f"{_LOOK}('{c['hv']}')")
        page.mouse.move(c["x"], c["y"])
        page.wait_for_timeout(120)
        b = page.evaluate(f"{_LOOK}('{c['hv']}')")
        look = ("brighter" if b["filter"] != a["filter"] and "brightness" in b["filter"] else
                "underline" if b["line"] != a["line"] and "underline" in b["line"] else
                "tint" if b["bg"] != a["bg"] else None)
        out.append((f"{c['label']} @ {c['kind']}", c["disabled"], look))
    return out


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_control_has_one_of_the_three_hover_looks(tmp_path, theme):
    path = tmp_path / "h.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.evaluate(_PARTS)
            page.evaluate(f"rsSetTheme('{theme}')")
            page.wait_for_timeout(300)
            link_color, accent = page.evaluate("""() => { const a = document.querySelector('#sb a[href="#x"]'), t = document.createElement('i');
              t.style.color = 'var(--accent)'; a.parentElement.append(t); const r = [getComputedStyle(a).color, getComputedStyle(t).color]; t.remove(); return r; }""")
            seen, rows = set(), []
            rows += _looks(page, seen)
            page.click("#h-day .rs-day-field")
            page.wait_for_timeout(200)
            rows += _looks(page, seen)
            page.keyboard.press("Escape")
            page.click("#sb .sb-top .rs-help-btn")
            page.wait_for_timeout(200)
            rows += _looks(page, seen)
            page.keyboard.press("Escape")
            for tool in page.evaluate("[...document.querySelectorAll('#rs-toolbar [data-rs-tool]')].map(b => b.dataset.rsTool)"):
                btn = page.locator(f"#rs-toolbar [data-rs-tool='{tool}']")
                if not btn.is_visible():
                    continue
                btn.click()
                page.wait_for_timeout(250)
                rows += _looks(page, seen)
                page.keyboard.press("Escape")
                page.mouse.click(640, 400)
            page.click("#sb-hide")
            page.wait_for_timeout(300)
            rows += _looks(page, seen)
        finally:
            browser.close()
    assert len(rows) > 30, rows
    assert [r[0] for r in rows if r[1] and r[2]] == [], "a disabled control reacts"
    bad = [r[0] for r in rows if not r[1] and r[2] is None]
    assert bad == [], "no hover: " + " | ".join(bad)
    assert link_color == accent, (link_color, accent)                     # a link in the panel has the accent, not the browser's blue
    assert [e for e in errors if "accelerometer" not in e] == []

"""rs.tools.disable(id, reason) and rs.tools.enable(id) (tools.js): the tool stays in its place, greyed out, with the reason in its title, also when the tool
reads its own state again (the tool `buildings` after a new base map, noise-map 2026-11-25); enable gives the tool its own state back. Skipped without
playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

_STATE = """id => { const b = document.querySelector(`[data-rs-tool="${id}"]`); b.matches('button') || (b = b.querySelector('button'));
  const t = rs.tools.list().find(t => t.id === id); return {disabled: b.disabled, tip: b.title || b.dataset.rsTip, listed: t.disabled, title: t.title}; }"""


def test_a_disabled_tool_stays_grey_with_its_reason(tmp_path):
    path = tmp_path / "tools.html"
    rs.render_dashboard(_edges(), basemap="blank").save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            page.goto(path.resolve().as_uri())
            page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
            state = _STATE.replace("const b", "let b")
            before = page.evaluate(state, "theme")
            page.evaluate("rs.tools.disable('theme', 'The page has one theme')")
            assert page.evaluate(state, "theme") == {"disabled": True, "tip": "The page has one theme", "listed": True, "title": "The page has one theme"}
            page.evaluate("rs.tools.enable('theme')")
            assert page.evaluate(state, "theme") == before
            page.evaluate("rs.tools.disable('buildings', 'This page draws its own 3D buildings')")
            page.evaluate("document.dispatchEvent(new CustomEvent('rs:buildings3dchange', {detail: {}}))")      # the tool reads its state again
            page.wait_for_timeout(50)
            s = page.evaluate(state, "buildings")
            assert s["disabled"] and s["tip"] == "This page draws its own 3D buildings" and s["listed"], s
            page.evaluate("rs.tools.enable('buildings')")
            assert page.evaluate(state, "buildings")["tip"].startswith("3D buildings need")
            with pytest.raises(Exception, match="no tool"):
                page.evaluate("rs.tools.disable('nothing', 'x')")
        finally:
            browser.close()
    assert errors == [], errors

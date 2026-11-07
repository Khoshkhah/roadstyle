"""The colour picker of the panel (dashboard/colorpick.js, docs/guides/dashboard-parts.md "A colour picker"): each `<input type="color">` of the panel
gets a swatch button and a box in the look of the select list, in place of the browser's own picker. The page's code keeps `value`, `disabled`, `input`
and `change`. A drag sends `input`; Escape puts the old colour back; a click outside keeps the new colour and sends one `change`. Both themes: readable,
and no light surface in the dark theme (the square, the hue bar and the swatches show colours and are not checked). Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402
from test_dashboard_themes_browser import _PROBE  # noqa: E402

import roadstyle as rs  # noqa: E402

_HTML = '<label>Road fill</label><input type="color" id="fill" value="#b8d986"> <input type="color" id="off" value="#7a8a9a" disabled>'


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_colour_picker_keeps_the_inputs_value_and_events(tmp_path, theme):
    path = tmp_path / "cp.html"
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"sections": [{"id": "c", "label": "Colours", "html": _HTML}]}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate(f"rsSetTheme({json.dumps(theme)})")
        page.evaluate("window.ev = []; const c = document.getElementById('fill'); ['input', 'change'].forEach(t => c.addEventListener(t, () => ev.push(t)));")
        assert page.evaluate("[!!document.getElementById('fill').closest('.rs-cp'), getComputedStyle(document.getElementById('fill')).display, document.querySelectorAll('#sb .rs-cp-btn').length]") == [True, "none", 2]
        assert page.evaluate("document.querySelectorAll('#sb .rs-cp-btn')[1].disabled")                 # disabled follows the input
        page.click("#sb .rs-cp-btn >> nth=0")
        sv = page.locator(".rs-cp-sv").bounding_box()
        page.mouse.move(sv["x"] + sv["width"] * .8, sv["y"] + sv["height"] * .3); page.mouse.down()
        page.mouse.move(sv["x"] + sv["width"] * .9, sv["y"] + sv["height"] * .2, steps=3); page.mouse.up()
        dragged = page.evaluate("document.getElementById('fill').value")
        assert dragged != "#b8d986" and page.evaluate("ev.every(e => e === 'input') && ev.length >= 2")
        found = page.evaluate(_PROBE, [".rs-cp-box", theme == "dark"])
        marks = ("span.rs-cp-dot", "i", "div.rs-cp-sv")                          # the handles have a white ring on purpose: it shows on every colour
        assert not [f for f in found if f[1] not in marks], found                # the box: readable, no light surface in the dark theme
        page.keyboard.press("Escape")
        assert page.evaluate("[document.getElementById('fill').value, !!document.querySelector('.rs-cp-box'), ev.includes('change')]") == ["#b8d986", False, False]
        page.click("#sb .rs-cp-btn >> nth=0")
        page.fill(".rs-cp-hex", "#ff6b35")
        page.mouse.click(1200, 700)                                                                      # a click outside keeps it
        assert page.evaluate("[document.getElementById('fill').value, ev.filter(e => e === 'change').length]") == ["#ff6b35", 1]
        page.evaluate("document.getElementById('fill').value = '#123456'")                              # the page's code sets the value: the swatch follows
        assert page.evaluate("getComputedStyle(document.querySelector('#sb .rs-cp-btn .rs-cp-sw')).backgroundColor") == "rgb(18, 52, 86)"
        browser.close()
    assert not errors, errors

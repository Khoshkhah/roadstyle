"""The place of the bar along its edge (`toolbar.align`, the Settings row "Toolbar place"; docs/guides/dashboard-layout.md): at each of the four edges, start
and end put the bar in a corner of the free part (8 px from the panel's card or the window's edge, clear of the box of the scale), and middle keeps it in
the middle. The person's choice is kept in this browser. Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

_RECTS = """() => { const R = s => { const e = document.querySelector(s); if(!e || getComputedStyle(e).display === "none") return null;
  const r = e.getBoundingClientRect(); return r.width ? [r.left, r.top, r.right, r.bottom] : null; };
  return {bar: R("#rs-toolbar"), card: R("#sb .sb-card"), scale: R("#rs-scalebox"), win: [innerWidth, innerHeight]}; }"""


def _meet(a, b):
    return b is not None and a[0] < b[2] - 2 and b[0] < a[2] - 2 and a[1] < b[3] - 2 and b[1] < a[3] - 2      # the bar may touch the card (OVERLAP)


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_the_bar_goes_to_a_corner_or_the_middle_of_its_edge(tmp_path, edge):
    path = tmp_path / "a.html"
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"scale_box": True}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        got = {}
        for align in ["start", "middle", "end"]:
            page.evaluate(f"localStorage.setItem('rs-settings:layout', {json.dumps(json.dumps({'toolbar': edge, 'align': align}))})")
            page.reload()
            page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
            page.wait_for_timeout(400)              # the bar's move (a 0.15 s transition)
            got[align] = page.evaluate(_RECTS)
        # the Settings row "Toolbar place": its names follow the edge, and the saved place is on
        page.click("[data-rs-tool=settings] > button")
        row = page.evaluate("""(() => { const r = [...document.querySelectorAll('#rs-settings-box .rs-set-row')]
                                 .find(r => r.querySelector('.rs-set-l').textContent === 'Toolbar place');
                               return [...r.querySelectorAll('button')].map(b => [b.textContent, b.classList.contains('on')]); })()""")
        browser.close()
    assert errors == [], errors
    names = ["Left", "Middle", "Right"] if edge in ("top", "bottom") else ["Top", "Middle", "Bottom"]
    assert row == [[n, n == names[2]] for n in names], row
    for align, r in got.items():
        bar, card, scale, (w, h) = r["bar"], r["card"], r["scale"], r["win"]
        assert not _meet(bar, card) and not _meet(bar, scale), (align, r)
        if edge in ("top", "bottom"):
            lo = card[2] if card else 0
            want = {"start": bar[0] - lo, "end": (scale[0] if edge == "bottom" and scale and scale[0] > w / 2 else w) - bar[2]}
            mid = (bar[0] + bar[2]) / 2 - (lo + w) / 2
        else:
            low = scale[1] if scale and (scale[0] < w / 2) == (edge == "left") else h
            want = {"start": bar[1], "end": low - bar[3]}
            mid = (bar[1] + bar[3]) / 2 - h / 2
        if align == "middle":
            assert abs(mid) < 60, (align, r)
        else:
            assert abs(want[align] - 8) < 2, (align, want, r)

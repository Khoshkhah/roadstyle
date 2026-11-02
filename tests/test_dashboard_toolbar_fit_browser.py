"""The bar stays in the free part of the window and wraps (docs/design/dashboard_templates.md, 3.2 and 3.4): a bar at the right or left edge that is
too short for its tools takes a second column, a bar along the top or the bottom is centered between the panel and the edge and takes a second row, and a box
never goes under the bar. Each case is checked in the light and the dark theme. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

_BOXES = ".bm-menu.open, #rs-attr-box, #rs-color-box, #rs-nav-box, #rs-roads-box, #rs-settings-box"
_RECTS = """() => {
  const R = e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const bar = document.getElementById("rs-toolbar"), card = document.querySelector("#sb .sb-card");
  const tools = {}; for(const e of document.querySelectorAll("[data-rs-tool]")) tools[e.dataset.rsTool] = {r: R(e), inBar: bar.contains(e)};
  return {bar: R(bar), card: card ? R(card) : null, tools, win: [innerWidth, innerHeight]};
}"""
_SHOWN = """() => [...document.querySelectorAll(%r)].filter(e => !e.hidden && getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0)
  .map(e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })""" % _BOXES


def _meet(a, b, gap=0.5):
    return a[0] < b[2] - gap and b[0] < a[2] - gap and a[1] < b[3] - gap and b[1] < a[3] - gap


def _inside(a, b, gap=0.5):
    return a[0] >= b[0] - gap and a[1] >= b[1] - gap and a[2] <= b[2] + gap and a[3] <= b[3] + gap


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    d = tmp_path_factory.mktemp("fit")
    out = {}
    for name, dash in (("right", {}), ("top", {"toolbar": {"position": "top"}}), ("left", {"toolbar": {"position": "left"}})):
        out[name] = d / f"{name}.html"
        rs.render_dashboard(_edges(), basemap="blank", dashboard=dash).save(out[name])
    return out


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=_ARGS)
        yield b
        b.close()


def _open(browser, path, w, h, theme, extra=0):
    page = browser.new_page(viewport={"width": w, "height": h})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
    if extra:
        page.evaluate("n => { for(let i = 0; i < n; i++) rs.tools.add({id: 'x' + i, title: 'Tool ' + i, icon: '&#9733;', onClick: () => {}}); }", extra)
    if theme == "dark":
        page.click('[data-rs-tool="theme"] button')
    page.wait_for_timeout(400)
    return page


def _check_layout(page):
    """Every tool of the bar is inside the bar, no two tools meet, and the bar meets neither the panel, nor the credits button, nor the window's edge."""
    s = page.evaluate(_RECTS)
    bar = s["bar"]
    inbar = {k: v["r"] for k, v in s["tools"].items() if v["inBar"]}
    assert len(inbar) >= 9, inbar.keys()
    for k, r in inbar.items():
        assert _inside(r, bar), (k, r, bar)
    ks = list(inbar)
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            assert not _meet(inbar[a], inbar[b]), (a, b)
    assert _inside(bar, [0, 0, *s["win"]]), bar
    if s["card"]:
        assert not _meet(bar, s["card"], 1.5), ("panel", bar, s["card"])
    credits = s["tools"]["attribution"]["r"]
    assert not _meet(bar, credits), ("credits button", bar, credits)
    return s


def _check_boxes(page, s):
    """Each box of the bar, opened in turn, lies in the window and does not meet the bar."""
    opened = 0
    for tool in page.evaluate("rs.tools.list().filter(t => t.kind === 'box' && !t.disabled).map(t => t.id)"):
        page.click(f'[data-rs-tool="{tool}"] button')
        page.wait_for_timeout(250)
        for r in page.evaluate(_SHOWN):
            opened += 1
            bar = page.evaluate("(() => { const r = document.getElementById('rs-toolbar').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })()")
            assert _inside(r, [0, 0, *s["win"]], 1), (tool, r)
            assert not _meet(r, bar), (tool, "box meets the bar", r, bar)
            for k, v in s["tools"].items():
                if v["inBar"]:
                    assert not _meet(r, v["r"]), (tool, "box meets tool", k)
        page.keyboard.press("Escape")
    assert opened >= 4


_SIZES = [(1000, 390), (1000, 530), (940, 480), (1400, 850), (1000, 630), (800, 630), (1000, 315), (850, 172)]
_TINY = (850, 145)       # a bar along the top and the credits box (95 px) do not both fit in 145 px: only the bars at a side are checked at this height


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("edge, w, h", [(e, w, h) for e in ("right", "left", "top") for w, h in _SIZES] + [(e, *_TINY) for e in ("right", "left")])
def test_every_tool_is_in_the_bar_and_nothing_meets(browser, pages, edge, w, h, theme):
    page = _open(browser, pages[edge], w, h, theme)
    _check_boxes(page, _check_layout(page))
    assert page.errors == []
    page.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_short_window_gives_a_second_column(browser, pages, theme):
    page = _open(browser, pages["right"], 1000, 390, theme)
    xs = {round(v["r"][0]) for v in page.evaluate(_RECTS)["tools"].values() if v["inBar"]}
    assert len(xs) == 2
    page.set_viewport_size({"width": 1000, "height": 850})
    page.wait_for_timeout(300)
    xs = {round(v["r"][0]) for v in page.evaluate(_RECTS)["tools"].values() if v["inBar"]}
    assert len(xs) == 1
    page.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_narrow_free_area_gives_a_second_row_and_the_bar_is_centered_in_it(browser, pages, theme):
    page = _open(browser, pages["top"], 740, 480, theme)
    s = _check_layout(page)
    assert len({round(v["r"][1]) for v in s["tools"].values() if v["inBar"]}) >= 2
    free_lo, free_hi = s["card"][2], s["win"][0]
    assert abs((s["bar"][0] + s["bar"][2]) / 2 - (free_lo + free_hi) / 2) < 2
    page.set_viewport_size({"width": 1400, "height": 480})
    page.wait_for_timeout(300)
    s = _check_layout(page)
    assert len({round(v["r"][1]) for v in s["tools"].values() if v["inBar"]}) == 1
    assert abs((s["bar"][0] + s["bar"][2]) / 2 - (s["card"][2] + 1400) / 2) < 2
    page.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_credits_box_does_not_go_under_the_bar(browser, pages, theme):
    page = _open(browser, pages["right"], 1000, 530, theme)
    s = page.evaluate(_RECTS)
    page.click('[data-rs-tool="attribution"] button')
    page.wait_for_timeout(300)
    (box,) = page.evaluate(_SHOWN)
    assert not _meet(box, s["bar"]), (box, s["bar"])
    assert all(not _meet(box, v["r"]) for v in s["tools"].values() if v["inBar"])
    assert box[2] <= s["bar"][0] - 11, "the box has 12 px between it and the bar"
    page.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("extra", [1, 4])
@pytest.mark.parametrize("edge", ["right", "top"])
def test_tools_that_a_page_adds_wrap_too(browser, pages, edge, extra, theme):
    """The ten built-in tools and one or four more (11 and 14 buttons in the bar, with the credits in the corner)."""
    page = _open(browser, pages[edge], 1000 if edge == "right" else 740, 390 if edge == "right" else 480, theme, extra)
    s = page.evaluate(_RECTS)
    assert sum(1 for k, v in s["tools"].items() if k.startswith("x") and v["inBar"]) == extra
    _check_layout(page)
    page.close()


@pytest.fixture(scope="module")
def scale_page(tmp_path_factory):
    path = tmp_path_factory.mktemp("scale") / "s.html"
    edges = _edges(8)       # eight road classes: the legend and the roads boxes are tall
    edges["highway"] = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "service", "track"]
    rs.render_dashboard(edges, basemap="blank", color_options={"Road class": {}}, dashboard={"scale_box": True}).save(path)
    return path


_CORNER = "() => { const r = document.getElementById('rs-scalebox').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("w, h", [(1000, 340), (1000, 530)])
def test_no_box_goes_over_the_scale_box_or_the_credits_button(browser, scale_page, w, h, theme):
    """With the scale and the zoom number on, the legend, the roads and the credits boxes end above the corner box (which holds the credits button)."""
    page = _open(browser, scale_page, w, h, theme)
    corner = page.evaluate(_CORNER)
    assert corner[2] - corner[0] > 100, "the scale box is on"
    s = page.evaluate(_RECTS)
    credits = s["tools"]["attribution"]["r"]
    opened = 0
    for tool in ("legend", "roads", "attribution"):
        page.click(f'[data-rs-tool="{tool}"] button')
        page.wait_for_timeout(300)
        for r in page.evaluate(_SHOWN):
            opened += 1
            assert _inside(r, [0, 0, *s["win"]], 1), (tool, r)
            assert not _meet(r, corner), (tool, "box meets the scale box", r, corner)
            assert not _meet(r, credits), (tool, "box meets the credits button", r, credits)
            assert not _meet(r, s["bar"]), (tool, "box meets the bar", r, s["bar"])
        page.keyboard.press("Escape")
    assert opened == 3
    assert page.errors == []
    page.close()


def test_the_bar_has_no_overflow_rule_on_a_desktop(browser, pages):
    page = _open(browser, pages["right"], 1000, 390, "light")
    assert page.evaluate("getComputedStyle(document.getElementById('rs-toolbar')).overflow") == "visible"
    page.close()


def test_the_phone_bar_stays_one_scrolling_row(browser, pages):
    page = _open(browser, pages["top"], 390, 800, "light")
    row = page.evaluate("""() => { const s = document.querySelector('.rs-tb-scroll'), b = document.getElementById('rs-toolbar').getBoundingClientRect();
      return {ov: getComputedStyle(s).overflowX, h: b.height, left: b.left, right: innerWidth - b.right}; }""")
    assert row["ov"] == "auto" and row["h"] < 60 and row["left"] == 8 and row["right"] == 8
    page.close()

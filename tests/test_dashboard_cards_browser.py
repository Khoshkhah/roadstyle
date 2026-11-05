"""The card standard of the panel (docs/guides/dashboard-panel.md, "Cards: the panel standard"): all cards are as wide as each other, the space between
two cards is `--rs-card-gap` (12px), a closed card that folds is 44px high, its title row is flat (no border, no fill), and "collapse all" is at the
left of "hide the panel". Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_SECTIONS = [
    {"id": "plain", "html": '<div class="rs-sec-box"><div class="rs-card-title">Find</div><p>A plain card</p></div>'},
    {"id": "open", "label": "Open card", "fold": True, "html": "<p>The body of an open card</p>"},
    {"id": "shut", "label": "Closed card", "fold": True, "html": "<p>The body of a closed card</p>"},
    {"id": "last", "html": '<div class="rs-sec-box"><div class="rs-card-title">Last</div><p>The last card</p></div>'}]
_MEASURE = """() => {
  const box = s => document.querySelector(s).getBoundingClientRect();
  const ids = ["plain", "open", "shut", "last"];
  const el = id => document.querySelector(`[data-rs-section=${id}]`);
  const card = id => el(id).dataset.rsFold ? el(id) : el(id).querySelector(".rs-sec-box");
  const r = ids.map(id => card(id).getBoundingClientRect());
  const hd = getComputedStyle(el("shut").querySelector(".rs-sec-hd"));
  const top = [...document.querySelector("#sb .sb-top").querySelectorAll("button")].map(b => b.id);
  return {widths: r.map(x => Math.round(x.width * 10) / 10), gaps: r.slice(1).map((x, i) => Math.round((x.top - r[i].bottom) * 10) / 10),
          shut: r[2].height, hdBorder: hd.borderTopWidth, hdBg: hd.backgroundColor, top};
}"""


def _page(tmp_path, root=""):
    import geopandas as gpd
    from shapely.geometry import LineString
    edges = gpd.GeoDataFrame({"highway": ["primary"]}, geometry=[LineString([(18.0, 59.30), (18.0, 59.31)])], crs=4326)
    path = tmp_path / "c.html"
    html = rs.render_dashboard(edges, basemap="blank", color_options={"Road class": {}}, dashboard={"panel": {"sections": _SECTIONS}}, page_style=root)
    html.save(path)
    return path


def _measure(path, theme):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.evaluate(f"() => {{ rsSetTheme('{theme}'); rs.sections.fold('open', false); rs.sections.fold('shut', true); }}")
        page.wait_for_timeout(300)
        out = page.evaluate(_MEASURE)
        browser.close()
    assert not errors, errors
    return out


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_cards_have_one_width_one_gap_and_a_closed_card_is_44px_high(tmp_path, theme):
    m = _measure(_page(tmp_path), theme)
    assert len(set(m["widths"])) == 1, m["widths"]
    assert m["gaps"] == [12, 12, 12], m["gaps"]
    assert m["shut"] == 44, m["shut"]
    assert m["hdBorder"] == "0px" and m["hdBg"] == "rgba(0, 0, 0, 0)", (m["hdBorder"], m["hdBg"])
    assert m["top"].index("rs-fold-all") < m["top"].index("sb-hide"), m["top"]


def test_a_page_that_sets_the_gap_variable_gets_that_gap(tmp_path):
    m = _measure(_page(tmp_path, root=":root{--rs-card-gap:20px}"), "light")
    assert m["gaps"] == [20, 20, 20], m["gaps"]


_KINDS = [
    {"id": "card", "label": "A card", "html": "<p>Words</p>"},
    {"id": "nobg", "label": "No background", "background": False, "html": "<p>Words</p>"},
    {"id": "fold", "label": "A card that folds", "fold": True, "html": "<p>Words</p>"},
    {"id": "nobg_fold", "label": "A long title of a card that folds and has no background", "fold": True, "background": False, "html": "<p>Words</p>"},
    {"id": "block", "html": '<div class="rs-kpis"><div class="rs-kpi">1</div></div><p>A block of the page, no label</p>'},
    {"id": "own", "html": '<div class="rs-sec-box"><div class="rs-card-title">A card of the page</div><p>Words</p></div>'}]


def test_every_kind_of_card_and_a_block_without_a_label_follow_one_standard_and_the_help_button_is_before_the_chevron(tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString
    edges = gpd.GeoDataFrame({"highway": ["primary"]}, geometry=[LineString([(18.0, 59.30), (18.0, 59.31)])], crs=4326)
    path = tmp_path / "k.html"
    rs.render_dashboard(edges, basemap="blank", dashboard={"panel": {"sections": _KINDS}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 1100})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        for theme in ("light", "dark"):
            m = page.evaluate("""theme => { rsSetTheme(theme); rs.sections.fold('fold', true); rs.sections.fold('nobg_fold', false);
              if(!document.querySelector('#sb .rs-help-btn')) for(const id of ["card", "nobg", "fold", "nobg_fold", "own"]) rs.help.button(rs.sections.get(id), {title: "About " + id});
              const r = e => e.getBoundingClientRect(), sec = id => rs.sections.get(id);
              const box = id => id === "own" ? sec(id).querySelector(".rs-sec-box") : sec(id), ids = ["card", "nobg", "fold", "nobg_fold", "block", "own"];
              const bs = ids.map(id => r(box(id))), q = id => sec(id).querySelector(".rs-help-btn"), cs = id => getComputedStyle(sec(id));
              const fold = sec("fold"), tt = fold.querySelector(".rs-sec-title"), chev = fold.querySelector(".rs-sec-hd > svg");
              return {widths: bs.map(x => Math.round(x.width)), gaps: bs.slice(1).map((x, i) => Math.round(x.top - bs[i].bottom)),
                      ends: ["card", "nobg", "own"].map(id => Math.round(r(q(id)).right)), foldEnds: ["fold", "nobg_fold"].map(id => Math.round(r(q(id)).right)),
                      order: r(tt).right <= r(q("fold")).left && r(q("fold")).right <= r(chev).left, inTitle: !!q("fold").closest(".rs-sec-title"),
                      lastInRow: ["card", "nobg"].every(id => sec(id).querySelector(".rs-sec-hd").lastElementChild === q(id))
                                 && ["fold", "nobg_fold"].every(id => sec(id).querySelector(".rs-sec-hd").lastElementChild.tagName === "svg"),
                      bg: [cs("card").backgroundColor !== "rgba(0, 0, 0, 0)", cs("nobg").backgroundColor, cs("block").backgroundColor],
                      pad: [cs("nobg").paddingTop, cs("block").paddingTop], shut: r(fold).height, icons: [...document.querySelectorAll("#sb .rs-help-btn svg")].map(e => r(e).width),
                      noLabel: !sec("block").querySelector(".rs-sec-hd"),
                      foldAllGap: (() => { const h = document.getElementById("sb-hide"); let w = h; while(w.parentNode !== document.querySelector("#sb .sb-top")) w = w.parentNode;
                                           return Math.round(r(w).left - r(document.getElementById("rs-fold-all")).right); })()}; }""", theme)
            assert len(set(m["widths"])) == 1, (theme, m["widths"])                       # the cards, a card without background and a block: one width
            assert m["gaps"] == [12] * 5, (theme, m["gaps"])                              # and one gap between any two of them
            assert len(set(m["ends"])) == 1 and len(set(m["foldEnds"])) == 1, (theme, m)  # the "?" is at one place in the cards without a chevron, and at one place in the cards that fold
            assert m["order"] and not m["inTitle"] and m["lastInRow"], (theme, m)        # title, "?", then the chevron at the end of the row (decided 2026-11-03)
            assert m["bg"] == [True, "rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"] and m["pad"] == ["14px", "0px"] and m["noLabel"], (theme, m)
            assert m["shut"] == 44 and set(m["icons"]) == {16}, (theme, m)
            assert 0 <= m["foldAllGap"] <= 8, (theme, m["foldAllGap"])                   # "collapse all" is beside "hide the panel", not in the middle of the row
        page.click("[data-rs-section=fold] .rs-help-btn")
        assert page.locator("#rs-help .rs-help-ttl").inner_text() == "About fold"
        assert page.evaluate("rs.sections.get('fold').classList.contains('folded')")             # the "?" opens the help, it does not fold
        page.keyboard.press("Escape")
        page.click("[data-rs-section=fold] .rs-sec-title")
        assert not page.evaluate("rs.sections.get('fold').classList.contains('folded')")
        assert page.get_attribute("[data-rs-section=fold] .rs-sec-title", "aria-expanded") == "true"
        assert page.evaluate("rs.sections.get('card').querySelector('.rs-sec-title').tagName") == "DIV"   # a card that does not fold has no button for its title
        browser.close()
    assert not errors, errors


def test_a_card_that_folds_at_the_end_of_a_scrolled_panel_keeps_its_title_row_in_place(tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString
    edges = gpd.GeoDataFrame({"highway": ["primary"]}, geometry=[LineString([(18.0, 59.30), (18.0, 59.31)])], crs=4326)
    path = tmp_path / "j.html"
    tall = "".join(f"<p>Line {i}</p>" for i in range(12))
    rs.render_dashboard(edges, basemap="blank", dashboard={"panel": {"sections": [{"id": f"c{i}", "label": f"Card {i}", "html": tall} for i in range(3)]
                                                                     + [{"id": "last", "label": "Last", "fold": True, "html": tall}]}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 700})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.evaluate("() => { rs.sections.fold('last', false); const b = document.querySelector('#sb .sb-body'); b.scrollTop = b.scrollHeight; }")
        hd = "[data-rs-section=last] .rs-sec-hd"
        y0 = page.locator(hd).bounding_box()["y"]
        page.click(hd)
        assert page.evaluate("rs.sections.get('last').classList.contains('folded')")
        assert abs(page.locator(hd).bounding_box()["y"] - y0) < 1, (y0, page.locator(hd).bounding_box()["y"])   # it did not jump
        room = "() => parseFloat(document.querySelector('#sb .sb-body').style.getPropertyValue('--rs-fold-room')) || 0"
        assert page.evaluate(room) > 0
        page.evaluate("() => { document.querySelector('#sb .sb-body').scrollTop = 0; }")
        page.wait_for_timeout(100)
        assert page.evaluate(room) == 0                                                       # the room goes when the panel scrolls up
        page.click(hd)
        assert not page.evaluate("rs.sections.get('last').classList.contains('folded')")
        browser.close()
    assert not errors, errors


def test_a_card_that_opens_is_one_button_with_an_arrow_and_a_note(tmp_path):
    """A card with `open` (JavaScript only: a function) opens the page's own panel with one click anywhere on the card, or Enter on its title. It
    never folds ("collapse all" leaves it), it is 44px high like a closed card that folds, its row ends with the arrow after the "?", and its note is
    one line under the title (rs.sections.note). A disabled title does not open."""
    path = _page(tmp_path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.evaluate("""() => { window.opened = 0;
          rs.sections.add({id: "go", label: "Edit levels", open: () => { window.opened++; }});
          rs.help.button(rs.sections.get("go"), {title: "About go"}); }""")
        sec = "[data-rs-section=go]"
        def h():
            return page.evaluate(f"document.querySelector('{sec}').getBoundingClientRect().height")
        assert h() == 44, h()
        hd = page.evaluate(f"""() => {{ const hd = document.querySelector('{sec} .rs-sec-hd'), r = e => e.getBoundingClientRect();
          return {{last: hd.lastElementChild.tagName, order: r(hd.querySelector('.rs-help-btn')).right <= r(hd.lastElementChild).left,
                   button: hd.querySelector('.rs-sec-title').tagName}}; }}""")
        assert hd == {"last": "svg", "order": True, "button": "BUTTON"}, hd
        page.click(f"{sec} .rs-sec-title")
        page.focus(f"{sec} .rs-sec-title")
        page.keyboard.press("Enter")
        assert page.evaluate("window.opened") == 2
        page.click(f"{sec} .rs-help-btn")
        assert page.evaluate("window.opened") == 2, "the ? opens the help, not the card"
        page.keyboard.press("Escape")
        page.evaluate("rs.sections.note('go', '5 edits applied')")
        assert h() > 44 and page.inner_text(f"{sec} .rs-sec-note") == "5 edits applied"
        page.click(f"{sec} .rs-sec-note")
        assert page.evaluate("window.opened") == 3, "a click on the note opens the card too"
        page.evaluate("rs.sections.foldAll(true)")
        assert not page.evaluate("rs.sections.get('go').classList.contains('folded')") and page.is_visible(f"{sec} .rs-sec-note")
        page.evaluate(f"document.querySelector('{sec} .rs-sec-title').disabled = true")
        page.click(f"{sec} .rs-sec-note")
        assert page.evaluate("window.opened") == 3, "a disabled card does not open"
        for bad in ["{id: 'x', label: 'X', open: () => 1, fold: true}", "{id: 'y', open: () => 1}", "{id: 'z', label: 'Z', open: 'no'}"]:
            assert page.evaluate(f"() => {{ try {{ rs.sections.add({bad}); return false; }} catch(e) {{ return true; }} }}"), bad
        browser.close()
    assert not errors, errors

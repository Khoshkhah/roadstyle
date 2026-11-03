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

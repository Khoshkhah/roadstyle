"""The day picker of a page (`rs.days.use`, docs/guides/dashboard-parts.md, "A day picker"): the field shows the day and opens a calendar that offers
only the days with data, the arrows and "Latest" step through those days, a load that fails gives the old day back with a note, and a hover
marks the field. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_DAYS = ["2026-09-28", "2026-09-30", "2026-10-04", "2026-10-05"]
_SCRIPT = """rs.ready(() => {
  window.__asked = [];
  window.__day = rs.days.use(document.getElementById("day"), {days: %s, onChange: d => {
    window.__asked.push(d);
    return new Promise((ok, no) => setTimeout(() => d === "2026-09-28" ? no(new Error("no file")) : ok(), 300));
  }});
});""" % _DAYS


def _page(tmp_path, p):
    import geopandas as gpd
    from shapely.geometry import LineString
    edges = gpd.GeoDataFrame({"highway": ["primary"]}, geometry=[LineString([(18.0, 59.30), (18.0, 59.31)])], crs=4326)
    path = tmp_path / "days.html"
    rs.render_dashboard(edges, basemap="blank", page_script=_SCRIPT,
                        dashboard={"panel": {"sections": [{"id": "d", "html": '<div id="day"></div>'}]}}).save(path)
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.__day", timeout=60_000)
    return browser, page, errors


def test_the_day_picker_offers_only_the_days_with_data_and_steps_through_them(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(tmp_path, p)
        try:
            assert page.inner_text(".rs-day-label") == "DAY"                                  # the label, upper case as the card titles
            assert page.inner_text(".rs-day-text") == "Mon 5 Oct 2026"                        # the latest day when the page gives no value
            assert page.is_disabled(".rs-day-step[data-step='1']") and page.is_disabled(".rs-day-last")
            page.click(".rs-day-field")
            assert page.get_attribute(".rs-day-field", "aria-expanded") == "true"
            on = page.evaluate("[...document.querySelectorAll('.rs-day-cal .rs-day-cd:not(:disabled)')].map(b => b.dataset.d)")
            assert on == ["2026-10-04", "2026-10-05"]                                          # October: only its days with data are buttons
            page.click(".rs-day-cal [data-m='-1']")
            on = page.evaluate("[...document.querySelectorAll('.rs-day-cal .rs-day-cd:not(:disabled)')].map(b => b.dataset.d)")
            assert on == ["2026-09-28", "2026-09-30"]
            assert page.is_disabled(".rs-day-cal [data-m='-1']")                               # no month before the first day
            page.click(".rs-day-cal [data-d='2026-09-30']")
            assert page.locator(".rs-day-cal").is_hidden()
            assert page.inner_text(".rs-day-text") == "Wed 30 Sep 2026"
            assert page.evaluate("document.querySelector('.rs-day').classList.contains('rs-day-busy')")   # the field pulses while the page loads
            page.wait_for_function("!document.querySelector('.rs-day').classList.contains('rs-day-busy')")
            page.click(".rs-day-step[data-step='1']")                                         # the day after with data, not the next date
            page.wait_for_function("!document.querySelector('.rs-day').classList.contains('rs-day-busy')")
            assert page.inner_text(".rs-day-text") == "Sun 4 Oct 2026"
            page.click(".rs-day-last")
            page.wait_for_function("!document.querySelector('.rs-day').classList.contains('rs-day-busy')")
            assert page.evaluate("window.__day.value()") == "2026-10-05"
            assert page.evaluate("window.__asked") == ["2026-09-30", "2026-10-04", "2026-10-05"]
            page.click(".rs-day-field")
            page.keyboard.press("Escape")
            assert page.locator(".rs-day-cal").is_hidden()
        finally:
            browser.close()
    assert errors == []


def test_a_day_that_does_not_load_gives_the_old_day_back_with_a_note(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(tmp_path, p)
        try:
            page.evaluate("window.__day.set('2026-09-28')")
            page.wait_for_function("!document.querySelector('.rs-day').classList.contains('rs-day-busy')")
            assert page.evaluate("window.__day.value()") == "2026-10-05"
            assert page.inner_text(".rs-day-note") == "Could not load Mon 28 Sep 2026."
            page.evaluate("window.__day.set('2026-10-04', true)")                               # quiet: no onChange, and the note goes
            assert page.evaluate("window.__asked") == ["2026-09-28"] and page.locator(".rs-day-note").is_hidden()
            with pytest.raises(Exception, match="not one of the days"):
                page.evaluate("window.__day.set('2026-10-01')")
        finally:
            browser.close()
    assert errors == []


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_field_is_marked_on_hover_in_the_theme(tmp_path, theme):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(tmp_path, p)
        try:
            page.evaluate(f"rsSetTheme({theme!r})")
            read = "(() => { const s = getComputedStyle(document.querySelector('.rs-day-field')); return [s.borderTopColor, s.backgroundColor, s.boxShadow]; })()"
            rest = page.evaluate(read)
            page.hover(".rs-day-field")
            page.wait_for_timeout(250)
            hover = page.evaluate(read)
            accent = page.evaluate("(() => { const e = document.createElement('i'); e.style.color = 'var(--accent)'; document.getElementById('sb').append(e); const c = getComputedStyle(e).color; e.remove(); return c; })()")
            assert hover[0] == accent and hover[1] != rest[1] and hover[2] != "none", (rest, hover)   # a teal border, a fill and a ring
        finally:
            browser.close()
    assert errors == []

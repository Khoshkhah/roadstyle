"""Every part of a dashboard in the light and the dark theme: each tool's box, the panel with its parts, the help window, the popup and the
windows. A visible text has a contrast of 4.5 or more against its real background, and in the dark theme no surface and no line is light
(a colour swatch shows data and is not checked). A part that uses a fixed colour in place of the theme's tokens fails here.
Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_PARTS = """<nav class="rs-tabs" id="tb"><button class="rs-tab on" data-tab="a">Overview</button><button class="rs-tab" data-tab="b">Streets</button></nav>
<div data-pane="a"><div class="rs-callout" style="--rs-callout:#16a34a"><b>Yes.</b> On 80 % of hours the traffic was inside the range.</div>
<div class="rs-cap">All counted hours</div><div class="rs-kpis" id="k"></div>
<div class="rs-sec-box"><h3>By hour</h3><p>How often the range held.</p><svg id="chart" viewBox="0 0 300 80"></svg></div></div>
<div data-pane="b" hidden><div class="rs-scroll"><table class="rs-table"><thead><tr><th data-sort="desc">Street</th><th>Hours</th></tr></thead>
<tbody><tr><td>A street</td><td>24</td></tr><tr><td>B street</td><td>12</td></tr></tbody></table></div></div>
<div class="rs-seg" id="mode"><button class="on" data-v="all">Every day</button><button data-v="first">First day</button></div>
<div id="day"></div>
<p><button>Plain</button> <button class="sb-primary">Primary</button> <input placeholder="A text box"></p>
<p class="sb-note">Small print</p><a href="#">a link</a> <span class="rs-chip">chip</span> <span class="rs-chip accent">accent</span>
<div id="p2-range"></div><div id="p2-hour"></div><div id="p2-hours"></div><div id="p2-sl"></div><div id="p2-num"></div><div id="p2-col"></div>
<label class="rs-switch"><input type="checkbox" role="switch" checked><span>Show bridges</span></label><div id="p2-q"></div><div id="p2-drop"></div><div id="p2-prog"></div>
<div class="rs-status warn">3 fixes are not saved.</div><div class="rs-status error">Not an OSM file.</div><div class="rs-status ok">Done.</div>
<p><button>Fixes<span class="rs-badge">12</span></button> <button class="sb-primary">Save<span class="rs-badge">3</span></button> <button class="sb-danger">Delete</button>
<button class="rs-busy" disabled>Load</button> <span id="p2-menu"></span> <button id="p2-tog" aria-pressed="true">What is here?</button></p>
<ol class="rs-steps"><li class="rs-step done"><span class="rs-step-n">1</span><div class="rs-step-b"><b>Area</b><p>Monaco</p></div></li>
<li class="rs-step on"><span class="rs-step-n">2</span><div class="rs-step-b"><b>Build</b><p>The roads.</p></div></li><li class="rs-step wait"><span class="rs-step-n">3</span><div class="rs-step-b"><b>Edit</b><span class="rs-step-note">After step 2</span></div></li></ol>
<div class="rs-toolrow" id="p2-tools"><button data-v="a" aria-label="Move">M</button><button data-v="b" aria-label="Draw">D</button></div>
<div class="rs-rows" id="p2-rows"><button class="rs-row on" data-v="1"><b>Wall</b><small>barrier=wall</small><span class="rs-row-v">new</span></button><button class="rs-row" data-v="2"><b>Door</b><small>entrance=yes</small></button></div>
<div class="rs-empty"><span><b>No fixes yet.</b> Click a road.</span><button type="button">Add a fix</button></div><div id="p2-more"></div>"""
_SCRIPT = """rs.ready(() => {
  rs.help.set({title: "How to read this page", intro: "What the page shows.", terms: [["Term", "Its meaning."]], note: "A note."});
  document.getElementById("k").innerHTML = rs.kpi("Inside", "80.4%", "promised 80 %", "#15803d") + rs.kpi("Typical miss", "10 %", "on one hour");
  const s = document.getElementById("chart");
  rs.svg(s, "line", {x1: 0, x2: 300, y1: 40, y2: 40, stroke: "var(--rs-chart-grid)"});
  rs.svg(s, "polygon", {points: "0,60 100,30 200,40 300,20 300,70 0,70", fill: "var(--rs-chart-band)", stroke: "var(--rs-chart-band-line)"});
  rs.svg(s, "text", {x: 4, y: 12, fill: "var(--mut)", "font-size": 9}, "100 %");
  rs.tabs.use(document.getElementById("tb"), () => {});
  rs.tabs.use(document.getElementById("mode"), () => {});
  rs.days.use(document.getElementById("day"), {days: ["2026-10-01", "2026-10-04", "2026-10-05"]});
  rs.legend.add({id: "ev", color: "#ff0066", label: "Events"});
  const $ = id => document.getElementById(id);
  rs.days.range($("p2-range"), {min: "2026-09-01", max: "2026-11-06"}); rs.hours.use($("p2-hour"), {value: 8, hours: [6, 7, 8, 10]}); rs.hours.use($("p2-hours"), {value: [7, 9], range: true});
  rs.slider($("p2-sl"), {label: "Speed", min: 0, max: 130, value: 50, unit: "km/h"}); rs.number($("p2-num"), {label: "Lanes", min: 1, max: 8, value: 2, unit: "lanes"});
  rs.colorPick($("p2-col"), {label: "Fill"}); rs.search($("p2-q"), {button: "Go", suggest: () => [{label: "Monaco", sub: "Monaco"}, {label: "Monte Carlo", sub: "Monaco"}]}).set("Mo");
  rs.drop($("p2-drop"), {hint: "Up to 2 GB"}); rs.progress($("p2-prog"), {label: "Build", value: 0.4});
  $("p2-menu").append(rs.menu.button([{label: "Edit"}, {label: "Export", disabled: true}, "-", {label: "Delete", danger: true}]));
  rs.toggle($("p2-tog")); rs.tabs.use($("p2-tools")); rs.tabs.use($("p2-rows"));
  rs.more($("p2-more"), {items: Array.from({length: 30}, (_, i) => i), page: 3, noun: "roads", render: i => '<div class="rs-qrow"><b>Road ' + i + '</b><span>12 m</span></div>'});
  rs.panel.bar().innerHTML = '<span>3 fixes not saved</span><button class="sb-primary">Build</button>';
});"""
_PROBE = r"""([scope, dark]) => {
  const ctx = document.createElement('canvas').getContext('2d'); ctx.canvas.width = ctx.canvas.height = 1;
  const rgba = c => { ctx.clearRect(0,0,1,1); ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.fillRect(0,0,1,1); return [...ctx.getImageData(0,0,1,1).data]; };
  const lum = ([r,g,b]) => { const f = v => { v /= 255; return v <= .03928 ? v/12.92 : ((v+.055)/1.055)**2.4; }; return .2126*f(r)+.7152*f(g)+.0722*f(b); };
  const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m,n) => n-m); return (x+.05)/(y+.05); };
  const bgOf = el => { let stack = []; for(let e = el; e; e = e.parentElement){ const c = getComputedStyle(e).backgroundColor; const v = rgba(c); if(v[3] > 0){ stack.push(v); if(v[3] >= 250) break; } }
    let base = dark ? [20,23,28] : [255,255,255]; for(const v of stack.reverse()){ const a = v[3]/255; base = base.map((x,i) => v[i]*a + x*(1-a)); } return base.map(Math.round); };
  const name = el => { let s = el.tagName.toLowerCase(); if(el.id) s += '#'+el.id; if(el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\s+/).slice(0,2).join('.'); return s; };
  const out = [];
  for(const el of document.querySelectorAll(scope)){
    for(const e of [el, ...el.querySelectorAll('*')]){
      const r = e.getBoundingClientRect(); if(r.width < 2 || r.height < 2) continue;
      const cs = getComputedStyle(e); if(cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
      const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
      const bg = bgOf(e);
      if(own){ const c = rgba(cs.color); const k = cr(c.slice(0,3), bg); if(k < 4.5) out.push(['text', name(e), (e.textContent||'').trim().slice(0,30), cs.color, 'rgb('+bg+')', k.toFixed(2)]); }
      const swatch = /sw|swatch|lg-|flt-|rs-bm-sw/.test(e.className && e.className.baseVal === undefined ? e.className : '') || e.tagName === 'I' || e.type === 'color';
      const b = rgba(cs.backgroundColor); if(dark && !swatch && e.type !== 'range' && b[3] > 150 && lum(b) > .35) out.push(['light-bg', name(e), (e.textContent||'').trim().slice(0,30), cs.backgroundColor, '', '']);
      for(const side of ['Top','Bottom','Left','Right']){ const w = parseFloat(cs['border'+side+'Width']); if(w > 0 && cs['border'+side+'Style'] !== 'none'){ const v = rgba(cs['border'+side+'Color']); if(dark && v[3] > 150 && lum(v) > .35) { out.push(['light-line', name(e), side, cs['border'+side+'Color'], '', '']); break; } } }
    }
  }
  return out;
}"""
_STEPS = [("panel", "rsSelect(rsQuery(p => p.name)[5])", "#sb"), ("panel, tab b", "document.querySelector('#tb [data-tab=b]').click()", "#sb"), ("toolbar", None, "#rs-toolbar"),
         ("roads box", "rs.tools.open('roads')", "#rs-roads-box"), ("colour box", "rs.tools.open('legend')", "#rs-color-box"),
         ("base map box", "rs.tools.open('basemap')", ".rs-bm-box, .bm-menu"), ("navigate box", "rs.tools.open('navigate')", "#rs-nav-box"),
         ("settings box", "rs.tools.open('settings')", ".rs-settings, #rs-settings-box, .rs-st-box"), ("credits box", "rs.tools.open('attribution')", "#rs-attr-box"),
         ("help window", "document.querySelector('#sb .sb-top button[title*=\"read\"], #sb .rs-help-btn, #sb button[aria-label*=\"elp\"]')?.click()", ".rs-help, .rs-help-win, [role=dialog]"),
         ("popup", "rsSelect(rsQuery(p => p.name)[5])", ".maplibregl-popup"),
         ("street view window", "rsSetStreetView && rsSetStreetView(true)", ".rs-svw"), ("day calendar", "document.querySelector('.rs-day-field').click()", ".rs-day-cal:not([hidden])"),
         ("range calendar", "document.querySelector('#p2-range .rs-day-field').click()", ".rs-range-cal:not([hidden])"),
         ("hour list", "document.querySelector('#p2-hour .rs-hours-field').click()", ".rs-hours-list:not([hidden])"),
         ("colour picker box", "document.querySelector('#p2-col .rs-color-btn').click()", ".rs-color-box:not([hidden])"),
         ("action menu", "document.querySelector('#p2-menu .rs-more-btn').click()", ".rs-menu:not(.rs-hours-list):not([hidden])"),
         ("search list", "document.querySelector('#p2-q input').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown'}))", ".rs-search-list:not([hidden])"),
         ("toasts", "['info', 'ok', 'warn', 'error'].forEach(k => rs.toast('A toast of the kind ' + k, {kind: k, ms: 0, action: k === 'ok' ? {label: 'Undo'} : null}))", "#rs-toasts"),
         ("confirm dialog", "rs.confirm({title: 'Delete 3 fixes?', text: 'You cannot undo this.', ok: 'Delete', danger: true})", ".rs-dialog"), ("google 3d window", "rs.tools.open('google_3d')", ".rs-g3d")]


def _edges(n=6):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary", "residential"] * (n // 2), "name": [f"Street {i}" for i in range(n)], "maxspeed_kmh": [50, 30] * (n // 2),
                             "edge_id": list(range(1, n + 1))},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)], crs=4326)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_part_is_readable_in_the_theme(tmp_path, theme):
    path = tmp_path / "themes.html"
    rs.render_dashboard(_edges(), basemap="blank", name="Themes", color_options={"Road class": {}, "Speed": {"color_by": "maxspeed_kmh"}}, google_3d=True,
                        street_view="window", road_tooltip=["name"], page_script=_SCRIPT, dashboard={"panel": {"sections": [
                            {"id": "q", "part": "query", "label": "Query", "text": "p.maxspeed_kmh >= 50"},
                            {"id": "road", "part": "road_card", "label": "Selected road"},
                            {"id": "parts", "label": "The shared parts", "html": _PARTS}]}}).save(path)
    problems = {}
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate(f"rsSetTheme({json.dumps(theme)})")
        page.wait_for_timeout(400)
        page.evaluate("document.querySelector('#sb [data-q=run]').click()")
        assert page.evaluate("document.querySelectorAll('#k > *').length") == 2                    # the tiles are drawn
        for part, act, scope in _STEPS:
            page.keyboard.press("Escape")
            if act:
                page.evaluate(f"(() => {{ try {{ {act} }} catch(e) {{ return String(e) }} }})()")
                page.wait_for_timeout(500)
            if page.evaluate(f"document.querySelectorAll({json.dumps(scope)}).length"):
                found = page.evaluate(_PROBE, [scope, theme == "dark"])
                if found:
                    problems[part] = sorted({" | ".join(str(x) for x in f if x != "") for f in found})[:6]
        browser.close()
    assert not errors, errors
    assert not problems, json.dumps(problems, indent=1)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_design_panel_is_readable_in_the_theme(tmp_path, theme):
    from test_design_panel_browser import open_page, served
    problems = {}
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = open_page(p, url, 1400, 900)
        page.evaluate(f"rsSetTheme({json.dumps(theme)})")
        page.evaluate("dz.open('theme'); document.getElementById('mine-name').value = 'Mine'; document.getElementById('mine-save').click()")
        page.wait_for_timeout(300)
        for tab in ("theme", "roads", "text", "layers", "tiles"):
            page.evaluate(f"dz.tab('{tab}')")
            page.wait_for_timeout(200)
            found = page.evaluate(_PROBE, ["#sb .rs-dz, #sb .rs-dz-title", theme == "dark"])
            if found:
                problems[tab] = sorted({" | ".join(str(x) for x in f if x != "") for f in found})[:6]
        browser.close()
    assert not errors, errors
    assert not problems, json.dumps(problems, indent=1)

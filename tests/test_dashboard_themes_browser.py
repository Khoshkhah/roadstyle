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
<p><button>Plain</button> <button class="sb-primary">Primary</button> <input placeholder="A text box"></p>
<p class="sb-note">Small print</p><a href="#">a link</a> <span class="rs-chip">chip</span> <span class="rs-chip accent">accent</span>"""
_SCRIPT = """rs.ready(() => {
  rs.help.set({title: "How to read this page", intro: "What the page shows.", terms: [["Term", "Its meaning."]], note: "A note."});
  document.getElementById("k").innerHTML = rs.kpi("Inside", "80.4%", "promised 80 %", "#15803d") + rs.kpi("Typical miss", "10 %", "on one hour");
  const s = document.getElementById("chart");
  rs.svg(s, "line", {x1: 0, x2: 300, y1: 40, y2: 40, stroke: "var(--rs-chart-grid)"});
  rs.svg(s, "polygon", {points: "0,60 100,30 200,40 300,20 300,70 0,70", fill: "var(--rs-chart-band)", stroke: "var(--rs-chart-band-line)"});
  rs.svg(s, "text", {x: 4, y: 12, fill: "var(--mut)", "font-size": 9}, "100 %");
  rs.tabs.use(document.getElementById("tb"), () => {});
  rs.tabs.use(document.getElementById("mode"), () => {});
  rs.legend.add({id: "ev", color: "#ff0066", label: "Events"});
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
         ("street view window", "rsSetStreetView && rsSetStreetView(true)", ".rs-svw"), ("google 3d window", "rs.tools.open('google_3d')", ".rs-g3d")]


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

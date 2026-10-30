// roadstyle studio in the browser: the knobs of the Python studio's Map and Dashboard pages (src/roadstyle/studio/), roadstyle's
// Rust engine in a Web Worker (worker.js: the whole page for each change of the knobs, page_from) and that page in an iframe. The page in
// the iframe is the page that "Download" saves; the code panel is the Python call that makes it.
import {pythonCode, pyrepr} from "./code.js";
import {caller} from "../../rust/roadstyle-assets/files/static/dashboard/worker/call.js";

const $ = (id) => document.getElementById(id);
const SAMPLES = {"Södermalm driving": "sodermalm_driving", "Södermalm walking": "sodermalm_walking", "Södermalm cycling": "sodermalm_cycling"};
const OVERLAY_SAMPLES = {sensors: "sensors.geojson", zones: "zones.geojson"};
const CMAPS = ["viridis", "plasma", "magma", "cividis", "coolwarm", "RdYlGn_r"];
const OV_COLORS = ["#7c4dff", "#00bcd4", "#ff9800", "#e91e63"];
const ID_COLS = new Set(["id", "fid", "gid", "uid", "objectid"]);
// the pages (pages.render_dashboard: template=), their Python call, title and base maps offered (studio/dashboard.py)
const PAGES = {map: {fn: "render_edges", file: "map.html"},
               dashboard: {fn: "render_dashboard", file: "dashboard.html", title: "Roads dashboard"}};
const OFFERED = ["ofm_positron", "ofm_dark", "osm", "satellite", "blank"];
const MAPLIBRE = "https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist";   // render_web._MAPLIBRE_CDN: the preview's MapLibre (a page's _repr_html_)

// the state of the knobs
const st = {data: null, loader: "", page: "map", title: "", palette: "amber", basemap: "", offered: [], view3d: false, tiles: false,
            colours: {}, classes: null, minzoom: false, labels: true, arrows: true, popup: "curated", popupCols: [], hover: [], overlays: []};
let table = null, columns = [], numeric = new Set(), allClasses = [], gen = 0, html = "", url = "";
let BASEMAPS = [], colourOpts = [{name: "Class"}];      // basemaps.json's keys; the last colour options

// ---------------------------------------------------------------- the engine in its worker
const worker = new Worker(new URL("./worker.js", import.meta.url), {type: "module"});
const call = caller(worker);                // the calls and answers of rust/roadstyle-assets/files/static/dashboard/worker/call.js
window.studio = {debug: () => ({table, columns, allClasses, st})};      // for a check in a browser (the tests)

// ---------------------------------------------------------------- the page's keywords
// render_edges' keywords of the knobs, in their order: the look's args (with state "live", as a page) and the code's keywords
function keywords(co){
  const P = PAGES[st.page], kw = {palette: st.palette, basemap: st.basemap};
  if (P.title) { kw.basemaps = st.offered.length ? st.offered : null; kw.name = st.title || P.title; }
  if (st.view3d) kw.view_3d = true;
  if (st.tiles) kw.tiles = true;
  if (co.length > 1) kw.color_options = Object.fromEntries(co.map(({name, ...o}) => [name, o]));
  if (st.classes && st.classes.length !== allClasses.length) kw.include = st.classes;
  if (st.minzoom) kw.minzoom = true;
  if (!st.labels) kw.labels = false;
  if (!st.arrows) kw.arrows = false;
  if (!P.title) { const popup = {choose: st.popupCols, panel: "panel", all: "all", off: false}[st.popup]; if (popup !== undefined) kw.road_popup = popup; }
  if (st.hover.length) kw.tooltip = st.hover;
  if (st.overlays.length) kw.overlays = st.overlays;
  return kw;
}
// the look's options (resolveLook's and page_from's): the keywords as JSON, with the sidebar of a Dashboard page; the classes
// are the dashboard's filter (include= is Python's filter before the engine), the overlays their GeoJSON
function lookOptions(co){
  const {palette, include, ...kw} = keywords(co), args = {...kw, name: kw.name || "roadstyle", state: "live"};
  if (st.page !== "map") args.template = st.page;
  // a JSON object's keys are text, as in Python's json.dumps of the dict
  if (args.color_options) args.color_options = co.map((o) => o.colors ? {...o, colors: Object.fromEntries([...o.colors].map(([k, c]) => [String(k), c]))} : o);
  if (args.overlays) args.overlays = st.overlays.map((o) => ({label: o.label, color: o.color, placement: o.under ? "under" : "over", popup: o.popup,
    ...(o.tooltip.length ? {tooltip: o.tooltip} : {}), fc: o.fc}));
  return {palette, args};
}
// the colour options of the picked columns, as the Python studio makes them (studio/common.py, _colour_opt): a numeric column with more
// than 12 values is a ramp from its 2nd to its 98th percentile (pandas' quantile: linear between the ranks); another column is min(5, n)
// stepped colours of the ramp, its sorted values split into even groups (a categorical legend)
async function colourOptions(){
  const out = [{name: "Class"}];
  for (const [col, cmap] of Object.entries(st.colours)) {
    const all = table.props.map((p) => p && p[col]).filter((x) => x != null && !(typeof x === "number" && !isFinite(x)));
    const vals = [...new Set(all)].sort((a, b) => a < b ? -1 : a > b ? 1 : 0), n = vals.length;
    if (!n) continue;
    if (numeric.has(col) && n > 12) {
      const v = all.slice().sort((a, b) => a - b);
      const q = (f) => { const x = f * (v.length - 1), i = Math.floor(x), j = Math.min(i + 1, v.length - 1); return v[i] + (v[j] - v[i]) * (x - i); };
      out.push({name: col, color_by: col, cmap, vmin: q(0.02), vmax: q(0.98), missing: "self"});
    } else {
      const k = Math.min(5, n), stops = (await call({type: "ramp", cmap, n: k})).stops, colors = new Map();
      for (let i = 0; i < k; i++) for (const v of vals.slice(Math.floor(i * n / k), Math.floor((i + 1) * n / k))) colors.set(v, stops[i]);
      out.push({name: col, color_by: col, missing: "self", colors});         // a Map: the code keeps each value's type (1, True)
    }
  }
  return out;
}

// ---------------------------------------------------------------- build: the page, then the iframe
let busy = false, again = false, timer = 0;
const later = () => { clearTimeout(timer); timer = setTimeout(build, 250); };
const win = () => $("preview").contentWindow;
async function build(){
  if (!st.data) return;
  if (busy) { again = true; return; }
  busy = true; $("status").textContent = "making the page…";
  try {
    gen += 1;
    if (table) colourOpts = await colourOptions();
    const r = await call({type: "page", options: lookOptions(colourOpts)});
    html = r.html;
    await show(r.html, !!table);                                // new data: the page's own view of it, not the last camera
    if (!table) { table = win().RS_SIDE; dataKnown(); }
    $("status").textContent = `${table.props.length.toLocaleString()} roads, made in ${(r.ms / 1000).toFixed(1)} s`;
    $("status").dataset.built = gen;                            // the number of the last build (a test waits for it)
    code();
  } catch (e) {
    $("status").innerHTML = `<span class="err">The page failed: ${e.message}</span>`;
  }
  busy = false;
  if (again) { again = false; build(); }
}
// the page in the iframe (MapLibre from the CDN, as a page's notebook preview), with the camera of the last one (keep: the same data)
// and the classes' filter
function show(page, keep){
  let camera = null;
  try { camera = keep && win().rs && win().rs.getState().camera; } catch (e) { camera = null; }
  if (url) URL.revokeObjectURL(url);
  url = URL.createObjectURL(new Blob([page.replace("<style>__MAPLIBRE_CSS__</style>", `<link rel="stylesheet" href="${MAPLIBRE}/maplibre-gl.css"/>`)
    .replace("<script>__MAPLIBRE_JS__</script>", `<script src="${MAPLIBRE}/maplibre-gl.js"></script>`)], {type: "text/html"}));
  return new Promise((ok) => {
    $("preview").onload = () => {
      const ready = () => { const w = win();
        if (!(w.rs && w.map && w.map.isStyleLoaded && w.map.isStyleLoaded() && w.RS_SIDE)) return setTimeout(ready, 50);
        if (camera) w.rs.setState({camera});
        if (st.classes) w.rs.setFilter({classes: st.classes});
        ok(); };
      ready();
    };
    $("preview").src = url;
  });
}

// ---------------------------------------------------------------- the knobs that the data decides
function dataKnown(){
  allClasses = [...new Set(table.props.map((p) => p && p.highway).filter((h) => h != null))].sort();
  st.classes = null; st.colours = {}; st.popupCols = columns.filter((c) => ["name", "edge_id", "highway", "lanes", "maxspeed_kmh"].includes(c));
  $("count").textContent = `${table.props.length.toLocaleString()} edges`;
  // colour by (studio/common.py, colour_by_section): the numeric columns and the other columns with 1 to 12 values, not the id columns
  const values = (c) => table.props.map((p) => p && p[c]).filter((v) => v != null);
  numeric = new Set(columns.filter((c) => { const v = values(c); return v.length && v.every((x) => typeof x === "number"); }));
  $("colours").innerHTML = "";
  let picked = 0;
  for (const c of columns) {
    if (ID_COLS.has(c.toLowerCase()) || c.toLowerCase().endsWith("_id")) continue;
    const n = new Set(values(c)).size;
    if (!numeric.has(c) && !(n > 0 && n <= 12)) continue;
    const row = document.createElement("div");
    row.innerHTML = `<label class="inline"><input type="checkbox"> ${c}</label><select hidden>${CMAPS.map((m) => `<option>${m}</option>`).join("")}</select>`;
    const [cb, sel] = [row.querySelector("input"), row.querySelector("select")];
    cb.onchange = () => {
      if (cb.checked && !(c in st.colours)) sel.selectedIndex = (++picked) % CMAPS.length;   // the Python studio: the i-th pick's map is CMAPS[(i + 1) % n]
      sel.hidden = !cb.checked; if (cb.checked) st.colours[c] = sel.value; else delete st.colours[c]; later();
    };
    sel.onchange = () => { st.colours[c] = sel.value; later(); };
    $("colours").appendChild(row);
  }
  checklist($("classes"), allClasses, allClasses, (v) => { st.classes = v; win().rs.setFilter({classes: v}); code(); });
  checklist($("popupcols"), columns, st.popupCols, (v) => { st.popupCols = v; later(); });
  checklist($("hover"), columns, [], (v) => { st.hover = v; later(); });
}
function checklist(box, items, on, change){
  box.innerHTML = "";
  for (const it of items) {
    const l = document.createElement("label"); l.className = "inline";
    l.innerHTML = `<input type="checkbox" ${on.includes(it) ? "checked" : ""}> ${it}`;
    box.appendChild(l);
  }
  box.onchange = () => change(items.filter((_, i) => box.querySelectorAll("input")[i].checked));
}
function code(){
  const P = PAGES[st.page];
  $("code").textContent = pythonCode(keywords(colourOpts), st.loader, st.overlays.map((o) => ({path: o.path, args: o.args()})), P.fn, P.file);
}

// ---------------------------------------------------------------- the data
async function loadRoads(bytes, kind, name, loader, shp = {}){
  st.data = {name}; st.loader = loader; table = null; colourOpts = [{name: "Class"}];
  $("status").textContent = "reading the roads…";
  try { columns = (await call({type: "roads", bytes, kind, name, ...shp}, [bytes])).columns.filter((c) => c !== "geometry"); }
  catch (e) { $("status").innerHTML = `<span class="err">${name}: ${e.message}</span>`; return; }
  build();
}
for (const k of Object.keys(SAMPLES)) $("sample").add(new Option(k, k));
$("sample").onchange = async () => {
  const f = SAMPLES[$("sample").value];
  const r = await fetch(`samples/${f}.geojson`);
  if (!r.ok) { $("status").innerHTML = `<span class="err">samples/${f}.geojson: ${r.status}</span>`; return; }
  loadRoads(await r.arrayBuffer(), "geojson", $("sample").value, `edges = gpd.read_file("ui/studio/samples/${f}.geojson")`);
};
$("file").onchange = async () => {
  const fs = [...$("file").files], f = fs[0]; if (!f) return;
  // a Shapefile: its .shp, .dbf and .prj, picked together (the Rust engine reads it in EPSG:4326; no .prj: no CRS, an error)
  const shp = fs.find((x) => /\.shp$/i.test(x.name));
  if (shp) {
    const sib = (ext) => fs.find((x) => x.name.toLowerCase() === shp.name.toLowerCase().replace(/\.shp$/, ext));
    const dbf = sib(".dbf"), prj = sib(".prj");
    if (!dbf) { $("status").innerHTML = `<span class="err">${shp.name}: pick its .dbf file too</span>`; return; }
    loadRoads(await shp.arrayBuffer(), "shp", shp.name, `edges = gpd.read_file("${shp.name}")`,
              {dbf: await dbf.arrayBuffer(), prj: prj ? await prj.text() : undefined});
    return;
  }
  const parquet = /\.(geo)?parquet$/i.test(f.name);
  loadRoads(await f.arrayBuffer(), parquet ? "parquet" : "geojson", f.name,
            parquet ? `edges = gpd.read_parquet("${f.name}")` : `edges = gpd.read_file("${f.name}")`);
};

// ---------------------------------------------------------------- the look and the other knobs
const knob = (id, key, prop = "value") => { $(id).onchange = () => { st[key] = $(id)[prop]; later(); }; };
knob("palette", "palette"); knob("view3d", "view3d", "checked"); knob("tiles", "tiles", "checked"); knob("minzoom", "minzoom", "checked");
knob("labels", "labels", "checked"); knob("arrows", "arrows", "checked"); knob("basemap", "basemap"); knob("title", "title");
$("popup").onchange = () => { st.popup = $("popup").value; $("popupcols").hidden = st.popup !== "choose"; later(); };
// the page: a Dashboard page has its sidebar, a title, the base maps offered, and no road popup (its sidebar shows the road)
$("page").onchange = () => {
  st.page = $("page").value; const P = PAGES[st.page];
  st.title = P.title || ""; $("title").value = st.title;
  document.querySelectorAll(".sidebar-only").forEach((e) => { e.hidden = !P.title; });
  document.querySelectorAll(".map-only").forEach((e) => { e.hidden = !!P.title; });
  later();
};
$("copy").onclick = () => navigator.clipboard.writeText($("code").textContent);
// the download: the page in the iframe, with MapLibre in it (rust/roadstyle-assets/files/vendor, as WebMap.html: a page that works offline)
$("download").onclick = async () => {
  const get = async (f) => (await fetch(`../../rust/roadstyle-assets/files/vendor/${f}`)).text();
  const page = html.replace("__MAPLIBRE_CSS__", await get("maplibre-gl.css"))
    .replace("__MAPLIBRE_JS__", (await get("maplibre-gl.js")).replace(/<\/script>/g, "<\\/script>"));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([page], {type: "text/html"})); a.download = PAGES[st.page].file; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};

// the base maps: data/basemaps.json, one list for Python and the studio (the menu has all of them, as rs.BASEMAPS)
fetch("../../rust/roadstyle-assets/files/data/basemaps.json").then((r) => r.ok ? r.json() : Promise.reject(new Error(`basemaps.json: ${r.status}`))).then((j) => {
  BASEMAPS = j.basemaps.map((b) => b.key);
  for (const b of j.basemaps) $("basemap").add(new Option(b.label, b.key));
  st.basemap = BASEMAPS[0] || "";
  st.offered = OFFERED.filter((k) => BASEMAPS.includes(k));
  checklist($("offered"), BASEMAPS, st.offered, (v) => { st.offered = v; later(); });
  $("sample").onchange();
}).catch((e) => { $("status").innerHTML = `<span class="err">The base maps: ${e.message}</span>`; });

// ---------------------------------------------------------------- overlays: GeoJSON files, each one an rs.Overlay
async function addOverlay(name, text, path){
  const fc = JSON.parse(text), i = st.overlays.length, cols = Object.keys((fc.features[0] || {}).properties || {});
  const poly = /Polygon/.test(((fc.features[0] || {}).geometry || {}).type || "");
  const o = {name, path, fc, label: name.replace(/\.[^.]+$/, ""), color: OV_COLORS[i % OV_COLORS.length], under: poly, popup: cols, tooltip: []};
  o.args = () => `label=${pyrepr(o.label)}, color=${pyrepr(o.color)}, placement=${pyrepr(o.under ? "under" : "over")}, popup=${pyrepr(o.popup)}` +
    (o.tooltip.length ? `, tooltip=${pyrepr(o.tooltip)}` : "");
  st.overlays.push(o);
  const div = o.div = document.createElement("div"); div.className = "ov";
  div.innerHTML = `<b>${name}</b><label>Label</label><input type="text" value="${o.label}"><label>Colour</label><input type="color" value="${o.color}">` +
    `<label class="inline"><input type="checkbox" ${o.under ? "checked" : ""}> Under the roads</label><label>Click popup columns</label><div class="list"></div>` +
    `<label>Hover tooltip columns</label><div class="list"></div>`;
  const [label, color, under] = div.querySelectorAll("input"), [pop, tip] = div.querySelectorAll(".list");
  label.onchange = () => { o.label = label.value; later(); };
  color.onchange = () => { o.color = color.value; later(); };
  under.onchange = () => { o.under = under.checked; later(); };
  checklist(pop, cols, cols, (v) => { o.popup = v; later(); });
  checklist(tip, cols, [], (v) => { o.tooltip = v; later(); });
  $("overlays").appendChild(div);
  later();
}
$("ovfile").onchange = async () => { for (const f of $("ovfile").files) addOverlay(f.name, await f.text(), f.name); };
for (const [k, f] of Object.entries(OVERLAY_SAMPLES)) {
  const l = document.createElement("label"); l.className = "inline";
  l.innerHTML = `<input type="checkbox"> ${k}`;
  l.querySelector("input").onchange = async (e) => {
    if (e.target.checked) addOverlay(f, await (await fetch(`samples/${f}`)).text(), `ui/studio/samples/${f}`);
    else { st.overlays.filter((o) => o.name === f).forEach((o) => o.div.remove()); st.overlays = st.overlays.filter((o) => o.name !== f); later(); }
  };
  $("ovsamples").appendChild(l);
}

// roadstyle studio in the browser: the knobs of the Python studio's Map page (src/roadstyle/studio/map.py), roadstyle's Rust engine in a Web
// Worker (worker.js: the look and stage 1 for each change of the knobs) and the map with the dashboard in an iframe (preview.html).
import {pythonCode, pyrepr} from "./code.js";

const $ = (id) => document.getElementById(id);
const SAMPLES = {"Södermalm driving": "sodermalm_driving", "Södermalm walking": "sodermalm_walking", "Södermalm cycling": "sodermalm_cycling"};
const OVERLAY_SAMPLES = {sensors: "sensors.geojson", zones: "zones.geojson"};
const CMAPS = ["viridis", "plasma", "magma", "cividis", "coolwarm", "RdYlGn_r"];
const OV_COLORS = ["#7c4dff", "#00bcd4", "#ff9800", "#e91e63"];
const ID_COLS = new Set(["id", "fid", "gid", "uid", "objectid"]);

// the state of the knobs
const st = {data: null, loader: "", palette: "amber", basemap: "", view3d: false, tiles: false, colours: {}, classes: null, minzoom: false,
            labels: true, arrows: true, popup: "curated", popupCols: [], hover: [], overlays: []};
let table = null, columns = [], allClasses = [], basemaps = [], gen = 0, dashKey = "";

// ---------------------------------------------------------------- the engine in its worker
const worker = new Worker(new URL("./worker.js", import.meta.url), {type: "module"});
let callId = 0;
const pending = new Map();
worker.onmessage = (e) => { const p = pending.get(e.data.id); pending.delete(e.data.id); e.data.ok ? p.ok(e.data) : p.no(new Error(e.data.error)); };
const call = (msg, transfer) => new Promise((ok, no) => { const id = ++callId; pending.set(id, {ok, no}); worker.postMessage({...msg, id}, transfer || []); });

// ---------------------------------------------------------------- what the preview asks for
window.studio = {
  dashboardOptions: () => ({basemaps, basemap: st.basemap, dashboard: {popup_mode: st.popup === "panel" ? "panel" : "popup", street_view: "window"}}),
  tile: async (url) => {                               // rs://<gen>/<source>/<z>/<x>/<y>, from the worker's Tiler
    const [g, source, z, x, y] = url.slice("rs://".length).split("/");
    if (+g !== gen) return new Uint8Array();
    return (await call({type: "tile", source, z: +z, x: +x, y: +y})).bytes;
  },
  previewReady: () => previewWaiters.splice(0).forEach((f) => f()),
  debug: () => ({table, columns, allClasses, st}),     // for a check in a browser (the tests), not for the preview
};
const previewWaiters = [];

// ---------------------------------------------------------------- the look's options, the code's keywords
// The knobs as the look's options (makeLook's input in the worker): render_edges' keywords that the engine reads.
function lookOptions(){
  // state "live": the global states stay in the expressions and the style has the dashboard's options (roadstyle:controls), as a page
  const args = {name: "roadstyle", state: "live"};
  if (st.view3d) args.view_3d = true;
  if (st.tiles) args.tiles = true;
  const co = colourOptions();
  if (co.length > 1) args.color_options = co;
  if (st.minzoom) args.minzoom = true;
  if (!st.labels) args.labels = false;
  if (!st.arrows) args.arrows = false;
  if (st.hover.length) args.tooltip = st.hover;
  if (st.overlays.length) args.overlays = st.overlays.map((o) => ({label: o.label, color: o.color, placement: o.under ? "under" : "over",
    popup: o.popup, ...(o.tooltip.length ? {tooltip: o.tooltip} : {}), fc: o.fc}));
  return {palette: st.palette, args};
}
// the colour options of the picked columns: a ramp from the 2nd to the 98th percentile (studio/common.py, _colour_opt's numeric case)
function colourOptions(){
  const out = [{name: "Class"}];
  for (const [col, cmap] of Object.entries(st.colours)) {
    const v = table.props.map((p) => p && p[col]).filter((x) => typeof x === "number" && isFinite(x)).sort((a, b) => a - b);
    if (!v.length) continue;
    const q = (f) => v[Math.min(v.length - 1, Math.max(0, Math.round(f * (v.length - 1))))];
    out.push({name: col, color_by: col, cmap, vmin: q(0.02), vmax: q(0.98), missing: "self"});
  }
  return out;
}
function codeKeywords(){
  const kw = {palette: st.palette, basemap: st.basemap};
  if (st.view3d) kw.view_3d = true;
  if (st.tiles) kw.tiles = true;
  const co = colourOptions();
  if (co.length > 1) kw.color_options = Object.fromEntries(co.map(({name, ...o}) => [name, o]));
  if (st.classes && st.classes.length !== allClasses.length) kw.include = st.classes;
  if (st.minzoom) kw.minzoom = true;
  if (!st.labels) kw.labels = false;
  if (!st.arrows) kw.arrows = false;
  const popup = {choose: st.popupCols, panel: "panel", all: "all", off: false}[st.popup];
  if (popup !== undefined) kw.road_popup = popup;
  if (st.hover.length) kw.tooltip = st.hover;
  if (st.overlays.length) kw.overlays = true;
  return kw;
}
// the road popup and tooltip as the dashboard reads them (the style's metadata roadstyle:interaction): the knob over the engine's own
function interaction(style){
  const it = {...(style.metadata["roadstyle:interaction"] || {})};
  if (st.popup === "choose") it.popup = st.popupCols;
  else if (st.popup === "all") it.popup = null;
  else if (st.popup === "off") it.popup = false;
  if (st.hover.length) it.tooltip = st.hover;
  style.metadata["roadstyle:interaction"] = it;
}

// ---------------------------------------------------------------- build: the engine, then the preview
let busy = false, again = false, timer = 0;
const later = () => { clearTimeout(timer); timer = setTimeout(build, 250); };
async function build(){
  if (!st.data) return;
  if (busy) { again = true; return; }
  busy = true; $("status").textContent = "making the map…";
  try {
    gen += 1;
    const r = await call({type: "build", options: lookOptions(), name: "roadstyle", tiles: st.tiles, gen,
                          keep: ["name", "highway", "edge_id"].concat(st.hover)});
    const t = JSON.parse(r.table), first = !table || t.props.length !== table.props.length;
    table = t;
    if (first) dataKnown();
    const b = bounds(table.bboxes);
    interaction(r.style);
    const key = [st.data.name, st.popup].join("|");             // the dashboard is made again for new data or another popup mode
    const fresh = key !== dashKey;
    if (fresh) { dashKey = key; await reloadPreview(); }
    await $("preview").contentWindow.show({style: r.style, table, files: r.files, fit: first || fresh ? [[b[0], b[1]], [b[2], b[3]]] : null});
    if (st.classes) $("preview").contentWindow.rs.setFilter({classes: st.classes});
    $("status").textContent = `${table.props.length.toLocaleString()} roads, made in ${(r.ms / 1000).toFixed(1)} s`;
    $("status").dataset.built = gen;                            // the number of the last build (a test waits for it)
    $("code").textContent = pythonCode(codeKeywords(), st.loader, st.overlays.map((o) => ({path: o.path, args: o.args()})));
  } catch (e) {
    $("status").innerHTML = `<span class="err">The map failed: ${e.message}</span>`;
  }
  busy = false;
  if (again) { again = false; build(); }
}
function reloadPreview(){
  return new Promise((ok) => { previewWaiters.push(ok); $("preview").src = "preview.html?" + Date.now(); });
}
function bounds(bbs){
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const x of bbs) if (x) { b[0] = Math.min(b[0], x[0]); b[1] = Math.min(b[1], x[1]); b[2] = Math.max(b[2], x[2]); b[3] = Math.max(b[3], x[3]); }
  return b;
}

// ---------------------------------------------------------------- the knobs that the data decides
function dataKnown(){
  const keys = new Set();
  for (const p of table.props.slice(0, 2000)) if (p) for (const k of Object.keys(p)) if (k[0] !== "_" && k !== "lvl") keys.add(k);
  columns = [...keys];
  allClasses = [...new Set(table.props.map((p) => p && p.highway).filter((h) => h != null))].sort();
  st.classes = null; st.colours = {}; st.popupCols = columns.filter((c) => ["name", "edge_id", "highway", "lanes", "maxspeed_kmh"].includes(c));
  $("count").textContent = `${table.props.length.toLocaleString()} edges`;
  // colour by: numeric columns with many values (not the id columns); the others wait for the engine's ramp steps
  const numeric = (c) => table.props.some((p) => p && typeof p[c] === "number");
  const distinct = (c) => new Set(table.props.slice(0, 5000).map((p) => p && p[c]).filter((v) => v != null)).size;
  $("colours").innerHTML = "";
  for (const c of columns) {
    if (ID_COLS.has(c.toLowerCase()) || c.toLowerCase().endsWith("_id")) continue;
    const n = distinct(c), ramp = numeric(c) && n > 12;
    if (!ramp && !(n > 0 && n <= 12)) continue;
    const row = document.createElement("div");
    row.innerHTML = `<label class="inline"><input type="checkbox" ${ramp ? "" : "disabled"}> ${c}</label>` +
      (ramp ? `<select hidden>${CMAPS.map((m) => `<option>${m}</option>`).join("")}</select>` : `<span class="note">(categories: later)</span>`);
    const [cb, sel] = [row.querySelector("input"), row.querySelector("select")];
    if (sel) {
      sel.selectedIndex = (Object.keys(st.colours).length + 1) % CMAPS.length;
      cb.onchange = () => { sel.hidden = !cb.checked; if (cb.checked) st.colours[c] = sel.value; else delete st.colours[c]; later(); };
      sel.onchange = () => { st.colours[c] = sel.value; later(); };
    }
    $("colours").appendChild(row);
  }
  checklist($("classes"), allClasses, allClasses, (v) => { st.classes = v; $("preview").contentWindow.rs.setFilter({classes: v}); code(); });
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
const code = () => { $("code").textContent = pythonCode(codeKeywords(), st.loader, st.overlays.map((o) => ({path: o.path, args: o.args()}))); };

// ---------------------------------------------------------------- the data
async function loadRoads(bytes, name, loader){
  st.data = {name}; st.loader = loader; table = null;
  $("status").textContent = "reading the roads…";
  await call({type: "roads", bytes}, [bytes]);
  build();
}
for (const k of Object.keys(SAMPLES)) $("sample").add(new Option(k, k));
$("sample").onchange = async () => {
  const f = SAMPLES[$("sample").value];
  const r = await fetch(`samples/${f}.parquet`);
  if (!r.ok) { $("status").innerHTML = `<span class="err">samples/${f}.parquet is not there: make it with ui/studio/make_samples.py</span>`; return; }
  loadRoads(await r.arrayBuffer(), $("sample").value, `edges = gpd.read_file("ui/studio/samples/${f}.geojson")`);
};
$("file").onchange = async () => {
  const f = $("file").files[0]; if (!f) return;
  loadRoads(await f.arrayBuffer(), f.name, `edges = gpd.read_parquet("${f.name}")`);
};

// ---------------------------------------------------------------- the look and the other knobs
const knob = (id, key, prop = "value") => { $(id).onchange = () => { st[key] = $(id)[prop]; later(); }; };
knob("palette", "palette"); knob("view3d", "view3d", "checked"); knob("tiles", "tiles", "checked"); knob("minzoom", "minzoom", "checked");
knob("labels", "labels", "checked"); knob("arrows", "arrows", "checked");
$("popup").onchange = () => { st.popup = $("popup").value; $("popupcols").hidden = st.popup !== "choose"; later(); };
$("basemap").onchange = () => { st.basemap = $("basemap").value; $("preview").contentWindow.rs.setBasemap(st.basemap); code(); };
$("copy").onclick = () => navigator.clipboard.writeText($("code").textContent);

// the base maps: one list for Python and the studio (src/roadstyle/data/basemaps.json, the look session's)
fetch("../../src/roadstyle/data/basemaps.json").then((r) => r.ok ? r.json() : Promise.reject(new Error(r.status))).then((list) => {
  basemaps = list;
  for (const b of list) $("basemap").add(new Option(b.label, b.key));
  st.basemap = list.length ? list[0].key : "";
}).catch(() => {
  basemaps = [];
  $("bmnote").innerHTML = '<span class="err">The base-map list (src/roadstyle/data/basemaps.json) is not there yet: no base map.</span>';
}).finally(() => $("sample").onchange());

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

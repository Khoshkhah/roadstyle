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
let table = null, columns = [], numeric = new Set(), allClasses = [], gen = 0, dashKey = "";
let BM = {basemaps: [], switcher: []}, background = null, colourOpts = [{name: "Class"}];   // basemaps.json; the look's canvas colours; the last options

// ---------------------------------------------------------------- the engine in its worker
const worker = new Worker(new URL("./worker.js", import.meta.url), {type: "module"});
let callId = 0;
const pending = new Map();
worker.onmessage = (e) => { const p = pending.get(e.data.id); pending.delete(e.data.id); e.data.ok ? p.ok(e.data) : p.no(new Error(e.data.error)); };
const call = (msg, transfer) => new Promise((ok, no) => { const id = ++callId; pending.set(id, {ok, no}); worker.postMessage({...msg, id}, transfer || []); });

// ---------------------------------------------------------------- what the preview asks for
window.studio = {
  dashboardOptions: () => ({basemaps: pageBasemaps(), basemap: st.basemap, dashboard: {popup_mode: st.popup === "panel" ? "panel" : "popup", street_view: "window"}}),
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
function lookOptions(co){
  // state "live": the global states stay in the expressions and the style has the dashboard's options (roadstyle:controls), as a page
  const args = {name: "roadstyle", state: "live"};
  if (st.view3d) args.view_3d = true;
  if (st.tiles) args.tiles = true;
  // the look's options are JSON: a value is a text key there, as in Python's json.dumps of the dict
  if (co.length > 1) args.color_options = co.map((o) => o.colors ? {...o, colors: Object.fromEntries([...o.colors].map(([k, c]) => [String(k), c]))} : o);
  if (st.minzoom) args.minzoom = true;
  if (!st.labels) args.labels = false;
  if (!st.arrows) args.arrows = false;
  if (st.hover.length) args.tooltip = st.hover;
  if (st.overlays.length) args.overlays = st.overlays.map((o) => ({label: o.label, color: o.color, placement: o.under ? "under" : "over",
    popup: o.popup, ...(o.tooltip.length ? {tooltip: o.tooltip} : {}), fc: o.fc}));
  return {palette: st.palette, args};
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
function codeKeywords(){
  const kw = {palette: st.palette, basemap: st.basemap};
  if (st.view3d) kw.view_3d = true;
  if (st.tiles) kw.tiles = true;
  if (colourOpts.length > 1) kw.color_options = Object.fromEntries(colourOpts.map(({name, ...o}) => [name, o]));
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
    if (table) colourOpts = await colourOptions();
    const r = await call({type: "build", options: lookOptions(colourOpts), name: "roadstyle", tiles: st.tiles, gen,
                          keep: ["name", "highway", "edge_id"].concat(st.hover)});
    const t = JSON.parse(r.table), first = !table || t.props.length !== table.props.length;
    table = t; background = r.background;
    if (first) dataKnown();
    const b = bounds(table.bboxes);
    interaction(r.style);
    const key = [st.data.name, st.popup, st.basemap].join("|"); // the dashboard is made again for new data, a popup mode, a base map
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
  // columns: the file's own columns (the worker's answer to "roads"), as the Python studio lists the GeoDataFrame's
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
async function loadRoads(bytes, kind, name, loader){
  st.data = {name}; st.loader = loader; table = null; colourOpts = [{name: "Class"}];
  $("status").textContent = "reading the roads…";
  try { columns = (await call({type: "roads", bytes, kind}, [bytes])).columns.filter((c) => c !== "geometry"); }
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
  const f = $("file").files[0]; if (!f) return;
  const parquet = /\.(geo)?parquet$/i.test(f.name);
  loadRoads(await f.arrayBuffer(), parquet ? "parquet" : "geojson", f.name,
            parquet ? `edges = gpd.read_parquet("${f.name}")` : `edges = gpd.read_file("${f.name}")`);
};

// ---------------------------------------------------------------- the look and the other knobs
const knob = (id, key, prop = "value") => { $(id).onchange = () => { st[key] = $(id)[prop]; later(); }; };
knob("palette", "palette"); knob("view3d", "view3d", "checked"); knob("tiles", "tiles", "checked"); knob("minzoom", "minzoom", "checked");
knob("labels", "labels", "checked"); knob("arrows", "arrows", "checked");
$("popup").onchange = () => { st.popup = $("popup").value; $("popupcols").hidden = st.popup !== "choose"; later(); };
$("basemap").onchange = () => { st.basemap = $("basemap").value; later(); };   // the page's list starts with the active one: a new dashboard
$("copy").onclick = () => navigator.clipboard.writeText($("code").textContent);

// the base maps: one list for Python and the studio (src/roadstyle/data/basemaps.json). The menu has all of them, as the Python studio
// (rs.BASEMAPS); the page's switcher has the active one and then the default set.
// TODO(R3): a copy of render_web._page_basemaps, _tiles and _bg_color. Remove it in the change that uses the page writer.
function pageBasemaps(){
  const by = Object.fromEntries(BM.basemaps.map((b) => [b.key, b])), active = by[st.basemap] || BM.basemaps[0];
  if (!active) return [];
  const tiles = (b) => !b.url ? [] : b.url.includes("{s}") ? [...(b.subdomains || "a")].map((s) => b.url.replace("{s}", s).replace("{r}", ""))
                                                            : [b.url.replace("{r}", "")];
  const bg = (b) => b.bg.startsWith("#") ? b.bg : background[b.is_dark ? "dark" : "light"];
  return [active, ...BM.switcher.filter((k) => k !== active.key && by[k]).map((k) => by[k])]
    .map((b) => ({key: b.key, label: b.label, tiles: tiles(b), bg: bg(b), maxzoom: b.maxzoom, attr: b.attr}));
}
fetch("../../src/roadstyle/data/basemaps.json").then((r) => r.ok ? r.json() : Promise.reject(new Error(`basemaps.json: ${r.status}`))).then((j) => {
  BM = j;
  for (const b of BM.basemaps) $("basemap").add(new Option(b.label, b.key));
  st.basemap = BM.basemaps.length ? BM.basemaps[0].key : "";
  $("sample").onchange();
}).catch((e) => { $("bmnote").innerHTML = `<span class="err">The base maps: ${e.message}</span>`; });

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

// The level editor as a module that any page can hold (the level editor's files: roadstyle's level area; docs/rust/browser.md, "The level
// editor in a page"): levelEditor({map, container, pkg, store}) loads the area's files from `store`, solves in the page (the roadstyle-wasm
// package `pkg`, initialised: LevelArea, resolveLook, styleSources, tilesOfSources), draws the area on `map` (a MapLibre map of the host, else
// one of its own in `container`) and puts the panel (static/level_editor.html) in `container`. It saves your edits, heads and caps and the
// solved levels.csv to `store`, and after each solve it sends the event "solved" ({levelsCsv, levelsInfo, draw()}: draw gives the map's
// table, GeoParquet, one row for each edge) so that the host can apply it. A store is {load(name, bytes) -> {body, mtime} | null,
// save(name, text | bytes)} with an optional `name` (the area's, shown in the panel) and `key`: httpStore for roadstyle serve,
// browserStore for a page with no server.
// The option `levels` ({csv, edge_hash}: the levels that the host's map has) is the answer to start from with no solve; saveArea and
// areaIsFor let a page make the area only when its edges changed (docs/rust/browser.md, "The level editor in a page").
// The option `host` ({replaceRoads(rows) -> Promise, edgeIdCol = "edge_id"}, with `map` and `dashboard`): the editor draws no map. It uses
// the host's roads, road table (window.RS_SIDE, which must keep the edge id field) and pick; an apply gives replaceRoads the levels.csv
// rows (one object for each edge, the CSV's fields as text) of the edges whose levels, heads or caps changed, and the host draws them.
import {rsDashboard} from "../index.js";
import {style as dashboardStyle} from "../core.js";
import {caller} from "../worker/call.js";

const COLS = ["relation", "a", "b", "a_end", "b_end", "enabled"];
const EMPTY = COLS.join(",") + "\n";
// the keywords of the editor's map (level_editor.Area._render)
const LOOK = {state: "live", edge_id_col: "edge", directed_col: "directed", driving_col: "driving", road_popup: false, select_color: "rgba(0,0,0,0)",
  filter_control: false, tunnel_control: false, casing_start_col: "casing_start", casing_level_col: "casing_level", casing_end_col: "casing_end",
  fill_level_col: "fill_level", cap_start_col: "cap_start", cap_end_col: "cap_end", head_start_m_col: "head_start_m", head_end_m_col: "head_end_m"};
const KEEP = ["edge", "road", "name", "highway", "edge_ref", "modes", "s_lon", "s_lat", "e_lon", "e_lat"];   // the road fields in the tiles
const PART = {start: "start head", main: "main", end: "end head"};

/** The store of `roadstyle serve`: the area under `base` (GET), saved with a PUT; the area's name from the header X-Area. */
export function httpStore(base = "/area/"){
  const s = {key: base, name: "area",
    async load(name, bytes){
      const r = await fetch(base + name, {cache: "no-store"});
      if(!r.ok) return null;
      if(r.headers.get("X-Area")) s.name = r.headers.get("X-Area");
      return {body: bytes ? new Uint8Array(await r.arrayBuffer()) : await r.text(), mtime: +r.headers.get("X-Mtime") || 0};
    },
    async save(name, data){
      const r = await fetch(base + name, {method: "PUT", body: data});
      if(!r.ok) throw new Error(`${name} not saved (${r.status}): this host saves nothing; open the area with roadstyle serve`);
    }};
  return s;
}

/** The store of a page with no server: the area's files in this browser under `key`, in the origin's private file system (the texts
 * too: pairs.csv of a large area is more than localStorage holds), each with the time it was saved (seconds, in localStorage). */
export function browserStore(key, name = key){
  const at = n => `lv:${key}:${n}`;
  const dir = async () => (await navigator.storage.getDirectory()).getDirectoryHandle("lv-" + key.replace(/[^\w.-]/g, "_"), {create: true});
  const write = async (n, data) => { const w = await (await (await dir()).getFileHandle(n, {create: true})).createWritable(); await w.write(data); await w.close(); };
  return {key, name,
    async load(n, bytes){
      const old = localStorage.getItem(at(n));                    // a text that an older version kept in localStorage: moved once
      if(old != null){ await write(n, old); localStorage.removeItem(at(n)); }
      let f;
      try { f = await (await (await dir()).getFileHandle(n)).getFile(); }
      catch(e){ if(e.name === "NotFoundError") return null; throw e; }
      return {body: bytes ? new Uint8Array(await f.arrayBuffer()) : await f.text(), mtime: +(localStorage.getItem(at(n) + "@mtime") || 0)};
    },
    async save(n, data){
      await write(n, data);
      localStorage.setItem(at(n) + "@mtime", String(Date.now() / 1000));
    }};
}

/** The files of a new level area in the store (`area`: makeArea's AreaFiles): roads.parquet, pairs.csv, edits.csv when the store has none
 * (the edits of an earlier session stay), and edges.json with `edgeHash`, the area's edges by roadstyle's edge_hash (duckOSM's
 * edge_levels_meta.edge_hash), for areaIsFor. */
export async function saveArea(store, area, edgeHash){
  await store.save("roads.parquet", area.roads);
  await store.save("pairs.csv", area.pairs);
  if(!(await store.load("edits.csv"))) await store.save("edits.csv", area.edits);
  await store.save("edges.json", JSON.stringify({edge_hash: edgeHash}));
}

/** The store has the level area of these edges (`edgeHash`, as saveArea took it): a page makes the area again only when its edges changed. */
export async function areaIsFor(store, edgeHash){
  const f = await store.load("edges.json");
  return !!f && JSON.parse(f.body).edge_hash === edgeHash;
}

function csvRows(text){                                          // the rows of a CSV text with a header, as objects (pandas' quotes)
  const lines = (text || "").split(/\r?\n/).filter(l => l.trim());
  const split = l => { const out = []; let cur = "", q = false;
    for(let i = 0; i < l.length; i++){ const c = l[i];
      if(c === '"' && q && l[i + 1] === '"'){ cur += '"'; i++; } else if(c === '"') q = !q; else if(c === "," && !q){ out.push(cur); cur = ""; } else cur += c; }
    out.push(cur); return out; };
  if(!lines.length) return [];
  const head = split(lines[0]);
  return lines.slice(1).map(l => { const f = split(l); return Object.fromEntries(head.map((h, i) => [h, f[i] ?? ""])); });
}
const cell = v => /[",\n]/.test(String(v ?? "")) ? `"${String(v).replaceAll('"', '""')}"` : String(v ?? "");
const toCsv = (rows, cols = COLS) => cols.join(",") + "\n" + rows.map(r => cols.map(c => cell(r[c])).join(",")).join("\n") + (rows.length ? "\n" : "");

/** The level editor on `map` (or a map of its own in `container`), with the panel in `container`; see the file's head. A page has one
 * dashboard (its state is the module's): on a host map that has one, give it as `dashboard` with the `prefix` it was made with; the
 * editor then draws its roads with that prefix (take your own roads off first) and gives the dashboard its style (setStyle). Gives an
 * EventTarget (event "solved") with `map`, `area` (the LevelArea), `download(name)` (edits.csv, heads.csv, caps.csv or levels.csv as they
 * are now), `files` (those names) and `answer()` (the last answer of the solver). */
export async function levelEditor({map = null, container = document.body, pkgUrl, store, maplibregl: ml = globalThis.maplibregl, dashboard = null,
                                   prefix = dashboard ? null : "lv-rs-", layout = "auto", levels: given = null, host = null,
                                   colors = {}}){
// the picked roads and the hover (`colors`: {select, hover, second}): road 1 in the selection's colour, road 2 darker, the hover lighter
const COLORS = {select: "#7c4dff", hover: "#b388ff", second: "#4527a0", ...colors};
if(!["auto", "sheet", "side"].includes(layout)) throw new Error(`level editor: layout must be "auto", "sheet" or "side", not ${JSON.stringify(layout)}`);
if(map && !dashboard && window.rs)
  throw new Error("level editor: this page has a dashboard (window.rs): give it as levelEditor({dashboard, prefix}), so that the editor uses it; a second dashboard takes the first one's state");
if(host && !(map && dashboard && typeof host.replaceRoads === "function"))
  throw new Error("level editor: the option host needs the host's map and dashboard, and host.replaceRoads(rows)");
if(dashboard && !prefix && !host)
  throw new Error("level editor: give the prefix of your dashboard (its layers and sources); the editor takes the layers with it off the map before it draws");
if(map && window.map instanceof ml.Map && window.map !== map)     // (an element with the id "map" is window.map too: not a map)
  throw new Error("level editor: window.map is another map; the panel draws on window.map");
const P = map ? prefix : "rs-";                                  // a host map: the editor's layers and sources with the prefix given
// the road table's fields: what the page reads of a row (the dashboard's reads.json, "table"), live data's id and the road that a click
// picks (the other fields of a road are a large part of the table's text, which the page parses after each answer)
const reads = await fetch(new URL("../reads.json", import.meta.url));
if(!reads.ok) throw new Error(`level editor: the dashboard's reads.json (${reads.status})`);
const TABLE = [...(await reads.json()).table, LOOK.edge_id_col, "road"];
// the engine in a worker (level_worker.js): the solve, the map and its tiles do not stop the page
const worker = new Worker(new URL("./level_worker.js", import.meta.url), {type: "module"});
const call = caller(worker);
await call({type: "init", pkgUrl: String(new URL(pkgUrl, location.href)), look: JSON.stringify({args: {...LOOK, hover_color: COLORS.hover}})});
const flat = (r) => r.levels.flat();
const hostSide = window.RS_SIDE, hadApi = window.lvApi;          // the host's, for destroy
const events = new EventTarget();
const get = (n, bytes) => store.load(n, bytes);
const [roadsF, pairsF, editsF, headsF, capsF, levelsF, infoF] = await Promise.all([get("roads.parquet", true), get("pairs.csv"), get("edits.csv"),
  get("heads.csv"), get("caps.csv"), get("levels.csv"), get("levels_info.json")]);
if(!roadsF || !pairsF) throw new Error("the store has no roads.parquet or pairs.csv: make the area first (makeArea, or roadstyle levels make)");
const roadsBytes = roadsF.body.slice();
// the inputs of a solve, by their content (the SHA-256 of roads.parquet, pairs.csv and edits.csv): levels.csv is for them when its
// levels_info.json has the same key, also after a page wrote the same area again (a file's time says nothing then). heads.csv and caps.csv
// are drawing only: they are not inputs of the solve.
const sha = async d => [...new Uint8Array(await crypto.subtle.digest("SHA-256", typeof d === "string" ? new TextEncoder().encode(d) : d))]
  .map(b => b.toString(16).padStart(2, "0")).join("");
const areaKey = `${await sha(roadsBytes)}:${await sha(pairsF.body)}`;
const inputsKey = async edits => `${areaKey}:${await sha(edits)}`;
const order = (await call({type: "open", roads: roadsBytes.buffer, pairs: pairsF.body}, [roadsBytes.buffer])).roads;   // the road ids, in the roads' order
// pairs.csv's lines: the panel's found rules of a road come from them when it asks (relations); the open does not parse them
const pairLines = pairsF.body.split(/\r?\n/).filter(l => l.trim());
// what the page knows of the roads, asked from the worker when the panel needs them (need): any edge id -> its road id, and a road's
// facts (with its levels and ends). A new answer clears the facts.
const roadOf = Object.fromEntries(order.map(r => [r, r]));
let facts = {};
async function need(ids){
  ids = [...new Set(ids.filter(x => x != null && x !== "").map(String))];
  const miss = ids.filter(x => !(x in roadOf));
  if(miss.length){ const rs_ = (await call({type: "roadOf", ids: miss})).roads; miss.forEach((x, i) => { if(rs_[i]) roadOf[x] = rs_[i]; }); }
  const roads = [...new Set(ids.map(x => roadOf[x]).filter(r => r != null && !(r in facts)))];
  if(!roads.length) return;
  for(const f of JSON.parse((await call({type: "facts", ids: roads, heads: headsText, caps: capsText})).facts)) facts[f.road] = {...f, levels: res.levels[f.i]};
}
let editsText = editsF ? editsF.body : EMPTY, headsText = headsF ? headsF.body : "", capsText = capsF ? capsF.body : "";
const SAVED = "lv-saved:" + (store.key || location.pathname);    // the edits saved before this session (the Python server keeps it)
let saved = +(sessionStorage.getItem(SAVED) ?? csvRows(editsText).length);
let res = null;                                                  // the last answer of the solver (JSON of LevelArea)
let lastCsv = null;                                              // levels.csv of `res` as save wrote it (host: the rows before an apply)

// --- the answer to start from: levels.csv when it was solved for these inputs (inputsKey) and has every edge, else a solve
// each road's 4 numbers in its own way from a levels.csv text (one row for each edge; only the other way: its heads swapped), or null
// when a road of the area has none
async function levelsOf(text){
  const l = (await call({type: "levelsOf", csv: text})).levels;
  return l ? order.map((_, i) => Array.from(l.subarray(4 * i, 4 * i + 4))) : null;
}
async function fromStored(){
  if(!levelsF || !infoF) return null;
  if(JSON.parse(infoF.body).inputs !== await inputsKey(editsText)) return null;
  const levels = await levelsOf(levelsF.body);
  if(!levels) return null;
  const info = JSON.parse(infoF.body);
  await call({type: "startFrom", levels: levels.flat(), parts: (info.given_up_parts || []).map(p => p.join("|")), orders: (info.orders_not_kept || []).length,
    near: (info.near || []).length, crossings: (info.crossings_not_kept || []).length});
  return {levels, given_up: info.given_up || [], given_up_parts: info.given_up_parts || [], near: info.near || [], orders_not_kept: info.orders_not_kept || [],
    crossings_not_kept: info.crossings_not_kept || [],
    info: {pairs: info.pairs, meets: info.meets, order_pairs: info.order_pairs, order_violations: info.order_violations, near_warnings: info.near_warnings},
    resolve: {how: "stored"}};
}
async function save(newRes){                                       // levels.csv and levels_info.json of an answer; then the host hears of it
  const [heads, caps] = [headsText, capsText];
  const levelsCsv = lastCsv = (await call({type: "levelsCsv", levels: flat(newRes), heads, caps})).csv;
  const info = JSON.stringify({...newRes.info, given_up: newRes.given_up, given_up_parts: newRes.given_up_parts, near: newRes.near,
    orders_not_kept: newRes.orders_not_kept, crossings_not_kept: newRes.crossings_not_kept || [], inputs: await inputsKey(editsText)});
  await store.save("levels.csv", levelsCsv);
  await store.save("levels_info.json", info);
  events.dispatchEvent(new CustomEvent("solved", {detail: {levelsCsv, levelsInfo: info,
    draw: async () => (await call({type: "draw", levels: flat(newRes), heads, caps})).bytes}}));
}
// the levels that the host's map has (the option `levels`: {csv: levels.csv text with edge, casing_start, casing_level, casing_end and
// fill_level, edge_hash: duckOSM's edge_levels_meta.edge_hash}): the answer to start from, with no solve, when they are for the area's
// edges (roadstyle's edge_hash: sha256 of the sorted edge ids, 8 bytes each, little endian; the first 32 hex characters) and have one
// row for each; else the whole area is solved and the answer says why (resolve.why). The rules that they do not keep are not known
// without a solve: the counts of the pairs come from pairs.csv, the order wishes and near rules not kept are null.
const edgeHash = async () => (await call({type: "edgeHash"})).hash;
let givenWhy = null;
async function fromGiven(){
  if(!given) return null;
  if(given.edge_hash !== await edgeHash()){ givenWhy = "the map's levels are for other edges (edge_hash): solved the whole area"; return null; }
  const levels = await levelsOf(given.csv);
  if(!levels){ givenWhy = "the map's levels have no row for some edges of the area: solved the whole area"; return null; }
  await call({type: "startFrom", levels: levels.flat(), parts: [], orders: 0, near: 0, crossings: 0});
  const at = pairLines[0].split(",").indexOf("relation");
  const n = rel => pairLines.reduce((k, l, i) => k + (i > 0 && l.split(",")[at] === rel), 0);
  return {levels, given_up: [], given_up_parts: [], near: [], orders_not_kept: [],
    info: {pairs: n("stack"), meets: n("meet"), order_pairs: n("order"), order_violations: null, near_warnings: null}, resolve: {how: "given"}};
}
res = await fromStored() || await fromGiven();
if(res?.resolve.how === "given"){ try { await save(res); } catch(e){ console.warn(e.message); } }        // the next open starts from the store
if(!res){
  res = JSON.parse((await call({type: "solve", edits: editsText})).answer);
  if(givenWhy) res.resolve = {...res.resolve, why: givenWhy};
  try { await save(res); } catch(e){ console.warn(e.message); }
}

const stats = () => ({area: store.name || "area", roads: order.length,
  ...res.info, given_up: res.given_up});

// --- the map: the engine's tiles of one row for each edge, a new generation for each answer
async function build(){
  const b = await call({type: "build", levels: flat(res), heads: headsText, caps: capsText, keep: KEEP, table: TABLE});
  window.RS_SIDE = JSON.parse(new TextDecoder().decode(b.table));
  document.dispatchEvent(new CustomEvent("rs:tableready"));
  return ownSources(JSON.parse(b.style));
}
// the editor's sources with names of their own ("lv-roads", ...; on the map with the prefix P): a host's source of the same name (one that
// its base map's layers share with its roads) stays. The layer ids stay the dashboard's (it finds them by its prefix), and the roles in
// roadstyle:sources name the new sources.
function ownSources(st){
  const name = id => "lv-" + id;
  st.sources = Object.fromEntries(Object.entries(st.sources).map(([id, src]) => [name(id), src]));
  for(const l of st.layers) if(l.source) l.source = name(l.source);
  for(const r of Object.values((st.metadata || {})["roadstyle:sources"] || {})) if(r.source) r.source = name(r.source);
  return st;
}
const own = !map;                                                // no host map: the editor's own, on the area's box
const added = ["road", "s_lon", "s_lat", "e_lon", "e_lat"];      // host: the fields that the panel reads, put on the host's road table
const mine = {layers: [], sources: [], images: []};              // what the editor put on the map
const taken = {layers: [], sources: {}, order: [], style: null};  // the host's roads that the editor took off, for destroy
let rs = dashboard, showRoads = null;
// host: each row of the host's road table gets its road and its line's ends (the panel's end marks), again when the host gives a new table
async function addFields(){
  const t = window.RS_SIDE, col = host.edgeIdCol || "edge_id";
  if(!t || !t.props) throw new Error("level editor: the host has no road table (window.RS_SIDE)");
  if(t.lvFields) return;
  t.lvFields = true;
  const roads = (await call({type: "roadOf", ids: t.props.map(p => p ? String(p[col]) : "")})).roads;
  // a table without lines: the host's endsOf() gives 4 numbers for each row (the engine's roadEnds(): start lon, lat, end lon, lat)
  const ends = !t.lines && t.endsOf ? await t.endsOf() : null;
  t.props.forEach((p, i) => {
    const r = p && roads[i], c = t.lines && t.lines[i];
    if(!r) return;
    p.road = r;
    if(c && c.length){ [p.s_lon, p.s_lat] = c[0]; [p.e_lon, p.e_lat] = c[c.length - 1]; }
    else if(ends && !Number.isNaN(ends[4 * i])) [p.s_lon, p.s_lat, p.e_lon, p.e_lat] = ends.subarray(4 * i, 4 * i + 4);
  });
}
if(host){                                                        // the host's map and pick stay as they are
  await addFields();
  window.map = map;
} else {
  const style = await build();
  // the editor's own tiles (a host's rs:// stays its own), cut in the worker
  ml.addProtocol("lv", async (params) => ({data: (await call({type: "tile", url: params.url})).bytes}));
  // the camera: the area's box (the road table's boxes)
  const bb = window.RS_SIDE.bboxes.filter(Boolean).reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])],
    [180, 90, -180, -90]);
  if(own){
    const div = document.createElement("div");
    div.style.cssText = "position:absolute;inset:0";
    container.appendChild(div);
    map = new ml.Map({container: div, style: "https://tiles.openfreemap.org/styles/positron", bounds: [[bb[0], bb[1]], [bb[2], bb[3]]],
      attributionControl: {compact: true}});
    map.addControl(new ml.NavigationControl({visualizePitch: true}));
    map.addControl(new ml.ScaleControl({maxWidth: 120, unit: "metric"}), "bottom-left");
  } else map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {padding: 40, duration: 0});
  window.map = map;                                                // the panel (level_editor.html) draws on the global map
  // the page's one dashboard: the host's, else one for the editor (the road fields: the road table RS_SIDE)
  rs = dashboard || rsDashboard(map, {style: null, prefix: P, tiles: true, simple: "roads-simple", edge_id_col: "edge", basemap_switcher: false,
    select_color: "rgba(0,0,0,0)"});
  let first = true;
  showRoads = async function(st){                                      // the roads style on the map (prefix P), in place of the one before
    const layers = st.layers.map(l => P + l.id), sources = Object.keys(st.sources).map(id => P + id);
    // off: the editor's own layers, the layers with an id it adds, and the first time the host dashboard's roads (the layers of the roles of
    // its style's roadstyle:sources: not its base map)
    // (a role is a source and its source layer: a host's base map can share the roads' tile source with other source layers)
    const role = (source, layer) => source + "|" + (layer || "");
    const roles = first && dashboard ? Object.values((dashboardStyle?.metadata || {})["roadstyle:sources"] || {}).map(r => role(P + r.source, r.layer)) : [];
    const off = new Set([...mine.layers, ...layers, ...map.getStyle().layers.filter(l => roles.includes(role(l.source, l["source-layer"]))).map(l => l.id)]);
    if(first && dashboard){                                          // the host's, as they are, to put back
      const now = map.getStyle();
      Object.assign(taken, {layers: now.layers.filter(l => off.has(l.id)), order: now.layers.map(l => l.id), style: dashboardStyle,
        sources: Object.fromEntries(sources.filter(id => now.sources[id]).map(id => [id, now.sources[id]]))});
    }
    for(const id of off) if(map.getLayer(id)) map.removeLayer(id);
    for(const id of new Set([...mine.sources, ...sources])) if(map.getSource(id) && !map.getStyle().layers.some(l => l.source === id)) map.removeSource(id);
    [mine.layers, mine.sources, first] = [layers, sources, false];
    for(const [id, im] of Object.entries(st.metadata["roadstyle:images"] || {}))
      if(!map.hasImage(P + id)){ map.addImage(P + id, (await map.loadImage(im.url)).data, {sdf: im.sdf, pixelRatio: im.pixelRatio}); mine.images.push(P + id); }
    // a live style's global state (rs_colors, rs_co, ...): its start values, as a style with them would set them (the base map has none)
    for(const [k, v] of Object.entries(st.state || {})) map.setGlobalStateProperty(k, v.default ?? null);
    for(const [id, src] of Object.entries(st.sources)) map.addSource(P + id, src);
    for(const l of st.layers){
      const layer = JSON.parse(JSON.stringify(l).replaceAll('"oneway"', `"${P}oneway"`));
      map.addLayer({...layer, id: P + l.id, source: P + l.source}, map.getLayer("lv-ends") ? "lv-ends" : undefined);   // under the panel's end marks
    }
    // the taps of a finger: a wide line on the roads that draws nothing (the sheet's layout picks a road with it)
    map.addLayer({id: P + "lv-tap", type: "line", source: P + "lv-roads", "source-layer": "simple", paint: {"line-width": 28, "line-opacity": 0}},
      map.getLayer("lv-ends") ? "lv-ends" : undefined);
    mine.layers.push(P + "lv-tap");
    rs.setStyle(st);
  }
  // the style loaded: a host map's load event can be over, and isStyleLoaded false a moment while it loads an image, with no event after
  while(!map.isStyleLoaded()) await new Promise(ok => setTimeout(ok, 50));
  await showRoads(style);
  await map.once("idle");                                          // the roads style in place: the panel starts on a loaded style
}

// --- the editor's API in the page (roadstyle's level_editor.Area): the same answers as the Python server's /api/...
const name = r => { const f = facts[r] || {}; return (f.name || f.highway || "road") + (f.edge_ref ? ` [${f.edge_ref}]` : ` [${r}]`); };
function say(r){
  const nm = x => name(roadOf[x] ?? x);
  const txt = r.relation === "meet" ? `${nm(r.a)} (${r.a_end}) joins ${nm(r.b)} (${r.b_end})`
    : r.relation === "order" ? `${nm(r.a)}'s fill after ${nm(r.b)}'s`
    : `${nm(r.a)}'s ${PART[r.a_end] || r.a_end} over ${nm(r.b)}` + (r.relation === "near" ? " (near only)" : "");
  return txt + (r.own ? " · yours" : "enabled" in r ? "" : " · found");
}
const editRows = () => csvRows(editsText).map(r => Object.fromEntries(COLS.map(c => [c, r[c] ?? ""])));
async function rows(){
  const e = editRows();
  await need(e.flatMap(r => [r.a, r.b]));
  return e.map((r, i) => ({...r, index: i, section: i < saved ? "saved" : "new", ra: roadOf[r.a] ?? r.a, rb: roadOf[r.b] ?? r.b}));
}
async function roadsOf(rs_){
  const ids = [...new Set(rs_)];
  await need(ids);
  return Object.fromEntries(ids.map(x => [x, facts[x] || {road: x}]));
}
// the found rules of a road: the lines of pairs.csv that name it, parsed
const pairsOf = r => csvRows([pairLines[0], ...pairLines.slice(1).filter(l => ("," + l + ",").includes("," + r + ","))].join("\n"));
async function relations(a, b){
  await need([a, b]);
  const ra = roadOf[a], rb = b ? roadOf[b] : null;
  if(ra == null || (b && rb == null)) throw new Error("unknown road");
  const mine = (x, y) => (x === ra && (rb == null || y === rb)) || (y === ra && (rb == null || x === rb));
  const found = pairsOf(ra).filter(r => mine(r.a, r.b)).map(r => ({...r, section: "found", ra: r.a, rb: r.b}));
  const edits = (await rows()).filter(r => mine(r.ra, r.rb));
  return {a: ra, b: rb, rows: found.concat(edits), roads: await roadsOf([...found, ...edits].flatMap(r => [r.ra, r.rb]).concat([ra], rb ? [rb] : []))};
}
async function find(q){
  q = q.trim(); if(!q) return [];
  await need([q]);
  if(q in roadOf) return [facts[roadOf[q]]];
  // the roads whose edge_ref (or an edge's) has q in it: [road, edge_ref, one of them is q]
  const hits = JSON.parse((await call({type: "find", q})).hits)
    .sort((x, y) => (!x[2]) - (!y[2]) || String(x[1]).localeCompare(String(y[1]))).slice(0, 20);
  await need(hits.map(h => h[0]));
  return hits.map(h => facts[h[0]]);
}
async function givenUp(){
  await need([...res.given_up, ...res.near, ...res.orders_not_kept].flatMap(p => [p[0], p[1]]));
  const row = (u, l, broken) => { const lv = facts[u].levels, under = facts[l].levels[3];
    return {a: u, b: l, levels: lv, b_fill: under, fill_under: lv[3] <= under, parts: broken.filter(p => p[0] === u && p[1] === l).map(p => p[2])}; };
  const rows_ = res.given_up.map(([u, l]) => row(u, l, res.given_up_parts));
  const near = [...new Map(res.near.map(p => [p[0] + "|" + p[1], p])).values()].map(([u, l]) => row(u, l, res.near));
  const wishes = res.orders_not_kept.map(([x, y]) => ({a: x, b: y, fa: facts[x].levels[3], fb: facts[y].levels[3]}));
  return {rows: rows_, near, wishes, roads: await roadsOf([...rows_, ...near, ...wishes].flatMap(r => [r.a, r.b]))};
}
function rowOf(body){                                             // one edit from the page's form, checked (level_editor._row)
  const row = Object.fromEntries(COLS.map(c => [c, String(body[c] ?? "")]));
  if(!["meet", "stack", "order", "near"].includes(row.relation)) throw new Error("relation must be meet, stack or order (or near, to switch a found near row off)");
  if(row.relation === "meet" && !(["start", "end"].includes(row.a_end) && ["start", "end"].includes(row.b_end))) throw new Error("a meet needs an end of each road (start / end)");
  if((row.relation === "stack" || row.relation === "near") && !["start", "main", "end"].includes(row.a_end)) throw new Error("a stack names one part of the upper road (start, main or end)");
  for(const c of ["a", "b"]) if(!(row[c] in roadOf)) throw new Error(`edits: ${row[c]} is not an edge of the roads`);
  return row;
}
function after(ops){                                             // edits.csv after the waiting changes: the deletes out, the adds in
  const gone = new Set(ops.filter(o => o.op === "delete").map(o => +o.index));
  return editRows().filter((_, i) => !gone.has(i)).concat(ops.filter(o => o.op === "add").map(o => rowOf(o.body)));
}
async function check(rows_, ops = []){
  await need([...rows_, ...ops.filter(o => o.op === "add").map(o => o.body || {})].flatMap(r => [r.a, r.b]));
  const found = JSON.parse((await call({type: "check", edits: toCsv(after(ops)), rows: toCsv(rows_.map(rowOf))})).conflicts);
  await need(found.flatMap(([, , w]) => w.flatMap(r => [r.a, r.b])));
  return found.map(([i, why, w]) => ({rule: say(rowOf(rows_[i])), why, with: w.map(r => say({...r, own: false}))}));
}
async function apply(ops){
  if(!ops || !ops.length) throw new Error("nothing to apply");
  if(ops.some(o => !["add", "delete", "cap", "head"].includes(o.op))) throw new Error("a change is add, delete, cap or head");
  // your heads and caps now (the roads that have one: {road: [heads, caps]}), and those of the roads that the changes name
  const own = JSON.parse((await call({type: "ownEnds", heads: headsText, caps: capsText})).ends), prev = res;
  await need(ops.flatMap(o => o.op === "add" ? [o.body?.a, o.body?.b] : [o.road]));
  const heads = {}, caps = {};
  for(const [r, [h, c]] of Object.entries(own)){ heads[r] = [...h]; caps[r] = [...c]; }
  const mine = r => { heads[r] ??= ["", ""]; caps[r] ??= ["", ""]; };
  for(const o of ops){
    const r = roadOf[String(o.road)], k = {start: 0, end: 1}[o.end];
    if(o.op === "cap"){
      const c = o.cap || "";
      if(r == null || k == null || !["", "round", "square", "flat"].includes(c)) throw new Error(`ends: ${o.road} is not a road, ${o.end} not start / end, or ${c} not auto, round, square or flat`);
      mine(r);
      caps[r][k] = c === facts[r].caps_auto[k] ? "" : c;          // the default shape is not stored
    } else if(o.op === "head"){
      const m = String(o.m ?? "").trim();
      if(r == null || k == null || !(m === "" || +m > 0)) throw new Error(`heads: ${o.road} is not a road, ${o.end} not start / end, or ${m} not a positive number of metres`);
      mine(r);
      heads[r][k] = m;
    }
  }
  for(const r of new Set(ops.filter(o => o.op === "head").map(o => roadOf[String(o.road)]))){
    const v = heads[r], [hs, he] = v.map((x, j) => x ? +x : facts[r].heads_auto[j]);
    if(v.every(Boolean) && hs + he > facts[r].length_m + 0.05) throw new Error(`heads of ${name(r)}: ${hs} + ${he} m is more than the road's ${facts[r].length_m} m`);
  }
  const old = editRows(), gone = [...new Set(ops.filter(o => o.op === "delete").map(o => +o.index))];
  for(const o of ops.filter(o => o.op === "delete")){
    const e = old[+o.index];
    if(!e || COLS.some(c => String(e[c] ?? "") !== String(o.row[c] ?? ""))) throw new Error("an edit to delete is not in edits.csv as the page showed it (changed since): reload the page");
  }
  const kept = old.filter((_, i) => !gone.includes(i)), have = new Set(kept.map(r => COLS.map(c => r[c]).join("|")));
  const added = ops.filter(o => o.op === "add").map(o => rowOf(o.body));
  for(const r of added){ const k = COLS.map(c => r[c]).join("|");
    if(have.has(k)) throw new Error(`this rule is already in edits.csv: ${say(r)}: nothing saved`); have.add(k); }
  const newEdits = ops.some(o => o.op === "add" || o.op === "delete") ? kept.concat(added) : null;
  const headsCsv = toCsv(Object.entries(heads).filter(([, v]) => v.some(Boolean)).sort().map(([road, v]) => ({road, start_m: v[0], end_m: v[1]})), ["road", "start_m", "end_m"]);
  const capsCsv = toCsv(Object.entries(caps).filter(([, v]) => v.some(Boolean)).sort().map(([road, v]) => ({road, start: v[0], end: v[1]})), ["road", "start", "end"]);
  // the roads a change names (level_editor._changed): of the edit rows added or taken out, and those whose heads changed
  const key = r => COLS.map(c => r[c]).join("|"), before = new Set(old.map(key)), now = new Set((newEdits || old).map(key));
  const changed = [...(newEdits || old), ...old].filter(r => before.has(key(r)) !== now.has(key(r))).flatMap(r => [r.a, r.b])
    .concat(Object.keys(heads).filter(r => JSON.stringify((own[r] || [["", ""]])[0]) !== JSON.stringify(heads[r])));
  const nextEdits = newEdits ? toCsv(newEdits) : editsText;
  // caps and heads are drawing only (level_editor.py's change, 2026-10-08): only a relation edit is solved, locally (solveLocal)
  let said = headsCsv === headsText ? "not solved again (only caps)" : "not solved again (heads and caps are drawing only)", full = false, next = res;
  if(newEdits){
    const t = performance.now();
    next = JSON.parse((await call({type: "solveLocal", edits: nextEdits, changed})).answer);   // a refusal throws: nothing is saved
    const s = ((performance.now() - t) / 1000).toFixed(1);
    full = next.resolve.how === "full";
    said = full ? `solved the whole area in ${s} s${next.resolve.why ? ": the local re-solve did not do (" + next.resolve.why + ")" : ""}`
      : `re-solved the roads around the change in ${s} s`;
  }
  const was = host ? lastCsv ?? (await call({type: "levelsCsv", levels: flat(res), heads: headsText, caps: capsText})).csv : null;
  await store.save("heads.csv", headsCsv);
  await store.save("caps.csv", capsCsv);
  if(newEdits) await store.save("edits.csv", nextEdits);
  [editsText, headsText, capsText, res] = [nextEdits, headsCsv, capsCsv, next];
  await save(res);
  saved -= gone.filter(i => i < saved).length;
  sessionStorage.setItem(SAVED, String(saved));
  // the panel's facts again: of the roads that the changes name and of those whose numbers changed
  facts = {};
  const shown = await roadsOf(ops.flatMap(o => o.op === "add" ? [o.body.a, o.body.b] : [o.road]).map(x => roadOf[String(x)])
    .concat(order.filter((r, i) => res.levels[i].some((v, j) => v !== prev.levels[i][j]))).filter(Boolean));
  if(host){                                                        // the host draws the edges whose row of levels.csv changed
    const before = new Set(was.split("\n"));
    const t = performance.now();
    await host.replaceRoads(csvRows(lastCsv.split("\n").filter((l, i) => i === 0 || !before.has(l)).join("\n")));
    await addFields();
    said += ` · drawn in ${((performance.now() - t) / 1000).toFixed(1)} s`;
  } else await showRoads(await build());                           // the new map in place: new tiles, the roads style swapped
  return {ok: true, said, full, redrawn: true, facts: shown, stats: stats()};
}
window.lvApi = async (path, body) => {
  const u = new URL(path, location.href), q = k => u.searchParams.get(k) || "";
  switch(u.pathname){
    case "/api/edits": { const r = await rows(); return {rows: r, roads: await roadsOf(r.flatMap(x => [x.ra, x.rb]))}; }
    case "/api/given_up": return givenUp();
    case "/api/find": return find(q("q"));
    case "/api/relations": return relations(q("a"), q("b") || null);
    case "/api/check": return {conflicts: await check(body.rows || [], body.ops || [])};
    case "/api/new_session": saved = editRows().length; sessionStorage.setItem(SAVED, String(saved)); return {ok: true, saved};
    case "/api/apply": return apply(body.ops || []);
  }
  throw new Error("not found: " + path);
};

// --- the panel (static/level_editor.html, the Python editor's too), with its scripts run
const panel = (await (await fetch(new URL("../../level_editor.html", import.meta.url))).text()).replace("__STATS__", JSON.stringify(stats()));
window.lvColors = [COLORS.select, COLORS.second];
const holder = document.createElement("div");
holder.innerHTML = panel;
// the panel's nodes, and the listeners that its scripts add to the document and the map as they run (destroy takes them off)
const nodes = [], heard = [];
const [docOn, mapOn] = [document.addEventListener, map.on];
document.addEventListener = function(...a){ heard.push(() => document.removeEventListener(...a)); return docOn.apply(this, a); };
map.on = function(...a){ heard.push(() => map.off(...a)); return mapOn.apply(this, a); };
try {
  for(const n of [...holder.childNodes]){
    const node = n.tagName === "SCRIPT" ? Object.assign(document.createElement("script"), {textContent: n.textContent}) : n;
    nodes.push(node);
    container.appendChild(node);                                 // a script runs here, at once
  }
} finally { [document.addEventListener, map.on] = [docOn, mapOn]; }

// --- the phone's layout: a sheet at the bottom of the map (layout "sheet", or "auto" up to 700 px wide: the dashboard panel's width)
const narrow = matchMedia("(max-width: 700px)"), body = document.body, root = document.documentElement;
const sheetOn = () => layout === "sheet" || (layout === "auto" && narrow.matches);
function sheet(state){                                           // "fold" (one row), "half" or "full"; the map's camera keeps the top
  body.dataset.lvSheet = state;
  setTimeout(() => sheetOn() && map.setPadding({...map.getPadding(), bottom: document.getElementById("lv").getBoundingClientRect().height}), 220);
}
function useLayout(){
  const on = sheetOn();
  body.classList.toggle("lv-sheet", on);
  if(on) sheet(body.dataset.lvSheet || "half");
  else { delete body.dataset.lvSheet; map.setPadding({...map.getPadding(), bottom: 0}); }
  setTimeout(() => map.resize(), 220);
}
const NEXT = {half: "full", full: "fold", fold: "half"};
const handle = document.getElementById("lv-handle");
handle.onclick = () => sheet(NEXT[body.dataset.lvSheet] || "half");
// the phone's keyboard: the sheet goes up above it (the visual viewport is the part of the page the keyboard leaves)
const keyboard = () => root.style.setProperty("--lv-kb", `${Math.max(0, innerHeight - visualViewport.height - visualViewport.offsetTop)}px`);
// a Street View or Google 3D window at the bottom (the dashboard's, up to 520 px wide): the sheet folds to its one row
const windows = new MutationObserver(() => {
  if(sheetOn() && innerWidth <= 520 && [...document.querySelectorAll(".rs-svw")].some(w => !w.hidden)) sheet("fold");
});
windows.observe(body, {subtree: true, childList: true, attributes: true, attributeFilter: ["hidden"]});
// a tap on a road: the wide tap line, when the dashboard picked nothing for this tap (its pick box can be wider than the road layers
// under the finger, and its pick comes before the map's click); the road table's row of the piece, which has the road
let lastPick = -1e9;
const heardPick = (e) => { if(!e.detail.lvTap) lastPick = performance.now(); };
document.addEventListener("rs:select", heardPick);
function tap(e){
  if(host || !sheetOn()) return;
  const f = map.queryRenderedFeatures(e.point, {layers: [P + "lv-tap"]})[0];
  const p = f && window.RS_SIDE?.props[f.id];
  const t = performance.now();
  setTimeout(() => {                                             // ponytail: one gesture = 300 ms around the click
    if(p?.road != null && lastPick < t - 300) document.dispatchEvent(new CustomEvent("rs:select", {detail: {properties: p, lvTap: true}}));
  });
}
narrow.addEventListener("change", useLayout);
visualViewport?.addEventListener("resize", keyboard);
map.on("click", tap);
useLayout();
// the files of the area as the page has them now, to download (a page with no server keeps them in the browser)
const files = {"edits.csv": async () => editsText, "heads.csv": async () => headsText, "caps.csv": async () => capsText,
  "levels.csv": async () => (await call({type: "levelsCsv", levels: flat(res), heads: headsText, caps: capsText})).csv};
async function download(name){
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([await files[name]()], {type: "text/csv"}));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
/** The editor off the page: its panel and its listeners, its roads, tiles and images, the panel's end marks and the page state it set;
 * on a host map, the host's roads that it took off go back in their places, with the host's road table and dashboard style. Your
 * files stay in the store. A map of its own is removed. */
function destroy(){
  worker.terminate();
  narrow.removeEventListener("change", useLayout);
  visualViewport?.removeEventListener("resize", keyboard);
  windows.disconnect();
  map.off("click", tap);
  document.removeEventListener("rs:select", heardPick);
  if(!own) map.setPadding({...map.getPadding(), bottom: 0});
  body.classList.remove("lv-sheet");
  delete body.dataset.lvSheet;
  root.style.removeProperty("--lv-kb");
  heard.forEach(off => off());
  nodes.forEach(n => n.remove());
  document.body.classList.remove("lv-open");
  for(const id of [...mine.layers, "lv-ends"]) if(map.getLayer(id)) map.removeLayer(id);
  for(const id of [...mine.sources, "lv-ends"]) if(map.getSource(id)) map.removeSource(id);
  mine.images.forEach(id => map.hasImage(id) && map.removeImage(id));
  if(host){
    const t = window.RS_SIDE;
    if(t && t.lvFields){ t.props.forEach(p => { if(p) for(const k of added) delete p[k]; }); delete t.lvFields; }
    if(hadApi) window.lvApi = hadApi; else delete window.lvApi;
    delete window.lvColors;
    return;
  }
  ml.removeProtocol("lv");
  if(own){ map.remove(); if(window.map === map) delete window.map; }
  else if(dashboard){
    for(const [id, src] of Object.entries(taken.sources)) if(!map.getSource(id)) map.addSource(id, src);
    for(const l of taken.layers){                                  // before the first later layer of the host's that is on the map
      const after = taken.order.slice(taken.order.indexOf(l.id) + 1).find(id => map.getLayer(id));
      map.addLayer(l, after);
    }
    window.RS_SIDE = hostSide;
    if(taken.style) dashboard.setStyle(taken.style);
    document.dispatchEvent(new CustomEvent("rs:tableready"));
  }
  // window.map stays the host's map (the panel's last timers read it)
  if(hadApi) window.lvApi = hadApi; else delete window.lvApi;
  delete window.lvColors;
}
return Object.assign(events, {map, roads: order, facts: roadsOf, download, destroy, files: Object.keys(files), answer: () => res});
}

// The level editor as a module that any page can hold (the level editor's files: roadstyle's level area; docs/rust/browser.md, "The level
// editor in a page"): levelEditor({map, container, pkg, store}) loads the area's files from `store`, solves in the page (the roadstyle-wasm
// package `pkg`, initialised: LevelArea, resolveLook, makeSources, tileSources), draws the area on `map` (a MapLibre map of the host, else
// one of its own in `container`) and puts the panel (static/level_editor.html) in `container`. It saves your edits, heads and caps and the
// solved levels.csv to `store`, and after each solve it sends the event "solved" ({levelsCsv, levelsInfo, draw()}: draw gives the map's
// table, GeoParquet, one row for each edge) so that the host can apply it. A store is {load(name, bytes) -> {body, mtime} | null,
// save(name, text | bytes)} with an optional `name` (the area's, shown in the panel) and `key`: httpStore for roadstyle serve,
// browserStore for a page with no server.
import {rsDashboard} from "../index.js";

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

/** The store of a page with no server: the area's files in this browser under `key` (the texts in localStorage, the bytes, such as
 * roads.parquet, in the origin's private file system), each with the time it was saved (seconds). */
export function browserStore(key, name = key){
  const at = n => `lv:${key}:${n}`;
  const dir = async () => (await navigator.storage.getDirectory()).getDirectoryHandle("lv-" + key.replace(/[^\w.-]/g, "_"), {create: true});
  return {key, name,
    async load(n, bytes){
      const mtime = +(localStorage.getItem(at(n) + "@mtime") || 0);
      if(bytes){
        try { const f = await (await (await dir()).getFileHandle(n)).getFile(); return {body: new Uint8Array(await f.arrayBuffer()), mtime}; }
        catch { return null; }
      }
      const body = localStorage.getItem(at(n));
      return body == null ? null : {body, mtime};
    },
    async save(n, data){
      if(typeof data === "string") localStorage.setItem(at(n), data);
      else { const w = await (await (await dir()).getFileHandle(n, {create: true})).createWritable(); await w.write(data); await w.close(); }
      localStorage.setItem(at(n) + "@mtime", String(Date.now() / 1000));
    }};
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
export async function levelEditor({map = null, container = document.body, pkg, store, maplibregl: ml = globalThis.maplibregl, dashboard = null,
                                   prefix = dashboard ? null : "lv-rs-"}){
if(map && !dashboard && window.rs)
  throw new Error("level editor: this page has a dashboard (window.rs): give it as levelEditor({dashboard, prefix}), so that the editor uses it; a second dashboard takes the first one's state");
if(dashboard && !prefix)
  throw new Error("level editor: give the prefix of your dashboard (its layers and sources); the editor takes the layers with it off the map before it draws");
if(map && window.map instanceof ml.Map && window.map !== map)     // (an element with the id "map" is window.map too: not a map)
  throw new Error("level editor: window.map is another map; the panel draws on window.map");
const P = map ? prefix : "rs-";                                  // a host map: the editor's layers and sources with the prefix given
const {LevelArea} = pkg;
const events = new EventTarget();
const get = (n, bytes) => store.load(n, bytes);
const [roadsF, pairsF, editsF, headsF, capsF, levelsF, infoF] = await Promise.all([get("roads.parquet", true), get("pairs.csv"), get("edits.csv"),
  get("heads.csv"), get("caps.csv"), get("levels.csv"), get("levels_info.json")]);
if(!roadsF || !pairsF) throw new Error("the store has no roads.parquet or pairs.csv: make the area first (makeArea, or roadstyle levels make)");
const area = new LevelArea(roadsF.body, pairsF.body);
const pairs = csvRows(pairsF.body);
const order = JSON.parse(area.facts());                          // each road, in the roads' order
const facts = Object.fromEntries(order.map(f => [f.road, f]));
const roadOf = {};                                               // any edge id -> its road id
for(const f of order){ roadOf[f.road] = f.road; for(const d of f.directions) roadOf[d.edge] = f.road; }
const autoEnds = JSON.parse(area.ends("", ""));                  // the ends with none of yours: the default caps and heads
let editsText = editsF ? editsF.body : EMPTY, headsText = headsF ? headsF.body : "", capsText = capsF ? capsF.body : "";
const SAVED = "lv-saved:" + (store.key || location.pathname);    // the edits saved before this session (the Python server keeps it)
let saved = +(sessionStorage.getItem(SAVED) ?? csvRows(editsText).length);
let res = null;                                                  // the last answer of the solver (JSON of LevelArea)

// --- the answer to start from: levels.csv when it is newer than the inputs and has every edge, else a solve
function fromStored(){
  if(!levelsF || !infoF) return null;
  const newest = Math.max(roadsF.mtime, pairsF.mtime, editsF ? editsF.mtime : 0, headsF ? headsF.mtime : 0);
  if(levelsF.mtime < newest) return null;
  const at = Object.fromEntries(csvRows(levelsF.body).map(r => [r.edge, [+r.casing_start, +r.casing_level, +r.casing_end, +r.fill_level]]));
  const levels = [];
  for(const f of order){
    const fw = f.directions.find(d => d.way === "along"), bw = f.directions.find(d => d.way === "against");
    if(fw && at[fw.edge]) levels.push(at[fw.edge]);
    else if(bw && at[bw.edge]){ const [s, m, e, fl] = at[bw.edge]; levels.push([e, m, s, fl]); }      // only the other way: its heads swapped
    else return null;
  }
  const info = JSON.parse(infoF.body);
  area.startFrom(Int32Array.from(levels.flat()), (info.given_up_parts || []).map(p => p.join("|")), (info.orders_not_kept || []).length, (info.near || []).length);
  return {levels, given_up: info.given_up || [], given_up_parts: info.given_up_parts || [], near: info.near || [], orders_not_kept: info.orders_not_kept || [],
    info: {pairs: info.pairs, meets: info.meets, order_pairs: info.order_pairs, order_violations: info.order_violations, near_warnings: info.near_warnings},
    resolve: {how: "stored"}};
}
async function save(newRes){                                       // levels.csv and levels_info.json of an answer; then the host hears of it
  const levelsCsv = area.levelsCsv(Int32Array.from(newRes.levels.flat()), headsText, capsText);
  const info = JSON.stringify({...newRes.info, given_up: newRes.given_up, given_up_parts: newRes.given_up_parts, near: newRes.near,
    orders_not_kept: newRes.orders_not_kept});
  await store.save("levels.csv", levelsCsv);
  await store.save("levels_info.json", info);
  events.dispatchEvent(new CustomEvent("solved", {detail: {levelsCsv, levelsInfo: info, draw: () => area.draw(Int32Array.from(newRes.levels.flat()), headsText, capsText)}}));
}
res = fromStored();
if(!res){ res = JSON.parse(area.solve(editsText)); try { await save(res); } catch(e){ console.warn(e.message); } }

// --- what the panel shows: each road's numbers and ends
function setFacts(){
  const ends = JSON.parse(area.ends(headsText, capsText));
  order.forEach((f, i) => Object.assign(f, {levels: res.levels[i], heads: ends[i].heads, heads_auto: autoEnds[i].heads,
    heads_own: ends[i].heads_own.map(Boolean), caps: ends[i].caps_own, caps_auto: autoEnds[i].caps}));
}
setFacts();
const stats = () => ({area: store.name || "area", roads: order.length,
  ...res.info, given_up: res.given_up});

// --- the map: the engine's tiles of one row for each edge, a new generation for each answer
const look = pkg.resolveLook(JSON.stringify({args: LOOK}));
let tiler = null, gen = 0;
function build(){
  const src = pkg.makeSources(area.draw(Int32Array.from(res.levels.flat()), headsText, capsText), look, undefined, undefined, "Level editor");
  window.RS_SIDE = JSON.parse(new TextDecoder().decode(src.roadTable()));
  tiler = pkg.tileSources(src, `lv://${++gen}/`, KEEP);
  document.dispatchEvent(new CustomEvent("rs:tableready"));
  return JSON.parse(tiler.style());
}
const style = build();
ml.addProtocol("lv", async (params) => {                             // the editor's own tiles (a host's rs:// stays its own)
  const [g, source, z, x, y] = params.url.slice("lv://".length).split("/");
  return {data: +g === gen ? tiler.tile(source, +z, +x, +y) : new Uint8Array()};
});
// the camera: the area's box (the road table's boxes)
const bb = window.RS_SIDE.bboxes.filter(Boolean).reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])],
  [180, 90, -180, -90]);
const own = !map;                                                // no host map: the editor's own, on the area's box
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
const rs = dashboard || rsDashboard(map, {style: null, prefix: P, tiles: true, simple: "roads-simple", edge_id_col: "edge", basemap_switcher: false,
  select_color: "rgba(0,0,0,0)"});
async function showRoads(st){                                      // the roads style on the map, in place of the one before (prefix P)
  for(const l of map.getStyle().layers) if(l.id.startsWith(P)) map.removeLayer(l.id);
  for(const id of Object.keys(map.getStyle().sources)) if(id.startsWith(P)) map.removeSource(id);
  for(const [id, im] of Object.entries(st.metadata["roadstyle:images"] || {}))
    if(!map.hasImage(P + id)) map.addImage(P + id, (await map.loadImage(im.url)).data, {sdf: im.sdf, pixelRatio: im.pixelRatio});
  // a live style's global state (rs_colors, rs_co, ...): its start values, as a style with them would set them (the base map has none)
  for(const [k, v] of Object.entries(st.state || {})) map.setGlobalStateProperty(k, v.default ?? null);
  for(const [id, src] of Object.entries(st.sources)) map.addSource(P + id, id === "roads" ? {...src, promoteId: {simple: "__rs_edge"}} : src);
  for(const l of st.layers){
    const layer = JSON.parse(JSON.stringify(l).replaceAll('"oneway"', `"${P}oneway"`));
    map.addLayer({...layer, id: P + l.id, source: P + l.source}, map.getLayer("lv-ends") ? "lv-ends" : undefined);   // under the panel's end marks
  }
  rs.setStyle(st);
}
if(!map.isStyleLoaded()) await map.once("load");
await showRoads(style);
await map.once("idle");                                          // the roads style in place: the panel starts on a loaded style

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
function rows(){
  return editRows().map((r, i) => ({...r, index: i, section: i < saved ? "saved" : "new", ra: roadOf[r.a] ?? r.a, rb: roadOf[r.b] ?? r.b}));
}
const roadsOf = rs_ => Object.fromEntries([...new Set(rs_)].map(x => [x, facts[x] || {road: x}]));
function relations(a, b){
  const ra = roadOf[a], rb = b ? roadOf[b] : null;
  if(ra == null || (b && rb == null)) throw new Error("unknown road");
  const mine = (x, y) => (x === ra && (rb == null || y === rb)) || (y === ra && (rb == null || x === rb));
  const found = pairs.filter(r => mine(r.a, r.b)).map(r => ({...r, section: "found", ra: r.a, rb: r.b}));
  const edits = rows().filter(r => mine(r.ra, r.rb));
  return {a: ra, b: rb, rows: found.concat(edits), roads: roadsOf([...found, ...edits].flatMap(r => [r.ra, r.rb]).concat([ra], rb ? [rb] : []))};
}
function find(q){
  q = q.trim(); if(!q) return [];
  if(q in roadOf) return [facts[roadOf[q]]];
  const low = q.toLowerCase(), refs = f => [f.edge_ref, ...f.directions.map(d => d.edge_ref)].filter(Boolean).map(x => x.toLowerCase());
  return order.filter(f => refs(f).some(x => x.includes(low)))
    .sort((x, y) => (!refs(x).includes(low)) - (!refs(y).includes(low)) || String(x.edge_ref).localeCompare(String(y.edge_ref))).slice(0, 20);
}
function givenUp(){
  const row = (u, l, broken) => { const lv = facts[u].levels, under = facts[l].levels[3];
    return {a: u, b: l, levels: lv, b_fill: under, fill_under: lv[3] <= under, parts: broken.filter(p => p[0] === u && p[1] === l).map(p => p[2])}; };
  const rows_ = res.given_up.map(([u, l]) => row(u, l, res.given_up_parts));
  const near = [...new Map(res.near.map(p => [p[0] + "|" + p[1], p])).values()].map(([u, l]) => row(u, l, res.near));
  const wishes = res.orders_not_kept.map(([x, y]) => ({a: x, b: y, fa: facts[x].levels[3], fb: facts[y].levels[3]}));
  return {rows: rows_, near, wishes, roads: roadsOf([...rows_, ...near, ...wishes].flatMap(r => [r.a, r.b]))};
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
function check(rows_, ops = []){
  const found = JSON.parse(area.check(toCsv(after(ops)), toCsv(rows_.map(rowOf))));
  return found.map(([i, why, w]) => ({rule: say(rowOf(rows_[i])), why, with: w.map(r => say({...r, own: false}))}));
}
async function apply(ops){
  if(!ops || !ops.length) throw new Error("nothing to apply");
  if(ops.some(o => !["add", "delete", "cap", "head"].includes(o.op))) throw new Error("a change is add, delete, cap or head");
  const ends = JSON.parse(area.ends(headsText, capsText)), idx = Object.fromEntries(order.map((f, i) => [f.road, i]));
  const caps = Object.fromEntries(order.map((f, i) => [f.road, [...ends[i].caps_own]])), heads = Object.fromEntries(order.map((f, i) => [f.road, [...ends[i].heads_own]]));
  for(const o of ops){
    const r = roadOf[String(o.road)], k = {start: 0, end: 1}[o.end];
    if(o.op === "cap"){
      const c = o.cap || "";
      if(r == null || k == null || !["", "round", "square", "flat"].includes(c)) throw new Error(`ends: ${o.road} is not a road, ${o.end} not start / end, or ${c} not auto, round, square or flat`);
      caps[r][k] = c === autoEnds[idx[r]].caps[k] ? "" : c;      // the default shape is not stored
    } else if(o.op === "head"){
      const m = String(o.m ?? "").trim();
      if(r == null || k == null || !(m === "" || +m > 0)) throw new Error(`heads: ${o.road} is not a road, ${o.end} not start / end, or ${m} not a positive number of metres`);
      heads[r][k] = m;
    }
  }
  for(const r of new Set(ops.filter(o => o.op === "head").map(o => roadOf[String(o.road)]))){
    const v = heads[r], [hs, he] = v.map((x, j) => x ? +x : autoEnds[idx[r]].heads[j]);
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
    .concat(order.filter((f, i) => JSON.stringify(ends[i].heads_own) !== JSON.stringify(heads[f.road])).map(f => f.road));
  const nextEdits = newEdits ? toCsv(newEdits) : editsText;
  let said = "not solved again (only caps)", full = false, next = res;
  if(newEdits || headsCsv !== headsText){
    const t = performance.now();
    next = JSON.parse(area.solveLocal(nextEdits, changed));         // a refusal throws: nothing is saved
    const s = ((performance.now() - t) / 1000).toFixed(1);
    full = next.resolve.how === "full";
    said = full ? `solved the whole area in ${s} s${next.resolve.why ? ": the local re-solve did not do (" + next.resolve.why + ")" : ""}`
      : `re-solved the roads around the change in ${s} s`;
  }
  await store.save("heads.csv", headsCsv);
  await store.save("caps.csv", capsCsv);
  if(newEdits) await store.save("edits.csv", nextEdits);
  [editsText, headsText, capsText, res] = [nextEdits, headsCsv, capsCsv, next];
  await save(res);
  saved -= gone.filter(i => i < saved).length;
  sessionStorage.setItem(SAVED, String(saved));
  setFacts();
  await showRoads(build());                                        // the new map in place: new tiles, the roads style swapped
  return {ok: true, said, full, redrawn: true, facts, stats: stats()};
}
window.lvApi = async (path, body) => {
  const u = new URL(path, location.href), q = k => u.searchParams.get(k) || "";
  switch(u.pathname){
    case "/api/edits": { const r = rows(); return {rows: r, roads: roadsOf(r.flatMap(x => [x.ra, x.rb]))}; }
    case "/api/given_up": return givenUp();
    case "/api/find": return find(q("q"));
    case "/api/relations": return relations(q("a"), q("b") || null);
    case "/api/check": return {conflicts: check(body.rows || [], body.ops || [])};
    case "/api/new_session": saved = editRows().length; sessionStorage.setItem(SAVED, String(saved)); return {ok: true, saved};
    case "/api/apply": return apply(body.ops || []);
  }
  throw new Error("not found: " + path);
};

// --- the panel (static/level_editor.html, the Python editor's too), with its scripts run
const panel = (await (await fetch(new URL("../../level_editor.html", import.meta.url))).text()).replace("__STATS__", JSON.stringify(stats()));
const holder = document.createElement("div");
holder.innerHTML = panel;
for(const n of [...holder.childNodes]){
  if(n.tagName === "SCRIPT"){ const s = document.createElement("script"); s.textContent = n.textContent; container.appendChild(s); }
  else container.appendChild(n);
}
// the files of the area as the page has them now, to download (a page with no server keeps them in the browser)
const files = {"edits.csv": () => editsText, "heads.csv": () => headsText, "caps.csv": () => capsText,
  "levels.csv": () => area.levelsCsv(Int32Array.from(res.levels.flat()), headsText, capsText)};
function download(name){
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([files[name]()], {type: "text/csv"}));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
return Object.assign(events, {map, area, download, files: Object.keys(files), answer: () => res});
}

// The level editor as a module that any page can hold (the level editor's files: roadstyle's level area; docs/rust/browser.md, "The level
// editor in a page"): levelEditor({map, panel, pkgUrl, store}) loads the area's files from `store`, solves in the page (the roadstyle-wasm
// package at `pkgUrl`: LevelArea, resolveLook, styleSources, tilesOfSources), draws the area on `map` (a MapLibre map of the host, else
// one of its own in `container`) and draws the editor into `panel`, the host's standard dashboard panel (#sb > .sb-card with .sb-top and
// .sb-body): the panel's body is kept and hidden, the title in .sb-top is swapped for "← <backLabel>" and "Edit levels", the editor's tabs and
// its apply bar fill the rest of the card, and destroy() puts the host's panel back. The editor has no frame, side, width or fold button of
// its own: they are the panel's. It saves your edits, heads and caps and the
// solved levels.csv to `store`, and after each solve it sends the event "solved" ({levelsCsv, levelsInfo, draw()}: draw gives the map's
// table, GeoParquet, one row for each edge) so that the host can apply it. The event "back" comes when the person leaves with "← <backLabel>"
// (with changes waiting, after "Apply, discard or stay" has an answer that leaves): the host then calls destroy() and shows its own steps.
// `backLabel: null` has no "← ..." button (a page with no steps). `template` is the dashboard template of the editor's own map's dashboard, and `basemaps` its base maps ({style, basemaps, ontop}: host_options.json): the same base-map box as every dashboard.
// A store is {load(name, bytes) -> {body, mtime} | null,
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
import {editorFrame} from "../frame.js";
import {quiet} from "../select.js";

const COLS = ["relation", "a", "b", "a_end", "b_end", "enabled"];      // what a rule is (its key)
const TCOLS = [...COLS, "time"];                                     // edits.csv: and when it was applied (local "YYYY-MM-DD HH:MM"; "" = before times)
const HCOLS = ["road", "start_m", "end_m", "time"], KCOLS = ["road", "start", "end", "time"];   // heads.csv, caps.csv: time = the road's last change
const stamp = () => { const d = new Date(), z = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`; };
const EMPTY = COLS.join(",") + "\n";
// the keywords of the editor's map (level_editor.Area._render)
const LOOK = {state: "live", edge_id_col: "edge", directed_col: "directed", driving_col: "driving", road_popup: false,
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
 * too: pairs.csv of a large area is more than localStorage holds), each with the time it was saved (seconds, in localStorage).
 * `memoryFallback: true`: a file that the browser cannot keep (no private file system, a full storage) stays in memory for this page, with a
 * warning in the console, and `store.lostBytes()` gives the size of those files (the page can tell the person: the edits stay only until the
 * page closes). Without it, a file that cannot be kept is an error of `save`. `lostBytes()` is 0 when every file is kept. */
export function browserStore(key, name = key, {memoryFallback = false} = {}){
  const at = n => `lv:${key}:${n}`;
  const dir = async () => (await navigator.storage.getDirectory()).getDirectoryHandle("lv-" + key.replace(/[^\w.-]/g, "_"), {create: true});
  const write = async (n, data) => { const w = await (await (await dir()).getFileHandle(n, {create: true})).createWritable(); await w.write(data); await w.close(); };
  const mem = new Map();                                          // memoryFallback: the files that the browser did not keep
  let lost = 0;
  const size = d => typeof d === "string" ? d.length : d.byteLength;
  const as = (d, bytes) => bytes ? (typeof d === "string" ? new TextEncoder().encode(d) : d) : (typeof d === "string" ? d : new TextDecoder().decode(d));
  return {key, name, lostBytes: () => lost,
    async load(n, bytes){
      if(mem.has(n)){ const m = mem.get(n); return {body: as(m.body, bytes), mtime: m.mtime}; }
      let d;
      try { d = await dir(); }
      catch(e){ if(memoryFallback) return null; throw e; }        // no private file system: the browser kept nothing (save puts the file in memory)
      const old = localStorage.getItem(at(n));                    // a text that an older version kept in localStorage: moved once
      if(old != null){ await write(n, old); localStorage.removeItem(at(n)); }
      let f;
      try { f = await (await d.getFileHandle(n)).getFile(); }
      catch(e){ if(e.name === "NotFoundError") return null; throw e; }
      return {body: bytes ? new Uint8Array(await f.arrayBuffer()) : await f.text(), mtime: +(localStorage.getItem(at(n) + "@mtime") || 0)};
    },
    async save(n, data){
      if(!mem.has(n)){
        try { await write(n, data); localStorage.setItem(at(n) + "@mtime", String(Date.now() / 1000)); return; }
        catch(e){ if(!memoryFallback) throw e; console.warn(`level editor: ${n} is not kept in the browser (${e.message}): it stays in memory until the page closes`); lost += size(data); }
      } else lost += size(data) - size(mem.get(n).body);          // a file that is in memory stays there: its size is the newest one
      mem.set(n, {body: data, mtime: Date.now() / 1000});
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

/** The level area of the host's edges is in `store`: made only when the store has another area (`edgeHash` differs) or `force` is true. `edges()` gives the
 * roads of the area as GeoParquet bytes (the host's own query; it is called only when the area is made), `pkg` is the roadstyle WebAssembly module
 * (initialised; with none, `pkgUrl` is loaded), `idCol` the column with the edge id. With `edgeHash` and `pkgUrl`, the engine of the area is also made
 * in the background (`prepareEditor`, unless `prepare` is false), so that the open only draws the panel. Gives `{made, warnings, roadCount, pairCount}` (the last three only
 * when the area was made). */
export async function ensureArea({store, edgeHash = "", edges, pkg = null, pkgUrl = null, idCol = "edge_id", look = null, force = false, prepare = true}){
  if(!force && edgeHash && await areaIsFor(store, edgeHash)){
    if(prepare && pkgUrl) prepareEditor({store, pkgUrl, look, edgeHash}).catch(() => {});
    return {made: false, warnings: []};
  }
  if(typeof edges !== "function") throw new Error("ensureArea: give edges(), the host's roads of the area as GeoParquet bytes");
  if(!pkg){
    if(!pkgUrl) throw new Error("ensureArea: give pkg (the roadstyle WebAssembly module) or pkgUrl");
    pkg = await import(String(new URL(pkgUrl, location.href))); await pkg.default();
  }
  const a = pkg.makeArea(await edges(), JSON.stringify({id_col: idCol}));
  try {
    await saveArea(store, a, edgeHash);
    if(prepare && edgeHash && pkgUrl) prepareEditor({store, pkgUrl, look, edgeHash}).catch(() => {});
    return {made: true, warnings: [...a.warnings], roadCount: a.roadCount, pairCount: a.pairCount};
  } finally { a.free(); }
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

// the guide of the editor on the site: the help window links to its two sections (they open in a new tab; the anchors are the headings of docs/guides/levels.md)
const DOCS = "https://khoshkhah.github.io/roadstyle/guides/levels/";

/** The words of the editor's help window (rs.help.set): `c` the colours of the two picked roads, `back` the label of the "← ..." button (null: none). */
function levelsHelp(c, back){
  const dot = (col, n) => `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${col};vertical-align:middle"></span> road ${n}`;
  const terms = [
    ["Road ends", "The tab for one road. Click a road to pick it. Each end has its own row: choose its shape (<b>round</b>, <b>square</b> or <b>flat</b>) and use the slider to change the length of its casing head. <b>no main part</b> sets the main part to zero: the end head is then the rest of the road. <b>default lengths</b> sets the lengths back. On the map, ● is the start of the road and ■ is the end."],
    ["Stacking", "The tab for two roads. Click a road, then a second road, to see the rules between them and to add a rule. Click a picked road, its ×, or press Esc to remove it. You can also type an edge id or an edge_ref in the find box."],
    ["Order", "Says which road is drawn on top where the two roads meet. Use <b>on top</b> to choose the road. The solver keeps an order when it can."],
    ["Stack", "Says that one road crosses over the other road, for example on a bridge. Choose the road that is on top, and the parts of its casing that cross. A stack always wins over an order."],
    ["Meet", "Joins an end of road 1 to an end of road 2. Each end is drawn under the fill of the other road, so the two roads join with no ring."],
    ["Casing parts", "The casing is the outline of a road. It has three parts: the <b>start head</b> ●, the <b>main</b> part and the <b>end head</b> ■. Choose one part, some parts or the whole road. Each part is one row. Set the length of a head in <b>Road ends</b>."],
    ["Switch off", "Stops a rule that the map data found (a <b>found</b> rule), for example a wrong stack. The rule stays in the data, and edits.csv keeps a row that switches it off. To replace a found stack with your own: switch off <b>all</b> its rows, then add your own parts. A stack that you added yourself has <b>delete</b> in place of switch off."],
    ["Conflict", "When a new rule makes a loop with other rules (A over B over A), a red box shows those rules. <b>Add anyway</b> puts it in the list; the solver then gives up one rule of the loop. <b>Cancel</b> keeps the list as it was. Usually you switch off one of the other rules first."],
    ["Add to the list", "Puts the new rule in the list of waiting changes at the bottom. Nothing is solved yet. <b>Discard</b> removes all waiting changes."],
    ["Apply and solve", "Solves all waiting changes together, draws again the roads that changed, and saves them. A green box tells what changed. If the solver refuses the changes, a red box tells why and nothing is saved. Click a red box to close it."],
    ["History", "The rules in <b>edits.csv</b>. <b>Today</b> holds the changes of this session; <b>start a new session</b> moves them to <b>Earlier</b> (nothing is deleted). <b>Road ends</b> lists the roads with their own head lengths or end shapes (heads.csv and caps.csv); <b>reset</b> sets the defaults again. Each row shows when it was applied. <b>Add from files…</b> puts the rows of your edits.csv, heads.csv or caps.csv in the list of waiting changes: a rule that the area has already and a row of another area are skipped, and a row with no time gets the time of the Apply. The links at the bottom download the three files."],
    ["Issues", "Three counts: <b>Given up</b> (a stack that the solver could not keep: a flaw on the map), <b>Near</b> (a road that only comes near the road below it) and <b>Wishes not kept</b> (an order that a stack or another order won). Click a count to go to its list. Click a row to see the two roads on the map; <b>edit</b> opens them in Stacking."]];
  if(back != null) terms.push([`← ${back}`, "Goes back to the steps of the page. If changes are waiting, the editor asks you to <b>Apply</b>, <b>Discard</b> or <b>Stay</b>."]);
  return {title: "Edit levels", button: "How to use the level editor",
    intro: `A level says which road is drawn over which road: a road at a higher level is drawn over a road at a lower level. The editor has two tabs for changes. <b>Road ends</b> changes one road: the shape and the head length of each end. <b>Stacking</b> changes two roads: which one is drawn over the other. In Stacking, the first road you click is ${dot(c.select, 1)} and the second is ${dot(c.second, 2)}, on the map and in the panel.`,
    terms,
    note: `More in the guide: <a href="${DOCS}#edit-the-levels" target="_blank" rel="noopener">Edit the levels</a> and <a href="${DOCS}#edit-the-levels-in-a-dashboard" target="_blank" rel="noopener">Edit the levels in a dashboard</a>.`};
}

// --- the engine of an area: the worker with its LevelArea and what the editor knows of the roads. It takes seconds to make (the worker's module, the
// roads' file, the area's parse), so a host that gives the same `levels.edge_hash` again gets the same engine: `destroy()` keeps it, and
// `prepareEditor` makes it before the first open (when the host is idle). One engine for each store key.
const engines = new Map();                                       // store key -> {token: edge_hash, ready: Promise of the engine}
const sha = async d => [...new Uint8Array(await crypto.subtle.digest("SHA-256", typeof d === "string" ? new TextEncoder().encode(d) : d))]
  .map(b => b.toString(16).padStart(2, "0")).join("");
async function startEngine({store, pkgUrl, lookText, boundary}){
  const worker = new Worker(new URL("./level_worker.js", import.meta.url), {type: "module"});
  const stopHooks = new Set();                                    // the editors that listen for a stop of this worker (levelEditor adds its own)
  const call = caller(worker, err => stopHooks.forEach(f => f(err)));
  try {
    const init = call({type: "init", pkgUrl: String(new URL(pkgUrl, location.href)), base: lookText,
      look: JSON.stringify({args: {...LOOK, hover_color: SENT.hover, select_color: SENT.select, ...(boundary ? {boundary} : {})}})});
    const [roadsF, pairsF] = await Promise.all([store.load("roads.parquet", true), store.load("pairs.csv")]);
    if(!roadsF || !pairsF) throw new Error("the store has no roads.parquet or pairs.csv: make the area first (makeArea, or roadstyle levels make)");
    const roadsBytes = roadsF.body.slice();
    // the inputs of a solve, by their content (the SHA-256 of roads.parquet, pairs.csv and edits.csv): levels.csv is for them when its
    // levels_info.json has the same key, also after a page wrote the same area again (a file's time says nothing then). heads.csv and caps.csv
    // are drawing only: they are not inputs of the solve.
    const areaKey = `${await sha(roadsBytes)}:${await sha(pairsF.body)}`;
    await init;
    const order = (await call({type: "open", roads: roadsBytes.buffer, pairs: pairsF.body}, [roadsBytes.buffer])).roads;   // the road ids, in the roads' order
    // pairs.csv's lines: the panel's found rules of a road come from them when it asks (relations); the open does not parse them
    const pairLines = pairsF.body.split(/\r?\n/).filter(l => l.trim());
    // what the page knows of the roads, asked from the worker when the panel needs them: any edge id -> its road id
    return {worker, call, areaKey, order, pairLines, roadOf: Object.fromEntries(order.map(r => [r, r])), stopHooks};
  } catch(e){ worker.terminate(); throw e; }
}
const SENT = {select: "#fe0a01", hover: "#fe0a02"};                 // (the editor's sentinel colours, see levelEditor)

/** Makes the engine of the area in `store` before `levelEditor` is called, in the background: the next `levelEditor({host, levels, ...})` with the same
 * `levels.edge_hash` (and `store`) finds it and opens at once. Give `look` and `pkgUrl` as for levelEditor. A Promise; an error is also kept for the open. */
export function prepareEditor({store, pkgUrl, look = null, edgeHash}){
  const k = store.key ?? "area", old = engines.get(k);
  if(old?.token === edgeHash) return old.ready.then(() => {});
  if(old) old.ready.then(e => e.worker.terminate(), () => {});
  const ready = startEngine({store, pkgUrl, lookText: look});
  engines.set(k, {token: edgeHash, ready});
  ready.catch(() => { if(engines.get(k)?.ready === ready) engines.delete(k); });
  return ready.then(() => {});
}

/** The level editor on `map` (or a map of its own in `container`), with the panel in `container`; see the file's head. A page has one
 * dashboard (its state is the module's): on a host map that has one, give it as `dashboard` with the `prefix` it was made with; the
 * editor then draws its roads with that prefix (take your own roads off first) and gives the dashboard its style (setStyle). Gives an
 * EventTarget (event "solved") with `map`, `area` (the LevelArea), `download(name)` (edits.csv, heads.csv, caps.csv or levels.csv as they
 * are now), `files` (those names) and `answer()` (the last answer of the solver).
 * The option `look` (the text of a saved look, such as the page's own look.json) gives the editor's roads the page's palette and sections: the editor then only
 * sets its own column names, its state `live` and the colours of its picks. */
export async function levelEditor({map = null, container = document.body, panel, backLabel = "Steps", template = null, basemaps = null, pkgUrl, store,
                                   maplibregl: ml = globalThis.maplibregl, dashboard = null, prefix = dashboard ? null : "lv-rs-",
                                   levels: given = null, host = null, colors = {}, look: lookText = null, area = null}){
// the picked roads and the hover (`colors`: {select, hover, second}): road 1 red, road 2 blue, the hover a lighter red
const COLORS = {select: "#e53935", hover: "#ff8a80", second: "#1e63d6", hover2: "#82b1ff", ...colors};
// The dashboard has one select colour and one hover colour for every road; the editor wants road 1 red and road 2 blue, and the hover of the road
// that would be the next pick lighter in its colour. The look gets two sentinel colours, which `highlight` replaces in the road layers' paint.
// On a host's roads (`host`) the colours to swap are the host's own select and hover colours, from its look (the look's interaction colours, else its selection section)
const hostLook = host && lookText ? JSON.parse(lookText) : null;
const FIND = !host ? SENT : {select: hostLook?.map?.interaction?.select_color ?? hostLook?.selection?.select ?? "\0",
  hover: hostLook?.map?.interaction?.hover_color ?? hostLook?.selection?.hover ?? "\0"};
// the host's panel: the card, its title line (the title first, then the hide button) and its body
const hostCard = panel?.querySelector?.(".sb-card"), hostBar = hostCard?.querySelector(".sb-top"), hostBody = hostCard?.querySelector(".sb-body");
if(!hostBar?.firstElementChild || !hostBody)
  throw new Error("level editor: give `panel`, the host's dashboard panel: an element with .sb-card, in it .sb-top (the title first, then the hide button) and .sb-body");
if(map && !dashboard && window.rs)
  throw new Error("level editor: this page has a dashboard (window.rs): give it as levelEditor({dashboard, prefix}), so that the editor uses it; a second dashboard takes the first one's state");
if(host && !(map && dashboard && typeof host.replaceRoads === "function"))
  throw new Error("level editor: the option host needs the host's map and dashboard, and host.replaceRoads(rows)");
if(dashboard && !prefix && !host)
  throw new Error("level editor: give the prefix of your dashboard (its layers and sources); the editor takes the layers with it off the map before it draws");
if(map && window.map instanceof ml.Map && window.map !== map)     // (an element with the id "map" is window.map too: not a map)
  throw new Error("level editor: window.map is another map; the panel draws on window.map");
const P = map ? prefix : "rs-";                                  // a host map: the editor's layers and sources with the prefix given
// the highlight colours (see SENT): `captureHL` keeps the paint of the road layers that hold a sentinel, `highlight(groups)` ([[ids, colour], ...], one for each
// picked road, as rsColor takes them) sets that paint again: a picked road in its colour (an expression on the road's id), the hover in the colour of the road
// that the next click would pick (light red for the first, light blue for the second)
const hl = {orig: new Map(), groups: null};
const swapColors = (v, to) => Array.isArray(v) ? v.map(x => swapColors(x, to)) : v && typeof v === "object"
  ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, swapColors(x, to)])) : v === FIND.select ? to.select : v === FIND.hover ? to.hover : v;
const hasSent = v => { const t = JSON.stringify(v); return t.includes(FIND.select) || t.includes(FIND.hover); };
// (a layer that has no sentinel now keeps what it had: its paint is already swapped)
function captureHL(){
  for(const l of map.getStyle().layers) if(l.paint && hasSent(l.paint)) hl.orig.set(l.id, l.paint);
}
function highlight(groups){
  hl.groups = groups;
  const picked = (groups || []).filter(g => g[0].length);
  const select = picked.length ? ["match", ["id"], ...picked.flatMap(([ids, c]) => [ids, c]), COLORS.select] : COLORS.select;
  const to = {select, hover: picked.length === 1 && picked[0][1] === COLORS.select ? COLORS.hover2 : COLORS.hover};
  for(const [id, paint] of hl.orig) if(map.getLayer(id)) for(const [k, v] of Object.entries(paint)) if(hasSent(v)) map.setPaintProperty(id, k, swapColors(v, to));
}
// the road table's fields: what the page reads of a row (the dashboard's reads.json, "table"), live data's id and the road that a click
// picks (the other fields of a road are a large part of the table's text, which the page parses after each answer)
const reads = await fetch(new URL("../reads.json", import.meta.url));
if(!reads.ok) throw new Error(`level editor: the dashboard's reads.json (${reads.status})`);
const TABLE = [...(await reads.json()).table, LOOK.edge_id_col, "road", "modes", "s_lon", "s_lat", "e_lon", "e_lat"];   // "modes": the panel's mode box;
// s_lon ... e_lat: the two ends of the road, where the panel draws ● and ■ (a host's table gets them from addFields; before, the editor's own map had none)
// the engine in a worker (level_worker.js): the solve, the map and its tiles do not stop the page. With `host` and `levels.edge_hash`, the engine of this
// area is the one that an earlier open (or prepareEditor) made, when it has the same hash: `destroy()` keeps it for the next open.
const engKey = store.key ?? "area", token = host && given ? given.edge_hash : undefined;
let eng = null, areaInfo = null;
const kept = engines.get(engKey);
if(kept && token !== undefined && kept.token === token){
  try { eng = await kept.ready; } catch(e){ eng = null; }
}
if(!eng){
  if(kept){ engines.delete(engKey); kept.ready.then(e => e.worker.terminate(), () => {}); }
  // the area's edge: boundary.geojson in the store (roadstyle levels make --boundary) is the dashed line of the editor's own map; a host map has its own
  const boundaryF = map ? null : await store.load("boundary.geojson");
  // `area` ({edges, edgeHash, idCol, pkg}: see ensureArea): the editor makes the area itself, and makes it once more when the store lost its files
  // after it was made (the browser cleared its storage); `levelEditor` has the result in `editor.areaInfo`
  const start = () => startEngine({store, pkgUrl, lookText, boundary: boundaryF ? JSON.parse(boundaryF.body) : null});
  if(area) areaInfo = await ensureArea({store, pkgUrl, prepare: false, ...area});
  try { eng = await start(); }
  catch(e){
    if(!area || !/make the area first/.test(e.message)) throw e;
    areaInfo = await ensureArea({store, pkgUrl, prepare: false, ...area, force: true});
    eng = await start();
  }
}
engines.delete(engKey);                                          // in use: destroy() puts it back (host), or ends it
const {worker, call, areaKey, order, pairLines, roadOf, stopHooks} = eng;
const flat = (r) => r.levels.flat();
const hostSide = window.RS_SIDE, hadApi = window.lvApi;          // the host's, for destroy
const events = new EventTarget();
// the worker stops (no memory, a file that does not load): the editor sends the event "error" ({message, fatal: true}); close it and open it again
const onStop = err => events.dispatchEvent(new CustomEvent("error", {detail: {message: err.message, fatal: true}}));
stopHooks.add(onStop);
// a road that the page selected and its popups are not the editor's: they go at the open (the editor's picks are its own)
if(map){ window.rsDeselect?.(); map.getContainer().querySelectorAll(".maplibregl-popup").forEach(p => p.remove()); }
let dirty = false;                                               // an Apply of the person (a solve, or a head or a cap) happened in this editor: the host's tables are behind
const get = (n, bytes) => store.load(n, bytes);
const [editsF, headsF, capsF, levelsF, infoF] = await Promise.all([get("edits.csv"), get("heads.csv"), get("caps.csv"), get("levels.csv"), get("levels_info.json")]);
const inputsKey = async edits => `${areaKey}:${await sha(edits)}`;
// the facts of a road, asked from the worker when the panel needs them (need). A new answer clears the facts.
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
if(own && !basemaps?.style) throw new Error("level editor: the editor's own map needs `basemaps`, the base maps of a host page (host_options.json: style, basemaps, ontop)");
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
if(host){                                                        // the host's map and roads stay; its picks are the editor's (colours, no popup)
  await addFields();
  window.map = map;
  captureHL();
  quiet(true);
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
    map = new ml.Map({container: div, style: basemaps.style, bounds: [[bb[0], bb[1]], [bb[2], bb[3]]],
      attributionControl: {compact: true}});
    map.addControl(new ml.NavigationControl({visualizePitch: true}));
    map.addControl(new ml.ScaleControl({maxWidth: 120, unit: "metric"}), "bottom-left");
  } else map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {padding: 40, duration: 0});
  window.map = map;                                                // the panel (level_editor.html) draws on the global map
  // the page's one dashboard: the host's, else one for the editor (the road fields: the road table RS_SIDE)
  rs = dashboard || rsDashboard(map, {style: null, prefix: P, tiles: true, simple: "roads-simple", edge_id_col: "edge",
    basemaps: basemaps.basemaps, ontop: basemaps.ontop, dashboard: template});
  if(own){                                                         // the area in the part of the map that the panel and the bar leave free
    const f = rs.freeArea(), r = map.getContainer().getBoundingClientRect();
    map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {duration: 0, padding: {left: f.lo - r.left + 40, right: r.right - f.hi + 40, top: f.top - r.top + 40,
      bottom: r.bottom - f.bottom + 40}});
  }
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
    // a live style's global state (rs_colors, rs_co, ...): its start values, as a style with them would set them (the base map has none). A name that the map has
    // keeps its value: the dashboard's theme (rs_theme), and what the person set (the road fill, the Tunnels look) stay while the editor draws its own roads
    const have = map.getGlobalState();
    for(const [k, v] of Object.entries(st.state || {})) if(!(k in have)) map.setGlobalStateProperty(k, v.default ?? null);
    // the area's own layers of the page (the base map's: landcover, water, buildings, ...) stay on the map: the dashboard keeps them (the switch and the legend list) with the
    // style that it had before, whose controls the editor's roads style does not have
    const before = (dashboardStyle?.metadata || {})["roadstyle:controls"] || {};
    if(dashboard && before.overlays?.length){
      st.metadata = {...(st.metadata || {})};
      st.metadata["roadstyle:controls"] = {...(st.metadata["roadstyle:controls"] || {}), overlays: before.overlays};
    }
    for(const [id, src] of Object.entries(st.sources)) map.addSource(P + id, src);
    for(const l of st.layers){
      const layer = JSON.parse(JSON.stringify(l).replaceAll('"oneway"', `"${P}oneway"`));
      map.addLayer({...layer, id: P + l.id, source: P + l.source}, map.getLayer("lv-ends") ? "lv-ends" : undefined);   // under the panel's end marks
    }
    // the taps of a finger: a wide line on the roads that draws nothing (a finger on a phone picks a road with it)
    map.addLayer({id: P + "lv-tap", type: "line", source: P + "lv-roads", "source-layer": "simple", paint: {"line-width": 28, "line-opacity": 0}},
      map.getLayer("lv-ends") ? "lv-ends" : undefined);
    mine.layers.push(P + "lv-tap");
    rs.setStyle(st);
    captureHL();
    highlight(hl.groups);
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
const editRows = () => csvRows(editsText).map(r => Object.fromEntries(TCOLS.map(c => [c, r[c] ?? ""])));
// the time of each road's own row in heads.csv or caps.csv ({road: time}); the readers ignore the column (they read by name)
async function timesOf(text){
  const rs_ = csvRows(text); await need(rs_.map(r => r.road));
  return Object.fromEntries(rs_.filter(r => roadOf[r.road] != null).map(r => [roadOf[r.road], r.time || ""]));
}
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
// "Add from files": the rows of an edits.csv, heads.csv or caps.csv (by its header) as changes for the waiting list, checked as the editor checks
// its own: a rule that the area (or the list) has already, a row that names no road of this area or a value that is not right is skipped and
// counted by its reason (nothing is dropped in silence). Apply then adds them as any change. A head or cap row names the road (as the editor
// writes it); a row by an edge against its road is not swapped here.
async function importRows(text, ops){
  const rs_ = csvRows(text), head = rs_.length ? Object.keys(rs_[0]) : (text.split(/\r?\n/)[0] || "").split(",").map(h => h.trim());
  const skip = {}, out = [], no = why => skip[why] = (skip[why] || 0) + 1;
  if(head.includes("relation")){
    await need(rs_.flatMap(r => [r.a, r.b]));
    const key = r => COLS.map(c => String(r[c] ?? "")).join("|"), have = new Set(after(ops).map(key));
    for(const r of rs_){
      if(r.relation === "crossing"){ no("a crossing row (the editor adds no crossing rules)"); continue; }
      let row; try { row = rowOf(r); } catch(err){ no(/not an edge/.test(err.message) ? "not a road of this area" : err.message); continue; }
      if(have.has(key(row))){ no("already in the area or the list"); continue; }
      have.add(key(row)); out.push({op: "add", body: {...row, time: r.time || ""}});
    }
  } else if(head.includes("road") && (head.includes("start_m") || head.includes("start"))){
    const kind = head.includes("start_m") ? "head" : "cap";
    await need(rs_.map(r => r.road));
    for(const r of rs_){
      if(roadOf[r.road] == null){ no("not a road of this area"); continue; }
      for(const end of ["start", "end"]){
        const v = String(r[kind === "head" ? end + "_m" : end] ?? "").trim();
        if(v === "") continue;                                        // not set: the area keeps its own
        if(kind === "head" ? !(+v > 0) : !["round", "square", "flat"].includes(v)){ no(`a ${kind} that is not right (${v})`); continue; }
        out.push(kind === "head" ? {op: "head", road: r.road, end, m: v} : {op: "cap", road: r.road, end, cap: v});
      }
    }
  } else throw new Error("not an edits.csv, heads.csv or caps.csv: the header has no relation, start_m or start column");
  return {ops: out, skipped: Object.entries(skip), roads: await roadsOf(out.flatMap(o => o.op === "add" ? [o.body.a, o.body.b] : [o.road]).map(x => roadOf[x]))};
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
  const ownRoad = r => { heads[r] ??= ["", ""]; caps[r] ??= ["", ""]; };
  for(const o of ops){
    const r = roadOf[String(o.road)], k = {start: 0, end: 1}[o.end];
    if(o.op === "cap"){
      const c = o.cap || "";
      if(r == null || k == null || !["", "round", "square", "flat"].includes(c)) throw new Error(`ends: ${o.road} is not a road, ${o.end} not start / end, or ${c} not auto, round, square or flat`);
      ownRoad(r);
      caps[r][k] = c === facts[r].caps_auto[k] ? "" : c;          // the default shape is not stored
    } else if(o.op === "head"){
      const m = String(o.m ?? "").trim();
      if(r == null || k == null || !(m === "" || +m > 0)) throw new Error(`heads: ${o.road} is not a road, ${o.end} not start / end, or ${m} not a positive number of metres`);
      ownRoad(r);
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
  const at = stamp();
  const added = ops.filter(o => o.op === "add").map(o => ({...rowOf(o.body), time: o.body.time || at}));   // a rule from a file keeps its time
  for(const r of added){ const k = COLS.map(c => r[c]).join("|");
    if(have.has(k)) throw new Error(`this rule is already in edits.csv: ${say(r)}: nothing saved`); have.add(k); }
  const newEdits = ops.some(o => o.op === "add" || o.op === "delete") ? kept.concat(added) : null;
  // the time of a road's row: now when this apply changed it, else the time it had
  const [hT, kT] = [await timesOf(headsText), await timesOf(capsText)], touched = op => new Set(ops.filter(o => o.op === op).map(o => roadOf[String(o.road)]));
  const [hNew, kNew] = [touched("head"), touched("cap")];
  const headsCsv = toCsv(Object.entries(heads).filter(([, v]) => v.some(Boolean)).sort().map(([road, v]) => ({road, start_m: v[0], end_m: v[1],
    time: hNew.has(road) && JSON.stringify(v) !== JSON.stringify((own[road] || [["", ""]])[0]) ? at : hT[road] || ""})), HCOLS);
  const capsCsv = toCsv(Object.entries(caps).filter(([, v]) => v.some(Boolean)).sort().map(([road, v]) => ({road, start: v[0], end: v[1],
    time: kNew.has(road) && JSON.stringify(v) !== JSON.stringify((own[road] || [, ["", ""]])[1]) ? at : kT[road] || ""})), KCOLS);
  // the roads a change names (level_editor._changed): of the edit rows added or taken out, and those whose heads changed
  const key = r => COLS.map(c => r[c]).join("|"), before = new Set(old.map(key)), now = new Set((newEdits || old).map(key));
  const changed = [...(newEdits || old), ...old].filter(r => before.has(key(r)) !== now.has(key(r))).flatMap(r => [r.a, r.b])
    .concat(Object.keys(heads).filter(r => JSON.stringify((own[r] || [["", ""]])[0]) !== JSON.stringify(heads[r])));
  const nextEdits = newEdits ? toCsv(newEdits, TCOLS) : editsText;
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
  const was = lastCsv ?? (await call({type: "levelsCsv", levels: flat(res), heads: headsText, caps: capsText})).csv;
  await store.save("heads.csv", headsCsv);
  await store.save("caps.csv", capsCsv);
  if(newEdits) await store.save("edits.csv", nextEdits);
  [editsText, headsText, capsText, res] = [nextEdits, headsCsv, capsCsv, next];
  dirty = true;                                                  // before save: a host that hears "solved" finds it set
  await save(res);
  saved -= gone.filter(i => i < saved).length;
  sessionStorage.setItem(SAVED, String(saved));
  // the panel's facts again: of the roads that the changes name and of those whose numbers changed
  facts = {};
  const shown = await roadsOf(ops.flatMap(o => o.op === "add" ? [o.body.a, o.body.b] : [o.road]).map(x => roadOf[String(x)])
    .concat(order.filter((r, i) => res.levels[i].some((v, j) => v !== prev.levels[i][j]))).filter(Boolean));
  // the edges whose row of levels.csv changed are drawn again, and only they (and the edges near them): the host's replaceRoads, or the worker's relevel
  const had = new Set(was.split("\n"));
  const changedRows = csvRows(lastCsv.split("\n").filter((l, i) => i === 0 || !had.has(l)).join("\n"));
  const drawStart = performance.now();
  if(host){
    await host.replaceRoads(changedRows);
    await addFields();
    captureHL(); highlight(hl.groups); quiet(true);                // (a new style of the host has its own colours and popup again)
  } else if(changedRows.length){
    let r = null;
    try { r = await call({type: "relevel", rows: JSON.stringify(changedRows)}); }
    catch(err){ console.warn(`level editor: ${err.message}: the whole map is made again`); }       // (the engine says when it cannot redraw a map)
    if(!r) await showRoads(await build());
    else if(r.style) await showRoads(ownSources(JSON.parse(r.style)));  // the layers changed: the style swapped
    else {                                                         // the same style: the tiles are loaded again (the worker cuts again only the pieces of the changed edges)
      for(const id of mine.sources){ const s = map.getStyle().sources[id]; if(s?.type === "vector") map.getSource(id).setTiles(s.tiles); }
      await new Promise(ok => { map.once("idle", ok); setTimeout(ok, 30000); });
    }
  }
  if(host) said += ` · drawn in ${((performance.now() - drawStart) / 1000).toFixed(1)} s`;
  return {ok: true, said, full, redrawn: true, facts: shown, stats: stats()};
}
window.lvApi = async (path, body) => {
  const u = new URL(path, location.href), q = k => u.searchParams.get(k) || "";
  switch(u.pathname){
    case "/api/edits": { const r = await rows(); return {rows: r, roads: await roadsOf(r.flatMap(x => [x.ra, x.rb]))}; }
    case "/api/ends": {                                          // the roads with their own head lengths or end shapes (heads.csv, caps.csv): only the values now
      const own = JSON.parse((await call({type: "ownEnds", heads: headsText, caps: capsText})).ends);
      const [hT, kT] = [await timesOf(headsText), await timesOf(capsText)];
      return {rows: Object.entries(own).map(([road, [heads, caps]]) => ({road, heads, caps, time: [hT[road] || "", kT[road] || ""].sort().pop()})), roads: await roadsOf(Object.keys(own))}; }
    case "/api/import": return importRows(body.text || "", body.ops || []);
    case "/api/given_up": return givenUp();
    case "/api/find": return find(q("q"));
    case "/api/relations": return relations(q("a"), q("b") || null);
    case "/api/check": return {conflicts: await check(body.rows || [], body.ops || [])};
    case "/api/new_session": saved = editRows().length; sessionStorage.setItem(SAVED, String(saved)); return {ok: true, saved};
    case "/api/apply": return apply(body.ops || []);
  }
  throw new Error("not found: " + path);
};

// --- the panel (static/level_editor.html), with its scripts run, in roadstyle's editor frame (../frame.js; docs/guides/dashboard-parts.md, "An editor in
// the panel"): the frame gives the title line with "← <backLabel>" (none with backLabel null), the dashboard's tab row (with the counts of History and
// Issues), the one body that scrolls and the bar at the bottom edge; open() keeps the host's title and body and hides them, close() shows them again
const html = (await (await fetch(new URL("../../level_editor.html", import.meta.url))).text()).replace("__STATS__", JSON.stringify(stats()));
window.lvColors = [COLORS.select, COLORS.second];
window.lvHighlight = highlight;                                 // the panel gives the picked roads (static/level_editor.html)
window.lvDownload = download;                                    // the History tab's button
const fr = editorFrame({panel, title: "Edit levels", back: backLabel, id: "lv", label: "Level editor",
  tabs: [["ends", "Road ends"], ["edit", "Stacking"], ["history", "History"], ["given", "Issues"]]});
fr.root.id = "lv"; fr.root.dataset.mode = "ends";               // the panel's own rules (#lv ...) and its mode (Road ends or Stacking)
for(const b of fr.root.querySelectorAll("#lv-tabs [data-tab]")) b.dataset.t = b.dataset.tab;      // the attribute of the old tab row: a host's script can still find a tab
// the counts of History and Issues: hidden while 0 (the panel shows them when it has the numbers)
fr.root.querySelector("#lv-tab-history").insertAdjacentHTML("beforeend", '<span class="rs-count" id="lv-hist-n" hidden>0</span>');
fr.root.querySelector("#lv-tab-given").insertAdjacentHTML("beforeend", '<span class="rs-count" id="lv-gu-n" hidden>0</span><span class="rs-count" id="lv-nr-n" hidden>0</span>');
window.lvFrame = fr;
fr.open("ends");
if(window.rs?.sheet && rs.sheet() === 2) rs.sheet(1);         // a phone: the frame opens the sheet at its full height, but you pick the roads on the map: 40 %
const holder = document.createElement("div");
holder.innerHTML = html;
// the panel's parts into the frame (its panes into the body, its apply bar into the bar, the note and the busy cover over the frame), and the listeners
// that its scripts add to the document and the map as they run (destroy takes them off)
const heard = [];
const [docOn, mapOn] = [document.addEventListener, map.on];
document.addEventListener = function(...a){ heard.push(() => document.removeEventListener(...a)); return docOn.apply(this, a); };
map.on = function(...a){ heard.push(() => map.off(...a)); return mapOn.apply(this, a); };
try {
  for(const n of [...holder.childNodes]){
    if(n.id === "lv-src"){
      for(const part of [...n.children]) (part.dataset.pane ? fr.body : part.id === "lv-bar" ? fr.bar : fr.root).appendChild(part);
    } else if(n.tagName === "SCRIPT") fr.root.appendChild(Object.assign(document.createElement("script"), {textContent: n.textContent}));   // it runs here, at once
    else if(n.nodeType === 1) fr.root.appendChild(n);            // the panel's <style>: it goes away with the frame
  }
} finally { [document.addEventListener, map.on] = [docOn, mapOn]; }
fr.root.addEventListener("lv:back", () => events.dispatchEvent(new CustomEvent("back")));
// the help window (rs.help, the dashboard's own): its "?" button is next to the title; destroy() sets the host's own words again, or takes the window away
const hadHelp = rs.help.get();
rs.help.set({...levelsHelp(COLORS, backLabel), anchor: fr.top.querySelector(".t")});

// a finger's tap on a phone: the wide tap line, when the dashboard picked nothing for this tap (its pick box can be wider than the road layers
// under the finger, and its pick comes before the map's click); the road table's row of the piece, which has the road
const narrow = matchMedia("(max-width: 700px)");                 // the dashboard's phone width
let lastPick = -1e9;
const heardPick = (e) => { if(!e.detail.lvTap) lastPick = performance.now(); };
document.addEventListener("rs:select", heardPick);
function tap(e){
  if(host || !narrow.matches) return;
  const f = map.queryRenderedFeatures(e.point, {layers: [P + "lv-tap"]})[0];
  const p = f && window.RS_SIDE?.props[f.id];
  const t = performance.now();
  setTimeout(() => {                                             // ponytail: one gesture = 300 ms around the click
    if(p?.road != null && lastPick < t - 300) document.dispatchEvent(new CustomEvent("rs:select", {detail: {properties: p, lvTap: true}}));
  });
}
map.on("click", tap);
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
  stopHooks.delete(onStop);
  if(token !== undefined) engines.set(engKey, {token, ready: Promise.resolve(eng)});     // the engine waits for the next open of this area
  else worker.terminate();
  map.off("click", tap);
  document.removeEventListener("rs:select", heardPick);
  window.rsColor?.(null);                                        // the colour of the picked roads (the panel's paint) and their glow stay on the map otherwise
  window.rsDeselect?.();
  if(hadHelp) rs.help.set(hadHelp); else rs.help.clear();
  heard.forEach(off => off());
  fr.close();                                                    // the frame and the panel go; the host's title and body show again
  delete window.lvFrame;
  for(const id of [...mine.layers, "lv-ends-end", "lv-ends"]) if(map.getLayer(id)) map.removeLayer(id);
  for(const id of [...mine.sources, "lv-ends"]) if(map.getSource(id)) map.removeSource(id);
  mine.images.forEach(id => map.hasImage(id) && map.removeImage(id));
  if(host){
    quiet(false);
    for(const [id, paint] of hl.orig) if(map.getLayer(id)) for(const [k, v] of Object.entries(paint)) map.setPaintProperty(id, k, v);   // the host's colours
    const t = window.RS_SIDE;
    if(t && t.lvFields){ t.props.forEach(p => { if(p) for(const k of added) delete p[k]; }); delete t.lvFields; }
    if(hadApi) window.lvApi = hadApi; else delete window.lvApi;
    delete window.lvColors; delete window.lvDownload; delete window.lvHighlight;
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
  delete window.lvColors; delete window.lvDownload; delete window.lvHighlight;
}
// the four files as texts, {"edits.csv", "heads.csv", "caps.csv", "levels.csv"}: for a host that keeps them in its own tables (call it before destroy(), or
// after an Apply: levels.csv comes from the last Apply when the worker has ended)
const exportFiles = async () => Object.fromEntries(await Promise.all(Object.keys(files).map(async n => [n, n === "levels.csv" && lastCsv != null ? lastCsv : await files[n]()])));
Object.defineProperty(events, "dirty", {get: () => dirty, enumerable: true});
Object.defineProperty(events, "areaInfo", {get: () => areaInfo, enumerable: true});    // the result of ensureArea of the option `area` (null: none)          // (Object.assign would copy the value, not the getter)
return Object.assign(events, {map, roads: order, facts: roadsOf, download, destroy, files: Object.keys(files), answer: () => res, exportFiles});
}

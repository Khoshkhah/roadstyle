// The level-edit part (docs/design/level_part.md, step e): a card in the dashboard's panel that opens roadstyle's level editor on the page's map. A host gives
// its map, its dashboard and a data adapter (the roads of the area, the stored levels, the write-back, the redraw of changed edges); the part does the rest:
// the card and its line of state, the store, the area, the busy veil, the limit for many roads, the redraw, the close and the write-back.
//
//   const part = levelEditPart({dashboard: rs, map, pkgUrl, data: {edges, storedLevels, saveLevels, relevel, roadsStyle},   // the adapter: see below
//                               card: {id: "level", label: "Edit levels"}, maxRoads: 200000});
//   part.addEventListener("applied", (e) => e.detail.files);   // after the host's tables have the new levels
//   part.open(); part.close(); part.isOpen(); part.editor        // the card calls open()
//
// The adapter `data` (async functions, all of them the host's own data):
//   edges()               the roads of the area as GeoParquet bytes (called only when the area is made)
//   storedLevels()        {csv, edge_hash} of the levels in the host's tables, or null
//   saveLevels(files, {name})  writes {"levels.csv", "edits.csv", "heads.csv", "caps.csv"} (texts) into the host's tables
//   relevel(rows)         draws the changed edges again in the host's map worker; gives {style?} (a style when the layers changed)
//   roadsStyle()          the style of the page's roads; used when the page's roads are not on the map at the open (see `ensureRoads`)
// Optional: roadCount() (for maxRoads), ensureRoads() (the host draws its roads itself; with it, roadsStyle is not used), after(style) (the host's
// own layers on a swapped style), useStyle(style) (the host swaps a style itself), pkg (the roadstyle module, initialised).
// The host also keeps `window.RS_SIDE`, the road table of its roads, as the dashboard reads it (a host that draws roads has it).
// Events: "opening" (the open began: the dashboard's busy veil shows "Opening the level editor…" too), "open", "close", "applied" {files, rules, heads, caps}, "error" {message, fatal}.
// `part.state` is "closed", "opening" or "open"; `part.dirty` is true after an Apply of the person. `part.prepare()` makes the area and the engine before the first open (a
// Promise; the host calls it after its first draw), or the option `prepare: "idle"` does it 500 ms after the map is first idle: the open then does not call `data.edges()` again.
// `areaName` may be a function (read at each open and prepare): the store, its key and the `name` of saveLevels follow the area of that open, so two areas do not share files. The
// levels are read from `data.storedLevels()` at each open (a new build has other levels); `part.reset()` forgets the stores and the prepared area (call it at each build and restore).
// `card` is any option of rs.sections.add (id, label, note, icon, step, before, after, ...): `card: {id: "step8", label: "Edit levels", step: 8, before: "step9"}` is a numbered card.
import {levelEditor, browserStore, ensureArea} from "./level_editor.js";
import {roadLayers} from "../roadlayers.js";

const num = (n, d = 0) => Number(n).toLocaleString("en", {maximumFractionDigits: d}).replace(/,/g, " ");

export function levelEditPart({dashboard = globalThis.rs, map, data, pkgUrl, look = null, card = {}, maxRoads = 200000, panel = document.getElementById("sb"),
                               backLabel = "Steps", prefix = "rs-", before = null, also = [], idCol = "edge_id", areaName = "area", pkg = null, prepare: prepareMode = null}){
  for(const f of ["edges", "storedLevels", "saveLevels", "relevel"]) if(typeof data?.[f] !== "function") throw new Error(`levelEditPart: data.${f}() is necessary`);
  const events = new EventTarget(), id = card.id ?? "level";
  const roads = roadLayers({map, dashboard, prefix, before, also});
  // one store and one state for each area: `areaName` may be a function (read at each open and prepare), so a host with more than one area has no shared files
  const nameOf = () => String(typeof areaName === "function" ? areaName() : areaName);
  const areas = new Map();                                         // name -> {name, store, levels, prepared, synth}
  let cur = null, editArea = null;                                 // cur: the area of the last open or prepare; editArea: the area that the open editor edits
  function area(){
    const name = nameOf();
    if(!areas.has(name)) areas.set(name, {name, store: browserStore("lv-part:" + name, name, {memoryFallback: true}), levels: null, prepared: null, synth: null});
    return cur = areas.get(name);
  }
  // the edge hash of the area: the host's stored levels have it; with none, one token for this area and page (the area is made once, not at each open)
  const hashOf = (a) => a.levels?.edge_hash || (a.synth ??= "part-" + Date.now().toString(36));
  let editor = null, opening = false, applied = false;
  const lostBytes = () => (editArea ?? cur)?.store.lostBytes() ?? 0;
  const note = (t) => dashboard.sections.note(id, t + (lostBytes() ? ` The browser could not keep the area files (${num(lostBytes() / 2 ** 20, 1)} MB): your edits stay only until you close the page; download edits.csv to keep them.` : ""));
  const send = (type, detail) => events.dispatchEvent(new CustomEvent(type, {detail}));
  const roadsOnMap = () => map.getStyle().layers.some(l => l.id.startsWith(prefix));
  // the redraw of the edges that a change of the editor redrew: the host's worker cuts them again, then the tiles load again (or a new style is swapped)
  async function replaceRoads(rows){
    const r = await data.relevel(rows);
    if(r?.style) await (data.useStyle ? data.useStyle(r.style) : roads.show(r.style, {after: data.after}));
    else await roads.reloadTiles();
  }
  function closeEditor(){
    if(!editor) return;
    editor.destroy();
    editor = null;
    document.body.removeAttribute("data-rs-editing");
    map.resize();
    send("close");
  }
  async function leave(){                                          // "← Steps": the editor's own Apply, Discard or Stay came before
    if(!editor.dirty){ closeEditor(); return note("Closed. No change."); }
    try {
      note("writing the drawing order into the tables…");
      const files = await editor.exportFiles();
      await data.saveLevels(files, {name: editArea.name});
      applied = true;                                              // (the next open reads the stored levels again)
      closeEditor();
      const n = (f) => Math.max(0, (files[f] || "").trim().split("\n").length - 1);
      const detail = {files, rules: n("edits.csv"), heads: n("heads.csv"), caps: n("caps.csv")};
      note(`Applied. Rules: ${num(detail.rules)}, heads: ${num(detail.heads)}, line ends: ${num(detail.caps)}. The map has it.`);
      send("applied", detail);
    } catch(e){ note("Apply failed: " + e.message); }              // the editor stays open
  }
  async function open(){
    if(editor || opening) return;
    const count = data.roadCount ? await data.roadCount() : 0;
    if(count > maxRoads) return note(`The level editor shows all ${num(count)} roads of the area. A browser page draws at most ${num(maxRoads)}. Use a smaller area.`);
    const a = area();
    opening = true;
    send("opening");                                               // a host can show a reason now; the busy veil of the dashboard shows "Opening the level editor…" too
    dashboard.mapBusy?.("Opening the level editor…");
    try {
      const t0 = performance.now();
      if(a.prepared){ await a.prepared.promise.catch(() => {}); a.levels = a.prepared.levels; a.prepared = null; }   // the area and the engine that prepare() made, once
      else a.levels = await data.storedLevels();                   // the levels of the tables now (a new build or another area has other levels)
      editArea = a;
      if(!roadsOnMap()){ if(data.ensureRoads) await data.ensureRoads(); else await roads.show(await data.roadsStyle()); }
      dashboard.mapBusy?.("Opening the level editor…");            // a draw that ran meanwhile put the veil away
      editor = await levelEditor({map, panel, backLabel, pkgUrl, store: a.store, dashboard, prefix, levels: a.levels ?? undefined, look,
        host: {edgeIdCol: idCol, replaceRoads}, area: {edges: data.edges, edgeHash: hashOf(a), idCol, pkg}});
      const made = `${num(editor.roads.length)} roads` + (editor.areaInfo?.warnings?.length ? `. Warnings: ${editor.areaInfo.warnings.join("; ")}` : "");
      editor.addEventListener("solved", () => note(`${made}. Changed: ← Steps applies the new drawing order.`));
      editor.addEventListener("back", leave);
      editor.addEventListener("error", (e) => { note(`The level editor's worker stopped (${e.detail.message}). Close the editor and open it again.`); send("error", e.detail); });
      document.body.setAttribute("data-rs-editing", "levels");
      note(`${made}, open in ${num((performance.now() - t0) / 1000, 1)} s`);
      send("open");
    } catch(e){
      closeEditor();
      note("The level editor failed: " + e.message);
      send("error", {message: e.message, fatal: true});
    } finally { opening = false; dashboard.mapBusy?.(null); }
  }
  // the area and the engine, made before the first open: the first open is then as fast as the next ones (the open uses it once)
  function prepare(){
    const a = area();
    if(!a.prepared){
      const pre = {levels: null};
      pre.promise = (async () => {
        pre.levels = a.levels = await data.storedLevels();
        await ensureArea({store: a.store, edgeHash: hashOf(a), edges: data.edges, pkg, pkgUrl, idCol, look});
      })().catch((e) => { a.prepared = null; throw e; });
      a.prepared = pre;
    }
    return a.prepared.promise;
  }
  // the host calls it at each build and restore: the part forgets the stores and the levels, and reads them again at the next open or prepare
  function reset(){ if(editor) throw new Error("levelEditPart: close the editor before reset()"); areas.clear(); cur = null; applied = false; }
  if(prepareMode === "idle") map.once("idle", () => setTimeout(() => prepare().catch((e) => console.warn("level edit part: prepare failed:", e.message)), 500));
  dashboard.sections.add({...card, id, label: card.label ?? "Edit levels", note: card.note ?? "", icon: card.icon ?? "edit", open});   // `card`: any option of rs.sections.add (step, before, after, ...)
  Object.defineProperty(events, "editor", {get: () => editor, enumerable: true});          // (Object.assign would copy the values, not the getters)
  Object.defineProperty(events, "state", {get: () => editor ? "open" : opening ? "opening" : "closed", enumerable: true});
  Object.defineProperty(events, "dirty", {get: () => !!editor?.dirty || applied, enumerable: true});
  return Object.assign(events, {open, close: closeEditor, isOpen: () => !!editor, prepare, reset, roads});
}

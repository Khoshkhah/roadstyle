// The level editor's engine in a Web Worker (level_editor.js), so that the page does not stop while it solves, makes the map (the map's
// table, stage 1, stage 2) or cuts a tile: it keeps the area (roadstyle-wasm's LevelArea) and the tiles of its map (a LiveMap). The calls
// (worker/call.js): init (the package's URL and the map's look), open, roadOf, facts, ownEnds, find, levelsOf, edgeHash, solve,
// solveLocal, startFrom, check, levelsCsv, draw, build, relevel and tile. A map of the editor's own is built once (build); a change goes
// to relevel, which redraws only the edges that changed and the edges near them.
import {answer} from "../worker/call.js";

let pkg = null, area = null, look = null, live = null, gen = 0;
const i32 = (a) => Int32Array.from(a);
const bytes = (b) => ({bytes: b, transfer: [b.buffer]});

answer({
  // `base`: the text of the page's saved look. The editor's roads have the page's palette and sections (the colours, the widths, the dark theme), and the page's colour options
  // (the legend's "Colour by" list), over the editor's own map options: its column names (the page's columns name the page's own table), the state `live` and the colours of its picks
  async init({pkgUrl, look: options, base}){
    pkg = await import(pkgUrl);
    await pkg.default();
    look = pkg.resolveLook(options);
    if(base){
      const page = JSON.parse(base), own = JSON.parse(look.toJson()).map;
      look = pkg.Look.fromJson(JSON.stringify({...page, map: {...own, color: {...own.color, options: page.map.color.options, active: page.map.color.active}}}));
    }
  },
  open({roads, pairs}){
    area = new pkg.LevelArea(new Uint8Array(roads), pairs);
    return {roads: area.roadIds()};
  },
  // what the panel shows of some roads, when it asks (LevelArea's factsOf, roadOf, ownEnds, find)
  roadOf: ({ids}) => ({roads: area.roadOf(ids)}),
  facts: ({ids, heads, caps}) => ({facts: area.factsOf(ids, heads, caps)}),
  ownEnds: ({heads, caps}) => ({ends: area.ownEnds(heads, caps)}),
  find: ({q}) => ({hits: area.find(q)}),
  levelsOf: ({csv}) => ({levels: area.levelsOf(csv) ?? null}),
  edgeHash: () => ({hash: area.edgeHash()}),
  solve: ({edits}) => ({answer: area.solve(edits)}),
  solveLocal: ({edits, changed}) => ({answer: area.solveLocal(edits, changed)}),
  startFrom({levels, parts, orders, near, crossings}){ area.startFrom(i32(levels), parts, orders, near, crossings); },
  check: ({edits, rows}) => ({conflicts: area.check(edits, rows)}),
  levelsCsv: ({levels, heads, caps}) => ({csv: area.levelsCsv(i32(levels), heads, caps)}),
  draw: ({levels, heads, caps}) => bytes(area.draw(i32(levels), heads, caps)),
  // the map of an answer: its style (a new generation of lv:// tiles) and its road table (the dashboard's RS_SIDE)
  build({levels, heads, caps, keep, table}){
    const src = pkg.styleSources(area.draw(i32(levels), heads, caps), look, undefined, undefined, "Level editor");
    const rows = src.roadTable(table, true);                      // only the fields that the page reads, and the lines
    if(live) live.free();
    live = new pkg.LiveMap(src, look, `lv://${++gen}/`, keep);    // takes `src`
    return {style: live.style(), table: rows, transfer: [rows.buffer]};
  },
  // a change: `rows` (JSON text, the levels.csv rows of the edges that changed) give those edges their new levels, heads and caps. The map has the same
  // generation: the tiles that show those edges are cut again, the other tiles stay. `style` only when the layers changed.
  relevel({rows}){
    const counts = JSON.parse(live.relevel(rows));
    return {counts, style: counts.style_changed ? live.style() : null};
  },
  tile({url}){
    const [g, source, z, x, y] = url.slice("lv://".length).split("?")[0].split("/")     // the style's URL has ?g=<generation>;
    return bytes(+g === gen ? live.tile(source, +z, +x, +y) : new Uint8Array());
  },
});

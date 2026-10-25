// The level editor's engine in a Web Worker (level_editor.js), so that the page does not stop while it solves, makes the map (the map's
// table, stage 1, stage 2) or cuts a tile: it keeps the area (roadstyle-wasm's LevelArea) and the tiles of the last map. The calls
// (worker/call.js): init (the package's URL and the map's look), open, ends, solve, solveLocal, startFrom, check, levelsCsv, draw, build
// and tile.
import {answer} from "../worker/call.js";

let pkg = null, area = null, look = null, tiler = null, gen = 0;
const i32 = (a) => Int32Array.from(a);
const bytes = (b) => ({bytes: b, transfer: [b.buffer]});

answer({
  async init({pkgUrl, look: options}){
    pkg = await import(pkgUrl);
    await pkg.default();
    look = pkg.resolveLook(options);
  },
  open({roads, pairs}){
    area = new pkg.LevelArea(new Uint8Array(roads), pairs);
    return {facts: area.facts(), auto: area.ends("", "")};
  },
  ends: ({heads, caps}) => ({ends: area.ends(heads, caps)}),
  solve: ({edits}) => ({answer: area.solve(edits)}),
  solveLocal: ({edits, changed}) => ({answer: area.solveLocal(edits, changed)}),
  startFrom({levels, parts, orders, near, crossings}){ area.startFrom(i32(levels), parts, orders, near, crossings); },
  check: ({edits, rows}) => ({conflicts: area.check(edits, rows)}),
  levelsCsv: ({levels, heads, caps}) => ({csv: area.levelsCsv(i32(levels), heads, caps)}),
  draw: ({levels, heads, caps}) => bytes(area.draw(i32(levels), heads, caps)),
  // the map of an answer: its style (a new generation of lv:// tiles) and its road table (the dashboard's RS_SIDE)
  build({levels, heads, caps, keep, table}){
    const src = pkg.makeSources(area.draw(i32(levels), heads, caps), look, undefined, undefined, "Level editor");
    const rows = src.roadTable(table);                            // only the fields that the page reads
    if(tiler) tiler.free();
    tiler = pkg.tileSources(src, `lv://${++gen}/`, keep);
    src.free();
    return {style: tiler.style(), table: rows, transfer: [rows.buffer]};
  },
  tile({url}){
    const [g, source, z, x, y] = url.slice("lv://".length).split("/");
    return bytes(+g === gen ? tiler.tile(source, +z, +x, +y) : new Uint8Array());
  },
});

// LIVE DATA (R22): rs.setData(table, options) joins a table to the roads, by edge_id or by the row, and gives each road its colour and its
// width factor as feature state on its row (the names of the style's metadata roadstyle:live: rs_c and rs_w), which the road layer reads.
// The colour goes through color.js, which also has rsColor's and rsColorBase's colours for rs_c (theirs win).
// No new style and no tile reload: a second call replaces only the values. rs.clearData() takes them away. The legend shows the data, and
// the popup and the panel show the joined fields (core.js, _joined).
import {map, O, RoadTable, _src, _setJoined, _emit} from "./core.js";
import {setLiveLegend} from "./legend.js";
import {setLiveColors} from "./color.js";
let _liveRows = [];                  // the rows that have a live width now
const _hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
const _toHex = v => "#" + v.map(x => Math.round(x).toString(16).padStart(2, "0")).join("");
// the colour at t (0..1) on a ramp of colours, linear between its stops (the engine's ramps: branca's LinearColormap, 9 stops); stepped:
// the nearest stop (SonoFlow's Daily page colours so)
function _at(ramp, t, stepped){
  const x = Math.max(0, Math.min(1, t)) * (ramp.length - 1), i = Math.min(ramp.length - 2, Math.floor(x)), f = x - i;
  if(stepped) return ramp[Math.round(x)];
  const a = _hex(ramp[i]), b = _hex(ramp[i + 1]);
  return _toHex(a.map((v, k) => v + (b[k] - v) * f)); }
function _rows(table){
  if(Array.isArray(table)) return table;
  if(table && typeof table.toArray === "function") return table.toArray().map(r => r && typeof r.toJSON === "function" ? r.toJSON() : {...r});   // an Arrow table
  throw new Error("rs.setData: the table must be an array of rows, an Arrow table or the URL of a JSON array"); }
function _range(vals, lo, hi){
  const v = vals.filter(x => typeof x === "number" && isFinite(x));
  return [lo != null ? lo : Math.min(...v), hi != null ? hi : Math.max(...v)]; }
export async function setData(table, opts){
  const o = opts || {}, L = O.live, t0 = performance.now();
  if(!L) throw new Error("rs.setData: this style has no live data (make it with live_data=True: the metadata roadstyle:live)");
  if(typeof table === "string") table = await (await fetch(table)).json();
  const rows = _rows(table), key = o.key || O.edge_id_col, s = _src("simple");
  if(!s) throw new Error("rs.setData: the style has no road pieces (the role simple)");
  const joined = new Map();
  if(key === "row") rows.forEach(r => { if(r.row != null) joined.set(+r.row, r); });
  else {
    const at = new Map(); for(let i = 0, n = RoadTable.rows(); i < n; i++){ const v = RoadTable.props(i)[O.edge_id_col]; if(v != null) at.set(String(v), i); }
    rows.forEach(r => { const i = at.get(String(r[key])); if(i != null) joined.set(i, r); }); }
  // the colour: a number on the ramp from vmin to vmax (else the data's range), a text a ramp colour for each value; no value: nodata
  const ramp = o.ramp || L.ramp, nodata = o.nodata !== undefined ? o.nodata : L.nodata, cols = new Map(), ws = new Map();
  let legend = null;
  if(o.colorBy){
    const vals = [...joined.values()].map(r => r[o.colorBy]), num = vals.some(v => typeof v === "number");
    if(num){ const [lo, hi] = _range(vals, o.vmin, o.vmax);
      joined.forEach((r, i) => { const v = r[o.colorBy]; if(typeof v === "number" && isFinite(v)) cols.set(i, _at(ramp, hi > lo ? (v - lo) / (hi - lo) : 0.5, o.stepped)); });
      legend = {kind: "continuous", title: o.colorBy, ramp: ramp, vmin: lo, vmax: hi, stepped: !!o.stepped}; }
    else { const cats = [...new Set(vals.filter(v => v != null).map(String))].sort(), col = {};
      cats.forEach((c, k) => { col[c] = _at(ramp, cats.length > 1 ? k / (cats.length - 1) : 0.5, o.stepped); });
      joined.forEach((r, i) => { const v = r[o.colorBy]; if(v != null) cols.set(i, col[String(v)]); });
      legend = {kind: "categorical", title: o.colorBy, entries: cats.map(c => [c, col[c]])}; }
    if(nodata) for(let i = 0, n = RoadTable.rows(); i < n; i++) if(!cols.has(i)) cols.set(i, nodata);
  }
  // the width: a factor of the drawn width, from widthRange[0] at the smallest value to widthRange[1] at the largest
  if(o.widthBy){
    const vals = [...joined.values()].map(r => r[o.widthBy]), [lo, hi] = _range(vals), [w0, w1] = o.widthRange || [1, 3];
    joined.forEach((r, i) => { const v = r[o.widthBy]; if(typeof v === "number" && isFinite(v))
      ws.set(i, w0 + (hi > lo ? (v - lo) / (hi - lo) : 0.5) * (w1 - w0)); }); }
  // a second call replaces the values: a row that has none now loses the old ones
  _liveRows.forEach(i => { if(!ws.has(i)) map.removeFeatureState({...s, id: i}, L.width); });
  ws.forEach((v, i) => map.setFeatureState({...s, id: i}, {[L.width]: v}));
  _liveRows = [...ws.keys()];
  setLiveColors(cols);
  _setJoined(joined);
  setLiveLegend(o.legend === false ? null : legend && {...legend, ...(o.legend || {})});
  const ms = performance.now() - t0;
  _emit("rs:datachange", {rows: rows.length, matched: joined.size, colorBy: o.colorBy || null, widthBy: o.widthBy || null, ms});
  return {rows: rows.length, matched: joined.size, ms};
}
export function clearData(){
  const L = O.live, s = _src("simple");
  if(L && s) _liveRows.forEach(i => map.removeFeatureState({...s, id: i}, L.width));
  _liveRows = []; setLiveColors(null); _setJoined(null); setLiveLegend(null);
  _emit("rs:datachange", {rows: 0, matched: 0, colorBy: null, widthBy: null});
}

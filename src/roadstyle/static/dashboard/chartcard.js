// The part "chart" (docs/guides/charts.md): a chart in a card of the panel, with no JavaScript of the page. A page adds it with `{id, part: "chart",
// chart: {kind, x, y, agg, scale, data, title, height, follow}}`. With no `data`, the rows are the map's own road table (x and y are road columns);
// with `data`, they are the page's own rows ({columns, rows}, or a list of objects). A bar, a line or a pie joins the rows of each value of x with
// `agg` (with no y: the count of rows); a number x with more than 40 values goes in ranges, as in the data dock (rs.chart.ranges). rs.chart draws it.
// A click on a mark of the map's roads lights its roads (the highlight set "chart"), a second click ends the light; with `data`, a click sends
// rs:chartpick {id, row, rows}. `follow: true` draws the chart again for the roads that the map shows now (rs:filterchange).
import {RoadTable, _emit} from "./core.js";
import {rsChart} from "./chart.js";
import {_roadTest} from "./filter.js";
const _CC_KINDS = ["bar", "line", "histogram", "scatter", "pie"], _CC_AGGS = ["sum", "mean", "min", "max", "count"];
const _CC_LIGHT = "chart";
// the type of a column of plain values: the first value that is not null tells it ("2026-06-01": a date, "2026-06-01 08:00": a time)
function _ccType(rows, j){
  for(const r of rows){ const v = r[j]; if(v == null) continue;
    return typeof v === "number" || typeof v === "bigint" ? "DOUBLE" : typeof v === "boolean" ? "BOOLEAN"
      : /^\d{4}-\d\d-\d\d$/.test(v) ? "DATE" : /^\d{4}-\d\d-\d\d[ T]\d\d:\d\d/.test(v) ? "TIMESTAMP" : "VARCHAR"; }
  return "VARCHAR";
}
// the page's own rows as {columns, rows}: as they are, or of a list of objects (the keys of the first 100 objects)
function _ccTable(data){
  if(Array.isArray(data)){
    const names = [...new Set([].concat(...data.slice(0, 100).map(o => Object.keys(o || {}))))], rows = data.map(o => names.map(n => (o || {})[n] ?? null));
    return {columns: names.map((name, j) => ({name, type: _ccType(rows, j)})), rows};
  }
  if(data && Array.isArray(data.columns) && Array.isArray(data.rows)) return data;
  throw new Error("rs.sections.add: chart.data is {columns, rows} or a list of objects");
}
// the drawn table of a chart card: {columns, rows, members} (members[i]: the source rows of drawn row i), from the source's columns and rows
function _ccDrawn(c, cols, rows, roads){
  const ys = [].concat(c.y ?? []), at = n => cols.findIndex(k => k.name === n), xi = at(c.x), yi = ys.map(at), k = c.scale ?? 1;
  if(xi < 0 || yi.some(i => i < 0) || c.kind === "histogram") return {columns: cols, rows, members: null};     // (rs.chart says what is wrong)
  const num = v => v == null || v === "" ? null : isFinite(+v) ? +v : null;
  if(c.kind === "scatter") return {columns: [cols[xi], {name: ys[0], type: "DOUBLE"}], rows: rows.map(r => [r[xi], num(r[yi[0]]) == null ? null : num(r[yi[0]]) * k]),
                                   members: rows.map((r, i) => [i])};
  const xNum = rsChart.isNumber(cols[xi].type), xTime = rsChart.isTime(cols[xi].type), keys = rows.map(r => r[xi]);
  const many = (c.kind === "bar" || c.kind === "pie") && xNum && new Set(keys).size > 40;
  const rg = many ? rsChart.ranges(keys.map(num).filter(v => v != null), c.kind === "pie" ? 6 : 12) : null;
  const yNames = ys.length ? ys : [roads ? "roads" : "rows"], agg = ys.length ? c.agg || "sum" : "count";
  const groups = new Map();
  rows.forEach((r, i) => {
    if(many && num(r[xi]) == null) return;
    const key = many ? rg.of(num(r[xi])) : String(r[xi]);
    let g = groups.get(key);
    if(!g) groups.set(key, g = {x: many ? rg.label(key) : r[xi], at: many ? key : null, acc: yNames.map(() => ({s: 0, n: 0, lo: Infinity, hi: -Infinity})), members: []});
    g.members.push(i);
    yi.forEach((j, m) => { const v = num(r[j]); if(v == null) return; const a = g.acc[m]; a.s += v; a.n++; if(v < a.lo) a.lo = v; if(v > a.hi) a.hi = v; });
    if(!ys.length) g.acc[0].n++;
  });
  const val = a => agg === "count" ? a.n : !a.n ? null : agg === "mean" ? a.s / a.n : agg === "min" ? a.lo : agg === "max" ? a.hi : a.s;
  let list = [...groups.values()];
  // the order: ranges and a number or a time x from small to large; the map's roads by the first value, the largest first; the page's rows as they come
  if(many) list.sort((a, b) => a.at - b.at);
  else if(xNum || xTime) list.sort((a, b) => (xTime ? Date.parse(String(a.x)) - Date.parse(String(b.x)) : num(a.x) - num(b.x)));
  else if(roads) list.sort((a, b) => (val(b.acc[0]) ?? -Infinity) - (val(a.acc[0]) ?? -Infinity));
  return {columns: [many ? {name: c.x, type: "VARCHAR"} : cols[xi], ...yNames.map(name => ({name, type: "DOUBLE"}))],
          rows: list.map(g => [g.x, ...g.acc.map(a => { const v = val(a); return v == null ? null : v * k; })]), members: list.map(g => g.members)};
}
export function chartCardPart(spec){
  const c = spec.chart || {};
  const bad = !_CC_KINDS.includes(c.kind) ? "chart.kind is one of " + _CC_KINDS.join(", ") : !c.x ? "chart.x (a column) is necessary"
    : c.kind === "histogram" && c.y != null ? "a histogram has no chart.y" : c.agg != null && !_CC_AGGS.includes(c.agg) ? "chart.agg is one of " + _CC_AGGS.join(", ")
    : c.follow && c.data != null ? "chart.follow is for the map's roads, not for chart.data" : null;
  if(bad) throw new Error("rs.sections.add: '" + spec.id + "': " + bad);
  const own = c.data != null ? _ccTable(c.data) : null;
  const el = document.createElement("div"); el.className = "rs-chart-card"; el.style.height = (c.height || 220) + "px";
  let chart = null, drawn = null, roads = null, lit = -1;
  const light = (i, colour) => {
    lit = i;
    window.rsHighlight(i < 0 ? [] : drawn.members[i].map(m => roads[m]), {set: _CC_LIGHT, color: colour, opacity: 0.85});
  };
  // the colour of drawn row i: its slice of a pie (the slices are in the order of their values), else the first chart colour
  const colourOf = i => {
    let slot = 0;
    if(c.kind === "pie"){ const v = r => drawn.rows[r][1] ?? 0, order = drawn.rows.map((r, j) => j).filter(j => v(j) > 0).sort((a, b) => v(b) - v(a)); slot = Math.max(0, order.indexOf(i)) % 8; }
    return getComputedStyle(el).getPropertyValue("--rs-chart-" + (slot + 1)).trim() || "#0d9488";
  };
  const pick = i => {
    if(!drawn.members) return;
    if(own){ const row = Object.fromEntries(drawn.columns.map((k, j) => [k.name, drawn.rows[i][j]]));
      _emit("rs:chartpick", {id: spec.id, row, rows: drawn.members[i].slice()}); return; }
    light(lit === i ? -1 : i, colourOf(i));
  };
  const draw = () => {
    let cols, rows;
    if(own){ cols = own.columns; rows = own.rows; }
    else {
      const on = c.follow ? _roadTest().edgeOn : null, names = [c.x, ...[].concat(c.y ?? [])];
      roads = []; for(let i = 0, n = RoadTable.rows(); i < n; i++) if(!on || on(i)) roads.push(i);
      rows = roads.map(i => { const p = RoadTable.props(i); return names.map(n => p[n] ?? null); });
      cols = names.map((name, j) => ({name, type: _ccType(rows, j)}));
    }
    if(lit >= 0) light(-1);
    drawn = _ccDrawn(c, cols, rows, own ? null : roads);
    const s = {kind: c.kind, x: c.x, y: drawn.columns.slice(1).map(k => k.name), columns: drawn.columns, rows: drawn.rows, values: null,
               title: c.title || (spec.label ? false : undefined), onPick: drawn.members ? pick : null,
               count: rows.length.toLocaleString("en").replace(/,/g, " ") + (own ? " rows" : " roads")};      // the source's rows, not the groups
    if(c.kind === "histogram"){ s.y = undefined; }
    else if(s.y.length === 1) s.y = s.y[0];
    chart ? chart.set(s) : (chart = rsChart(el, s));
  };
  // the first draw after rs.sections.add puts the card in the panel (rs.chart reads the box's size); again when the road table comes or the map's filter changes
  queueMicrotask(draw);
  if(!own) document.addEventListener("rs:tableready", () => { if(el.isConnected) draw(); });
  if(c.follow) document.addEventListener("rs:filterchange", e => { if(el.isConnected && chart && !(e.detail && e.detail.overlay)) draw(); });
  return el;
}

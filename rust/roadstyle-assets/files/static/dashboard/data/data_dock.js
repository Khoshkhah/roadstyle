// The data dock (docs/design/ask_and_data_dock.md, "2. The data dock"; docs/guides/data-dock.md): one SQL line over a wide table, in the bottom dock. The host
// runs the SQL on its own data (`query`) and tells what the data has (`schema`); roadstyle knows no database. The dock shows the result in rs.dock.table,
// lights the result's roads on the map (the highlight set "dock"), and keeps the lasting map changes of the page as layers in its buttons Colour and Focus.
//
//   dataDock({dashboard, query, schema, ready, tables, load, idColumn, keys, roadsBy, sql, label, limit, card, guard}) -> EventTarget + {run, show, sql, result,
//     csv, stop, open, close, ready, roads, idColumn, keyOf, roadsOf, colour, focus, layers, remove, lightOff, schema}
//   events: "run" {sql, columns, rows, more, ms, source}, "error" {sql, message, source}, "layers" {layers}
import {guard as guardSql, inner} from "./guard.js";
import {rsSelectBoxes} from "../selectbox.js";

const $ = (tag, cls, text) => { const e = document.createElement(tag); if(cls) e.className = cls; if(text != null) e.textContent = text; return e; };
const PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#9a6324"];
const LIGHT = {set: "dock", color: "#7c4dff", opacity: 0.55};          // the light: roadstyle's select purple on the road's own fill
const MAP_LIMIT = 100000, CSV_LIMIT = 1000000;
const quoteId = (c) => '"' + String(c).replace(/"/g, '""') + '"';
const lit = (v) => typeof v === "string" ? "'" + v.replace(/'/g, "''") + "'" : typeof v === "bigint" ? String(v) : String(v);
const fmt = (n) => Number(n).toLocaleString("en").replace(/,/g, " ");
const sentence = (s) => { const t = String(s || "").split("\n")[0].replace(/^.*?Error: /, "").trim(); return /[.!?]$/.test(t) ? t : t + "."; };

// a value that a person can read: a DATE and a TIMESTAMP that come as milliseconds, a geometry that comes as bytes (the design: "Values that a person can read")
function readable(columns, rows){
  const conv = columns.map((c) => { const t = String(c.type || "");
    return /^date/i.test(t) ? (v) => typeof v === "number" || typeof v === "bigint" ? new Date(Number(v)).toISOString().slice(0, 10) : v
      : /^timestamp/i.test(t) ? (v) => typeof v === "number" || typeof v === "bigint" ? new Date(Number(v)).toISOString().slice(0, 19).replace("T", " ") : v
      : (v) => v instanceof Uint8Array ? `(${v.length} bytes)` : v; });
  return rows.map((r) => r.map((v, i) => v == null ? v : conv[i](v)));
}
// the condition of a query, short (the name of a layer): the part after WHERE, at most 38 characters, cut at a word; with no WHERE, the table
export function shortOf(sql){
  const s = String(sql || "").replace(/\s+/g, " ").trim(), m = s.match(/\bWHERE\b(.*?)(\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)/i);
  let t = m && m[1].trim() ? m[1].trim() : ((s.match(/\bFROM\s+([\w."]+)/i) || [])[1] || "roads");
  while(t.endsWith(")") && (t.match(/\)/g) || []).length > (t.match(/\(/g) || []).length) t = t.slice(0, -1).trim();
  return t.length > 38 ? t.slice(0, t.lastIndexOf(" ", 38) > 20 ? t.lastIndexOf(" ", 38) : 38) + "…" : t;
}
const idsKey = (ids) => { let h = 0; for(const s of [...ids].sort()) for(let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return ids.length + ":" + h; };

export function dataDock(o = {}){
  const rs = o.dashboard || window.rs, ID = o.idColumn || "edge_id", KEYS = o.keys || ["osm_id", "name"], LIMIT = o.limit || 1000;
  if(typeof o.query !== "function" || typeof o.schema !== "function") throw new Error("dataDock: query and schema are necessary.");
  if((o.tables || []).length && typeof o.load !== "function") throw new Error("dataDock: tables need load (the host loads each one).");
  const events = new EventTarget(), emit = (name, detail) => events.dispatchEvent(new CustomEvent(name, {detail}));
  // the data is ready when the host's data is loaded and every table of the page too; a table that does not load does not stop the others
  const ready = (async () => { await o.ready; for(const t of o.tables || []) await Promise.resolve(o.load(t)).catch((e) => console.warn(`dataDock: the table ${t.name} did not load: ${e.message}`)); })();
  let loaded = false; ready.then(() => { loaded = true; }, () => {});

  // ---- the parts: the actions in the dock's title row, the SQL line, the error line, the list of tables, the table and the road card beside it ----
  const el = $("div", "rs-dd"), acts = $("span", "rs-dd-acts");
  const tablesB = $("button", "rs-dd-qb rs-dd-ib rs-dd-tablesb"), csvB = $("button", "rs-dd-qb rs-dd-ib"), colourB = $("button", "rs-dd-mb"), focusB = $("button", "rs-dd-mb");
  for(const b of [tablesB, csvB, colourB, focusB]) b.type = "button";
  colourB.innerHTML = 'Colour <span class="rs-dd-count" hidden></span> ▾'; focusB.innerHTML = 'Focus <span class="rs-dd-count" hidden></span> ▾';
  colourB.title = "The colour layers of the map"; focusB.title = "The focus of the map: the other roads fade or hide";
  tablesB.title = "The tables of the data"; tablesB.setAttribute("aria-label", tablesB.title); csvB.title = "Download all the rows of this result as a CSV file"; csvB.setAttribute("aria-label", csvB.title);
  // two icons at the ends of the SQL line (Kaveh, 2026-11-07): the download of the rows before the line ("csv should change to just download icon"),
  // and the tables of the data after Run (a database; "Tables" was too near the view button "Table")
  tablesB.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13"/><path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/></svg>';
  csvB.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5"/><path d="M5 19h14"/></svg>';
  // Table | Chart: two views of the same result (the design's "4. Charts")
  const viewSw = $("span", "rs-seg rs-dd-view"), tableB = $("button", "on", "Table"), chartB = $("button", "", "Chart");
  tableB.type = chartB.type = "button"; viewSw.append(tableB, chartB);
  // the light: the roads of the table in purple on the map, on by default; off, the map shows its own colours (Kaveh, 2026-11-06: "there is no easy way to
  // see map with default colors after opening a table"). The browser keeps the choice. A closed dock lights nothing.
  const LIGHT_KEY = "rs-data-light:" + location.pathname;
  let lightOn = (() => { try{ return localStorage.getItem(LIGHT_KEY) !== "0"; }catch(e){ return true; } })();
  // the map switch (Kaveh, 2026-11-07: "it must change to something for show or unshow the table on map", and "only be on or off for those colour
  // and focus [buttons]. for off make them disable and on make them enable"): roadstyle's on/off switch at the start of the map group. On, the table is
  // on the map: its roads are lit, the dock's Colour and Focus layers show, and a host draws its own shapes of the result (the event `light`). Off,
  // the map shows its own colours: no light, the layers are hidden (they stay in their lists), and Colour and Focus are disabled.
  const lightB = $("label", "rs-switch rs-dd-light"), lightIn = $("input"), lightS = $("span"), lightT = "The table on the map. On: its roads are lit, " +
    "the Colour and Focus layers show, and the shapes that the page draws. Off: the map shows its own colours, and Colour and Focus are disabled. " +
    "A closed dock shows no light.";
  lightIn.type = "checkbox"; lightIn.setAttribute("role", "switch"); lightIn.setAttribute("aria-label", "The table on the map"); lightB.title = lightT;
  lightB.append(lightIn, lightS);
  function setLight(on){
    lightOn = on; lightIn.checked = on; lightS.textContent = on ? "On" : "Off"; colourB.disabled = focusB.disabled = !on;
    try{ localStorage.setItem(LIGHT_KEY, on ? "1" : "0"); }catch(e){}
  }
  lightIn.onchange = () => { setLight(lightIn.checked); light(); paint(); tellLight(); };
  setLight(lightOn);
  // the event `light` {on}: the table is shown on the map now (the switch is on and the dock is open), when that changes; `data.light()` reads it
  let shownNow = false;
  const shown = () => lightOn && rs.dock.isOpen();
  const tellLight = () => { const on = shown(); if(on !== shownNow){ shownNow = on; emit("light", {on}); } };
  // the title row: what the dock shows (Table | Chart) and the map (the switch, Colour, Focus), in the look of joined groups (Kaveh chose "connected
  // groups"). Tables and CSV are on the SQL line (Kaveh, 2026-11-07: "they are unrelated to that row"): the data that the SQL reads, and its rows.
  const grp = (cls, ...els) => { const g = $("span", "rs-dd-grp " + cls); g.append(...els); return g; };
  acts.append(viewSw, grp("rs-dd-g-map", lightB, colourB, focusB));
  const q = $("div", "rs-dd-q"), line = $("button", "rs-dd-line"), run = $("button", "sb-primary rs-dd-run", "Run");
  line.type = run.type = "button"; line.title = "Click to edit. Ctrl+Enter runs it.";
  q.append(csvB, line, run, tablesB);      // the download before the line, the tables after Run (Kaveh, 2026-11-07: "that download button and tables button must be swap place")
  const err = $("div", "rs-dd-err"), list = $("div", "rs-dd-tables"); list.hidden = true;
  // the side column beside the table or the chart (Kaveh, 2026-11-06: the list of the tables "in the same place" as the card of a road): one of the
  // two at a time, the last one opened; the table and the chart stay in view
  // the table has a fixed width (Kaveh, 2026-11-06: "I want to fix the length of table and chart part"): on a desktop the side column always keeps
  // its place beside the table, with a hint while it has neither a card nor the list; on a phone it shows only with one of the two. The chart takes
  // the width of an empty side column (a reviewer, 2026-11-06: 300 px with only the hint in it); CSS .rs-dd-chart:not([hidden]) ~ .rs-dd-side.empty
  const split = $("div", "rs-dd-split"), side = $("div", "rs-dd-side"), card = $("div", "rs-dd-card"), hint = $("p", "rs-dd-side-hint", "Select a road or an item on the map, or a row in the table, or open the tables (the database button).");
  card.hidden = true;
  const table = rs.dock.table({columns: [], rows: [], idColumn: ID, onRow: (r, i, cols) => { const k = cols.findIndex((c) => c.name === ID); emit("row", {columns: cols, row: r, index: i, rowId: k >= 0 && r[k] != null ? String(r[k]) : null}); rowClick(r, cols); }, onSort: (col, dir) => sortAll(col, dir)});
  const chartBox = $("div", "rs-dd-chart"), chartRow = $("div", "rs-dd-chartrow"), chartEl = $("div", "rs-dd-chartel"); chartBox.hidden = true;
  const kindS = $("select"), xS = $("select"), yS = $("select"), svgB = $("button", "", "SVG");
  svgB.type = "button"; svgB.title = "The chart as an SVG file";
  for(const [k, t] of [["bar", "Bar"], ["line", "Line"], ["histogram", "Histogram"], ["scatter", "Scatter"], ["pie", "Pie"]]) kindS.append(Object.assign($("option", "", t), {value: k}));
  const lab = (t, e) => { const l = $("label", "rs-dd-cl"); l.append($("span", "", t), e); return l; };
  // how to use each kind of chart: under the controls, and in the tooltip of its button
  const HINT = {bar: "One bar for each value of X (the groups). Y: the count of rows, or the sum of a number column.",
    line: "X: a number, a date or a time, in its order. Y: the count of rows, or the sum of a number column, for each X.",
    histogram: "X: a number column. It counts the rows in each of 20 equal ranges of X.",
    scatter: "X and Y: two number columns. One point for each row.",
    pie: "One slice for each value of X (the parts). Y: the count of rows, or the sum of a number column. At most 6 slices."};
  // Kind: five icon buttons, the chosen one filled (Kaveh, 2026-11-06: "also design of these parts too"); X and Y: roadstyle's select box
  const ICON = {bar: '<path d="M5 20V11M10 20V5M15 20v-6M20 20V8"/>', line: '<path d="m3 17 5-6 4 3 5-7 4 4"/>', histogram: '<path d="M3 20h18M4 20v-6h4v6M8 20V8h4v12M12 20v-9h4v9M16 20v-4h4v4"/>',
                scatter: '<circle cx="6" cy="16" r="1.6"/><circle cx="10" cy="10" r="1.6"/><circle cx="15" cy="13" r="1.6"/><circle cx="18" cy="6" r="1.6"/><circle cx="8" cy="5" r="1.6"/>',
                pie: '<path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>'};
  const kinds = $("span", "rs-dd-kinds"); kinds.setAttribute("role", "radiogroup"); kinds.setAttribute("aria-label", "The kind of chart");
  for(const o2 of kindS.options){ const b = $("button", "rs-dd-kind"); b.type = "button"; b.dataset.kind = o2.value; b.title = `${o2.textContent}: ${HINT[o2.value]}`; b.setAttribute("aria-label", o2.textContent); b.setAttribute("role", "radio");
    b.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[o2.value]}</svg>`;
    b.onclick = () => { kindS.value = o2.value; change(); }; kinds.append(b); }
  const paintKinds = () => kinds.querySelectorAll("button").forEach((b) => { const on = b.dataset.kind === kindS.value; b.classList.toggle("on", on); b.setAttribute("aria-checked", String(on)); });
  // the chart's title line is in this row, so the chart has the height of the box under it (Kaveh, 2026-11-06: "most of rows spend by other
  // than thing in compare to show the chart"); the hint of a kind is its button's tooltip, not a line
  const titleEl = $("div", "rs-dd-ctitle");
  chartRow.append(kinds, lab("X", xS), lab("Y", yS));
  // no title line: the chart has the whole height, and SVG is in its top right corner (Kaveh: "remove 'rows by km 14 rows'"); the chart's own
  // title line goes to titleEl, which is not on the page (its name stays in the chart's aria-label)
  const chartMain = $("div", "rs-dd-cmain");
  svgB.classList.add("rs-dd-svg"); chartMain.append(chartEl, svgB);
  rsSelectBoxes(chartRow);
  chartBox.append(chartRow, chartMain);
  side.append(list, card, hint); side.classList.add("empty");
  split.append(table.el, chartBox, side);
  el.append(q, err, split);
  const label = o.label || "Data", id = "data";
  rs.dock.add({id, label, el, actions: acts});
  // the help window: one row for each control of the title row, in its order (Kaveh, 2026-11-06: "needs to update")
  if(o.help !== false && rs.help) rs.help.button(acts, {title: "The data dock", intro: "One SQL line over the result. Click the line to edit it. Ctrl+Enter or Run runs it. Click a row to select its road: its card shows beside the table.",
    terms: [["Table | Chart", "The result as a table or as a chart. In the chart, the column at the left sets the kind, X and Y, and SVG saves the chart as a file."],
            ["\u2913 Download (before the line)", "All the rows of the result as a CSV file (at most 1\u00a0000\u00a0000)."],
            ["\u26c1 The tables (after Run)", "The tables of the data, with what each one holds. Click a table to show its rows."],
            ["On | Off", lightT],
            ["Colour ▾", "A layer that colours the roads of the result: one colour for each value of a text column with 2 to 8 values, else one colour. It stays until you remove it."],
            ["Focus ▾", "Keeps the roads of the result: the other roads fade or hide. One focus at a time; None turns it off."]]});

  // the road card, beside the table in place of the popup (Kaveh, 2026-11-06: "that card need to redesign and better style and also font size"): the
  // name; the main facts as small chips (class, length, speed limit, one-way, the networks); the other fields in 12 px with rounded numbers and yes/no;
  // no empty field and no field of roadstyle's drawing (casing_*, fill_level, ...); the id, Copy id and Zoom at its foot
  const DRAWING = /^(__|casing_|fill_level$|head_(start|end)_m$|cap_(start|end)$|is_directed$|has_arrows$|lvl$|geometry$|geom$|edge_ref$)/;
  const CHIPS = new Set(["name", "highway", "length_m", "maxspeed_kmh", "oneway", "driving", "walking", "cycling", ID]);
  const val = (v) => typeof v === "boolean" ? (v ? "yes" : "no") : typeof v === "number" ? (Number.isInteger(v) ? fmt(v) : fmt(+v.toFixed(Math.abs(v) < 100 ? 1 : 0))) : String(v);
  const metres = (m) => m >= 1000 ? `${(m / 1000).toFixed(m >= 10000 ? 0 : 1)} km` : `${Math.round(m)} m`;
  function drawCard(p, roadId){
    const hd = $("div", "rs-dd-rc-hd"), x = $("button", "rs-dd-rc-x", "\u2715");
    x.type = "button"; x.title = "Close the card"; x.setAttribute("aria-label", x.title); x.onclick = () => rs.select(null);
    hd.append($("b", "rs-dd-rc-name", p.name || p.ref || "A road with no name"), x);
    const chips = $("div", "rs-dd-rc-chips"), chip = (t, cls = "") => chips.append($("span", "rs-dd-rc-chip " + cls, t));
    if(p.highway) chip(String(p.highway).replace(/_/g, " "), "strong");
    if(typeof p.length_m === "number") chip(metres(p.length_m));
    if(p.maxspeed_kmh != null) chip(`${p.maxspeed_kmh} km/h`);
    if(p.oneway === true) chip("one-way");
    const nets = [["driving", "cars"], ["walking", "foot"], ["cycling", "bikes"]].filter(([k]) => p[k] === true).map(([, t]) => t);
    if(nets.length) chip(nets.join(" \u00b7 "));
    const rows = $("dl", "rs-dd-rc-rows");
    for(const [k, v] of Object.entries(p)){
      if(CHIPS.has(k) || DRAWING.test(k) || v == null || v === "" || typeof v === "object") continue;
      const dt = $("dt", "", k.replace(/_/g, " ")), dd = $("dd", "", val(v)); if(String(v).length > 28) dd.title = String(v); rows.append(dt, dd);
    }
    const foot = $("div", "rs-dd-rc-foot"), idv = String(p[ID] ?? roadId ?? ""), copy = $("button", "", "Copy id"), zoom = $("button", "", "Zoom");
    copy.type = zoom.type = "button";
    copy.onclick = async () => { try{ await navigator.clipboard.writeText(idv); copy.textContent = "Copied"; setTimeout(() => { copy.textContent = "Copy id"; }, 1200); }catch(e){} };
    zoom.onclick = () => rs.focus([idv]);
    foot.append($("span", "rs-dd-rc-id", `${ID} ${idv}`), copy, zoom);
    card.replaceChildren(hd, chips, ...(rows.childElementCount ? [rows] : []), foot);
  }
  // the facts card of an item that is not a road: a title, a chip, rows of [name, value] and an id with Copy id. An overlay item (a building, a
  // crossing; Kaveh, 2026-11-07: "click on item should show info into sql panel card info") and the page's own card (`data.card`) draw it. `onClose` is
  // what the close button does.
  function drawFacts({title, chip, rows: kv = [], id: idv = null}, onClose){
    const hd = $("div", "rs-dd-rc-hd"), x = $("button", "rs-dd-rc-x", "\u2715");
    x.type = "button"; x.title = "Close the card"; x.setAttribute("aria-label", x.title); x.onclick = onClose;
    hd.append($("b", "rs-dd-rc-name", title == null ? "" : String(title)), x);
    const chips = $("div", "rs-dd-rc-chips"); if(chip) chips.append($("span", "rs-dd-rc-chip strong", String(chip)));
    const rows = $("dl", "rs-dd-rc-rows");
    for(const [k, v] of kv){
      if(v == null || v === "" || typeof v === "object") continue;
      const dt = $("dt", "", String(k).replace(/_/g, " ")), dd = $("dd", "", val(v)); if(String(v).length > 28) dd.title = String(v); rows.append(dt, dd);
    }
    const foot = $("div", "rs-dd-rc-foot"), copy = $("button", "", "Copy id");
    copy.type = "button";
    const idt = idv == null ? "" : String(idv);
    copy.onclick = async () => { try{ await navigator.clipboard.writeText(idt); copy.textContent = "Copied"; setTimeout(() => { copy.textContent = "Copy id"; }, 1200); }catch(e){} };
    if(idt) foot.append($("span", "rs-dd-rc-id", `id ${idt}`), copy);
    card.replaceChildren(hd, ...(chip ? [chips] : []), ...(rows.childElementCount ? [rows] : []), ...(foot.childElementCount ? [foot] : []));
  }
  // an overlay item: the overlay's name, the item's name when it has one, its fields (the overlay's popup fields when it has them), and its id. The
  // close button deselects it.
  function drawItem(d){
    const p = d.properties || {};
    drawFacts({title: p.name || d.overlay, chip: d.overlay, id: d.id,
      rows: (d.fields && d.fields.length ? d.fields : Object.keys(p)).filter((k) => k !== "name" && !DRAWING.test(k)).map((k) => [k, p[k]])}, () => rs.select(null));
  }
  // the page's own card (`data.card({title, chip, rows, id})`, Kaveh, 2026-11-07: "each selecting from table must show that item on map also shows its info
  // in card info in sql panel"): for a row of a result that is not a road (a node, a building, a wall), which the page draws on the map itself. The close
  // button, a new selection, a new result and `data.card(null)` close it; the event `cardclose` tells the page (it removes its own selection on the map).
  let hostCard = false;
  const closeHostCard = (tell = true) => {
    if(!hostCard) return;
    hostCard = false; card.hidden = true; table.clear(); paintSide();
    if(tell) emit("cardclose", {});
  };
  const showCard = () => { list.hidden = true; tablesB.classList.remove("on"); tablesB.setAttribute("aria-expanded", "false"); card.hidden = false; paintSide(); };
  const paintSide = () => { const none = list.hidden && card.hidden; hint.hidden = !none; side.classList.toggle("empty", none); };
  document.addEventListener("rs:select", (e) => { if(o.card === false) return;
    closeHostCard();
    if(e.detail.overlay) drawItem(e.detail); else drawCard(e.detail.properties || {}, e.detail.id);
    showCard(); });
  document.addEventListener("rs:deselect", () => { card.hidden = true; paintSide(); closeHostCard(); });

  // ---- the SQL line: one line; a click opens it as a text box, Escape folds it ----
  let sql = o.sql || "", res = null, ctl = null, ta = null;
  // the open box folds back to one line on Escape and on a click outside it (Kaveh, 2026-11-06: an open box by an accidental click had "no way except
  // click on run"); the text stays, and Run runs it. A hint under the open box says so.
  let edit = null;
  const fold = () => { if(ta){ sql = ta.value; edit.replaceWith(line); ta = edit = null; } line.textContent = sql.replace(/\s+/g, " ") || "Write SQL here"; line.classList.toggle("empty", !sql); };
  const size = () => { ta.rows = Math.min(10, Math.max(3, ta.value.split("\n").length + 1)); };
  line.onclick = () => {
    edit = $("div", "rs-dd-edit"); ta = $("textarea", "rs-dd-ta"); ta.value = sql; ta.spellcheck = false; ta.setAttribute("aria-label", "SQL"); size();
    edit.append(ta, $("span", "rs-dd-edit-hint", "Ctrl+Enter runs \u00b7 Esc or a click outside closes"));
    line.replaceWith(edit); ta.focus();
    ta.onkeydown = (e) => { if(e.key === "Enter" && (e.ctrlKey || e.metaKey)){ e.preventDefault(); runSql().catch(() => {}); } else if(e.key === "Escape") fold(); };
    ta.oninput = size;
    ta.onblur = () => setTimeout(() => { if(ta && document.activeElement !== ta) fold(); }, 0);
  };
  fold();

  // ---- a run: the guard, the row limit (one row more), the true count when there are more ----
  async function query(text, limit, signal){ if(!loaded) await ready; const g = guardOf(text, limit); return readableResult(await o.query(g, {signal})); }
  const guardOf = (text, limit) => { if(o.guard === false) return limit == null ? inner(text) : `SELECT * FROM (${inner(text)}) AS rs_q LIMIT ${limit + 1}`;
    const g = guardSql(text, limit); if(!g.ok) throw new Error(g.reason); return g.sql; };
  const readableResult = (r) => ({columns: r.columns, rows: readable(r.columns, r.rows)});
  async function runSql(text, {source = "person"} = {}){
    if(text != null){ sql = text; if(ta) ta.value = text; }
    if(ta) sql = ta.value;
    if(ctl) ctl.abort();
    const me = ctl = new AbortController(), t0 = performance.now();
    err.textContent = ""; run.textContent = "Stop";
    try{
      const g = o.guard === false && source === "person" ? null : guardSql(sql, LIMIT);
      if(g && !g.ok) throw new Error(g.reason);
      if(!loaded){ rs.dock.note(id, "Loading the data…"); await ready; }
      const r = readableResult(await o.query(g ? g.sql : `SELECT * FROM (${inner(sql)}) AS rs_q LIMIT ${LIMIT + 1}`, {signal: me.signal}));
      if(me.signal.aborted) throw new Error("Stopped.");
      const out = {sql, columns: r.columns, rows: r.rows.slice(0, LIMIT), more: r.rows.length > LIMIT, ms: Math.round(performance.now() - t0), source};
      if(out.more) out.total = await countOf(sql).catch(() => null);
      fold(); show(out, true);
      emit("run", out);
      return out;
    }catch(e){
      const message = me.signal.aborted ? "Stopped." : sentence(e.message);
      err.textContent = message; if(source === "person" && !ta) line.click();
      emit("error", {sql, message, source});
      throw e;
    }finally{ if(ctl === me){ ctl = null; run.textContent = "Run"; } }
  }
  async function countOf(text){ const r = await o.query(`SELECT count(*) AS n FROM (${guardOf(text, null)}) AS rs_c`, {}); return Number(r.rows[0][0]); }
  // all the rows of a result, not only the ones in the table: for the CSV, the light and the map layers
  async function allRows(r, limit){ if(!r.more) return r === res ? table.rows() : r.rows; return (await query(sorted(r), limit)).rows.slice(0, limit); }   // (the table's order: a sort)
  const sorted = (r) => r.sort ? `SELECT * FROM (${inner(r.sql)}) AS rs_s ORDER BY ${quoteId(r.sort.col)} ${r.sort.dir === "desc" ? "DESC" : "ASC"} NULLS LAST` : r.sql;
  async function sortAll(col, dir){ if(!res || !res.more) return null; res.sort = col ? {col, dir} : null; const r = await query(sorted(res), LIMIT); res.rows = r.rows.slice(0, LIMIT); return {rows: res.rows}; }
  run.onclick = () => { if(ctl){ ctl.abort(); return; } runSql().catch(() => {}); };

  // ---- show a result: the table, the note, the light ----
  function show(r, ran){
    closeHostCard();                // a new result: the page's card of a row of the old one goes, and the page removes its selection
    res = {...r, columns: r.columns, rows: r.rows, more: !!r.more};
    if(!ran){ sql = r.sql || sql; fold(); }
    table.set({columns: res.columns, rows: res.rows, more: res.more});
    const n = res.more ? (res.total ? `${fmt(res.rows.length)} of ${fmt(res.total)} rows` : `${fmt(res.rows.length)} rows (there are more)`) : `${fmt(res.rows.length)} row${res.rows.length === 1 ? "" : "s"}`;
    rs.dock.note(id, `${n} · ${res.columns.length} column${res.columns.length === 1 ? "" : "s"}${res.ms != null ? ` · ${res.ms} ms` : ""}`);
    paintButtons(); light();
    if(res.chart === undefined){ const m = new Set(measures(res));   // the first chart: from the columns, with the ids as text (never a measure)
      res.chart = rs.chart.guess(res.columns.filter((col) => col.name !== ID).map((col) => rs.chart.isNumber(col.type) && !m.has(col.name) ? {...col, type: "VARCHAR"} : col), ID);
      if(res.chart && ["bar", "line", "pie"].includes(res.chart.kind) && !res.chart.y) res.chart.y = COUNT;
      // a bar: X is the text column with the fewest values (2 or more), never an id (edge_ref) - for SELECT * of the roads: the roads by highway;
      // when each value is once in the rows (a result of GROUP BY), Y is its first measure, else the count of rows
      if(res.chart && res.chart.kind === "bar"){
        // the order: 3 to 40 values (a yes/no column last), less than half null (tunnel is mostly null), then the most values (highway)
        const t = res.columns.map((col, i) => [col, new Set(res.rows.map((x) => String(x[i]))).size, res.rows.filter((x) => x[i] == null).length / Math.max(1, res.rows.length)])
          .filter(([col, n]) => col.name !== ID && !ID_NAME.test(col.name) && !NOT_X.test(String(col.type)) && !rs.chart.isNumber(col.type) && !rs.chart.isTime(col.type) && n >= 2 && n <= 40)
          .sort((a, b) => (a[1] < 3) - (b[1] < 3) || (a[2] > 0.5) - (b[2] > 0.5) || b[1] - a[1])[0];
        if(t){ const once = t[1] === res.rows.length && !res.more; res.chart = {kind: "bar", x: t[0].name, y: once && m.size ? [...m][0] : COUNT}; } }
      // no measure: the rows for each value of the text column with the fewest values (2 or more), for example highway
      if(!res.chart || (res.chart.kind === "histogram" && !m.size)){ const t = res.columns.map((col, i) => [col, new Set(res.rows.map((x) => String(x[i]))).size])
          .filter(([col, n]) => col.name !== ID && !rs.chart.isNumber(col.type) && n >= 2).sort((a, b) => a[1] - b[1])[0];
        res.chart = t ? {kind: "bar", x: t[0].name, y: COUNT} : null; } }
    if(view === "chart") drawChart();
    return res;
  }
  // the roads of a result: its id column; else a key column (osm_id, name) through the host's roadsBy; else none
  const keyOf = (r) => r.columns.some((c) => c.name === ID) ? ID : KEYS.find((k) => r.columns.some((c) => c.name === k) && o.roadsBy) || null;
  async function roadsOf(r){
    if(r.__ids) return r.__ids;
    const k = keyOf(r); if(!k) return [];
    if(k === ID){ const i = r.columns.findIndex((c) => c.name === ID); return (r.__ids = (await allRows(r, MAP_LIMIT)).map((x) => String(x[i]))); }
    const q = await query(o.roadsBy(inner(r.sql), k), MAP_LIMIT), i = q.columns.findIndex((c) => c.name === ID);
    return (r.__ids = q.rows.map((x) => String(x[i < 0 ? 0 : i])));
  }
  // the light: always the dock's table, one set; a table that a colour or a focus already shows is not lit (the light would hide its colours)
  let lightSeq = 0;
  async function light(){
    const me = ++lightSeq, r = res;
    const ids = lightOn && rs.dock.isOpen() && r && !r.byLayer && keyOf(r) ? await roadsOf(r).catch(() => []) : [];
    if(me === lightSeq) rs.highlight(onMap(ids), LIGHT);
  }
  document.addEventListener("rs:dockchange", (e) => { if(e.detail.id === id && !!e.detail.open !== lightWasOpen){ lightWasOpen = !!e.detail.open; light(); }
    tellLight();
    // the card is the one place for the facts while the dock shows it: no popup for a road or an item, from the table, Ask or the map
    if(o.card !== false && rs.holdPopup) rs.holdPopup("data-dock", !!e.detail.open && e.detail.id === id); });
  let lightWasOpen = false;
  async function rowClick(r, cols){
    const i = cols.findIndex((c) => c.name === ID);
    if(i >= 0){ const idv = String(r[i]); rs.select(idv); rs.focus([idv]); return; }
    const k = res && keyOf(res); if(!k) return;
    const v = r[cols.findIndex((c) => c.name === k)]; if(v == null) return;
    const q = await query(o.roadsBy(`SELECT ${quoteId(k)} FROM (SELECT ${lit(v)} AS ${quoteId(k)}) AS rs_v`, k), MAP_LIMIT), j = q.columns.findIndex((c) => c.name === ID);
    const ids = onMap(q.rows.map((x) => String(x[j < 0 ? 0 : j])));
    if(ids.length){ rs.select(ids[0]); rs.focus(ids); }
  }
  // only the roads that the map draws: a road that is not on the map changes nothing
  let mapIds = null;
  const onMap = (ids) => { if(!mapIds) mapIds = new Set((rs.query({}) || []).map(String)); return ids.filter((i) => mapIds.has(String(i))); };
  document.addEventListener("rs:tableready", () => { mapIds = null; });

  // ---- the chart view: the same result as the table; Kind, X and Y choose the chart; a click on a mark does what a click on its row does ----
  let view = "table", chartObj = null;
  function setView(v){
    view = v; tableB.classList.toggle("on", v === "table"); chartB.classList.toggle("on", v === "chart");
    table.el.hidden = v !== "table"; chartBox.hidden = v !== "chart";
    return v === "chart" ? drawChart() : Promise.resolve();
  }
  tableB.onclick = () => setView("table");
  chartB.onclick = () => setView("chart");
  const fill = (sel, names, v, any) => { sel.replaceChildren(...(any ? [Object.assign($("option", "", "(none)"), {value: ""})] : []), ...names.map((n) => Object.assign($("option", "", n), {value: n}))); sel.value = v ?? ""; };
  // Y "count of rows": the rows for each value of X. A bar, a line or a pie whose X has a value more than once (or a result of more rows than the
  // table) is drawn from all the rows, one mark for each value of X: the count of rows, or the sum of Y (Kaveh, 2026-11-06: a pie of lanes had one
  // slice for each road). The road ids are never a choice of Y or X: a chart of ids says nothing.
  const COUNT = "(count of rows)";
  // the columns that fit each kind, and one line that says how to use it
  function fits(kind, r){
    const m = measures(r), plain = r.columns.filter((col) => col.name !== ID && !ID_NAME.test(col.name) && !NOT_X.test(String(col.type))).map((col) => col.name);
    const times = r.columns.filter((col) => rs.chart.isTime(col.type)).map((col) => col.name);
    return kind === "line" ? {xs: [...times, ...m], ys: [COUNT, ...m]} : kind === "histogram" ? {xs: m, ys: []}
      : kind === "scatter" ? {xs: m, ys: m} : {xs: plain, ys: [COUNT, ...m]};
  }
  // a number column that is a measure, not an id: not the id column, not a name of an id (osm_id, source, target, ..._ref), and no value of 10^12 or more
  const ID_NAME = /(^|_)(id|ref)$|^(source|target|from_node|to_node)$/i;
  const NOT_X = /GEOMETRY|BLOB|BYTEA|BINARY|^MAP|^STRUCT|^UNION|\[\]|^LIST|JSON/i;      // no chart of geometries, bytes, maps, structs or lists
  const measures = (r) => r.columns.filter((col, i) => rs.chart.isNumber(col.type) && col.name !== ID && !ID_NAME.test(col.name) &&
    !r.rows.slice(0, 200).some((x) => { const v = x[i]; return v != null && Math.abs(Number(v)) >= 1e12; })).map((col) => col.name);
  let chartSeq = 0;
  async function drawChart(){
    const r = res, me = ++chartSeq; if(!r) return;
    const sp = r.chart || {kind: "bar"}, f = fits(sp.kind, r);
    const ys = [].concat(sp.y || []), grouped = ["bar", "line", "pie"].includes(sp.kind);
    kindS.value = sp.kind; paintKinds();
    fill(xS, f.xs, sp.x); fill(yS, f.ys, ys[0], sp.kind === "histogram"); yS.disabled = sp.kind === "histogram";
    if(!f.xs.length || (sp.kind === "scatter" && f.ys.length < 1)){
      chartEl.replaceChildren(Object.assign($("p", "rs-chart-none"), {textContent: `This result has no column for a ${sp.kind} chart. ${HINT[sp.kind]}`})); return; }
    let spec = {...sp, title: sp.title, head: titleEl, columns: r.columns, rows: table.rows(), values: null, onPick: (i) => rowClick(table.rows()[i], r.columns)};   // (title: also when none)
    const xi = r.columns.findIndex((c) => c.name === sp.x);
    const repeats = xi >= 0 && new Set(table.rows().map((x) => String(x[xi]))).size < table.rows().length;
    // a bar or a pie whose X is a number with more than 40 values (a length): the rows in ranges of X, about 6 for a pie and 12 for a bar, over all
    // the rows (Kaveh, 2026-11-06: a pie of the lengths had one slice of 0 % for each road)
    const many = xi >= 0 && ["bar", "pie"].includes(sp.kind) && measures(r).includes(sp.x) && new Set(table.rows().map((x) => x[xi])).size > 40;
    if(many){
      const all = await allRows(r, CSV_LIMIT); if(me !== chartSeq) return;
      const yi = ys[0] && ys[0] !== COUNT ? r.columns.findIndex((col) => col.name === ys[0]) : -1, vals = all.map((x) => [Number(x[xi]), yi < 0 ? 1 : Number(x[yi]) || 0]).filter(([v]) => isFinite(v));
      const rg = rs.chart.ranges(vals.map(([v]) => v), sp.kind === "pie" ? 6 : 12), sums = new Array(rg.n).fill(0);
      for(const [v, w] of vals) sums[rg.of(v)] += w;
      const yName = yi < 0 ? "rows" : `sum of ${ys[0]}`, rows = sums.map((s, k) => [rg.label(k), s]).filter(([, s]) => s > 0);
            spec = {...spec, x: sp.x, y: yName, count: `${sp.x} in ranges`, columns: [{name: sp.x, type: "VARCHAR"}, {name: yName, type: "DOUBLE"}], rows, onPick: null};
    }
    else if(grouped && xi >= 0 && (ys[0] === COUNT || repeats || r.more)){
      const time = rs.chart.isTime(r.columns[xi].type) || rs.chart.isNumber(r.columns[xi].type), yName = ys[0] === COUNT || !ys.length ? "rows" : `sum of ${ys[0]}`;
      const agg = ys[0] === COUNT || !ys.length ? "count(*)" : `sum(${quoteId(ys[0])})`;
      const g = await query(`SELECT ${quoteId(sp.x)}, ${agg} AS ${quoteId(yName)} FROM (${inner(r.sql)}) AS rs_a GROUP BY 1 ORDER BY ${sp.kind === "line" || (sp.kind === "bar" && time) ? 1 : 2} ${sp.kind === "line" || time ? "ASC" : "DESC"} LIMIT 500`, null).catch((e) => ({error: e}));
      if(me !== chartSeq) return;
      if(g.error){ chartEl.replaceChildren(Object.assign($("p", "rs-chart-none"), {textContent: sentence(g.error.message)})); return; }
      const key = r.columns[xi].name;
      spec = {...spec, y: yName, columns: g.columns, rows: g.rows, onPick: (i) => rowClick([g.rows[i][0]], [{name: key, type: r.columns[xi].type}])};
    }
    if(sp.kind === "histogram" && r.more){ const v = await allRows(r, CSV_LIMIT); if(me !== chartSeq) return; spec.values = v.map((x) => x[xi]); }
    if(!chartObj) chartObj = rs.chart(chartEl, spec); else chartObj.set(spec);
  }
  // a new kind, X or Y: X and Y move to a column that fits the kind (Kaveh, 2026-11-06: a histogram of the road ids)
  const change = () => { if(!res) return; const k = kindS.value, old = res.chart || {}, f = fits(k, res);
    const pick = (want, list, alt) => list.includes(want) ? want : list.includes(alt) ? alt : list[0];
    const time = res.columns.find((col) => rs.chart.isTime(col.type));
    const x = pick(xS.value, f.xs, k === "line" && time ? time.name : old.x);
    let y = k === "histogram" ? undefined : pick(yS.value, f.ys, [].concat(old.y || [])[0]);
    if(["bar", "line", "pie"].includes(k) && y === x) y = COUNT;                                     // the sum of x for each x says nothing: the rows
    if(k === "scatter" && y === x) y = f.ys.find((n) => n !== x) || y;
    res.chart = {kind: k, x, y}; drawChart(); };      // the person's own chart: its own title, not the one of the model
  kindS.onchange = xS.onchange = yS.onchange = change;
  svgB.onclick = () => { const s = chartObj && chartObj.svg(); if(!s) return;
    const copy = s.cloneNode(true), css = getComputedStyle(document.documentElement);
    copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    copy.querySelectorAll("*").forEach((e) => { for(const p of ["fill", "stroke"]){ const v = e.style[p]; if(v && v.startsWith("var(")) e.style[p] = css.getPropertyValue(v.slice(4, -1).trim()).trim(); } });
    const a = $("a"); a.href = URL.createObjectURL(new Blob([copy.outerHTML], {type: "image/svg+xml"})); a.download = "chart.svg"; a.click(); };

  // ---- CSV: all the rows (at most 1 000 000), in the order of the table ----
  async function csv(){
    const cell = (v) => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const rows = res ? await allRows(res, CSV_LIMIT) : [];
    return res ? [res.columns.map((c) => cell(c.name)).join(","), ...rows.map((r) => r.map(cell).join(","))].join("\n") : "";
  }
  csvB.onclick = async () => { const a = $("a"); a.href = URL.createObjectURL(new Blob([await csv()], {type: "text/csv"})); a.download = "data.csv"; a.click(); };

  // ---- Tables: the schema's tables in groups; a click puts the name into the line ----
  // the list of the tables (Kaveh, 2026-11-06: "tables part need to better design and style"): it takes the place of the table while it is open; a search
  // field; one group for each schema with its number of tables (the page's own "extra" first); each table a card with its name, its rows and one line of
  // what it holds. A click shows the rows of the table and closes the list; the line then has its SQL, to change.
  const fmtRows = (n) => n == null ? "" : Number(n) >= 1e6 ? (Number(n) / 1e6).toFixed(1) + "M rows" : Number(n) >= 1e4 ? Math.round(Number(n) / 1e3) + "K rows" : fmt(n) + (Number(n) === 1 ? " row" : " rows");
  async function drawTables(){
    const s = await o.schema(), groups = new Map();                  // each time: a table of the page can come later
    for(const t of s.tables || []){ const g = t.name.includes(".") ? t.name.split(".")[0] : ""; if(!groups.has(g)) groups.set(g, []); groups.get(g).push(t); }
    const find = $("input", "rs-dd-tfind"), close = $("button", "rs-dd-tclose", "\u2715"), head = $("div", "rs-dd-thead"), body = $("div", "rs-dd-tbody");
    find.type = "search"; find.placeholder = "Find a table"; find.setAttribute("aria-label", "Find a table"); close.type = "button"; close.title = "Close the list"; close.setAttribute("aria-label", close.title);
    head.append(find, $("span", "rs-dd-tcount", `${(s.tables || []).length} tables`), close);
    const order = [...groups.keys()].sort((a, b) => (b === "extra") - (a === "extra") || (b === "main") - (a === "main") || a.localeCompare(b));
    const cards = [];
    for(const g of order){
      const sec = $("section", "rs-dd-tgroup"), h = $("div", "rs-dd-tg-h"), grid = $("div", "rs-dd-tgrid");
      h.append($("b", "", g || "tables"), $("span", "", `${groups.get(g).length} table${groups.get(g).length === 1 ? "" : "s"}`));
      if(g === "extra") h.append($("span", "rs-dd-tg-own", "the page's own data"));
      for(const t of groups.get(g)){
        const b = $("button", "rs-dd-tcard"), name = t.name.split(".").map((p) => /^[A-Za-z_]\w*$/.test(p) ? p : quoteId(p)).join(".");
        b.type = "button"; b.title = `${t.name}${t.about ? "\n" + t.about : ""}\nClick to see its rows.`;
        const top = $("span", "rs-dd-tc-top"); top.append($("span", "rs-dd-tc-name", t.name.split(".").pop()), $("span", "rs-dd-tc-rows", fmtRows(t.rows)));
        b.append(top); if(t.about) b.append($("span", "rs-dd-tc-about", t.about));        // no description: no empty line
        b.onclick = () => { setList(false); runSql(`SELECT * FROM ${name}`).catch(() => {}); };
        b.dataset.find = (t.name + " " + (t.about || "")).toLowerCase(); grid.append(b); cards.push([b, sec]);
      }
      sec.append(h, grid); body.append(sec);
    }
    find.oninput = () => { const q = find.value.trim().toLowerCase(); for(const [b] of cards) b.hidden = !!q && !b.dataset.find.includes(q);
      body.querySelectorAll(".rs-dd-tgroup").forEach((sec) => { sec.hidden = ![...sec.querySelectorAll(".rs-dd-tcard")].some((b) => !b.hidden); }); };
    find.onkeydown = (e) => { if(e.key === "Escape") setList(false); if(e.key === "Enter"){ const first = cards.find(([b]) => !b.hidden); if(first) first[0].click(); } };
    close.onclick = () => setList(false);
    list.replaceChildren(head, body);
    setTimeout(() => find.focus(), 0);
  }
  async function setList(on){
    if(on) await drawTables();
    list.hidden = !on; if(on) card.hidden = true; tablesB.classList.toggle("on", on); tablesB.setAttribute("aria-expanded", String(on)); paintSide();
  }
  tablesB.onclick = () => setList(list.hidden);

  // ---- the layers of the map: Colour (several on) and Focus (one on; fade or hide). One layer for each kind and set of roads. ----
  const layers = []; let legendIds = [], seq = 0;
  const layerKey = (l) => l.kind + "|" + (l.kind === "colour" ? l.groups.map((g) => g.label + "=" + idsKey(g.ids)).join("|") : idsKey(l.ids));
  function addLayer(l){
    l.key = layerKey(l);
    const old = layers.find((x) => x.key === l.key);
    if(old){ layers.splice(layers.indexOf(old), 1); if(l.mode) old.mode = l.mode; l = old; } else l.n = ++seq;
    l.on = true;
    if(!lightOn){ setLight(true); light(); tellLight(); }      // a new layer (a button, Ask) shows: the map switch turns on
    if(l.kind === "focus") layers.forEach((x) => { if(x.kind === "focus" && x !== l) x.on = false; });
    layers.push(l); paint(); return l;
  }
  function paint(){
    const colours = lightOn ? layers.filter((l) => l.kind === "colour" && l.on).reverse() : [];      // the map switch off: no layer on the map        // the newest first: where two meet, the newest wins
    rs.color(colours.flatMap((l) => l.groups.map((g) => ({color: g.color, ids: g.ids}))));
    legendIds.forEach((x) => rs.legend.remove(x));
    legendIds = colours.flatMap((l) => l.groups).map((g, k) => { const x = "rs-dd-" + k; rs.legend.add({id: x, color: g.color, label: g.label, shape: "line"}); return x; });
    const f = lightOn && layers.find((l) => l.kind === "focus" && l.on);
    rs.setFilter({ids: f && f.mode === "hide" ? f.ids : null});
    if(rs.fade) rs.fade(f && f.mode === "fade" ? f.ids : null);
    paintButtons(); drawMenu();
    emit("layers", {layers: layers.map(({kind, label, sql, on, mode, n}) => ({kind, label, sql, on, mode, n}))});
  }
  const count = (b, n) => { const c = b.querySelector(".rs-dd-count"); c.hidden = !n; c.textContent = n || ""; };
  function paintButtons(){ count(colourB, layers.filter((l) => l.kind === "colour" && l.on).length); count(focusB, layers.some((l) => l.kind === "focus" && l.on) ? 1 : 0); }
  // the dock's own actions on its table (Ask's tools call the same: colour and focus)
  async function colourThis(){
    const r = res; if(!r || !keyOf(r)) return;
    const idx = r.columns.findIndex((c) => c.name === ID), rows = idx >= 0 ? await allRows(r, MAP_LIMIT) : [];
    const col = idx < 0 ? -1 : r.columns.findIndex((c, i) => i !== idx && !KEYS.includes(c.name) && /utf8|bool|varchar|text|string/i.test(String(c.type)) && ((n) => n >= 2 && n <= 8)(new Set(rows.map((x) => x[i])).size));
    const groups = col >= 0 ? [...new Set(rows.map((x) => x[col]))].map((v, k) => ({label: String(v), color: PALETTE[k % PALETTE.length], ids: onMap(rows.filter((x) => x[col] === v).map((x) => String(x[idx])))}))
      : [{label: shortOf(r.sql), color: PALETTE[layers.filter((l) => l.kind === "colour").length % PALETTE.length], ids: onMap(await roadsOf(r))}];
    colour(groups, {sql: r.sql}); r.byLayer = true; light();
  }
  async function focusThis(mode){ const r = res; if(!r || !keyOf(r)) return; const ids = onMap(await roadsOf(r)); focus(ids, {sql: r.sql, mode}); r.byLayer = true; light(); }
  function colour(groups, {sql: s = "", label} = {}){ return addLayer({kind: "colour", groups, sql: s, label: label || groups.map((g) => g.label).join(", ")}); }
  function focus(ids, {sql: s = "", mode = "fade", label} = {}){ const l = addLayer({kind: "focus", ids, sql: s, mode, label: label || shortOf(s)}); rs.focus(ids); return l; }

  // ---- the lists of Colour and Focus: a box under the button, in the look of the toolbox's boxes ----
  const menu = $("div", "rs-dd-menu"); menu.hidden = true; menu.setAttribute("role", "menu"); document.body.append(menu);
  let menuOf = null;
  function openMenu(kind, btn){
    if(menuOf === kind && !menu.hidden){ closeMenu(); return; }
    menuOf = kind; drawMenu(); menu.hidden = false; btn.setAttribute("aria-expanded", "true");
    const b = btn.getBoundingClientRect();
    Object.assign(menu.style, {top: Math.round(b.bottom + 4) + "px", right: Math.max(8, Math.round(innerWidth - b.right)) + "px"});
  }
  function closeMenu(){ menu.hidden = true; menuOf = null; colourB.setAttribute("aria-expanded", "false"); focusB.setAttribute("aria-expanded", "false"); }
  document.addEventListener("pointerdown", (e) => { if(!menu.hidden && !menu.contains(e.target) && !colourB.contains(e.target) && !focusB.contains(e.target)) closeMenu(); }, true);
  document.addEventListener("keydown", (e) => { if(e.key === "Escape" && !menu.hidden) closeMenu(); });
  colourB.onclick = () => openMenu("colour", colourB);
  focusB.onclick = () => openMenu("focus", focusB);
  function drawMenu(){
    if(!menuOf) return;
    const kind = menuOf, mine = layers.filter((l) => l.kind === kind).slice().reverse(), rows = [];
    const add = $("button", "rs-dd-menu-add", kind === "colour" ? "+ Colour the roads of this table" : "+ Focus on the roads of this table");
    add.type = "button"; add.disabled = !res || !keyOf(res); add.onclick = () => (kind === "colour" ? colourThis() : focusThis());
    rows.push(add);
    if(kind === "focus"){
      const none = $("label", "rs-dd-menu-row"), rb = $("input"); rb.type = "radio"; rb.name = "rs-dd-focus"; rb.checked = !mine.some((l) => l.on);
      rb.onchange = () => { layers.forEach((l) => { if(l.kind === "focus") l.on = false; }); paint(); };
      none.append(rb, $("span", "", "None: all the roads")); rows.push(none);
    }
    for(const l of mine){
      const row = $("label", "rs-dd-menu-row" + (l.on ? "" : " off")), box = $("input"); row.title = l.sql || l.label;
      box.type = kind === "colour" ? "checkbox" : "radio"; box.name = "rs-dd-focus"; box.checked = l.on;
      box.onchange = () => { if(kind === "focus") layers.forEach((x) => { if(x.kind === "focus") x.on = false; }); l.on = box.checked; paint(); };
      row.append(box);
      if(kind === "colour") row.append(...l.groups.slice(0, 6).map((g) => { const i = $("i", "rs-dd-sw"); i.style.background = g.color; i.title = g.label; return i; }));
      row.append($("span", "rs-dd-menu-t", l.label), $("small", "", fmt(kind === "colour" ? l.groups.reduce((n, g) => n + g.ids.length, 0) : l.ids.length)));
      if(kind === "focus"){
        const seg = $("span", "rs-dd-seg");
        for(const m of ["fade", "hide"]){ const b = $("button", m === l.mode ? "on" : "", m === "fade" ? "Fade" : "Hide"); b.type = "button";
          b.onclick = (e) => { e.preventDefault(); l.mode = m; l.on = true; layers.forEach((x) => { if(x.kind === "focus" && x !== l) x.on = false; }); paint(); }; seg.append(b); }
        row.append(seg);
      }
      const x = $("button", "rs-dd-menu-x", "✕"); x.type = "button"; x.title = "Remove this layer"; x.setAttribute("aria-label", x.title);
      x.onclick = (e) => { e.preventDefault(); layers.splice(layers.indexOf(l), 1); paint(); };
      row.append(x); rows.push(row);
    }
    if(!mine.length) rows.push($("p", "rs-dd-menu-empty", kind === "colour" ? "No colour layer yet." : "No focus yet."));
    menu.replaceChildren(...rows);
  }

  return Object.assign(events, {
    run: runSql, show: (r) => show(r, false), sql: () => (ta ? ta.value : sql), result: () => res, csv, stop: () => ctl && ctl.abort(),
    open: () => rs.dock.open(id), close: () => rs.dock.close(), ready: () => ready, schema: () => (loaded ? o.schema() : ready.then(() => o.schema())),
    // for Ask's tools: the roads (on the map) that SQL selects by its id column, and the same layers as the buttons
    async roads(text){ const r = await query(text, MAP_LIMIT), i = r.columns.findIndex((c) => c.name === ID);
      if(i < 0) throw new Error(`The query must select the column ${ID}.`);
      if(r.rows.length > MAP_LIMIT) throw new Error(`The query selects more than ${fmt(MAP_LIMIT)} roads. Make it narrower.`);
      const all = r.rows.map((x) => String(x[i])), ids = onMap(all); ids.missing = all.length - ids.length; return ids; },
    // for Ask's answer: the id column, the column that finds the roads of a result (or null), and its roads on the map (for the camera)
    idColumn: ID, keyOf, roadsOf: async (r) => keyOf(r) ? onMap(await roadsOf(r)) : [],
    query: (text, limit = LIMIT) => query(text, limit),
    // the chart of the result now: {kind, x, y, title}; it opens the chart view (Ask's draw_chart). A spec that does not fit gives an error.
    chart(spec){ if(!res) throw new Error("There is no result to draw.");
      // a bar, a line or a pie with no y (or "(count of rows)"): the count of rows for each value of x
      if(["bar", "line", "pie"].includes(spec.kind) && (!spec.y || spec.y === COUNT)){
        if(!res.columns.some((col) => col.name === spec.x)) throw new Error(`The column "${spec.x}" is not in the result.`);
        res.chart = {kind: spec.kind, x: spec.x, y: COUNT, title: spec.title}; return setView("chart").then(() => res.chart); }
      const s = {...spec, columns: res.columns, rows: res.rows};
      const why = rs.chart.check ? rs.chart.check(s) : null; if(why) throw new Error(why); res.chart = {kind: spec.kind, x: spec.x, y: spec.y, title: spec.title}; return setView("chart").then(() => res.chart); },
    // the chart that the dock drew last: its kind, columns and rows (the rows for each value of x when it grouped them), for a copy of it
    drawnChart: () => (chartObj ? chartObj.spec() : null),
    view: (v) => (v ? setView(v) : view),
    colour, focus, layers: () => layers.slice(), remove: (l) => { const i = layers.indexOf(l); if(i >= 0){ layers.splice(i, 1); paint(); } },
    lightOff(r = res){ if(r){ r.byLayer = true; light(); } },
    // the page's own card for a row that is not a road: {title, chip, rows: [[name, value], ...], id}; null closes it. The event `cardclose` comes when the
    // person closes it (the close button), or a new selection or a new result takes its place
    card(spec){
      if(!spec){ if(hostCard) closeHostCard(false); else{ card.hidden = true; paintSide(); } return; }
      if(typeof spec !== "object" || !Array.isArray(spec.rows)) throw new Error("data.card: give {title, chip, rows: [[name, value], ...], id}");
      drawFacts(spec, () => closeHostCard()); hostCard = true; showCard();
    },
    // turns the map switch on (Ask, before a colour, a focus or a move: off, the result would not show); true when it was off
    showOnMap(){ if(lightOn) return false; setLight(true); light(); paint(); tellLight(); return true; },
    light: shown,                // true while the table is shown on the map: the map switch is on and the dock is open (the event `light` tells a change)
  });
}

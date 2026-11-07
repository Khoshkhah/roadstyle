// The bottom dock (docs/design/ask_and_data_dock.md, "1. The bottom dock"; docs/guides/dashboard-layout.md): a wide area under the map, a layout part as
// the panel and the windows are. It has no content of its own: a page or a part adds one or more (`rs.dock.add`), and a dock with no content is not on the
// page. On a desktop it has the left and the right edge of the map, the map and the other parts end above it (`--rs-dock-h`), and the grip on its top edge
// sets its height. On a phone (rs-phone) it is a bottom sheet, one sheet at a time (windows.js), and a closed dock is a small round button.
//
//   rs.dock.add({id, label, el, note, actions, closable}) | remove(id) | open(id?) | close() | isOpen() | show(id) | note(id, text) | height(px?) | list()
//   rs.dock.table({columns, rows, idColumn, more, onSort}) -> {el, set({columns, rows, more}), rows()}
//   event rs:dockchange {open, id, height}
import {map} from "./core.js";
// (one closure: the dashboard's modules join into one script, so the names stay inside)
export const rsDock = (() => {
  const root = document.documentElement, phone = () => root.classList.contains("rs-phone");

  const KEY = () => "rs-dock:" + location.pathname;
  const MIN = 120, SHUT = 32;
  const ARROW = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
  const el = (tag, cls, text) => { const e = document.createElement(tag); if(cls) e.className = cls; if(text != null) e.textContent = text; return e; };

  const items = new Map();                 // id -> {id, label, el, note, actions, closable}
  let current = null, dom = null;
  const st = (() => { try{ return JSON.parse(localStorage.getItem(KEY())) || {}; }catch(e){ return {}; } })();   // {h, open, sheet}
  const save = () => { try{ localStorage.setItem(KEY(), JSON.stringify(st)); }catch(e){} };
  const H = () => Math.max(MIN, Math.min(st.h || 300, innerHeight * 0.7));

  // the low edge for the boxes of the toolbox and the floating windows: the top of the dock on a desktop, else the bottom of the window
  const dockTop = () => !dom || phone() || !root.classList.contains("rs-dock-has") ? innerHeight : dom.dock.getBoundingClientRect().top;

  function build(){
    const dock = el("div"); dock.id = "rs-dock"; dock.setAttribute("role", "region");
    const grip = el("div", "rs-dock-grip"); grip.title = "Drag to change the height. Double-click to close or open.";
    const hd = el("div", "rs-dock-hd"), tabs = el("nav", "rs-tabs rs-dock-tabs"), title = el("b", "rs-dock-title"), note = el("span", "rs-dock-note");
    const acts = el("span", "rs-dock-acts"), x = el("button", "rs-dock-x", "✕"), tog = el("button", "rs-dock-arrow");
    x.type = tog.type = "button"; tog.innerHTML = ARROW; x.title = "Remove"; x.setAttribute("aria-label", "Remove");
    hd.append(tabs, title, note, el("span", "rs-dock-sp"), acts, tog, x);
    const body = el("div", "rs-dock-body");
    dock.append(grip, hd, body);
    const pill = el("button"); pill.id = "rs-dock-pill"; pill.type = "button";
    document.body.append(dock, pill);
    tog.onclick = () => setOpen(!isOpen());
    x.onclick = () => current && remove(current);
    pill.onclick = () => setOpen(true);
    hd.addEventListener("click", e => { if(!isOpen() && !e.target.closest("button")) setOpen(true); });
    grip.addEventListener("dblclick", () => { if(!phone()) setOpen(!isOpen()); });
    grip.addEventListener("pointerdown", e => {
      const y0 = e.clientY;
      grip.setPointerCapture(e.pointerId); grip.classList.add("on");
      const mv = ev => { if(phone()) return; st.h = innerHeight - ev.clientY; st.open = true; place(); };
      grip.addEventListener("pointermove", mv);
      grip.addEventListener("pointerup", ev => {
        grip.removeEventListener("pointermove", mv); grip.classList.remove("on");
        // a phone: the grip of the panel's sheet - a tap goes to the next height, a drag of 30 px goes one height up or down (two heights: 40 % and full)
        if(phone()){
          const d = ev.clientY - y0;
          if(d > 30 && st.sheet !== 2){ setOpen(false); return; }
          st.sheet = d > 30 ? 1 : d < -30 ? 2 : st.sheet === 2 ? 1 : 2; save(); place();
        }
        else { st.h = H(); save(); place(); }
        changed();
      }, {once: true});
    });
    addEventListener("resize", () => place());
    new ResizeObserver(() => place()).observe(map.getContainer());
    matchMedia("(max-width: 700px)").addEventListener("change", () => setTimeout(place, 50));
    dom = {dock, grip, hd, tabs, title, note, acts, x, tog, body, pill};
  }

  function place(){
    if(!dom) return;
    const on = items.size > 0, open = on && isOpen();
    root.classList.toggle("rs-dock-has", on);
    root.classList.toggle("rs-dock-open", open);
    root.classList.toggle("rs-dock-shut", on && !open);
    root.classList.toggle("rs-dock-full", on && open && phone() && st.sheet === 2);
    root.style.setProperty("--rs-dock-h", (!on || phone() ? 0 : open ? H() : SHUT) + "px");
    dom.tog.title = open ? "Collapse" : "Open"; dom.tog.setAttribute("aria-label", dom.tog.title); dom.tog.setAttribute("aria-expanded", String(open));
    // the left and the right edge of the map (a panel in its own column, the divider of a docked Street View); a phone: the whole width
    if(!phone()){ const m = map.getContainer().getBoundingClientRect(); dom.dock.style.left = Math.max(0, m.left) + "px"; dom.dock.style.right = Math.max(0, innerWidth - m.right) + "px"; }
    else dom.dock.style.left = dom.dock.style.right = "";
    if(map) map.resize();
  }

  function draw(){
    if(!dom) return;
    const list = [...items.values()], it = items.get(current);
    dom.tabs.replaceChildren(...(list.length > 1 ? list.map(i => { const b = el("button", "rs-tab" + (i.id === current ? " on" : ""), i.label); b.type = "button";
      b.setAttribute("aria-selected", String(i.id === current)); b.onclick = () => { show(i.id); if(!isOpen()) setOpen(true); }; return b; }) : []));
    dom.tabs.hidden = list.length < 2; dom.title.hidden = list.length > 1;
    dom.title.textContent = it ? it.label : "";
    dom.note.textContent = it && it.note ? it.note : "";
    dom.acts.replaceChildren(...(it && it.actions ? [it.actions] : []));
    dom.x.hidden = !(it && it.closable);
    dom.body.replaceChildren(...(it ? [it.el] : []));
    dom.pill.textContent = it ? (it.note ? `${it.label} · ${it.note}` : it.label) : "";
    dom.dock.setAttribute("aria-label", it ? it.label : "Dock");
  }

  const changed = () => document.dispatchEvent(new CustomEvent("rs:dockchange", {detail: {open: isOpen(), id: current, height: phone() ? 0 : isOpen() ? H() : SHUT}}));
  function isOpen(){ return !!st.open && items.size > 0; }
  function setOpen(on){
    if(on && !items.size) return;
    st.open = !!on; if(on && phone() && !st.sheet) st.sheet = 1;
    save(); place(); changed();
  }

  function add({id, label, el: content, note = "", actions = null, closable = false}){
    if(!id || items.has(id)) throw new Error(`rs.dock.add: the id "${id}" is ${id ? "used twice" : "missing"}.`);
    if(!(content instanceof Element)) throw new Error("rs.dock.add: el must be an element.");
    if(!dom) build();
    items.set(id, {id, label: label || id, el: content, note, actions, closable});
    if(!current) current = id;
    if(st.open == null) st.open = false;        // a new dock starts closed: the page opens it
    draw(); place(); changed();
  }
  function remove(id){
    if(!items.delete(id)) return;
    if(current === id) current = items.keys().next().value ?? null;
    draw(); place(); changed();
  }
  function show(id){ if(!items.has(id)) throw new Error(`rs.dock.show: no content "${id}".`); current = id; draw(); changed(); }
  function open(id){ if(id != null) show(id); setOpen(true); }
  function close(){ setOpen(false); }
  function note(id, text){ const it = items.get(id); if(!it) return; it.note = text || ""; if(id === current) draw(); }
  function height(px){ if(px === undefined) return H(); st.h = px; save(); place(); changed(); return H(); }

  // ---- the dock's table (the design's "The dock's table"): a box as wide as its columns, the header row fixed, the first column in view when the table
  // scrolls sideways, numbers at the right; a BIGINT is exact (String), null is a muted "null". A click on a header sorts (rising, falling, the order of the
  // rows again): `onSort(column, dir)` lets the host sort all its rows (a result of more rows than the table has), else the table sorts its own rows. With
  // `idColumn`, a click on a row selects that road and zooms to it. Over 1000 rows the table draws only the rows in view. ----
  const NUM = /^(TINYINT|SMALLINT|INT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|FLOAT|REAL|DOUBLE|DECIMAL|NUMERIC|number|Int|Uint|Float)/i;
  const ROW_H = 26, WINDOW = 1000;
  const text = v => v == null ? "null" : typeof v === "number" && !Number.isInteger(v) ? String(+v.toFixed(3)) : String(v);
  const cmpVal = (a, b) => a == null ? (b == null ? 0 : 1) : b == null ? -1
    : (typeof a === "number" || typeof a === "bigint") && (typeof b === "number" || typeof b === "bigint") ? (a < b ? -1 : a > b ? 1 : 0)
    : String(a).localeCompare(String(b), undefined, {numeric: true});

  function table({columns = [], rows = [], idColumn = null, more = false, onSort = null, onRow = null} = {}){
    const box = el("div", "rs-dock-table rs-scroll"), t = el("table", "rs-table"), head = el("thead"), tb = el("tbody");
    t.append(head, tb); box.append(t);
    let cols = columns, data = rows, orig = rows, sort = null, picked = null, pickedRow = null;
    // the row that the person picked (onRow) is kept by its values, not by its place: a sort moves it and it stays selected; the host sorts all its rows
    // (onSort) and gives new row arrays, so the values decide (a BigInt is equal by value)
    const sameRow = (a, b) => !!a && !!b && a.length === b.length && a.every((v, j) => v === b[j]);
    const isNum = c => NUM.test(String(c.type || "")) && c.name !== idColumn;
    const idAt = () => idColumn ? cols.findIndex(c => c.name === idColumn) : -1;
    // the width of each column (Kaveh, 2026-11-06: "is there any algorithm to make suitable width size for every column?"): measured on a sample of
    // up to 200 rows in the table's font. A number column has its widest value (a number is never cut); a text column the width that 90 % of its
    // values fit, at least its header and at most 320 px (a longer value ends with "..." and has its text in the tooltip). The table then has fixed widths.
    const colgroup = el("colgroup"); t.prepend(colgroup);
    let measure = null;
    const widths = () => {
      if(!measure){ measure = document.createElement("canvas").getContext("2d"); }
      // the font of the dock's table (dashboard.css): the table may not be on the page yet, so its computed font is not known
      const pad = 30, sample = data.length <= 200 ? data : Array.from({length: 200}, (_, i) => data[Math.floor(i * data.length / 200)]);
      const w = (s, bold) => { measure.font = `${bold ? 600 : 400} 12.5px system-ui, sans-serif`; return measure.measureText(s).width; };
      const out = cols.map((c, j) => {
        const vals = sample.map((r) => w(text(r[j]))).sort((a, b) => a - b), head = Math.max(w(c.name, true), w(String(c.type || "")) * 0.85) + pad;
        const p = vals.length ? (isNum(c) ? vals[vals.length - 1] * 1.1 : vals[Math.floor((vals.length - 1) * 0.9)]) + pad : 0;   // (the table's digits are tabular: wider)
        return Math.round(Math.max(56, head, Math.min(isNum(c) ? 400 : 320, p)));
      });
      colgroup.replaceChildren(...out.map((x) => { const e = el("col"); e.style.width = x + "px"; return e; }));
      t.style.width = out.reduce((a, b) => a + b, 0) + "px";
      return out;
    };
    let colW = [];
    // the widths are measured once for each result (`set`), not at each draw: a sort changes the order of the rows, so the sample of 200 rows (and the
    // 90 % rule) gave other widths, and the columns jumped (Kaveh, 2026-11-07: "sort column in sql table change location of columns a little and they jumps")
    const drawHead = () => {
      const tr = el("tr");
      cols.forEach(c => {
        const th = el("th", isNum(c) ? "n" : ""); th.tabIndex = 0; th.title = c.about || c.name;
        th.append(el("span", "", c.name), el("small", "", String(c.type || "").replace(/\(.*$/, "").toUpperCase()));
        if(sort && sort.col === c.name) th.dataset.sort = sort.dir;
        th.onclick = () => sortBy(c.name);
        th.onkeydown = e => { if(e.key === "Enter" || e.key === " "){ e.preventDefault(); sortBy(c.name); } };
        tr.append(th);
      });
      head.replaceChildren(tr);
    };
    const rowEl = (r, i) => {
      const tr = el("tr"), k = idAt();
      // onRow(row, index, columns): the host's own click (the data dock: a row of names selects its roads); else a row with an id selects its road
      if(onRow){ tr.className = "rs-dock-id" + (sameRow(r, pickedRow) ? " on" : ""); tr.onclick = () => { pickedRow = r; mark(); onRow(r, i, cols); }; }
      else if(k >= 0){ tr.className = "rs-dock-id" + (picked != null && String(r[k]) === picked ? " on" : ""); tr.onclick = () => pick(String(r[k])); }
      r.forEach((v, j) => { const td = el("td", (v == null ? "rs-dock-null " : "") + (isNum(cols[j]) ? "n" : ""), text(v)); const s = text(v); if(s.length * 6.5 > (colW[j] || 320) - 28) td.title = s; tr.append(td); });
      tr.dataset.i = i;
      if(tr.onclick){ tr.tabIndex = 0; tr.onkeydown = e => { if(e.target === tr && (e.key === "Enter" || e.key === " ")){ e.preventDefault(); tr.click(); } }; }   // the keys do what a click does
      return tr;
    };
    // over WINDOW rows only the rows in view are in the table: a spacer row above and below keeps the height (one height per row)
    const drawBody = () => {
      if(data.length <= WINDOW){ tb.replaceChildren(...data.map(rowEl)); return; }
      const top = Math.max(0, Math.floor((box.scrollTop - 40) / ROW_H) - 20), n = Math.ceil(box.clientHeight / ROW_H) + 40, end = Math.min(data.length, top + n);
      const pad = h => { const tr = el("tr", "rs-dock-pad"); const td = el("td"); td.colSpan = cols.length || 1; td.style.height = h + "px"; tr.append(td); return tr; };
      tb.replaceChildren(pad(top * ROW_H), ...data.slice(top, end).map((r, i) => rowEl(r, top + i)), pad((data.length - end) * ROW_H));
    };
    box.addEventListener("scroll", () => { if(data.length > WINDOW) requestAnimationFrame(drawBody); }, {passive: true});
    async function sortBy(col){
      sort = !sort || sort.col !== col ? {col, dir: "asc"} : sort.dir === "asc" ? {col, dir: "desc"} : null;
      if(onSort && more){ const r = await onSort(sort ? sort.col : null, sort ? sort.dir : null); if(r){ data = orig = r.rows; } }
      else if(!sort) data = orig;
      else { const i = cols.findIndex(c => c.name === col), k = sort.dir === "asc" ? 1 : -1; data = [...orig].sort((x, y) => x[i] == null || y[i] == null ? cmpVal(x[i], y[i]) : k * cmpVal(x[i], y[i])); }
      drawHead(); drawBody();
    }
    const mark = () => tb.querySelectorAll("tr.rs-dock-id").forEach(tr => tr.classList.toggle("on", sameRow(data[+tr.dataset.i], pickedRow)));
    function pick(id){
      picked = id; tb.querySelectorAll("tr.rs-dock-id").forEach(tr => tr.classList.toggle("on", String(data[+tr.dataset.i][idAt()]) === id));
      if(window.rs){ window.rs.select(id); window.rs.focus([id]); }
    }
    const set = (x = {}) => { if(x.columns) cols = x.columns; if(x.rows){ data = orig = x.rows; sort = null; picked = null; pickedRow = null; } if("more" in x) more = x.more; box.scrollTop = 0; colW = widths(); drawHead(); drawBody(); };
    set({});
    // clear(): no row is selected (the host closed its card)
    const clear = () => { picked = null; pickedRow = null; tb.querySelectorAll("tr.rs-dock-id.on").forEach(tr => tr.classList.remove("on")); };
    return {el: box, set, rows: () => data, sort: () => sort, clear};
  }

  return {add, remove, open, close, isOpen, show, note, height, list: () => [...items.keys()], table, top: dockTop};
})();
export const dockTop = () => rsDock.top();

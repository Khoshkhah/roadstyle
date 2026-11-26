// A chart of a table of rows (docs/design/ask_and_data_dock.md, "4. Charts"; docs/guides/dashboard-parts.md, "A chart"): bar, line, histogram, scatter
// pie or heatmap, in SVG with the theme's tokens (--rs-chart-1 to -8, --rs-chart-grid, --mut, --ink), so it follows the theme with no code of its own. The marks are
// thin, a bar has round ends at its data end, a line is 2 px; the pointer on a mark shows its values (rs.hover); a click on a mark gives its row (onPick).
// The chart fits its box: the bars get thinner to fit the height, down to a minimum; only past it the box scrolls. A pie is the largest circle that
// fits above or beside its legend. A value label is on each bar or point only when all of them fit (at most 15); else the hover shows the value.
//
//   rs.chart(el, {kind, columns, rows, x, y, title, values, onPick, small, head, y_range}) -> {set(change), spec(), svg(), destroy()}
//     columns: [{name, type}]; rows: [[...]]; x: a column name; y: a column name or a list of them (bar, line); values: all the numbers of x (histogram);
//     title: false: no title, only the count (a card has its label as the title); count: the text of the count ("13 298 roads");
//     y_range (line, bar): "data": the y axis fits the values (a line only: a bar always starts at 0); [lo, hi]: the y axis covers at least lo to hi
//     (null: that end fits the values). The axis always covers every value, and its ends are nice ticks. None: from 0 (a line with no value under 0)
//   The legend of a line or a bar of two or more series is a filter: a click on a series hides it, a second click shows it (the last one stays); the
//   series keep their colours, and the y axis fits the series that show
//   heatmap: {kind: "heatmap", x, y, z, group, breaks, colors, mark}: a grid of cells, a column for each value of x and a row for each value of y, each cell
//     coloured by the class of its value of z (no cell for null). Numbers go in order (the rows from the bottom up), text in the order of the rows.
//     group: a column that puts the columns of the grid in groups, with a gap and the group's name under each group; breaks: the ascending class limits
//     (a value v is in class n, n = the number of limits <= v); colors: one more colour than breaks (none: 5 classes of the values, in --rs-chart-1);
//     mark: {x, y} a cell, {x} a column, {y} a row, or a list of them (with group: {x, group}). A click on a cell gives its row (onPick). A grid wider
//     than its box scrolls to the side; the row labels stay.
//   rs.chart.ranges(numbers, parts) -> {n, of(v), label(k)}: about `parts` ranges of the numbers (a bar or a pie of a number x with many values)
import {rsSvg} from "./svg.js";
import {rsHover} from "./hover.js";

export const rsChart = (() => {
  const SLOTS = 8, BARS = 40, POINTS = 5000, SLICES = 6, BINS = 20, LABELS = 15;   // a pie is for a few parts: 5 and "Other"; values on at most 15 bars
  const NUM = /^(TINYINT|SMALLINT|INT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|FLOAT|REAL|DOUBLE|DECIMAL|NUMERIC|Int|Uint|Float|Decimal|number)/i;
  const TIME = /^(DATE|TIMESTAMP|Date|Timestamp)/i;
  const isNum = (t) => NUM.test(String(t || "")) && !/\[\]|^(MAP|STRUCT|LIST)/i.test(String(t || ""));     // a list (BIGINT[]) is not a number
  const col = (c) => `var(--rs-chart-${(c % SLOTS) + 1})`;
  const fmt = (v) => { const n = Number(v); if(!isFinite(n)) return String(v);
    const s = Math.abs(n) >= 100 || Number.isInteger(n) ? Math.round(n).toLocaleString("en") : (+n.toPrecision(3)).toLocaleString("en", {maximumFractionDigits: 3});
    return s.replace(/,/g, " "); };
  // an axis tick, compact from 1 000 up: 2.5K, 1.2M (the hover and the labels give the full value)
  const tick = (v) => { const a = Math.abs(v); if(a >= 1e15) return v.toExponential(1).replace("e+", "e").replace(".0e", "e");          // 1.2e18: an id range, say
    for(const [d, u] of [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]]) if(a >= d) return +(v / d).toFixed(1) + u;
    return fmt(v); };
  // the width of a text in the chart's font, measured (a label column as wide as its labels)
  let ctx2d = null;
  const textWidth = (px) => (t) => { ctx2d = ctx2d || document.createElement("canvas").getContext("2d"); ctx2d.font = `${px}px system-ui, sans-serif`; return ctx2d.measureText(String(t)).width; };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
  const num = (v) => v == null || v === "" ? null : typeof v === "bigint" ? Number(v) : typeof v === "number" ? v : isFinite(+v) ? +v : null;
  const when = (v) => v == null ? null : typeof v === "number" || typeof v === "bigint" ? Number(v) : Date.parse(String(v).replace(" ", "T")) || null;
  // the ticks of a scale: at most 6, at 1, 2 or 5 times a power of ten
  function ticks(lo, hi, n = 5){
    if(!(hi > lo)){ hi = lo + 1; }
    const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw);
    // from a tick at or under the smallest value to a tick at or over the largest: the axis covers every value
    const out = []; for(let v = Math.floor(lo / step + 1e-9) * step; v < hi + step * (1 - 1e-9); v += step) out.push(+v.toPrecision(12));
    if(out[out.length - 1] < hi) out.push(+(out[out.length - 1] + step).toPrecision(12));
    return {list: out, lo: out[0], hi: out[out.length - 1]};
  }
  const dayFmt = (ms, span) => { const d = new Date(ms); return span > 3 * 365 * 864e5 ? String(d.getUTCFullYear()) : span > 90 * 864e5 ? d.toISOString().slice(0, 7) : d.toISOString().slice(0, 10); };

  // the kind's columns: the error line when the result has none that fit
  function check(s){
    const by = (n) => s.columns.findIndex((c) => c.name === n), ys = [].concat(s.y || []), isN = (n) => isNum((s.columns[by(n)] || {}).type);
    if(by(s.x) < 0) return `The column "${s.x}" is not in the result.`;
    for(const y of ys) if(by(y) < 0) return `The column "${y}" is not in the result.`;
    if(s.kind === "histogram") return isN(s.x) ? null : "A histogram needs a number column.";
    if(s.kind === "heatmap"){
      if(ys.length !== 1) return "A heatmap needs one column for y (its rows).";
      if(by(s.z) < 0) return s.z == null ? "A heatmap needs a number column for z." : `The column "${s.z}" is not in the result.`;
      if(!isN(s.z)) return "A heatmap needs a number column for z.";
      if(s.group != null && by(s.group) < 0) return `The column "${s.group}" is not in the result.`;
      if(s.colors && s.colors.length !== (s.breaks || []).length + 1) return "A heatmap has one more colour than breaks.";
      if(s.breaks && s.breaks.some((b, k) => k && b <= s.breaks[k - 1])) return "The breaks of a heatmap go up.";
      return null; }
    if(!ys.length) return `A ${s.kind} chart needs a number column for y.`;
    if(ys.some((y) => !isN(y))) return `A ${s.kind} chart needs number columns for y.`;
    const empty = ys.find((y) => s.rows.length && !s.rows.some((r) => num(r[by(y)]) != null));         // a number type with text in it (a DECIMAL as a quoted text)
    if(empty) return `The column "${empty}" has no numbers in its rows.`;
    if(s.kind === "scatter" && !isN(s.x)) return "A scatter chart needs two number columns.";
    if(s.kind === "line" && !isN(s.x) && !TIME.test(String(s.columns[by(s.x)].type))) return "A line chart needs a number, a date or a time column for x.";
    if(s.kind === "pie" && (ys.length > 1 || s.rows.some((r) => (num(r[by(ys[0])]) ?? 0) < 0))) return "A pie chart needs a text column and one number column of 0 or more.";
    if(!["bar", "line", "histogram", "scatter", "pie", "heatmap"].includes(s.kind)) return `There is no chart of the kind "${s.kind}".`;
    return null;
  }

  function chart(el, spec){
    let s = {...spec}, svg = null, foot = null;
    el.classList.add("rs-chart"); el.classList.toggle("rs-chart-small", !!spec.small);
    // draw again when the box gets wider, narrower, taller or shorter (the dock is resized); the size after a draw is the base, so the content's own
    // change of the size does not draw again
    let lastW = 0, lastH = 0;
    const ro = new ResizeObserver(() => { if(Math.abs(el.clientWidth - lastW) > 2 || Math.abs(el.clientHeight - lastH) > 2) draw(); }); ro.observe(el);
    function set(change){ s = {...s, ...change}; draw(); }
    let hsl = 0;                                                     // the side scroll of a heatmap, kept over a new draw
    const off = new Set();                                           // the series that the legend hides
    const ci = (y) => [].concat(s.y || []).indexOf(y);               // the colour slot of a series: its place in y, also when others are hidden
    function draw(){
      el.replaceChildren(); el.classList.remove("rs-chart-side");
      const bad = s.columns && s.rows ? check(s) : "No data.";
      if(bad){ el.append(Object.assign(document.createElement("p"), {className: "rs-chart-none", textContent: bad})); lastW = el.clientWidth; lastH = el.clientHeight; return; }
      const W = Math.max(160, el.clientWidth - 2), ys = [].concat(s.y || []);
      for(const y of off) if(!ys.includes(y)) off.delete(y);           // (a new y: its hidden series go)
      const filter = !s.small && ys.length > 1 && (s.kind === "line" || s.kind === "bar"), shown = filter ? ys.filter((y) => !off.has(y)) : ys;
      // the title and a muted line under it: what is drawn, and from how many rows (a small copy has neither: its card says it)
      if(!s.small){ const hd = document.createElement("div"), t = document.createElement("b"), sub = document.createElement("span"); hd.className = "rs-chart-hd";
        t.textContent = s.title === false ? "" : s.title || (s.kind === "histogram" ? `${s.x}: the rows in each range` : s.kind === "scatter" ? `${ys[0]} against ${s.x}` : s.kind === "heatmap" ? `${s.z} by ${s.x} and ${ys[0]}` : `${ys.join(" and ")} by ${s.x}`);
        const n = s.kind === "histogram" && s.values ? s.values.length : s.rows.length;
        sub.textContent = s.count != null ? s.count : `${fmt(n)} ${s.kind === "histogram" ? "values" : "rows"}`; hd.append(...(s.title === false ? [sub] : [t, sub]));
        if(s.head) s.head.replaceChildren(hd); else el.append(hd); }      // head: an element of the host for the title line (the data dock's tool row)
      // a small copy has no legend, but a pie keeps it: its slices have no names of their own (Kaveh: "legend is not there", the pie in Ask's card)
      const legend = s.kind === "pie" || (!s.small && (ys.length > 1 || s.kind === "heatmap")) ? document.createElement("div") : null;
      if(legend){ legend.className = "rs-chart-legend"; el.append(legend); if(s.kind !== "pie" && s.kind !== "heatmap") legendOf(legend, ys.map((y, k) => [y, col(k)]));
        if(filter) [...legend.children].forEach((k, j) => { const y = ys[j], on = !off.has(y);
          k.className = "rs-chart-key" + (on ? "" : " rs-off"); k.setAttribute("role", "button"); k.tabIndex = 0; k.setAttribute("aria-pressed", String(on));
          k.setAttribute("aria-label", on ? `Hide ${y}` : `Show ${y}`);
          const flip = () => { if(on && shown.length === 1) return; on ? off.add(y) : off.delete(y); draw(); el.querySelector(`.rs-chart-key:nth-child(${j + 1})`)?.focus(); };
          k.addEventListener("click", flip); k.addEventListener("keydown", (e) => { if(e.key === "Enter" || e.key === " "){ e.preventDefault(); flip(); } }); }); }
      // the foot: a line under the chart when it does not show all the rows (empty: no line); a small copy has none
      foot = document.createElement("div"); foot.className = "rs-chart-foot"; if(!s.small) el.append(foot);
      foot.textContent = s.kind === "bar" && s.rows.length > BARS ? `… ${fmt(s.rows.length - BARS)} more in the table` : s.kind === "scatter" && s.rows.length > POINTS ? `The first ${fmt(POINTS)} of ${fmt(s.rows.length)} rows` : "";
      // the height of the plot: the box's height without its padding, the title, the legend and the foot (as drawn: a legend can have two lines)
      const cs = getComputedStyle(el); inner = Math.floor(el.getBoundingClientRect().height - parseFloat(cs.borderTopWidth) - parseFloat(cs.borderBottomWidth) - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom));
      const H = s.small ? Math.max(40, inner) : Math.max(s.kind === "pie" || s.kind === "bar" ? 60 : 100, room());      // (a bar chart has its own minimum)
      // width 100 % and a viewBox: the chart is never wider than its box, also when the box gets narrower before the next draw
      svg = rsSvg(null, "svg", {width: "100%", height: H, viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMin meet", role: "img", "aria-label": s.title || `${s.kind} chart of ${ys.join(", ") || s.x}`});
      // the size and the paint of the drawing are in its style: a host's rule for icons (`#sb svg {width: 18px; fill: none; stroke: currentColor}`) is not for it
      svg.style.cssText = `width:100%;height:${H}px;fill:initial;stroke:none;stroke-width:1;stroke-linecap:butt;stroke-linejoin:miter`;
      el.insertBefore(svg, s.small ? null : foot);
      const kinds = {bar, line, histogram, scatter, pie, heatmap};
      kinds[s.kind](W, H, shown, legend);
      // the box scrolls only when the drawing is taller than the box (bars at their least height); else nothing in it can make a scrollbar
      el.classList.toggle("rs-chart-scrolls", Number(svg.getAttribute("height")) > inner + 1);
      lastW = el.clientWidth; lastH = el.clientHeight; more();
    }
    // a chart taller than its box: the box scrolls; data-more while there is more below (a phone shows a fade there: its scrollbar shows only in a scroll)
    const more = () => el.toggleAttribute("data-more", el.scrollTop + el.clientHeight < el.scrollHeight - 2);
    el.addEventListener("scroll", more, {passive: true});
    let inner = 0;
    // whole pixels: a box of 191.6 px (a scaled screen) with a 192 px drawing scrolls (Kaveh: "why it has scrol in this position?")
    const room = () => Math.floor(inner - [...el.children].reduce((t, c) => t + (c === svg || c.contains(svg) ? 0 : c.getBoundingClientRect().height), 0));
    const size = (w, h) => { svg.setAttribute("height", h); svg.style.height = h + "px"; svg.setAttribute("viewBox", `0 0 ${w} ${h}`); };
    const at = (n) => s.columns.findIndex((c) => c.name === n);
    const tip = (node, i, extra) => { if(s.small) return;
      node.style.cursor = s.onPick ? "pointer" : "default";
      node.classList.add("rs-mk");                                   // under the pointer: this mark, the others fade (CSS)
      node.addEventListener("mouseenter", () => { svg.classList.add("rs-chart-dim"); node.classList.add("on"); });
      node.addEventListener("mouseleave", () => { svg.classList.remove("rs-chart-dim"); node.classList.remove("on"); });
      rsHover.on(node, () => `<b>${esc(extra ? extra.head : s.rows[i][at(s.x)])}</b>` + (extra ? extra.lines : [].concat(s.y).filter((y) => !off.has(y)).map((y) => `<br>${esc(y)}: ${fmt(s.rows[i][at(y)])}`).join("")));
      node.addEventListener("mouseleave", () => rsHover.hide());
      if(s.onPick && i != null) node.addEventListener("click", () => s.onPick(i));
    };
    const legendOf = (legend, items) => { if(!legend) return; for(const [name, c] of items){ const k = document.createElement("span"), sw = document.createElement("i");
      sw.style.background = c; k.append(sw, document.createTextNode(name)); legend.append(k); } };
    // the axes of a plot: grid lines of y and their labels at the left, the x labels under the plot; small: no labels
    function frame(W, H, yr, {left = 44, top = 10, bottom = 22, xt = null} = {}){
      const pad = s.small ? {l: 4, r: 4, t: 6, b: 4} : {l: left, r: 12, t: top, b: bottom};
      const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b, Y = (v) => pad.t + ih - ((v - yr.lo) / (yr.hi - yr.lo)) * ih;
      for(const v of yr.list){ rsSvg(svg, "line", {x1: pad.l, x2: pad.l + iw, y1: Y(v), y2: Y(v), stroke: "var(--rs-chart-grid)", "stroke-width": 1});
        if(!s.small) rsSvg(svg, "text", {x: pad.l - 6, y: Y(v) + 3.5, "text-anchor": "end", fill: "var(--mut)", "font-size": 10.5}, tick(v)); }
      const base = Y(Math.max(yr.lo, Math.min(yr.hi, 0)));            // the base line: one step darker than the grid
      rsSvg(svg, "line", {x1: pad.l, x2: pad.l + iw, y1: base, y2: base, stroke: "var(--line)", "stroke-width": 1});
      // an x label stays inside the chart: a long one (a day) at an edge moves in
      if(xt && !s.small) for(const [x, label] of xt){ const half = String(label).length * 3.1 + 2;
        rsSvg(svg, "text", {x: Math.max(half, Math.min(W - half, x)), y: pad.t + ih + 16, "text-anchor": "middle", fill: "var(--mut)", "font-size": 10.5}, label); }
      return {pad, iw, ih, Y};
    }
    // the y scale: from 0 (zero), or fitted to the values; y_range [lo, hi] makes it at least that wide (it never hides a value)
    const yRange = (ys, rows, zero = true) => { let lo = zero ? 0 : Infinity, hi = zero ? 0 : -Infinity;
      for(const r of rows) for(const y of ys){ const v = num(r[at(y)]); if(v != null){ lo = Math.min(lo, v); hi = Math.max(hi, v); } }
      const g = Array.isArray(s.y_range) ? s.y_range : [];
      if(g[0] != null) lo = Math.min(lo, g[0]);
      if(g[1] != null) hi = Math.max(hi, g[1]);
      return ticks(isFinite(lo) ? lo : 0, isFinite(hi) ? hi : lo + 1); };
    // a bar with a round end (4 px) at its data end and a flat end at the base
    const barPath = (x, y, w, h, horizontal, up) => { const r = Math.min(4, (horizontal ? h : w) / 2, Math.abs(horizontal ? w : h));
      if(horizontal){ const x2 = x + w; return `M${x},${y}H${x2 - r}Q${x2},${y} ${x2},${y + r}V${y + h - r}Q${x2},${y + h} ${x2 - r},${y + h}H${x}Z`; }
      return up ? `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
                : `M${x},${y}V${y + h - r}Q${x},${y + h} ${x + r},${y + h}H${x + w - r}Q${x + w},${y + h} ${x + w},${y + h - r}V${y}Z`; };

    function bar(W, H, ys, legend){
      const lab = (v) => v == null ? "null" : typeof v === "number" || typeof v === "bigint" ? fmt(v) : String(v);     // a number label: rounded
      const rows = s.rows.slice(0, BARS), labels = rows.map((r) => lab(r[at(s.x)])), yr = yRange(ys, rows);
      const horizontal = !s.small && labels.some((l) => l.length > 8);
      const top = ys.length ? rows.reduce((b, r, i) => (num(r[at(ys[0])]) ?? -Infinity) > (num(rows[b][at(ys[0])]) ?? -Infinity) ? i : b, 0) : -1;
      if(horizontal){
        const lw = Math.min(160, 10 + 6.2 * Math.max(...labels.map((l) => l.length))), pad = {l: lw, r: 56, t: 6, b: 18};
        // the bars fit the height: a row is at least 12 px (its label) and each bar 4 px; a longer list is taller than the box, and the box scrolls
        const need = rows.length * Math.max(12, 5 * ys.length + 4) + pad.t + pad.b;
        if(need > H){ H = need; size(W, H); }
        const iw = W - pad.l - pad.r, band = (H - pad.t - pad.b) / rows.length, X = (v) => pad.l + ((v - yr.lo) / (yr.hi - yr.lo)) * iw;
        for(const v of yr.list){ rsSvg(svg, "line", {x1: X(v), x2: X(v), y1: pad.t, y2: H - pad.b, stroke: "var(--rs-chart-grid)"}); rsSvg(svg, "text", {x: X(v), y: H - 4, "text-anchor": "middle", fill: "var(--mut)", "font-size": 10.5}, tick(v)); }
        const bh = Math.max(2, Math.min(22, (band - 2) / ys.length));
        rows.forEach((r, i) => {
          rsSvg(svg, "text", {x: pad.l - 6, y: pad.t + band * i + band / 2 + 3.5, "text-anchor": "end", fill: "var(--ink)", "font-size": 11}, labels[i].length > 24 ? labels[i].slice(0, 23) + "…" : labels[i]);
          ys.forEach((y, k) => { const v = num(r[at(y)]) ?? 0, y0 = pad.t + band * i + (band - bh * ys.length) / 2 + bh * k;
            tip(rsSvg(svg, "path", {d: barPath(X(Math.min(0, v)), y0 + 1, Math.abs(X(v) - X(0)), bh - 2, true), fill: col(ci(y))}), i);
            // the value at the tip: of each bar up to 15 bars, else of the largest; in the text colour, never the bar's
            if(ys.length === 1 && (rows.length <= LABELS || i === top)) rsSvg(svg, "text", {class: "rs-chart-val", x: X(Math.max(0, v)) + 5, y: y0 + bh / 2 + 3.5, fill: "var(--ink)", "font-size": 10.5}, fmt(v)); });
        });
        return;
      }
      if(H < 100){ H = 100; size(W, H); }                              // upright bars: a plot of at least 100 px
      const {pad, iw, Y} = frame(W, H, yr), band = iw / rows.length, bw = Math.max(2, Math.min(26, (band - 2) / ys.length));     // a bar is at most 24 px
      rows.forEach((r, i) => ys.forEach((y, k) => { const v = num(r[at(y)]) ?? 0, x0 = pad.l + band * i + (band - bw * ys.length) / 2 + bw * k;
        tip(rsSvg(svg, "path", {d: barPath(x0 + 1, Math.min(Y(v), Y(0)), bw - 2, Math.abs(Y(v) - Y(0)), false, v >= 0), fill: col(ci(y))}), i);
        // the value on the cap, when it fits over its bar's slot: of each bar up to 15 bars, else of the largest
        if(!s.small && ys.length === 1 && (rows.length <= LABELS || i === top) && fmt(v).length * 6.2 < band) rsSvg(svg, "text", {class: "rs-chart-val", x: x0 + bw / 2, y: Math.min(Y(v), Y(0)) - 5, "text-anchor": "middle", fill: "var(--ink)", "font-size": 10.5}, fmt(v)); }));
      if(!s.small){ const every = Math.ceil(rows.length / Math.max(1, Math.floor(iw / 56)));
        rows.forEach((r, i) => { if(i % every === 0) rsSvg(svg, "text", {x: pad.l + band * i + band / 2, y: H - 6, "text-anchor": "middle", fill: "var(--mut)", "font-size": 10.5}, labels[i]); }); }
    }
    function line(W, H, ys, legend){
      const t = TIME.test(String(s.columns[at(s.x)].type)), xv = (r) => t ? when(r[at(s.x)]) : num(r[at(s.x)]);
      const idx = s.rows.map((r, i) => i).filter((i) => xv(s.rows[i]) != null).sort((a, b) => xv(s.rows[a]) - xv(s.rows[b]));
      // values of 0 or more: from 0; as many x ticks as fit (a day label needs about 80 px, a number 48 px)
      const xs = idx.map((i) => xv(s.rows[i])), lo = Math.min(...xs), hi = Math.max(...xs), yr = yRange(ys, s.rows, s.y_range !== "data" && !Array.isArray(s.y_range) && !s.rows.some((r) => ys.some((y) => (num(r[at(y)]) ?? 0) < 0))), xr = ticks(lo, hi, Math.max(1, Math.min(5, Math.floor((W - 56) / (t ? 80 : 48)))));
      const pad0 = s.small ? 4 : 44, iw0 = W - pad0 - 12, X = (v) => pad0 + ((v - xr.lo) / (xr.hi - xr.lo || 1)) * iw0;
      const {Y} = frame(W, H, yr, {xt: xr.list.map((v) => [X(v), t ? dayFmt(v, hi - lo) : tick(v)])});
      ys.forEach((y, k) => {
        const pts = idx.map((i) => [X(xv(s.rows[i])), num(s.rows[i][at(y)])]).filter((p) => p[1] != null).map(([x, v]) => `${x},${Y(v)}`);
        if(ys.length === 1 && pts.length > 1){                        // one series: a soft wash under its line (10 %), and its last value at the end
          const fx = pts[0].split(",")[0], lx = pts[pts.length - 1].split(",")[0], b = Y(Math.max(yr.lo, Math.min(yr.hi, 0)));
          rsSvg(svg, "polygon", {points: `${fx},${b} ${pts.join(" ")} ${lx},${b}`, fill: col(ci(y)), "fill-opacity": 0.1, stroke: "none"}); }
        rsSvg(svg, "polyline", {points: pts.join(" "), fill: "none", stroke: col(ci(y)), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"});
        // the value over each point only when all of them fit: one line, at most 15 points, each label narrower than the space to the next point;
        // else no label (the hover shows the value)
        const pv = idx.map((i) => [X(xv(s.rows[i])), num(s.rows[i][at(y)])]).filter((p) => p[1] != null), lw = (v) => fmt(v).length * 6.2 + 6;
        if(!s.small && ys.length === 1 && pv.length <= LABELS && pv.every(([x, v], j) => j === 0 || x - pv[j - 1][0] >= (lw(v) + lw(pv[j - 1][1])) / 2))
          for(const [x, v] of pv){ const w = lw(v) / 2, cy = Y(v);
            rsSvg(svg, "text", {class: "rs-chart-val", x: Math.max(w, Math.min(W - w, x)), y: cy - 8 < 10 ? cy + 16 : cy - 8, "text-anchor": "middle", fill: "var(--ink)", "font-size": 10.5}, fmt(v)); }
        if(idx.length <= 60 && !s.small) idx.forEach((i) => { const v = num(s.rows[i][at(y)]); if(v == null) return;
          tip(rsSvg(svg, "circle", {cx: X(xv(s.rows[i])), cy: Y(v), r: 4, fill: col(ci(y)), stroke: "var(--bg)", "stroke-width": 2}), i); });
      });
      if(idx.length > 60 && !s.small){                                  // many points: the nearest row to the pointer, with a crosshair
        const hit = rsSvg(svg, "rect", {x: pad0, y: 0, width: iw0, height: H, fill: "transparent"}), cross = rsSvg(svg, "line", {y1: 8, y2: H - 22, stroke: "var(--mut)", "stroke-width": 1, opacity: 0});
        let near = null;
        hit.addEventListener("mousemove", (ev) => { const r = svg.getBoundingClientRect(), x = ev.clientX - r.left;
          near = idx.reduce((b, i) => Math.abs(X(xv(s.rows[i])) - x) < Math.abs(X(xv(s.rows[b])) - x) ? i : b, idx[0]);
          cross.setAttribute("x1", X(xv(s.rows[near]))); cross.setAttribute("x2", X(xv(s.rows[near]))); cross.setAttribute("opacity", 0.5);
          rsHover.show(`<b>${esc(t ? new Date(xv(s.rows[near])).toISOString().slice(0, 10) : fmt(xv(s.rows[near])))}</b>` + ys.map((y) => `<br>${esc(y)}: ${fmt(s.rows[near][at(y)])}`).join(""), ev); });
        hit.addEventListener("mouseleave", () => { rsHover.hide(); cross.setAttribute("opacity", 0); });
        if(s.onPick) hit.addEventListener("click", () => near != null && s.onPick(near));
      }
    }
    function histogram(W, H){
      const vals = (s.values || s.rows.map((r) => r[at(s.x)])).map(num).filter((v) => v != null);
      if(!vals.length){ el.replaceChildren(Object.assign(document.createElement("p"), {className: "rs-chart-none", textContent: "There are no numbers in this column."})); return; }
      let lo = Infinity, hi = -Infinity; for(const v of vals){ if(v < lo) lo = v; if(v > hi) hi = v; }
      const xr = ticks(lo, hi, BINS), step = (xr.hi - xr.lo) / BINS, n = new Array(BINS).fill(0);
      for(const v of vals) n[Math.min(BINS - 1, Math.floor((v - xr.lo) / step))]++;
      const yr = ticks(0, Math.max(...n)), pad0 = s.small ? 4 : 44, iw = W - pad0 - 12, X = (v) => pad0 + ((v - xr.lo) / (xr.hi - xr.lo)) * iw;
      const {Y} = frame(W, H, yr, {xt: ticks(xr.lo, xr.hi).list.map((v) => [X(v), tick(v)])});
      n.forEach((c, b) => { const a = xr.lo + step * b; if(!c) return;
        tip(rsSvg(svg, "path", {d: barPath(X(a) + 1, Y(c), X(a + step) - X(a) - 2, Y(0) - Y(c), false, true), fill: col(0)}), null,
            {head: `${fmt(a)} to ${fmt(a + step)}`, lines: `<br>${fmt(c)} row${c === 1 ? "" : "s"}`}); });
    }
    function scatter(W, H, ys){
      const y = ys[0], rows = s.rows.slice(0, POINTS), xs = rows.map((r) => num(r[at(s.x)])), yv = rows.map((r) => num(r[at(y)]));
      const okx = xs.filter((v) => v != null), xr = ticks(Math.min(...okx), Math.max(...okx)), yr = ticks(Math.min(...yv.filter((v) => v != null)), Math.max(...yv.filter((v) => v != null)));
      const pad0 = s.small ? 4 : 44, iw = W - pad0 - 12, X = (v) => pad0 + ((v - xr.lo) / (xr.hi - xr.lo)) * iw;
      // the axis titles are outside the plot: y over the y ticks, x under the x ticks (a small copy has none)
      const {Y} = frame(W, H, yr, {top: 24, bottom: 36, xt: xr.list.map((v) => [X(v), tick(v)])});
      rows.forEach((r, i) => { if(xs[i] == null || yv[i] == null) return;
        tip(rsSvg(svg, "circle", {cx: X(xs[i]), cy: Y(yv[i]), r: s.small ? 2 : 4, fill: col(0), "fill-opacity": 0.75, stroke: "var(--bg)", "stroke-width": 2}), i,
            {head: String(r[at(s.x)] != null ? `${s.x}: ${fmt(xs[i])}` : ""), lines: `<br>${esc(y)}: ${fmt(yv[i])}`}); });
      if(!s.small){ rsSvg(svg, "text", {x: W - 12, y: H - 3, "text-anchor": "end", fill: "var(--mut)", "font-size": 10.5}, s.x);
                    rsSvg(svg, "text", {x: 2, y: 11, fill: "var(--mut)", "font-size": 10.5}, y); }
    }
    function pie(W, H, ys, legend){
      const y = ys[0], order = s.rows.map((r, i) => [i, num(r[at(y)]) ?? 0]).filter((p) => p[1] > 0).sort((a, b) => b[1] - a[1]);
      const keep = order.length > SLICES ? order.slice(0, SLICES - 1) : order, rest = order.slice(keep.length).reduce((t, p) => t + p[1], 0);
      const parts = keep.map(([i, v]) => ({i, v, name: ((x) => x == null ? "null" : typeof x === "number" || typeof x === "bigint" ? fmt(x) : String(x))(s.rows[i][at(s.x)])})).concat(rest > 0 ? [{i: null, v: rest, name: `Other (${order.length - keep.length})`}] : []);
      const total = parts.reduce((t, p) => t + p.v, 0);
      legendOf(legend, parts.map((p, k) => [`${p.name} ${Math.round((p.v / total) * 100)} %`, col(k)]));
      // the largest pie that fits: with the legend above it (in lines over the full width) or beside it (a column at its right); the two are in the
      // middle of the box (CSS .rs-chart-side)
      if(legend){ const above = Math.min(W, room());
        el.classList.add("rs-chart-side"); svg.setAttribute("width", 0);              // (the legend's own width, with no pie beside it)
        const tall = room() + legend.offsetHeight, lw = legend.offsetWidth + 16, side = legend.offsetHeight <= tall ? Math.min(W - lw, tall) : 0;
        if(side > above){ H = Math.max(60, tall); W = Math.max(60, side); svg.setAttribute("width", W); }
        else { el.classList.remove("rs-chart-side"); svg.setAttribute("width", "100%"); H = Math.max(60, room()); }
        size(W, H); }
      const cx = W / 2, cy = H / 2, R = Math.max(10, Math.min(W, H) / 2 - 6);      // the names are in the legend, not round the pie
      let a0 = -Math.PI / 2;
      parts.forEach((p, k) => {
        const a1 = a0 + (p.v / total) * Math.PI * 2, big = a1 - a0 > Math.PI ? 1 : 0, pt = (a) => `${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`;
        const d = parts.length === 1 ? `M${cx - R},${cy}a${R},${R} 0 1 0 ${2 * R},0a${R},${R} 0 1 0 ${-2 * R},0` : `M${cx},${cy}L${pt(a0)}A${R},${R} 0 ${big} 1 ${pt(a1)}Z`;
        tip(rsSvg(svg, "path", {d, fill: col(k), stroke: "var(--bg)", "stroke-width": 2, "stroke-linejoin": "round"}), p.i,
            {head: p.name, lines: `<br>${esc(y)}: ${fmt(p.v)} (${Math.round((p.v / total) * 100)} %)`});
        a0 = a1;
      });
    }
    function heatmap(W, H, ys, legend){
      const xi = at(s.x), yi = at(ys[0]), zi = at(s.z), gi = s.group != null ? at(s.group) : -1, lab = (v) => v == null ? "null" : typeof v === "number" ? fmt(v) : String(v);
      // the columns {k, x, g} and the rows {k, y}, each value once; numbers in order (the columns of a group stay together), text as the rows come
      const cols = new Map(), rws = new Map(), cell = new Map(), gOrder = new Map();
      s.rows.forEach((r, i) => { const g = gi < 0 ? null : r[gi], k = (gi < 0 ? "" : String(g) + "\u0000") + String(r[xi]), yk = String(r[yi]);
        if(!gOrder.has(String(g))) gOrder.set(String(g), gOrder.size);
        if(!cols.has(k)) cols.set(k, {k, x: r[xi], g}); if(!rws.has(yk)) rws.set(yk, {k: yk, y: r[yi]});
        if(num(r[zi]) != null) cell.set(k + "\u0001" + yk, i); });
      let cx = [...cols.values()], ry = [...rws.values()];
      if(cx.every((c) => num(c.x) != null)) cx.sort((a, b) => gOrder.get(String(a.g)) - gOrder.get(String(b.g)) || num(a.x) - num(b.x));
      else if(gi >= 0) cx.sort((a, b) => gOrder.get(String(a.g)) - gOrder.get(String(b.g)));       // (a stable sort: the order of the rows inside a group)
      if(ry.every((r) => num(r.y) != null)) ry.sort((a, b) => num(b.y) - num(a.y));                   // the smallest at the bottom
      // the classes: the page's limits and colours, or 5 classes of the values in the first chart colour, from light to full
      const zs = [...cell.values()].map((i) => num(s.rows[i][zi]));
      let br = s.breaks, cl = s.colors;
      if(!br){ const t = ticks(Math.min(...zs), Math.max(...zs), 5).list; br = t.slice(1, -1); }
      if(!cl) cl = br.concat([0]).map((_, k, a) => `color-mix(in srgb, var(--rs-chart-1) ${Math.round(15 + 85 * k / Math.max(1, a.length - 1))}%, var(--bg))`);
      const klass = (v) => br.filter((b) => b <= v).length;
      // the legend: one bar of the class colours, the limits under the joins and the name of z at its end
      if(legend){ const bar = document.createElement("div"), cells = document.createElement("div"), lims = document.createElement("div"), unit = document.createElement("span");
        bar.className = "rs-chart-scale"; cells.className = "rs-chart-scale-bar"; lims.className = "rs-chart-scale-lim"; unit.textContent = s.z;
        bar.setAttribute("role", "img"); bar.setAttribute("aria-label", `${s.z}: ` + cl.map((c, k) => k === 0 ? `under ${fmt(br[0])}` : k === br.length ? `${fmt(br[k - 1])} or more` : `${fmt(br[k - 1])} to ${fmt(br[k])}`).join(", "));
        for(const c of cl){ const i = document.createElement("i"); i.style.background = c; cells.append(i); }
        br.forEach((b, k) => { const t = document.createElement("span"); t.textContent = fmt(b); t.style.left = `${(k + 1) / cl.length * 100}%`; lims.append(t); });
        const col0 = document.createElement("div"); col0.append(cells, lims); bar.append(col0, unit); legend.replaceChildren(bar);
        H = Math.max(100, room()); }                                  // (the legend is in its place now)
      // the text of a cell on the page's colour #rrggbb: dark on a light colour, light on a dark one (a theme token cannot follow the page's colour)
      const ink = (c) => { const m = /^#([0-9a-f]{6})$/i.exec(c); if(!m) return "var(--ink)"; const n = parseInt(m[1], 16);
        return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255 > 0.55 ? "#1a1a1a" : "#ffffff"; };
      // the size: the row labels at the left, the columns share the rest. The grid fits the box first: the gap between groups gets smaller (8 px
      // down to 2 px), then the columns (down to 3 px); only then the grid is wider than the box, and the box scrolls to the side. A row is at least
      // 10 px, else the box scrolls down. Over the grid: the name of y (over the grid too, so the label column is as wide as the labels); under it:
      // the column labels and the name of x, or with group the group names (the x values of a group are often only an order)
      const MINW = s.small ? 1 : 3, MINH = s.small ? 1 : 10;
      // the label column: the width of the widest row label as the page draws it, and 5 px to the grid (no free space at its left)
      const rowTag = [].concat(s.mark || []).some((m) => m.y != null && m.x == null);           // (a marked row has its label in a tag: 8 px more)
      const tw = textWidth(10.5), lw = s.small ? 0 : Math.ceil(Math.min(120, 5 + (rowTag ? 8 : 0) + Math.max(6, ...ry.map((r) => tw(lab(r.y))))));
      const gaps = cx.filter((c, j) => j && String(c.g) !== String(cx[j - 1].g)).length, top = s.small ? 0 : 4, bot = s.small ? 0 : 36, room0 = W - lw - 4, n = Math.max(1, cx.length);
      // the gap between groups: a third of a column, from 2 to 8 px (the line under each group shows where it ends; many groups must not take the columns' width)
      const G = !gaps ? 0 : Math.max(2, Math.min(8, room0 / (n + gaps / 3) / 3));
      const cw = Math.max(MINW, (room0 - gaps * G) / n);
      const xs = []; let at0 = 0; cx.forEach((c, j) => { if(j && String(c.g) !== String(cx[j - 1].g)) at0 += G; xs.push(at0); at0 += cw; });
      const GW = Math.ceil(at0) + 4;
      // two drawings side by side: the row labels, and the grid in a box that scrolls to the side (its scrollbar takes height from the rows)
      const side = rsSvg(null, "svg", {width: lw, height: H, "aria-hidden": "true"}), wrapEl = document.createElement("div"), scroll = document.createElement("div");
      wrapEl.className = "rs-chart-hm"; scroll.className = "rs-chart-hscroll"; side.style.cssText = svg.style.cssText; side.style.width = lw + "px";
      svg.replaceWith(wrapEl); wrapEl.append(side, scroll); scroll.append(svg);
      if(!s.small){ const yn = document.createElement("div"); yn.className = "rs-chart-yname"; yn.textContent = ys[0]; wrapEl.before(yn); H -= yn.offsetHeight; }
      svg.setAttribute("width", GW); svg.removeAttribute("preserveAspectRatio"); svg.style.width = GW + "px"; size(GW, 1);
      if(s.small) side.remove();
      const ch = Math.max(MINH, (H - (scroll.offsetHeight - scroll.clientHeight) - top - bot) / Math.max(1, ry.length));
      H = Math.ceil(top + ch * ry.length + bot); size(GW, H); side.setAttribute("height", H); side.style.height = H + "px";
      // a cell is a tile: a gap round it and round corners, when it is large enough
      const gp = Math.min(cw, ch) >= 8 ? 1.5 : Math.min(cw, ch) >= 4 ? 1 : 0, rr = Math.min(cw, ch) >= 8 ? 2 : 0, yb = top + ch * ry.length;
      // a thin edge in the text colour at 16 % round a tile of 8 px or more: a pale class stays apart from a light card; a narrower tile keeps all its colour
      const edge = !s.small && Math.min(cw, ch) - gp >= 8 ? {stroke: "color-mix(in srgb, var(--ink) 16%, transparent)", "stroke-width": 1} : {};
      // the marks: a column or a row is a light band behind its tiles and its label in a dark tag; a cell is a ring in the text colour round it
      const marks = [].concat(s.mark || []).map((m) => {
        const nx = m.x == null ? null : cx.findIndex((c) => String(c.x) === String(m.x) && (m.group == null || String(c.g) === String(m.group)));
        const ny = m.y == null ? null : ry.findIndex((r) => String(r.y) === String(m.y));
        return nx === -1 || ny === -1 || (nx == null && ny == null) ? null : {nx, ny}; }).filter(Boolean);
      const tagX = new Set(), tagY = new Set();
      for(const {nx, ny} of marks){ if(nx != null && ny != null) continue;
        if(ny == null){ tagX.add(nx); rsSvg(svg, "rect", {class: "rs-chart-mark", x: xs[nx] - 2, y: top - 4, width: cw + 4, height: ch * ry.length + 8, rx: 4, fill: "color-mix(in srgb, var(--ink) 12%, transparent)", "pointer-events": "none"}); }
        else { tagY.add(ny); rsSvg(svg, "rect", {class: "rs-chart-mark", x: -2, y: top + ch * ny - 2, width: at0 + 4, height: ch + 4, rx: 4, fill: "color-mix(in srgb, var(--ink) 12%, transparent)", "pointer-events": "none"}); } }
      ry.forEach((r, j) => { const y = top + ch * j;
        cx.forEach((c, n) => { const i = cell.get(c.k + "\u0001" + r.k); if(i == null) return;
          const v = num(s.rows[i][zi]), f = cl[klass(v)], t = fmt(v);
          rsSvg(svg, "rect", {x: xs[n] + gp / 2, y: y + gp / 2, width: Math.max(0.5, cw - gp), height: Math.max(0.5, ch - gp), rx: rr, fill: f, "data-i": i, ...edge});
          if(!s.small && ch >= 12 && cw >= t.length * 6 + 4) rsSvg(svg, "text", {x: xs[n] + cw / 2, y: y + ch / 2 + 3.5, "text-anchor": "middle", fill: ink(f), "font-size": 10, "pointer-events": "none"}, t); }); });
      for(const {nx, ny} of marks) if(nx != null && ny != null){ const x = xs[nx], y = top + ch * ny;
        rsSvg(svg, "rect", {class: "rs-chart-mark", x: x - 1, y: y - 1, width: cw + 2, height: ch + 2, rx: rr + 2, fill: "none", stroke: "var(--ink)", "stroke-width": 2, "pointer-events": "none"});
        rsSvg(svg, "rect", {x: x + gp / 2 + 0.5, y: y + gp / 2 + 0.5, width: Math.max(0.5, cw - gp - 1), height: Math.max(0.5, ch - gp - 1), rx: rr, fill: "none", stroke: "var(--bg)", "stroke-width": 1, "pointer-events": "none"}); }
      if(s.small) return;
      // a label in a dark tag (a marked column or row)
      const tag = (on, x, y, text, anchor) => { const w = text.length * 6.2 + 10, x0 = anchor === "end" ? x - w : x - w / 2;
        rsSvg(on, "rect", {x: x0, y: y - 11.5, width: w, height: 16, rx: 4, fill: "var(--ink)"});
        rsSvg(on, "text", {x: x0 + w / 2, y, "text-anchor": "middle", fill: "var(--bg)", "font-size": 10.5, "font-weight": 600}, text); };
      // the labels: as many as fit (a row label needs 12 px, and with more than 6 rows every second one; a column label its width)
      const ev = Math.max(ry.length > 6 ? 2 : 1, Math.ceil(12 / ch));
      ry.forEach((r, j) => { const y = top + ch * j + ch / 2 + 3.5;
        if(tagY.has(j)) tag(side, lw - 1, y, lab(r.y), "end"); else if((ry.length - 1 - j) % ev === 0) rsSvg(side, "text", {x: lw - 5, y, "text-anchor": "end", fill: "var(--mut)", "font-size": 10.5}, lab(r.y)); });
      const xe = Math.ceil((6.2 * Math.max(1, ...cx.map((c) => lab(c.x).length)) + 8) / cw);
      if(gi < 0) cx.forEach((c, n) => { const x = xs[n] + cw / 2, near = [...tagX].some((t) => t !== n && Math.abs(xs[t] - xs[n]) < (lab(c.x).length * 6.2 + 16));
        if(tagX.has(n)) tag(svg, x, yb + 15, lab(c.x)); else if(n % xe === 0 && !near) rsSvg(svg, "text", {x, y: yb + 15, "text-anchor": "middle", fill: "var(--mut)", "font-size": 10.5}, lab(c.x)); });
      // the groups: a thin line under the columns of each group, and its name on the first of two lines where it does not touch the last name there;
      // a name that is wider than that: its last part ("NE" of "front · NE"); a group with no room for either has its line, and the hover names it
      if(gi >= 0){ const ends = [-Infinity, -Infinity];
        for(let a = 0; a < cx.length;){ let b = a; while(b + 1 < cx.length && String(cx[b + 1].g) === String(cx[a].g)) b++;
          const x0 = xs[a], x1 = xs[b] + cw, mid = (x0 + x1) / 2, name = lab(cx[a].g), last = name.split(/\s*[·|\/,:\-–]\s*|\s+/).filter(Boolean).pop() || name;
          rsSvg(svg, "line", {x1: x0 + 0.5, x2: x1 - 0.5, y1: yb + 3, y2: yb + 3, stroke: "var(--mut)", "stroke-width": 1.5, "stroke-linecap": "round"});
          let done = false;
          for(const t of name === last ? [name] : [name, last]){ const w = t.length * 6.2, lo = Math.max(0, Math.min(at0 - w, mid - w / 2));
            for(const ln of [0, 1]) if(!done && lo >= ends[ln] + 6 && (w <= x1 - x0 + 2 * G + 12 || t === last)){
              rsSvg(svg, "text", {x: lo + w / 2, y: yb + 16 + 13 * ln, "text-anchor": "middle", fill: "var(--ink)", "font-size": 10.5}, t); ends[ln] = lo + w; done = true; }
            if(done) break; }
          a = b + 1; } }
      if(gi < 0) rsSvg(svg, "text", {x: at0, y: yb + 31, "text-anchor": "end", fill: "var(--mut)", "font-size": 10.5}, s.x);
      // the pointer on a cell: its row, its column and its value, and a frame round it; a click gives its row
      const hov = rsSvg(svg, "rect", {width: cw + 1, height: ch + 1, rx: rr + 1, fill: "none", stroke: "var(--ink)", "stroke-width": 1.5, opacity: 0, "pointer-events": "none"});
      const under = (e) => { const i = e.target && e.target.getAttribute && e.target.getAttribute("data-i"); return i == null ? null : +i; };
      rsHover.on(svg, (e) => { const i = under(e); if(i == null){ hov.setAttribute("opacity", 0); return null; }
        const r = s.rows[i], c = e.target;
        hov.setAttribute("x", +c.getAttribute("x") - gp / 2 - 0.5); hov.setAttribute("y", +c.getAttribute("y") - gp / 2 - 0.5); hov.setAttribute("opacity", 1);
        return `<b>${esc(ys[0])} ${esc(lab(r[yi]))} · ${esc(s.x)} ${esc(lab(r[xi]))}</b>` + (gi >= 0 ? `<br>${esc(s.group)}: ${esc(lab(r[gi]))}` : "") + `<br>${esc(s.z)}: ${fmt(r[zi])}`; });
      svg.addEventListener("mouseleave", () => { rsHover.hide(); hov.setAttribute("opacity", 0); });
      svg.style.cursor = s.onPick ? "pointer" : "default";
      if(s.onPick) svg.addEventListener("click", (e) => { const i = under(e); if(i != null) s.onPick(i); });
      scroll.scrollLeft = hsl; scroll.addEventListener("scroll", () => { hsl = scroll.scrollLeft; }, {passive: true});
    }
    draw();
    return {set, spec: () => ({...s}), svg: () => svg, destroy(){ ro.disconnect(); el.replaceChildren(); }};
  }
  // the first chart of a result, from its columns: a date or a time and a number: line; a text and a number: bar; one number: histogram; two numbers: scatter
  chart.guess = (columns, idColumn) => {
    const c = columns.filter((x) => x.name !== idColumn), n = c.filter((x) => isNum(x.type)), t = c.find((x) => TIME.test(String(x.type)));
    const txt = c.find((x) => !isNum(x.type) && !TIME.test(String(x.type)));
    if(t && n.length) return {kind: "line", x: t.name, y: n[0].name};
    if(txt && n.length) return {kind: "bar", x: txt.name, y: n[0].name};
    if(n.length >= 2) return {kind: "scatter", x: n[0].name, y: n[1].name};
    if(n.length === 1) return {kind: "histogram", x: n[0].name};
    return null;
  };
  // the ranges of many numbers, for a bar (about 12) or a pie (about 6) of a number x with more than 40 values (the data dock, the chart card): a step of
  // 1, 2, 2.5 or 5 times a power of ten, from a multiple of the step at or under the smallest number. of(v): the range of v; label(k): "0–250"
  chart.ranges = (vals, parts) => {
    let lo = Infinity, hi = -Infinity; for(const v of vals){ if(v < lo) lo = v; if(v > hi) hi = v; }
    if(!isFinite(lo)){ lo = 0; hi = 0; }
    const raw = (hi - lo) / parts || 1, pw = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 2.5, 5, 10].map((k) => k * pw).find((x) => x >= raw);
    const start = Math.floor(lo / step) * step, n = Math.max(1, Math.ceil((hi - start) / step + 1e-9));
    const f = (v) => (+v.toPrecision(6)).toLocaleString("en", {maximumFractionDigits: 6}).replace(/,/g, " ");
    return {n, of: (v) => Math.max(0, Math.min(n - 1, Math.floor((v - start) / step))), label: (k) => `${f(start + k * step)}\u2013${f(start + (k + 1) * step)}`};
  };
  chart.check = check;
  chart.isNumber = (type) => isNum(type);
  chart.isTime = (type) => TIME.test(String(type || ""));
  return chart;
})();

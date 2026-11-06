// A chart of a table of rows (docs/design/ask_and_data_dock.md, "4. Charts"; docs/guides/dashboard-parts.md, "A chart"): bar, line, histogram, scatter
// or pie, in SVG with the theme's tokens (--rs-chart-1 to -8, --rs-chart-grid, --mut, --ink), so it follows the theme with no code of its own. The marks are
// thin, a bar has round ends at its data end, a line is 2 px; the pointer on a mark shows its values (rs.hover); a click on a mark gives its row (onPick).
//
//   rs.chart(el, {kind, columns, rows, x, y, title, values, onPick, small}) -> {set(change), spec(), svg(), destroy()}
//     columns: [{name, type}]; rows: [[...]]; x: a column name; y: a column name or a list of them (bar, line); values: all the numbers of x (histogram)
import {rsSvg} from "./svg.js";
import {rsHover} from "./hover.js";

export const rsChart = (() => {
  const SLOTS = 8, BARS = 40, POINTS = 5000, SLICES = 8, BINS = 20;
  const NUM = /^(TINYINT|SMALLINT|INT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|FLOAT|REAL|DOUBLE|DECIMAL|NUMERIC|Int|Uint|Float|Decimal|number)/i;
  const TIME = /^(DATE|TIMESTAMP|Date|Timestamp)/i;
  const isNum = (t) => NUM.test(String(t || "")) && !/\[\]|^(MAP|STRUCT|LIST)/i.test(String(t || ""));     // a list (BIGINT[]) is not a number
  const col = (c) => `var(--rs-chart-${(c % SLOTS) + 1})`;
  const fmt = (v) => { const n = Number(v); if(!isFinite(n)) return String(v);
    const s = Math.abs(n) >= 100 || Number.isInteger(n) ? Math.round(n).toLocaleString("en") : (+n.toPrecision(3)).toLocaleString("en", {maximumFractionDigits: 3});
    return s.replace(/,/g, " "); };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
  const num = (v) => v == null || v === "" ? null : typeof v === "bigint" ? Number(v) : typeof v === "number" ? v : isFinite(+v) ? +v : null;
  const when = (v) => v == null ? null : typeof v === "number" || typeof v === "bigint" ? Number(v) : Date.parse(String(v).replace(" ", "T")) || null;
  // the ticks of a scale: at most 6, at 1, 2 or 5 times a power of ten
  function ticks(lo, hi, n = 5){
    if(!(hi > lo)){ hi = lo + 1; }
    const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw);
    const out = []; for(let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toPrecision(12));
    return {list: out, lo: Math.min(lo, out[0]), hi: Math.max(hi, out[out.length - 1])};
  }
  const dayFmt = (ms, span) => { const d = new Date(ms); return span > 3 * 365 * 864e5 ? String(d.getUTCFullYear()) : span > 90 * 864e5 ? d.toISOString().slice(0, 7) : d.toISOString().slice(0, 10); };

  // the kind's columns: the error line when the result has none that fit
  function check(s){
    const by = (n) => s.columns.findIndex((c) => c.name === n), ys = [].concat(s.y || []), isN = (n) => isNum((s.columns[by(n)] || {}).type);
    if(by(s.x) < 0) return `The column "${s.x}" is not in the result.`;
    for(const y of ys) if(by(y) < 0) return `The column "${y}" is not in the result.`;
    if(s.kind === "histogram") return isN(s.x) ? null : "A histogram needs a number column.";
    if(!ys.length) return `A ${s.kind} chart needs a number column for y.`;
    if(ys.some((y) => !isN(y))) return `A ${s.kind} chart needs number columns for y.`;
    if(s.kind === "scatter" && !isN(s.x)) return "A scatter chart needs two number columns.";
    if(s.kind === "line" && !isN(s.x) && !TIME.test(String(s.columns[by(s.x)].type))) return "A line chart needs a number, a date or a time column for x.";
    if(s.kind === "pie" && (ys.length > 1 || s.rows.some((r) => (num(r[by(ys[0])]) ?? 0) < 0))) return "A pie chart needs a text column and one number column of 0 or more.";
    if(!["bar", "line", "histogram", "scatter", "pie"].includes(s.kind)) return `There is no chart of the kind "${s.kind}".`;
    return null;
  }

  function chart(el, spec){
    let s = {...spec}, svg = null, foot = null;
    el.classList.add("rs-chart");
    let lastW = 0;                                             // draw again when the width changes, not for a change of the content
    const ro = new ResizeObserver(() => { const w = el.clientWidth; if(Math.abs(w - lastW) > 2){ lastW = w; draw(); } }); ro.observe(el);
    function set(change){ s = {...s, ...change}; draw(); }
    function draw(){
      el.replaceChildren();
      const bad = s.columns && s.rows ? check(s) : "No data.";
      if(bad){ el.append(Object.assign(document.createElement("p"), {className: "rs-chart-none", textContent: bad})); return; }
      const W = Math.max(160, el.clientWidth - 2), ys = [].concat(s.y || []); lastW = el.clientWidth;
      const legend = ys.length > 1 || s.kind === "pie" ? document.createElement("div") : null;
      if(legend){ legend.className = "rs-chart-legend"; el.append(legend); }
      let H = Math.max(100, el.clientHeight - (legend ? 24 : 0) - 20);
      // horizontal bars have at least 18 px each: a long list is taller than the box, and the box scrolls
      const rowsH = s.kind === "bar" && !s.small && s.rows.slice(0, BARS).some((r) => String(r[at(s.x)] ?? "").length > 8) ? s.rows.slice(0, BARS).length * 18 * Math.max(1, ys.length * 0.6) + 26 : 0;
      if(rowsH > H) H = rowsH;
      // width 100 % and a viewBox: the chart is never wider than its box, also when the box gets narrower before the next draw
      svg = rsSvg(el, "svg", {width: "100%", height: H, viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMin meet", role: "img", "aria-label": s.title || `${s.kind} chart of ${ys.join(", ") || s.x}`});
      foot = document.createElement("div"); foot.className = "rs-chart-foot"; el.append(foot);
      const kinds = {bar, line, histogram, scatter, pie};
      kinds[s.kind](W, H, ys, legend);
    }
    const at = (n) => s.columns.findIndex((c) => c.name === n);
    const tip = (node, i, extra) => { if(s.small) return;
      node.style.cursor = s.onPick ? "pointer" : "default";
      rsHover.on(node, () => `<b>${esc(extra ? extra.head : s.rows[i][at(s.x)])}</b>` + (extra ? extra.lines : [].concat(s.y).map((y) => `<br>${esc(y)}: ${fmt(s.rows[i][at(y)])}`).join("")));
      node.addEventListener("mouseleave", () => rsHover.hide());
      if(s.onPick && i != null) node.addEventListener("click", () => s.onPick(i));
    };
    const legendOf = (legend, items) => { if(!legend) return; for(const [name, c] of items){ const k = document.createElement("span"), sw = document.createElement("i");
      sw.style.background = c; k.append(sw, document.createTextNode(name)); legend.append(k); } };
    // the axes of a plot: grid lines of y and their labels at the left, the x labels under the plot; small: no labels
    function frame(W, H, yr, {left = 44, bottom = 22, xt = null} = {}){
      const pad = s.small ? {l: 4, r: 4, t: 6, b: 4} : {l: left, r: 12, t: 10, b: bottom};
      const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b, Y = (v) => pad.t + ih - ((v - yr.lo) / (yr.hi - yr.lo)) * ih;
      for(const v of yr.list){ rsSvg(svg, "line", {x1: pad.l, x2: pad.l + iw, y1: Y(v), y2: Y(v), stroke: "var(--rs-chart-grid)", "stroke-width": 1});
        if(!s.small) rsSvg(svg, "text", {x: pad.l - 6, y: Y(v) + 3.5, "text-anchor": "end", fill: "var(--mut)", "font-size": 10.5}, fmt(v)); }
      if(xt && !s.small) for(const [x, label] of xt) rsSvg(svg, "text", {x, y: H - 6, "text-anchor": "middle", fill: "var(--mut)", "font-size": 10.5}, label);
      return {pad, iw, ih, Y};
    }
    const yRange = (ys, rows, zero = true) => { let lo = zero ? 0 : Infinity, hi = zero ? 0 : -Infinity;
      for(const r of rows) for(const y of ys){ const v = num(r[at(y)]); if(v != null){ lo = Math.min(lo, v); hi = Math.max(hi, v); } }
      return ticks(isFinite(lo) ? lo : 0, isFinite(hi) ? hi : 1); };
    // a bar with a round end (4 px) at its data end and a flat end at the base
    const barPath = (x, y, w, h, horizontal, up) => { const r = Math.min(4, (horizontal ? h : w) / 2, Math.abs(horizontal ? w : h));
      if(horizontal){ const x2 = x + w; return `M${x},${y}H${x2 - r}Q${x2},${y} ${x2},${y + r}V${y + h - r}Q${x2},${y + h} ${x2 - r},${y + h}H${x}Z`; }
      return up ? `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
                : `M${x},${y}V${y + h - r}Q${x},${y + h} ${x + r},${y + h}H${x + w - r}Q${x + w},${y + h} ${x + w},${y + h - r}V${y}Z`; };

    function bar(W, H, ys, legend){
      const rows = s.rows.slice(0, BARS), labels = rows.map((r) => String(r[at(s.x)] ?? "null")), yr = yRange(ys, rows);
      if(s.rows.length > BARS) foot.textContent = `… ${fmt(s.rows.length - BARS)} more in the table`;
      legendOf(legend, ys.map((y, k) => [y, col(k)]));
      const horizontal = !s.small && labels.some((l) => l.length > 8);
      if(horizontal){
        const lw = Math.min(160, 10 + 6.2 * Math.max(...labels.map((l) => l.length))), pad = {l: lw, r: 40, t: 6, b: 18};
        const iw = W - pad.l - pad.r, band = (H - pad.t - pad.b) / rows.length, X = (v) => pad.l + ((v - yr.lo) / (yr.hi - yr.lo)) * iw;
        for(const v of yr.list){ rsSvg(svg, "line", {x1: X(v), x2: X(v), y1: pad.t, y2: H - pad.b, stroke: "var(--rs-chart-grid)"}); rsSvg(svg, "text", {x: X(v), y: H - 4, "text-anchor": "middle", fill: "var(--mut)", "font-size": 10.5}, fmt(v)); }
        const bh = Math.max(2, Math.min(22, (band - 2) / ys.length));
        rows.forEach((r, i) => {
          rsSvg(svg, "text", {x: pad.l - 6, y: pad.t + band * i + band / 2 + 3.5, "text-anchor": "end", fill: "var(--ink)", "font-size": 11}, labels[i].length > 24 ? labels[i].slice(0, 23) + "…" : labels[i]);
          ys.forEach((y, k) => { const v = num(r[at(y)]) ?? 0, y0 = pad.t + band * i + (band - bh * ys.length) / 2 + bh * k;
            tip(rsSvg(svg, "path", {d: barPath(X(Math.min(0, v)), y0 + 1, Math.abs(X(v) - X(0)), bh - 2, true), fill: col(k)}), i); });
        });
        return;
      }
      const {pad, iw, Y} = frame(W, H, yr), band = iw / rows.length, bw = Math.max(2, Math.min(36, (band - 2) / ys.length));
      rows.forEach((r, i) => ys.forEach((y, k) => { const v = num(r[at(y)]) ?? 0, x0 = pad.l + band * i + (band - bw * ys.length) / 2 + bw * k;
        tip(rsSvg(svg, "path", {d: barPath(x0 + 1, Math.min(Y(v), Y(0)), bw - 2, Math.abs(Y(v) - Y(0)), false, v >= 0), fill: col(k)}), i); }));
      if(!s.small){ const every = Math.ceil(rows.length / Math.max(1, Math.floor(iw / 56)));
        rows.forEach((r, i) => { if(i % every === 0) rsSvg(svg, "text", {x: pad.l + band * i + band / 2, y: H - 6, "text-anchor": "middle", fill: "var(--mut)", "font-size": 10.5}, labels[i]); }); }
    }
    function line(W, H, ys, legend){
      const t = TIME.test(String(s.columns[at(s.x)].type)), xv = (r) => t ? when(r[at(s.x)]) : num(r[at(s.x)]);
      const idx = s.rows.map((r, i) => i).filter((i) => xv(s.rows[i]) != null).sort((a, b) => xv(s.rows[a]) - xv(s.rows[b]));
      legendOf(legend, ys.map((y, k) => [y, col(k)]));
      const xs = idx.map((i) => xv(s.rows[i])), lo = Math.min(...xs), hi = Math.max(...xs), yr = yRange(ys, s.rows, false), xr = ticks(lo, hi);
      const pad0 = s.small ? 4 : 44, iw0 = W - pad0 - 12, X = (v) => pad0 + ((v - xr.lo) / (xr.hi - xr.lo || 1)) * iw0;
      const {Y} = frame(W, H, yr, {xt: xr.list.map((v) => [X(v), t ? dayFmt(v, hi - lo) : fmt(v)])});
      ys.forEach((y, k) => {
        const pts = idx.map((i) => [X(xv(s.rows[i])), num(s.rows[i][at(y)])]).filter((p) => p[1] != null).map(([x, v]) => `${x},${Y(v)}`);
        rsSvg(svg, "polyline", {points: pts.join(" "), fill: "none", stroke: col(k), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"});
        if(idx.length <= 60 && !s.small) idx.forEach((i) => { const v = num(s.rows[i][at(y)]); if(v == null) return;
          tip(rsSvg(svg, "circle", {cx: X(xv(s.rows[i])), cy: Y(v), r: 4, fill: col(k), stroke: "var(--bg)", "stroke-width": 2}), i); });
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
      const {Y} = frame(W, H, yr, {xt: ticks(xr.lo, xr.hi).list.map((v) => [X(v), fmt(v)])});
      n.forEach((c, b) => { const a = xr.lo + step * b; if(!c) return;
        tip(rsSvg(svg, "path", {d: barPath(X(a) + 1, Y(c), X(a + step) - X(a) - 2, Y(0) - Y(c), false, true), fill: col(0)}), null,
            {head: `${fmt(a)} to ${fmt(a + step)}`, lines: `<br>${fmt(c)} row${c === 1 ? "" : "s"}`}); });
      foot.textContent = `${fmt(vals.length)} values of ${s.x} in ${BINS} ranges`;
    }
    function scatter(W, H, ys){
      const y = ys[0], rows = s.rows.slice(0, POINTS), xs = rows.map((r) => num(r[at(s.x)])), yv = rows.map((r) => num(r[at(y)]));
      if(s.rows.length > POINTS) foot.textContent = `The first ${fmt(POINTS)} of ${fmt(s.rows.length)} rows`;
      const okx = xs.filter((v) => v != null), xr = ticks(Math.min(...okx), Math.max(...okx)), yr = ticks(Math.min(...yv.filter((v) => v != null)), Math.max(...yv.filter((v) => v != null)));
      const pad0 = s.small ? 4 : 44, iw = W - pad0 - 12, X = (v) => pad0 + ((v - xr.lo) / (xr.hi - xr.lo)) * iw;
      const {Y} = frame(W, H, yr, {xt: xr.list.map((v) => [X(v), fmt(v)])});
      rows.forEach((r, i) => { if(xs[i] == null || yv[i] == null) return;
        tip(rsSvg(svg, "circle", {cx: X(xs[i]), cy: Y(yv[i]), r: s.small ? 2 : 4, fill: col(0), "fill-opacity": 0.75, stroke: "var(--bg)", "stroke-width": 1.5}), i,
            {head: String(r[at(s.x)] != null ? `${s.x}: ${fmt(xs[i])}` : ""), lines: `<br>${esc(y)}: ${fmt(yv[i])}`}); });
      if(!s.small){ rsSvg(svg, "text", {x: W - 12, y: H - 22, "text-anchor": "end", fill: "var(--mut)", "font-size": 10.5}, s.x);
                    rsSvg(svg, "text", {x: pad0 + 4, y: 12, fill: "var(--mut)", "font-size": 10.5}, y); }
    }
    function pie(W, H, ys, legend){
      const y = ys[0], order = s.rows.map((r, i) => [i, num(r[at(y)]) ?? 0]).filter((p) => p[1] > 0).sort((a, b) => b[1] - a[1]);
      const keep = order.length > SLICES ? order.slice(0, SLICES - 1) : order, rest = order.slice(keep.length).reduce((t, p) => t + p[1], 0);
      const parts = keep.map(([i, v]) => ({i, v, name: String(s.rows[i][at(s.x)] ?? "null")})).concat(rest > 0 ? [{i: null, v: rest, name: `Other (${order.length - keep.length})`}] : []);
      const total = parts.reduce((t, p) => t + p.v, 0), cx = W / 2, cy = H / 2, R = Math.max(10, Math.min(W, H) / 2 - (s.small ? 4 : 26));
      legendOf(legend, parts.map((p, k) => [`${p.name} ${Math.round((p.v / total) * 100)} %`, col(k)]));
      let a0 = -Math.PI / 2;
      parts.forEach((p, k) => {
        const a1 = a0 + (p.v / total) * Math.PI * 2, big = a1 - a0 > Math.PI ? 1 : 0, pt = (a) => `${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`;
        const d = parts.length === 1 ? `M${cx - R},${cy}a${R},${R} 0 1 0 ${2 * R},0a${R},${R} 0 1 0 ${-2 * R},0` : `M${cx},${cy}L${pt(a0)}A${R},${R} 0 ${big} 1 ${pt(a1)}Z`;
        tip(rsSvg(svg, "path", {d, fill: col(k), stroke: "var(--bg)", "stroke-width": 2, "stroke-linejoin": "round"}), p.i,
            {head: p.name, lines: `<br>${esc(y)}: ${fmt(p.v)} (${Math.round((p.v / total) * 100)} %)`});
        a0 = a1;
      });
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
  chart.check = check;
  chart.isNumber = (type) => isNum(type);
  chart.isTime = (type) => TIME.test(String(type || ""));
  return chart;
})();

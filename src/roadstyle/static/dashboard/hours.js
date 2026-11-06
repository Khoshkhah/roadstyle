// The hour picker of a page (docs/design/dashboard_parts_2.md), in the look of the day picker: a field that shows the hour and opens a list of the
// hours (Kaveh chose this design on 2026-11-06).
//   const h = rs.hours.use(el, {value: 8, onChange: h => load(h)});                       // one hour: "‹ [08:00 – 09:00 ▾] ›"
//   const r = rs.hours.use(el, {value: [7, 9], range: true, onChange: ([a, b]) => ...});  // a range: "From [07:00 ▾] To [10:00 ▾] 3 h", the hours 7, 8 and 9
// One hour: "‹" and "›" go to the hour before and after. A range: "From" is the first hour, "To" is the end of the last hour (later than From).
// The list scrolls to the chosen hour; the arrow keys walk it, Enter picks, Escape closes. `hours` (default all 24) are the hours that can be
// chosen: the others are dimmed in the list. It returns {value(), set(v, quiet)}.
import {rsPopAt, rsPopClose, rsPopKeys} from "./menu.js";
const _hrT = h => String(h).padStart(2, "0") + ":00";
const _hrClock = '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="6.3"/><path d="M8 4.6V8l2.3 1.5"/></svg>';
const _hrChev = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
const _hrTick = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3.5 8.5 3 3 6-7"/></svg>';
// a field and its list: `items()` gives [{v, label, off}], `now()` the value that has the tick, `pick(v)` sets it
function _hrField(name, items, now, pick, clock){
  const field = document.createElement("button"); field.type = "button"; field.className = "rs-day-field rs-hours-field";
  field.setAttribute("aria-haspopup", "listbox"); field.setAttribute("aria-expanded", "false"); field.setAttribute("aria-label", name);
  field.innerHTML = '<span class="rs-day-text"></span>' + (clock ? _hrClock : "") + _hrChev;
  const box = document.createElement("div"); box.className = "rs-menu rs-hours-list"; box.hidden = true; box.setAttribute("role", "listbox"); box.setAttribute("aria-label", name);
  document.body.appendChild(box);
  const close = () => { box.hidden = true; field.setAttribute("aria-expanded", "false"); };
  function open(){
    const v = now();
    box.innerHTML = items().map(it => '<button type="button" class="rs-menu-item' + (it.v === v ? " on" : "") + '" role="option" aria-selected="' + (it.v === v) +
      '" data-v="' + it.v + '"' + (it.off ? " disabled" : "") + "><span>" + it.label + "</span>" + (it.v === v ? _hrTick : "") + "</button>").join("");
    box.hidden = false; field.setAttribute("aria-expanded", "true"); rsPopAt(box, field);
    const on = box.querySelector(".on") || box.querySelector(".rs-menu-item:not(:disabled)");
    if(on){ box.scrollTop = on.offsetTop - (box.clientHeight - on.offsetHeight) / 2; on.focus({preventScroll: true}); }
  }
  field.addEventListener("click", e => { e.stopPropagation(); box.hidden ? open() : close(); });
  field.addEventListener("keydown", e => { if(e.key === "ArrowDown" && box.hidden){ open(); e.preventDefault(); } });
  box.addEventListener("click", e => { const b = e.target.closest(".rs-menu-item"); if(!b || b.disabled) return; close(); field.focus(); pick(+b.dataset.v); });
  box.addEventListener("keydown", e => { if(e.key === "Tab") close(); });
  rsPopKeys(box, ".rs-menu-item");
  rsPopClose(box, field, close);
  return field;
}
export const rsHours = {
  use(el, opts = {}){
    if(!(el instanceof Element)) throw new Error("rs.hours.use: give the element that the picker goes in");
    const range = !!opts.range, can = new Set(opts.hours || [...Array(24).keys()]);
    let cur = range ? [...(opts.value || [0, 23])] : [opts.value ?? 0, opts.value ?? 0];
    const name = opts.label || (range ? "Hours" : "Hour");
    el.classList.add("rs-day", "rs-hours");
    el.innerHTML = '<div class="rs-day-label"></div><div class="rs-day-row"></div>';
    el.querySelector(".rs-day-label").textContent = name;
    const row = el.querySelector(".rs-day-row"), val = () => range ? [...cur] : cur[0];
    function set(v, quiet){
      const next = range ? [Math.min(...v), Math.max(...v)] : [v, v];
      if(next.some(h => !(h >= 0 && h <= 23))) throw new Error("rs.hours: an hour is 0 to 23");
      const same = next[0] === cur[0] && next[1] === cur[1]; cur = next; paint();
      if(!quiet && !same) opts.onChange?.(val());
    }
    let paint;
    if(!range){
      const step = d => { const b = document.createElement("button"); b.type = "button"; b.className = "rs-day-step"; b.dataset.step = d; b.textContent = d < 0 ? "‹" : "›";
        b.title = d < 0 ? "The hour before" : "The hour after"; b.setAttribute("aria-label", b.title); return b; };
      const near = d => { for(let h = cur[0] + d; h >= 0 && h <= 23; h += d) if(can.has(h)) return h; return null; };   // the next hour that can be chosen
      const field = _hrField(name, () => [...Array(24).keys()].map(h => ({v: h, label: _hrT(h) + " – " + _hrT(h + 1), off: !can.has(h)})), () => cur[0], h => set(h), true);
      const [lo, hi] = [step(-1), step(1)];
      row.append(lo, field, hi);
      [lo, hi].forEach(b => b.addEventListener("click", () => { const h = near(+b.dataset.step); if(h !== null) set(h); }));
      paint = () => { field.firstChild.textContent = _hrT(cur[0]) + " – " + _hrT(cur[0] + 1); lo.disabled = near(-1) === null; hi.disabled = near(1) === null; };
    }else{
      // From: 00:00 to 23:00. To: the end of the last hour, 01:00 to 24:00, later than From. A From at or after To moves To to one hour after it.
      const from = _hrField("From", () => [...Array(24).keys()].map(h => ({v: h, label: _hrT(h), off: !can.has(h)})), () => cur[0],
        h => set([h, Math.max(h, cur[1])]));
      const to = _hrField("To", () => [...Array(24).keys()].map(h => ({v: h, label: _hrT(h + 1), off: !can.has(h) || h < cur[0]})), () => cur[1],
        h => set([cur[0], h]));
      const span = document.createElement("span"); span.className = "rs-hours-n";
      const tag = t => { const s = document.createElement("span"); s.className = "rs-hours-tag"; s.textContent = t; return s; };
      row.append(tag("From"), from, tag("To"), to, span);
      paint = () => { from.firstChild.textContent = _hrT(cur[0]); to.firstChild.textContent = _hrT(cur[1] + 1); span.textContent = (cur[1] - cur[0] + 1) + " h"; };
    }
    set(range ? cur : cur[0], true);
    return {value: val, set};
  },
};

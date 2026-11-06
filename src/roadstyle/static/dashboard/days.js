// The day picker of a page (docs/guides/dashboard-parts.md): a label, a field that shows the day and opens a calendar, the day before and the day
// after, and "Latest". The page gives an empty element and its days, roadstyle builds the rest:
//   const day = rs.days.use(el, {days: ["2026-10-04", "2026-10-05"], value: "2026-10-05", onChange: d => load(d)});
// `days` are the days that have data, as "YYYY-MM-DD": the calendar offers only these, and the arrows step through them. `onChange(day)` can give a
// promise: while it runs, the field pulses and the buttons wait; if it fails, the day goes back and a line under the row says so. It returns
// `{set(day, quiet), value()}`.
// `rs.days.range(el, {unit, value: [from, to], min, max, days, onChange})` is the same field for a period: from one day to another ("day"), one
// week, Monday to Sunday ("week"), or one month ("month"); the arrows go to the period before and after. It returns `{set([from, to], quiet), value(), unit(u)}`.
import {rsPopAt, rsPopClose} from "./menu.js";
const _dyChev = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
const _dyCal = '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5.5 1.5v3M10.5 1.5v3"/></svg>';
const _dyMonths = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const _dyDate = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const _dyIso = (y, m, d) => y + "-" + String(m + 1).padStart(2, "0") + "-" + String(d).padStart(2, "0");
const _dyText = s => { const t = _dyDate(s);    // "Mon 5 Oct 2026", the same in every browser (toLocaleDateString adds a comma in some)
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][t.getDay()] + " " + t.getDate() + " " + _dyMonths[t.getMonth()].slice(0, 3) + " " + t.getFullYear(); };
const _dyAdd = (s, n) => { const t = _dyDate(s), u = new Date(t.getFullYear(), t.getMonth(), t.getDate() + n); return _dyIso(u.getFullYear(), u.getMonth(), u.getDate()); };
const _dyMon = s => _dyAdd(s, -((_dyDate(s).getDay() + 6) % 7));                       // the Monday of the week of a day
const _dyWeekNo = s => { const t = _dyDate(_dyAdd(_dyMon(s), 3)), y = new Date(t.getFullYear(), 0, 4);   // ISO 8601: the week with the year's first Thursday is week 1
  return 1 + Math.round((t - _dyDate(_dyMon(_dyIso(y.getFullYear(), 0, 4)))) / 6048e5); };
const _dyMonth = s => { const t = _dyDate(s); return [_dyIso(t.getFullYear(), t.getMonth(), 1), _dyIso(t.getFullYear(), t.getMonth(), new Date(t.getFullYear(), t.getMonth() + 1, 0).getDate())]; };
const _dySpan = ([a, b]) => Math.round((_dyDate(b) - _dyDate(a)) / 864e5) + 1;
function _dyRangeText([a, b], unit){
  const A = _dyDate(a), B = _dyDate(b), mo = t => _dyMonths[t.getMonth()].slice(0, 3);
  if(unit === "month") return _dyMonths[A.getMonth()] + " " + A.getFullYear();
  const days = A.getFullYear() !== B.getFullYear() ? A.getDate() + " " + mo(A) + " " + A.getFullYear() + " – " + B.getDate() + " " + mo(B) + " " + B.getFullYear()
    : A.getMonth() !== B.getMonth() ? A.getDate() + " " + mo(A) + " – " + B.getDate() + " " + mo(B) + " " + B.getFullYear()
    : a === b ? _dyText(a) : A.getDate() + "–" + B.getDate() + " " + mo(B) + " " + B.getFullYear();
  return unit === "week" ? "Week " + _dyWeekNo(a) + " · " + days : days;
}
export const rsDays = {
  use(el, opts = {}){
    if(!(el instanceof Element)) throw new Error("rs.days.use: give the element that the picker goes in");
    const days = [...(opts.days || [])].sort(); let cur = opts.value || days[days.length - 1] || null, busy = false;
    if(cur && !days.includes(cur)) throw new Error("rs.days.use: the value " + cur + " is not one of the days");
    el.classList.add("rs-day");
    el.innerHTML = '<div class="rs-day-label"></div><div class="rs-day-row">' +
      '<button type="button" class="rs-day-step" data-step="-1" title="The day before" aria-label="The day before">‹</button>' +
      '<button type="button" class="rs-day-field" aria-haspopup="dialog" aria-expanded="false"><span class="rs-day-text"></span>' + _dyCal + _dyChev + '</button>' +
      '<button type="button" class="rs-day-step" data-step="1" title="The day after" aria-label="The day after">›</button>' +
      '<button type="button" class="rs-day-last">Latest</button></div><div class="rs-day-note" hidden></div>';
    const q = s => el.querySelector(s), field = q(".rs-day-field"), note = q(".rs-day-note"), last = q(".rs-day-last");
    const steps = [...el.querySelectorAll(".rs-day-step")];
    q(".rs-day-label").textContent = opts.label || "Day";
    // the calendar: one box for each picker, over the page, with the days that have data as buttons
    const cal = document.createElement("div"); cal.className = "rs-day-cal"; cal.hidden = true; cal.setAttribute("role", "dialog"); cal.setAttribute("aria-label", "Choose a day");
    document.body.appendChild(cal);
    let calY = 0, calM = 0;
    function paint(){
      q(".rs-day-text").textContent = cur ? _dyText(cur) : "—";
      const i = days.indexOf(cur);
      steps[0].disabled = busy || i <= 0; steps[1].disabled = busy || i < 0 || i >= days.length - 1;
      last.disabled = busy || !days.length || cur === days[days.length - 1]; field.disabled = busy || !days.length;
      el.classList.toggle("rs-day-busy", busy);
    }
    function drawCal(){
      const lead = (new Date(calY, calM, 1).getDay() + 6) % 7, n = new Date(calY, calM + 1, 0).getDate(), have = new Set(days);
      const lo = days[0] || "", hi = days[days.length - 1] || "";
      let h = '<div class="rs-day-ch"><button type="button" data-m="-1" aria-label="The month before"' + (_dyIso(calY, calM, 1) <= lo ? " disabled" : "") + ">‹</button>" +
        "<b>" + _dyMonths[calM] + " " + calY + '</b><button type="button" data-m="1" aria-label="The month after"' + (_dyIso(calY, calM, n) >= hi ? " disabled" : "") + ">›</button></div>" +
        '<div class="rs-day-cg">' + ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map(w => '<span class="rs-day-cw">' + w + "</span>").join("") + "<span></span>".repeat(lead);
      for(let d = 1; d <= n; d++){ const k = _dyIso(calY, calM, d);
        h += '<button type="button" class="rs-day-cd' + (k === cur ? " on" : "") + '" data-d="' + k + '"' + (have.has(k) ? "" : " disabled") + ">" + d + "</button>"; }
      cal.innerHTML = h + "</div>";
    }
    function closeCal(){ cal.hidden = true; field.setAttribute("aria-expanded", "false"); }
    function openCal(){
      const t = _dyDate(cur); calY = t.getFullYear(); calM = t.getMonth(); drawCal(); cal.hidden = false; field.setAttribute("aria-expanded", "true");
      const r = field.getBoundingClientRect();
      cal.style.left = Math.max(8, Math.min(innerWidth - cal.offsetWidth - 8, r.left)) + "px";
      cal.style.top = Math.max(8, Math.min(innerHeight - cal.offsetHeight - 8, r.bottom + 6)) + "px";
      (cal.querySelector(".rs-day-cd.on") || cal.querySelector(".rs-day-cd:not(:disabled)"))?.focus();
    }
    function go(d, quiet){
      if(busy || !d || d === cur) return;
      if(!days.includes(d)) throw new Error("rs.days: " + d + " is not one of the days");
      const old = cur; cur = d; note.hidden = true; paint();
      const run = quiet || !opts.onChange ? null : opts.onChange(d);
      if(!run || typeof run.then !== "function") return;
      busy = true; paint();
      run.catch(e => { console.error("rs.days: the page could not change to " + d, e); cur = old; note.textContent = "Could not load " + _dyText(d) + "."; note.hidden = false; })
         .then(() => { busy = false; paint(); });
    }
    field.addEventListener("click", e => { e.stopPropagation(); cal.hidden ? openCal() : closeCal(); });
    steps.forEach(b => b.addEventListener("click", () => go(days[days.indexOf(cur) + +b.dataset.step])));
    last.addEventListener("click", () => go(days[days.length - 1]));
    cal.addEventListener("click", e => {
      e.stopPropagation();
      const b = e.target.closest("button"); if(!b || b.disabled) return;
      if(b.dataset.m){ calM += +b.dataset.m; if(calM < 0){ calM = 11; calY--; } if(calM > 11){ calM = 0; calY++; } drawCal(); return; }
      closeCal(); go(b.dataset.d); field.focus();
    });
    document.addEventListener("click", () => { if(!cal.hidden) closeCal(); });
    document.addEventListener("keydown", e => { if(e.key === "Escape" && !cal.hidden){ closeCal(); field.focus(); } });
    paint();
    return {
      set: (d, quiet) => go(d, quiet),
      value: () => cur,
    };
  },
  range(el, opts = {}){
    if(!(el instanceof Element)) throw new Error("rs.days.range: give the element that the picker goes in");
    const have = opts.days ? new Set(opts.days) : null, sorted = opts.days ? [...opts.days].sort() : [];
    const lo = opts.min || sorted[0] || "1970-01-01", hi = opts.max || sorted[sorted.length - 1] || _dyIso(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
    let unit = opts.unit || "day", cur = null, anchor = null, busy = false, calY = 0, calM = 0;
    const whole = d => unit === "week" ? [_dyMon(d), _dyAdd(_dyMon(d), 6)] : unit === "month" ? _dyMonth(d) : [d, d];
    const fits = ([a, b]) => b >= lo && a <= hi;                         // a period with at least one day in [min, max]
    const can = d => unit === "day" ? d >= lo && d <= hi && (!have || have.has(d)) : fits(whole(d));
    el.classList.add("rs-day", "rs-range");
    el.innerHTML = '<div class="rs-day-label"></div><div class="rs-day-row">' +
      '<button type="button" class="rs-day-step" data-step="-1">‹</button>' +
      '<button type="button" class="rs-day-field" aria-haspopup="dialog" aria-expanded="false"><span class="rs-day-text"></span>' + _dyCal + _dyChev + "</button>" +
      '<button type="button" class="rs-day-step" data-step="1">›</button></div><div class="rs-day-note" hidden></div>';
    const q = s => el.querySelector(s), field = q(".rs-day-field"), note = q(".rs-day-note"), steps = [...el.querySelectorAll(".rs-day-step")];
    const cal = document.createElement("div"); cal.className = "rs-day-cal rs-range-cal"; cal.hidden = true; cal.setAttribute("role", "dialog");
    document.body.appendChild(cal);
    const name = () => ({day: "days", week: "week", month: "month"})[unit];
    function moved(d){                                                   // the period before (-1) or after (1)
      if(unit === "month"){ const t = _dyDate(cur[0]); return _dyMonth(_dyIso(t.getFullYear(), t.getMonth() + d, 1)); }
      const n = unit === "week" ? 7 : _dySpan(cur); return [_dyAdd(cur[0], d * n), _dyAdd(cur[1], d * n)];
    }
    function paint(){
      q(".rs-day-label").textContent = opts.label || ({day: "Days", week: "Week", month: "Month"})[unit];
      q(".rs-day-text").textContent = field.title = cur ? _dyRangeText(cur, unit) : "—";      // the title: the whole text where the field cuts it
      steps.forEach(b => { const d = +b.dataset.step, w = unit === "day" ? "The " + _dySpan(cur) + " days " + (d < 0 ? "before" : "after") : "The " + name() + " " + (d < 0 ? "before" : "after");
        b.title = w; b.setAttribute("aria-label", w); b.disabled = busy || !fits(moved(d)); });
      field.disabled = busy; el.classList.toggle("rs-day-busy", busy);
      cal.setAttribute("aria-label", "Choose the " + name());
    }
    function drawCal(){
      if(unit === "month"){
        let h = '<div class="rs-day-ch"><button type="button" data-y="-1" aria-label="The year before"' + (calY + "-01-01" <= lo ? " disabled" : "") + ">‹</button><b>" + calY +
          '</b><button type="button" data-y="1" aria-label="The year after"' + (calY + "-12-31" >= hi ? " disabled" : "") + '>›</button></div><div class="rs-range-mg">';
        for(let m = 0; m < 12; m++){ const k = _dyIso(calY, m, 1);
          h += '<button type="button" class="rs-day-cd' + (cur && k === cur[0] ? " on" : "") + '" data-d="' + k + '"' + (can(k) ? "" : " disabled") + ">" + _dyMonths[m].slice(0, 3) + "</button>"; }
        cal.innerHTML = h + "</div>"; return;
      }
      const lead = (new Date(calY, calM, 1).getDay() + 6) % 7, n = new Date(calY, calM + 1, 0).getDate();
      const [a, b] = anchor ? [anchor, anchor] : cur || ["", ""];
      let h = '<div class="rs-day-ch"><button type="button" data-m="-1" aria-label="The month before"' + (_dyIso(calY, calM, 1) <= lo ? " disabled" : "") + ">‹</button>" +
        "<b>" + _dyMonths[calM] + " " + calY + '</b><button type="button" data-m="1" aria-label="The month after"' + (_dyIso(calY, calM, n) >= hi ? " disabled" : "") + ">›</button></div>" +
        '<div class="rs-day-cg">' + ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map(w => '<span class="rs-day-cw">' + w + "</span>").join("") + "<span></span>".repeat(lead);
      for(let d = 1; d <= n; d++){ const k = _dyIso(calY, calM, d);
        h += '<button type="button" class="rs-day-cd' + (k === a || k === b ? " on" : k > a && k < b ? " in" : "") + '" data-d="' + k + '"' + (can(k) ? "" : " disabled") + ">" + d + "</button>"; }
      cal.innerHTML = h + "</div>" + (unit === "day" ? '<div class="rs-range-hint">' + (anchor ? "Now click the last day." : "Click the first day, then the last day.") + "</div>" : "");
    }
    // the pointer over a day shows what a click gives: the range from the anchor, or the week of the day
    cal.addEventListener("pointerover", e => {
      const b = e.target.closest(".rs-day-cd"); if(!b || b.disabled || unit === "month" || (unit === "day" && !anchor)) return;
      const [x, y] = unit === "week" ? whole(b.dataset.d) : [anchor, b.dataset.d].sort();
      cal.querySelectorAll(".rs-day-cd").forEach(c => { const k = c.dataset.d; c.classList.toggle("hov", k >= x && k <= y); });
    });
    cal.addEventListener("pointerleave", () => cal.querySelectorAll(".hov").forEach(c => c.classList.remove("hov")));
    function closeCal(){ cal.hidden = true; anchor = null; field.setAttribute("aria-expanded", "false"); }
    function openCal(){
      const t = _dyDate(cur ? cur[0] : hi); calY = t.getFullYear(); calM = t.getMonth(); anchor = null; drawCal(); cal.hidden = false;
      field.setAttribute("aria-expanded", "true"); rsPopAt(cal, field);
      (cal.querySelector(".rs-day-cd.on") || cal.querySelector(".rs-day-cd:not(:disabled)"))?.focus();
    }
    function go(v, quiet){
      if(busy || !v) return;
      v = [...v].sort(); if(cur && v[0] === cur[0] && v[1] === cur[1]) return;
      const old = cur; cur = v; note.hidden = true; paint();
      const run = quiet || !opts.onChange ? null : opts.onChange([...v]);
      if(!run || typeof run.then !== "function") return;
      busy = true; paint();
      run.catch(e => { console.error("rs.days.range: the page could not change to " + v, e); cur = old; note.textContent = "Could not load " + _dyRangeText(v, unit) + "."; note.hidden = false; })
         .then(() => { busy = false; paint(); });
    }
    field.addEventListener("click", e => { e.stopPropagation(); cal.hidden ? openCal() : closeCal(); });
    steps.forEach(b => b.addEventListener("click", () => go(moved(+b.dataset.step))));
    cal.addEventListener("click", e => {
      e.stopPropagation();
      const b = e.target.closest("button"); if(!b || b.disabled) return;
      if(b.dataset.m){ calM += +b.dataset.m; if(calM < 0){ calM = 11; calY--; } if(calM > 11){ calM = 0; calY++; } drawCal(); return; }
      if(b.dataset.y){ calY += +b.dataset.y; drawCal(); return; }
      const d = b.dataset.d;
      if(unit === "day" && !anchor){ anchor = d; drawCal(); cal.querySelector('[data-d="' + d + '"]')?.focus(); return; }
      const v = unit === "day" ? [anchor, d] : whole(d);
      closeCal(); go(v); field.focus();
    });
    rsPopClose(cal, field, closeCal);
    const start = opts.value || (unit === "day" ? [_dyAdd(hi, -6) < lo ? lo : _dyAdd(hi, -6), hi] : whole(hi));
    go(unit === "day" ? start : whole(start[0]), true);
    return {
      value: () => [...cur],
      set: (v, quiet) => go(unit === "day" ? v : whole(v[0]), quiet),
      unit(u){ if(u === undefined) return unit; unit = u; closeCal(); go(u === "day" ? cur : whole(cur[1] > hi ? hi : cur[1]), false); paint(); },
    };
  },
};

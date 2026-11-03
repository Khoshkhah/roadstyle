// The day picker of a page (docs/guides/dashboard-parts.md): a label, a field that shows the day and opens a calendar, the day before and the day
// after, and "Latest". The page gives an empty element and its days, roadstyle builds the rest:
//   const day = rs.days.use(el, {days: ["2026-10-04", "2026-10-05"], value: "2026-10-05", onChange: d => load(d)});
// `days` are the days that have data, as "YYYY-MM-DD": the calendar offers only these, and the arrows step through them. `onChange(day)` can give a
// promise: while it runs, the field pulses and the buttons wait; if it fails, the day goes back and a line under the row says so. It returns
// `{set(day, quiet), value()}`.
const _dyChev = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
const _dyCal = '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5.5 1.5v3M10.5 1.5v3"/></svg>';
const _dyMonths = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const _dyDate = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const _dyIso = (y, m, d) => y + "-" + String(m + 1).padStart(2, "0") + "-" + String(d).padStart(2, "0");
const _dyText = s => { const t = _dyDate(s);    // "Mon 5 Oct 2026", the same in every browser (toLocaleDateString adds a comma in some)
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][t.getDay()] + " " + t.getDate() + " " + _dyMonths[t.getMonth()].slice(0, 3) + " " + t.getFullYear(); };
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
};

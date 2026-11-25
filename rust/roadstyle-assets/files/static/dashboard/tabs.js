// Tabs and the two-way switch of a page (docs/guides/dashboard-parts.md). The page writes the buttons, roadstyle gives the look and the behaviour:
//   <nav class="rs-tabs"><button class="rs-tab on" data-tab="a">A</button> ...</nav>  <div data-pane="a">...</div> <div data-pane="b" hidden>...</div>
//   <div class="rs-seg"><button class="on" data-v="all">All</button><button data-v="one">One</button></div>
// `rs.tabs.use(nav, onChange)` wires one of them: a click or an arrow key selects, the chosen button has `on` and `aria-selected`, and the panes beside
// a `.rs-tabs` (the siblings with `data-pane`) show the one with the same id. It returns `{select(id), current()}`.
// A list of rows that a click selects (`<div class="rs-rows"><button class="rs-row" data-v="12">...</button>...</div>`) uses the same function: the
// selected row has `on` and `aria-selected`, and the up and down arrows walk the rows.
// `rs.toggle(button, onChange)` makes a button that stays pressed (`aria-pressed`) until the next click: {set(on, quiet), value()}.
// The options of a tab row (the attributes of its `nav`, or `rs.tabs.use(nav, onChange, {icons, fill, tint})`, which sets them):
//   data-icons ("inline", or "top": the icon over a smaller label) - each tab's icon before its label: its `data-icon` (a name of TAB_ICONS) or its own
//   first `<svg>`; data-fill - the tabs share the row's width (a label that does not fit keeps its width); data-tint - a tint behind the selected tab.
// outline icons on a 24 px grid in the tab's colour (currentColor), drawn for roadstyle
const _TI = {
  car: '<path d="M5 17H4a1 1 0 0 1-1-1v-4l2-5h12l2 5v4a1 1 0 0 1-1 1h-1M3 12h18M9.5 17h5"/><circle cx="7.5" cy="17" r="2"/><circle cx="16.5" cy="17" r="2"/>',
  gauge: '<path d="M4.5 18a9 9 0 1 1 15 0M12 14l4-5"/><circle cx="12" cy="14" r="1.5"/>',
  volume: '<path d="M4 10v4h4l5 4V6l-5 4zM16.5 9a4 4 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11"/>',
  chart: '<path d="M4 20h16M7 16v-5M12 16V6M17 16V8"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  map: '<path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20zM9 4v13.5M15 6.5V20"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
  road: '<path d="M8 4 5 20M16 4l3 16M12 5v2M12 11v2M12 17v2"/>',
  building: '<path d="M5 20V5l7-2v17M12 8h7v12M3 20h18M8 8h.01M8 12h.01M8 16h.01M15.5 12h.01M15.5 16h.01"/>',
};
export const TAB_ICONS = Object.keys(_TI);
function _tabIcons(nav){
  for(const t of nav.querySelectorAll(":scope > .rs-tab")){
    if(t.querySelector(":scope > .rs-tab-ic")) continue;
    const own = t.firstElementChild;
    if(own && own.tagName.toLowerCase() === "svg"){ own.classList.add("rs-tab-ic"); own.setAttribute("aria-hidden", "true"); }
    else if(t.dataset.icon){
      if(!_TI[t.dataset.icon]) throw new Error("rs.tabs: no icon '" + t.dataset.icon + "' (the icons: " + TAB_ICONS.join(", ") + ")");
      t.insertAdjacentHTML("afterbegin", '<svg class="rs-tab-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
        'stroke-linejoin="round" aria-hidden="true">' + _TI[t.dataset.icon] + "</svg>");
    }
    // the label and its count in one box, so that the icon can go over them ("top")
    const lb = document.createElement("span"); lb.className = "rs-tab-lb";
    for(const n of [...t.childNodes]) if(!(n.classList && n.classList.contains("rs-tab-ic"))) lb.appendChild(n);
    t.appendChild(lb);
  }
}
export const rsTabs = {
  icons: TAB_ICONS,
  use(nav, onChange, opts){
    const isTabs = nav.classList.contains("rs-tabs"), isRows = nav.classList.contains("rs-rows"), idOf = el => el.dataset.tab !== undefined ? el.dataset.tab : el.dataset.v;
    if(opts && isTabs){
      if(opts.icons !== undefined && !["inline", "top", true, false].includes(opts.icons)) throw new Error('rs.tabs.use: icons is "inline", "top", true or false');
      for(const k of ["icons", "fill", "tint"]) if(k in opts){ if(opts[k]) nav.setAttribute("data-" + k, opts[k] === true ? "" : opts[k]); else nav.removeAttribute("data-" + k); }
    }
    if(isTabs && nav.hasAttribute("data-icons")) _tabIcons(nav);
    const items = () => [...nav.querySelectorAll("[data-tab], [data-v]")];
    const [role, itemRole, mark] = isTabs ? ["tablist", "tab", "aria-selected"] : isRows ? ["listbox", "option", "aria-selected"] : ["radiogroup", "radio", "aria-checked"];
    nav.setAttribute("role", role);
    let cur = null;
    function select(id, quiet){
      cur = id;
      for(const it of items()){
        const on = idOf(it) === id;
        it.classList.toggle("on", on); it.setAttribute(mark, on); it.tabIndex = on || (cur === null && it === items()[0]) ? 0 : -1;
        it.setAttribute("role", itemRole);
      }
      if(isTabs && nav.parentElement) for(const p of nav.parentElement.querySelectorAll(":scope > [data-pane]")) p.hidden = p.dataset.pane !== id;
      if(!quiet && onChange) onChange(id);
    }
    nav.addEventListener("click", e => {
      const it = e.target.closest("[data-tab], [data-v]"); if(!it || !nav.contains(it)) return;
      const ctl = e.target.closest("select, input, textarea, .rs-sel, button");
      if(ctl && ctl !== it && it.contains(ctl)) return;         // a control in a row (a select box) does its own work and does not select the row
      select(idOf(it));
    });
    nav.addEventListener("keydown", e => {
      // a row that is not a button (a <div class="rs-row" tabindex="0"> with a select box in it): Enter or Space selects it, as a click on a button
      const own = e.target.closest("[data-tab], [data-v]");
      if((e.key === "Enter" || e.key === " ") && own === e.target && !own.matches("button")){ select(idOf(own)); e.preventDefault(); return; }
      const d = {ArrowRight: 1, ArrowLeft: -1, ArrowDown: 1, ArrowUp: -1}[e.key]; if(!d) return;
      const a = items(), i = a.findIndex(it => idOf(it) === cur);
      const n = a[i < 0 ? 0 : (i + d + a.length) % a.length]; select(idOf(n)); n.focus(); e.preventDefault();
    });
    const first = items().find(it => it.classList.contains("on")) || (isRows ? null : items()[0]);      // a list starts with no row selected
    if(first) select(idOf(first), true); else select(null, true);
    return {select, current: () => cur};
  },
};
export function rsToggle(button, onChange){
  let on = button.getAttribute("aria-pressed") === "true";
  button.classList.add("rs-toggle");
  const set = (v, quiet) => { on = !!v; button.setAttribute("aria-pressed", on); if(!quiet) onChange?.(on); };
  button.addEventListener("click", () => set(!on));
  set(on, true);
  return {set, value: () => on};
}

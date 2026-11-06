// Tabs and the two-way switch of a page (docs/guides/dashboard-panel.md). The page writes the buttons, roadstyle gives the look and the behaviour:
//   <nav class="rs-tabs"><button class="rs-tab on" data-tab="a">A</button> ...</nav>  <div data-pane="a">...</div> <div data-pane="b" hidden>...</div>
//   <div class="rs-seg"><button class="on" data-v="all">All</button><button data-v="one">One</button></div>
// `rs.tabs.use(nav, onChange)` wires one of them: a click or an arrow key selects, the chosen button has `on` and `aria-selected`, and the panes beside
// a `.rs-tabs` (the siblings with `data-pane`) show the one with the same id. It returns `{select(id), current()}`.
// A list of rows that a click selects (`<div class="rs-rows"><button class="rs-row" data-v="12">...</button>...</div>`) uses the same function: the
// selected row has `on` and `aria-selected`, and the up and down arrows walk the rows.
// `rs.toggle(button, onChange)` makes a button that stays pressed (`aria-pressed`) until the next click: {set(on, quiet), value()}.
export const rsTabs = {
  use(nav, onChange){
    const isTabs = nav.classList.contains("rs-tabs"), isRows = nav.classList.contains("rs-rows"), idOf = el => el.dataset.tab !== undefined ? el.dataset.tab : el.dataset.v;
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

// Tabs and the two-way switch of a page (docs/guides/dashboard-panel.md). The page writes the buttons, roadstyle gives the look and the behaviour:
//   <nav class="rs-tabs"><button class="rs-tab on" data-tab="a">A</button> ...</nav>  <div data-pane="a">...</div> <div data-pane="b" hidden>...</div>
//   <div class="rs-seg"><button class="on" data-v="all">All</button><button data-v="one">One</button></div>
// `rs.tabs.use(nav, onChange)` wires one of them: a click or an arrow key selects, the chosen button has `on` and `aria-selected`, and the panes beside
// a `.rs-tabs` (the siblings with `data-pane`) show the one with the same id. It returns `{select(id), current()}`.
export const rsTabs = {
  use(nav, onChange){
    const isTabs = nav.classList.contains("rs-tabs"), idOf = el => el.dataset.tab !== undefined ? el.dataset.tab : el.dataset.v;
    const items = () => [...nav.querySelectorAll("[data-tab], [data-v]")];
    nav.setAttribute("role", isTabs ? "tablist" : "radiogroup");
    let cur = null;
    function select(id, quiet){
      cur = id;
      for(const it of items()){
        const on = idOf(it) === id;
        it.classList.toggle("on", on); it.setAttribute(isTabs ? "aria-selected" : "aria-checked", on); it.tabIndex = on ? 0 : -1;
        it.setAttribute("role", isTabs ? "tab" : "radio");
      }
      if(isTabs && nav.parentElement) for(const p of nav.parentElement.querySelectorAll(":scope > [data-pane]")) p.hidden = p.dataset.pane !== id;
      if(!quiet && onChange) onChange(id);
    }
    nav.addEventListener("click", e => { const it = e.target.closest("[data-tab], [data-v]"); if(it && nav.contains(it)) select(idOf(it)); });
    nav.addEventListener("keydown", e => {
      if(e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const a = items(), i = a.findIndex(it => idOf(it) === cur); if(i < 0) return;
      const n = a[(i + (e.key === "ArrowRight" ? 1 : a.length - 1)) % a.length]; select(idOf(n)); n.focus(); e.preventDefault();
    });
    const first = items().find(it => it.classList.contains("on")) || items()[0];
    if(first) select(idOf(first), true);
    return {select, current: () => cur};
  },
};

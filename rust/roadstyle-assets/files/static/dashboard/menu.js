// A box that opens under a control (docs/design/dashboard_parts_2.md): the action menu, the colour picker's palette, the search field's list and the
// date range's calendar use it. `rsPopAt(box, anchor)` puts the box under the anchor and keeps it inside the window (above the anchor when there is no room
// below); `rsPopClose(box, anchor, close)` calls `close()` on a click outside the box and the anchor, and on Escape (the focus then goes back to the anchor).
export function rsPopAt(box, anchor){
  const r = anchor.getBoundingClientRect();
  box.style.minWidth = Math.min(r.width, innerWidth - 16) + "px";
  const w = box.offsetWidth, h = box.offsetHeight;
  box.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left)) + "px";
  box.style.top = (r.bottom + 6 + h <= innerHeight - 8 ? r.bottom + 6 : Math.max(8, r.top - 6 - h)) + "px";
}
export function rsPopClose(box, anchor, close){
  document.addEventListener("pointerdown", e => { if(!box.hidden && !box.contains(e.target) && !anchor.contains(e.target)) close(); });
  document.addEventListener("keydown", e => { if(e.key === "Escape" && !box.hidden){ close(); anchor.focus(); } });
}
// the keys of a list of buttons (a menu, a palette): the arrows walk, Home and End go to the ends; `cols` > 1 walks a grid
export function rsPopKeys(box, sel, cols = 1){
  box.addEventListener("keydown", e => {
    const a = [...box.querySelectorAll(sel)].filter(b => !b.disabled), i = a.indexOf(document.activeElement);
    const step = {ArrowDown: cols, ArrowUp: -cols, ArrowRight: cols > 1 ? 1 : 0, ArrowLeft: cols > 1 ? -1 : 0}[e.key];
    let n = -1;
    if(step) n = i < 0 ? 0 : Math.max(0, Math.min(a.length - 1, i + step));
    if(e.key === "Home") n = 0;
    if(e.key === "End") n = a.length - 1;
    if(n >= 0 && a[n]){ a[n].focus(); e.preventDefault(); }
  });
}
// The action menu: a "⋯" button (or any button) opens a list of actions.
//   rs.menu(button, [{label: "Rename", onClick}, {label: "Delete", danger: true, onClick}, "-", {label: "Export", disabled: true}])
// A "-" is a line between two groups. `icon` is an SVG string before the label. It returns `{open(), close(), set(items)}`.
// `rs.menu.button(items, title)` makes a new "⋯" button with the menu and gives it back.
const _mnDots = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>';
export function rsMenu(button, items){
  if(!(button instanceof Element)) throw new Error("rs.menu: give the button that opens the menu");
  const box = document.createElement("div"); box.className = "rs-menu"; box.hidden = true; box.setAttribute("role", "menu");
  document.body.appendChild(box);
  button.setAttribute("aria-haspopup", "menu"); button.setAttribute("aria-expanded", "false");
  let list = items || [];
  function draw(){
    box.innerHTML = "";
    list.forEach((it, i) => {
      if(it === "-"){ box.insertAdjacentHTML("beforeend", '<div class="rs-menu-line" role="separator"></div>'); return; }
      const b = document.createElement("button"); b.type = "button"; b.setAttribute("role", "menuitem"); b.dataset.i = i;
      b.className = "rs-menu-item" + (it.danger ? " danger" : ""); b.disabled = !!it.disabled;
      b.innerHTML = (it.icon || "") + "<span></span>"; b.lastChild.textContent = it.label;
      box.appendChild(b);
    });
  }
  function close(){ if(box.hidden) return; box.hidden = true; button.setAttribute("aria-expanded", "false"); }
  function open(){
    draw(); box.hidden = false; button.setAttribute("aria-expanded", "true"); rsPopAt(box, button);
    box.querySelector(".rs-menu-item:not(:disabled)")?.focus();
  }
  button.addEventListener("click", e => { e.stopPropagation(); box.hidden ? open() : close(); });
  button.addEventListener("keydown", e => { if(e.key === "ArrowDown"){ open(); e.preventDefault(); } });
  box.addEventListener("click", e => {
    const b = e.target.closest(".rs-menu-item"); if(!b || b.disabled) return;
    close(); button.focus(); list[+b.dataset.i].onClick?.();
  });
  box.addEventListener("keydown", e => { if(e.key === "Tab") close(); });
  rsPopKeys(box, ".rs-menu-item");
  rsPopClose(box, button, close);
  return {open, close, set(next){ list = next || []; if(!box.hidden) draw(); }};
}
rsMenu.button = (items, title = "More actions") => {
  const b = document.createElement("button"); b.type = "button"; b.className = "rs-more-btn"; b.innerHTML = _mnDots;
  b.setAttribute("aria-label", title); b.title = title;
  rsMenu(b, items);
  return b;
};

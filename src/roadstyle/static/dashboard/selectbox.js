// A select list in the look of the boxes (docs/design/dashboard_templates.md, 3.3). The browser draws a native list itself (corners, highlight and
// background are the system's), so the `<select>` of a panel stays in the page, hidden, and a button and a list take its place. The page's code
// still reads and sets `select.value`, the `change` event, `disabled` and the options: the button follows them. The list is outside the panel, so
// the panel's scroll does not clip it, and its background is the card's (the layer before the text).
const _sbChevron = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
const _sbCheck = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 5 5 9-10"/></svg>';
let _sbOpen = null;                                  // {close}: the list that is open (one at a time)
function _sbEnhance(sel){
  if(sel.dataset.rsSel) return;
  sel.dataset.rsSel = "1";
  const wrap = document.createElement("div"), btn = document.createElement("button"), label = document.createElement("span");
  wrap.className = "rs-sel"; btn.type = "button"; btn.className = "rs-sel-btn"; label.className = "rs-sel-t";
  btn.setAttribute("role", "combobox"); btn.setAttribute("aria-haspopup", "listbox"); btn.setAttribute("aria-expanded", "false");
  btn.append(label); btn.insertAdjacentHTML("beforeend", _sbChevron);
  sel.after(wrap); wrap.append(btn); wrap.append(sel); sel.classList.add("rs-sel-native");
  const text = () => { const o = sel.options[sel.selectedIndex]; return o ? o.textContent : ""; };
  const sync = () => { label.textContent = text(); btn.disabled = sel.disabled; };
  // the page sets `value` and `disabled` from its code: the button follows
  const proto = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
  Object.defineProperty(sel, "value", {get(){ return proto.get.call(sel); }, set(v){ proto.set.call(sel, v); sync(); }});
  const dis = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "disabled") || Object.getOwnPropertyDescriptor(HTMLElement.prototype, "disabled");
  if(dis) Object.defineProperty(sel, "disabled", {get(){ return dis.get.call(sel); }, set(v){ dis.set.call(sel, v); sync(); }, configurable: true});
  sel.addEventListener("change", sync);
  let list = null, at = -1;
  const close = () => {
    if(!list) return;
    list.remove(); list = null; btn.setAttribute("aria-expanded", "false"); _sbOpen = null;
    document.removeEventListener("pointerdown", away, true); document.removeEventListener("keydown", keys, true); removeEventListener("resize", close);
  };
  const away = e => { if(list && !list.contains(e.target) && !btn.contains(e.target)) close(); };
  const pick = i => { sel.selectedIndex = i; sel.dispatchEvent(new Event("change", {bubbles: true})); sync(); close(); btn.focus(); };
  const mark = i => { at = i; [...list.children].forEach((o, k) => o.classList.toggle("on", k === at)); const e = list.children[at]; if(e) e.scrollIntoView({block: "nearest"}); };
  const keys = e => {
    if(!list) return;
    if(e.key === "Escape"){ e.preventDefault(); close(); btn.focus(); }
    else if(e.key === "ArrowDown"){ e.preventDefault(); mark(Math.min(sel.options.length - 1, at + 1)); }
    else if(e.key === "ArrowUp"){ e.preventDefault(); mark(Math.max(0, at - 1)); }
    else if(e.key === "Enter" || e.key === " "){ e.preventDefault(); pick(at); }
    else if(e.key === "Tab") close();
  };
  const open = () => {
    if(sel.disabled) return;
    if(_sbOpen) _sbOpen.close();
    list = document.createElement("div"); list.className = "rs-sel-list"; list.setAttribute("role", "listbox");
    [...sel.options].forEach((o, i) => {
      const row = document.createElement("div");
      row.className = "rs-sel-opt" + (i === sel.selectedIndex ? " sel" : ""); row.setAttribute("role", "option"); row.setAttribute("aria-selected", String(i === sel.selectedIndex));
      const t = document.createElement("span"); t.textContent = o.textContent; row.append(t);
      if(i === sel.selectedIndex) row.insertAdjacentHTML("beforeend", _sbCheck);
      row.onpointerdown = e => e.preventDefault();
      row.onclick = () => pick(i);
      row.onpointerenter = () => mark(i);
      list.append(row);
    });
    document.body.append(list);
    const r = btn.getBoundingClientRect(), room = innerHeight - r.bottom - 12, h = Math.min(list.scrollHeight, 280);
    const up = room < h && r.top > room;                                 // not enough room below: the list opens upward
    Object.assign(list.style, {left: r.left + "px", width: r.width + "px", maxHeight: Math.min(280, (up ? r.top : room) - 4) + "px"});
    if(up) list.style.bottom = (innerHeight - r.top + 4) + "px"; else list.style.top = (r.bottom + 4) + "px";
    btn.setAttribute("aria-expanded", "true"); mark(sel.selectedIndex);
    _sbOpen = {close};
    document.addEventListener("pointerdown", away, true); document.addEventListener("keydown", keys, true); addEventListener("resize", close);
  };
  btn.onclick = () => list ? close() : open();
  btn.addEventListener("keydown", e => { if(!list && (e.key === "ArrowDown" || e.key === "ArrowUp")){ e.preventDefault(); open(); } });
  sync();
}
// every select of a panel (the dashboard sidebar, the docked panel, a host panel)
export function initSelectBox(){
  const run = () => document.querySelectorAll("#sb select, .rs-side select, .rs-host select").forEach(_sbEnhance);
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
  document.addEventListener("rs:sectionchange", run);          // a section that the page adds (rs.sections, the typed `panel.sections`) can have a select: the same list as the others
}

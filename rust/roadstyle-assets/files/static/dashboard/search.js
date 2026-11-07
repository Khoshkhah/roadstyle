// The search field of a page (docs/design/dashboard_parts_2.md): a magnifier, the text, a clear button, an optional button at the end, and a list of
// suggestions that the arrow keys walk.
//   const s = rs.search(el, {placeholder: "Find a place", button: "Go", end: toggleButton,
//     suggest: q => fetch(url + q).then(r => r.json()).then(a => a.map(p => ({label: p.name, sub: p.country, value: p}))),
//     onPick: item => fly(item.value), onSubmit: q => find(q)});
// `suggest(text)` gives an array (or a promise of one) of {label, sub, value}; the list shows it under the field. Enter picks the marked row, or
// calls onSubmit(text) when no row is marked; the end button calls onSubmit too. `end` is an element (an icon button, for example a rs.toggle) that goes
// inside the field at its right end, after the clear button and before the end button; the page keeps its events. Escape closes the list, a second Escape clears the text.
// It returns {value(), set(text), focus(), clear()}.
import {rsPopAt, rsPopClose} from "./menu.js";
const _srIcon = '<svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="7" cy="7" r="4.8"/><path d="m10.6 10.6 3.6 3.6"/></svg>';
let _srN = 0;
export function rsSearch(el, opts = {}){
  if(!(el instanceof Element)) throw new Error("rs.search: give the element that the field goes in");
  const id = "rs-search-" + (++_srN);
  el.classList.add("rs-search");
  el.innerHTML = '<div class="rs-search-box"><span class="rs-search-i">' + _srIcon + '</span>' +
    '<input type="search" autocomplete="off" spellcheck="false" role="combobox" aria-autocomplete="list" aria-expanded="false">' +
    '<button type="button" class="rs-search-x" aria-label="Clear" hidden>×</button>' +
    (opts.button ? '<button type="button" class="rs-search-go"></button>' : "") + "</div>";
  const box = el.querySelector(".rs-search-box"), inp = el.querySelector("input"), x = el.querySelector(".rs-search-x"), go = el.querySelector(".rs-search-go");
  inp.placeholder = opts.placeholder || "Search"; inp.setAttribute("aria-label", opts.label || inp.placeholder);
  if(go) go.textContent = opts.button;
  if(opts.end instanceof Element){ opts.end.classList.add("rs-search-end"); x.after(opts.end); }
  else if(opts.end != null) throw new Error("rs.search: end is an element (a button) that goes inside the field");
  const list = document.createElement("div"); list.className = "rs-search-list"; list.id = id; list.hidden = true; list.setAttribute("role", "listbox");
  inp.setAttribute("aria-controls", id);
  document.body.appendChild(list);
  let items = [], mark = -1, ask = 0, timer = 0;
  function close(){ list.hidden = true; inp.setAttribute("aria-expanded", "false"); inp.removeAttribute("aria-activedescendant"); mark = -1; }
  function draw(note){
    list.innerHTML = note ? '<div class="rs-search-note"></div>' : items.map((it, i) => '<div class="rs-search-opt" role="option" id="' + id + "-" + i +
      '" data-i="' + i + '"><b></b><span></span></div>').join("");
    if(note) list.firstChild.textContent = note;
    else items.forEach((it, i) => { const r = list.children[i]; r.firstChild.textContent = it.label; r.lastChild.textContent = it.sub || ""; });
    list.hidden = false; inp.setAttribute("aria-expanded", "true"); rsPopAt(list, box);
  }
  function walk(i){
    mark = i;
    [...list.querySelectorAll(".rs-search-opt")].forEach((r, k) => { r.classList.toggle("on", k === i); r.setAttribute("aria-selected", k === i); });
    const r = list.children[i]; if(r){ inp.setAttribute("aria-activedescendant", r.id); r.scrollIntoView({block: "nearest"}); }
  }
  function pick(i){ const it = items[i]; if(!it) return; inp.value = it.label; paint(); close(); opts.onPick?.(it); }
  const paint = () => { x.hidden = !inp.value; };
  async function run(){
    const q = inp.value.trim(), n = ++ask;
    if(!q || !opts.suggest){ close(); return; }
    el.classList.add("rs-search-busy");
    try{
      const got = await opts.suggest(q);
      if(n !== ask) return;                                  // a newer text is on its way
      items = (got || []).slice(0, opts.max || 8); mark = -1;
      items.length ? draw() : draw(opts.none || "No match for “" + q + "”");
    }catch(e){ if(n === ask){ items = []; draw("The search did not work."); console.error("rs.search", e); } }
    finally{ if(n === ask) el.classList.remove("rs-search-busy"); }
  }
  inp.addEventListener("input", () => { paint(); clearTimeout(timer); timer = setTimeout(run, opts.wait ?? 200); });
  inp.addEventListener("keydown", e => {
    const n = items.length, open = !list.hidden && n;
    if(e.key === "ArrowDown" || e.key === "ArrowUp"){
      if(!open){ run(); e.preventDefault(); return; }
      walk(((mark < 0 && e.key === "ArrowUp" ? 0 : mark) + (e.key === "ArrowDown" ? 1 : -1) + n) % n); e.preventDefault();
    }else if(e.key === "Enter"){
      e.preventDefault();
      if(open && mark >= 0) pick(mark); else{ close(); opts.onSubmit?.(inp.value.trim()); }
    }else if(e.key === "Escape"){
      if(!list.hidden) close(); else if(inp.value){ inp.value = ""; paint(); }
      e.preventDefault(); e.stopPropagation();
    }
  });
  list.addEventListener("pointerdown", e => e.preventDefault());       // the field keeps the focus
  list.addEventListener("click", e => { const r = e.target.closest(".rs-search-opt"); if(r) pick(+r.dataset.i); });
  x.addEventListener("click", () => { inp.value = ""; paint(); close(); inp.focus(); opts.onClear?.(); });
  go?.addEventListener("click", () => { close(); opts.onSubmit?.(inp.value.trim()); });
  rsPopClose(list, el, close);
  return {value: () => inp.value, set(t){ inp.value = t || ""; paint(); }, focus: () => inp.focus(), clear(){ inp.value = ""; paint(); close(); }};
}

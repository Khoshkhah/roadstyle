// "Show more" of a long list (docs/design/dashboard_parts_2.md): the list shows its first rows, and a line under it says how many there are and
// adds the next page on a click.
//   const l = rs.more(el, {items: roads, page: 50, render: r => `<div class="rs-qrow"><b>${r.name}</b><span>${r.km} km</span></div>`});
//   l.set(otherRoads);       // a new list: the first page again
// `render(item)` gives an element or HTML. `noun` names the rows in the line ("roads": "50 of 134 roads"). It returns {set(items), shown()}.
export function rsMore(el, opts = {}){
  if(!(el instanceof Element)) throw new Error("rs.more: give the element that the list goes in");
  const page = opts.page || 50, noun = opts.noun || "rows";
  let items = [], n = 0;
  const list = document.createElement("div"), line = document.createElement("div");
  list.className = "rs-more-list"; line.className = "rs-more";
  el.replaceChildren(list, line);
  function add(){
    const end = Math.min(items.length, n + page);
    for(const it of items.slice(n, end)){ const r = opts.render(it); r instanceof Node ? list.appendChild(r) : list.insertAdjacentHTML("beforeend", r); }
    n = end;
    const left = items.length - n;
    line.hidden = !items.length;
    line.innerHTML = '<span class="rs-more-n"></span>' + (left ? '<button type="button" class="rs-more-b"></button>' : "");
    line.firstChild.textContent = (left ? n + " of " : "All ") + items.length + " " + noun;
    if(left) line.lastChild.textContent = "Show " + Math.min(page, left) + " more";
  }
  line.addEventListener("click", e => { if(e.target.closest(".rs-more-b")){ add(); line.querySelector(".rs-more-b")?.focus(); } });
  function set(next){ items = [...(next || [])]; n = 0; list.innerHTML = ""; add(); }
  set(opts.items);
  return {set, shown: () => n};
}

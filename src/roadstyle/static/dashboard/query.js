// The part "query" (docs/guides/dashboard-panel.md): a WHERE clause over the roads' columns, with Run, Filter, Colour and Reset, and the
// list of the matching roads (a click on a name selects the road and flies to it). A page adds it with `{id, part: "query", text}`.
import {_esc} from "../popup.js";
// let SQL habits work: AND/OR/NOT, True/False, and a single = become their JS equivalents
function _qSqlish(s){
  return s.replace(/\bAND\b/gi, " && ").replace(/\bOR\b/gi, " || ").replace(/\bNOT\b/gi, " !")
          .replace(/\bTrue\b/g, "true").replace(/\bFalse\b/g, "false")
          .replace(/([^=!<>&|])=([^=])/g, "$1==$2");   // p.oneway = True  ->  ==  (>=, <=, == untouched)
}
// the part's element: the box, its buttons, the count and the list
export function queryPart(spec){
  const w = document.createElement("div"); w.className = "rs-query";
  w.innerHTML = '<input class="rs-q" spellcheck="false" placeholder="p.maxspeed_kmh >= 50 AND p.oneway = True"' +
    ' title="SQL-style (AND / OR / NOT / = / True) or plain JS (&& / || / ! / === / true); Enter runs it">' +
    '<div class="sb-actions"><button type="button" class="sb-primary" data-q="run">Run</button><button type="button" data-q="filter">Filter</button>' +
    '<button type="button" data-q="color">Colour</button><input type="color" class="rs-q-col" value="#7c4dff" title="colour for the query set">' +
    '<button type="button" data-q="reset">Reset</button></div><div class="rs-q-count"></div><div class="rs-q-list"></div>';
  const q = w.querySelector(".rs-q"), count = w.querySelector(".rs-q-count"), list = w.querySelector(".rs-q-list");
  q.value = spec.text || "";
  let ids = [];
  const run = () => {
    let fn;
    try { fn = new Function("p", "return (" + _qSqlish(q.value) + ")"); }
    catch(e){ count.textContent = "bad query: " + e.message; return; }
    ids = window.rsQuery(p => { try { return fn(p); } catch(e){ return false; } });
    count.textContent = ids.length + " edges match";
    const props = window.rsGetProps(ids), seen = new Set();
    const rows = ids.map((id, k) => ({id, p: props[k]})).filter(r => r.p.name && !seen.has(r.p.name) && seen.add(r.p.name)).slice(0, 30);
    list.innerHTML = rows.map(r => '<div><a href="#" data-id="' + r.id + '">' + _esc(r.p.name) + "</a></div>").join("");
  };
  list.onclick = e => {
    const a = e.target.closest("a[data-id]"); if(!a) return;
    e.preventDefault(); window.rsSelect(+a.dataset.id); window.rsFocus(+a.dataset.id);   // select AND fly the camera to it
  };
  q.onkeydown = e => { if(e.key === "Enter") run(); };
  const act = {run, filter: () => window.rsFilter(ids), color: () => window.rsColor(ids, w.querySelector(".rs-q-col").value),
    reset: () => { window.rsFilter(null); window.rsColor(null); window.rsHighlight([]); window.rsDeselect(); ids = []; list.innerHTML = ""; count.textContent = ""; }};
  w.querySelector(".sb-actions").onclick = e => { const b = e.target.closest("button[data-q]"); if(b) act[b.dataset.q](); };
  return w;
}

// The tool `roads` (docs/design/dashboard_templates.md, 3.2): the road filter in the bar. One box with a row for each road class of the page (a check box, the class's
// colour, its name and the number of roads), All and None, and the rows of Bridges, Tunnels and the restricted kinds when the data has them. A click on a name shows only that class.
// It calls the filter calls of the page (rsSetClasses, rsSetBridges, ...), so the map template's Roads box and this tool are one filter.
import {O, RoadTable} from "./core.js";
import {replaceTool, greyTool, getTool, wrap, ROADS_ICON} from "./tools.js";
import {FILTER, rsSetClasses, rsSetBridges, rsSetTunnels, rsSetAccess} from "./filter.js";
import {_esc} from "../popup.js";

let _rdVis = null;                      // the classes that show now (null: all); kept from the event rs:filterchange
let _rdBox = null;                      // {box, fill}
const _rdClasses = () => (FILTER && FILTER.classes) || [];
// the number of roads of each class: one pass over the road table, at each opening (a new style has a new table)
function _rdCounts(){
  const n = RoadTable.rows && RoadTable.rows(), col = FILTER.col;
  if(!n || !col) return null;
  const out = {};
  for(let i = 0; i < n; i++){ const c = (RoadTable.props(i) || {})[col]; if(c != null) out[c] = (out[c] || 0) + 1; }
  return out;
}
export function useRoadsBox(){
  if(!(O.dashboard && O.dashboard.toolbar)) return;
  const want = _rdClasses().length > 0, has = getTool("roads") && !getTool("roads").disabled;
  if(!want){ _rdBox = null; if(has) greyTool("roads"); return; }
  if(has) return;
  const b = document.createElement("button"), d = wrap(b), box = document.createElement("div");
  b.type = "button"; b.title = "Roads: show and hide road types"; b.innerHTML = ROADS_ICON;
  d.classList.add("rs-roads-ctrl"); box.id = "rs-roads-box"; box.hidden = true; d.appendChild(box);
  const fill = () => {
    const cls = _rdClasses(), sw = FILTER.swatches || {}, cnt = _rdCounts(), on = c => !_rdVis || _rdVis.has(c);
    const grade = [["bridges", "Bridges", rsSetBridges], ["tunnels", "Tunnels", rsSetTunnels]].filter(r => FILTER[r[0]]);
    const acc = FILTER.access || [];
    box.innerHTML = '<div class="rs-bm-h">Roads</div><div class="rs-rd-bar"><button type="button" data-a="all">All</button><button type="button" data-a="none">None</button></div><div class="rs-rd-list">' +
      cls.map(c => '<label class="rs-rd-row"><input type="checkbox" data-c="' + _esc(c) + '"' + (on(c) ? " checked" : "") + '><i style="background:' + _esc(sw[c] || "#888") + '"></i>' +
        '<button type="button" data-only="' + _esc(c) + '" title="Show only ' + _esc(c) + '">' + _esc(c) + "</button><b>" + (cnt && cnt[c] != null ? cnt[c].toLocaleString() : "") + "</b></label>").join("") + "</div>" +
      (grade.length || acc.length ? "<hr>" : "") +
      grade.map(r => '<label class="rs-rd-row rs-rd-plain"><input type="checkbox" data-g="' + r[0] + '" checked><span>' + r[1] + "</span></label>").join("") +
      acc.map(a => '<label class="rs-rd-row"><input type="checkbox" data-k="' + _esc(a[0]) + '" checked><i style="background:' + _esc(a[1]) + '"></i><span>' + _esc(a[2]) + "</span><b>" + (a[3] != null ? a[3].toLocaleString() : "") + "</b></label>").join("");
    const checked = () => cls.filter(c => box.querySelector('input[data-c="' + CSS.escape(c) + '"]').checked);
    box.querySelectorAll("input[data-c]").forEach(i => { i.onchange = () => rsSetClasses(checked()); });
    box.querySelectorAll("button[data-only]").forEach(x => { x.onclick = () => rsSetClasses([x.dataset.only]); });
    box.querySelectorAll("button[data-a]").forEach(x => { x.onclick = () => rsSetClasses(x.dataset.a === "all" ? cls : []); });
    box.querySelectorAll("input[data-g]").forEach(i => { i.onchange = () => (i.dataset.g === "bridges" ? rsSetBridges : rsSetTunnels)(i.checked); });
    box.querySelectorAll("input[data-k]").forEach(i => { i.onchange = () => rsSetAccess(i.dataset.k, i.checked); });
  };
  const open = () => { fill(); box.hidden = false; };
  b.onclick = e => { e.stopPropagation(); box.hidden ? open() : (box.hidden = true); };
  box.addEventListener("click", e => e.stopPropagation());                 // a click inside the box does not close it
  _rdBox = {box, fill};
  replaceTool("roads", "box", d, {title: b.title, open, close: () => { box.hidden = true; }, isOpen: () => !box.hidden});
}
export function initRoadsBox(){
  // the classes that show: from the page's own calls too (rsSetClasses, the Roads box of the map template, a script)
  document.addEventListener("rs:filterchange", e => {
    const v = e.detail && e.detail.visible;
    if(Array.isArray(v)){ _rdVis = new Set(v); if(_rdBox && !_rdBox.box.hidden) _rdBox.fill(); }
  });
  useRoadsBox();
}

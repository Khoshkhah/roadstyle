// The tool `roads` (docs/design/dashboard_templates.md, 3.2): the road filter in the bar. One box with a row for each road class of the page (a check box, the class's
// colour, its name and the number of roads), All and None, and the rows of Bridges, Tunnels and the restricted kinds when the data has them. A click on a name shows only that class.
// It calls the filter calls of the page (rsSetClasses, rsSetBridges, ...), so the map template's Roads box and this tool are one filter.
import {O, RoadTable} from "./core.js";
import {replaceTool, greyTool, getTool, wrap, ROADS_ICON} from "./tools.js";
import {FILTER, rsSetClasses, rsSetBridges, rsSetTunnels, rsSetAccess} from "./filter.js";
import {_esc} from "../popup.js";
import {rsSetBridges3D, _bmHas, rsBridgeGroups, rsSetBridgeHeight, rsSetBridgeNode, rsBridgeProfile} from "./bridgemesh.js";

let _rdVis = null;                      // the classes that show now (null: all); kept from the event rs:filterchange
let _rdBox = null;                      // {box, fill}
let _rdBridge = null;                   // the group of 3D bridges that is selected (its number, from rsBridgeGroups), or null
const _rdClasses = () => (FILTER && FILTER.classes) || [];
// the number of roads of each class: one pass over the road table, at each opening (a new style has a new table)
function _rdCounts(){
  const n = RoadTable.rows && RoadTable.rows(), col = FILTER.col;
  if(!n || !col) return null;
  const out = {};
  for(let i = 0; i < n; i++){ const c = (RoadTable.props(i) || {})[col]; if(c != null) out[c] = (out[c] || 0) + 1; }
  return out;
}
// THE HEIGHT OF THE SELECTED BRIDGE: when a 3D bridge is selected (a click on its deck, or a road of it selected by a call), the box under the row "3D bridges" has its height in metres.
// One number for the whole group of bridges that touch each other (rsSetBridgeHeight); Reset gives the height that the group's length gives (or the page's bridge_heights).
function _rdHeightBlock(){
  if(_rdBridge == null || !rsSetBridges3D()) return "";
  const g = rsBridgeGroups().find(x => x.group === _rdBridge);
  if(!g) return "";
  const n = g.roads.length;
  return '<div class="rs-rd-bh"><span>Height</span><input type="number" data-bh min="0" max="500" step="0.5" value="' + (Math.round(g.height * 10) / 10) + '" aria-label="Height of the selected bridge, in metres"><u>m</u>' +
    '<button type="button" data-bh-reset' + (g.set ? "" : " disabled") + '>Reset</button></div>' +
    '<div class="rs-rd-bhn">One height for the ' + n + (n === 1 ? " road" : " roads") + ' of this bridge that touch each other.</div>' + _rdNodes(g);
}
// the nodes of the group, from the bridge profile: a row for each with its height in metres (a number to change: rsSetBridgeNode) and where the height comes from (`given`: a person;
// `rule`, `data`: the engine; `page`: set in this page). A group that the person set is drawn at its height, so each node shows the profile's height times (height now / the top of its chain).
// Reset nodes gives the profile's heights back. Copy profile puts the profile with these heights on the clipboard, to give to `bridge_profile=` for the exact pieces.
function _rdNodes(g){
  if(!g.nodes.length) return "";
  const top = id => { const c = g.chains.find(c => c.from === id || c.to === id); return c && c.top_m ? c.top_m : null; };
  const z = nd => Math.round(nd.z_m * (g.set && top(nd.id) ? g.height / top(nd.id) : 1) * 10) / 10;
  const rows = g.nodes.map(nd => '<div class="rs-rd-bh rs-rd-bn" data-node="' + _esc(nd.id) + '"><span>' + _esc(nd.id) + '</span><input type="number" data-bn="' + _esc(nd.id) + '" min="0" max="500" step="0.5" value="' + z(nd) +
    '" aria-label="Height of the node ' + _esc(nd.id) + ', in metres"><u>m</u><em>' + _esc(nd.source) + "</em></div>").join("");
  return '<div class="rs-rd-bhn">Nodes: the height at each end of a bridge road. Change one and the roads that meet there are drawn again.</div>' + rows +
    '<div class="rs-rd-bar rs-rd-bnbar"><button type="button" data-bn-reset' + (g.nodesSet.length ? "" : " disabled") + '>Reset nodes</button><button type="button" data-bn-copy>Copy profile</button></div>';
}
// Copy profile: the profile with the heights of this page on the clipboard. A browser that does not allow it (a page that is not on https or localhost) says so on the button.
function _rdCopyProfile(btn){
  const text = JSON.stringify(rsBridgeProfile(), null, 1);
  const done = ok => { btn.textContent = ok ? "Copied" : "Not copied: use rsBridgeProfile()"; setTimeout(() => { btn.textContent = "Copy profile"; }, 2500); };
  if(!navigator.clipboard) return done(false);
  navigator.clipboard.writeText(text).then(() => done(true), () => done(false));
}
// the group of the bridge that a selection is: a deck (its properties have the group) or a road of a bridge (its row is in a group)
function _rdGroupOf(d){
  const p = (d && d.properties) || {};
  if(p.__rs_group != null) return +p.__rs_group;
  const g = d && d.id != null && !d.item && p.lvl > 0 ? rsBridgeGroups().find(x => x.roads.includes(d.id)) : null;      // a road with a level of 1 or more: a bridge
  return g ? g.group : null;
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
      grade.map(r => '<label class="rs-rd-row rs-rd-plain"><input type="checkbox" data-g="' + r[0] + '" checked><span>' + r[1] + "</span></label>" +
        (r[0] === "bridges" && _bmHas() ? '<label class="rs-rd-row rs-rd-plain"><input type="checkbox" data-b3d' + (rsSetBridges3D() ? " checked" : "") + '><span>3D bridges</span></label>' + _rdHeightBlock() : "")).join("") +
      acc.map(a => '<label class="rs-rd-row"><input type="checkbox" data-k="' + _esc(a[0]) + '" checked><i style="background:' + _esc(a[1]) + '"></i><span>' + _esc(a[2]) + "</span><b>" + (a[3] != null ? a[3].toLocaleString() : "") + "</b></label>").join("");
    const checked = () => cls.filter(c => box.querySelector('input[data-c="' + CSS.escape(c) + '"]').checked);
    box.querySelectorAll("input[data-c]").forEach(i => { i.onchange = () => rsSetClasses(checked()); });
    box.querySelectorAll("button[data-only]").forEach(x => { x.onclick = () => rsSetClasses([x.dataset.only]); });
    box.querySelectorAll("button[data-a]").forEach(x => { x.onclick = () => rsSetClasses(x.dataset.a === "all" ? cls : []); });
    box.querySelectorAll("input[data-b3d]").forEach(i => { i.onchange = () => rsSetBridges3D(i.checked); });
    box.querySelectorAll("input[data-bh]").forEach(i => { i.onchange = () => { const v = parseFloat(i.value); if(v >= 0) rsSetBridgeHeight(_rdBridge, v); else _rdBox.fill(); }; });
    box.querySelectorAll("button[data-bh-reset]").forEach(x => { x.onclick = () => rsSetBridgeHeight(_rdBridge, null); });
    box.querySelectorAll("input[data-bn]").forEach(i => { i.onchange = () => { const v = parseFloat(i.value); if(v >= 0) rsSetBridgeNode(i.dataset.bn, v); else _rdBox.fill(); }; });
    box.querySelectorAll("button[data-bn-reset]").forEach(x => { x.onclick = () => { const g = rsBridgeGroups().find(y => y.group === _rdBridge); if(g) g.nodesSet.forEach(id => rsSetBridgeNode(id, null)); }; });
    box.querySelectorAll("button[data-bn-copy]").forEach(x => { x.onclick = () => _rdCopyProfile(x); });
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
  // the selected bridge: its group, for the height box (the box is made again when it is open)
  const again = () => { if(_rdBox && !_rdBox.box.hidden) _rdBox.fill(); };
  document.addEventListener("rs:select", e => { const g = _rdGroupOf(e.detail); if(g !== _rdBridge){ _rdBridge = g; again(); } });
  document.addEventListener("rs:deselect", () => { if(_rdBridge != null){ _rdBridge = null; again(); } });
  document.addEventListener("rs:bridgeheightchange", again);
  document.addEventListener("rs:bridges3dchange", again);
  useRoadsBox();
}

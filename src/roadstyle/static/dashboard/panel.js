// panel mode: a full-height side panel hosts the map controls (colour-by, road filter, legend,
// host tools) and the selected road's record. Built BEFORE the controls, so they mount into it.
import {_esc} from "../popup.js";
import {map, O} from "./core.js";
import {_findWire} from "./find.js";
import {rsDeselect} from "./select.js";
export let _popupMode = "popup";       // "popup" (floating) or "panel" (full-height side panel)
export let _sideBd=null, _sideCtl=null;
let _sideTab=null, _hostEl=null, _hostKey="", _sideEl=null;
export function rsPanelShow(on){                      // hide/unhide the whole panel; the map takes the space
  if(!_sideEl) return;
  document.body.classList.toggle("rs-side-hidden", !on);
  if(_sideTab) _sideTab.style.display = on ? "none" : "block";
  if(_hostEl) try{ localStorage.setItem(_hostKey, on ? "1" : "0"); }catch(e){}
  try{ map.resize(); }catch(e){}
}
function _sideInit(){
  if(_sideBd || _popupMode!=="panel") return;
  document.body.classList.add("rs-panel");
  const sd=document.createElement("div"); sd.className="rs-side"; _sideEl=sd;
  sd.innerHTML='<div class="rs-side-hd"><span>'+_esc(document.title||"Map")+'</span>'+
    '<span class="rs-side-min" title="Hide panel">&raquo;</span></div>'+
    '<div class="rs-side-q"><input type="search" placeholder="Search roads\u2026" spellcheck="false">'+
    '<div class="rs-side-q-res"></div></div>'+
    '<div class="rs-side-ctl"></div><div class="rs-side-tools"></div>'+
    '<div class="rs-side-hd rs-side-hd2"><span>Selected road</span>'+
    '<span class="rs-side-x" title="Clear selection">×</span></div>'+
    '<div class="rs-side-bd"></div>';
  document.body.appendChild(sd);
  sd.querySelector(".rs-side-x").onclick=()=>{ rsDeselect(); };
  sd.querySelector(".rs-side-min").onclick=()=>{ rsPanelShow(false); };
  _sideBd=sd.querySelector(".rs-side-bd");
  _sideCtl=sd.querySelector(".rs-side-ctl");
  _findWire(sd.querySelector(".rs-side-q input"), sd.querySelector(".rs-side-q-res"));
  rsInfoClear();
  try{ map.resize(); }catch(e){}               // #map just lost 320px to the panel
}
export function initPanel(){
  _popupMode = O.popup_mode || "popup";
  _hostEl=document.querySelector(".rs-host"); _hostKey="rs-host-panel:"+location.pathname;   // side_panel_html: the host page's own panel (docs/design/sensor_matching_requests.md)
  _sideEl=_hostEl;
  window.rsPanelShow = rsPanelShow;
  _sideInit();
}
// the host panel's hide button, and the button that shows a hidden panel again
export function initPanelTab(){
  if(_hostEl){ _hostEl.querySelector(".rs-side-min").onclick=()=>{ rsPanelShow(false); }; }
  if(_popupMode==="panel" || _hostEl){    // panel-reopen button: same chrome as 2D, right below it in the stack
    map.addControl({onAdd(){
      const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
      const b=document.createElement("button"); b.type="button";
      b.style.cssText="font:700 14px/1 system-ui";
      b.textContent="\u00ab"; b.title="Show panel";
      b.onclick=()=>{ rsPanelShow(true); };
      _sideTab=d; d.style.display="none";
      d.appendChild(b); return d;
    }, onRemove(){}});
  }
  if(_hostEl){ let on=innerWidth>700; try{ const v=localStorage.getItem(_hostKey); if(v!=null) on=v==="1"; }catch(e){} if(!on) rsPanelShow(false); }   // remembered per page; a narrow screen starts closed
}
export function rsInfoClear(){ if(_sideBd) _sideBd.innerHTML='<div class="rs-empty">Click a road to see its full record here.</div>'; }
export function rsInfoShow(html){ if(_sideBd) _sideBd.innerHTML=html; }
// non-panel: one top-left stack hosts the colour-by + filter cards (panel mode docks them instead)
// the controls' parts: an element with a class; a box with a header and a body (cls-hd, cls-body) that folds when the header is clicked
// (folded: true or false, the start; null: it does not fold); a checkbox row (o: id, cls, rule: the first row of a group, ruled off;
// sw: a swatch of this colour, swCls its class)
export const _el = (tag, cls) => { const e = document.createElement(tag); if(cls) e.className = cls; return e; };
export function _box(cls, pre, title, folded){
  const box = _el("div", cls), hd = _el("div", pre+"-hd"), body = _el("div", pre+"-body");
  const set = c => { box.classList.toggle("collapsed", c); hd.textContent = title+" "+(c ? "▸" : "▾"); };
  if(folded == null) hd.textContent = title; else { set(folded); hd.onclick = () => set(!box.classList.contains("collapsed")); }
  box.append(hd, body);
  return {box, hd, body};
}
export function _check(text, on, change, o = {}){
  const lab = _el("label", o.cls), cb = _el("input"), sw = o.sw != null ? _el("span", o.swCls || "flt-sw") : null;
  cb.type = "checkbox"; cb.checked = on; if(o.id) cb.id = o.id;
  cb.onchange = () => change(cb.checked);
  if(o.rule) lab.classList.add("rs-rule");
  lab.append(cb);
  if(sw){ sw.style.background = o.sw; lab.append(sw); }
  lab.append(" "+text);
  return {lab, cb, sw};
}
export function _tlHost(){
  if(_sideCtl) return _sideCtl;
  let h=document.getElementById("rs-tl");
  if(!h){ h=document.createElement("div"); h.className="rs-tl"; h.id="rs-tl"; document.body.appendChild(h); }
  return h;
}

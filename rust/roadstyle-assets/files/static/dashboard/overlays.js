// extra overlay layers (zones / POIs / lines): click an interactive overlay -> popup of its
// fields; a Layers control toggles each overlay's visibility. Click precedence follows the
// visual stacking: "over" overlays (in front of the roads) win, then roads, then "under"
// overlays (zone fills) — and a selected road also reports the interactive overlays under the
// click (rs:select detail.overlays), so a sidebar can show the road AND its zone together.
import {POPUP, _rfields, _esc} from "../popup.js";
import {map, O, OVERLAYS, _emit} from "./core.js";
import {getTool} from "./tools.js";
import {_popupMode, rsInfoShow, _tlHost, _box, _check} from "./panel.js";
import {rsDeselect, _rrows, _TIP_DELAY} from "./select.js";
let _OV_POPUP = true;       // overlay_popup=False: no overlay shows a popup (an Overlay's popup_window=False: that one); a click still selects and fires rs:select
export const _ovWin = ov => ov.popup_window!==false && _OV_POPUP;
export let _ovSel=null, _ovHov=null, _ovUnder=null, _ovT=0;      // {source,id} of the selected / lit (hovered) overlay feature; the one under the mouse now
function _ovState(ref, st){ if(ref) map.setFeatureState({source:ref.source, id:ref.id}, st); }
export function clearOvSel(){ _ovState(_ovSel,{select:false}); _ovSel=null; }
// the interactive overlay features at a screen point: [{label, fields, properties}] — one entry
// per overlay (its topmost hit). Feeds rs:select's `overlays` payload and the popup/panel.
// A layer's popup fields are not in its tiles: its props file (roadstyle:interaction.base_props, by source) holds them by row, the feature id.
const _ovRows = {};
function _ovFetch(ov){ if(ov.props && !_ovRows[ov.props]) fetch(ov.props).then(r=>r.json()).then(j=>{ _ovRows[ov.props] = j; }, ()=>{}); }
const _ovProps = (ov, f) => ({...f.properties, ...(_ovRows[ov.props] || [])[f.id]});
export function _ovAt(pt){
  const out=[];
  for(const ov of OVERLAYS){
    if(!ov.interactive) continue;
    const ids = ov.layers.filter(id=>map.getLayer(id));
    const hits = ids.length ? map.queryRenderedFeatures(pt, {layers:ids}) : [];
    if(hits.length) out.push({label:ov.label, fields:ov.popup, properties:_ovProps(ov, hits[0]), shown:_ovWin(ov)});
  }
  return out;
}
export function _ovSections(ovs){                                 // extra popup/panel rows per overlay hit
  return (ovs||[]).filter(o=>o.shown!==false).map(o =>
    '<hr style="border:none;border-top:1px solid #dedede;margin:6px 0">'+
    '<span style="color:#777">'+_esc(o.label)+'</span><br>'+_rfields(o.properties, o.fields)).join("");
}
export function handleOverlayClick(e, tier){                      // info popup only on SELECT (click), not hover
  for(const ov of OVERLAYS){
    if(!ov.interactive || ov.base) continue;               // an item attached to a road: the click selects its road (pick)
    if(tier && (tier==="under") !== !!ov.under) continue;  // consult only the requested tier
    const ids = ov.layers.filter(id=>map.getLayer(id));
    const hits = ids.length ? map.queryRenderedFeatures(e.point, {layers:ids}) : [];
    if(hits.length){
      const f = hits[0], p = _ovProps(ov, f);
      rsDeselect();                                        // road selection yields to the overlay
      _ovState(_ovSel,{select:false}); _ovSel={source:ov.source, id:f.id}; _ovState(_ovSel,{select:true});
      const fields = ov.popup && ov.popup.length ? ov.popup : Object.keys(p);
      if(!_ovWin(ov)){ /* popup_window=False: selected and lit, nothing shown */ }
      else if(_popupMode==="panel"){   // panel mode: dock the read-out like a road's, no floating popup
        rsInfoShow('<div class="rs-name">'+_esc(ov.label)+'</div>'+_rrows(p, fields));
      }else{
        const rows = fields.filter(k=>p[k]!=null && p[k]!=="").map(k=>"<b>"+_esc(k)+"</b>: "+_esc(p[k]));
        new maplibregl.Popup({closeButton:true,maxWidth:POPUP.maxWidth})
          .setLngLat(e.lngLat).setHTML(rows.join("<br>")||"(no data)").addTo(map)
          .on("close", clearOvSel);
      }
      // overlay clicks feed dashboards exactly like road clicks: rs:select with the overlay's
      // label + popup fields, so a sidebar shows sensor/zone info without extra wiring
      _emit("rs:select", {id:f.id, layer:ov.label, overlay:ov.label, fields:fields, properties:p});
      return true;
    }
  }
  return false;
}
let _ovTip = null;   // one shared hover tooltip for every overlay that asked for one (Overlay(tooltip=[...]))
// window.rsSetOverlay(label, on) shows/hides one overlay; the Layers control is UI over it.
export const _ovCbs={};   // label -> its checkbox in the Layers box
export function rsSetOverlay(labelOrIdx, on){
  const i = typeof labelOrIdx==="number" ? labelOrIdx : OVERLAYS.findIndex(o=>o.label===labelOrIdx);
  const ov = OVERLAYS[i]; if(!ov) return;
  ov.layers.forEach(id=>{ if(map.getLayer(id))
    map.setLayoutProperty(id,"visibility", on?"visible":"none"); });
  ov.visible = !!on;
  on ? _ovOff.delete(ov.label) : _ovOff.add(ov.label);
  if(_ovCbs[ov.label]) _ovCbs[ov.label].checked = !!on;
  _emit("rs:overlaychange", {overlay:ov.label, visible:!!on});
}
function _ovRow(ov, rule){
  const r=_check(ov.label, ov.visible!==false, on=>rsSetOverlay(ov.label, on), {rule, ...(ov.color ? {sw:ov.color, swCls:"ov-sw"} : {})});
  _ovCbs[ov.label]=r.cb;
  return r.lab;
}
// the hover tooltip and the hover glow of an overlay's layer, made once for each layer id of the map: the handlers find the overlay of the layer
// at each move, so a layer that a later style brings (the same ids) has the overlay of the new style
const _ovBound = new Set();
const _ovOfLayer = id => OVERLAYS.find(o=>o.layers.includes(id));
// rsSetInteraction can make a layer clickable, or give it its tooltip, later; the handlers read ov.interactive and ov.tooltip on each move
const _ovTips = ov=>ov.tooltip===true || (ov.tooltip && ov.tooltip.length);   // true: every field (rsSetInteraction, a layer with no list)
function _ovBind(id){
  if(_ovBound.has(id)) return;
  _ovBound.add(id);
  map.on("mousemove", id, e=>{ const ov=_ovOfLayer(id); if(!ov || !(ov.interactive || _ovTips(ov))) return;
    map.getCanvas().style.cursor = ov.interactive ? "pointer" : "";   // hover -> recolour, once the mouse rests on it (_TIP_DELAY)
    const f = e.features && e.features[0]; if(!f) return;
    const k={source:ov.source, id:f.id}, same=o=>!!o && o.source===k.source && o.id===k.id;
    _ovUnder=k;
    if(same(_ovHov)){ if(_ovTip && _ovTip.isOpen()) _ovTip.setLngLat(e.lngLat); return; }   // lit: its tooltip follows the mouse
    if(_ovHov){ _ovState(_ovHov,{hover:false}); _ovHov=null; if(_ovTip) _ovTip.remove(); }  // another one: the last off at once
    clearTimeout(_ovT); const ll=e.lngLat, props=f.properties||{};
    _ovT=setTimeout(()=>{ if(!same(_ovUnder)) return; _ovHov=k; if(ov.interactive) _ovState(_ovHov,{hover:true});
      if(_ovTip && _ovTips(ov)){
        _ovTip.setLngLat(ll).setHTML(_rfields(props, ov.tooltip===true ? null : ov.tooltip)); if(!_ovTip.isOpen()) _ovTip.addTo(map); } }, _TIP_DELAY); });
  map.on("mouseleave", id, ()=>{ map.getCanvas().style.cursor=""; clearTimeout(_ovT); _ovUnder=null;
    _ovState(_ovHov,{hover:false}); _ovHov=null;
    if(_ovTip) _ovTip.remove(); });
}
// The Layers box: one row for each overlay, in the panel's Roads card (panel mode) or in a box of its own; a new style takes the rows of the old one away
// and brings its own (a box with no row is taken away). The labels that the person turned off stay off.
const _ovOff = new Set();
let _ovBox = null, _ovGroupOff = false;
// A page with a toolbar has no Layers box: one switch for all the layers is in the base-map box (basemapbox.js), and the legend box lists them
// (colorbox.js). A page with no base-map box keeps the Layers box.
const _ovInToolbox = () => !!(O.dashboard && O.dashboard.toolbar && getTool("basemap"));
// rsSetOverlays(on): every layer of the style together. On: each layer as the style starts it (the points of a base map start off); off: all of them hidden
export function rsSetOverlays(on){
  _ovGroupOff = !on;
  OVERLAYS.forEach(ov=>rsSetOverlay(ov.label, on ? ov.visible0 : false));
  _emit("rs:overlayschange", {visible: !!on});
}
export const rsGetOverlays = () => OVERLAYS.length > 0 && !_ovGroupOff;
function _ovBoxRows(){
  if(_ovBox){ _ovBox.remove(); _ovBox = null; }
  for(const k of Object.keys(_ovCbs)){ _ovCbs[k].closest("label")?.remove(); delete _ovCbs[k]; }
  if(!OVERLAYS.length || !O.overlay_control || _ovInToolbox()) return;       // overlay_control=False: no Layers box (rsSetOverlay still works)
  // panel mode: overlay toggles join the panel's Roads card, right after its Bridges row — a
  // second floating "Layers" box on the map competes with the panel that hosts everything else.
  // Non-panel keeps the standalone Layers control.
  const host=_popupMode==="panel" ? document.querySelector(".flt-ctrl .flt-body") : null;
  if(host) OVERLAYS.forEach((ov,i)=> host.appendChild(_ovRow(ov, i===0)));
  else{   // its own Layers box; a base map's page (box_layout "stack"): under the Roads box, folded like it
    const stack=O.box_layout==="stack", {box, body}=_box("ov-ctrl", "ov", "Layers", stack ? true : null);
    OVERLAYS.forEach(ov=> body.appendChild(_ovRow(ov)));
    (stack ? _tlHost() : document.body).appendChild(box);
    _ovBox = box;
  }
}
// the overlays of the style of the moment (at the start, and again for a new style: rs.setStyle): their handlers, their rows, and their start state
export function useOverlays(){
  _OV_POPUP = O.overlay_popup;
  clearOvSel(); _ovHov = null; _ovUnder = null;
  if(!_ovTip) _ovTip = new maplibregl.Popup({closeButton:false, closeOnClick:false, maxWidth:POPUP.maxWidth, offset:POPUP.tipOffset, className:"rs-tip"});
  OVERLAYS.forEach(ov=>{ ov.visible0 = ov.visible !== false; _ovFetch(ov); ov.layers.forEach(_ovBind); if(_ovGroupOff || _ovOff.has(ov.label)) rsSetOverlay(ov.label, false); });
  window.RS_OVERLAYS = OVERLAYS;
  _ovBoxRows();
  _emit("rs:overlayschange", {visible: rsGetOverlays()});       // the base-map box and the legend box read the layers again
}
export function initOverlays(){
  window.rsSetOverlay = rsSetOverlay;
  window.rsSetOverlays = rsSetOverlays;
  window.rsGetOverlays = rsGetOverlays;
  useOverlays();
}

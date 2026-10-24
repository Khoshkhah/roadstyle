// extra overlay layers (zones / POIs / lines): click an interactive overlay -> popup of its
// fields; a Layers control toggles each overlay's visibility. Click precedence follows the
// visual stacking: "over" overlays (in front of the roads) win, then roads, then "under"
// overlays (zone fills) — and a selected road also reports the interactive overlays under the
// click (rs:select detail.overlays), so a sidebar can show the road AND its zone together.
import {POPUP, _rfields, _esc} from "../popup.js";
import {map, O, OVERLAYS, _emit} from "./core.js";
import {_popupMode, rsInfoShow, _tlHost, _box, _check} from "./panel.js";
import {rsDeselect, _rrows, _TIP_DELAY} from "./select.js";
let _OV_POPUP = true;       // overlay_popup=False: no overlay shows a popup (an Overlay's popup_window=False: that one); a click still selects and fires rs:select
export const _ovWin = ov => ov.popup_window!==false && _OV_POPUP;
export let _ovSel=null, _ovHov=null, _ovUnder=null, _ovT=0;      // {source,id} of the selected / lit (hovered) overlay feature; the one under the mouse now
function _ovState(ref, st){ if(ref) map.setFeatureState({source:ref.source, id:ref.id}, st); }
export function clearOvSel(){ _ovState(_ovSel,{select:false}); _ovSel=null; }
// the interactive overlay features at a screen point: [{label, fields, properties}] — one entry
// per overlay (its topmost hit). Feeds rs:select's `overlays` payload and the popup/panel.
export function _ovAt(pt){
  const out=[];
  for(const ov of OVERLAYS){
    if(!ov.interactive) continue;
    const ids = ov.layers.filter(id=>map.getLayer(id));
    const hits = ids.length ? map.queryRenderedFeatures(pt, {layers:ids}) : [];
    if(hits.length) out.push({label:ov.label, fields:ov.popup, properties:hits[0].properties||{}, shown:_ovWin(ov)});
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
      const f = hits[0], p = f.properties||{};
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
  if(_ovCbs[ov.label]) _ovCbs[ov.label].checked = !!on;
  _emit("rs:overlaychange", {overlay:ov.label, visible:!!on});
}
function _ovRow(ov, rule){
  const r=_check(ov.label, ov.visible!==false, on=>rsSetOverlay(ov.label, on), {rule, ...(ov.color ? {sw:ov.color, swCls:"ov-sw"} : {})});
  _ovCbs[ov.label]=r.cb;
  return r.lab;
}
export function initOverlays(){
  _OV_POPUP = O.overlay_popup;
  // the shared hover tooltip
  _ovTip = OVERLAYS.length                     // rsSetInteraction can give a layer its tooltip later
    ? new maplibregl.Popup({closeButton:false, closeOnClick:false, maxWidth:POPUP.maxWidth,
                            offset:POPUP.tipOffset, className:"rs-tip"}) : null;
  // every overlay: rsSetInteraction can make a layer clickable, or give it its tooltip, later; the handlers read ov.interactive and
  // ov.tooltip on each move
  const tips = ov=>ov.tooltip===true || (ov.tooltip && ov.tooltip.length);   // true: every field (rsSetInteraction, a layer with no list)
  OVERLAYS.forEach(ov=>{
   ov.layers.forEach(id=>{
    map.on("mousemove", id, e=>{ if(!(ov.interactive || tips(ov))) return;
      map.getCanvas().style.cursor = ov.interactive ? "pointer" : "";   // hover -> recolour, once the mouse rests on it (_TIP_DELAY)
      const f = e.features && e.features[0]; if(!f) return;
      const k={source:ov.source, id:f.id}, same=o=>!!o && o.source===k.source && o.id===k.id;
      _ovUnder=k;
      if(same(_ovHov)){ if(_ovTip && _ovTip.isOpen()) _ovTip.setLngLat(e.lngLat); return; }   // lit: its tooltip follows the mouse
      if(_ovHov){ _ovState(_ovHov,{hover:false}); _ovHov=null; if(_ovTip) _ovTip.remove(); }  // another one: the last off at once
      clearTimeout(_ovT); const ll=e.lngLat, props=f.properties||{};
      _ovT=setTimeout(()=>{ if(!same(_ovUnder)) return; _ovHov=k; if(ov.interactive) _ovState(_ovHov,{hover:true});
        if(_ovTip && tips(ov)){
          _ovTip.setLngLat(ll).setHTML(_rfields(props, ov.tooltip===true ? null : ov.tooltip)); if(!_ovTip.isOpen()) _ovTip.addTo(map); } }, _TIP_DELAY); });
    map.on("mouseleave", id, ()=>{ map.getCanvas().style.cursor=""; clearTimeout(_ovT); _ovUnder=null;
      _ovState(_ovHov,{hover:false}); _ovHov=null;
      if(_ovTip) _ovTip.remove(); });
  }); });
  window.rsSetOverlay = rsSetOverlay;
  window.RS_OVERLAYS = OVERLAYS;
  if(OVERLAYS.length && O.overlay_control){     // overlay_control=False: no Layers box (rsSetOverlay still works)
    // panel mode: overlay toggles join the panel's Roads card, right after its Bridges row — a
    // second floating "Layers" box on the map competes with the panel that hosts everything else.
    // Non-panel keeps the standalone Layers control.
    const host=_popupMode==="panel" ? document.querySelector(".flt-ctrl .flt-body") : null;
    if(host) OVERLAYS.forEach((ov,i)=> host.appendChild(_ovRow(ov, i===0)));
    else{   // its own Layers box; a base map's page (box_layout "stack"): under the Roads box, folded like it
      const stack=O.box_layout==="stack", {box, body}=_box("ov-ctrl", "ov", "Layers", stack ? true : null);
      OVERLAYS.forEach(ov=> body.appendChild(_ovRow(ov)));
      (stack ? _tlHost() : document.body).appendChild(box);
    }
  }
}

// extra overlay layers (zones / POIs / lines): click an interactive overlay -> popup of its
// fields; a Layers control toggles each overlay's visibility. Click precedence follows the
// visual stacking: "over" overlays (in front of the roads) win, then roads, then "under"
// overlays (zone fills) — and a selected road also reports the interactive overlays under the
// click (rs:select detail.overlays), so a sidebar can show the road AND its zone together.
import {POPUP, _rfields} from "../popup.js";
import {map, O, OVERLAYS} from "./core.js";
import {_popupMode, rsInfoShow} from "./panel.js";
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
    '<span style="color:#777">'+o.label+'</span><br>'+_rfields(o.properties, o.fields)).join("");
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
        rsInfoShow('<div class="rs-name">'+ov.label+'</div>'+_rrows(p, fields));
      }else{
        const rows = fields.filter(k=>p[k]!=null && p[k]!=="").map(k=>"<b>"+k+"</b>: "+p[k]);
        new maplibregl.Popup({closeButton:true,maxWidth:POPUP.maxWidth})
          .setLngLat(e.lngLat).setHTML(rows.join("<br>")||"(no data)").addTo(map)
          .on("close", clearOvSel);
      }
      // overlay clicks feed dashboards exactly like road clicks: rs:select with the overlay's
      // label + popup fields, so a sidebar shows sensor/zone info without extra wiring
      document.dispatchEvent(new CustomEvent("rs:select",
        {detail:{id:f.id, layer:ov.label, overlay:ov.label, fields:fields, properties:p}}));
      return true;
    }
  }
  return false;
}
let _ovTip = null;   // one shared hover tooltip for every overlay that asked for one (Overlay(tooltip=[...]))
// window.rsSetOverlay(label, on) shows/hides one overlay; the Layers control is UI over it.
const _ovCbs={};
export function rsSetOverlay(labelOrIdx, on){
  const i = typeof labelOrIdx==="number" ? labelOrIdx : OVERLAYS.findIndex(o=>o.label===labelOrIdx);
  const ov = OVERLAYS[i]; if(!ov) return;
  ov.layers.forEach(id=>{ if(map.getLayer(id))
    map.setLayoutProperty(id,"visibility", on?"visible":"none"); });
  ov.visible = !!on;
  if(_ovCbs[ov.label]) _ovCbs[ov.label].checked = !!on;
  document.dispatchEvent(new CustomEvent("rs:overlaychange",{detail:{overlay:ov.label, visible:!!on}}));
}
function _ovRow(ov){
  const lab=document.createElement("label");
  const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=ov.visible!==false;
  cb.onchange=()=> rsSetOverlay(ov.label, cb.checked);
  _ovCbs[ov.label]=cb; lab.appendChild(cb);
  if(ov.color){ const sw=document.createElement("span"); sw.className="ov-sw";
    sw.style.background=ov.color; lab.appendChild(sw); }
  lab.appendChild(document.createTextNode(" "+ov.label));
  return lab;
}
export function initOverlays(){
  _OV_POPUP = O.overlay_popup;
  // the shared hover tooltip
  _ovTip = OVERLAYS.some(o=>o.tooltip && o.tooltip.length)
    ? new maplibregl.Popup({closeButton:false, closeOnClick:false, maxWidth:POPUP.maxWidth,
                            offset:POPUP.tipOffset, className:"rs-tip"}) : null;
  OVERLAYS.forEach(ov=>{ if(!(ov.interactive || (ov.tooltip && ov.tooltip.length))) return;
   ov.layers.forEach(id=>{
    map.on("mousemove", id, e=>{ map.getCanvas().style.cursor="pointer";   // hover -> recolour, once the mouse rests on it (_TIP_DELAY)
      const f = e.features && e.features[0]; if(!f) return;
      const k={source:ov.source, id:f.id}, same=o=>!!o && o.source===k.source && o.id===k.id;
      _ovUnder=k;
      if(same(_ovHov)){ if(_ovTip && _ovTip.isOpen()) _ovTip.setLngLat(e.lngLat); return; }   // lit: its tooltip follows the mouse
      if(_ovHov){ _ovState(_ovHov,{hover:false}); _ovHov=null; if(_ovTip) _ovTip.remove(); }  // another one: the last off at once
      clearTimeout(_ovT); const ll=e.lngLat, props=f.properties||{};
      _ovT=setTimeout(()=>{ if(!same(_ovUnder)) return; _ovHov=k; _ovState(_ovHov,{hover:true});
        if(_ovTip && ov.tooltip && ov.tooltip.length){
          _ovTip.setLngLat(ll).setHTML(_rfields(props, ov.tooltip)); if(!_ovTip.isOpen()) _ovTip.addTo(map); } }, _TIP_DELAY); });
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
    if(host){
      OVERLAYS.forEach((ov,i)=>{
        const lab=_ovRow(ov);
        if(i===0) lab.style.cssText="margin-top:4px;padding-top:4px;border-top:1px solid #ddd";
        host.appendChild(lab);
      });
    } else {
      const box=document.createElement("div"); box.className="ov-ctrl";
      const hd=document.createElement("div"); hd.className="ov-hd"; hd.textContent="Layers";
      const body=document.createElement("div"); body.className="ov-body";
      box.appendChild(hd); box.appendChild(body);
      OVERLAYS.forEach(ov=> body.appendChild(_ovRow(ov)));
      document.body.appendChild(box);
    }
  }
}

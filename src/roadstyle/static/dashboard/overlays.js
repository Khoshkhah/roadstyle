// extra overlay layers (zones / POIs / lines): click an interactive overlay -> popup of its
// fields; a Layers control toggles each overlay's visibility. Click precedence follows the
// visual stacking: "over" overlays (in front of the roads) win, then roads, then "under"
// overlays (zone fills) — and a selected road also reports the interactive overlays under the
// click (rs:select detail.overlays), so a sidebar can show the road AND its zone together.
import {POPUP, _rfields, _esc} from "../popup.js";
import {map, O, OVERLAYS, OV_ROWS, RS_PREFIX, _NO_HOVER, _role, _emit} from "./core.js";
import {getTool} from "./tools.js";
import {_popupMode, rsInfoShow, _tlHost, _box, _check} from "./panel.js";
import {rsDeselect, _rrows, _TIP_DELAY, _popupHeld} from "./select.js";
let _OV_POPUP = true;       // overlay_popup=False: no overlay shows a popup (an Overlay's popup_window=False: that one); a click still selects and fires rs:select
export const _ovWin = ov => ov.popup_window!==false && _OV_POPUP;
// The reference is the RENDERED feature's source (f.source): a layer can draw a source of its own name (ov0 -> rs-ov0) or one that many overlays share (Studio:
// rs-roads and rs-low, a source layer for each overlay). _ovUnder also has the overlay (`ov`).
export let _ovSel=null, _ovHov=null, _ovUnder=null, _ovT=0;      // {source,sourceLayer,id} of the selected / lit (hovered) overlay feature; the one under the mouse now
export function _ovState(ref, st){ if(ref) map.setFeatureState({source:ref.source, sourceLayer:ref.sourceLayer, id:ref.id}, st); }
export function clearOvSel(){ _ovState(_ovSel,{select:false}); _ovSel=null; }
// holdSelectLook(key, on) (select.js): while a key holds it, a selection sets no `select` state on a road or an overlay item, and rs:select still
// comes, so a host page draws its own selection (duckOSM's fixes editor)
export const _lookHolds = new Set();
// the interactive overlay features at a screen point: [{label, fields, properties}] — one entry
// per overlay (its topmost hit). Feeds rs:select's `overlays` payload and the popup/panel.
// A layer's popup fields are not in its tiles: its props file (roadstyle:interaction.base_props, by source) holds them by row, the feature id.
const _ovRows = {};
// A page that is one HTML file (way A) holds the file as a `data:application/gzip` URL; with lazy_overlays=True it is a .json.gz file next to the page.
// Gzipped JSON is inflated (a web server can give the file inflated already: then it has no gzip header); else it is JSON.
const _ovJson = r => { if(!r.ok) throw new Error(r.url+": HTTP "+r.status); return r.arrayBuffer().then(b => { const u = new Uint8Array(b);
  return u[0]===0x1f && u[1]===0x8b ? new Response(new Blob([u]).stream().pipeThrough(new DecompressionStream("gzip"))).json() : JSON.parse(new TextDecoder().decode(u)); }); };
// The rows are also the overlay's features for rsQuery, rsGetProps and rsFocus (`OV_ROWS`: the row is the feature's properties, `__rs_bbox` its box).
// The rows in a file (lazy_overlays=True) are fetched when the overlay first shows (rsSetOverlay); the rows in the page at the start.
function _ovFetch(ov){ if(ov.props && !(ov.props in _ovRows)){ _ovRows[ov.props] = undefined; fetch(ov.props).then(_ovJson).then(j=>{
  _ovRows[ov.props] = j; OV_ROWS.set(ov.source, j.map((r, i) => ({id: i, properties: r, bbox: r.__rs_bbox}))); },
  e=>console.error("overlay rows:", e)); } }
const _ovInFile = ov => !!ov.props && !ov.props.startsWith("data:");
// an item's fields: its tile properties and its row, without roadstyle's own keys (__rs_bbox, ...): the popup, the panel and rs:select show the data only
const _ovProps = (ov, f) => Object.fromEntries(Object.entries({...f.properties, ...(_ovRows[ov.props] || [])[f.id]}).filter(([k]) => !k.startsWith("__rs")));
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
      _ovState(_ovSel,{select:false}); _ovSel={source:f.source, sourceLayer:f.sourceLayer, id:f.id}; if(!_lookHolds.size) _ovState(_ovSel,{select:true});
      const fields = ov.popup && ov.popup.length ? ov.popup : Object.keys(p);
      if(!_ovWin(ov) || _popupHeld()){ /* popup_window=False, or a part shows the facts (rs.holdPopup): selected and lit, no popup */ }
      else if(_popupMode==="panel"){   // panel mode: dock the read-out like a road's, no floating popup
        rsInfoShow('<div class="rs-name">'+_esc(ov.label)+'</div>'+_rrows(p, fields));
      }else{
        const rows = fields.filter(k=>p[k]!=null && p[k]!=="").map(k=>"<b>"+_esc(k)+"</b>: "+_esc(p[k]));
        const mine = _ovSel;       // a click on another feature closes this popup after it set its own selection: only a popup of the selection clears it
        new maplibregl.Popup({closeButton:true,maxWidth:POPUP.maxWidth})
          .setLngLat(e.lngLat).setHTML(rows.join("<br>")||"(no data)").addTo(map)
          .on("close", ()=>{ if(_ovSel===mine) clearOvSel(); });
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
// every layer of the map that draws an overlay's source: its `layers` and also the ones that the style does not list there (the fill pattern `ov0-pattern`, the
// icons `ov13-icon`, the 3D layer), found by their source (a GeoJSON source) or source layer (tiles), so that a switch hides or shows the whole overlay
const _ovAllLayers = ov => {
  const role = ov.source.slice(RS_PREFIX.length);
  return [...new Set([...ov.layers, ...map.getStyle().layers.filter(l=>_role(l)===role).map(l=>l.id)])].filter(id=>map.getLayer(id));
};
// Hidden overlays outside the starting style (O.overlay_layers, page_options.rs `lazy_layers`): an overlay's source and layers are added when it shows,
// each layer before the next layer of the style's order that the map has, and taken away when it hides. A page of a thousand hidden overlays then pans
// as fast as one with none (MapLibre walks every layer of the style at each frame).
const _ovLazyOf = ov => ((O.overlay_layers || {}).sources || {})[ov.source];
function _ovLazyAdd(ov){
  const z = _ovLazyOf(ov), order = O.overlay_layers.order;
  if(!z || map.getSource(ov.source)) return;
  map.addSource(ov.source, z.source);
  for(const l of z.layers){
    const i = order.indexOf(l.id), before = order.slice(i + 1).find(id => map.getLayer(id));
    map.addLayer({...l, layout: {...(l.layout || {}), visibility: "visible"}}, before);
  }
}
function _ovLazyRemove(ov){
  const z = _ovLazyOf(ov);
  if(!z || !map.getSource(ov.source)) return;
  if(_ovSel && _ovSel.source === ov.source) clearOvSel();
  if(_ovHov && _ovHov.source === ov.source) _ovHov = null;
  // the page's own changes of a layer (paint, layout, filter) stay in its definition for the next time it shows
  for(const l of z.layers) if(map.getLayer(l.id)){ const s = map.getStyle().layers.find(x => x.id === l.id); Object.assign(l, {paint: s.paint, layout: s.layout, filter: s.filter}); map.removeLayer(l.id); }
  map.removeSource(ov.source);
}
// A page's script can change a layer of a hidden overlay while it is out of the map (noise-map sets its points' colour at the start): get and set of
// paint, layout and filter on such a layer read and change its definition, which the overlay is added with.
function _ovLazyCalls(){
  if(!O.overlay_layers || map.__rsLazy) return;
  map.__rsLazy = true;
  const out = id => { if(map.getLayer(id)) return null; for(const z of Object.values(O.overlay_layers.sources)){ const l = z.layers.find(x => x.id === id); if(l) return l; } return null; };
  const wrap = (name, f) => { const own = map[name].bind(map); map[name] = (id, ...a) => { const l = out(id); return l ? f(l, ...a) : own(id, ...a); }; };
  wrap("getPaintProperty", (l, k) => (l.paint || {})[k]);
  wrap("setPaintProperty", (l, k, v) => { (l.paint = l.paint || {})[k] = v; return map; });
  wrap("getLayoutProperty", (l, k) => (l.layout || {})[k]);
  wrap("setLayoutProperty", (l, k, v) => { if(k !== "visibility") (l.layout = l.layout || {})[k] = v; return map; });   // rsSetOverlay decides if it shows
  wrap("getFilter", l => l.filter);
  wrap("setFilter", (l, f) => { l.filter = f; return map; });
}
export function rsSetOverlay(labelOrIdx, on){
  const i = typeof labelOrIdx==="number" ? labelOrIdx : OVERLAYS.findIndex(o=>o.label===labelOrIdx);
  const ov = OVERLAYS[i]; if(!ov) return;
  if(_ovLazyOf(ov)) on ? _ovLazyAdd(ov) : _ovLazyRemove(ov);
  _ovAllLayers(ov).forEach(id=>map.setLayoutProperty(id,"visibility", on?"visible":"none"));
  ov.visible = !!on;
  if(on) _ovFetch(ov);
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
// rsSetTooltip(label, fn) (rs.tooltip): the hover tooltip of an overlay, made by the page: fn(properties) gives {title, rows: [[name, value], ...]} (the
// title in bold, then one field on each line, as the other tooltips), or null for no tooltip on that feature. For values that are in the page, not in
// the tiles (the level of a wall at the hour that the page shows). fn null: the overlay's own tooltip again.
const _ovTipFn = {};
export function rsSetTooltip(label, fn){
  if(fn != null && typeof fn !== "function") throw new Error("rs.tooltip: give a function of the feature's properties, or null");
  if(fn == null) delete _ovTipFn[label]; else _ovTipFn[label] = fn;
}
const _ovTipHtml = t => [t.title != null && t.title !== "" ? "<b>" + _esc(t.title) + "</b>" : null,
                         ...(t.rows || []).map(([k, v]) => "<b>" + _esc(k) + "</b>: " + _esc(v))].filter(Boolean).join("<br>");
const _ovTips = ov=>!!_ovTipFn[ov.label] || ov.tooltip===true || (ov.tooltip && ov.tooltip.length);   // true: every field (rsSetInteraction, a layer with no list)
function _ovBind(id){
  if(_ovBound.has(id)) return;
  _ovBound.add(id);
  map.on("mousemove", id, e=>{ if(_NO_HOVER.matches) return; const ov=_ovOfLayer(id); if(!ov || !(ov.interactive || _ovTips(ov))) return;
    map.getCanvas().style.cursor = ov.interactive ? "pointer" : "";   // hover -> recolour, once the mouse rests on it (_TIP_DELAY)
    const f = e.features && e.features[0]; if(!f) return;
    const k={source:f.source, sourceLayer:f.sourceLayer, id:f.id, ov}, same=o=>!!o && o.source===k.source && o.sourceLayer===k.sourceLayer && o.id===k.id;
    _ovUnder=k;
    if(same(_ovHov)){ if(_ovTip && _ovTip.isOpen()) _ovTip.setLngLat(e.lngLat); return; }   // lit: its tooltip follows the mouse
    if(_ovHov){ _ovState(_ovHov,{hover:false}); _ovHov=null; if(_ovTip) _ovTip.remove(); }  // another one: the last off at once
    clearTimeout(_ovT); const ll=e.lngLat, props=_ovProps(ov, f);
    _ovT=setTimeout(()=>{ if(!same(_ovUnder)) return; _ovHov=k; if(ov.interactive) _ovState(_ovHov,{hover:true});
      if(_ovTip && _ovTips(ov)){
        const fn = _ovTipFn[ov.label], t = fn ? fn(props) : null;          // the page's own tooltip (rs.tooltip), else the overlay's fields
        const html = fn ? (t ? _ovTipHtml(t) : "") : _rfields(props, ov.tooltip===true ? null : ov.tooltip);
        if(html){ _ovTip.setLngLat(ll).setHTML(html); if(!_ovTip.isOpen()) _ovTip.addTo(map); } else _ovTip.remove(); } }, _TIP_DELAY); });
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
// rsSetOverlays(on): the layers of the base map together (the base-map box's one switch, O.overlays_label). On: each layer as the style starts it (the points of
// a base map start off); off: all of them hidden. A page's own overlays (rs.Overlay) are not in the group: a page switches them itself (rsSetOverlay, a row
// of its own: rsAddTopRow). A page with no base-map layer has its own overlays as the group.
export const _ovGroup = () => OVERLAYS.some(o => o.base_map) ? OVERLAYS.filter(o => o.base_map) : OVERLAYS;
export function rsSetOverlays(on){
  _ovGroupOff = !on;
  _ovGroup().forEach(ov=>rsSetOverlay(ov.label, on ? ov.visible0 : false));
  _emit("rs:overlayschange", {visible: !!on});
}
export const rsGetOverlays = () => _ovGroup().length > 0 && !_ovGroupOff;
function _ovBoxRows(){
  if(_ovBox){ _ovBox.remove(); _ovBox = null; }
  for(const k of Object.keys(_ovCbs)){ _ovCbs[k].closest("label")?.remove(); delete _ovCbs[k]; }
  if(!OVERLAYS.length || !O.overlay_control || _ovInToolbox()) return;       // overlay_control=False: no Layers box (rsSetOverlay still works)
  // a Layers box of its own (a page with no bar, or with no base-map box); a base map's page (box_layout "stack"): in the stack, folded
  const stack=O.box_layout==="stack", {box, body}=_box("ov-ctrl", "ov", "Layers", stack ? true : null);
  OVERLAYS.forEach(ov=> body.appendChild(_ovRow(ov)));
  (stack ? _tlHost() : document.body).appendChild(box);
  _ovBox = box;
}
// the overlays of the style of the moment (at the start, and again for a new style: rs.setStyle): their handlers, their rows, and their start state
export function useOverlays(){
  _OV_POPUP = O.overlay_popup;
  _ovLazyCalls();
  clearOvSel(); _ovHov = null; _ovUnder = null;
  if(!_ovTip) _ovTip = new maplibregl.Popup({closeButton:false, closeOnClick:false, maxWidth:POPUP.maxWidth, offset:POPUP.tipOffset, className:"rs-tip"});
  OVERLAYS.forEach(ov=>{ ov.visible0 = ov.visible !== false; if(ov.visible0 || !_ovInFile(ov)) _ovFetch(ov); ov.layers.forEach(_ovBind); if((_ovGroupOff && _ovGroup().includes(ov)) || _ovOff.has(ov.label)) rsSetOverlay(ov.label, false); });
  window.RS_OVERLAYS = OVERLAYS;
  _ovBoxRows();
  _emit("rs:overlayschange", {visible: rsGetOverlays()});       // the base-map box and the legend box read the layers again
}
export function initOverlays(){
  window.rsSetOverlay = rsSetOverlay;
  window.rsSetTooltip = rsSetTooltip;
  window.rsSetOverlays = rsSetOverlays;
  window.rsGetOverlays = rsGetOverlays;
  useOverlays();
}

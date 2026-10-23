// hover + click-to-select + info popup (feature-state, tolerance box, throttled to one query/frame)
import {POPUP, _rpairs, _rfields} from "../popup.js";
import {map, style, O, RS_LEAN, RS_DECK_LAYERS, OVERLAYS, _itemOv, _feats, _side, _rprops, _roadOfPiece, _FILL_PIECE, _fs, _deckIdsForRoad} from "./core.js";
import {_popupMode, rsInfoShow, rsInfoClear} from "./panel.js";
import {_ovUnder, _ovWin, clearOvSel, _ovAt, _ovSections, handleOverlayClick} from "./overlays.js";
import {_svLine, _svDist, _svTiled, _svPick, _sv, initSpot} from "./svspot.js";
const HIT = 4;
function box(p){ return [[p.x-HIT,p.y-HIT],[p.x+HIT,p.y+HIT]]; }
// query only layers that EXIST: the 3D view swaps roads-bridge-fill for the deck extrusions,
// and MapLibre errors out (killing hover+click) when asked to query a missing layer id.
// the fill halves (source "halves", square_ends.md) only paint: their edge is picked in its own, transparent fill layer
// an item attached to a road (Overlay(edge_col=...)) is picked as its road (docs/design/edge_items.md): hovering it highlights the road,
// clicking it selects the road; an interactive item's own fields come along as an overlay of the click (rs:select detail.overlays).
// An item of an Overlay(select="item") is picked as itself: hover and select highlight the item, a click shows its own popup and
// rs:select carries it (detail.item) next to its road.
let ITEM_LAYERS = new Set();
// render(items=...): the road's own items are pieces of the one road layer; a picked one (__rs_pick) is clicked and highlighted as itself there
let ROAD_ITEMS = null;   // {label, popup, layer: the one road layer} or null
let ITEM_PICK = null, PICK_LAYERS = [];
export function _roadOf(f){ const e=f.properties.__rs_edge;   // the road an item belongs to, as a picked road feature
  return {id:e, properties:_rprops(e), layer:f.layer, item:f,
          get geometry(){ const r=_feats()[e] || _svTiled(e); return r && r.geometry; }}; }   // tiles: only when Street View asks
// the feature right under the cursor first, the tolerance box only when there is none: a two-way road's two directions lie side by
// side, and the box reaches both, where the one drawn last would win (a click near the middle selected the other direction)
export function pick(p){ const ids = PICK_LAYERS.filter(id=>map.getLayer(id)); if(!ids.length) return null;
  if(ITEM_PICK && map.getLayer(ROAD_ITEMS.layer)){       // a picked road item under the cursor wins over its road
    const it = map.queryRenderedFeatures([p.x, p.y], {layers:[ROAD_ITEMS.layer], filter:["to-boolean",["get","__rs_pick"]]});
    if(it.length) return _roadOf(it[0]); }
  const q = RS_LEAN ? {layers:ids, filter:_FILL_PIECE} : {layers:ids};
  let l = map.queryRenderedFeatures([p.x, p.y], q);
  if(!l.length) l = map.queryRenderedFeatures(box(p), q);
  return !l.length ? null : ITEM_LAYERS.has(l[0].layer.id) ? _roadOf(l[0]) : RS_LEAN && l[0].layer.id===RS_LEAN ? _roadOfPiece(l[0]) : l[0]; }
export function srcOf(f){ return f && f.layer && f.layer.id.indexOf("roads-bridge-decks")===0 ? "decks" : "roads"; }
// full properties of a picked feature: tiles carry only the style props, so road hits read the
// sidecar row behind the feature id; decks (and inline mode) keep the feature's own properties
function _pickProps(f){ const s=_side();
  return (s && srcOf(f)==="roads" && f.id!=null) ? (s.props[f.id]||f.properties||{}) : (f.properties||{}); }
function _selItem(f){ if(ITEM_PICK && f && f.item && f.item.layer.id===ROAD_ITEMS.layer) return ITEM_PICK;   // a road item of items=
  const o = f && f.item && _itemOv(f.item.layer.id); return o && o.select==="item" ? o : null; }   // its overlay
function hitOf(f){ if(!f || f.id==null) return null;
  if(_selItem(f)) return {s:f.item.source, key:"i"+f.item.source+":"+f.item.id, ids:[f.item.id]};
  if(srcOf(f)==="decks"){ let e=f.properties && f.properties.__rs_edges;
    if(typeof e==="string") e=JSON.parse(e);                   // a rendered feature stringifies its list
    if(!e || !e.length || f.properties.__rs_casing_slab) return null;   // casing slab: not a road
    return {s:"decks", key:"e"+e[0], ids:_deckIdsForRoad(e[0])}; }  // one directed edge = one hover
  return {s:"roads", key:"r"+f.id, ids:[f.id]}; }
function setS(h, st){ if(h) h.ids.forEach(id=>_fs({source:h.s, id:id}, st)); }
let _hov=null, _pt=null, _raf=0;
// a reverse pair drawn as one line (config single_line_classes): its edge names the other direction in __rs_edge2, and the line's popup, panel and tooltip show both
function _twinDetail(p){ return p && p.__rs_edge2!=null ? {id:p.__rs_edge2, properties:_rprops(p.__rs_edge2)} : undefined; }   // rs:select detail.twin
function _both(p, rows, only){ const f=rows?_rrows:_rfields, t=p.__rs_edge2!=null ? _rprops(p.__rs_edge2) : null;
  if(!t || !Object.keys(t).length) return f(p, only);
  const sec=(n,q)=>'<div style="color:#777;margin-top:.3em">Direction '+n+'</div>'+f(q, only);
  return p.__rs_dup ? sec(1,t)+sec(2,p) : sec(1,p)+sec(2,t); }
export function _rrows(p, only){   // the side panel's layout: big name, then aligned key/value rows
  const [name, kv]=_rpairs(p, only);
  return (name ? '<div class="rs-name">'+name+'</div>' : "")+
    kv.map(([k,s])=>'<div class="rs-kv"><span>'+k+'</span><b>'+s+'</b></div>').join(""); }
export let _popupFields = null;   // curated field list, or null => all columns
export let _ID_KEYS = [];         // the road's id fields: the panel search always reads them
let _roadPopup = true;            // road_popup=False: a click selects and fires rs:select, no popup
export function rsDeselect(){
  if(_sel){ setS(_sel,{select:false});
    if(_sel.road!=null) _fs({source:"roads", id:_sel.road},{select:false});
    _sel=null; }
  rsInfoClear();
  document.dispatchEvent(new CustomEvent("rs:deselect"));
}
// programmatic selection by id (same id space as rsQuery / rs:select): highlight + popup/panel
// + rs:select, exactly like a click. The floating popup anchors at the edge's midpoint.
function _midOf(g){                         // the middle of the length (a middle VERTEX can be an end)
  const cs=_svLine({geometry:g}); if(cs.length<2) return cs[0]||null;
  const d=_svDist(cs), h=d[d.length-1]/2; let i=0; while(i<cs.length-2 && d[i+1]<h) i++;
  const t=(h-d[i])/((d[i+1]-d[i])||1);
  return [cs[i][0]+t*(cs[i+1][0]-cs[i][0]), cs[i][1]+t*(cs[i+1][1]-cs[i][1])]; }
export function rsSelect(id){
  const s=_side();
  const props = s ? s.props[id] : (_feats()[id]||{}).properties;
  if(props==null) return;
  clearOvSel();
  if(_sel) setS(_sel,{select:false});
  // a bridge: glow the deck chain (shown above flat_below) AND the flat line (shown below it)
  const hi = props && props.__rs_dup ? props.__rs_edge2 : id;      // a reverse pair is drawn by one edge: that one glows
  const dids = (props && props.lvl>0) ? _deckIdsForRoad(hi) : [];
  _sel = dids.length ? {s:"decks", key:"e"+hi, ids:dids, road:hi}
                     : {s:"roads", key:"r"+hi, ids:[hi]};
  setS(_sel,{select:true});
  if(_sel.road!=null) _fs({source:"roads", id:_sel.road},{select:true});
  // best effort for programmatic selection: overlays at the edge's midpoint (when on screen)
  const c = s ? s.mids[id] : _midOf((_feats()[id]||{}).geometry);
  let ovs=[]; if(c){ try{ ovs=_ovAt(map.project({lng:c[0], lat:c[1]})); }catch(err){} }
  const cll = c ? {lng:c[0], lat:c[1]} : null;
  document.dispatchEvent(new CustomEvent("rs:select",
    {detail:{id:id, layer:null, properties:props || {}, twin:_twinDetail(props), overlays:ovs, streetView:_svPick(cll, _feats()[id] || _svTiled(id), id)}}));
  const sv = _sv(cll, _feats()[id] || _svTiled(id));
  if(_roadPopup){
    if(_popupMode === "panel"){ rsInfoShow(_both(props||{}, true, _popupFields) + sv + _ovSections(ovs)); }
    else if(c) new maplibregl.Popup({closeButton:true, maxWidth:POPUP.maxWidth})
      .setLngLat(c).setHTML(_both(props||{}, false, _popupFields) + sv + _ovSections(ovs)).addTo(map);
  }
}
let _ttip = false, _ttipOnly = null;  // false | true | [fields]
export let _TIP_DELAY = 300;   // ms the mouse rests on a road or an overlay item before it lights up and its tooltip shows (a passing mouse lights nothing)
let _tipT = 0, _cur = null;               // _cur: the road under the mouse now
let _tip = null;
function hoverFrame(){ _raf=0; if(!_pt) return;
  const ho = _ovUnder && OVERLAYS.find(o=>o.source===_ovUnder.source);
  const ovHit = ho && !ho.under && !ho.base;   // an interactive overlay under the cursor wins over the road, as for a click; an item attached to a road is its road
  const f = ovHit ? null : pick(_pt); map.getCanvas().style.cursor = (f || ovHit) ? "pointer" : "";
  const h = hitOf(f);
  if(!(h && _cur && h.key === _cur.key)){                                                  // another road, or none: the last one off at once
    setS(_hov,{hover:false}); _hov=null; if(_tip && _tip.isOpen()) _tip.remove(); _cur = h; }
  if(_hov){ if(_tip && _tip.isOpen()) _tip.setLngLat(map.unproject(_pt)); return; }       // lit: its tooltip follows the mouse along the road
  clearTimeout(_tipT); if(!h) return;
  const p = _pt;
  _tipT = setTimeout(()=>{ if(_pt !== p) return;                                          // the mouse rested on it: light it up
    _hov=h; setS(_hov,{hover:true});
    if(_tip) _tip.setLngLat(map.unproject(p)).setHTML(_both(_pickProps(f), false, _ttipOnly)).addTo(map); }, _TIP_DELAY);
}
let _sel=null;
export function initSelect(){
  // only clickable items take part (2026-10-10): a non-interactive item (lanestyle's lane lines, arrows) let the click through to the lane under it
  ITEM_LAYERS = new Set(OVERLAYS.filter(o=>o.base && (o.interactive || o.select==="item")).flatMap(o=>o.layers));
  ROAD_ITEMS = O.items;
  ITEM_PICK = ROAD_ITEMS && {label:ROAD_ITEMS.label, popup:ROAD_ITEMS.popup, select:"item", interactive:true};
  PICK_LAYERS = style.layers.filter(l=>l.source!=="halves").map(l=>l.id)
    .filter(id=>(RS_LEAN ? id===RS_LEAN : /^roads-(low-|high-|bridge-)?fill/.test(id)) || ITEM_LAYERS.has(id)).concat(RS_DECK_LAYERS);
  _roadPopup = O.road_popup !== false; _popupFields = Array.isArray(O.road_popup) ? O.road_popup : null;
  _ID_KEYS = [...new Set([O.edge_id_col, "edge_ref"])];
  _ttip = O.road_tooltip; _ttipOnly = Array.isArray(_ttip) ? _ttip : null; _TIP_DELAY = O.hover_delay_ms;
  _tip = _ttip ? new maplibregl.Popup(
    {closeButton:false, closeOnClick:false, maxWidth:POPUP.maxWidth, offset:POPUP.tipOffset, className:"rs-tip"}) : null;
  initSpot();
  window.rsDeselect = rsDeselect;
  window.rsSelect = rsSelect;
  map.on("mousemove", e=>{ _pt=e.point; if(!_raf) _raf=requestAnimationFrame(hoverFrame); });
  map.on("mouseout", ()=>{ _pt=null; if(_raf){cancelAnimationFrame(_raf);_raf=0;} setS(_hov,{hover:false}); _hov=null; _cur=null; clearTimeout(_tipT); if(_tip) _tip.remove(); });
  map.on("click", e=>{
    // visual stacking decides the click: an "over" overlay (POIs, in front of the roads) wins;
    // then the roads; an "under" overlay (zone fills) only when the click missed every road —
    // so a road inside a zone stays selectable and still feeds rs:select / the sidebar.
    // (handleOverlayClick deselects the road itself BEFORE dispatching the overlay's rs:select,
    // so the sidebar isn't wiped by a trailing rs:deselect.)
    if(handleOverlayClick(e, "over")) return;
    const f = pick(e.point);
    if(!f){ if(!handleOverlayClick(e, "under")) rsDeselect(); return; }
    clearOvSel();
    if(_sel) setS(_sel,{select:false});
    _sel = hitOf(f); setS(_sel,{select:true});
    const props = _pickProps(f), io = _selItem(f);
    const item = io ? {overlay:io.label, id:f.item.id, properties:f.item.properties||{}} : undefined;   // the item selected itself
    const ovs = _ovAt(e.point).filter(o=>!io || o.label!==io.label);   // interactive overlays under the click (e.g. the zone)
    // structured click-data for host pages / dashboards (fires in every popup mode, incl. False)
    document.dispatchEvent(new CustomEvent("rs:select",
      {detail:{id:f.id, layer:f.layer && f.layer.id, properties:props, twin:_twinDetail(props), overlays:ovs, item:item,
               streetView:_svPick(e.lngLat, f, f.id)}}));
    const sv = _sv(e.lngLat, f);
    if(io){ if(io.interactive && _ovWin(io)){             // the item's own popup (its popup fields), the road's Street View below it
        if(_popupMode === "panel") rsInfoShow('<div class="rs-name">'+io.label+'</div>'+_rrows(item.properties, io.popup) + sv + _ovSections(ovs));
        else new maplibregl.Popup({closeButton:true, maxWidth:POPUP.maxWidth}).setLngLat(e.lngLat)
          .setHTML('<span style="color:#777">'+io.label+'</span><br>'+_rfields(item.properties, io.popup) + sv + _ovSections(ovs)).addTo(map); } }
    else if(_roadPopup){
      if(_popupMode === "panel"){ rsInfoShow(_both(props, true, _popupFields) + sv + _ovSections(ovs)); }
      else new maplibregl.Popup({closeButton:true, maxWidth:POPUP.maxWidth})
        .setLngLat(e.lngLat).setHTML(_both(props, false, _popupFields) + sv + _ovSections(ovs)).addTo(map);
    }
  });
}

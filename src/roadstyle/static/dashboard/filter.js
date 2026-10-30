// road-class filtering: window.rsSetClasses([...]) shows exactly those classes and hides the
// rest across every road layer; the collapsible checkbox panel is just UI over it. The class
// filter composes (AND) with the id filter from rsFilter below.
import {map, O, OVERLAYS, RS_ROLES, RoadTable, _has, _itemOv, _rprops, _sfeats, _src, _role, _lyr, _emit} from "./core.js";
export let FILTER = {classes:[], class_key:"__rs_ci", class_list:[]};     // a tile: the key that the filter reads and the class of each of its numbers (the style of a tile has them)
const _fltBase={};
let _fltVis=null;   // Set of visible classes; null = all
let _fltSeen=new Set();   // the classes of the style of the moment
let _qIds=null;     // id-set filter from rsFilter; null = off
let ACCESS = [];   // access_col: [[kind, colour, label, count], ...] for the kinds the data has (docs/design/sensor_matching_requests.md)
const _accHid = new Set();            // the access kinds switched off (rsSetAccess)
let _bridgesOn=true;   // rsSetBridges: hide every elevated (lvl>0) road and its 3D deck ribbons
let _tunnelsOn=true;   // rsSetTunnels: hide every below-ground (lvl<0) road, its names and arrows
const _ovIds={};       // an overlay's own rsFilter(ids, label) id set, by label (an attached one: composed with its edges' filter below)
const _ovKinds={};     // rsSetKinds: the kinds of a base-map layer that show, by label (null: all)
const _ovBase={};      // a not attached overlay layer's own filter, by layer id (read once)
let _modes=null, _modeRows=null;   // rsSetModes: the modes whose roads show (null: all), and the rows that one of them can use
// the overlay attached to edges (Overlay(edge_col=...)) that a layer draws: core.js, _itemOv
const _fltLayers=()=>map.getStyle().layers.filter(l=>RS_ROLES.has(_role(l)) || _itemOv(l.id));
// the one lookup (docs/design/edge_items.md): the class, bridge, tunnel and rsFilter switches decide which edges show, and every layer that
// draws a piece of a road, or an item attached to one, shows exactly the pieces and items of those edges. The class and level tests stay
// short property tests: every piece and item carries its edge's class (__rs_cls: FILTER.col of the edge, also on a name or an arrow,
// which carry the chain's highway) and level (lvl; an attached item has it baked as __rs_lvl). The rsFilter id set goes through the id (the road's row) and the twin from the road table (a two-way pair's shared piece shows while
// either edge shows). A shadow line or a 3D deck covers several edges (__rs_edges): it shows while any of them shows, decided here.
export function _applyRoadFilters(){
  // the id set: rsFilter's and the modes' (both: the rows in each)
  const ids = _qIds && _modeRows ? _qIds.filter(i=>_modeRows.has(i)) : _qIds || (_modeRows && [..._modeRows]);
  const hidden = _fltVis===null ? [] : FILTER.classes.filter(c=>!_fltVis.has(c)), hid=new Set(hidden), q=ids && new Set(ids);
  const edgeOn = i=>{ const p=_rprops(i), v=p.lvl||0;
    return !hid.has(p.__rs_cls) && !(p.__rs_access && _accHid.has(p.__rs_access)) && (_bridgesOn || v<1) && (_tunnelsOn || v>=0) && (!q || q.has(i)); };
  const multi = {};   // decks / shadows: the ids of the features with at least one edge shown (null = no switch is on)
  ["decks","shadows"].forEach(src=>{ multi[src] = !_bridgesOn ? [] : (hidden.length || q || !_tunnelsOn || _accHid.size)
    ? _sfeats((_src(src)||{}).source).map((f,k)=>(f.properties.__rs_edges||[]).some(edgeOn) ? k : -1).filter(k=>k>=0) : null; });
  const and = (f,c)=>f?["all",f,c]:c;
  // a pair drawn as one line has the row of one of its edges as the id of its pieces: it shows while either edge shows (the twin is in the road table)
  const qr = q && _has(["id"],[...q, ...[...q].map(i=>(_rprops(i)||{}).__rs_edge2).filter(t=>t!=null)]), qe = qr;   // once per change
  _fltLayers().forEach(l=>{
    if(!(l.id in _fltBase)) _fltBase[l.id]=map.getFilter(l.id)||null;
    let f=_fltBase[l.id];
    // the layer's data: roads, casings, halves, ends, slots, arrows, decks, shadows or an overlay; in tiles mode the slots share the archive
    // source, so the tile layer name is what separates them
    const kind = _role(l), ov=_itemOv(l.id);
    if(kind==="decks" || kind==="shadows"){
      if(multi[kind]) f=and(f, multi[kind].length ? _has(["id"], multi[kind]) : false);
    }else{
      const lvl=ov?"__rs_lvl":"lvl";
      // a tile has the class as a number (FILTER.class_key, __rs_ci or, for a filter on another column, __rs_cc: its place in FILTER.class_list, docs/design/tiling.md), a GeoJSON source its text (__rs_cls)
      if(hidden.length) f=and(f, l["source-layer"]
        ? ["!",["in",["coalesce",["get",FILTER.class_key],-1],["literal",hidden.map(c=>FILTER.class_list.indexOf(c))]]]
        : ["!",["in",["get","__rs_cls"],["literal",hidden]]]);
      if(_accHid.size) f=and(f, ["!",["in",["coalesce",["get","__rs_access"],""],["literal",[..._accHid]]]]);
      if(!_bridgesOn) f=and(f, ["<",["coalesce",["get",lvl],0],1]);
      if(!_tunnelsOn) f=and(f, [">=",["coalesce",["get",lvl],0],0]);
      if(q) f=and(f, kind==="roads" ? qr : qe);
      if(ov && _ovIds[ov.label]) f=and(f, _has(["id"],_ovIds[ov.label]));
    }
    // validate:false: our own filters need no grammar check, which cost ~6 ms a layer (a mode or class switch on a page of ~500 layers froze it ~3 s)
    try{ map.setFilter(l.id,f,{validate:false}); }catch(e){}
  });
  return hidden;
}
export function rsSetClasses(visible){
  _fltVis=new Set(visible);
  const hidden=_applyRoadFilters();
  _emit("rs:filterchange", {visible:FILTER.classes.filter(c=>_fltVis.has(c)), hidden:hidden});
}
export function rsSetBridges(on){
  _bridgesOn=!!on; _applyRoadFilters();
  _emit("rs:filterchange", {bridges:_bridgesOn});
}
export function rsSetTunnels(on){
  _tunnelsOn=!!on; _applyRoadFilters();
  _emit("rs:filterchange", {tunnels:_tunnelsOn});
}
export function rsFilter(ids, layer){   // show only these features; rsFilter(null) resets
  const L=_lyr(layer); if(!L) return;
  if(L.ov){
    // an overlay attached to edges: its own ids AND its edges' filter (the one lookup above)
    if(ids==null) delete _ovIds[L.ov.label]; else _ovIds[L.ov.label]=Array.from(ids);
    if(L.ov.base) _applyRoadFilters(); else _ovApply(L.ov);
    _emit("rs:filterchange", {overlay:L.ov.label, ids:ids==null?null:Array.from(ids)});
    return;
  }
  _qIds = ids==null ? null : Array.from(ids);
  _applyRoadFilters();
  _emit("rs:filterchange", {ids:_qIds});
}
// a not attached overlay's layers: each one's own filter, AND its rsFilter ids, AND its kinds (rsSetKinds)
function _ovApply(ov){
  const ids=_ovIds[ov.label], kinds=_ovKinds[ov.label];
  ov.layers.forEach(id=>{ if(!map.getLayer(id)) return;
    if(!(id in _ovBase)) _ovBase[id]=map.getFilter(id)||null;
    let f=_ovBase[id];
    if(ids) f=f?["all",f,_has(["id"],ids)]:_has(["id"],ids);
    if(kinds){ const k=["in",["get","kind"],["literal",kinds]]; f=f?["all",f,k]:k; }
    try{ map.setFilter(id, f, {validate:false}); }catch(e){} });
}
// rsSetKinds(label, list): only these `kind` values of a base-map layer (null: all); RS_KINDS: each layer's kinds and their counts
export function rsSetKinds(label, list){
  const L=_lyr(label); if(!L || !L.ov) return;
  _ovKinds[L.ov.label] = list==null ? null : Array.from(list);
  _ovApply(L.ov);
  _emit("rs:filterchange", {overlay:L.ov.label, kinds:list==null?null:Array.from(list)});
}
// rsSetModes(list): only the roads that one of these modes can use (the road table's flags driving, walking, cycling; null: all);
// one road filter with the classes, the access kinds and rsFilter
export function rsSetModes(list){
  _modes = list==null ? null : Array.from(list);
  if(_modes==null) _modeRows=null;
  else{ _modeRows=new Set(); for(let i=0, n=RoadTable.rows(); i<n; i++){ const p=RoadTable.props(i); if(_modes.some(m=>p[m]===true)) _modeRows.add(i); } }
  _applyRoadFilters();
  _emit("rs:filterchange", {modes:_modes && _modes.slice()});
}
export function rsSetAccess(kind, on){      // show / hide the roads of one access kind
  on ? _accHid.delete(kind) : _accHid.add(kind); _applyRoadFilters();
  _emit("rs:filterchange", {access:kind, visible:!!on});
}
// a new roads style (rs.setStyle): its layers' own filters are read again, and the switches that are off hide its roads too
export function useFilter(){
  FILTER = O.filter; ACCESS = FILTER.access || [];
  // a class that the person has not seen yet shows; the ones that were switched off stay off
  if(_fltVis) FILTER.classes.forEach(c=>{ if(!_fltSeen.has(c)) _fltVis.add(c); });
  _fltSeen = new Set(FILTER.classes);
  window.RS_CLASSES = FILTER.classes;
  window.RS_CLASS_COL = FILTER.col;          // the column RS_CLASSES came from (for custom UIs / stats)
  window.RS_CLASS_COLORS = FILTER.swatches || {};   // class -> its baked fill colour
  window.rsGetAccess = ()=>Object.fromEntries(ACCESS.map(a=>[a[0], !_accHid.has(a[0])]));
  window.RS_ACCESS = Object.fromEntries(ACCESS.map(a=>[a[0], a[3]]));
  window.RS_MODES = Object.fromEntries(O.modes || []);       // roadstyle:controls.modes: [[mode, count], ...]
  window.RS_KINDS = Object.fromEntries(OVERLAYS.filter(ov=>ov.kinds).map(ov=>[ov.label, Object.fromEntries(ov.kinds)]));
  for(const k in _fltBase) delete _fltBase[k];
  for(const k in _ovBase) delete _ovBase[k];
  if(_modes) rsSetModes(_modes);                              // the new road table's rows
  else if(_fltVis || _qIds || !_bridgesOn || !_tunnelsOn || _accHid.size) _applyRoadFilters();
  OVERLAYS.filter(ov=>!ov.base && (_ovIds[ov.label] || _ovKinds[ov.label])).forEach(_ovApply);
}
export function initFilter(){
  map.on("load",()=>{ _fltLayers().forEach(l=>{ if(!(l.id in _fltBase)) _fltBase[l.id]=map.getFilter(l.id)||null; }); });
  window.rsSetClasses = rsSetClasses;
  window.rsSetAccess = rsSetAccess;
  window.rsSetBridges = rsSetBridges;
  window.rsSetTunnels = rsSetTunnels;
  window.rsFilter = rsFilter;
  window.rsSetModes = rsSetModes;
  window.rsGetModes = ()=>_modes && _modes.slice();
  window.rsSetKinds = rsSetKinds;
  window.rsGetKinds = label=>{ const L=_lyr(label), k=L && L.ov && _ovKinds[L.ov.label]; return k ? k.slice() : null; };
  useFilter();
}

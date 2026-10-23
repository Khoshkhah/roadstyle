// roadstyle's map dashboard: the state that every control reads, the road data, and the id-set queries (docs/design/dashboard_module.md).
// Each file of this folder is an ES module. roadstyle's Python page puts them all in one script (render_web.py removes the import and
// export words), so every name of the folder is also a global of that page: two files must not use the same top-level name.
export let map = null, style = null, O = {};
// tiles=True: the roads are an embedded-PMTiles vector source (no inline features) — reads of
// per-edge data go to the sidecar table (window.RS_SIDE), and roads feature-state needs the
// source-layer name. RS_TILED=false leaves every code path exactly as the inline version.
export let RS_TILED = false;
// RS_LEAN (simple mode, inline data): the id of the one road layer, else false. The roads source is not drawn then, so MapLibre cuts it into no tiles. A road is
// picked on the fill pieces of that layer (__rs_k 1, their __rs_edge is the road's index), and its hover / select glow is the feature-state of those pieces (_fs).
export let RS_LEAN = false;
export let RS_DECK_LAYERS = [];
// extra overlay layers (zones / POIs / lines), their metadata: label, source, layers, popup, tooltip, interactive, under, base, ...
export let OVERLAYS = [];
export function initCore(m, opts){
  map = m; O = opts; style = opts.style;
  RS_TILED = opts.tiles; RS_LEAN = opts.simple; OVERLAYS = opts.overlays;
  RS_DECK_LAYERS = style.layers.filter(l=>l.id.indexOf("roads-bridge-decks")===0).map(l=>l.id);
  map.on("sourcedata", e=>{ const s=map.getSource(e.sourceId); if(s && s._data) delete s._data._rs; });
  window.rsQuery = rsQuery; window.rsGetProps = rsGetProps; window.rsHighlight = rsHighlight; window.rsFocus = rsFocus;
}
// whether a feature's value is one of ids: a "match" on the sorted, distinct ids (a lookup); an "in" on a literal list scanned the whole list for
// every feature in every layer, and a filter of thousands of ids froze the page (2026-10-07)
export function _has(expr, ids){ const u=[...new Set(Array.from(ids))].filter(v=>v!=null).sort((a,b)=>a<b?-1:a>b?1:0);
  return u.length ? ["match",expr,u,true,false] : false; }
// the overlay attached to edges (Overlay(edge_col=...)) that a layer draws, or null
export function _itemOv(id){ return OVERLAYS.find(o=>o.base && id in o.base) || null; }
// id-set queries: the baked features are a queryable table. rsQuery(p => …) returns the ids of
// the matching edges (generateId: a feature's id is its index in the source array); the verbs
// below act on any id set — filter to it, read it back as rows, or highlight it.
// every verb takes an optional `layer` argument: omitted -> the roads; an overlay's label (or
// index) -> that overlay's features. Overlay sources use generateId too, so the same id-set
// model applies — but each layer is its OWN id space: never mix ids across layers.
// MapLibre 5 keeps a GeoJSON source's data in `_data.geojson` (4.x: `_data` itself); there is no sync public getter
// After an updateData (the level editor's update in place) it keeps a Map id -> feature instead, in the source's order (a feature replaced
// keeps its place): read as a FeatureCollection, kept until the source's data changes again
export function _sdata(s){ const d=s && s._data; if(!d) return null; if(d.geojson || !d.updateable) return d.geojson;
  return d._rs || (d._rs={type:"FeatureCollection", features:Array.from(d.updateable.values())}); }
export function _sfeats(src){ const g=_sdata(map.getSource(src)); return (g && g.features)||[]; }
export function _feats(){ return _sfeats("roads"); }
// tiles mode plumbing: _side() -> the sidecar table (null while it inflates / in inline mode);
// _rprops(id) -> a road's full properties from either world; _fs() -> setFeatureState that adds
// the source-layer tiled road refs need (decks/overlays pass through untouched).
export function _side(){ return (RS_TILED && window.RS_SIDE) || null; }
export function _rprops(i){ const s=_side(); if(s) return s.props[i]||{};
  const f=_feats()[i]; return (f && f.properties)||{}; }
let _pcIdx = null, _pcFs = null;         // lean: a road's index -> the ids of its fill pieces in the simple source, and the feature list it was made from
export function _pieces(e){
  const fs=_sfeats("simple");            // a new list after the data changes (setData, or the level editor's updateData): the index is made again
  if(!_pcIdx || _pcFs!==fs){ const m=new Map();
    fs.forEach((f,i)=>{ const p=f.properties||{}; if(p.__rs_k===1){ let a=m.get(p.__rs_edge); if(!a) m.set(p.__rs_edge, a=[]); a.push(f.id!=null ? f.id : i); } });
    if(!fs.length) return [];
    _pcIdx=m; _pcFs=fs; }
  return _pcIdx.get(e) || []; }
export function _roadOfPiece(f){ const e=f.properties.__rs_edge;      // a fill piece, as the road feature it belongs to
  return {id:e, properties:_rprops(e), layer:{id:"roads-fill"}, get geometry(){ const r=_feats()[e]; return r && r.geometry; }}; }
export const _FILL_PIECE = ["any", ["==", ["get", "__rs_k"], 1], ["!", ["has", "__rs_k"]]];   // the fill pieces of the road layer, and what has no piece kind (overlays, decks)
export function _fs(ref, st){
  if(RS_LEAN && ref.source==="roads"){ _pieces(ref.id).forEach(id=>map.setFeatureState({source:"simple", id:id}, st)); return; }
  if(RS_TILED && ref.source==="roads") ref={source:"roads", sourceLayer:"roads", id:ref.id};
  map.setFeatureState(ref, st); }
export function _lyr(name){   // -> {src, ov} | null; ov null = the roads
  if(name==null) return {src:"roads", ov:null};
  const i = typeof name==="number" ? name : OVERLAYS.findIndex(o=>o.label===name);
  return OVERLAYS[i] ? {src:OVERLAYS[i].source, ov:OVERLAYS[i]} : null;
}
export function rsQuery(test, layer){
  const L=_lyr(layer); if(!L) return [];
  const out=[];
  const s = !L.ov && _side();
  if(s){ s.props.forEach((p,i)=>{ try{ if(test(p||{})) out.push(i); }catch(e){} }); return out; }
  _sfeats(L.src).forEach((f,i)=>{ try{ if(test(f.properties||{})) out.push(i); }catch(e){} });
  return out;
}
export function rsGetProps(ids, layer){ // the rows behind an id set (internals stripped) — table-ready
  const L=_lyr(layer); if(!L) return [];
  const s = !L.ov && _side(), fs = s ? null : _sfeats(L.src);
  return Array.from(ids||[]).map(i=>{
    const p=(s ? s.props[i] : (fs[i]&&fs[i].properties))||{}; const r={};
    for(const k in p){ if(k[0]!=="_" && k!=="lvl") r[k]=p[k]; }
    return r; });
}
// bridges in 3D are deck ribbons on their own source: this maps a road id to the deck slices
// of its whole chain (via the baked __rs_edges), so selection/highlight glows on the deck
// instead of the flat ground-level line
export function _deckIdsForRoad(i){
  const fs=_sfeats("decks");
  const out=[];
  fs.forEach((f,k)=>{ const e=f.properties && f.properties.__rs_edges;
    if(e && e.indexOf(i)>=0) out.push(k); });
  return out;
}
let _qHl=[], _qHlD=[];
const _qHlOv={};   // per-overlay highlighted ids
export function rsHighlight(ids, layer){ // selection glow on an id set; rsHighlight([]) clears
  const L=_lyr(layer); if(!L) return;
  if(L.ov){
    (_qHlOv[L.ov.label]||[]).forEach(i=>map.setFeatureState({source:L.src,id:i},{select:false}));
    const cur = ids==null ? [] : Array.from(ids);
    _qHlOv[L.ov.label]=cur;
    cur.forEach(i=>map.setFeatureState({source:L.src,id:i},{select:true}));
    document.dispatchEvent(new CustomEvent("rs:highlightchange",
      {detail:{overlay:L.ov.label, ids:cur.slice()}}));
    return;
  }
  _qHl.forEach(i=>_fs({source:"roads",id:i},{select:false}));
  _qHlD.forEach(i=>_fs({source:"decks",id:i},{select:false}));
  _qHl = ids==null ? [] : Array.from(ids);
  const dset=new Set();
  _qHl.forEach(i=>{ _fs({source:"roads",id:i},{select:true});
    const p=_rprops(i);
    if(p && p.lvl>0) _deckIdsForRoad(i).forEach(d=>dset.add(d)); });
  _qHlD = Array.from(dset);
  _qHlD.forEach(i=>_fs({source:"decks",id:i},{select:true}));
  document.dispatchEvent(new CustomEvent("rs:highlightchange",{detail:{ids:_qHl.slice()}}));
}
function _bbExtend(c, bb){  // walk any GeoJSON coordinates nesting (Point .. MultiPolygon)
  if(typeof c[0]==="number"){ bb.ok=true;
    if(c[0]<bb.minx)bb.minx=c[0]; if(c[0]>bb.maxx)bb.maxx=c[0];
    if(c[1]<bb.miny)bb.miny=c[1]; if(c[1]>bb.maxy)bb.maxy=c[1]; }
  else c.forEach(x=>_bbExtend(x, bb));
}
export function rsFocus(ids, opt, layer){ // fly the camera to an id (or id set); opt -> fitBounds
  const L=_lyr(layer); if(!L) return;
  const s = !L.ov && _side();
  const fs = s ? null : _sfeats(L.src), bb={ok:false, minx:1/0, miny:1/0, maxx:-1/0, maxy:-1/0};
  (Array.isArray(ids)?ids:[ids]).forEach(i=>{
    if(s){ const b=s.bboxes[i];
      if(b){ _bbExtend([[b[0],b[1]],[b[2],b[3]]], bb); } return; }
    const g=fs[i] && fs[i].geometry;
    if(g && g.coordinates) _bbExtend(g.coordinates, bb);
  });
  if(bb.ok) map.fitBounds([[bb.minx,bb.miny],[bb.maxx,bb.maxy]],
    {padding:80, maxZoom:17, duration:700, ...(opt||{})});
}

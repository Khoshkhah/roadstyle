// roadstyle's map dashboard: the state that every control reads, the road data, and the id-set queries (docs/design/dashboard_module.md).
// Each file of this folder is an ES module. roadstyle's Python page puts them all in one script (render_web.py removes the import and
// export words), so every name of the folder is also a global of that page: two files must not use the same top-level name.
export let map = null, style = null, O = {};
// the prefix of the roads style's source and layer ids in the map: a page that adds the style beside its own adds one ("rs-");
// the names in the style itself (a layer's source-layer, its metadata) stay without it
export let RS_PREFIX = "";
// tiles=True: the roads are a vector source (the template's no-roads message reads it). The modules do not branch on it: they read the
// source map (_src) and the road table (RoadTable).
export let RS_TILED = false;
// simple mode (the style has the role simple): the id of its one road layer in the map, else false (Python's full look). A road is picked
// on the fill pieces of that layer (__rs_k 1, their __rs_edge is the road's row), and its hover / select glow is the feature-state of those
// pieces (_fs).
export let RS_LEAN = false;
export let RS_DECK_LAYERS = [];
// extra overlay layers (zones / POIs / lines), their metadata: label, source, layers, popup, tooltip, interactive, under, base, ...
export let OVERLAYS = [];
export function initCore(m, opts){
  map = m; O = opts; RS_PREFIX = opts.prefix;
  RS_TILED = opts.tiles; OVERLAYS = opts.overlays;
  useStyle(opts.style);
  map.once("load", _checkPromote);
  map.on("sourcedata", e=>{ const s=map.getSource(e.sourceId); if(s && s._data) delete s._data._rs; if(_SRC.decks && e.sourceId===RS_PREFIX+_SRC.decks.source) _decks=null; });
  window.rsQuery = rsQuery; window.rsGetProps = rsGetProps; window.rsHighlight = rsHighlight; window.rsFocus = rsFocus;
}
// the roads style, at the start or later (rs.setStyle: a page that adds the roads after a build, again for each network). No style yet:
// no road layers, nothing to pick
export function useStyle(st){
  style = st || {layers:[], sources:{}, metadata:{}};
  _SRC = O.sources || (style.metadata || {})["roadstyle:sources"] || _sourcesOf(style);
  const lean = style.layers.find(l=>(l["source-layer"] || l.source)==="simple" && l.type==="line");
  RS_LEAN = lean ? RS_PREFIX+lean.id : false;
  RS_DECK_LAYERS = style.layers.filter(l=>l.id.indexOf("roads-bridge-decks")===0).map(l=>RS_PREFIX+l.id);
  _decks = null;
  _checkPromote();
}
// simple mode needs the pieces' row as their id (promoteId "__rs_edge"): else the glow by row lights other pieces. Checked when the map has
// the source (at the start: on "load")
function _checkPromote(){
  if(RS_LEAN && map.getSource(_src("simple").source) && !_promoted("simple"))
    console.error('rs: the source of the role simple needs promoteId "__rs_edge" (addSource), or a road does not glow');
}
// THE ROADS STYLE'S SOURCES BY ROLE: role -> {source, layer}. The roles are the names of the roads style's sources (simple, slots, arrows,
// decks, shadows, boundary, ov<i>, and roads in Python's full look); with tiles a role is a source layer of a vector source. The option
// sources (the page) or the metadata roadstyle:sources gives them; a style without them gives them by its layers (a layer's source-layer,
// else its source, is its role): the same map.
let _SRC = {};
function _sourcesOf(st){ const out = {};
  for(const l of st.layers) if(l.source) out[l["source-layer"] || l.source] = {source:l.source, layer:l["source-layer"] || null};
  return out; }
// a role's source in the map (with the prefix) and its source layer (only for a vector source), for setFeatureState and querySourceFeatures
export function _src(role){ const s = _SRC[role]; if(!s) return null;
  const r = {source:RS_PREFIX+s.source}; if(s.layer) r.sourceLayer = s.layer; return r; }
// the role of a layer of the map
export function _role(l){ return l["source-layer"] || (l.source && l.source.indexOf(RS_PREFIX)===0 ? l.source.slice(RS_PREFIX.length) : l.source); }
// whether a role's features have the road's row as their id (promoteId "__rs_edge": a GeoJSON source's, or a vector source's for that layer)
function _promoted(role){ const s = _src(role), m = s && map.getSource(s.source), p = m && m.promoteId;
  return !!p && (typeof p === "string" ? p : p[s.sourceLayer]) === "__rs_edge"; }
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
// the features of an inline source of the roads style that has no table (decks, slots, overlays); src: the source's id in the map
export function _sfeats(src){ const g=_sdata(src && map.getSource(src)); return (g && g.features)||[]; }
// THE ROAD TABLE: each road's fields, midpoint, bbox, heading and line, keyed by the row ({props, mids, bboxes, headings, lines}, as stage 1
// makes it). The page gives it (options.road_table, or window.RS_SIDE: the page loads it after the style and then sends rs:tableready).
// RoadTable is the one port of every read of a road; null and {} where it has nothing (before the table has come).
function _table(){ return O.road_table || window.RS_SIDE || null; }
export function _side(){ return _table(); }
// live data (live.js, rs.setData): row -> the joined row's fields, which a road's properties show too (the popup, the panel); null: none
export let _joined = null, _joinedKeys = [];
export function _setJoined(m){ _joined = m;
  _joinedKeys = m ? [...new Set([].concat(...[...m.values()].slice(0, 100).map(r => Object.keys(r))))] : []; }
export const RoadTable = {
  has(i){ const t=_table(); return !!t && t.props[i]!=null; },
  props(i){ const t=_table(), p=(t && t.props[i]) || {}, j=_joined && _joined.get(i); return j ? {...p, ...j} : p; },
  line(i){ const t=_table(); return (t && t.lines && t.lines[i]) || null; },
  mid(i){ const t=_table(); return (t && t.mids && t.mids[i]) || null; },
  bbox(i){ const t=_table(); return (t && t.bboxes && t.bboxes[i]) || null; },
  rows(){ const t=_table(); return t ? t.props.length : 0; },
};
export function _rprops(i){ return RoadTable.props(i); }
// a road as a feature with its whole line ({id, properties, geometry}), for Street View and Google 3D; null without a line
export function _road(i){ const c=RoadTable.line(i); return c ? {id:i, get properties(){ return RoadTable.props(i); }, geometry:{type:"LineString", coordinates:c}} : null; }
// a fill piece, as the road feature it belongs to (its line: the road's whole line, from the road table)
export function _roadOfPiece(f){ const e=f.properties.__rs_edge;
  return {id:e, properties:_rprops(e), layer:{id:RS_PREFIX+"roads-fill"}, get geometry(){ const r=_road(e); return r && r.geometry; }}; }
export const _FILL_PIECE = ["any", ["==", ["get", "__rs_k"], 1], ["!", ["has", "__rs_k"]]];   // the fill pieces of the road layer, and what has no piece kind (overlays, decks)
// THE GLOW: the feature state of a road by its row. ref.source: "roads" or "decks" (roles of the roads style), or an overlay's source id.
// Simple mode: the road's pieces in the role simple, which all have the row as their id (promoteId "__rs_edge"); the full look: the road in
// the role roads. The source layer only where the role is in a vector source.
export function _fs(ref, st){
  if(ref.source==="roads" && RS_LEAN){ const s=_src("simple"); if(s) map.setFeatureState({...s, id:ref.id}, st); return; }
  if(ref.source==="roads" || ref.source==="decks"){ const s=_src(ref.source); if(!s) return; ref={...s, id:ref.id}; }
  map.setFeatureState(ref, st); }
export function _lyr(name){   // -> {src, ov} | null; ov null = the roads (the road table)
  if(name==null) return {src:null, ov:null};
  const i = typeof name==="number" ? name : OVERLAYS.findIndex(o=>o.label===name);
  return OVERLAYS[i] ? {src:OVERLAYS[i].source, ov:OVERLAYS[i]} : null;
}
export function rsQuery(test, layer){
  const L=_lyr(layer); if(!L) return [];
  const out=[];
  if(!L.ov){ for(let i=0, n=RoadTable.rows(); i<n; i++){ try{ if(test(RoadTable.props(i))) out.push(i); }catch(e){} } return out; }
  _sfeats(L.src).forEach((f,i)=>{ try{ if(test(f.properties||{})) out.push(i); }catch(e){} });
  return out;
}
export function rsGetProps(ids, layer){ // the rows behind an id set (internals stripped) — table-ready
  const L=_lyr(layer); if(!L) return [];
  const fs = L.ov ? _sfeats(L.src) : null;
  return Array.from(ids||[]).map(i=>{
    const p=(fs ? fs[i]&&fs[i].properties : RoadTable.props(i))||{}; const r={};
    for(const k in p){ if(k[0]!=="_" && k!=="lvl") r[k]=p[k]; }
    return r; });
}
// bridges in 3D are deck ribbons on their own source: this maps a road id to the deck slices
// of its whole chain (via the baked __rs_edges), so selection/highlight glows on the deck
// instead of the flat ground-level line. One index road -> decks, made again when the decks' data changes.
let _decks = null;
export function _deckIdsForRoad(i){
  if(!_decks){ _decks = new Map();
    _sfeats((_src("decks")||{}).source).forEach((f,k)=>{ for(const e of (f.properties && f.properties.__rs_edges) || []){
      let a=_decks.get(e); if(!a) _decks.set(e, a=[]); a.push(k); } }); }
  return (_decks.get(i) || []).slice();
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
  const fs = L.ov ? _sfeats(L.src) : null, bb={ok:false, minx:1/0, miny:1/0, maxx:-1/0, maxy:-1/0};
  (Array.isArray(ids)?ids:[ids]).forEach(i=>{
    if(!fs){ const b=RoadTable.bbox(i);
      if(b){ _bbExtend([[b[0],b[1]],[b[2],b[3]]], bb); } return; }
    const g=fs[i] && fs[i].geometry;
    if(g && g.coordinates) _bbExtend(g.coordinates, bb);
  });
  if(bb.ok) map.fitBounds([[bb.minx,bb.miny],[bb.maxx,bb.maxy]],
    {padding:80, maxZoom:17, duration:700, ...(opt||{})});
}

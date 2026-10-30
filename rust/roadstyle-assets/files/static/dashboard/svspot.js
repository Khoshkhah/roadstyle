// GOOGLE STREET VIEW of the clicked edge (the window, the side-by-side page, or a plain link),
// looking the way the edge runs. A plain maps URL, no API key; where it stands is below.
import {_esc} from "../popup.js";
import {map, O, RS_PREFIX, RS_LEAN, RS_LEANS, _road, _roadOfPiece, _emit} from "./core.js";
import {_svWindow} from "./streetview.js";
import {srcOf} from "./select.js";
let _streetView = false;
let RS_FILL_LAYERS = [];   // the road fill layers (Street View finds a road on them)
// Street View stands at a spot ON the clicked edge: its own geometry (the road's centre line), the
// spot nearest the click, looking along the edge. The drawn lanes sit offset from that line by a
// pixel amount (tens of metres when zoomed out), so the raw click could land nearer an indoor
// photo than the road's imagery. A two-way road's direction then steps _SV_LANE_M to its right,
// into the middle of its own lane (MapLibre's line-offset draws it there: right-hand traffic).
// The position is kept as {edge, metres along it}: the map marker, the step buttons
// (rsStreetViewStep) and the URL all read it, so they cannot disagree.
const _SV_LANE_M = 2.5, _SV_R = 110540;          // metres per degree of latitude
let _svPos = null, _svMk = null, _svMarkOn = false;
// where a Street View that reports its moves says the viewer is (rsSetStreetViewMarkerAt): the
// heading they look, and - only when no drawn road is near - a free spot {c}. Cleared by the next
// selection or step.
let _svFree = null, _svLast = null;
export function _svLine(f){ const g=f && f.geometry;
  return !g ? [] : g.type==="LineString" ? g.coordinates : g.type==="MultiLineString" ? [].concat(...g.coordinates) : []; }
function _svFeat(f){                          // the edge's full geometry (a picked one may be tile-clipped)
  return (f && f.id!=null && srcOf(f)==="roads" && _road(f.id)) || f; }
export function _svDist(cs){ const k=Math.cos(cs[0][1]*Math.PI/180), d=[0];
  for(let i=1;i<cs.length;i++) d.push(d[i-1]+Math.hypot((cs[i][0]-cs[i-1][0])*k*_SV_R, (cs[i][1]-cs[i-1][1])*_SV_R));
  return d; }
function _svMeasure(f, ll){                     // metres along f to the spot nearest ll
  const cs=_svLine(f); if(cs.length<2) return null;
  const k=Math.cos(ll.lat*Math.PI/180), d=_svDist(cs); let best=0, bd=Infinity;
  for(let i=0;i+1<cs.length;i++){
    const dx=(cs[i+1][0]-cs[i][0])*k, dy=cs[i+1][1]-cs[i][1], px=(ll.lng-cs[i][0])*k, py=ll.lat-cs[i][1];
    const t=Math.max(0, Math.min(1, (px*dx+py*dy)/((dx*dx+dy*dy)||1))), q=(px-t*dx)**2+(py-t*dy)**2;
    if(q<bd){ bd=q; best=d[i]+t*(d[i+1]-d[i]); } }
  return best; }
export function _svAt(f, m){                           // the spot m metres along f: {lng, lat, h, m, len}
  const cs=_svLine(f); if(cs.length<2) return null;
  const d=_svDist(cs), len=d[d.length-1]; m=Math.max(0, Math.min(len, m));
  let i=0; while(i<cs.length-2 && d[i+1]<m) i++;
  const t=(m-d[i])/((d[i+1]-d[i])||1), k=Math.cos(cs[i][1]*Math.PI/180);
  const dx=(cs[i+1][0]-cs[i][0])*k, dy=cs[i+1][1]-cs[i][1];
  const p={lng:cs[i][0]+t*(cs[i+1][0]-cs[i][0]), lat:cs[i][1]+t*(cs[i+1][1]-cs[i][1]),
           h:(Math.atan2(dx,dy)*180/Math.PI+360)%360, m:m, len:len, a:cs[i], b:cs[i+1]};
  p.c=[p.lng, p.lat];                           // on the centre line: where the map draws from
  if(f.properties && f.properties.__rs_twoway){ // (dy,-dx) points right of travel
    const n=Math.hypot(dx, dy)||1, o=_SV_LANE_M/_SV_R; p.lng += dy/n*o/k; p.lat -= dx/n*o; }
  return p; }
function _svUrlOf(p){ return 'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint='+
  p.lat.toFixed(6)+','+p.lng.toFixed(6)+(p.h==null ? '' : '&heading='+Math.round(p.h)); }
function _svUrl(ll, f){
  if(!_streetView || !ll) return null;
  f=_svFeat(f); const m=_svMeasure(f, ll), p=m==null ? null : _svAt(f, m);
  return _svUrlOf(p || ll); }
// a selection: remember the spot (for the marker and the step buttons) and return its URL
export function _svPick(ll, f, id){
  f=_svFeat(f); const m=(_streetView && ll) ? _svMeasure(f, ll) : null;
  _svFree = null; _svLast = null;
  _svPos = m==null ? null : {f:f, m:m, id:id}; _svMark();
  queueMicrotask(_svSpotEvent);                 // after the rs:select this pick is part of
  return _svUrl(ll, f); }
// the map marker: a dot where Street View stands and a cone the way it looks. Shown while a
// Street View is on screen (the window open, or the side-by-side page); rsSetStreetViewMarker(on)
// the drawn lane offset (px) of an edge at this zoom: the road layer's own line-offset expression,
// ["interpolate",["linear"],["zoom"], z, ["case", two-way?, ["match",["get",class], ..., dflt], 0], ...]
export function _svLanePx(props){
  const lay=RS_LEAN || RS_PREFIX+"roads-fill"; if(!map.getLayer(lay)) return 0;     // the road layer: simple mode's one layer, or the full look's fill
  const e=map.getPaintProperty(lay, "line-offset");
  if(!Array.isArray(e) || e[0]!=="interpolate") return typeof e==="number" ? e : 0;
  const val=x=>{ if(typeof x==="number") return x;
    if(!Array.isArray(x)) return 0;
    if(x[0]==="case") return props.__rs_twoway ? val(x[2]) : val(x[3]);
    if(x[0]==="match"){ const v=props[x[1][1]];
      for(let i=2;i+1<x.length;i+=2) if(x[i]===v || (Array.isArray(x[i]) && x[i].includes(v))) return val(x[i+1]);
      return val(x[x.length-1]); }
    return 0; };
  const z=map.getZoom(), st=[]; for(let i=3;i+1<e.length;i+=2) st.push([e[i], e[i+1]]);
  if(!st.length) return 0;
  if(z<=st[0][0]) return val(st[0][1]);
  for(let i=0;i+1<st.length;i++) if(z<=st[i+1][0]){
    const t=(z-st[i][0])/(st[i+1][0]-st[i][0]); return val(st[i][1])+t*(val(st[i+1][1])-val(st[i][1])); }
  return val(st[st.length-1][1]); }
// place the marker on the centre line, shifted right of travel by the lane's drawn offset: Google
// gets the real 2.5 m lane point, the marker sits in the lane as drawn at this zoom
function _svMarkPlace(){
  if(!_svMk || !_svPos || (_svFree && _svFree.c)) return;
  const p=_svAt(_svPos.f, _svPos.m); if(!p) return;
  const px=_svLanePx(_svPos.f.properties||{}), a=map.project(p.a), b=map.project(p.b);
  const dx=b.x-a.x, dy=b.y-a.y, n=Math.hypot(dx, dy)||1;   // screen: y down, right of travel = (-dy, dx)
  _svMk.setLngLat(p.c).setOffset([-dy/n*px, dx/n*px]); }
function _svMark(){
  const p = !_svMarkOn ? null : _svFree && _svFree.c ? {c:_svFree.c, h:_svFree.h} : _svPos ? _svAt(_svPos.f, _svPos.m) : null;
  if(!p){ if(_svMk){ _svMk.remove(); _svMk=null; } return; }
  if(!_svMk){ const el=document.createElement("div"); el.className="rs-svm";
    el.innerHTML='<svg width="64" height="64" viewBox="-32 -32 64 64">'+
      '<path d="M0 0 L-16 -26 A31 31 0 0 1 16 -26 Z" fill="rgba(13,71,161,.45)" stroke="#fff" stroke-width="1.5"/>'+
      '<circle r="7" fill="#0d47a1" stroke="#fff" stroke-width="2.5"/></svg>';
    _svMk=new maplibregl.Marker({element:el, rotationAlignment:"map", pitchAlignment:"map"}); }
  _svMk.setLngLat(p.c).setRotation(_svFree ? _svFree.h : (p.h||0)).addTo(map);
  if(_svFree && _svFree.c) _svMk.setOffset([0, 0]); else _svMarkPlace(); }
// keep a point on screen: pan once it nears the map's edge (walking, by step or in the panorama)
function _svKeepInView(lng, lat){
  const q=map.project([lng, lat]), c=map.getCanvas(), pad=60;
  if(q.x<pad || q.y<pad || q.x>c.clientWidth-pad || q.y>c.clientHeight-pad) map.easeTo({center:[lng, lat], duration:400}); }
// the marker where a Street View panorama stands and the way it looks - for a Street View that
// reports its own moves (the Maps JavaScript API does; the keyless embed cannot). null clears it.
// ON THE ROAD AS DRAWN: a panorama stands where the camera car drove - between the drawn lanes of a
// two-way road - so the spot is snapped onto a drawn edge and the marker sits in its lane like a
// clicked one. The current edge while the viewer is still on it (looking round never switches
// lanes); off it, the nearest road drawn on screen, the direction they walked. Free only when no
// road is within _SV_SNAP_M.
const _SV_SNAP_M = 20;
function _svOnEdge(f, ll){                      // {f, m, d metres from its centre line, h} | null
  f=_svFeat(f); const m=_svMeasure(f, ll); if(m==null) return null;
  const cs=_svLine(f), d=_svDist(cs); let i=0; while(i<cs.length-2 && d[i+1]<m) i++;
  const t=(m-d[i])/((d[i+1]-d[i])||1), x=cs[i][0]+t*(cs[i+1][0]-cs[i][0]), y=cs[i][1]+t*(cs[i+1][1]-cs[i][1]);
  const k=Math.cos(ll.lat*Math.PI/180), h=(Math.atan2((cs[i+1][0]-cs[i][0])*k, cs[i+1][1]-cs[i][1])*180/Math.PI+360)%360;
  return {f:f, m:m, d:Math.hypot((ll.lng-x)*k*_SV_R, (ll.lat-y)*_SV_R), h:h}; }
export function rsSetStreetViewMarkerAt(lng, lat, heading){
  if(lng==null){ _svFree=null; _svLast=null; _svMark(); _svSpotEvent(); return; }
  const ll={lng:+lng, lat:+lat}, look=+heading||0, k=Math.cos(ll.lat*Math.PI/180);
  const moved=_svLast ? Math.hypot((ll.lng-_svLast.lng)*k*_SV_R, (ll.lat-_svLast.lat)*_SV_R) : 0;
  const walk=moved>2 ? (Math.atan2((ll.lng-_svLast.lng)*k, ll.lat-_svLast.lat)*180/Math.PI+360)%360 : null;
  _svLast=ll;
  const off=(a, b)=>{ const x=Math.abs(a-b)%360; return x>180 ? 360-x : x; };
  let best=_svPos ? _svOnEdge(_svPos.f, ll) : null;
  if(!best || best.d>_SV_LANE_M+6 || best.m<=0.01 || best.m>=_svAt(best.f, 1e9).len-0.01){
    const q=map.project([ll.lng, ll.lat]), r=40, lays=RS_LEAN ? RS_LEANS : RS_FILL_LAYERS.filter(id=>map.getLayer(id)), cand=[];
    map.queryRenderedFeatures([[q.x-r, q.y-r], [q.x+r, q.y+r]], RS_LEAN ? {layers:lays, filter:["==", ["get", "__rs_k"], 1]} : {layers:lays}).forEach(f=>{
      if(RS_LEAN) f=_roadOfPiece(f);
      if(f.id==null || cand.some(c=>c.f.id===f.id)) return;
      const o=_svOnEdge(f, ll); if(o) cand.push(o); });
    // the direction they walked (else look) first, then the nearest: a divided road's other
    // carriageway can be nearer the camera than its own, but it runs the wrong way
    const dir=walk!=null ? walk : look;
    // and at a crossing the road that goes on the way they walked, not the one across it:
    // every 10 degrees off that way weighs like 2 m further
    const score=c=>c.d+off(c.h, dir)/5+(off(c.h, dir)>100 ? 1000 : 0);
    cand.sort((a, b)=>score(a)-score(b));
    if(cand.length) best=cand[0];
  }
  // a road id is its index (generateId); a full-geometry feature may carry it as a string
  if(best && best.d<=_SV_SNAP_M){ _svPos={f:best.f, m:best.m, id:Number(best.f.id)}; _svFree={h:look}; }
  else _svFree={c:[ll.lng, ll.lat], h:look};
  _svMark(); _svSpotEvent();
  if(_svMarkOn){ const c=_svFree.c || _svAt(_svPos.f, _svPos.m).c; _svKeepInView(c[0], c[1]); } }
export function rsSetStreetViewMarker(on){ _svMarkOn=!!on; _svMark(); }
// move the Street View spot m metres along its edge (negative: back), still looking along it;
// stops at the edge's ends. Fires rs:streetviewmove {id, streetView, atStart, atEnd}.
export function rsStreetViewStep(m){
  if(!_svPos) return null;
  const p=_svAt(_svPos.f, _svPos.m+m); if(!p) return null;
  _svFree=null; _svLast=null; _svPos.m=p.m; _svMark(); const url=_svUrlOf(p);
  _svKeepInView(p.lng, p.lat);                  // keep the marker on screen while walking
  _emit("rs:streetviewmove", {id:_svPos.id, streetView:url, atStart:p.m<=0.01, atEnd:p.m>=p.len-0.01});
  _svSpotEvent();
  return url; }
// WHERE THE STREET VIEW SPOT IS, for placing something at an exact spot and direction:
// {id, properties, m, len, lng, lat, heading, roadHeading, onRoad, source} or null.
// source "panorama": a Street View that reports its moves put it there (Linked) - current.
// source "map": a click or a step put it there - in the keyless embed (Classic) the viewer may
// have walked on since, and nothing tells the page. lng/lat: the lane point Google is asked for
// (on a road), else where the panorama stands; m: metres along the edge's drawn line from its
// start; heading: where the viewer looks (the road's direction until a panorama reports one).
export function rsGetStreetViewSpot(){
  if(_svFree && _svFree.c)
    return {id:null, properties:null, m:null, len:null, lng:_svFree.c[0], lat:_svFree.c[1],
            heading:_svFree.h, roadHeading:null, onRoad:false, source:"panorama"};
  if(!_svPos) return null;
  const p=_svAt(_svPos.f, _svPos.m); if(!p) return null;
  return {id:_svPos.id, properties:_svPos.f.properties||{}, m:p.m, len:p.len, lng:p.lng, lat:p.lat,
          heading:_svFree ? _svFree.h : p.h, roadHeading:p.h, onRoad:true, source:_svFree ? "panorama" : "map"}; }
// the same, as an event on every change: a pick, a step, a walk or turn in the panorama
function _svSpotEvent(){
  _emit("rs:streetviewspot", rsGetStreetViewSpot()); }
export function _sv(ll, f){
  const u = _svUrl(ll, f);
  if(u && _svWindow)                          // the window mode opens its window, not a new tab
    return '<div class="rs-sv" style="margin-top:4px"><a href="#" onclick="rsSetStreetView(true);return false">Street View</a></div>';
  return !u ? "" : '<div class="rs-sv" style="margin-top:4px"><a target="_blank" rel="noopener" href="'+
    _esc(u)+'">Street View &#8599;</a></div>'; }
export function useSpot(){ _streetView = !!O.street_view; RS_FILL_LAYERS = O.fill_layers.map(id=>RS_PREFIX+id); }      // the style's fill layers: a later style has its own
export function initSpot(){
  useSpot();
  window.rsSetStreetViewMarkerAt = rsSetStreetViewMarkerAt;
  map.on("move", _svMarkPlace);                   // zoom / rotate / pitch change the drawn offset
  window.rsGetStreetViewSpot = rsGetStreetViewSpot;
  window.rsSetStreetViewMarker = rsSetStreetViewMarker; window.rsStreetViewStep = rsStreetViewStep;
}

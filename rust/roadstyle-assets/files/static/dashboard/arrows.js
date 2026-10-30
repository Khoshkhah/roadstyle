// oneway direction-arrow icon (openstreetmap-carto)
import {map, style, O, RS_LOADED, _src, _sfeats, RoadTable} from "./core.js";
import {_tunOn} from "./tunnel.js";
import {_svLanePx} from "./svspot.js";
let _arSdf = null;         // the icon on the map is an SDF one (a map with tunnels) or not
export function addArrow(){
  if(map.hasImage("oneway")){ if(_arSdf === _tunOn) return; map.removeImage("oneway"); }       // a later style with tunnels (or with none) needs the other kind
  // rasterised large (the profile's arrows.icon, 4x by default): the high-zoom size ramp scales the icon up to ~10x, and a 2x raster
  // turns to mush past ~2x
  const I=O.arrow_icon;     // the profile's arrows.icon
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+I.width+'" height="'+I.height+'" viewBox="0 0 '+I.view_box.join(" ")+'">'
    +'<path d="'+I.path+'" fill="'+O.arrow_color+'"/></svg>';
  const img=new Image(I.width,I.height);
  // a map with tunnels: an SDF icon (white), coloured by the arrow layers' icon-color, so the tunnel slider can fade a tunnel's arrows
  // (one symbol layer cannot mix SDF and plain icons)
  img.onload=()=>{ if(!map.hasImage("oneway")){ _arSdf = _tunOn; map.addImage("oneway",img,{pixelRatio:I.pixel_ratio, sdf:_tunOn}); } };
  img.src="data:image/svg+xml;base64,"+btoa(_tunOn ? svg.replace(/fill="[^"]*"/, 'fill="#ffffff"') : svg);
}
// one arrow per one-way road in the window (docs/design/arrows_and_names.md): after every move, each one-way chain of the slots (the
// pieces with the same "chain") gets ONE point in the middle of its part inside the window, rotated along the road, with the properties of
// the piece it lies on (so the arrow layers' filters, rsFilter and the class / tunnel toggles treat it as before). Repeating the icon along
// every 100 m slot crowded zoom 15; one arrow per stretch (line-center) was often outside the window. An arrow STAYS where it is
// while it is still in the window (re-centring after every pan slid it along its road); only a chain whose arrow left, or a newly
// visible one, gets a new place. Thinned (2026-10-06): below zoom 17 only the main classes; a road whose visible part is shorter
// than 100 px gets none; arrows stay 150 px apart (an arrow already shown keeps its place, then the higher class wins).
export const _rsArrowAt = new Map();                  // chain -> its arrow feature now
// the one-way direction of a two-half pair (cars one way, a bus / bike lane the other: 2026-10-09): its arrow in the middle of its own
// half as drawn at this zoom, right of travel by the half's offset (roads-fill's line-offset, _svLanePx), not on the pair's centre line.
// ft._c is the point on the centre line, ft._a -> ft._z the chain's segment there (the travel direction)
function _rsArrowLane(ft){
  const p = RoadTable.props(ft.id), px = p.__rs_twoway ? _svLanePx(p) : 0;
  if(!px){ ft.geometry.coordinates = ft._c; return ft; }
  const a = map.project(ft._a), b = map.project(ft._z), c = map.project(ft._c);
  const dx = b.x - a.x, dy = b.y - a.y, n = Math.hypot(dx, dy) || 1;     // screen: y down, right of travel = (-dy, dx)
  const ll = map.unproject([c.x - dy / n * px, c.y + dx / n * px]);
  ft.geometry.coordinates = [ll.lng, ll.lat]; return ft;
}
let _RS_ARROW = null;     // the profile's arrows.place, main_below and main, and labels.base_size
// the one-way slots, indexed once for each slots data (N12): each piece's line and box, and each chain's pieces; made again when the data
// changes (a new array of features: setData, or the level editor's update)
let _slotIdx = {fs: null, pieces: [], chains: new Map()};
// the class text of a name or arrow slot: a GeoJSON source has `highway`, a tile has `__rs_ci` (the place of the class in the style's `roadstyle:classes`)
function _slotClass(p){ return p.highway != null ? p.highway : (((style && style.metadata) || {})["roadstyle:classes"] || [])[p.__rs_ci]; }
function _slotIndex(){
  const fs = _sfeats((_src("slots")||{}).source);
  if(_slotIdx.fs === fs) return _slotIdx;
  const pieces = [], chains = new Map();
  for(const f of fs){
    const p = f.properties || {}; if(!p.oneway) continue;
    const c = f.geometry && f.geometry.coordinates; if(!c) continue;
    const box = [Infinity, Infinity, -Infinity, -Infinity];
    for(const [x, y] of c){ if(x < box[0]) box[0] = x; if(y < box[1]) box[1] = y; if(x > box[2]) box[2] = x; if(y > box[3]) box[3] = y; }
    const q = {c: c, p: p, box: box, main: _RS_ARROW.main.has(String(_slotClass(p) || "").replace(/_link$/, ""))};
    pieces.push(q);
    if(!chains.has(p.chain)) chains.set(p.chain, []);
    chains.get(p.chain).push(q);
  }
  return _slotIdx = {fs: fs, pieces: pieces, chains: chains};
}
export function _rsArrows(){
  // the style's arrows (roadstyle:arrows): "points", one arrow per one-way chain placed here, on the arrows source; "line" or "line-center": the
  // style's own symbol layers place them. A style without the key: points when it has an arrows source.
  const kind = O.arrows !== undefined ? O.arrows : (style.metadata || {})["roadstyle:arrows"]; if(kind !== undefined && kind !== "points") return;
  const src = _src("arrows") && map.getSource(_src("arrows").source); if(!src) return;
  const out = [];
  if(map.getZoom() >= 15){
    const bb = map.getBounds(), W = bb.getWest(), E = bb.getEast(), S = bb.getSouth(), N = bb.getNorth();
    const ctr = map.getCenter(), kx = Math.cos(ctr.lat * Math.PI / 180);   // degrees of longitude to the scale of latitude
    // pixels per degree of latitude at the center, from the zoom: the projection of a tilted (3D) map squashes the vertical pixels (8 times at zoom 17),
    // and every road looked too short for an arrow
    const pxPerDeg = 111320 / (78271.51696 * Math.cos(ctr.lat * Math.PI / 180) / Math.pow(2, map.getZoom()));
    const mainOnly = map.getZoom() < _RS_ARROW.mainBelow;
    const vis = new Map(), pieces = new Map();                   // chain -> its visible parts [{slot, lo, hi}] / its pieces [{slot, c, cum, len, p}]
    // only the pieces whose box meets the window, and the lengths only of the chains in view (N12): the one-way slots' index
    const idx = _slotIndex(), seen = [];
    for(const q of idx.pieces) if(q.box[0] <= E && q.box[2] >= W && q.box[1] <= N && q.box[3] >= S && (!mainOnly || q.main)) seen.push(q);
    const measure = q => {                                       // lengths along the piece, in degrees of latitude (the view's scale)
      const c = q.c, cum = [0];
      for(let i = 0; i < c.length - 1; i++) cum.push(cum[i] + Math.hypot((c[i + 1][0] - c[i][0]) * kx, c[i + 1][1] - c[i][1]));
      return {slot: q.p.slot, c: c, cum: cum, len: cum[cum.length - 1], p: q.p}; };
    for(const q of seen) if(!pieces.has(q.p.chain)) pieces.set(q.p.chain, idx.chains.get(q.p.chain).map(measure));
    for(const q of seen){
      const p = q.p, c = q.c, cum = pieces.get(p.chain).find(u => u.slot === p.slot && u.c === c).cum;
      for(let i = 0; i < c.length - 1; i++){
        let [x0, y0] = c[i], [x1, y1] = c[i + 1], t0 = 0, t1 = 1;   // Liang-Barsky: the part of the segment inside the window
        const dx = x1 - x0, dy = y1 - y0, P = [-dx, dx, -dy, dy], Q = [x0 - W, E - x0, y0 - S, N - y0];
        let ok = true;
        for(let j = 0; j < 4 && ok; j++){
          if(P[j] === 0){ if(Q[j] < 0) ok = false; }
          else { const r = Q[j] / P[j]; if(P[j] < 0){ if(r > t1) ok = false; else if(r > t0) t0 = r; } else { if(r < t0) ok = false; else if(r < t1) t1 = r; } }
        }
        if(!ok || t1 <= t0) continue;
        const seg = cum[i + 1] - cum[i];
        if(!vis.has(p.chain)) vis.set(p.chain, []);
        vis.get(p.chain).push({slot: p.slot, lo: cum[i] + t0 * seg, hi: cum[i] + t1 * seg});
      }
    }
    const inside = q => q[0] >= W && q[0] <= E && q[1] >= S && q[1] <= N;
    // the names' text: 10 px at zoom 14 to 14 px at zoom 18 (the label layers), about 0.6 em a letter
    const bs = _RS_ARROW.baseSize, fontPx = bs[0][1] + (bs[1][1] - bs[0][1]) * Math.min(Math.max((map.getZoom() - bs[0][0]) / (bs[1][0] - bs[0][0]), 0), 1);
    const margin = _RS_ARROW.edgePx / pxPerDeg;
    const cand = [];                                             // {ft, chain, kept, rank, len}
    for(const [chain, segs] of vis){
      const P = pieces.get(chain).sort((u, v) => u.slot - v.slot);
      let full = 0; const offOf = new Map();
      for(const q of P){ q.off = full; offOf.set(q.slot, full); full += q.len; }
      const iv = segs.map(g => [offOf.get(g.slot) + g.lo, offOf.get(g.slot) + g.hi]).sort((u, v) => u[0] - v[0]);   // visible, along the chain
      const total = iv.reduce((t, r) => t + r[1] - r[0], 0);
      if(total * pxPerDeg < _RS_ARROW.minLenPx) continue;        // too short on screen
      const kept = _rsArrowAt.get(chain);
      if(kept && inside(kept._c)){ cand.push({ft: kept, chain: chain, kept: 1, rank: kept.properties.rank || 0, len: total}); continue; }
      let h = total / 2, mid = iv[0][0];                         // the middle of the visible part, along the chain
      for(const [lo, hi] of iv){ if(h > hi - lo){ h -= hi - lo; continue; } mid = lo + h; break; }
      // where the arrow may go (arrows overlapped the names): an unnamed road, the middle of its visible part; a named one, the
      // middle of an odd slot (names sit in the middle of the even ones) or just past either end of a name; of those in the window, the
      // one nearest the middle. None in the window (the road is too short there for its name and an arrow): the name wins, no arrow.
      const name = P[0].p.name, spots = [];
      if(!name) spots.push(mid);
      else {
        const half = (String(name).length * fontPx * _RS_ARROW.charWidth / 2 + _RS_ARROW.nameGapPx) / pxPerDeg;
        for(const q of P){ const m = q.off + q.len / 2; if(q.slot % 2) spots.push(m); else spots.push(m - half, m + half); }
      }
      let best = null;
      for(const d of spots)
        if(d >= 0 && d <= full && iv.some(r => d >= r[0] + margin && d <= r[1] - margin) && (best === null || Math.abs(d - mid) < Math.abs(best - mid))) best = d;
      if(best === null) continue;
      const q = P.find(u => best <= u.off + u.len) || P[P.length - 1], local = best - q.off;
      let i = 0; while(i < q.c.length - 2 && q.cum[i + 1] < local) i++;
      const a = q.c[i], z = q.c[i + 1], t = (local - q.cum[i]) / ((q.cum[i + 1] - q.cum[i]) || 1);
      const x = a[0] + (z[0] - a[0]) * t, y = a[1] + (z[1] - a[1]) * t;
      const ang = -Math.atan2(z[1] - a[1], (z[0] - a[0]) * kx) * 180 / Math.PI;   // the icon points east; clockwise degrees
      const ft = {type: "Feature", properties: Object.assign({}, q.p, {b: ang}), geometry: {type: "Point", coordinates: [x, y]}, _c: [x, y], _a: a, _z: z};
      cand.push({ft: ft, chain: chain, kept: 0, rank: q.p.rank || 0, len: total});
    }
    // at least minGapPx apart: an arrow already shown first (no jumps while panning), then the higher class, then the longer road
    // ponytail: O(arrows^2) on the few hundred arrows of a window; a screen grid if a window ever holds thousands
    cand.sort((u, v) => (v.kept - u.kept) || (v.rank - u.rank) || (v.len - u.len));
    const shown = [], gap2 = _RS_ARROW.minGapPx * _RS_ARROW.minGapPx;
    _rsArrowAt.clear();
    for(const c of cand){
      const q = map.project(_rsArrowLane(c.ft).geometry.coordinates);
      if(shown.some(s => (s.x - q.x) ** 2 + (s.y - q.y) ** 2 < gap2)) continue;
      shown.push(q); out.push(c.ft); _rsArrowAt.set(c.chain, c.ft);
    }
  }
  if(map.getZoom() < 15) _rsArrowAt.clear();
  src.setData({type: "FeatureCollection", features: out});
}
let _rsSlotsN = -1;     // the slots arrive (inflated) after load: place the arrows once they are there, not on every tile event
let _arBound = false;
// the arrows of the style of the moment: at the start, and again for a new style (rs.setStyle; a style that has no arrow_icon has none)
export function initArrows(){
  if(!O.arrow_icon) return;   // no arrow_icon: the host adds the "oneway" image itself (the Rust engine: the style's metadata roadstyle:images)
  _RS_ARROW = {...O.arrow_rules, main: new Set(O.arrow_rules.main)};
  _rsSlotsN = -1;
  if(!_arBound){
    _arBound = true;
    map.on("moveend", _rsArrows);
    map.on("sourcedata", e => { const s = _src("slots"); if(!s || e.sourceId !== s.source) return; const n = _sfeats(s.source).length; if(n !== _rsSlotsN){ _rsSlotsN = n; _rsArrows(); } });
    map.on("styleimagemissing", e=>{ if(e.id==="oneway") addArrow(); });
  }
  const go = () => { addArrow(); _rsArrows(); };
  RS_LOADED ? go() : map.once("load", go);
}

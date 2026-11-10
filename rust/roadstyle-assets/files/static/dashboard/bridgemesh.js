// THE 3D BRIDGE DECKS AS ONE SLOPED MESH. MapLibre's fill-extrusion has only flat tops, so a ramp drawn with it is a stair. This module draws
// the decks' features (the style's source `decks`, view_3d) as triangles of its own, in one custom layer: the top of a deck piece slopes from
// its start lift to its end lift (`__rs_lift0`, `__rs_lift1`, from 0 on the ground to 1 at the full height), with two side walls and a bottom.
// The fill-extrusion layers of the decks stay in the map with opacity 0: they are what a click and a hover pick, and the paint expression of
// each is the colour of the mesh (its feature state: select, hover, a highlight set, rsColor), read with the layer's own evaluate.
// THE GROUP HEIGHT: the bridge roads that touch through shared nodes are one group (`__rs_group`, made by the engine). rsSetBridgeHeight gives
// the whole group one full height in metres (the ramps at its free ends stay); a road's own deck is never set alone.
// THE TERRAIN: with the 3D terrain on, a deck is level between the ground heights at the two ends of its chain (`__rs_s0`, `__rs_s1`: where a piece is
// along its chain), and its ramps rise from the ground at each free end. The heights come from the terrain (map.queryTerrainElevation); a tile that has not
// come yet gives none, and the mesh is made again when the map is idle.
import {map, O, RS_PREFIX, style, _src, _sfeats, _emit} from "./core.js";

const _bmId = () => RS_PREFIX + "roads-bridge-mesh";
const _bmDeck = () => RS_PREFIX + "roads-bridge-decks", _bmCasing = () => RS_PREFIX + "roads-deck-casing";
const _bmM = 40075016.686;                           // the metres round the equator
const _bmLight = [-0.4, 0.5, 0.75];                  // the light of the walls (fixed on the map)
const _BM_VS = "attribute vec3 a_pos; attribute float a_shade; attribute vec4 a_col; uniform mat4 u_m; varying vec4 v_col;" +
  "void main(){ if(a_col.a < 0.004){ gl_Position = vec4(3.0, 3.0, 3.0, 1.0); v_col = vec4(0.0); return; }" +
  " gl_Position = u_m * vec4(a_pos, 1.0); v_col = vec4(a_col.rgb * a_shade * a_col.a, a_col.a); }";
const _BM_FS = "precision mediump float; varying vec4 v_col; void main(){ gl_FragColor = v_col; }";

let _bmFeats = [], _bmRanges = [], _bmN = 0;         // the decks' features, the vertices of each, the vertex count
let _bmOrig = new Map();                             // feature id -> [base, height] as the engine made them
let _bmHeights = new Map();                          // group -> the metres that the person set
let _bmShown = null;                                 // the ids of the features that the filters show (filter.js); null: all
let _bmGeom = true, _bmDirty = new Set(), _bmAll = true;
let _bmEnds = new Map(), _bmMiss = false, _bmRetry = 0;   // chain -> {za, zb} the ground at its two ends (terrain on), a height that was not there yet, the tries
let _bmGl = null, _bmProg = null, _bmBuf = {}, _bmLoc = {}, _bmOrigin = [0, 0], _bmOp = null, _bmPatched = null;

// the switch "3D bridges" (the state rs_bridges3d; the style's filters of the flat bridge and of the decks read it too)
const _bmOn = () => { try { return map.getGlobalState().rs_bridges3d !== false; } catch(e){ return true; } };
const _bmSrc = () => { const s = _src("decks"); return s ? s.source : null; };
const _bmMerc = (lon, lat) => [(lon + 180) / 360, 0.5 - Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / (2 * Math.PI)];

// the decks' full height in metres: the group's own when it was set, else the look's (`__rs_full`)
function _bmHeight(p){ const h = _bmHeights.get(p.__rs_group); return h == null ? p.__rs_full : h; }

// the colour (bytes) of feature k: the paint expression of its layer, with its properties and its feature state
function _bmColour(k){
  const f = _bmFeats[k], p = f.properties, lay = map.getLayer(p.__rs_casing_slab ? _bmCasing() : _bmDeck());
  if(!lay || !lay.paint) return [128, 128, 128, 255];
  const c = lay.paint.get("fill-extrusion-color").evaluate({type: 3, properties: p, id: k}, map.getFeatureState({source: _bmSrc(), id: k}));
  if(!c) return [128, 128, 128, 255];
  const a = c.a > 0 ? c.a : 0, u = a > 0 ? 1 / a : 0, op = (_bmOp == null ? 1 : _bmOp);
  return [c.r * u * 255, c.g * u * 255, c.b * u * 255, a * op * 255].map(v => Math.max(0, Math.min(255, Math.round(v))));
}

// the ground height (metres, as the terrain is drawn) at a point; 0 without terrain. A tile that has not come gives none: 0 now, and the mesh again later
const _bmElev = c => {
  if(!map.getTerrain()) return 0;
  const e = map.queryTerrainElevation({lng: c[0], lat: c[1]});
  if(e == null){ _bmMiss = true; return 0; }
  return e;
};
// the vertices of every feature: the position (metres from the origin, in mercator units), the shade of its face and, later, its colour
function _bmBuild(){
  const s = _bmSrc(); _bmFeats = s ? _sfeats(s) : []; _bmRanges = []; _bmIdx = null;
  const pos = [], shade = [], adj = [];     // adj: for each feature, the base and the top of its pick shape over the ground under it (terrain on)
  let o = null;
  // the ground at the two ends of each chain (the terrain on): the deck is level between them
  _bmEnds = new Map(); _bmMiss = false;
  if(map.getTerrain()){
    const e = new Map();
    _bmFeats.forEach(f => { const p = f.properties, r = f.geometry && f.geometry.coordinates && f.geometry.coordinates[0];
      if(p.__rs_casing_slab || !r || r.length < 5 || (r.length - 1) % 2) return;
      let c = e.get(p.__rs_chain); if(!c) e.set(p.__rs_chain, c = {sa: 2, sb: -1, a: null, b: null});
      if(p.__rs_s0 < c.sa){ c.sa = p.__rs_s0; c.a = r[0]; }
      if(p.__rs_s1 > c.sb){ c.sb = p.__rs_s1; c.b = r[(r.length - 1) / 2 - 1]; } });
    e.forEach((c, k) => _bmEnds.set(k, {za: _bmElev(c.a), zb: _bmElev(c.b)}));
  }
  const push = (x, y, z, sh) => { pos.push(x, y, z); shade.push(sh); };
  _bmFeats.forEach((f, k) => {
    const p = f.properties, ring = f.geometry && f.geometry.coordinates && f.geometry.coordinates[0], first = shade.length;
    adj[k] = null;
    if(!ring || ring.length < 5 || (ring.length - 1) % 2){ _bmRanges.push([first, first]); return; }
    const m = (ring.length - 1) / 2, H = _bmHeight(p), th = p.__rs_thick, cas = !!p.__rs_casing_slab;
    const A = [], B = [];
    for(let i = 0; i < m; i++){ A.push(ring[i]); B.push(ring[2 * m - 1 - i]); }
    if(!o) o = _bmMerc(A[0][0], A[0][1]);
    const cos = Math.cos(A[0][1] * Math.PI / 180), mz = 1 / (_bmM * cos);
    // the distance along the side A fixes where each vertex is between the lift at the start and at the end
    const cum = [0];
    for(let i = 1; i < m; i++) cum.push(cum[i - 1] + Math.hypot((A[i][0] - A[i - 1][0]) * cos, A[i][1] - A[i - 1][1]));
    const L = i => p.__rs_lift0 + (p.__rs_lift1 - p.__rs_lift0) * (cum[m - 1] > 0 ? cum[i] / cum[m - 1] : 0);
    // the slab thins out to nothing on the ground (twice as fast as the lift rises), so the top of a ramp lands flush with the road: no blunt end
    const thin = i => Math.min(1, 2 * L(i));
    const ce = _bmEnds.get(p.__rs_chain);          // the terrain on: the level line between the ground at the two ends of the chain
    const zg = i => ce ? ce.za + (ce.zb - ce.za) * (p.__rs_s0 + (p.__rs_s1 - p.__rs_s0) * (cum[m - 1] > 0 ? cum[i] / cum[m - 1] : 0)) : 0;
    const top = i => zg(i) + H * L(i) + (cas ? 0.35 * th : th) * thin(i), bot = i => zg(i) + Math.max(0, H * L(i) + (cas ? -0.5 : 0));
    if(ce){ const mid = m >> 1, g = _bmElev(A[mid]); adj[k] = [bot(mid) - g, top(mid) - g]; }
    const v = (c, z) => { const q = _bmMerc(c[0], c[1]); return [q[0] - o[0], q[1] - o[1], z * mz]; };
    const quad = (a, b, c, d, sh) => { [a, b, c, a, c, d].forEach(q => push(q[0], q[1], q[2], sh)); };
    for(let i = 0; i < m - 1; i++){
      quad(v(A[i], top(i)), v(A[i + 1], top(i + 1)), v(B[i + 1], top(i + 1)), v(B[i], top(i)), 1);            // the top, sloped
      // the bottom: not where the slab is thin (its bottom and its top are then in one place, and the card draws one or the other in teeth)
      if(top(i) - bot(i) > 0.3 || top(i + 1) - bot(i + 1) > 0.3) quad(v(A[i], bot(i)), v(A[i + 1], bot(i + 1)), v(B[i + 1], bot(i + 1)), v(B[i], bot(i)), 0.45);
      for(const S of [A, B]){                                                                                  // the two walls
        const dx = (S[i + 1][0] - S[i][0]) * cos, dy = S[i + 1][1] - S[i][1], d = Math.hypot(dx, dy) || 1;
        const sh = 0.6 + 0.3 * Math.abs((dy / d) * _bmLight[0] - (dx / d) * _bmLight[1]);
        quad(v(S[i], top(i)), v(S[i + 1], top(i + 1)), v(S[i + 1], bot(i + 1)), v(S[i], bot(i)), sh);
      }
    }
    _bmRanges.push([first, shade.length]);
  });
  _bmOrigin = o || [0, 0]; _bmN = shade.length;
  return {pos: new Float32Array(pos), shade: new Float32Array(shade), adj};
}

// the colour bytes of all the vertices (the ones in `ids` only, when they are given: a hover, a selection)
let _bmCol = new Uint8Array(0);
function _bmPaint(ids){
  if(_bmCol.length !== _bmN * 4) { _bmCol = new Uint8Array(_bmN * 4); ids = null; }
  const each = k => {
    const [a, b] = _bmRanges[k]; if(b <= a) return;
    const c = (_bmShown && !_bmShown.has(k)) ? [0, 0, 0, 0] : _bmColour(k);
    for(let v = a; v < b; v++) _bmCol.set(c, v * 4);
  };
  if(ids) ids.forEach(k => { if(_bmRanges[k]) each(k); }); else for(let k = 0; k < _bmRanges.length; k++) each(k);
}

// THE PICK SHAPES (the invisible extrusions) follow the mesh: their base and height are the engine's, scaled to the group's height; with the terrain on they are
// the mesh's own base and top over the ground under each piece. The data is set again only when a value changed (a half metre), so a terrain that
// loads more tiles cannot loop through the source's own data event.
function _bmSyncPickers(adj){
  const s = _bmSrc(), src = s && map.getSource(s);
  if(!src || !src.setData || !_bmFeats.length) return;
  const vals = _bmFeats.map((f, k) => {
    const p = f.properties; if(!_bmOrig.has(k)) _bmOrig.set(k, [p.__rs_base, p.__rs_height]);
    const [b0, h0] = _bmOrig.get(k), r = p.__rs_full ? _bmHeight(p) / p.__rs_full : 1, a = adj && adj[k];
    return a ? [Math.max(0, a[0]), Math.max(a[0] + 0.1, a[1])] : [b0 * r, h0 + b0 * (r - 1)];
  });
  const h = vals.map(v => Math.round(v[0] * 2) + "," + Math.round(v[1] * 2)).join(";");
  if(h === _bmPickHash) return;
  _bmPickHash = h;
  src.setData({type: "FeatureCollection", features: _bmFeats.map((f, k) => ({...f, properties: {...f.properties, __rs_base: vals[k][0], __rs_height: vals[k][1]}}))});
}
let _bmPickHash = "";

function _bmUpload(gl){
  if(_bmGeom){
    const g = _bmBuild();
    gl.bindBuffer(gl.ARRAY_BUFFER, _bmBuf.pos); gl.bufferData(gl.ARRAY_BUFFER, g.pos, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, _bmBuf.shade); gl.bufferData(gl.ARRAY_BUFFER, g.shade, gl.STATIC_DRAW);
    _bmGeom = false; _bmAll = true;
    _bmSyncPickers(g.adj);
  }
  if(_bmAll || _bmDirty.size){
    _bmPaint(_bmAll ? null : _bmDirty);
    gl.bindBuffer(gl.ARRAY_BUFFER, _bmBuf.col); gl.bufferData(gl.ARRAY_BUFFER, _bmCol, gl.DYNAMIC_DRAW);
    _bmAll = false; _bmDirty.clear();
  }
}

function _bmShader(gl, type, src){ const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
  if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("bridge mesh shader: " + gl.getShaderInfoLog(s)); return s; }

const _bmLayer = {
  type: "custom", renderingMode: "3d",
  onAdd(m, gl){
    _bmGl = gl; _bmProg = gl.createProgram();
    gl.attachShader(_bmProg, _bmShader(gl, gl.VERTEX_SHADER, _BM_VS)); gl.attachShader(_bmProg, _bmShader(gl, gl.FRAGMENT_SHADER, _BM_FS));
    gl.linkProgram(_bmProg);
    if(!gl.getProgramParameter(_bmProg, gl.LINK_STATUS)) throw new Error("bridge mesh program: " + gl.getProgramInfoLog(_bmProg));
    _bmLoc = {pos: gl.getAttribLocation(_bmProg, "a_pos"), shade: gl.getAttribLocation(_bmProg, "a_shade"), col: gl.getAttribLocation(_bmProg, "a_col"), m: gl.getUniformLocation(_bmProg, "u_m")};
    _bmBuf = {pos: gl.createBuffer(), shade: gl.createBuffer(), col: gl.createBuffer()};
    _bmGeom = true;
  },
  onRemove(m, gl){ for(const k in _bmBuf) gl.deleteBuffer(_bmBuf[k]); gl.deleteProgram(_bmProg); _bmProg = null; _bmBuf = {}; },
  render(gl, args){
    const deck = map.getLayer(_bmDeck());
    if(!_bmProg || !deck || map.getZoom() < (deck.minzoom || 0) || !_bmOn()) return;
    _bmUpload(gl);
    if(!_bmN) return;
    const M = (args && args.defaultProjectionData) ? args.defaultProjectionData.mainMatrix : args;
    // the model matrix: the mesh is in mercator units from its origin, so the origin's own translation goes into the matrix (in doubles)
    const [ox, oy] = _bmOrigin, T = new Float64Array(16);
    for(let i = 0; i < 16; i++) T[i] = M[i];
    for(let r = 0; r < 4; r++) T[12 + r] = M[r] * ox + M[4 + r] * oy + M[12 + r];
    gl.useProgram(_bmProg);
    gl.uniformMatrix4fv(_bmLoc.m, false, new Float32Array(T));
    const attr = (loc, buf, size, type, norm) => { gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, type, norm, 0, 0); };
    attr(_bmLoc.pos, _bmBuf.pos, 3, gl.FLOAT, false); attr(_bmLoc.shade, _bmBuf.shade, 1, gl.FLOAT, false); attr(_bmLoc.col, _bmBuf.col, 4, gl.UNSIGNED_BYTE, true);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true); gl.disable(gl.CULL_FACE);
    // two passes: the depth of the nearest face first, then its colour (a translucent deck is not drawn twice over itself)
    gl.disable(gl.BLEND); gl.colorMask(false, false, false, false); gl.drawArrays(gl.TRIANGLES, 0, _bmN);
    gl.colorMask(true, true, true, true); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.drawArrays(gl.TRIANGLES, 0, _bmN);
    gl.disableVertexAttribArray(_bmLoc.pos); gl.disableVertexAttribArray(_bmLoc.shade); gl.disableVertexAttribArray(_bmLoc.col);
  },
};

// the extrusions that stay as the pick shapes are invisible: the mesh is what is drawn
function _bmPickers(){
  [_bmDeck(), _bmCasing()].forEach(id => { if(map.getLayer(id)) map.setPaintProperty(id, "fill-extrusion-opacity", 0); });
}

function _bmEnsure(){
  const s = _bmSrc();
  if(!s || !map.getSource(s) || !map.getLayer(_bmDeck())) return;
  if(!map.getLayer(_bmId())){
    if(_bmOp == null){ const l = style.layers.find(l => RS_PREFIX + l.id === _bmDeck()), o = l && l.paint && l.paint["fill-extrusion-opacity"]; _bmOp = typeof o === "number" ? o : 1; }
    map.addLayer(Object.assign({id: _bmId()}, _bmLayer), _bmCasing() && map.getLayer(_bmCasing()) ? _bmCasing() : _bmDeck());
    _bmPickers(); _bmGeom = true;
  }
}

// the feature state and the paint that change a colour: only the feature that was set is painted again
function _bmPatch(){
  if(_bmPatched === map) return;
  _bmPatched = map;
  const fs = map.setFeatureState.bind(map), rm = map.removeFeatureState.bind(map);
  const touch = t => { if(t && t.source === _bmSrc()){ if(t.id == null) _bmAll = true; else _bmDirty.add(+t.id); map.triggerRepaint(); } };
  map.setFeatureState = (t, s) => { fs(t, s); touch(t); };
  map.removeFeatureState = (t, k) => { rm(t, k); touch(t); };
  const gs = map.setGlobalStateProperty.bind(map);
  map.setGlobalStateProperty = (k, v) => { gs(k, v); _bmAll = true; };
  const pp = map.setPaintProperty.bind(map);
  map.setPaintProperty = (id, k, v, o) => { const r = pp(id, k, v, o); if(k === "fill-extrusion-color" && (id === _bmDeck() || id === _bmCasing())) _bmAll = true; return r; };
}

// filter.js: the ids of the features that the road filters show (null: all of them)
export function _bmFilter(ids){ _bmShown = ids == null ? null : new Set(ids); _bmAll = true; if(map.getLayer(_bmId())) map.triggerRepaint(); }

export function initBridgeMesh(){
  _bmEnsure(); _bmPatch();
  map.on("styledata", () => { _bmEnsure(); });
  map.on("terrain", () => { _bmRetry = 0; _bmGeom = true; map.triggerRepaint(); });
  // a terrain height that was not there yet (its tile): make the mesh again once the map is idle, a few times at most
  map.on("idle", () => { if(_bmMiss && _bmRetry < 4){ _bmRetry++; _bmGeom = true; map.triggerRepaint(); } });
  map.on("sourcedata", e => { if(e.sourceId === _bmSrc() && e.sourceDataType !== "metadata"){ _bmGeom = true; } });
}
export const useBridgeMesh = () => { _bmOrig.clear(); _bmHeights.clear(); _bmPickHash = ""; _bmGeom = true; _bmAll = true; _bmEnsure(); };

// THE STREET VIEW MARKER on a bridge: the height (metres) of the deck top at a point of the bridge road `road` (its row), where the marker stands;
// 0 where the mesh is not drawn (flat below flat_below, the 3D terrain) or the road has no deck
let _bmIdx = null;                                   // road row -> its deck features
export function _bmDeckZ(lng, lat, road){
  const deck = map.getLayer(_bmDeck());
  if(road == null || !deck || !map.getLayer(_bmId()) || map.getZoom() < (deck.minzoom || 0) || !_bmOn()) return 0;
  _bmLoad();
  if(!_bmIdx){ _bmIdx = new Map(); _bmFeats.forEach(f => { if(f.properties.__rs_casing_slab) return;
    (f.properties.__rs_edges || []).forEach(r => { let a = _bmIdx.get(r); if(!a) _bmIdx.set(r, a = []); a.push(f); }); }); }
  const k = Math.cos(lat * Math.PI / 180); let best = null, bd = Infinity;
  for(const f of _bmIdx.get(road) || []){
    const r = f.geometry.coordinates[0], n = r.length - 1; let cx = 0, cy = 0;
    for(let i = 0; i < n; i++){ cx += r[i][0]; cy += r[i][1]; }
    const d = ((cx / n - lng) * k) ** 2 + (cy / n - lat) ** 2; if(d < bd){ bd = d; best = f.properties; } }
  if(!best) return 0;
  const L = (best.__rs_lift0 + best.__rs_lift1) / 2, ce = _bmEnds.get(best.__rs_chain);
  // the terrain on: the deck's level line there, as a height over the ground under the marker (the marker stands on the terrain)
  const zg = ce ? ce.za + (ce.zb - ce.za) * (best.__rs_s0 + best.__rs_s1) / 2 - _bmElev([lng, lat]) : 0;
  return zg + _bmHeight(best) * L + best.__rs_thick * Math.min(1, 2 * L);
}
// where a point at `metres` above the ground is on the screen, as a shift in pixels from the point on the ground
export function _bmScreenUp(lng, lat, metres){
  const tr = map.transform, c = maplibregl.MercatorCoordinate.fromLngLat([lng, lat]);
  const g = _bmElev([lng, lat]), a = tr.coordinatePoint(c, g), b = tr.coordinatePoint(c, g + metres);      // the elevation is in metres
  return [b.x - a.x, b.y - a.y];
}
const _bmLoad = () => { if(!_bmFeats.length){ const s = _bmSrc(); _bmFeats = s ? _sfeats(s) : []; _bmIdx = null; } };
// the groups: [{group, roads (the road rows), height (metres), set (the person gave it)}], largest first
export function rsBridgeGroups(){
  _bmLoad();
  const g = new Map();
  _bmFeats.forEach(f => { const p = f.properties; if(p.__rs_casing_slab) return;
    let e = g.get(p.__rs_group); if(!e) g.set(p.__rs_group, e = {group: p.__rs_group, roads: new Set(), height: p.__rs_full, set: false});
    (p.__rs_edges || []).forEach(r => e.roads.add(r)); });
  return [...g.values()].map(e => ({group: e.group, roads: [...e.roads], height: _bmHeights.has(e.group) ? _bmHeights.get(e.group) : e.height, set: _bmHeights.has(e.group)}))
    .sort((a, b) => b.roads.length - a.roads.length);
}
// the group of a target: a group number from rsBridgeGroups, or a road row of a bridge
function _bmGroupOf(t){
  const gs = rsBridgeGroups();
  const byRoad = gs.find(g => g.roads.includes(t));
  if(byRoad && !gs.some(g => g.group === t && g !== byRoad)) return byRoad.group;       // a road row (a group number that is also a row: the group wins)
  if(gs.some(g => g.group === t)) return t;
  return null;
}
// rsSetBridgeHeight(target, metres): the whole group of `target` (a group number or a road row; an array: each one) gets this full height;
// metres = null gives the look's height back. The roads of a group that touch are one height: no road of it is set alone.
export function rsSetBridgeHeight(target, metres){
  const list = Array.isArray(target) ? target : [target], done = [];
  if(metres != null && !(metres >= 0)) throw new Error("rsSetBridgeHeight: metres must be a number of 0 or more, or null, got " + JSON.stringify(metres));
  for(const t of list){
    const g = _bmGroupOf(t);
    if(g == null) throw new Error("rsSetBridgeHeight: " + JSON.stringify(t) + " is not a bridge group or the row of a bridge road");
    if(metres == null) _bmHeights.delete(g); else _bmHeights.set(g, +metres);
    done.push(g);
  }
  _bmGeom = true; map.triggerRepaint();
  _emit("rs:bridgeheightchange", {groups: done.map(g => ({group: g, height: _bmHeights.has(g) ? _bmHeights.get(g) : null}))});
  return done;
}
export function rsBridgeHeight(target){
  const g = _bmGroupOf(target); if(g == null) return null;
  const f = _bmFeats.find(f => f.properties.__rs_group === g && !f.properties.__rs_casing_slab);
  return _bmHeights.has(g) ? _bmHeights.get(g) : f ? f.properties.__rs_full : null;
}
// rsSetBridges3D(on): the bridges as 3D decks (a sloped mesh above the zoom of the look's flat_below) or as flat lines; no argument: whether they are 3D.
// A page made without view_3d has no decks: it stays flat and this does nothing.
export function rsSetBridges3D(on){
  if(on === undefined) return _bmHas() && _bmOn();
  if(!_bmHas()) return false;
  map.setGlobalStateProperty("rs_bridges3d", !!on); _bmAll = true; map.triggerRepaint();
  document.dispatchEvent(new CustomEvent("rs:bridges3dchange", {detail: {bridges3d: !!on}}));
  document.dispatchEvent(new CustomEvent("rs:bridgeheightchange", {detail: {}}));      // the Street View marker goes up or down with the deck
  return !!on;
}
// whether the page has 3D decks (it was made with view_3d)
export const _bmHas = () => !!_bmSrc() && !!map.getSource(_bmSrc());
export function initBridgeApi(){ window.rsSetBridges3D = rsSetBridges3D; window.rsBridgeGroups = rsBridgeGroups; window.rsSetBridgeHeight = rsSetBridgeHeight; window.rsBridgeHeight = rsBridgeHeight; }

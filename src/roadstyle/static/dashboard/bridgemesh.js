// THE 3D BRIDGE DECKS AS ONE SLOPED MESH. MapLibre's fill-extrusion has only flat tops, so a ramp drawn with it is a stair. This module draws
// the decks' features (the style's source `decks`, view_3d) as triangles of its own, in one custom layer: the top of a deck piece slopes from
// its start lift to its end lift (`__rs_lift0`, `__rs_lift1`, from 0 on the ground to 1 at the full height), with two side walls and a bottom.
// The fill-extrusion layers of the decks stay in the map with opacity 0: they are what a click and a hover pick, and the paint expression of
// each is the colour of the mesh (its feature state: select, hover, a highlight set, rsColor), read with the layer's own evaluate.
// THE GROUP HEIGHT: the bridge roads that touch through shared nodes are one group (`__rs_group`, made by the engine). rsSetBridgeHeight gives
// the whole group one full height in metres (the ramps at its free ends stay); a road's own deck is never set alone.
// THE TERRAIN: with the 3D terrain on, a deck is level between the ground heights at the two end nodes of its chain (`__rs_enda`, `__rs_endb`; `__rs_s0`, `__rs_s1`:
// where a piece is along its chain), and its ramps rise from the ground at each free end. The heights come from the terrain's tiles, read here (`_bmDemAt`).
import {map, O, RS_PREFIX, style, _src, _sfeats, _emit} from "./core.js";

const _bmId = () => RS_PREFIX + "roads-bridge-mesh";
const _bmDeck = () => RS_PREFIX + "roads-bridge-decks", _bmCasing = () => RS_PREFIX + "roads-deck-casing";
const _BM_CLEAR = 0.3, _BM_CLEAR_SLOPE = 2.5;       // metres above the terrain where the deck meets it: this, and this for each metre of slope
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
let _bmStat = {rows: 0, inverted: 0, tooThick: 0, underGround: 0, maxEndGap: 0, minEndClearance: 1e9};   // what the last build found wrong in its own vertices (`_bmStats`)
let _bmPosArr = null, _bmBounds = null;               // the vertices (mercator units from the origin) for the pick, and the bounds of each feature
let _bmGl = null, _bmProg = null, _bmBuf = {}, _bmLoc = {}, _bmOrigin = [0, 0], _bmOp = null, _bmPatched = null;

// the switch "3D bridges" (the state rs_bridges3d; the style's filters of the flat bridge and of the decks read it too)
// whether the mesh is what is drawn now (then a click and a hover are picked on it, not on the invisible extrusions)
export const _bmDrawn = () => { const d = map.getLayer(_bmDeck()); return !!d && !!map.getLayer(_bmId()) && map.getZoom() >= (d.minzoom || 0) && _bmOn() && _bmN > 0; };
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

// THE GROUND HEIGHT comes from the terrain's own tiles (the DEM of O.ontop.dem), read here and not from the map: map.queryTerrainElevation knows only the tiles of
// the screen, and a bridge is longer than the screen (the chain that has no height at its far end would not be drawn). The tiles are the ones that the map draws its terrain
// from (the same source, the same zoom limit), decoded as the map decodes them (Terrarium) and read with the map's own bilinear step, so a deck and the ground agree.
const _bmDemTiles = new Map();                       // "z/x/y" -> Float32Array(256 * 256) | "loading" | "failed"
const _bmDemTries = new Map();                       // "z/x/y" -> the tries that failed
function _bmDemTile(z, x, y){
  const k = z + "/" + x + "/" + y, t = _bmDemTiles.get(k);
  if(t) return t === "loading" || t === "failed" ? null : t;
  _bmDemTiles.set(k, "loading");
  const url = O.ontop.dem.tiles[0].replace("{z}", z).replace("{x}", x).replace("{y}", y);
  fetch(url).then(r => { if(!r.ok) throw new Error("HTTP " + r.status); return r.blob(); })
    .then(b => createImageBitmap(b, {colorSpaceConversion: "none"}))
    .then(img => {
      const cv = document.createElement("canvas"); cv.width = cv.height = 256;
      const cx = cv.getContext("2d", {willReadFrequently: true}); cx.drawImage(img, 0, 0);
      const px = cx.getImageData(0, 0, 256, 256).data, out = new Float32Array(65536);
      for(let i = 0; i < 65536; i++) out[i] = px[i * 4] * 256 + px[i * 4 + 1] + px[i * 4 + 2] / 256 - 32768;      // Terrarium
      _bmDemTiles.set(k, out); _bmGeom = true; map.triggerRepaint();
    })
    .catch(e => {
      // a network error is tried again (3 tries, a little later each); then the tile is given up and said so: the bridges that need it are not drawn on the terrain
      const tries = (_bmDemTries.get(k) || 0) + 1; _bmDemTries.set(k, tries);
      if(tries < 3){ _bmDemTiles.delete(k); setTimeout(() => { _bmGeom = true; map.triggerRepaint(); }, 1500 * tries); return; }
      _bmDemTiles.set(k, "failed");
      console.warn("roadstyle: a terrain tile did not come (" + url + "): " + e.message + "; the bridges that need it are not drawn on the terrain");
    });
  return null;
}
// the ground height in metres at a longitude and a latitude (the terrain's exaggeration included); null where a tile that it needs has not come. The step is the
// map's own (it equals map.queryTerrainElevation over the screen to the last digit): the pixel at its corner, a bilinear mix of four, and at the edge of a tile the
// pixels of the next tile.
function _bmDemAt(lng, lat){
  const z = O.ontop.dem.maxzoom, n = 2 ** z, la = lat * Math.PI / 180;
  const xf = (lng + 180) / 360 * n, yf = (1 - Math.log(Math.tan(la) + 1 / Math.cos(la)) / Math.PI) / 2 * n;
  const tx = Math.floor(xf), ty = Math.floor(yf), fx = (xf - tx) * 256, fy = (yf - ty) * 256, x0 = Math.floor(fx), y0 = Math.floor(fy), u = fx - x0, v = fy - y0;
  let miss = false;
  const at = (x, y) => {
    const t = _bmDemTile(z, tx + (x > 255 ? 1 : x < 0 ? -1 : 0), ty + (y > 255 ? 1 : y < 0 ? -1 : 0));
    if(!t){ miss = true; return 0; }
    return t[((y + 256) % 256) * 256 + ((x + 256) % 256)];
  };
  const e = (at(x0, y0) * (1 - u) + at(x0 + 1, y0) * u) * (1 - v) + (at(x0, y0 + 1) * (1 - u) + at(x0 + 1, y0 + 1) * u) * v;
  return miss ? null : e * ((map.getTerrain() && map.getTerrain().exaggeration) || 1);
}
// the ground height (metres) at a point; 0 without terrain; null where its tile has not come (the mesh is made again when the tile comes: a chain whose end has no
// height is not drawn, never drawn at 0)
const _bmElev = c => {
  if(!map.getTerrain()) return 0;
  const e = _bmDemAt(c[0], c[1]);
  if(e == null){ _bmMiss = true; return null; }
  return e;
};
// how far above the exact ground a deck stands where it meets the terrain (see the height of a vertex): more on a steep slope, where the terrain mesh differs most from the
// ground. The slope is read from the same tiles, 4 m to each side; null where a tile has not come
function _bmClearance(c){
  const dx = 4 / (111320 * Math.cos(c[1] * Math.PI / 180)), dy = 4 / 111320;
  const e1 = _bmDemAt(c[0] + dx, c[1]), e2 = _bmDemAt(c[0] - dx, c[1]), e3 = _bmDemAt(c[0], c[1] + dy), e4 = _bmDemAt(c[0], c[1] - dy);
  if(e1 == null || e2 == null || e3 == null || e4 == null){ _bmMiss = true; return null; }
  return _BM_CLEAR + _BM_CLEAR_SLOPE * Math.hypot((e1 - e2) / 8, (e3 - e4) / 8);
}
// the vertices of every feature: the position (metres from the origin, in mercator units), the shade of its face and, later, its colour
function _bmBuild(){
  const s = _bmSrc(); _bmFeats = s ? _sfeats(s) : []; _bmRanges = []; _bmIdx = null;
  const pos = [], shade = [], adj = [];     // adj: for each feature, the base and the top of its pick shape over the ground under it (terrain on)
  let o = null;
  // the ground at the two end nodes of each chain (the terrain on): the deck is level between them. The nodes are the engine's (`__rs_enda`, `__rs_endb`), the same
  // coordinates for the chains that meet at a node, so they agree on its height
  _bmEnds = new Map(); _bmMiss = false; _bmStat = {rows: 0, inverted: 0, tooThick: 0, underGround: 0, maxEndGap: 0, minEndClearance: 1e9};
  if(map.getTerrain()){
    const e = new Map();
    _bmFeats.forEach(f => { const p = f.properties; if(p.__rs_casing_slab || !(p.__rs_enda || p.__rs_endb)) return;
      let c = e.get(p.__rs_chain); if(!c) e.set(p.__rs_chain, c = {a: null, b: null});
      if(p.__rs_enda) c.a = p.__rs_enda;
      if(p.__rs_endb) c.b = p.__rs_endb; });
    e.forEach((c, k) => _bmEnds.set(k, {za: c.a ? _bmElev(c.a) : null, zb: c.b ? _bmElev(c.b) : null}));
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
    if(map.getTerrain() && (!ce || ce.za == null || ce.zb == null)){ _bmMiss = true; _bmRanges.push([first, first]); return; }    // no height yet: not drawn
    const zg = i => ce ? ce.za + (ce.zb - ce.za) * (p.__rs_s0 + (p.__rs_s1 - p.__rs_s0) * (cum[m - 1] > 0 ? cum[i] / cum[m - 1] : 0)) : 0;
    // THE HEIGHT OF A VERTEX: the ground under it (on each side of the deck's width: a hill slopes sideways too) blends into the level line plus the group's height as the lift
    // rises, so near the ground the deck follows the terrain (and is not buried on the uphill side) and from the plateau up it is level across its width; without terrain the
    // ground is 0 and this is H * lift. A small clearance keeps the start of the ramp above the terrain that the map draws (a mesh, a few centimetres from the exact ground,
    // more on a steep slope, which would otherwise win the depth test and hide the ramp); it fades out as the deck rises.
    const GS = [[], []], CL = [[], []];
    for(const [sd, side] of [[0, A], [1, B]]) for(let i = 0; i < m; i++){
      const g = ce ? _bmElev(side[i]) : 0, cl = ce ? _bmClearance(side[i]) : 0;
      if(g == null || cl == null){ _bmMiss = true; _bmRanges.push([first, first]); return; }
      GS[sd].push(g); CL[sd].push(cl);
    }
    const base = (i, sd) => { const s3 = L(i); return GS[sd][i] * (1 - s3) + (zg(i) + H) * s3 + CL[sd][i] * (1 - s3); };
    const top = (i, sd) => base(i, sd) + (cas ? 0.35 * th : th) * thin(i);
    const bot = (i, sd) => cas ? Math.max(ce ? -1e9 : 0, base(i, sd) - 0.5) : base(i, sd);       // below the ground on the terrain is inside the hill: hidden, not cut
    if(ce){ const mid = m >> 1, g = (GS[0][mid] + GS[1][mid]) / 2; adj[k] = [(bot(mid, 0) + bot(mid, 1)) / 2 - g, (top(mid, 0) + top(mid, 1)) / 2 - g]; }
    // the checks of the mesh (see _bmStats): a slab with its top under its bottom, a slab or a deck much thicker than it is made, a top under the ground
    for(let i = 0; i < m; i++) for(const sd of [0, 1]){
      const t = top(i, sd), bo = bot(i, sd), thick = t - bo, made = (cas ? 0.35 * th + 0.5 : th) + 0.01;
      if(thick < -0.01) _bmStat.inverted++;
      if(thick > made + 0.05) _bmStat.tooThick++;
      if(t < GS[sd][i] - 0.05) _bmStat.underGround++;
      if(!cas && L(i) < 1e-3){ _bmStat.maxEndGap = Math.max(_bmStat.maxEndGap, Math.abs(base(i, sd) - GS[sd][i] - CL[sd][i])); _bmStat.minEndClearance = Math.min(_bmStat.minEndClearance, base(i, sd) - GS[sd][i]); }      // a deck's free end is at the clearance above the ground
      _bmStat.rows++;
    }
    const v = (c, z) => { const q = _bmMerc(c[0], c[1]); return [q[0] - o[0], q[1] - o[1], z * mz]; };
    const quad = (a, b, c, d, sh) => { [a, b, c, a, c, d].forEach(q => push(q[0], q[1], q[2], sh)); };
    for(let i = 0; i < m - 1; i++){
      quad(v(A[i], top(i, 0)), v(A[i + 1], top(i + 1, 0)), v(B[i + 1], top(i + 1, 1)), v(B[i], top(i, 1)), 1);            // the top, sloped
      // the bottom: not where the slab is thin (its bottom and its top are then in one place, and the card draws one or the other in teeth)
      if(top(i, 0) - bot(i, 0) > 0.3 || top(i + 1, 0) - bot(i + 1, 0) > 0.3) quad(v(A[i], bot(i, 0)), v(A[i + 1], bot(i + 1, 0)), v(B[i + 1], bot(i + 1, 1)), v(B[i], bot(i, 1)), 0.45);
      for(const [sd, S] of [[0, A], [1, B]]){                                                                                  // the two walls
        const dx = (S[i + 1][0] - S[i][0]) * cos, dy = S[i + 1][1] - S[i][1], d = Math.hypot(dx, dy) || 1;
        const sh = 0.6 + 0.3 * Math.abs((dy / d) * _bmLight[0] - (dx / d) * _bmLight[1]);
        quad(v(S[i], top(i, sd)), v(S[i + 1], top(i + 1, sd)), v(S[i + 1], bot(i + 1, sd)), v(S[i], bot(i, sd)), sh);
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
    const g = _bmBuild(); _bmPosArr = g.pos; _bmBounds = null;
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
  map.on("idle", () => {
    if(!_bmMiss) return;
    if(_bmRetry < 30){ _bmRetry++; _bmGeom = true; map.triggerRepaint(); }
    else if(_bmRetry++ === 30) console.warn("roadstyle: some bridges are not drawn on the terrain: the ground height at their ends did not come (the terrain tiles)");
  });
  map.on("sourcedata", e => { if(e.sourceId === _bmSrc() && e.sourceDataType !== "metadata"){ _bmGeom = true; } });
}
export const useBridgeMesh = () => { _bmOrig.clear(); _bmHeights.clear(); _bmPickHash = ""; _bmGeom = true; _bmAll = true; _bmEnsure(); };

// THE STREET VIEW MARKER on a bridge: the height (metres) of the deck top at a point of the bridge road `road` (its row), where the marker stands;
// 0 where the mesh is not drawn (flat below flat_below, the 3D terrain) or the road has no deck
let _bmIdx = null;                                   // road row -> its deck features
export function _bmDeckZ(lng, lat, road){
  const deck = map.getLayer(_bmDeck());
  if(road == null || !deck || !map.getLayer(_bmId()) || map.getZoom() < (deck.minzoom || 0) || !_bmOn()) return null;
  _bmLoad();
  if(!_bmIdx){ _bmIdx = new Map(); _bmFeats.forEach(f => { if(f.properties.__rs_casing_slab) return;
    (f.properties.__rs_edges || []).forEach(r => { let a = _bmIdx.get(r); if(!a) _bmIdx.set(r, a = []); a.push(f); }); }); }
  const k = Math.cos(lat * Math.PI / 180); let best = null, bd = Infinity;
  for(const f of _bmIdx.get(road) || []){
    const r = f.geometry.coordinates[0], n = r.length - 1; let cx = 0, cy = 0;
    for(let i = 0; i < n; i++){ cx += r[i][0]; cy += r[i][1]; }
    const d = ((cx / n - lng) * k) ** 2 + (cy / n - lat) ** 2; if(d < bd){ bd = d; best = f.properties; } }
  if(!best) return null;
  const L = (best.__rs_lift0 + best.__rs_lift1) / 2, ce = _bmEnds.get(best.__rs_chain);
  // the terrain on: the deck's level line there, as a height over the ground under the marker (the marker stands on the terrain)
  const here = _bmElev([lng, lat]);
  if(ce && (ce.za == null || ce.zb == null || here == null)) return null;      // no height yet: not on the deck
  // the deck's height over the ground under the marker: the ground blends into the level line plus the group's height by the lift (as the mesh does)
  const level = ce ? ce.za + (ce.zb - ce.za) * (best.__rs_s0 + best.__rs_s1) / 2 : 0, rise = (level + _bmHeight(best) - (ce ? here : 0)) * L + (ce ? (_bmClearance([lng, lat]) ?? _BM_CLEAR) * (1 - L) : 0);
  return rise + best.__rs_thick * Math.min(1, 2 * L);
}
// where a point at `metres` above sea level is on the screen (CSS px), drawn as the mesh is: with the matrix that the mesh layer gets
export function _bmProject(lng, lat, metres){
  const M = map.transform.getProjectionDataForCustomLayer(false).mainMatrix, mc = maplibregl.MercatorCoordinate.fromLngLat([lng, lat]), z = metres * mc.meterInMercatorCoordinateUnits();
  const cx = M[0] * mc.x + M[4] * mc.y + M[8] * z + M[12], cy = M[1] * mc.x + M[5] * mc.y + M[9] * z + M[13], cw = M[3] * mc.x + M[7] * mc.y + M[11] * z + M[15];
  const c = map.getCanvas();
  return [(cx / cw * 0.5 + 0.5) * c.clientWidth, (0.5 - cy / cw * 0.5) * c.clientHeight];
}
// where the deck of the road `road` (a row) is on the screen at a point of it; null where the mesh is not drawn (or its ground height has not come)
export function _bmDeckScreen(lng, lat, road){
  const z = _bmDeckZ(lng, lat, road), g = _bmElev([lng, lat]);
  return z == null || g == null ? null : _bmProject(lng, lat, g + z);
}
// where a point at `metres` above the ground is on the screen, as a shift in pixels from the point on the ground: the difference of two points drawn with the mesh's own matrix
export function _bmScreenUp(lng, lat, metres){
  const g = _bmElev([lng, lat]) ?? 0, a = _bmProject(lng, lat, g), b = _bmProject(lng, lat, g + metres);
  return [b[0] - a[0], b[1] - a[1]];
}
const _bmLoad = () => { if(!_bmFeats.length){ const s = _bmSrc(); _bmFeats = s ? _sfeats(s) : []; _bmIdx = null; } };
// THE PICK ON THE MESH: the deck piece that is under a screen point, the one nearest to the camera. The extrusions that MapLibre draws as pick shapes stand on the terrain by
// their own rule, a few metres from the mesh, so with the terrain on the pick is made on the mesh's own triangles, projected with the matrix that draws them.
function _bmMatrix(){
  const M = map.transform.getProjectionDataForCustomLayer(false).mainMatrix, T = new Float64Array(16);
  for(let i = 0; i < 16; i++) T[i] = M[i];
  for(let r = 0; r < 4; r++) T[12 + r] = M[r] * _bmOrigin[0] + M[4 + r] * _bmOrigin[1] + M[12 + r];
  return T;
}
function _bmFeatureBounds(){                          // the centre and the radius of each feature's vertices
  if(_bmBounds) return _bmBounds;
  _bmBounds = _bmRanges.map(([a, b]) => {
    if(b <= a) return null;
    let x = 0, y = 0, z = 0; for(let v = a; v < b; v++){ x += _bmPosArr[v * 3]; y += _bmPosArr[v * 3 + 1]; z += _bmPosArr[v * 3 + 2]; }
    const n = b - a; x /= n; y /= n; z /= n; let r = 0;
    for(let v = a; v < b; v++) r = Math.max(r, Math.hypot(_bmPosArr[v * 3] - x, _bmPosArr[v * 3 + 1] - y, _bmPosArr[v * 3 + 2] - z));
    return [x, y, z, r];
  });
  return _bmBounds;
}
function _bmPickPoint(px, py, T, W, H){
  const bounds = _bmFeatureBounds(), P = _bmPosArr; let best = -1, bw = Infinity;
  const proj = (x, y, z) => { const cw = T[3] * x + T[7] * y + T[11] * z + T[15]; if(cw <= 0) return null;
    return [((T[0] * x + T[4] * y + T[8] * z + T[12]) / cw * 0.5 + 0.5) * W, (0.5 - (T[1] * x + T[5] * y + T[9] * z + T[13]) / cw * 0.5) * H, cw]; };
  for(let k = 0; k < bounds.length; k++){
    const bd = bounds[k]; if(!bd) continue;
    const f = _bmFeats[k]; if(!f || f.properties.__rs_casing_slab || (_bmShown && !_bmShown.has(k))) continue;
    const c = proj(bd[0], bd[1], bd[2]); if(!c) continue;
    const e = proj(bd[0] + bd[3], bd[1], bd[2]), e2 = proj(bd[0], bd[1] + bd[3], bd[2]), e3 = proj(bd[0], bd[1], bd[2] + bd[3]);
    const rpx = Math.max(e ? Math.hypot(e[0] - c[0], e[1] - c[1]) : 0, e2 ? Math.hypot(e2[0] - c[0], e2[1] - c[1]) : 0, e3 ? Math.hypot(e3[0] - c[0], e3[1] - c[1]) : 0) * 1.5 + 4;
    if(Math.hypot(px - c[0], py - c[1]) > rpx) continue;
    const [a, b] = _bmRanges[k];
    for(let v = a; v + 2 < b; v += 3){
      const A = proj(P[v * 3], P[v * 3 + 1], P[v * 3 + 2]), B = proj(P[v * 3 + 3], P[v * 3 + 4], P[v * 3 + 5]), C = proj(P[v * 3 + 6], P[v * 3 + 7], P[v * 3 + 8]);
      if(!A || !B || !C) continue;
      const d = (B[1] - C[1]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[1] - C[1]); if(Math.abs(d) < 1e-9) continue;
      const u = ((B[1] - C[1]) * (px - C[0]) + (C[0] - B[0]) * (py - C[1])) / d, w = ((C[1] - A[1]) * (px - C[0]) + (A[0] - C[0]) * (py - C[1])) / d, t = 1 - u - w;
      if(u < 0 || w < 0 || t < 0) continue;
      const depth = u * A[2] + w * B[2] + t * C[2];
      if(depth < bw){ bw = depth; best = k; }
    }
  }
  return best;
}
// the feature that MapLibre would give for the deck under the screen point `p` ({x, y}), or null: the point first, then a box of 4 px (as the pick of select.js does)
export function _bmPickAt(p){
  if(!_bmDrawn() || !_bmPosArr) return null;
  const c = map.getCanvas(), T = _bmMatrix(), W = c.clientWidth, H = c.clientHeight;
  let k = _bmPickPoint(p.x, p.y, T, W, H);
  for(const [dx, dy] of [[4, 0], [-4, 0], [0, 4], [0, -4]]){ if(k >= 0) break; k = _bmPickPoint(p.x + dx, p.y + dy, T, W, H); }
  if(k < 0) return null;
  const f = _bmFeats[k];
  return {type: "Feature", id: k, properties: f.properties, geometry: f.geometry, layer: map.getLayer(_bmDeck()), source: _bmSrc(), state: {}};
}

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
// what the last build found wrong in its own vertices: {rows, inverted (a slab whose top is under its bottom), tooThick, underGround (a top under the ground), maxEndGap (metres between a free end and the ground plus the clearance), minEndClearance (the least height of a free end above the ground)}; for the tests
export const _bmStats = () => ({..._bmStat});
export function initBridgeApi(){ window.rsSetBridges3D = rsSetBridges3D; window.rsBridgeGroups = rsBridgeGroups; window.rsSetBridgeHeight = rsSetBridgeHeight; window.rsBridgeHeight = rsBridgeHeight; }

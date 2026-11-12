// THE 3D ROAD TILES (docs/design/scene_3d_tiles.md). A PMTiles archive of GLB files (SimReady's `<area>.page.pmtiles`: one GLB for each zoom-16 map tile, with the
// parts `roads`, `kerbs`, `markings` and `structures` as the children of the root node) is drawn as triangles in one MapLibre custom layer, as bridgemesh.js draws the
// bridge decks. The page option `scene_3d` (rust/roadstyle/src/scene3d.rs) gives the archive's address, its parts, its CRS and its ground id; the page's `ground` must be that ground.
//
// A vertex of a tile is (east - origin.x, height, -(north - origin.y)) in metres of the archive's CRS (the GLB's root `extras.simready`). Each vertex is converted
// to Web Mercator on the CPU, once, when its tile is read (the inverse of the CRS: `_s3Inv`; the parameters are rows of data/crs.json). The height is metres above the datum of the
// ground, drawn as height x the terrain's exaggeration, so the layer needs the 3D terrain, and the terrain's mesh is lower than the exact ground in places: the whole scene is lifted by
// `ontop.scene_3d.lift_m`. Measured on Monaco: with no lift only 0.3 to 6 % of the road pixels are visible, with 0.6 m 93 to 100 %. A lift that follows the slope (the surface normals of the GLB give a noisy slope) made the road edges ragged, so the lift is one number.
//
// THE TILES: the tiles that the view touches and one ring around them (a primitive is in the tile of the centre of its box, so it can reach a few metres into the next one), the
// nearest `max_tiles` of them, from `min_zoom` on. They are read one at a time as they come, kept in a cache with a byte budget (`cache_mb`) and drawn while they are in it.
// THE SWITCHES: one row of the base-map box for the scene and one for each part (a part that is off is not drawn: one draw range for each tile and part). `rsScene3d`, `rsScene3dKind`.
// THE PICK: on the triangles that are drawn, projected with the layer's matrix (as bridgemesh.js does). A click on the scene sends `rs:scene3dselect` and, with `popup`, shows the
// `extras` of the primitive; the primitive is drawn again in the select colour. Nothing is drawn or picked with a part off.
// ERRORS: a problem is never silent: it goes to the console, to a toast, and to `rsScene3dProblems()`; the part of the scene that it concerns is not drawn.
import {map, O, _emit} from "./core.js";
import {rsToast} from "./notice.js";
import {_esc, _rfields} from "../popup.js";

const _s3Id = "rs-scene3d";
const _s3Opt = () => O.scene_3d;
const _s3Cfg = () => ((O.ontop || {}).scene_3d) || {};
const _s3Theme = () => document.documentElement.dataset.rsTheme === "dark" ? "dark" : "light";

// ---- the inverse of the CRS: (east, north) in metres -> [lon, lat] in degrees
function _s3Inv(c){
  const D = Math.PI / 180, a = c.a, f = c.f, e2 = f * (2 - f), e = Math.sqrt(e2);
  if(c.family === "tmerc"){                          // transverse Mercator (UTM, SWEREF99 TM), Krueger's series to the 4th order
    const n = f / (2 - f), A = a / (1 + n) * (1 + n * n / 4 + n ** 4 / 64);
    const b = [n / 2 - 2 * n * n / 3 + 37 * n ** 3 / 96 - n ** 4 / 360, n * n / 48 + n ** 3 / 15 - 437 * n ** 4 / 1440, 17 * n ** 3 / 480 - 37 * n ** 4 / 840, 4397 * n ** 4 / 161280];
    const d = [2 * n - 2 * n * n / 3 - 2 * n ** 3 + 116 * n ** 4 / 45, 7 * n * n / 3 - 8 * n ** 3 / 5 - 227 * n ** 4 / 45, 56 * n ** 3 / 15 - 136 * n ** 4 / 35, 4279 * n ** 4 / 630];
    return (E, N) => {
      const xi = (N - c.fn) / (c.k0 * A), eta = (E - c.fe) / (c.k0 * A);
      let xp = xi, ep = eta;
      for(let j = 1; j <= 4; j++){ xp -= b[j - 1] * Math.sin(2 * j * xi) * Math.cosh(2 * j * eta); ep -= b[j - 1] * Math.cos(2 * j * xi) * Math.sinh(2 * j * eta); }
      const chi = Math.asin(Math.sin(xp) / Math.cosh(ep));
      let phi = chi; for(let j = 1; j <= 4; j++) phi += d[j - 1] * Math.sin(2 * j * chi);
      return [c.lon0 + Math.atan2(Math.sinh(ep), Math.cos(xp)) / D, phi / D];
    };
  }
  if(c.family === "lcc"){                            // Lambert conformal conic, two standard parallels (EPSG method 9802)
    const m = p => Math.cos(p) / Math.sqrt(1 - e2 * Math.sin(p) ** 2), t = p => Math.tan(Math.PI / 4 - p / 2) / Math.pow((1 - e * Math.sin(p)) / (1 + e * Math.sin(p)), e / 2);
    const l1 = c.lat1 * D, l2 = c.lat2 * D, m1 = m(l1), m2 = m(l2), t1 = t(l1), t2 = t(l2);
    const n = (Math.log(m1) - Math.log(m2)) / (Math.log(t1) - Math.log(t2)), F = m1 / (n * Math.pow(t1, n)), r0 = a * F * Math.pow(t(c.lat0 * D), n), s = Math.sign(n);
    return (E, N) => {
      const x = E - c.fe, y = r0 - (N - c.fn), r = s * Math.hypot(x, y), tp = Math.pow(r / (a * F), 1 / n), th = Math.atan2(s * x, s * y);
      let phi = Math.PI / 2 - 2 * Math.atan(tp);
      for(let i = 0; i < 8; i++) phi = Math.PI / 2 - 2 * Math.atan(tp * Math.pow((1 - e * Math.sin(phi)) / (1 + e * Math.sin(phi)), e / 2));
      return [(th / n + c.lon0 * D) / D, phi / D];
    };
  }
  if(c.family === "webmerc") return (E, N) => [E / a / D, (2 * Math.atan(Math.exp(N / a)) - Math.PI / 2) / D];
  throw new Error("scene_3d: the page has no formula for the projection family " + JSON.stringify(c.family));
}
const _s3Merc = (lon, lat) => [(lon + 180) / 360, 0.5 - Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / (2 * Math.PI)];
const _s3Srgb = v => Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055));

// ---- a GLB: its primitives [{kind, node, extras, pos (Float32Array, 3 for a vertex), nrm, idx (Uint32Array), color [r, g, b] (bytes)}] and the root's `extras.simready`
function _s3Typed(Ctor, buf, at, n){ return at % Ctor.BYTES_PER_ELEMENT === 0 ? new Ctor(buf, at, n) : new Ctor(buf.slice(at, at + n * Ctor.BYTES_PER_ELEMENT)); }
function _s3Glb(buf, what){
  const bad = m => new Error("scene_3d: " + what + ": " + m);
  if(buf.byteLength < 20) throw bad("not a GLB (too short)");
  const dv = new DataView(buf);
  if(dv.getUint32(0, true) !== 0x46546C67 || dv.getUint32(4, true) !== 2) throw bad("not a GLB 2.0 file");
  let off = 12, json = null, bin = -1;
  while(off + 8 <= buf.byteLength){
    const len = dv.getUint32(off, true), ty = dv.getUint32(off + 4, true);
    if(ty === 0x4E4F534A) json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, off + 8, len)));
    else if(ty === 0x004E4942 && bin < 0) bin = off + 8;
    off += 8 + len;
  }
  if(!json || bin < 0) throw bad("a GLB with no JSON or no BIN chunk");
  if((json.extensionsRequired || []).length) throw bad("it needs the glTF extension " + json.extensionsRequired.join(", ") + ", which the layer does not read");
  const acc = (i, type, comps) => {
    const a = json.accessors[i], bv = json.bufferViews[a.bufferView];
    if(a.sparse) throw bad("a sparse accessor");
    if(type === 5126 && bv.byteStride && bv.byteStride !== comps * 4) throw bad("an interleaved vertex buffer (byteStride " + bv.byteStride + ")");
    const at = bin + (bv.byteOffset || 0) + (a.byteOffset || 0);
    if(type === 5126){ if(a.componentType !== 5126) throw bad("a vertex attribute that is not float32 (component type " + a.componentType + ")"); return _s3Typed(Float32Array, buf, at, a.count * comps); }
    if(a.componentType === 5125) return _s3Typed(Uint32Array, buf, at, a.count);
    if(a.componentType === 5123) return Uint32Array.from(_s3Typed(Uint16Array, buf, at, a.count));
    if(a.componentType === 5121) return Uint32Array.from(new Uint8Array(buf, at, a.count));
    throw bad("an index accessor of component type " + a.componentType);
  };
  const out = [], root = json.nodes[json.scenes[json.scene || 0].nodes[0]];
  const walk = (ni, kind) => {
    const n = json.nodes[ni];
    if(n.mesh != null) for(const p of json.meshes[n.mesh].primitives){
      if((p.mode ?? 4) !== 4) throw bad("a primitive that is not a list of triangles (mode " + p.mode + ")");
      if(p.indices == null || p.attributes.POSITION == null || p.attributes.NORMAL == null) throw bad("a primitive with no indices, POSITION or NORMAL");
      const mat = p.material != null ? json.materials[p.material] : null;
      if(!mat || !mat.pbrMetallicRoughness || !mat.pbrMetallicRoughness.baseColorFactor) throw bad("a primitive with no material colour (baseColorFactor)");
      if(mat.alphaMode && mat.alphaMode !== "OPAQUE") throw bad("a material with alphaMode " + mat.alphaMode + ": the layer draws opaque surfaces");
      out.push({kind, node: n.name || "", extras: {...(n.extras || {}), ...(p.extras || {})}, pos: acc(p.attributes.POSITION, 5126, 3), nrm: acc(p.attributes.NORMAL, 5126, 3), idx: acc(p.indices, 5125, 1),
                color: mat.pbrMetallicRoughness.baseColorFactor.slice(0, 3).map(_s3Srgb)});
    }
    (n.children || []).forEach(c => walk(c, kind));
  };
  (root.children || []).forEach(c => walk(c, json.nodes[c].name));
  const fr = root.extras && root.extras.simready;
  if(!fr || !fr.crs || !Array.isArray(fr.origin)) throw bad("the root node has no extras.simready with crs and origin");
  return {prims: out, frame: fr};
}

// ---- the tiles
let _s3Arch = null, _s3Gen = 0, _s3Ready = null;
const _s3Tiles = new Map();                           // "x/y" -> {state: "loading" | "ok" | "empty" | "failed", tries, used, bytes, ...}
let _s3Want = [], _s3Capped = null, _s3Pend = 0, _s3Clock = 0, _s3Dead = [];
let _s3On = true, _s3Inverse = null, _s3Problems = [];
const _s3Kinds = new Map();                           // kind -> on
let _s3Sel = null, _s3Popup = null, _s3Gl = null, _s3Prog = null, _s3Loc = {}, _s3Mat = null;
const _s3Terrain = () => !!(map && map.getTerrain());
const _s3Active = () => { const o = _s3Opt(); return !!o && _s3On && _s3Terrain() && map.getZoom() >= o.min_zoom && !_s3Blocked(); };
const _s3Blocked = () => _s3Problems.some(p => p.fatal);
const _s3Url = () => new URL(_s3Opt().url, document.baseURI).href;

function _s3Problem(code, message, fatal){
  const old = _s3Problems.find(p => p.code === code);
  if(old && old.message === message) return;
  if(old) old.message = message; else _s3Problems.push({code, message, fatal: !!fatal});
  console.error("roadstyle scene_3d: " + message);
  rsToast("3D roads: " + message, {kind: "error", ms: 0});
  _emit("rs:scene3dchange", {on: _s3On, problem: code});
}
const _s3Clear = code => { const n = _s3Problems.length; _s3Problems = _s3Problems.filter(p => p.code !== code); if(n !== _s3Problems.length) _emit("rs:scene3dchange", {on: _s3On}); };
// the problems now: [{code, message}], [] when there is none
export const rsScene3dProblems = () => _s3Problems.map(({code, message}) => ({code, message}));

// the archive: its header (the zoom must be the option's), and the page's ground (the same ground id as the archive's)
function _s3Open(){
  if(_s3Ready) return _s3Ready;
  const o = _s3Opt(), P = window.pmtiles;
  if(!P){ _s3Problem("pmtiles", "the page has no pmtiles.js, so it cannot read the archive", true); return (_s3Ready = Promise.reject(new Error("no pmtiles.js"))); }
  const g = O.ground;
  if(!g || g.id !== o.ground_id){
    _s3Problem("ground", "the archive's heights are above the ground " + o.ground_id + ", and the page draws " + (g && g.id ? "the ground " + g.id : "no ground (ground=)") + ": the roads are drawn over the ground that they are measured in", true);
    return (_s3Ready = Promise.reject(new Error("ground")));
  }
  const a = _s3Arch = new P.PMTiles(_s3Url());
  return (_s3Ready = a.getHeader().then(h => {
    if(h.minZoom !== o.zoom || h.maxZoom !== o.zoom) throw new Error("the archive has tiles at zooms " + h.minZoom + " to " + h.maxZoom + " and the page expects only " + o.zoom);
    return h;
  }).catch(e => { _s3Problem("archive", "the archive " + o.url + " did not open: " + e.message, true); throw e; }));
}

// the tiles that the view needs: [[x, y], ...], the nearest first; the ones that the view touches and a ring around them
function _s3Wanted(){
  const o = _s3Opt(), z = o.zoom, n = 2 ** z, c = map.getCanvas(), W = c.clientWidth, H = c.clientHeight, ctr = map.getCenter();
  _s3Capped = null;
  if(map.getZoom() < o.min_zoom) return [];
  const tx = ll => (ll.lng + 180) / 360 * n, ty = ll => (1 - Math.log(Math.tan(ll.lat * Math.PI / 180) + 1 / Math.cos(ll.lat * Math.PI / 180)) / Math.PI) / 2 * n;
  const cx = tx(ctr), cy = ty(ctr), reach = 3000 / (40075016.686 * Math.cos(ctr.lat * Math.PI / 180) / n);       // a tilted view reaches far: not beyond 3 km of the centre
  let x0 = cx, x1 = cx, y0 = cy, y1 = cy;
  for(let i = 0; i <= 4; i++) for(let j = 0; j <= 4; j++){
    const ll = map.unproject([W * i / 4, H * j / 4]), x = tx(ll), y = ty(ll);
    if(!isFinite(x) || !isFinite(y) || Math.hypot(x - cx, y - cy) > reach) continue;
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  const list = [];
  for(let x = Math.floor(x0) - 1; x <= Math.floor(x1) + 1; x++) for(let y = Math.floor(y0) - 1; y <= Math.floor(y1) + 1; y++){
    if(x < 0 || y < 0 || x >= n || y >= n) continue;
    list.push([x, y, Math.hypot(x + 0.5 - cx, y + 0.5 - cy)]);
  }
  list.sort((p, q) => p[2] - q[2]);
  if(list.length > o.max_tiles){ _s3Capped = {shown: o.max_tiles, total: list.length}; list.length = o.max_tiles; }
  return list.map(t => [t[0], t[1]]);
}

// a tile's GLB as the buffers of the layer. The vertices are in Web Mercator units from the tile's centre (x, y) and metres (z); the parts are in the option's order, so each part is one range of indices
function _s3Make(x, y, bytes){
  const o = _s3Opt(), what = "the tile " + o.zoom + "/" + x + "/" + y, g = _s3Glb(bytes, what), fr = g.frame;
  if(fr.crs !== o.crs.code || fr.origin[0] !== o.origin[0] || fr.origin[1] !== o.origin[1]) throw new Error("scene_3d: " + what + " is in " + fr.crs + " at origin " + fr.origin + " and the archive's metadata says " + o.crs.code + " at " + o.origin);
  for(const p of g.prims) if(!o.kinds.includes(p.kind)) throw new Error("scene_3d: " + what + " has the part " + JSON.stringify(p.kind) + ", which the archive's metadata does not list (" + o.kinds.join(", ") + ")");
  const n = 2 ** o.zoom, mc = [(x + 0.5) / n, (y + 0.5) / n];
  const lat = (2 * Math.atan(Math.exp(Math.PI * (1 - 2 * mc[1]))) - Math.PI / 2) * 180 / Math.PI, mz = 1 / (40075016.686 * Math.cos(lat * Math.PI / 180));
  const prims = [], ranges = {};
  let V = 0, I = 0; const order = [];
  for(const kind of o.kinds) for(const p of g.prims) if(p.kind === kind){ order.push(p); V += p.pos.length / 3; I += p.idx.length; }
  const pos = new Float32Array(V * 3), nrm = new Int8Array(V * 4), col = new Uint8Array(V * 4), idx = new Uint32Array(I);
  let v = 0, i = 0;
  for(const kind of o.kinds){
    const start = i;
    for(const p of order) if(p.kind === kind){
      const cnt = p.pos.length / 3, v0 = v, i0 = i, lo = [1e30, 1e30, 1e30], hi = [-1e30, -1e30, -1e30];
      for(let k = 0; k < cnt; k++, v++){
        const ll = _s3Inverse(o.origin[0] + p.pos[k * 3], o.origin[1] - p.pos[k * 3 + 2]), m = _s3Merc(ll[0], ll[1]), h = p.pos[k * 3 + 1];
        const px = m[0] - mc[0], py = m[1] - mc[1];
        pos[v * 3] = px; pos[v * 3 + 1] = py; pos[v * 3 + 2] = h;
        // the GLB's axes are (east, up, -north) and the map's (east, south, up): the normal's y is the GLB's z, its z the GLB's y
        nrm[v * 4] = Math.round(p.nrm[k * 3] * 127); nrm[v * 4 + 1] = Math.round(p.nrm[k * 3 + 2] * 127); nrm[v * 4 + 2] = Math.round(p.nrm[k * 3 + 1] * 127);
        col[v * 4] = p.color[0]; col[v * 4 + 1] = p.color[1]; col[v * 4 + 2] = p.color[2]; col[v * 4 + 3] = 255;
        lo[0] = Math.min(lo[0], px); hi[0] = Math.max(hi[0], px); lo[1] = Math.min(lo[1], py); hi[1] = Math.max(hi[1], py); lo[2] = Math.min(lo[2], h); hi[2] = Math.max(hi[2], h);
      }
      for(let k = 0; k < p.idx.length; k++) idx[i++] = v0 + p.idx[k];
      prims.push({kind, node: p.node, extras: p.extras, first: i0, count: i - i0, v0, v1: v, lo, hi});
    }
    ranges[kind] = [start, i - start];
  }
  return {pos, nrm, col, idx, prims, ranges, mc, mz, bytes: (pos.byteLength + nrm.byteLength + col.byteLength + idx.byteLength) * 2};       // the CPU's copy for the pick and the GPU's
}

// the tiles that are wanted and not yet there: at most 4 at a time, each one read, built, and the map drawn again
function _s3Pump(){
  const o = _s3Opt(); if(!o || !_s3Active()) return;
  _s3Open().then(() => {
    for(const [x, y] of _s3Want){
      if(_s3Pend >= 4) break;
      const key = x + "/" + y, t = _s3Tiles.get(key);
      if(t && t.state !== "retry") continue;
      const rec = t || {state: "loading", tries: 0, used: 0, bytes: 0}; rec.state = "loading"; _s3Tiles.set(key, rec); _s3Pend++;
      const gen = _s3Gen;
      _s3Arch.getZxy(o.zoom, x, y).then(r => {
        if(gen !== _s3Gen) return;
        if(!r){ rec.state = "empty"; return; }
        Object.assign(rec, _s3Make(x, y, r.data), {state: "ok"});
        _s3Clear("tile:" + key); map.triggerRepaint();
      }).catch(e => {
        if(gen !== _s3Gen) return;
        rec.tries++;
        if(rec.tries < 3){ rec.state = "retry"; setTimeout(_s3Plan, 1000 * rec.tries); return; }
        rec.state = "failed";
        _s3Problem("tile:" + key, "the tile " + o.zoom + "/" + key + " did not load: " + e.message, false);
      }).finally(() => { _s3Pend--; _s3Evict(); _s3Pump(); _s3Status(); });
    }
  }).catch(() => {});
}
// the cache: the least recently used tiles that are not wanted go while the bytes are over the budget; the buffers of a tile that went are deleted by the next draw
function _s3Evict(){
  const o = _s3Opt(), budget = o.cache_mb * 1048576, want = new Set(_s3Want.map(t => t.join("/")));
  let sum = 0; _s3Tiles.forEach(t => { sum += t.bytes || 0; });
  const old = [..._s3Tiles.entries()].filter(([k, t]) => t.state === "ok" && !want.has(k)).sort((a, b) => a[1].used - b[1].used);
  for(const [k, t] of old){ if(sum <= budget) break; sum -= t.bytes; if(t.gpu) _s3Dead.push(t.gpu); _s3Tiles.delete(k); if(_s3Sel && _s3Sel.tile === t) _s3Sel = null; }
  if(sum > budget) _s3Problem("cache", "the tiles in view hold " + (sum / 1048576).toFixed(0) + " MB, more than cache_mb " + o.cache_mb + ": zoom in, or give a larger cache_mb", false);
  else _s3Clear("cache");
}
let _s3Timer = 0;
function _s3Plan(){
  if(!_s3Opt()) return;
  clearTimeout(_s3Timer);
  _s3Timer = setTimeout(() => { _s3Want = _s3Active() ? _s3Wanted() : []; _s3Pump(); _s3Status(); }, 0);
}
// the state of the layer, for the rows and the tests: {on, terrain, drawn, tiles: {wanted, loaded, loading, capped}, problems}
export function rsScene3dStatus(){
  const o = _s3Opt(); if(!o) return null;
  let loaded = 0, loading = 0; _s3Want.forEach(t => { const r = _s3Tiles.get(t.join("/")); if(r && (r.state === "ok" || r.state === "empty")) loaded++; else if(!r || r.state === "loading" || r.state === "retry") loading++; });
  return {on: _s3On, terrain: _s3Terrain(), zoom_ok: map.getZoom() >= o.min_zoom, drawn: _s3Active() && [..._s3Tiles.values()].some(t => t.state === "ok"),
          tiles: {wanted: _s3Want.length, loaded, loading, capped: _s3Capped}, problems: rsScene3dProblems()};
}
function _s3Status(){ _emit("rs:scene3dstatus", rsScene3dStatus()); }

// ---- the layer
const _S3_VS = "attribute vec3 a_pos; attribute vec3 a_nrm; attribute vec4 a_col; uniform mat4 u_m; uniform float u_zs; uniform float u_lift; uniform vec3 u_light; uniform float u_amb; uniform float u_dim; uniform vec4 u_hl; varying vec4 v_col;" +
  "void main(){ gl_Position = u_m * vec4(a_pos.xy, (a_pos.z + u_lift) * u_zs, 1.0); float d = max(dot(normalize(a_nrm), u_light), 0.0); vec3 c = a_col.rgb * (u_amb + (1.0 - u_amb) * d) * u_dim;" +
  " v_col = vec4(mix(c, u_hl.rgb, u_hl.a), 1.0); }";
const _S3_FS = "precision mediump float; varying vec4 v_col; void main(){ gl_FragColor = v_col; }";
const _s3Hex = h => { const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(h || ""); return m ? [1, 2, 3].map(i => parseInt(m[i], 16) / 255) : [0.49, 0.30, 1]; };
function _s3Shader(gl, type, src){ const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("scene_3d shader: " + gl.getShaderInfoLog(s)); return s; }
function _s3Upload(gl, t){
  const mk = (type, data) => { const b = gl.createBuffer(); gl.bindBuffer(type, b); gl.bufferData(type, data, gl.STATIC_DRAW); return b; };
  t.gpu = {pos: mk(gl.ARRAY_BUFFER, t.pos), nrm: mk(gl.ARRAY_BUFFER, t.nrm), col: mk(gl.ARRAY_BUFFER, t.col), idx: mk(gl.ELEMENT_ARRAY_BUFFER, t.idx)};
}
// the matrix of a tile (doubles: the tile's centre goes into the matrix) for the vertices (x, y in mercator units from the centre, z in metres scaled by the factor)
function _s3Matrix(M, t){
  const T = new Float64Array(16); for(let i = 0; i < 16; i++) T[i] = M[i];
  for(let r = 0; r < 4; r++) T[12 + r] = M[r] * t.mc[0] + M[4 + r] * t.mc[1] + M[12 + r];
  return T;
}
const _s3Zs = t => t.mz * ((map.getTerrain() && map.getTerrain().exaggeration) || 1);
const _s3Layer = {
  id: _s3Id, type: "custom", renderingMode: "3d",
  onAdd(m, gl){
    _s3Gl = gl; _s3Prog = gl.createProgram();
    gl.attachShader(_s3Prog, _s3Shader(gl, gl.VERTEX_SHADER, _S3_VS)); gl.attachShader(_s3Prog, _s3Shader(gl, gl.FRAGMENT_SHADER, _S3_FS)); gl.linkProgram(_s3Prog);
    if(!gl.getProgramParameter(_s3Prog, gl.LINK_STATUS)) throw new Error("scene_3d program: " + gl.getProgramInfoLog(_s3Prog));
    _s3Loc = {pos: gl.getAttribLocation(_s3Prog, "a_pos"), nrm: gl.getAttribLocation(_s3Prog, "a_nrm"), col: gl.getAttribLocation(_s3Prog, "a_col")};
    for(const u of ["u_m", "u_zs", "u_lift", "u_light", "u_amb", "u_dim", "u_hl"]) _s3Loc[u] = gl.getUniformLocation(_s3Prog, u);
    _s3Tiles.forEach(t => { t.gpu = null; });
  },
  onRemove(m, gl){ _s3Tiles.forEach(t => { if(t.gpu){ for(const k in t.gpu) gl.deleteBuffer(t.gpu[k]); t.gpu = null; } }); gl.deleteProgram(_s3Prog); _s3Prog = null; },
  render(gl, args){
    if(!_s3Prog) return;
    for(const g of _s3Dead.splice(0)) for(const k in g) gl.deleteBuffer(g[k]);
    if(!_s3Active()) return;
    const cfg = _s3Cfg(), M = args && args.defaultProjectionData ? args.defaultProjectionData.mainMatrix : args, dim = (cfg.dim || {})[_s3Theme()] ?? 1, L = cfg.light || [-0.4, 0.5, 0.75], ln = Math.hypot(...L);
    gl.useProgram(_s3Prog);
    gl.uniform1f(_s3Loc.u_lift, cfg.lift_m); gl.uniform3f(_s3Loc.u_light, L[0] / ln, L[1] / ln, L[2] / ln); gl.uniform1f(_s3Loc.u_amb, cfg.ambient); gl.uniform1f(_s3Loc.u_dim, dim);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true); gl.disable(gl.CULL_FACE); gl.disable(gl.BLEND);
    const attr = (loc, buf, size, ty, norm) => { gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, ty, norm, 0, 0); };
    _s3Tiles.forEach(t => {
      if(t.state !== "ok") return;
      t.used = ++_s3Clock; if(!t.gpu) _s3Upload(gl, t);
      gl.uniformMatrix4fv(_s3Loc.u_m, false, new Float32Array(_s3Matrix(M, t))); gl.uniform1f(_s3Loc.u_zs, _s3Zs(t)); gl.uniform4f(_s3Loc.u_hl, 0, 0, 0, 0);
      attr(_s3Loc.pos, t.gpu.pos, 3, gl.FLOAT, false); attr(_s3Loc.nrm, t.gpu.nrm, 3, gl.BYTE, true); attr(_s3Loc.col, t.gpu.col, 4, gl.UNSIGNED_BYTE, true);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, t.gpu.idx);
      for(const k in t.ranges){ const [s, c] = t.ranges[k]; if(c && _s3Kinds.get(k)) gl.drawElements(gl.TRIANGLES, c, gl.UNSIGNED_INT, s * 4); }
      if(_s3Sel && _s3Sel.tile === t){            // the picked primitive again, in the select colour, a little nearer
        const h = _s3Hex(O.select_color), p = _s3Sel.prim;
        gl.uniform4f(_s3Loc.u_hl, h[0], h[1], h[2], 0.75); gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(-1, -1);
        gl.drawElements(gl.TRIANGLES, p.count, gl.UNSIGNED_INT, p.first * 4); gl.disable(gl.POLYGON_OFFSET_FILL);
      }
    });
    gl.disableVertexAttribArray(_s3Loc.pos); gl.disableVertexAttribArray(_s3Loc.nrm); gl.disableVertexAttribArray(_s3Loc.col);
  },
};

// ---- the pick: the primitive of a visible part under a screen point {x, y}, the nearest to the camera; null when there is none
function _s3PickAt(p){
  if(!_s3Opt() || !_s3Active()) return null;
  const c = map.getCanvas(), W = c.clientWidth, H = c.clientHeight, M = map.transform.getProjectionDataForCustomLayer(false).mainMatrix, lift = _s3Cfg().lift_m;
  let best = null, bw = Infinity;
  const hit = (px, py) => {
    for(const t of _s3Tiles.values()){
      if(t.state !== "ok") continue;
      const T = _s3Matrix(M, t), zs = _s3Zs(t);
      const proj = (x, y, z) => { const zz = (z + lift) * zs, cw = T[3] * x + T[7] * y + T[11] * zz + T[15]; if(cw <= 0) return null;
        return [((T[0] * x + T[4] * y + T[8] * zz + T[12]) / cw * 0.5 + 0.5) * W, (0.5 - (T[1] * x + T[5] * y + T[9] * zz + T[13]) / cw * 0.5) * H, cw]; };
      for(const pr of t.prims){
        if(!_s3Kinds.get(pr.kind)) continue;
        let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, out = false;
        for(const x of [pr.lo[0], pr.hi[0]]) for(const y of [pr.lo[1], pr.hi[1]]) for(const z of [pr.lo[2], pr.hi[2]]){
          const q = proj(x, y, z); if(!q){ out = true; continue; }
          x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]);
        }
        if(!out && (px < x0 - 4 || px > x1 + 4 || py < y0 - 4 || py > y1 + 4)) continue;
        const S = new Map(), at = v => { let q = S.get(v); if(q === undefined){ q = proj(t.pos[v * 3], t.pos[v * 3 + 1], t.pos[v * 3 + 2]); S.set(v, q); } return q; };
        for(let k = pr.first; k + 2 < pr.first + pr.count; k += 3){
          const A = at(t.idx[k]), B = at(t.idx[k + 1]), C = at(t.idx[k + 2]); if(!A || !B || !C) continue;
          const d = (B[1] - C[1]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[1] - C[1]); if(Math.abs(d) < 1e-9) continue;
          const u = ((B[1] - C[1]) * (px - C[0]) + (C[0] - B[0]) * (py - C[1])) / d, w = ((C[1] - A[1]) * (px - C[0]) + (A[0] - C[0]) * (py - C[1])) / d, r = 1 - u - w;
          if(u < 0 || w < 0 || r < 0) continue;
          const depth = u * A[2] + w * B[2] + r * C[2];
          if(depth < bw){ bw = depth; best = {tile: t, prim: pr}; }
        }
      }
    }
  };
  hit(p.x, p.y);
  for(const [dx, dy] of [[4, 0], [-4, 0], [0, 4], [0, -4]]){ if(best) break; hit(p.x + dx, p.y + dy); }
  return best;
}
const _s3Key = t => { for(const [k, v] of _s3Tiles) if(v === t) return k; return null; };
const _s3Detail = h => ({kind: h.prim.kind, node: h.prim.node, tile: [_s3Opt().zoom, ..._s3Key(h.tile).split("/").map(Number)], extras: {...h.prim.extras}});
// rsScene3dPick({x, y}): what is drawn under a screen point, {kind, node, tile: [z, x, y], extras}, or null
export function rsScene3dPick(p){ const h = _s3PickAt(p); return h && _s3Detail(h); }
// select.js: a click on the scene. true when it took the click (it deselects the road first: `deselect`); a click on nothing of the scene only drops the scene's own selection
export function _s3Click(e, deselect){
  const had = !!_s3Sel; if(_s3Popup){ _s3Popup.remove(); _s3Popup = null; }
  const h = _s3PickAt(e.point);
  if(!h){ if(had){ _s3Sel = null; map.triggerRepaint(); _emit("rs:scene3ddeselect", {}); } return false; }
  deselect();
  _s3Sel = h; map.triggerRepaint();
  const d = _s3Detail(h);
  _emit("rs:scene3dselect", d);
  if(_s3Opt().popup) _s3Popup = new maplibregl.Popup({closeButton: true}).setLngLat(e.lngLat).setHTML(_rfields({name: d.kind + (d.node && d.node !== d.kind ? " " + d.node : ""), ...d.extras})).addTo(map);
  return true;
}

// ---- the switches
function _s3Set(on){ _s3On = !!on; map.triggerRepaint(); _s3Plan(); _emit("rs:scene3dchange", {on: _s3On, kinds: Object.fromEntries(_s3Kinds)}); }
// rsScene3d(on): the whole scene on or off; no argument: whether it is on (it is drawn only with the 3D terrain on, from `min_zoom`: rsScene3dStatus())
export function rsScene3d(on){
  if(!_s3Opt()) throw new Error("rsScene3d: this page has no 3D road tiles (the keyword scene_3d)");
  if(on === undefined) return _s3On;
  _s3Set(on); return _s3On;
}
// rsScene3dKind(kind, on): one part (a kind of the archive: rsScene3dKind() lists them) on or off; no `on`: whether it is on; no argument: {kind: on}
export function rsScene3dKind(kind, on){
  if(!_s3Opt()) throw new Error("rsScene3dKind: this page has no 3D road tiles (the keyword scene_3d)");
  if(kind === undefined) return Object.fromEntries(_s3Kinds);
  if(!_s3Kinds.has(kind)) throw new Error("rsScene3dKind: the archive has no part " + JSON.stringify(kind) + "; its parts are " + [..._s3Kinds.keys()].join(", "));
  if(on === undefined) return _s3Kinds.get(kind);
  _s3Kinds.set(kind, !!on); if(_s3Sel && _s3Sel.prim.kind === kind) _s3Sel = null;
  map.triggerRepaint(); _emit("rs:scene3dchange", {on: _s3On, kinds: Object.fromEntries(_s3Kinds)}); return !!on;
}
// the vertices of the tiles that are in memory, as [{kind, tile, lng, lat, h}], at most `max` (the first ones of each part): for the tests and for a page that checks its data
export function rsScene3dVertices(max = 1000){
  const out = [], n = 2 ** _s3Opt().zoom;
  _s3Tiles.forEach((t, key) => {
    if(t.state !== "ok") return;
    for(const p of t.prims) for(let v = p.v0; v < Math.min(p.v1, p.v0 + Math.ceil(max / Math.max(1, t.prims.length))); v++){
      const mx = t.mc[0] + t.pos[v * 3], my = t.mc[1] + t.pos[v * 3 + 1];
      out.push({kind: p.kind, tile: [_s3Opt().zoom, ...key.split("/").map(Number)], lng: mx * 360 - 180, lat: Math.atan(Math.sinh(Math.PI * (1 - 2 * my))) * 180 / Math.PI, h: t.pos[v * 3 + 2]});
    }
  });
  return out.slice(0, max);
}
const _s3Label = k => k.charAt(0).toUpperCase() + k.slice(1);
function _s3Rows(){
  const o = _s3Opt(), add = window.rsAddTopRow;
  const off = () => !_s3Terrain() ? "Needs the 3D terrain" : map.getZoom() < o.min_zoom ? "Zoom in to " + o.min_zoom + " to see the 3D roads" : "";
  add({id: "scene3d", label: "3D scene", get: () => _s3On, set: on => rsScene3d(on), available: () => _s3Terrain(), unavailable: off});
  for(const k of o.kinds) add({id: "scene3d-" + k, label: "3D " + k, get: () => _s3Kinds.get(k), set: on => rsScene3dKind(k, on), available: () => _s3Terrain() && _s3On, unavailable: () => _s3On ? off() : "The 3D roads are off"});
}

// ---- the page
export function initScene3D(){
  window.rsScene3d = rsScene3d; window.rsScene3dKind = rsScene3dKind; window.rsScene3dPick = rsScene3dPick; window.rsScene3dProblems = rsScene3dProblems;
  window.rsScene3dStatus = rsScene3dStatus; window.rsScene3dVertices = rsScene3dVertices;
  const o = _s3Opt(); if(!o) return;
  try { _s3Inverse = _s3Inv(o.crs); } catch(e){ _s3Problem("crs", e.message, true); return; }
  _s3On = o.on !== false; o.kinds.forEach(k => _s3Kinds.set(k, true));
  _s3Rows();
  const ensure = () => { if(!map.getLayer(_s3Id) && map.isStyleLoaded()) map.addLayer(_s3Layer); };
  ensure(); for(const ev of ["styledata", "idle"]) map.on(ev, ensure);
  map.on("moveend", _s3Plan); map.on("terrain", () => { _s3Plan(); document.dispatchEvent(new CustomEvent("rs:toprowschange")); });
  document.addEventListener("rs:terrainchange", () => { _s3Plan(); document.dispatchEvent(new CustomEvent("rs:toprowschange")); });
  document.addEventListener("rs:groundchange", () => { _s3Gen++; _s3Arch = null; _s3Ready = null; _s3Tiles.forEach(t => { if(t.gpu) _s3Dead.push(t.gpu); }); _s3Tiles.clear(); _s3Problems = []; _s3Plan(); });
  document.addEventListener("rs:themechange", () => map.triggerRepaint());
  map.on("zoomend", () => document.dispatchEvent(new CustomEvent("rs:toprowschange")));
  _s3Plan();
}

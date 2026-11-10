// THE VEHICLES OF A TRAFFIC MICROSIMULATION RUN (docs/design/vehicles_spec.md). A VehicleScene (roadstyle-wasm built with the feature
// "vehicles") places every vehicle at the clock time; this module draws them in one custom layer (renderingMode "3d", instanced
// boxes) and keeps the clock. rs.vehicles: load, play, pause, seek, speed, time, playing, report.
// THE MATRIX: MapLibre 5 gives a custom layer `defaultProjectionData.mainMatrix` for 0-1 Mercator coordinates (P0, vehicles.md); the
// scene gives "origin metres" (Mercator offsets from its origin divided by one metre's Mercator size there), so the layer's matrix is
// mainMatrix x translate(origin) x scale(metre): small numbers, exact in float32.
// THE ORDER: the layer must be drawn after every 3D layer that can hide a vehicle (the buildings), or the depth test is wrong (P0). A
// page adds layers later (the 3D switch, a base map change), so the layer goes to the top again on each style change.
// THE LOOK: the colours (one for each kind, light and dark), the kind and the size of each SUMO vClass and the numbers of a run come
// from the look's vehicles section (O.vehicle_look: the palette and the profile); a page can give its own in load().
// THE HEIGHT (P2, docs/design/road_heights.md): a vehicle on its lanes takes its height from its roads: each drawn road (the page's
// road table, by edge id) gets a height profile along its own line, from the terrain the road is drawn on (map.queryTerrainElevation: m
// above sea level, times the exaggeration; 0 with no terrain); a lane change blends the two roads, a junction goes from the road in to
// the road out. Never the ground at the vehicle's lon/lat (only lon/lat placement, which has no road, uses it). A vehicle whose road or
// height is not known yet is left out of the frame, never drawn at a wrong height; the layer asks again on the next frame.
// THE TUNNELS (P2): a vehicle on a tunnel road (the page's roads with a level below 0) has the tunnels' look: the global state
// rs_terrain_tunnel that the tunnel layers read (1 with the terrain off or "show", the fade, 0 for "hide"), and 0 while the Roads box
// hides the tunnels. It stays on the drawn tunnel line, so with the terrain on it is on the hill above, as the tunnel is.
// P2 steps 1 and 2: the terrain and the tunnels. The 3D bridge decks follow.
import {map, O, RS_PREFIX, _emit, RoadTable} from "./core.js";

const _VH_STRIDE = 16;                 // the numbers of one vehicle in VehicleScene.frame
const _VH_MAX_CLASSES = 8;             // the colours the shader holds (a class number past it takes colour number % 8)
const _VH_KEYS = ["placement", "teleport_m", "lane_change_s", "heading_lookahead_m", "class_sizes"];
const _vhLayerId = () => RS_PREFIX + "vehicles";

let _vhLast = null;              // the numbers of the last frame (rs.vehicles.drawn)
let _vhTunnelsOn = true;          // the Roads box's Tunnels switch (rs:filterchange)
let _vhScene = null, _vhOrigin = null, _vhColours = null, _vhReport = null, _vhIds = null, _vhClasses = [], _vhGiven = null;
let _vhT = 0, _vhSpeed = 1, _vhPlaying = false, _vhWall = null, _vhSentAt = 0, _vhDirty = true;
let _vhGl = null, _vhProg = null, _vhVao = null, _vhInstBuf = null, _vhN = 0, _vhLoc = {};

// a unit box: x forward (-0.5..0.5 of the length), y right (-0.5..0.5 of the width), z up (0..1 of the height); 6 faces, outward normals
function _vhBox(){
  const F = [[[1,0,0],[[.5,-.5,0],[.5,.5,0],[.5,.5,1],[.5,-.5,1]]], [[-1,0,0],[[-.5,.5,0],[-.5,-.5,0],[-.5,-.5,1],[-.5,.5,1]]],
             [[0,1,0],[[.5,.5,0],[-.5,.5,0],[-.5,.5,1],[.5,.5,1]]], [[0,-1,0],[[-.5,-.5,0],[.5,-.5,0],[.5,-.5,1],[-.5,-.5,1]]],
             [[0,0,1],[[-.5,-.5,1],[.5,-.5,1],[.5,.5,1],[-.5,.5,1]]], [[0,0,-1],[[-.5,.5,0],[.5,.5,0],[.5,-.5,0],[-.5,-.5,0]]]];
  const v = [];
  for(const [n, q] of F) for(const k of [0, 1, 2, 0, 2, 3]) v.push(...q[k], ...n);
  return new Float32Array(v);
}

const _VH_VS = `#version 300 es
in vec3 a_pos; in vec3 a_nrm;
in vec4 i_pos;                  // x, y, z (origin metres; y south), heading (radians, 0 = north, clockwise)
in vec4 i_size;                 // length, width, height (m), class
in vec2 i_tilt;                 // pitch (+ = the front up), roll (+ = the right side up), radians
in float i_flags;               // 1: in a tunnel
uniform mat4 u_m; uniform vec4 u_col[${_VH_MAX_CLASSES}];
uniform float u_tunnel;         // the tunnels' opacity now
out vec4 v_col;
void main(){
  float h = i_pos.w;
  vec2 f = vec2(sin(h), -cos(h)), r = vec2(cos(h), sin(h));   // forward and right in Mercator's x east, y south
  float cp = cos(i_tilt.x), sp = sin(i_tilt.x), cr = cos(i_tilt.y), sr = sin(i_tilt.y);
  // the box in its own axes (x forward, y right, z up), turned by the roll (about x), then by the pitch (about y)
  vec3 q = a_pos * i_size.xyz;
  q = vec3(q.x, q.y * cr - q.z * sr, q.z * cr + q.y * sr);
  q = vec3(q.x * cp - q.z * sp, q.y, q.z * cp + q.x * sp);
  vec3 m = vec3(a_nrm.x, a_nrm.y * cr - a_nrm.z * sr, a_nrm.z * cr + a_nrm.y * sr);
  m = vec3(m.x * cp - m.z * sp, m.y, m.z * cp + m.x * sp);
  vec2 xy = i_pos.xy + f * q.x + r * q.y;
  gl_Position = u_m * vec4(xy, i_pos.z + q.z, 1.0);
  vec3 n = normalize(vec3(f * m.x + r * m.y, m.z));
  float shade = 0.55 + 0.45 * max(dot(n, normalize(vec3(-0.4, -0.5, 0.75))), 0.0);
  vec4 c = u_col[int(i_size.w) % ${_VH_MAX_CLASSES}];
  float a = c.a * (i_flags > 0.5 ? u_tunnel : 1.0);
  v_col = vec4(c.rgb * shade * a, a);
}`;
const _VH_FS = `#version 300 es
precision mediump float; in vec4 v_col; out vec4 o_col; void main(){ if(v_col.a < 0.004) discard; o_col = v_col; }`;

function _vhShader(gl, kind, src){
  const s = gl.createShader(kind); gl.shaderSource(s, src); gl.compileShader(s);
  if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("rs.vehicles: shader: " + gl.getShaderInfoLog(s));
  return s;
}

// column-major 4x4 product a x b
function _vhMul(a, b){
  const o = new Float64Array(16);
  for(let c = 0; c < 4; c++) for(let r = 0; r < 4; r++){
    let s = 0; for(let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = s;
  }
  return o;
}

const _vhLayer = {
  id: "", type: "custom", renderingMode: "3d",
  onAdd(m, gl){
    if(!(typeof WebGL2RenderingContext !== "undefined" && gl instanceof WebGL2RenderingContext))
      throw new Error("rs.vehicles: the map has no WebGL2 context");
    _vhGl = gl;
    _vhProg = gl.createProgram();
    gl.attachShader(_vhProg, _vhShader(gl, gl.VERTEX_SHADER, _VH_VS));
    gl.attachShader(_vhProg, _vhShader(gl, gl.FRAGMENT_SHADER, _VH_FS));
    gl.linkProgram(_vhProg);
    if(!gl.getProgramParameter(_vhProg, gl.LINK_STATUS)) throw new Error("rs.vehicles: program: " + gl.getProgramInfoLog(_vhProg));
    for(const k of ["a_pos", "a_nrm", "i_pos", "i_size", "i_tilt", "i_flags"]) _vhLoc[k] = gl.getAttribLocation(_vhProg, k);
    _vhLoc.u_m = gl.getUniformLocation(_vhProg, "u_m"); _vhLoc.u_col = gl.getUniformLocation(_vhProg, "u_col");
    _vhLoc.u_tunnel = gl.getUniformLocation(_vhProg, "u_tunnel");
    _vhVao = gl.createVertexArray(); gl.bindVertexArray(_vhVao);
    const box = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, box); gl.bufferData(gl.ARRAY_BUFFER, _vhBox(), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(_vhLoc.a_pos); gl.vertexAttribPointer(_vhLoc.a_pos, 3, gl.FLOAT, false, 24, 0);
    gl.enableVertexAttribArray(_vhLoc.a_nrm); gl.vertexAttribPointer(_vhLoc.a_nrm, 3, gl.FLOAT, false, 24, 12);
    _vhInstBuf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, _vhInstBuf);
    const st = _VH_STRIDE * 4;
    gl.enableVertexAttribArray(_vhLoc.i_pos); gl.vertexAttribPointer(_vhLoc.i_pos, 4, gl.FLOAT, false, st, 0);   // x, y, z, heading
    gl.vertexAttribDivisor(_vhLoc.i_pos, 1);
    gl.enableVertexAttribArray(_vhLoc.i_size); gl.vertexAttribPointer(_vhLoc.i_size, 4, gl.FLOAT, false, st, 24); // length, width, height, class
    gl.vertexAttribDivisor(_vhLoc.i_size, 1);
    gl.enableVertexAttribArray(_vhLoc.i_tilt); gl.vertexAttribPointer(_vhLoc.i_tilt, 2, gl.FLOAT, false, st, 16);  // pitch, roll
    gl.vertexAttribDivisor(_vhLoc.i_tilt, 1);
    gl.enableVertexAttribArray(_vhLoc.i_flags); gl.vertexAttribPointer(_vhLoc.i_flags, 1, gl.FLOAT, false, st, 56);  // flags
    gl.vertexAttribDivisor(_vhLoc.i_flags, 1);
    gl.bindVertexArray(null);
  },
  render(gl, args){
    if(!_vhScene) return;
    const now = performance.now();
    if(_vhPlaying){
      if(_vhWall != null) _vhT = Math.min(_vhT + (now - _vhWall) / 1000 * _vhSpeed, _vhReport.t1);
      _vhWall = now; _vhDirty = true;
      if(_vhT >= _vhReport.t1) _vhPause();
    }
    if(_vhDirty){
      const inst = _vhScene.frame(_vhT);
      _vhN = inst.length / _VH_STRIDE; _vhLast = inst;
      gl.bindBuffer(gl.ARRAY_BUFFER, _vhInstBuf); gl.bufferData(gl.ARRAY_BUFFER, inst, gl.DYNAMIC_DRAW);
      _vhDirty = _vhScene.waiting() > 0;          // vehicles wait for a terrain tile: ask again on the next frame
      if(now - _vhSentAt > 250){ _vhSentAt = now; _emit("rs:vehicletime", {t: _vhT}); }
    }
    if(_vhN){
      const [, , ox, oy, u] = _vhOrigin;
      const m = _vhMul(args.defaultProjectionData.mainMatrix, [u,0,0,0, 0,u,0,0, 0,0,u,0, ox,oy,0,1]);
      gl.useProgram(_vhProg);
      gl.uniformMatrix4fv(_vhLoc.u_m, false, new Float32Array(m));
      gl.uniform4fv(_vhLoc.u_col, _vhColours);
      // the tunnels' look now: the same global state as the tunnel layers (elevation.js), 0 while the Roads box hides the tunnels
      const ts = map.getGlobalState().rs_terrain_tunnel;
      gl.uniform1f(_vhLoc.u_tunnel, !_vhTunnelsOn ? 0 : (ts == null ? 1 : ts));
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true);
      gl.disable(gl.CULL_FACE); gl.disable(gl.STENCIL_TEST);
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.bindVertexArray(_vhVao);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 36, _vhN);
      gl.bindVertexArray(null);
    }
    if(_vhPlaying || _vhDirty) map.triggerRepaint();
  }
};

// the layer on top: after the 3D switch, a base map change or a new style added layers above it
function _vhOnTop(){
  const id = _vhLayerId();
  if(!map.getLayer(id)) return;
  const order = map.getLayersOrder();
  if(order[order.length - 1] !== id) map.moveLayer(id);
}

// "#rrggbb" or [r, g, b, a] (0..1) to [r, g, b, a]
function _vhRgba(c, cls){
  if(Array.isArray(c) && c.length === 4) return c;
  const h = typeof c === "string" && /^#[0-9a-f]{6}$/i.exec(c) ? c : null;
  if(!h) throw new Error(`rs.vehicles.load: colours.${cls} must be "#rrggbb" or [r, g, b, a], not ${JSON.stringify(c)}`);
  return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).concat(1);
}

function _vhPause(){ _vhPlaying = false; _vhWall = null; }

// the tunnel edges for the scene: the page's roads with a level below 0 (the rule of the Roads box's Tunnels switch, filter.js)
function _vhTunnels(){
  if(!_vhScene || !RoadTable.rows()) return;
  const ids = [], col = O.edge_id_col || "edge_id";
  for(let i = 0; i < RoadTable.rows(); i++){ const p = RoadTable.props(i); if(p && (p.lvl || 0) < 0 && p[col] != null) ids.push(String(p[col])); }
  _vhScene.setTunnelEdges(ids); _vhDirty = true; map.triggerRepaint();
}

const _vhDark = () => document.documentElement.dataset.rsTheme === "dark";

// the run's options from the look: the profile's numbers and each class's size
function _vhOptions(look){
  const sizes = {};
  for(const [c, v] of Object.entries(look.classes)) sizes[c] = v.size;
  return {placement: "lane", teleport_m: look.teleport_m, lane_change_s: look.lane_change_s, heading_lookahead_m: look.heading_lookahead_m,
          class_sizes: sizes};
}

// the shader's colours, one for each class of the run: the page's (load's colours, by class) or the look's (the class's kind, in the theme)
function _vhPaint(){
  const cols = new Float32Array(_VH_MAX_CLASSES * 4), look = O.vehicle_look;
  _vhClasses.forEach((c, i) => {
    let col;
    if(_vhGiven){
      if(!(c in _vhGiven)) throw new Error(`rs.vehicles.load: colours has no colour for the class ${c}`);
      col = _vhGiven[c];
    } else {
      const cls = look && look.classes[c];
      if(!cls) throw new Error(`rs.vehicles: the look has no vehicles.classes.${c} (add the class to the profile)`);
      const tc = look.colours[cls.kind];
      if(!tc) throw new Error(`rs.vehicles: the look has no vehicles.colours.${cls.kind} (the kind of the class ${c})`);
      col = _vhDark() ? tc.dark : tc.light;
    }
    if(i < _VH_MAX_CLASSES) cols.set(_vhRgba(col, c), i * 4);
  });
  _vhColours = cols;
}

async function _vhBytes(x){ return typeof x === "string" ? new Uint8Array(await (await fetch(x)).arrayBuffer()) : x; }
async function _vhText(x){ return x == null ? undefined : (/^\s*</.test(x) ? x : await (await fetch(x)).text()); }

// load({wasm, fcd, net, routes, options?, colours?}): `wasm` the URL of roadstyle_wasm.js built with the feature "vehicles"; `fcd` the
// bytes or the URL of SUMO's FCD Parquet file; `net` the text or the URL of the run's net.xml; `routes` (optional) the text or URL of
// a file with the <vType> elements. `options` (every key of _VH_KEYS) and `colours` ({class: "#rrggbb"}) default to the look's vehicles
// section. Gives the run's report and sends rs:vehicleload. A page with the option `vehicles` calls it at start (index.js).
async function _vhLoad(o){
  for(const k of ["wasm", "fcd"]) if(o[k] == null) throw new Error(`rs.vehicles.load: ${k} is missing`);
  if((o.options == null || o.colours == null) && !O.vehicle_look)
    throw new Error("rs.vehicles.load: no options or colours, and the look has no vehicles section");
  const options = o.options || _vhOptions(O.vehicle_look);
  for(const k of _VH_KEYS) if(options[k] == null) throw new Error(`rs.vehicles.load: options.${k} is missing`);
  const mod = await import(new URL(o.wasm, document.baseURI).href);
  await mod.default();
  const [fcd, net, routes] = await Promise.all([_vhBytes(o.fcd), _vhText(o.net), _vhText(o.routes)]);
  const scene = new mod.VehicleScene(fcd, net, routes, JSON.stringify(options));
  _vhClasses = scene.classes(); _vhGiven = o.colours || null;
  // the ground: the drawn terrain (with its exaggeration), 0 with no terrain, NaN while its tile has not come
  scene.setGround({height: (lon, lat) => {
    if(!map.getTerrain()) return 0;
    const h = map.queryTerrainElevation([lon, lat]);
    return h == null ? NaN : h;
  }});
  // the drawn roads by edge id: the line of the road table's row (loaded first when the table has no lines)
  const rows = new Map(), col = O.edge_id_col || "edge_id";
  const index = () => { for(let i = 0; i < RoadTable.rows(); i++){ const p = RoadTable.own(i); if(p && p[col] != null) rows.set(String(p[col]), i); } };
  scene.setRoads({line: (id) => {
    if(!rows.size) index();          // a road table that comes after the run (rs:tableready)
    const i = rows.get(id);
    if(i == null) return undefined;
    const c = RoadTable.line(i);
    if(!c){ const w = RoadTable.load(i); if(w) w.then(() => { _vhDirty = true; map.triggerRepaint(); }); return undefined; }
    return Float64Array.from(c.flat());
  }});
  _vhPaint();
  _vhScene = scene; _vhOrigin = scene.origin(); _vhIds = scene.ids();
  _vhTunnels();
  _vhReport = JSON.parse(scene.report());
  _vhT = _vhReport.t0; _vhDirty = true; _vhPause();
  // the style can be busy after "load" (a theme or base map change of the page): wait for an "idle" with the style loaded, not for
  // "load", which fires once only
  await new Promise(r => { const ok = () => map.isStyleLoaded() ? r() : map.once("idle", ok); ok(); });
  _vhLayer.id = _vhLayerId();
  if(!map.getLayer(_vhLayer.id)){
    map.addLayer(_vhLayer); map.on("styledata", _vhOnTop);
    document.addEventListener("rs:themechange", () => { if(_vhScene){ _vhPaint(); map.triggerRepaint(); } });
    // the terrain on, off, or another exaggeration: the heights kept are wrong now
    map.on("terrain", () => { if(_vhScene){ _vhScene.clearGround(); _vhDirty = true; map.triggerRepaint(); } });
    // the Roads box's Tunnels switch, and a road table that comes later (a style with its own table)
    document.addEventListener("rs:filterchange", e => { if("tunnels" in e.detail){ _vhTunnelsOn = e.detail.tunnels; map.triggerRepaint(); } });
    document.addEventListener("rs:tableready", _vhTunnels);
  }
  _vhOnTop();
  map.triggerRepaint();
  _emit("rs:vehicleload", _vhReport);
  return _vhReport;
}

export function vehiclesApi(){
  const need = () => { if(!_vhScene) throw new Error("rs.vehicles: no run is loaded (rs.vehicles.load)"); };
  return {
    load: _vhLoad,
    play(){ need(); if(_vhT >= _vhReport.t1) _vhT = _vhReport.t0; _vhPlaying = true; _vhWall = null; map.triggerRepaint(); },
    pause(){ _vhPause(); },
    seek(t){ need(); _vhT = Math.max(_vhReport.t0, Math.min(_vhReport.t1, +t)); _vhDirty = true; map.triggerRepaint(); },
    speed(x){ if(x != null){ if(!(x > 0)) throw new Error("rs.vehicles.speed: a number above 0"); _vhSpeed = +x; } return _vhSpeed; },
    time(){ return _vhT; },
    playing(){ return _vhPlaying; },
    count(){ return _vhN; },
    waiting(){ return _vhScene ? _vhScene.waiting() : 0; },
    // the road heights' memory: {roads, bytes} (docs/design/road_heights.md)
    roadProfiles(){ if(!_vhScene) return null; const [roads, bytes] = _vhScene.roadProfiles(); return {roads, bytes}; },
    // the vehicles of the last frame: {id, z (m), tunnel}
    drawn(){
      const out = [];
      if(_vhLast) for(let k = 0; k < _vhN; k++){ const b = k * _VH_STRIDE;
        out.push({id: _vhIds[_vhLast[b + 15]], z: _vhLast[b + 2], tunnel: _vhLast[b + 14] > 0.5}); }
      return out;
    },
    ids(){ return _vhIds ? _vhIds.slice() : []; },
    report(){ return _vhReport ? {..._vhReport} : null; },
  };
}

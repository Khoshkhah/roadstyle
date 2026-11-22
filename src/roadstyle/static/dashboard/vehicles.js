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
// THE LANES: the junction areas and the lanes of the run's net.xml (VehicleScene.lanes, the surface that the vehicles drive on), under the
// vehicles: the junctions' polygons in the lane colour, then each lane at its width in metres, a marking line at the full width and the
// surface on it less the marking. A lane inside a junction has no marking.
// THE LEVELS: each lane and each vehicle has the drawing level of its road (the page's `fill_level`, by the SUMO edge id = the road's
// `edge_id`; VehicleScene.setEdges). Each level has its own layers, from the lowest up: the junctions, the lane markings, the lanes,
// then the vehicles of that level. So a bridge's lanes cover the vehicles under the bridge, and its vehicles are on top.
// THE TUNNELS: a lane and a vehicle on a tunnel road fade with the page's tunnel look: they are drawn partly see-through (opacity
// 1 - 0.75 x the tunnel strength of tunnel.js), so the page's own tunnel road under them shows through, in each theme; with the terrain
// on, the tunnels' fade (the state rs_terrain_tunnel, elevation.js) multiplies it.
// P1: flat ground (z 0), boxes, no camera.
import {map, O, RS_PREFIX, _emit, _side} from "./core.js";
import {TUNNEL} from "./tunnel.js";

const _VH_STRIDE = 16;                 // the numbers of one vehicle in VehicleScene.frame
const _VH_MAX_CLASSES = 8;             // the colours the shader holds (a class number past it takes colour number % 8)
const _VH_KEYS = ["placement", "teleport_m", "lane_change_s", "heading_lookahead_m", "class_sizes"];
// the layers of one level: the junctions, the lane markings, the lanes, the vehicles
const _vhIds4 = (lv) => ["vehicle-junctions", "vehicle-lane-marking", "vehicle-lane-fill", "vehicles"].map(k => `${RS_PREFIX}${k}-${lv}`);
let _vhLevels = [0];                   // the levels of the run, from the lowest
const _vhLayers = new Map();           // level -> its vehicle layer
const _VH_M_PX = 40075016.686 / 512;   // the metres of one pixel at zoom 0 at the equator (MapLibre's 512 px tiles)
let _vhLanes = null, _vhLanesIn = null; // the lanes' GeoJSON (null: the page shows no lanes), and the GeoJSON in the source now

let _vhScene = null, _vhOrigin = null, _vhColours = null, _vhReport = null, _vhIds = null, _vhClasses = [], _vhGiven = null;
let _vhT = 0, _vhSpeed = 1, _vhPlaying = false, _vhWall = null, _vhSentAt = 0, _vhDirty = true;
let _vhGl = null, _vhProg = null, _vhVao = null, _vhInstBuf = null, _vhN = 0, _vhLoc = {};
let _vhByLevel = new Map();            // level -> [first instance, count] in the instance buffer of this frame

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
in float i_tun;                 // 1 on a tunnel road
uniform mat4 u_m; uniform vec4 u_col[${_VH_MAX_CLASSES}];
uniform float u_tunop;          // the opacity of a vehicle on a tunnel road
out vec4 v_col;
void main(){
  float h = i_pos.w;
  vec2 f = vec2(sin(h), -cos(h)), r = vec2(cos(h), sin(h));   // forward and right in Mercator's x east, y south
  vec2 xy = i_pos.xy + f * (a_pos.x * i_size.x) + r * (a_pos.y * i_size.y);
  gl_Position = u_m * vec4(xy, i_pos.z + a_pos.z * i_size.z, 1.0);
  vec3 n = normalize(vec3(f * a_nrm.x + r * a_nrm.y, a_nrm.z));
  float shade = 0.55 + 0.45 * max(dot(n, normalize(vec3(-0.4, -0.5, 0.75))), 0.0);
  vec4 c = u_col[int(i_size.w) % ${_VH_MAX_CLASSES}];
  c.a *= mix(1.0, u_tunop, i_tun);
  v_col = vec4(c.rgb * shade * c.a, c.a);
}`;
const _VH_FS = `#version 300 es
precision mediump float; in vec4 v_col; out vec4 o_col; void main(){ o_col = v_col; }`;

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

// one vehicle layer for each level; they share the program and the buffers (made by the first)
function _vhLayerFor(level){
  return {
  id: _vhIds4(level)[3], type: "custom", renderingMode: "3d",
  onAdd(m, gl){
    if(_vhProg) return;
    if(!(typeof WebGL2RenderingContext !== "undefined" && gl instanceof WebGL2RenderingContext))
      throw new Error("rs.vehicles: the map has no WebGL2 context");
    _vhGl = gl;
    _vhProg = gl.createProgram();
    gl.attachShader(_vhProg, _vhShader(gl, gl.VERTEX_SHADER, _VH_VS));
    gl.attachShader(_vhProg, _vhShader(gl, gl.FRAGMENT_SHADER, _VH_FS));
    gl.linkProgram(_vhProg);
    if(!gl.getProgramParameter(_vhProg, gl.LINK_STATUS)) throw new Error("rs.vehicles: program: " + gl.getProgramInfoLog(_vhProg));
    for(const k of ["a_pos", "a_nrm", "i_pos", "i_size", "i_tun"]) _vhLoc[k] = gl.getAttribLocation(_vhProg, k);
    for(const k of ["u_m", "u_col", "u_tunop"]) _vhLoc[k] = gl.getUniformLocation(_vhProg, k);
    _vhVao = gl.createVertexArray(); gl.bindVertexArray(_vhVao);
    const box = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, box); gl.bufferData(gl.ARRAY_BUFFER, _vhBox(), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(_vhLoc.a_pos); gl.vertexAttribPointer(_vhLoc.a_pos, 3, gl.FLOAT, false, 24, 0);
    gl.enableVertexAttribArray(_vhLoc.a_nrm); gl.vertexAttribPointer(_vhLoc.a_nrm, 3, gl.FLOAT, false, 24, 12);
    _vhInstBuf = gl.createBuffer();
    for(const k of ["i_pos", "i_size", "i_tun"]){ gl.enableVertexAttribArray(_vhLoc[k]); gl.vertexAttribDivisor(_vhLoc[k], 1); }
    gl.bindVertexArray(null);
  },
  render(gl, args){
    if(!_vhScene) return;
    const now = performance.now();
    if(level === _vhLevels[0]) _vhTick(gl, now);       // the lowest level's layer is drawn first: it moves the clock and makes the frame
    const g = _vhByLevel.get(level);
    if(g){
      const [first, n] = g, st = _VH_STRIDE * 4, [, , ox, oy, u] = _vhOrigin;
      const m = _vhMul(args.defaultProjectionData.mainMatrix, [u,0,0,0, 0,u,0,0, 0,0,u,0, ox,oy,0,1]);
      gl.useProgram(_vhProg);
      gl.uniformMatrix4fv(_vhLoc.u_m, false, new Float32Array(m));
      gl.uniform4fv(_vhLoc.u_col, _vhColours);
      gl.uniform1f(_vhLoc.u_tunop, _vhTunnelOpacity());
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true);
      gl.disable(gl.CULL_FACE); gl.disable(gl.STENCIL_TEST);
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.bindVertexArray(_vhVao); gl.bindBuffer(gl.ARRAY_BUFFER, _vhInstBuf);
      gl.vertexAttribPointer(_vhLoc.i_pos, 4, gl.FLOAT, false, st, first * st);          // x, y, z, heading
      gl.vertexAttribPointer(_vhLoc.i_size, 4, gl.FLOAT, false, st, first * st + 24);    // length, width, height, class
      gl.vertexAttribPointer(_vhLoc.i_tun, 1, gl.FLOAT, false, st, first * st + 56);     // tunnel
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 36, n);
      gl.bindVertexArray(null);
    }
    if(_vhPlaying && level === _vhLevels[_vhLevels.length - 1]) map.triggerRepaint();
  }
  };
}

// the clock and, when it moved, the frame: the vehicles ordered by level (_vhByLevel)
function _vhTick(gl, now){
  if(_vhPlaying){
    if(_vhWall != null) _vhT = Math.min(_vhT + (now - _vhWall) / 1000 * _vhSpeed, _vhReport.t1);
    _vhWall = now; _vhDirty = true;
    if(_vhT >= _vhReport.t1) _vhPause();
  }
  if(!_vhDirty) return;
  const inst = _vhScene.frame(_vhT), n = inst.length / _VH_STRIDE, rows = new Map();
  _vhN = n;
  for(let i = 0; i < n; i++){
    const lv = inst[i * _VH_STRIDE + 10];
    if(!rows.has(lv)) rows.set(lv, []);
    rows.get(lv).push(i);
  }
  const out = new Float32Array(inst.length);
  let at = 0; _vhByLevel = new Map();
  for(const [lv, list] of rows){
    _vhByLevel.set(_vhLevels.includes(lv) ? lv : _vhLevels[0], [at, list.length]);
    for(const i of list) out.set(inst.subarray(i * _VH_STRIDE, (i + 1) * _VH_STRIDE), (at++) * _VH_STRIDE);
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, _vhInstBuf); gl.bufferData(gl.ARRAY_BUFFER, out, gl.DYNAMIC_DRAW);
  _vhDirty = false;
  if(now - _vhSentAt > 250){ _vhSentAt = now; _emit("rs:vehicletime", {t: _vhT}); }
}

// the opacity of a lane or a vehicle on a tunnel road: 1 - 0.75 x the tunnel strength (tunnel.js; 0 when the page has no tunnel look),
// times the tunnels' fade with the terrain on (elevation.js sets rs_terrain_tunnel)
function _vhTunnelOpacity(){
  const k = 1 - 0.75 * (TUNNEL && TUNNEL.strength != null ? +TUNNEL.strength : 0) / 100;
  let f = 1; try { const v = map.getGlobalState().rs_terrain_tunnel; if(v != null) f = +v; } catch(e){ /* a map with no global state */ }
  return k * f;
}

// every layer of the run on top, in the order of the levels: after the 3D switch, a base map change or a new style added layers
function _vhOnTop(){
  if(!_vhScene || !map.getLayer(_vhIds4(_vhLevels[0])[3])) return;
  _vhAddLanes();
  const want = _vhLevels.flatMap(lv => _vhIds4(lv)).filter(id => map.getLayer(id)), order = map.getLayersOrder();
  if(order.slice(-want.length).join() !== want.join()) want.forEach(id => map.moveLayer(id));
}

// a width in metres (`m`: a number or an expression) as pixels at each zoom, at the latitude `lat`
function _vhPx(m, lat){
  const k = 1 / (_VH_M_PX * Math.cos(lat * Math.PI / 180));
  return ["interpolate", ["exponential", 2], ["zoom"], 10, ["*", m, k * 2 ** 10], 24, ["*", m, k * 2 ** 24]];
}

// the lane layers: their colours in the theme, a tunnel lane faded (_vhTunnelOpacity)
function _vhLanePaint(){
  const l = O.vehicle_look.lanes, fill = _vhDark() ? l.fill.dark : l.fill.light, mark = _vhDark() ? l.marking.dark : l.marking.light;
  const op = ["case", ["get", "tunnel"], _vhTunnelOpacity(), 1];
  for(const lv of _vhLevels){
    const [jn, mk, fl] = _vhIds4(lv);
    if(map.getLayer(jn)) map.setPaintProperty(jn, "fill-color", fill);
    if(map.getLayer(mk)){ map.setPaintProperty(mk, "line-color", mark); map.setPaintProperty(mk, "line-opacity", op); }
    if(map.getLayer(fl)){ map.setPaintProperty(fl, "line-color", fill); map.setPaintProperty(fl, "line-opacity", op); }
  }
}

// the lane source and layers, under the vehicle layer (again after a style change that removed them)
function _vhAddLanes(){
  const src = RS_PREFIX + "vehicle-lanes";
  if(!_vhLanes) return;
  if(map.getSource(src) && _vhLanesIn !== _vhLanes) map.getSource(src).setData(_vhLanes);     // a second run
  _vhLanesIn = _vhLanes;
  if(map.getLayer(_vhIds4(_vhLevels[0])[2])) return;
  if(!O.vehicle_look || !O.vehicle_look.lanes) throw new Error("rs.vehicles: the look has no vehicles.lanes (the palette's colours, the profile's marking_m)");
  const lat = _vhOrigin[1], mm = O.vehicle_look.lanes.marking_m, round = {"line-cap": "butt", "line-join": "round"};
  if(!map.getSource(src)) map.addSource(src, {type: "geojson", data: _vhLanes});
  for(const lv of _vhLevels){
    const [jn, mk, fl, veh] = _vhIds4(lv), at = ["==", ["get", "level"], lv], lane = ["all", at, ["==", ["get", "kind"], "lane"]];
    map.addLayer({id: jn, type: "fill", source: src, filter: ["all", at, ["==", ["get", "kind"], "junction"]]}, veh);
    map.addLayer({id: mk, type: "line", source: src, filter: ["all", lane, ["!", ["get", "internal"]]], layout: round,
                  paint: {"line-width": _vhPx(["get", "w"], lat)}}, veh);
    map.addLayer({id: fl, type: "line", source: src, filter: lane, layout: round,
                  paint: {"line-width": _vhPx(["case", ["get", "internal"], ["get", "w"], ["-", ["get", "w"], mm]], lat)}}, veh);
  }
  _vhLanePaint();
}

// "#rrggbb" or [r, g, b, a] (0..1) to [r, g, b, a]
function _vhRgba(c, cls){
  if(Array.isArray(c) && c.length === 4) return c;
  const h = typeof c === "string" && /^#[0-9a-f]{6}$/i.exec(c) ? c : null;
  if(!h) throw new Error(`rs.vehicles.load: colours.${cls} must be "#rrggbb" or [r, g, b, a], not ${JSON.stringify(c)}`);
  return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).concat(1);
}

function _vhPause(){ _vhPlaying = false; _vhWall = null; }

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
// the bytes of a WebAssembly file; a gzip file (roadstyle's own module, roadstyle_wasm_bg.wasm.gz) is decompressed
async function _vhWasm(x){
  const b = await _vhBytes(x);
  return b[0] === 0x1f && b[1] === 0x8b ? new Uint8Array(await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer()) : b;
}
// the page's road of each SUMO edge (SUMO edge id = the road's edge_id): {edge_id: [level, tunnel]}, from the road table (it can come
// after the style: rs:tableready)
let _vhOn = false;
async function _vhEdges(){
  let t = _side();
  if(!t) await new Promise(r => document.addEventListener("rs:tableready", r, {once: true}));
  t = _side();
  const out = {};
  for(const p of t.props) if(p && p.edge_id != null){
    const lv = p.fill_level != null ? +p.fill_level : 0, tun = p.tunnel != null && p.tunnel !== "no" && p.tunnel !== false ? 1 : 0;
    out[String(p.edge_id)] = [lv, tun];
  }
  return out;
}
async function _vhText(x){ return x == null ? undefined : (/^\s*</.test(x) ? x : await (await fetch(x)).text()); }

// load({wasm, wasm_bin?, fcd, net, routes, lanes?, options?, colours?}): `wasm` the URL of roadstyle_wasm.js built with the feature "vehicles";
// `wasm_bin` (optional) the bytes or the URL of its roadstyle_wasm_bg.wasm, or of that file in gzip (needed when `wasm` is a data: URL, which has no folder); `fcd` the
// bytes or the URL of SUMO's FCD Parquet file; `net` the text or the URL of the run's net.xml; `routes` (optional) the text or URL of
// a file with the <vType> elements. `options` (every key of _VH_KEYS) and `colours` ({class: "#rrggbb"}) default to the look's vehicles
// section. `lanes` (default true): draw the lanes of net.xml under the vehicles. Gives the run's report and sends rs:vehicleload. A page with the option `vehicles` calls it at start (index.js).
async function _vhLoad(o){
  for(const k of ["wasm", "fcd"]) if(o[k] == null) throw new Error(`rs.vehicles.load: ${k} is missing`);
  if((o.options == null || o.colours == null) && !O.vehicle_look)
    throw new Error("rs.vehicles.load: no options or colours, and the look has no vehicles section");
  const options = o.options || _vhOptions(O.vehicle_look);
  for(const k of _VH_KEYS) if(options[k] == null) throw new Error(`rs.vehicles.load: options.${k} is missing`);
  const mod = await import(new URL(o.wasm, document.baseURI).href);
  await mod.default(o.wasm_bin == null ? undefined : {module_or_path: await _vhWasm(o.wasm_bin)});
  const [fcd, net, routes] = await Promise.all([_vhBytes(o.fcd), _vhText(o.net), _vhText(o.routes)]);
  const scene = new mod.VehicleScene(fcd, net, routes, JSON.stringify(options));
  _vhClasses = scene.classes(); _vhGiven = o.colours || null;
  _vhPaint();
  _vhScene = scene; _vhOrigin = scene.origin(); _vhIds = scene.ids();
  _vhReport = JSON.parse(scene.report());
  scene.setEdges(JSON.stringify(await _vhEdges()));
  _vhLanes = o.lanes === false ? null : JSON.parse(scene.lanes());
  _vhLevels = [...new Set([0, ...(_vhLanes ? _vhLanes.features.map(f => f.properties.level) : [])])].sort((a, b) => a - b);
  _vhT = _vhReport.t0; _vhDirty = true; _vhPause();
  // the style can be busy after "load" (a theme or base map change of the page): wait for an "idle" with the style loaded, not for
  // "load", which fires once only
  await new Promise(r => { const ok = () => map.isStyleLoaded() ? r() : map.once("idle", ok); ok(); });
  for(const lv of _vhLevels) if(!map.getLayer(_vhIds4(lv)[3])) map.addLayer(_vhLayerFor(lv));
  if(!_vhOn){
    _vhOn = true; map.on("styledata", _vhOnTop);
    const repaint = () => { if(_vhScene){ _vhPaint(); if(_vhLanes) _vhLanePaint(); map.triggerRepaint(); } };
    for(const e of ["rs:themechange", "rs:tunnelchange", "rs:terrainchange", "rs:tunnelsopacitychange"]) document.addEventListener(e, repaint);
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
    ids(){ return _vhIds ? _vhIds.slice() : []; },
    report(){ return _vhReport ? {..._vhReport} : null; },
  };
}

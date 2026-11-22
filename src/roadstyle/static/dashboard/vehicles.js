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
// THE SHAPES: each kind of the look has its own mesh (_VH_SHAPES) and colour; the instances of one kind are drawn together.
// P1: flat ground (z 0), no camera.
import {map, O, RS_PREFIX, _emit} from "./core.js";

const _VH_STRIDE = 16;                 // the numbers of one vehicle in VehicleScene.frame
const _VH_MAX_CLASSES = 8;             // the colours the shader holds (a class number past it takes colour number % 8)
const _VH_KEYS = ["placement", "teleport_m", "lane_change_s", "heading_lookahead_m", "class_sizes"];
const _vhLayerId = () => RS_PREFIX + "vehicles";
const _vhLaneIds = () => [RS_PREFIX + "vehicle-lane-marking", RS_PREFIX + "vehicle-lane-fill", RS_PREFIX + "vehicle-junctions"];
const _VH_M_PX = 40075016.686 / 512;   // the metres of one pixel at zoom 0 at the equator (MapLibre's 512 px tiles)
let _vhLanes = null, _vhLanesIn = null; // the lanes' GeoJSON (null: the page shows no lanes), and the GeoJSON in the source now

let _vhScene = null, _vhOrigin = null, _vhColours = null, _vhReport = null, _vhIds = null, _vhClasses = [], _vhGiven = null;
let _vhT = 0, _vhSpeed = 1, _vhPlaying = false, _vhWall = null, _vhSentAt = 0, _vhDirty = true;
let _vhGl = null, _vhProg = null, _vhVao = null, _vhInstBuf = null, _vhN = 0, _vhLoc = {};
let _vhKindOf = [], _vhGroups = [];    // the shape of each class number; the kinds of this frame: [shape, first instance, count]

// THE SHAPES: one mesh for each kind of the look (vehicles.classes.<class>.kind), in the unit space of a vehicle: x forward (-0.5..0.5 of
// the length), y right (-0.5..0.5 of the width), z up (0..1 of the height). Each vertex: position, normal, tone (the colour's factor:
// 1 the body, below 1 the glass, above 1 the lights at the front, so the heading shows). A kind with no mesh of its own takes the car's.
// a block: x0..x1, y0..y1, z0..z1, tone; `nose` (0..1) slopes the top of the front face back by that part of the length (a windscreen)
function _vhBlock(v, [x0, x1], [y0, y1], [z0, z1], tone, nose = 0){
  const xt = x1 - nose * (x1 - x0);
  const P = {a: [x0, y0, z0], b: [x1, y0, z0], c: [x1, y1, z0], d: [x0, y1, z0], e: [x0, y0, z1], f: [xt, y0, z1], g: [xt, y1, z1], h: [x0, y1, z1]};
  const face = (q, t = tone) => {
    const [p0, p1, p2] = q.map(k => P[k]);
    const u = p1.map((x, i) => x - p0[i]), w = p2.map((x, i) => x - p0[i]);
    let n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]];
    const l = Math.hypot(...n) || 1; n = n.map(x => x / l);
    for(const k of [0, 1, 2, 0, 2, 3]) v.push(...P[q[k]], ...n, t);
  };
  face(["b", "c", "g", "f"], nose ? tone * 0.55 : tone);   // the front (a sloped front is glass)
  face(["d", "a", "e", "h"]); face(["c", "d", "h", "g"]); face(["a", "b", "f", "e"]);
  face(["e", "f", "g", "h"]); face(["d", "c", "b", "a"]);
}
const _VH_GLASS = 0.5, _VH_LIGHT = 1.35;
const _VH_SHAPES = {
  car(v){
    _vhBlock(v, [-0.5, 0.5], [-0.5, 0.5], [0.12, 0.55], 1);              // the body
    _vhBlock(v, [-0.32, 0.22], [-0.44, 0.44], [0.55, 1], _VH_GLASS, 0.3);  // the cabin, its windscreen to the front
    _vhBlock(v, [0.47, 0.5], [-0.42, -0.22], [0.3, 0.45], _VH_LIGHT); _vhBlock(v, [0.47, 0.5], [0.22, 0.42], [0.3, 0.45], _VH_LIGHT);
  },
  bus(v){
    _vhBlock(v, [-0.5, 0.5], [-0.5, 0.5], [0.08, 0.62], 1);
    _vhBlock(v, [-0.48, 0.5], [-0.5, 0.5], [0.62, 0.9], _VH_GLASS);        // the band of windows
    _vhBlock(v, [-0.5, 0.5], [-0.5, 0.5], [0.9, 1], 1);
    _vhBlock(v, [0.49, 0.5], [-0.45, 0.45], [0.2, 0.3], _VH_LIGHT);
  },
  truck(v){
    _vhBlock(v, [0.22, 0.5], [-0.48, 0.48], [0.1, 0.55], 1);              // the cab
    _vhBlock(v, [0.22, 0.46], [-0.46, 0.46], [0.55, 0.85], _VH_GLASS, 0.2);
    _vhBlock(v, [-0.5, 0.19], [-0.5, 0.5], [0.12, 1], 0.85);              // the box
    _vhBlock(v, [0.48, 0.5], [-0.42, 0.42], [0.18, 0.28], _VH_LIGHT);
  },
  motorcycle(v){
    _vhBlock(v, [-0.5, 0.5], [-0.18, 0.18], [0.12, 0.45], 1);             // the frame
    _vhBlock(v, [-0.2, 0.12], [-0.4, 0.4], [0.45, 1], _VH_GLASS);         // the rider
    _vhBlock(v, [0.44, 0.5], [-0.12, 0.12], [0.35, 0.5], _VH_LIGHT);
  },
  bicycle(v){
    _vhBlock(v, [-0.5, 0.5], [-0.08, 0.08], [0.1, 0.4], 1);
    _vhBlock(v, [-0.25, 0.05], [-0.45, 0.45], [0.4, 1], _VH_GLASS);
  },
  rail(v){
    _vhBlock(v, [-0.5, 0.5], [-0.5, 0.5], [0.05, 0.6], 1);
    _vhBlock(v, [-0.5, 0.5], [-0.5, 0.5], [0.6, 0.88], _VH_GLASS, 0.03);
    _vhBlock(v, [-0.5, 0.485], [-0.5, 0.5], [0.88, 1], 1);
  },
};

// every kind's mesh in one buffer: the vertices (7 numbers each) and, for each kind, its first vertex and its vertex count
function _vhMeshes(){
  const v = [], at = {};
  for(const [k, make] of Object.entries(_VH_SHAPES)){ const first = v.length / 7; make(v); at[k] = [first, v.length / 7 - first]; }
  return {data: new Float32Array(v), at};
}
const _VH_MESH = _vhMeshes();

const _VH_VS = `#version 300 es
in vec3 a_pos; in vec3 a_nrm; in float a_tone;
in vec4 i_pos;                  // x, y, z (origin metres; y south), heading (radians, 0 = north, clockwise)
in vec4 i_size;                 // length, width, height (m), class
uniform mat4 u_m; uniform vec4 u_col[${_VH_MAX_CLASSES}];
out vec4 v_col;
void main(){
  float h = i_pos.w;
  vec2 f = vec2(sin(h), -cos(h)), r = vec2(cos(h), sin(h));   // forward and right in Mercator's x east, y south
  vec2 xy = i_pos.xy + f * (a_pos.x * i_size.x) + r * (a_pos.y * i_size.y);
  gl_Position = u_m * vec4(xy, i_pos.z + a_pos.z * i_size.z, 1.0);
  vec3 n = normalize(vec3(f * a_nrm.x + r * a_nrm.y, a_nrm.z));
  float shade = 0.55 + 0.45 * max(dot(n, normalize(vec3(-0.4, -0.5, 0.75))), 0.0);
  vec4 c = u_col[int(i_size.w) % ${_VH_MAX_CLASSES}];
  v_col = vec4(min(c.rgb * shade * a_tone, vec3(1.0)) * c.a, c.a);
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
    for(const k of ["a_pos", "a_nrm", "a_tone", "i_pos", "i_size"]) _vhLoc[k] = gl.getAttribLocation(_vhProg, k);
    _vhLoc.u_m = gl.getUniformLocation(_vhProg, "u_m"); _vhLoc.u_col = gl.getUniformLocation(_vhProg, "u_col");
    _vhVao = gl.createVertexArray(); gl.bindVertexArray(_vhVao);
    const mesh = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, mesh); gl.bufferData(gl.ARRAY_BUFFER, _VH_MESH.data, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(_vhLoc.a_pos); gl.vertexAttribPointer(_vhLoc.a_pos, 3, gl.FLOAT, false, 28, 0);
    gl.enableVertexAttribArray(_vhLoc.a_nrm); gl.vertexAttribPointer(_vhLoc.a_nrm, 3, gl.FLOAT, false, 28, 12);
    gl.enableVertexAttribArray(_vhLoc.a_tone); gl.vertexAttribPointer(_vhLoc.a_tone, 1, gl.FLOAT, false, 28, 24);
    _vhInstBuf = gl.createBuffer();
    gl.enableVertexAttribArray(_vhLoc.i_pos); gl.vertexAttribDivisor(_vhLoc.i_pos, 1);
    gl.enableVertexAttribArray(_vhLoc.i_size); gl.vertexAttribDivisor(_vhLoc.i_size, 1);
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
      _vhN = inst.length / _VH_STRIDE;
      gl.bindBuffer(gl.ARRAY_BUFFER, _vhInstBuf); gl.bufferData(gl.ARRAY_BUFFER, _vhByShape(inst), gl.DYNAMIC_DRAW);
      _vhDirty = false;
      if(now - _vhSentAt > 250){ _vhSentAt = now; _emit("rs:vehicletime", {t: _vhT}); }
    }
    if(_vhN){
      const [, , ox, oy, u] = _vhOrigin;
      const m = _vhMul(args.defaultProjectionData.mainMatrix, [u,0,0,0, 0,u,0,0, 0,0,u,0, ox,oy,0,1]);
      gl.useProgram(_vhProg);
      gl.uniformMatrix4fv(_vhLoc.u_m, false, new Float32Array(m));
      gl.uniform4fv(_vhLoc.u_col, _vhColours);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true);
      gl.disable(gl.CULL_FACE); gl.disable(gl.STENCIL_TEST);
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.bindVertexArray(_vhVao); gl.bindBuffer(gl.ARRAY_BUFFER, _vhInstBuf);
      const st = _VH_STRIDE * 4;
      for(const [shape, first, n] of _vhGroups){
        gl.vertexAttribPointer(_vhLoc.i_pos, 4, gl.FLOAT, false, st, first * st);        // x, y, z, heading
        gl.vertexAttribPointer(_vhLoc.i_size, 4, gl.FLOAT, false, st, first * st + 24);  // length, width, height, class
        const [v0, nv] = _VH_MESH.at[shape];
        gl.drawArraysInstanced(gl.TRIANGLES, v0, nv, n);
      }
      gl.bindVertexArray(null);
    }
    if(_vhPlaying) map.triggerRepaint();
  }
};

// the instances of a frame ordered by shape, and _vhGroups: [shape, first instance, count] for each shape of the frame
function _vhByShape(inst){
  const n = inst.length / _VH_STRIDE, groups = new Map();
  for(let i = 0; i < n; i++){
    const k = _vhKindOf[inst[i * _VH_STRIDE + 9]] || "car";
    if(!groups.has(k)) groups.set(k, []);
    groups.get(k).push(i);
  }
  const out = new Float32Array(inst.length);
  let at = 0; _vhGroups = [];
  for(const [k, rows] of groups){
    _vhGroups.push([k, at, rows.length]);
    for(const i of rows) out.set(inst.subarray(i * _VH_STRIDE, (i + 1) * _VH_STRIDE), (at++) * _VH_STRIDE);
  }
  return out;
}

// the layer on top: after the 3D switch, a base map change or a new style added layers above it
function _vhOnTop(){
  const id = _vhLayerId();
  if(!map.getLayer(id)) return;
  _vhAddLanes();
  const order = map.getLayersOrder();
  if(order[order.length - 1] !== id) map.moveLayer(id);
}

// a width in metres (`m`: a number or an expression) as pixels at each zoom, at the latitude `lat`
function _vhPx(m, lat){
  const k = 1 / (_VH_M_PX * Math.cos(lat * Math.PI / 180));
  return ["interpolate", ["exponential", 2], ["zoom"], 10, ["*", m, k * 2 ** 10], 24, ["*", m, k * 2 ** 24]];
}

// the lane layers: their colours in the theme
function _vhLanePaint(){
  const l = O.vehicle_look.lanes, [mk, fl, jn] = _vhLaneIds();
  if(map.getLayer(jn)) map.setPaintProperty(jn, "fill-color", _vhDark() ? l.fill.dark : l.fill.light);
  if(map.getLayer(mk)) map.setPaintProperty(mk, "line-color", _vhDark() ? l.marking.dark : l.marking.light);
  if(map.getLayer(fl)) map.setPaintProperty(fl, "line-color", _vhDark() ? l.fill.dark : l.fill.light);
}

// the lane source and layers, under the vehicle layer (again after a style change that removed them)
function _vhAddLanes(){
  const src = RS_PREFIX + "vehicle-lanes";
  if(!_vhLanes) return;
  if(map.getSource(src) && _vhLanesIn !== _vhLanes) map.getSource(src).setData(_vhLanes);     // a second run
  _vhLanesIn = _vhLanes;
  if(map.getLayer(_vhLaneIds()[1])) return;
  if(!O.vehicle_look || !O.vehicle_look.lanes) throw new Error("rs.vehicles: the look has no vehicles.lanes (the palette's colours, the profile's marking_m)");
  const lat = _vhOrigin[1], mm = O.vehicle_look.lanes.marking_m, [mk, fl, jn] = _vhLaneIds();
  if(!map.getSource(src)) map.addSource(src, {type: "geojson", data: _vhLanes});
  const before = map.getLayer(_vhLayerId()) ? _vhLayerId() : undefined, round = {"line-cap": "butt", "line-join": "round"};
  const lane = ["==", ["get", "kind"], "lane"];
  map.addLayer({id: jn, type: "fill", source: src, filter: ["==", ["get", "kind"], "junction"]}, before);
  map.addLayer({id: mk, type: "line", source: src, filter: ["all", lane, ["!", ["get", "internal"]]], layout: round, paint: {"line-width": _vhPx(["get", "w"], lat)}}, before);
  map.addLayer({id: fl, type: "line", source: src, filter: lane, layout: round,
                paint: {"line-width": _vhPx(["case", ["get", "internal"], ["get", "w"], ["-", ["get", "w"], mm]], lat)}}, before);
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
  _vhKindOf = _vhClasses.map(c => { const k = O.vehicle_look && O.vehicle_look.classes[c] && O.vehicle_look.classes[c].kind; return k in _VH_SHAPES ? k : "car"; });
  _vhPaint();
  _vhScene = scene; _vhOrigin = scene.origin(); _vhIds = scene.ids();
  _vhReport = JSON.parse(scene.report());
  _vhLanes = o.lanes === false ? null : JSON.parse(scene.lanes());
  _vhT = _vhReport.t0; _vhDirty = true; _vhPause();
  // the style can be busy after "load" (a theme or base map change of the page): wait for an "idle" with the style loaded, not for
  // "load", which fires once only
  await new Promise(r => { const ok = () => map.isStyleLoaded() ? r() : map.once("idle", ok); ok(); });
  _vhLayer.id = _vhLayerId();
  if(!map.getLayer(_vhLayer.id)){
    map.addLayer(_vhLayer); map.on("styledata", _vhOnTop);
    document.addEventListener("rs:themechange", () => { if(_vhScene){ _vhPaint(); if(_vhLanes) _vhLanePaint(); map.triggerRepaint(); } });
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

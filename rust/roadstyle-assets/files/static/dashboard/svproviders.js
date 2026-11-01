// STREET PHOTOS BESIDE GOOGLE: Panoramax (open data, no key) and Mapillary (free, needs a client token
// that the person saves in Settings > Keys). For a spot on a road each finds the nearest photo within
// _SP_RADIUS metres, and a viewer (Photo Sphere Viewer for Panoramax, MapillaryJS for Mapillary, loaded from
// a CDN when first needed) shows it inside the Street View window (streetview.js) and reports where it looks, so
// the map marker turns with it. Each can also draw where it has photos (its coverage) on the map as vector tiles.
import {map, O, _src} from "./core.js";
import {savedKey} from "./settings.js";

export const _SP_RADIUS = 30;
const _SP_PANORAMAX = "https://api.panoramax.xyz";
export const SV_PROVIDERS = {
  google:    {title: "Google"},
  panoramax: {title: "Panoramax", credit: "Panoramax contributors (CC-BY-SA)", href: "https://panoramax.fr/", color: "#e8590c"},
  mapillary: {title: "Mapillary", credit: "Mapillary contributors (CC-BY-SA)", href: "https://www.mapillary.com/", color: "#05a350"},
};
export const _spToken = () => savedKey("mapillary") || O.mapillary_token || "";
export const _spNeedsToken = p => p === "mapillary" && !_spToken();
const _spDist = (a, b, c, d) => { const k = Math.cos(a * Math.PI / 180);
  return Math.hypot((c - a) * 110540, (d - b) * 110540 * k); };       // metres, short distances

// ---- Panoramax photos: one list, filled by the lookups and by the load ahead along the selected road ----
const _spPan = {photos: new Map(), boxes: [], blobs: new Map(), tok: 0};
const _spPanPhoto = f => {
  const sd = f.assets && (f.assets.sd || f.assets.hd); if(!sd || !f.geometry) return null;
  const q = f.properties || {}, io = q["pers:interior_orientation"] || {};
  return {id: f.id, lng: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], az: q["view:azimuth"] || 0,
          by: q["geovisio:producer"], url: sd.href, fov: io.field_of_view || 70};
};
const _spBoxHas = (b, lat, lng) => lng >= b[0] && lng <= b[2] && lat >= b[1] && lat <= b[3];
const _spCovered = (lat, lng) => {            // the whole search circle of a spot is inside a box that was loaded in full
  const dy = _SP_RADIUS / 111320, dx = dy / Math.max(.05, Math.cos(lat * Math.PI / 180));
  return _spPan.boxes.some(b => _spBoxHas(b, lat - dy, lng - dx) && _spBoxHas(b, lat + dy, lng + dx));
};
// What a photo's direction costs, in metres: 0 for a 360 photo or an unknown direction, a little for turning from the road's direction
// (up to 45 degrees), and Infinity for a photo that looks aside or back. The photo must show the road the way it runs.
function _spAim(az, fov, heading, turn){
  if(heading == null || fov >= 300 || az == null) return 0;
  const t = turn(az, heading);
  return t <= 45 ? t * .3 : Infinity;
}
// the photo nearest the spot that looks along the road; the service does not sort by distance
function _spPanPick(list, lat, lng, heading){
  const turn = (a, b) => { const d = Math.abs(_spDeg(a - b)); return d > 180 ? 360 - d : d; };
  let best = null, bs = Infinity;
  for(const q of list){
    const d = _spDist(lat, lng, q.lat, q.lng); if(d > _SP_RADIUS) continue;
    // a flat photo must look the way the road runs (within 45 degrees); a 360 panorama has every direction
    const sc = d + _spAim(q.az, q.fov, heading, turn); if(sc >= Infinity) continue;
    if(sc < bs){ bs = sc; best = q; } }
  if(!best) return null;
  // sx, sy: the spot on the road, where the map marker stays (a photo's own position is a GPS fix, often beside the road)
  return {id: best.id, lng: best.lng, lat: best.lat, sx: lng, sy: lat, by: best.by, azimuth: best.az, fov: best.fov,
          url: _spPan.blobs.get(best.url) || best.url};
}
// Load ahead the photos along a road (line: [[lng, lat], ...]) near the spot (lat, lng): their list, in boxes along the line,
// and the images of the nearest ones into memory. A new road cancels the old load.
export function _spPrefetch(provider, line, lat, lng){
  const tok = ++_spPan.tok;
  if(provider !== "panoramax" || !line || line.length < 2) return;
  const k = Math.cos(lat * Math.PI / 180), pts = [];
  for(let i = 1; i < line.length; i++){            // a sample every ~100 m along the line
    const [x0, y0] = line[i - 1], [x1, y1] = line[i], n = Math.max(1, Math.ceil(_spDist(y0, x0, y1, x1) / 100));
    for(let j = 0; j <= n; j++) pts.push([x0 + (x1 - x0) * j / n, y0 + (y1 - y0) * j / n]);
  }
  const near = pts.map(c => [_spDist(lat, lng, c[1], c[0]), c]).sort((a, b) => a[0] - b[0]).slice(0, 16).map(x => x[1]);
  const dy = 70 / 111320, dx = dy / Math.max(.05, k), have = [];
  let at = 0;
  const lane = async () => {
    while(at < near.length && tok === _spPan.tok){
      const c = near[at++], box = [c[0] - dx, c[1] - dy, c[0] + dx, c[1] + dy];
      if(_spPan.boxes.some(b => _spBoxHas(b, box[1], box[0]) && _spBoxHas(b, box[3], box[2]))) continue;
      try{
        const r = await fetch(_SP_PANORAMAX + "/api/search?limit=100&bbox=" + box.map(v => v.toFixed(6)).join(","));
        if(!r.ok) continue;
        const fs = ((await r.json()).features || []).map(_spPanPhoto).filter(Boolean);
        fs.forEach(q => _spPan.photos.has(q.id) || _spPan.photos.set(q.id, q));
        if(fs.length < 100) _spPan.boxes.push(box);        // a full answer may have left photos out
        have.push(...fs);
      }catch(e){}
    } };
  Promise.all([lane(), lane(), lane()]).then(async () => {
    if(tok !== _spPan.tok) return;
    const todo = have.filter(q => !_spPan.blobs.has(q.url)).map(q => [_spDist(lat, lng, q.lat, q.lng), q])
      .sort((a, b) => a[0] - b[0]).slice(0, 30).map(x => x[1]);
    let i = 0;
    const img = async () => {
      while(i < todo.length && tok === _spPan.tok){
        const q = todo[i++];
        try{ const r = await fetch(q.url); if(r.ok) _spPan.blobs.set(q.url, URL.createObjectURL(await r.blob())); }catch(e){}
      } };
    await Promise.all([img(), img(), img()]);
    // keep the memory small: forget the oldest images
    for(const [u, b] of _spPan.blobs){ if(_spPan.blobs.size <= 80) break; URL.revokeObjectURL(b); _spPan.blobs.delete(u); }
  });
}

// the nearest photo to a spot: {id, lat, lng, ...what its viewer needs} | null (none within the radius);
// rejects when the service cannot be asked (offline, a wrong token)
export async function _spFind(provider, lat, lng, heading){
  if(provider === "panoramax"){
    // the photos along the road that were loaded ahead (_spPrefetch) answer at once
    if(_spCovered(lat, lng)) return _spPanPick([..._spPan.photos.values()], lat, lng, heading);
    const r = await fetch(_SP_PANORAMAX + "/api/search?limit=30&place_position=" + lng.toFixed(6) + "," + lat.toFixed(6) +
                          "&place_distance=0-" + _SP_RADIUS);
    if(!r.ok) throw new Error("Panoramax answered " + r.status);
    const got = ((await r.json()).features || []).map(_spPanPhoto).filter(Boolean);
    got.forEach(q => _spPan.photos.has(q.id) || _spPan.photos.set(q.id, q));
    return _spPanPick(got, lat, lng, heading);
  }
  if(provider === "mapillary"){
    const dy = _SP_RADIUS / 111320, dx = dy / Math.max(.05, Math.cos(lat * Math.PI / 180));   // a box of the radius around the spot
    const bbox = [lng - dx, lat - dy, lng + dx, lat + dy].map(v => v.toFixed(6)).join(",");
    const r = await fetch("https://graph.mapillary.com/images?fields=id,geometry,compass_angle,is_pano&limit=100&bbox=" + bbox + "&access_token=" + encodeURIComponent(_spToken()));
    if(!r.ok) throw new Error(r.status === 400 || r.status === 401 || r.status === 403 ? "Mapillary refused the token." : "Mapillary answered " + r.status);
    let best = null, bs = Infinity;
    const turn = (a, b) => { const d = Math.abs(_spDeg(a - b)); return d > 180 ? 360 - d : d; };
    for(const f of (await r.json()).data || []){
      const [x, y] = f.geometry.coordinates, d = _spDist(lat, lng, y, x); if(d > _SP_RADIUS) continue;
      // like Panoramax: a flat image must look the way the road runs (within 45 degrees); a 360 image has every direction
      const sc = d + _spAim(f.compass_angle, f.is_pano ? 360 : 70, heading, turn); if(sc >= Infinity) continue;
      if(sc < bs){ bs = sc; best = {id: f.id, lng: x, lat: y}; } }
    if(!best) return null;
    return best;
  }
  return null;
}

// ---- coverage: where a provider has photos, drawn as lines (sequences) and dots (single photos) ----
// Only inside the page's area (the bounds of its roads): the tiles are read back (querySourceFeatures) and their lines cut at the area's edge.
const _SP_SRC = "rs-sv-cov", _SP_OUT = "rs-sv-cov-out", _SP_SEL = "rs-sv-cov-sel", _SP_LAYERS = ["rs-sv-cov-load", "rs-sv-cov-lines", "rs-sv-cov-dots", "rs-sv-cov-ring"];
let _spPicked = null;       // the photo opened from a dot: [lng, lat] (drawn as a ring), or null
let _spCov = null, _spHooked = false, _spTimer = 0, _spWarned = false;
const _spBox = () => { const b = O.camera && O.camera.bounds; return b ? [b[0][0], b[0][1], b[1][0], b[1][1]] : null; };
// the parts of the segment a-b inside the box (Liang-Barsky), or null
function _spSeg(a, b, [x0, y0, x1, y1]){
  let t0 = 0, t1 = 1; const dx = b[0] - a[0], dy = b[1] - a[1];
  for(const [p, q] of [[-dx, a[0] - x0], [dx, x1 - a[0]], [-dy, a[1] - y0], [dy, y1 - a[1]]]){
    if(p === 0){ if(q < 0) return null; continue; }
    const r = q / p; if(p < 0){ if(r > t1) return null; if(r > t0) t0 = r; } else { if(r < t0) return null; if(r < t1) t1 = r; } }
  return [[a[0] + t0 * dx, a[1] + t0 * dy], [a[0] + t1 * dx, a[1] + t1 * dy]];
}
function _spCut(line, box){
  const out = []; let cur = null;
  for(let i = 1; i < line.length; i++){
    const s = _spSeg(line[i - 1], line[i], box);
    if(!s){ cur = null; continue; }
    if(cur && cur[cur.length - 1][0] === s[0][0] && cur[cur.length - 1][1] === s[0][1]) cur.push(s[1]);
    else { cur = [s[0], s[1]]; out.push(cur); } }
  return out;
}
// the page's `boundary` (the outer rings of its polygons), or null when it has none
function _spRings(){
  const role = _src("boundary"), src = role && map.getSource(role.source), fc = src && src.serialize().data, rings = [];
  for(const f of (fc && fc.features) || []){
    const g = f.geometry; if(!g) continue;
    if(g.type === "Polygon") rings.push(g.coordinates[0]);
    else if(g.type === "MultiPolygon") g.coordinates.forEach(q => rings.push(q[0]));
  }
  return rings.length ? rings : null;
}
const _spIn = (rings, x, y) => { let n = 0;       // inside an odd number of rings (even-odd rule)
  for(const r of rings) for(let i = 1; i < r.length; i++){
    const [x0, y0] = r[i - 1], [x1, y1] = r[i];
    if((y0 > y) !== (y1 > y) && x < x0 + (y - y0) * (x1 - x0) / (y1 - y0)) n++; }
  return n % 2 === 1; };
// the parts of a line inside the rings: every segment is split where it crosses a ring, and the pieces whose middle is inside are kept
function _spCutRings(line, rings){
  const out = []; let cur = null;
  for(let i = 1; i < line.length; i++){
    const [ax, ay] = line[i - 1], [bx, by] = line[i], dx = bx - ax, dy = by - ay, ts = [0, 1];
    for(const r of rings) for(let j = 1; j < r.length; j++){
      const [cx, cy] = r[j - 1], ex = r[j][0] - cx, ey = r[j][1] - cy, den = dx * ey - dy * ex;
      if(!den) continue;
      const t = ((cx - ax) * ey - (cy - ay) * ex) / den, u = ((cx - ax) * dy - (cy - ay) * dx) / den;
      if(t > 0 && t < 1 && u >= 0 && u <= 1) ts.push(t); }
    ts.sort((a, b) => a - b);
    for(let k = 1; k < ts.length; k++){
      const m = (ts[k - 1] + ts[k]) / 2;
      if(ts[k] === ts[k - 1] || !_spIn(rings, ax + dx * m, ay + dy * m)){ cur = null; continue; }
      const p0 = [ax + dx * ts[k - 1], ay + dy * ts[k - 1]], p1 = [ax + dx * ts[k], ay + dy * ts[k]];
      if(cur && cur[cur.length - 1][0] === p0[0] && cur[cur.length - 1][1] === p0[1]) cur.push(p1);
      else { cur = [p0, p1]; out.push(cur); } }
  }
  return out;
}
function _spSync(){
  _spTimer = 0;
  const rings = _spRings(), box = rings ? [Math.min(...rings.flat().map(c => c[0])), Math.min(...rings.flat().map(c => c[1])),
    Math.max(...rings.flat().map(c => c[0])), Math.max(...rings.flat().map(c => c[1]))] : _spBox(), out = map.getSource(_SP_OUT);
  if(!_spCov || !box || !out || !map.getSource(_SP_SRC)) return;
  const pan = _spCov === "panoramax", feats = [], seen = new Set();
  for(const f of map.querySourceFeatures(_SP_SRC, {sourceLayer: pan ? "sequences" : "sequence"})){
    const g = f.geometry, lines = g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : [];
    for(const l of lines) for(const c of rings ? _spCutRings(l, rings) : _spCut(l, box)){ const k = c.join(); if(!seen.has(k)){ seen.add(k); feats.push({type: "Feature", properties: {}, geometry: {type: "LineString", coordinates: c}}); } } }
  for(const f of map.querySourceFeatures(_SP_SRC, {sourceLayer: pan ? "pictures" : "image"})){
    const c = f.geometry.type === "Point" ? f.geometry.coordinates : null;
    if(c && (rings ? _spIn(rings, c[0], c[1]) : c[0] >= box[0] && c[0] <= box[2] && c[1] >= box[1] && c[1] <= box[3])){ const k = "p" + c.join(); if(!seen.has(k)){ seen.add(k); feats.push({type: "Feature", properties: f.properties || {}, geometry: {type: "Point", coordinates: c}}); } } }
  out.setData({type: "FeatureCollection", features: feats});
}
const _spLater = () => { if(!_spTimer) _spTimer = setTimeout(_spSync, 120); };
export function _spCoverage(provider, onError){   // a provider's name draws its coverage; anything else (or null) takes it away
  if(!map) return;
  if(!_spHooked){ _spHooked = true;               // a new base map style drops the layers: draw them again
    map.on("style.load", () => { const p = _spCov; _spCov = null; _spCoverage(p); });
    map.on("sourcedata", e => { if(e.sourceId === _SP_SRC && e.isSourceLoaded) _spLater(); });
    map.on("moveend", _spLater);
    map.on("error", e => { if(_spCov && e.sourceId === _SP_SRC && !_spWarned){ _spWarned = true; console.warn("coverage tiles:", e.error && e.error.message); if(_spOnError) _spOnError(e.error); } }); }
  _spOnError = onError || _spOnError;
  const want = SV_PROVIDERS[provider] && provider !== "google" && !_spNeedsToken(provider) ? provider : null;
  if(want === _spCov && (want === null || map.getSource(_SP_SRC))) return;
  for(const id of _SP_LAYERS) if(map.getLayer(id)) map.removeLayer(id);
  for(const id of [_SP_SRC, _SP_OUT, _SP_SEL]) if(map.getSource(id)) map.removeSource(id);
  _spCov = want; _spWarned = false; if(!want) return;
  const color = SV_PROVIDERS[want].color, pan = want === "panoramax";
  map.addSource(_SP_SRC, pan ?
    {type: "vector", tiles: [_SP_PANORAMAX + "/api/map/{z}/{x}/{y}.mvt"], minzoom: 0, maxzoom: 15, attribution: SV_PROVIDERS[want].credit} :
    {type: "vector", tiles: ["https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=" + encodeURIComponent(_spToken())],
     minzoom: 6, maxzoom: 14, attribution: SV_PROVIDERS[want].credit});
  map.addSource(_SP_OUT, {type: "geojson", data: {type: "FeatureCollection", features: []}});
  // an invisible layer keeps the tiles loading; what shows is the cut copy
  map.addLayer({id: _SP_LAYERS[0], type: "line", source: _SP_SRC, "source-layer": pan ? "sequences" : "sequence", paint: {"line-opacity": 0}});
  map.addLayer({id: _SP_LAYERS[1], type: "line", source: _SP_OUT, filter: ["==", ["geometry-type"], "LineString"],
    layout: {"line-cap": "round", "line-join": "round"},
    paint: {"line-color": color, "line-opacity": .85, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 1, 14, 2.5, 18, 4]}});
  map.addLayer({id: _SP_LAYERS[2], type: "circle", source: _SP_OUT, filter: ["==", ["geometry-type"], "Point"],
    paint: {"circle-color": color, "circle-radius": ["interpolate", ["linear"], ["zoom"], 15, 2.5, 19, 5],
            "circle-stroke-color": "#fff", "circle-stroke-width": 1}});
  map.addSource(_SP_SEL, {type: "geojson", data: {type: "FeatureCollection", features: []}});
  map.addLayer({id: _SP_LAYERS[3], type: "circle", source: _SP_SEL,
    paint: {"circle-color": color, "circle-opacity": .15, "circle-radius": 13, "circle-stroke-color": color, "circle-stroke-width": 3}});
  _spMark(_spPicked);
  _spLater();
}
// ring around the photo that is open from a dot (null: no ring)
export function _spMark(c){
  _spPicked = c;
  const src = map && map.getSource(_SP_SEL);
  if(src) src.setData({type: "FeatureCollection", features: c ? [{type: "Feature", properties: {}, geometry: {type: "Point", coordinates: c}}] : []});
}
let _spOnError = null;

// A click on a photo's dot (while the coverage shows): the photo's own record is asked for and handed to the Street View window.
// _spOnDot(fn) sets who is told, fn(photo) with the shape _spFind answers, its azimuth the way the photo looks. _spDotClick(e) is for the map's
// click handler and tells whether the click was on a dot, so that it does not select the road under it.
let _spDotFn = null;
export const _spOnDot = fn => { _spDotFn = fn; };
export function _spDotClick(e){
  if(!_spCov || !_spDotFn || !map.getLayer(_SP_LAYERS[2])) return false;
  const r = 7, hit = map.queryRenderedFeatures([[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]], {layers: [_SP_LAYERS[2]]});
  if(!hit.length) return false;
  const d = f => (f.geometry.coordinates[0] - e.lngLat.lng) ** 2 + (f.geometry.coordinates[1] - e.lngLat.lat) ** 2;
  hit.sort((a, b) => d(a) - d(b));
  const f = hit[0], q = f.properties, [lng, lat] = f.geometry.coordinates, provider = _spCov;
  _spMark([lng, lat]);
  _spDotFn(provider, (async () => {
    if(provider === "mapillary") return {id: q.id, lng, lat, sx: lng, sy: lat, azimuth: q.is_pano ? 0 : +q.compass_angle || 0};
    const seq = q.first_sequence || (JSON.parse(q.sequences || "[]")[0]);
    const r = await fetch(_SP_PANORAMAX + "/api/collections/" + seq + "/items/" + q.id);
    if(!r.ok) throw new Error("Panoramax answered " + r.status);
    const ph = _spPanPhoto(await r.json());
    if(!ph) throw new Error("this photo has no image");
    return {id: ph.id, lng: ph.lng, lat: ph.lat, sx: ph.lng, sy: ph.lat, by: ph.by, azimuth: ph.az, fov: ph.fov, url: _spPan.blobs.get(ph.url) || ph.url};
  })());
  return true;
}

// ---- the viewers: one per provider, kept between spots (a reload per spot was slow) ----
const _SP_PSV = "https://cdn.jsdelivr.net/npm/@photo-sphere-viewer/core@5.15.1/", _SP_MLY = "https://cdn.jsdelivr.net/npm/mapillary-js@4.1.2/dist/mapillary.";
const _spCss = href => { if(!document.querySelector('link[href="' + href + '"]')){
  const l = document.createElement("link"); l.rel = "stylesheet"; l.href = href; document.head.appendChild(l); } };
let _spPsvLib = null, _spMlyLib = null;
const _spPsv = () => _spPsvLib || (_spCss(_SP_PSV + "index.min.css"),
  _spPsvLib = import(_SP_PSV + "+esm").catch(e => { _spPsvLib = null; throw e; }));
const _spMly = () => _spMlyLib || (_spMlyLib = new Promise((ok, no) => {
  if(window.mapillary) return ok(window.mapillary);
  _spCss(_SP_MLY + "css");
  const t = document.createElement("script"); t.src = _SP_MLY + "js";
  t.onload = () => ok(window.mapillary); t.onerror = () => { _spMlyLib = null; no(new Error("the Mapillary viewer could not be loaded")); };
  document.head.appendChild(t); }));
const _spDeg = a => ((a % 360) + 360) % 360;
// a flat photo is a window onto the sphere: put it in the middle, as wide as its field of view says
const _spPanoData = fov => img => {
  const W = img.width, H = img.height;
  if(W >= 1.9 * H) return {fullWidth: W, fullHeight: H, croppedWidth: W, croppedHeight: H, croppedX: 0, croppedY: 0};
  const fw = W * 360 / fov, fh = fw / 2;
  return {fullWidth: fw, fullHeight: fh, croppedWidth: W, croppedHeight: H, croppedX: (fw - W) / 2, croppedY: (fh - H) / 2};
};

// open a viewer for the provider inside box; seen(lng, lat, heading) is told where it stands and looks.
// Resolves {go(photo, heading), destroy()}; rejects when the library cannot be loaded.
export async function _spOpen(provider, box, seen){
  if(provider === "panoramax"){
    const lib = await _spPsv(); let v = null, az = 0, at = null, want = 0, info = {flat: false, w: 70, h: 52};
    const report = () => { if(v && at) seen(at.lng, at.lat, _spDeg(az + v.getPosition().yaw * 180 / Math.PI)); };
    // a flat photo covers only its field of view, and the rest of the sphere is black: look at its middle and stay inside it.
    // A panorama of 360 degrees turns freely and opens along the road.
    const settle = () => {
      if(!v) return;
      const R = d => d + "deg";
      v.setOptions(info.flat ? {yawRange: [R(-info.w / 2), R(info.w / 2)], pitchRange: [R(-info.h / 2), R(info.h / 2)],
                                  minFov: 20, maxFov: Math.max(25, Math.min(90, info.h))} : {yawRange: null, pitchRange: null, minFov: 30, maxFov: 90});
      v.zoom(0);
      v.rotate({yaw: (info.flat ? 0 : want) * Math.PI / 180, pitch: 0}); report();
    };
    const dataFor = fov => img => {
      info = {flat: img.width < 1.9 * img.height, w: fov, h: fov * img.height / img.width};
      return _spPanoData(fov)(img); };
    return {
      go(r, heading){
        at = {lng: r.sx, lat: r.sy}; az = r.azimuth;
        want = (_spDeg(heading == null ? az : heading) - az + 540) % 360 - 180;
        const pd = dataFor(r.fov);
        if(!v){
          v = new lib.Viewer({container: box, navbar: false, panorama: r.url, panoData: pd, defaultYaw: 0,
                              touchmoveTwoFingers: false, mousewheelCtrlKey: false});
          v.addEventListener("position-updated", report);
          v.addEventListener("ready", settle, {once: true});
        } else v.setPanorama(r.url, {panoData: pd, position: {yaw: 0, pitch: 0}, transition: false}).then(settle, () => {});
        return Promise.resolve();
      },
      destroy(){ if(v){ try{ v.destroy(); }catch(e){} v = null; } box.textContent = ""; }
    };
  }
  const lib = await _spMly(); let v = null, ro = null, lngLat = null, bearing = 0;
  const report = () => { if(lngLat) seen(lngLat.lng, lngLat.lat, bearing); };
  return {
    go(r){
      if(!v){
        v = new lib.Viewer({accessToken: _spToken(), container: box, imageId: r.id, component: {cover: false}});
        v.on("image", e => { lngLat = e.image.lngLat; report(); });
        v.on("bearing", e => { bearing = e.bearing; report(); });
        ro = new ResizeObserver(() => { if(v) v.resize(); }); ro.observe(box);
        return Promise.resolve();
      }
      return v.moveTo(r.id).catch(() => {});
    },
    destroy(){ if(ro) ro.disconnect(); if(v){ try{ v.remove(); }catch(e){} v = null; } box.textContent = ""; }
  };
}

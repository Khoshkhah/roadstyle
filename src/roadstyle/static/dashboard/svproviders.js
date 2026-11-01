// STREET PHOTOS BESIDE GOOGLE: Panoramax (open data, no key) and Mapillary (free, needs a client token
// that the person saves in Settings > Keys). For a spot on a road each finds the nearest photo within
// _SP_RADIUS metres, and a viewer (Photo Sphere Viewer for Panoramax, MapillaryJS for Mapillary, loaded from
// a CDN when first needed) shows it inside the Street View window (streetview.js) and reports where it looks, so
// the map marker turns with it. Each can also draw where it has photos (its coverage) on the map as vector tiles.
import {map, O} from "./core.js";
import {savedKey} from "./settings.js";

export const _SP_RADIUS = 50;
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

// the nearest photo to a spot: {id, lat, lng, ...what its viewer needs} | null (none within the radius);
// rejects when the service cannot be asked (offline, a wrong token)
export async function _spFind(provider, lat, lng, heading){
  if(provider === "panoramax"){
    const r = await fetch(_SP_PANORAMAX + "/api/search?limit=30&place_position=" + lng.toFixed(6) + "," + lat.toFixed(6) +
                          "&place_distance=0-" + _SP_RADIUS);
    if(!r.ok) throw new Error("Panoramax answered " + r.status);
    // the service does not sort by distance: take the photo that is near the spot and looks along the road (its azimuth near the road's heading)
    const turn = (a, b) => { const d = Math.abs(_spDeg(a - b)); return d > 180 ? 360 - d : d; };
    let best = null, bs = Infinity;
    for(const f of (await r.json()).features || []){
      const sd = f.assets && (f.assets.sd || f.assets.hd); if(!sd) continue;
      const [x, y] = f.geometry.coordinates, az = (f.properties && f.properties["view:azimuth"]) || 0;
      const sc = _spDist(lat, lng, y, x) + (heading == null ? 0 : turn(az, heading) * .5);
      if(sc < bs){ bs = sc; best = {f, x, y, az, sd}; } }
    if(!best) return null;
    const io = (best.f.properties && best.f.properties["pers:interior_orientation"]) || {};
    // sx, sy: the spot on the road, where the map marker stays (a photo's own position is a GPS fix, often beside the road)
    return {id: best.f.id, lng: best.x, lat: best.y, sx: lng, sy: lat, by: best.f.properties && best.f.properties["geovisio:producer"],
            url: best.sd.href, azimuth: best.az, fov: io.field_of_view || 70};
  }
  if(provider === "mapillary"){
    const dy = _SP_RADIUS / 111320, dx = dy / Math.max(.05, Math.cos(lat * Math.PI / 180));   // a box of the radius around the spot
    const bbox = [lng - dx, lat - dy, lng + dx, lat + dy].map(v => v.toFixed(6)).join(",");
    const r = await fetch("https://graph.mapillary.com/images?fields=id,geometry&limit=100&bbox=" + bbox + "&access_token=" + encodeURIComponent(_spToken()));
    if(!r.ok) throw new Error(r.status === 400 || r.status === 401 || r.status === 403 ? "Mapillary refused the token." : "Mapillary answered " + r.status);
    let best = null, bd = Infinity;
    for(const f of (await r.json()).data || []){
      const [x, y] = f.geometry.coordinates, d = _spDist(lat, lng, y, x);
      if(d < bd){ bd = d; best = {id: f.id, lng: x, lat: y}; } }
    if(!best) return null;
    return best;
  }
  return null;
}

// ---- coverage: where a provider has photos, drawn as lines (sequences) and dots (single photos) ----
// Only inside the page's area (the bounds of its roads): the tiles are read back (querySourceFeatures) and their lines cut at the area's edge.
const _SP_SRC = "rs-sv-cov", _SP_OUT = "rs-sv-cov-out", _SP_LAYERS = ["rs-sv-cov-load", "rs-sv-cov-lines", "rs-sv-cov-dots"];
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
function _spSync(){
  _spTimer = 0;
  const box = _spBox(), out = map.getSource(_SP_OUT);
  if(!_spCov || !box || !out || !map.getSource(_SP_SRC)) return;
  const pan = _spCov === "panoramax", feats = [], seen = new Set();
  for(const f of map.querySourceFeatures(_SP_SRC, {sourceLayer: pan ? "sequences" : "sequence"})){
    const g = f.geometry, lines = g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : [];
    for(const l of lines) for(const c of _spCut(l, box)){ const k = c.join(); if(!seen.has(k)){ seen.add(k); feats.push({type: "Feature", properties: {}, geometry: {type: "LineString", coordinates: c}}); } } }
  for(const f of map.querySourceFeatures(_SP_SRC, {sourceLayer: pan ? "pictures" : "image"})){
    const c = f.geometry.type === "Point" ? f.geometry.coordinates : null;
    if(c && c[0] >= box[0] && c[0] <= box[2] && c[1] >= box[1] && c[1] <= box[3]){ const k = "p" + c.join(); if(!seen.has(k)){ seen.add(k); feats.push({type: "Feature", properties: {}, geometry: {type: "Point", coordinates: c}}); } } }
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
  for(const id of [_SP_SRC, _SP_OUT]) if(map.getSource(id)) map.removeSource(id);
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
  _spLater();
}
let _spOnError = null;

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

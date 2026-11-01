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
    const r = await fetch(_SP_PANORAMAX + "/api/search?limit=1&place_position=" + lng.toFixed(6) + "," + lat.toFixed(6) +
                          "&place_distance=0-" + _SP_RADIUS);
    if(!r.ok) throw new Error("Panoramax answered " + r.status);
    const f = ((await r.json()).features || [])[0]; if(!f) return null;
    const [x, y] = f.geometry.coordinates, az = f.properties && f.properties["view:azimuth"];
    const io = (f.properties && f.properties["pers:interior_orientation"]) || {}, sd = f.assets && (f.assets.sd || f.assets.hd);
    if(!sd) return null;
    return {id: f.id, lng: x, lat: y, by: f.properties && f.properties["geovisio:producer"],
            url: sd.href, azimuth: az || 0, fov: io.field_of_view || 70};
  }
  if(provider === "mapillary"){
    const r = await fetch("https://graph.mapillary.com/images?fields=id,geometry&limit=20&radius=" + _SP_RADIUS +
                          "&closeto=" + lng.toFixed(6) + "," + lat.toFixed(6) + "&access_token=" + encodeURIComponent(_spToken()));
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
const _SP_SRC = "rs-sv-cov", _SP_LAYERS = ["rs-sv-cov-lines", "rs-sv-cov-dots"];
let _spCov = null, _spHooked = false;
export function _spCoverage(provider){            // a provider's name draws its coverage; anything else (or null) takes it away
  if(!map) return;
  if(!_spHooked){ _spHooked = true;               // a new base map style drops the layers: draw them again
    map.on("style.load", () => { const p = _spCov; _spCov = null; _spCoverage(p); }); }
  const want = SV_PROVIDERS[provider] && provider !== "google" && !_spNeedsToken(provider) ? provider : null;
  if(want === _spCov && (want === null || map.getSource(_SP_SRC))) return;
  for(const id of _SP_LAYERS) if(map.getLayer(id)) map.removeLayer(id);
  if(map.getSource(_SP_SRC)) map.removeSource(_SP_SRC);
  _spCov = want; if(!want) return;
  const color = SV_PROVIDERS[want].color, pan = want === "panoramax";
  map.addSource(_SP_SRC, pan ?
    {type: "vector", tiles: [_SP_PANORAMAX + "/api/map/{z}/{x}/{y}.mvt"], minzoom: 0, maxzoom: 15, attribution: SV_PROVIDERS[want].credit} :
    {type: "vector", tiles: ["https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=" + encodeURIComponent(_spToken())],
     minzoom: 6, maxzoom: 14, attribution: SV_PROVIDERS[want].credit});
  const L = pan ? "sequences" : "sequence", D = pan ? "pictures" : "image";
  map.addLayer({id: _SP_LAYERS[0], type: "line", source: _SP_SRC, "source-layer": L,
    layout: {"line-cap": "round", "line-join": "round"},
    paint: {"line-color": color, "line-opacity": .75, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 1, 14, 2.5, 18, 4]}});
  map.addLayer({id: _SP_LAYERS[1], type: "circle", source: _SP_SRC, "source-layer": D, minzoom: 15,
    paint: {"circle-color": color, "circle-radius": ["interpolate", ["linear"], ["zoom"], 15, 2.5, 19, 5],
            "circle-stroke-color": "#fff", "circle-stroke-width": 1}});
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
    const lib = await _spPsv(); let v = null, az = 0, at = null;
    const report = () => { if(v && at) seen(at.lng, at.lat, _spDeg(az + v.getPosition().yaw * 180 / Math.PI)); };
    return {
      go(r, heading){
        at = r; az = r.azimuth;
        const yaw = (_spDeg(heading == null ? az : heading) - az + 540) % 360 - 180;
        const opt = {panoData: _spPanoData(r.fov), position: {yaw: yaw * Math.PI / 180, pitch: 0}, transition: false};
        if(!v){
          v = new lib.Viewer({container: box, navbar: false, panorama: r.url, panoData: opt.panoData,
                              defaultYaw: opt.position.yaw, touchmoveTwoFingers: false, mousewheelCtrlKey: false});
          v.addEventListener("position-updated", report);
          v.addEventListener("ready", report, {once: true});
        } else v.setPanorama(r.url, opt).then(report, () => {});
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

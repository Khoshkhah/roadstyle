// STREET PHOTOS BESIDE GOOGLE: Panoramax (open data, no key) and Mapillary (free, needs a client token
// that the person saves in Settings > Keys). For a spot on a road each finds the nearest photo within
// _SP_RADIUS metres and gives the address of its embeddable viewer, which the Street View window frames
// (streetview.js). Each can also draw where it has photos (its coverage) on the map as vector tiles.
import {map, O} from "./core.js";
import {savedKey} from "./settings.js";

export const _SP_RADIUS = 50;
const _SP_PANORAMAX = "https://api.panoramax.xyz", _SP_VIEWER = "https://panoramax.openstreetmap.fr/";
export const SV_PROVIDERS = {
  google:    {title: "Google"},
  panoramax: {title: "Panoramax", credit: "Panoramax contributors (CC-BY-SA)", href: "https://panoramax.fr/", color: "#e8590c"},
  mapillary: {title: "Mapillary", credit: "Mapillary contributors (CC-BY-SA)", href: "https://www.mapillary.com/", color: "#05a350"},
};
export const _spToken = () => savedKey("mapillary") || O.mapillary_token || "";
export const _spNeedsToken = p => p === "mapillary" && !_spToken();
const _spDist = (a, b, c, d) => { const k = Math.cos(a * Math.PI / 180);
  return Math.hypot((c - a) * 110540, (d - b) * 110540 * k); };       // metres, short distances

// the nearest photo to a spot: {id, lat, lng, src (the viewer's address), by} | null (none within the radius);
// rejects when the service cannot be asked (offline, a wrong token)
export async function _spFind(provider, lat, lng, heading){
  if(provider === "panoramax"){
    const r = await fetch(_SP_PANORAMAX + "/api/search?limit=1&place_position=" + lng.toFixed(6) + "," + lat.toFixed(6) +
                          "&place_distance=0-" + _SP_RADIUS);
    if(!r.ok) throw new Error("Panoramax answered " + r.status);
    const f = ((await r.json()).features || [])[0]; if(!f) return null;
    const [x, y] = f.geometry.coordinates, az = f.properties && f.properties["view:azimuth"];
    return {id: f.id, lng: x, lat: y, by: f.properties && f.properties["geovisio:producer"],
            src: _SP_VIEWER + "?focus=pic&pic=" + encodeURIComponent(f.id) +
                 (az == null ? "" : "&xyz=" + Math.round(((heading == null ? az : heading) % 360 + 360) % 360) + "/0/60")};
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
    best.src = "https://www.mapillary.com/embed?style=photo&image_key=" + encodeURIComponent(best.id);
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

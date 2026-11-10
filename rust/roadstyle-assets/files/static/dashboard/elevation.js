// Elevation on the map: the HILLSHADE under the roads and the 3D TERRAIN, both drawn from the page's one DEM; the Google 3D window reads its ground
// heights from the same tiles (google3d.js, through _elDemTile). THE DEM: with the page option `ground` (docs/design/ground_terrain.md), the area's
// terrain file (Terrarium PNG tiles in one PMTiles archive, made from the area's ground by the engine), read through the protocol `rsground`; a host
// gives it later with rsGround(ground). Without it, `O.ontop.dem` (data/basemaps.json: the AWS Terrain Tiles, Terrarium PNGs, no key).
// The file's zooms and box are in its header, so its source is known only after a first read: a hillshade or a terrain asked for before it
// is drawn when the header comes (_elApply). Their switches are rows of the base-map
// box (basemapbox.js); the keywords `hillshade=True` and `terrain=True` start them on.
// MapLibre draws a terrain from one raster-dem source and a hillshade from another, with the same tiles (one source for both would give a hillshade
// that follows the terrain's zoom), so there are two sources and the browser loads each tile once.
// THE LIMIT of the terrain: every layer lies on the ground of the DEM, and MapLibre has no height of its own for a line (so a per-edge height, a
// `z` column, cannot be drawn). A tunnel is drawn on the hill above it and a bridge on the valley under it. The roads are flat with the terrain off.
// `terrain_tunnels=` says what a tunnel does meanwhile: "show", "fade" (the default: drawn at `ontop.terrain.tunnel_fade`) or "hide". The style's tunnel
// pieces read the state `rs_terrain_tunnel` (1, the fade, or 0): this file only sets it.
import {map, O, _emit} from "./core.js";

const _elHill = "rs-top-hillshade", _elTerrain = "rs-dem";
const _elModes = ["show", "fade", "hide"];
let _elOn = false, _elTilted = false, _elMode = null;
// the DEM's source once known (null while the ground's header is read), the ground's archive (null: the AWS tiles), the hillshade asked for meanwhile,
// and the count of grounds (in the tile URLs: a new ground is new tiles)
let _elSpec = null, _elArchive = null, _elHillWant = null, _elGen = 0, _elReady = Promise.resolve(), _elProto = false;
// the attribution of a ground: its source, its product and datum ("datum unknown" where duckOSM has no value), its id and license when known
function _elAttr(g){
  const known = v => v != null && v !== "" && v !== "unknown";
  if(g.product === "DSM") return "Ground: surface model (" + (known(g.source) ? g.source : "source unknown") + ")";
  return "Ground: " + (known(g.source) ? g.source : "source unknown") + " (" + (known(g.product) ? g.product : "product unknown") + ", " +
    (known(g.vertical_datum) ? g.vertical_datum : "datum unknown") + ")" + (known(g.id) ? ", id " + String(g.id).slice(0, 8) : "") +
    (known(g.license) ? ", " + g.license : "");
}
// a PMTiles source of bytes in memory or of a File or Blob (an OPFS file: each read is one slice of the file on disk)
const _elBytes = (buf) => ({getKey: () => "ground", getBytes: (o, l) => buf.then(b => ({data: b.slice(o, o + l)}))});
const _elBlob = (f) => ({getKey: () => "ground", getBytes: (o, l) => f.slice(o, o + l).arrayBuffer().then(data => ({data}))});
function _elLoad(){
  const g = O.ground, gen = ++_elGen;
  if(!g || !g.terrain){
    const d = O.ontop.dem; _elArchive = null;
    _elSpec = {type: "raster-dem", tiles: d.tiles, encoding: d.encoding, tileSize: d.tile_size, maxzoom: d.maxzoom, attribution: d.attr};
    _elReady = Promise.resolve(); return;
  }
  const P = window.pmtiles, t = g.terrain;
  if(!P) throw new Error("rs ground: the page has no pmtiles.js, so it cannot read the terrain file");
  if(!_elProto){                                           // one protocol for the page: it reads the archive of the ground now
    _elProto = true;
    window.maplibregl.addProtocol("rsground", async (params, abort) => {
      const m = /^rsground:\/\/\d+\/(\d+)\/(\d+)\/(\d+)/.exec(params.url), r = m && _elArchive && await _elArchive.getZxy(+m[1], +m[2], +m[3], abort.signal);
      if(!r) throw new Error("rs ground: no tile " + params.url);
      return {data: r.data};
    });
  }
  const src = typeof t !== "string" ? (t instanceof Blob ? _elBlob(t) : _elBytes(Promise.resolve(t instanceof ArrayBuffer ? t : t.buffer.slice(t.byteOffset, t.byteOffset + t.byteLength))))
            : t.startsWith("data:") ? _elBytes(fetch(t).then(r => r.arrayBuffer())) : t;
  const a = _elArchive = new P.PMTiles(src);
  _elSpec = null;
  _elReady = a.getHeader().then(h => {
    if(gen !== _elGen) return;
    _elSpec = {type: "raster-dem", tiles: ["rsground://" + gen + "/{z}/{x}/{y}"], encoding: "terrarium", tileSize: 256, minzoom: h.minZoom, maxzoom: h.maxZoom,
               bounds: [h.minLon, h.minLat, h.maxLon, h.maxLat], attribution: _elAttr(g)};
    _elApply();
  }, e => console.warn("rs ground: the terrain file did not load", e));
}
// what was asked for while the ground's header was read
function _elApply(){
  if(!_elSpec) return;
  if(_elHillWant){ const w = _elHillWant; _elHillWant = null; _elHillshade(w.on, w.before); }
  if(_elOn && !map.getTerrain()){ _elTerrainOn(); _elTunnels(); _emit("rs:terrainchange", {on: true}); }
}
function _elTerrainOn(){
  if(!map.getSource(_elTerrain)) map.addSource(_elTerrain, {..._elSpec});
  map.setTerrain({source: _elTerrain, exaggeration: O.terrain_exaggeration ?? O.ontop.terrain.exaggeration});       // the keyword, else the config's
}
// the hillshade layer goes under `before` (the first road layer, basemapbox.js); no layer and no source when it is off
export function _elHillshade(on, before){
  if(!_elSpec && !_elArchive) _elLoad();
  if(!on){ _elHillWant = null; if(map.getLayer(_elHill)) map.removeLayer(_elHill); if(map.getSource(_elHill)) map.removeSource(_elHill); return; }
  if(map.getLayer(_elHill)) return;
  if(!_elSpec){ _elHillWant = {on, before}; return; }
  const h = O.ontop.hillshade;
  map.addSource(_elHill, {..._elSpec});
  map.addLayer({id: _elHill, type: "hillshade", source: _elHill,
                paint: {"hillshade-exaggeration": h.exaggeration, "hillshade-shadow-color": h.shadow, "hillshade-highlight-color": h.highlight, "hillshade-accent-color": h.accent}}, before);
}
// rsTerrain(on): the 3D terrain on or off, no argument: whether it is on. The camera stays where it is (a flat camera shows the hillshade of the ground only).
// With the ground's file, the terrain comes when its header is read: rs:terrainchange says when
export function rsTerrain(on){
  if(on === undefined) return _elOn;
  if(!_elSpec && !_elArchive) _elLoad();
  on = !!on;
  if(on === _elOn && (!on || map.getTerrain() || !_elSpec)) return _elOn;
  _elOn = on;
  if(on){
    if(!_elSpec) return _elOn;
    _elTerrainOn();
  } else {
    map.setTerrain(null);
    if(map.getSource(_elTerrain)) map.removeSource(_elTerrain);
  }
  _elTunnels();
  _emit("rs:terrainchange", {on});
  return _elOn;
}
// rsGround(ground): the area's ground from now on, no argument: the ground now. `ground`: {id, source, product, vertical_datum, resolution_m, license,
// terrain}, `terrain` the terrain file: a URL, a File or Blob (an OPFS file), an ArrayBuffer or a Uint8Array; null: the AWS tiles. The hillshade and
// the terrain that are on stay on, drawn from the new ground.
export function rsGround(ground){
  if(ground === undefined) return O.ground || null;
  const ls = map.getStyle().layers, i = ls.findIndex(l => l.id === _elHill);
  const hill = i >= 0 ? {on: true, before: ls[i + 1] && ls[i + 1].id} : _elHillWant, terrain = _elOn;
  _elHillshade(false);
  if(terrain){ map.setTerrain(null); if(map.getSource(_elTerrain)) map.removeSource(_elTerrain); }
  O.ground = ground || null;
  _elLoad();
  if(hill) _elHillshade(true, hill.before);
  if(terrain && _elSpec){ _elTerrainOn(); _elTunnels(); }
  _emit("rs:groundchange", {ground: O.ground});
  return O.ground;
}
// _elDemMaxZoom(): the last zoom of the page's one DEM (the ground's file, else ontop.dem): the zoom that the map draws its terrain from
export const _elDemMaxZoom = () => _elSpec ? _elSpec.maxzoom : O.ontop.dem.maxzoom;
// _elDemZoom(): the zoom of the DEM tiles that a reader of single heights takes (google3d.js): 14, or the DEM's last zoom
export const _elDemZoom = () => Math.min(14, _elDemMaxZoom());
// _elDemTile(z, x, y) -> Promise of the tile's RGBA pixels (256 x 256), from the page's one DEM, decoded as the map decodes them (no colour space
// conversion). The Terrarium height of pixel i: R*256 + G + B/256 - 32768, at the pixel's north-west corner
export async function _elDemTile(z, x, y){
  if(!_elSpec && !_elArchive) _elLoad();
  await _elReady;
  let blob;
  if(_elArchive){
    const r = await _elArchive.getZxy(z, x, y);
    if(!r) throw new Error("rs ground: no tile " + z + "/" + x + "/" + y);
    blob = new Blob([r.data], {type: "image/png"});
  } else {
    const url = _elSpec.tiles[0].replace("{z}", z).replace("{x}", x).replace("{y}", y), res = await fetch(url);
    if(!res.ok) throw new Error("HTTP " + res.status + " " + url);
    blob = await res.blob();
  }
  const img = await createImageBitmap(blob, {colorSpaceConversion: "none"});
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d", {willReadFrequently: true}); g.drawImage(img, 0, 0);
  return g.getImageData(0, 0, 256, 256).data;
}
// the state of the tunnels' pieces: 1 with the terrain off or "show", the fade, or 0 for "hide". Again after rs.setStyle (the state starts at 1 with a new style)
export function _elTunnels(){
  const mode = _elMode || O.terrain_tunnels, f = {show: 1, fade: O.ontop.terrain.tunnel_fade, hide: 0};
  map.setGlobalStateProperty("rs_terrain_tunnel", _elOn ? f[mode] : 1);
}
// rsTerrainTunnels(mode): "show", "fade" or "hide"; no argument: the mode now
export function rsTerrainTunnels(mode){
  if(mode === undefined) return _elMode || O.terrain_tunnels;
  if(!_elModes.includes(mode)) throw new Error("rsTerrainTunnels: mode must be " + _elModes.join(", ") + ", got " + JSON.stringify(mode));
  _elMode = mode; _elTunnels();
  return mode;
}
// A person's switch of the terrain (the box's row): on, the map is tilted if it is flat, so that the switch shows something; off, it is flattened again
// if this switch tilted it. A script calls rsTerrain(on), which moves nothing.
export function _elTerrainByPerson(on){
  rsTerrain(on);
  if(on && map.getPitch() < 5){ _elTilted = true; map.easeTo({pitch: O.ontop.terrain.pitch, duration: 600}); }
  else if(!on && _elTilted){ _elTilted = false; map.easeTo({pitch: 0, duration: 400}); }
}

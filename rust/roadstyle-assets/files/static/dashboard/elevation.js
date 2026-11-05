// Elevation on the map: the HILLSHADE under the roads and the 3D TERRAIN, both drawn from the DEM of `O.ontop.dem` (data/basemaps.json: Terrain Tiles on
// AWS, Terrarium PNGs, no key; the Google 3D window reads its ground heights from the same tiles, google3d.js). Their switches are rows of the base-map
// box (basemapbox.js); the keywords `hillshade=True` and `terrain=True` start them on.
// MapLibre draws a terrain from one raster-dem source and a hillshade from another, with the same tiles (one source for both would give a hillshade
// that follows the terrain's zoom), so there are two sources and the browser loads each tile once.
// THE LIMIT of the terrain: every layer lies on the ground of the DEM, and MapLibre has no height of its own for a line. A tunnel is drawn on the
// hill above it and a bridge on the valley under it. The roads are flat with the terrain off.
import {map, O, _emit} from "./core.js";

const _elHill = "rs-top-hillshade", _elTerrain = "rs-dem";
let _elOn = false, _elTilted = false;
const _elSource = () => { const d = O.ontop.dem; return {type: "raster-dem", tiles: d.tiles, encoding: d.encoding, tileSize: d.tile_size, maxzoom: d.maxzoom, attribution: d.attr}; };
// the hillshade layer goes under `before` (the first road layer, basemapbox.js); no layer and no source when it is off
export function _elHillshade(on, before){
  if(!on){ if(map.getLayer(_elHill)) map.removeLayer(_elHill); if(map.getSource(_elHill)) map.removeSource(_elHill); return; }
  if(map.getLayer(_elHill)) return;
  const h = O.ontop.hillshade;
  map.addSource(_elHill, _elSource());
  map.addLayer({id: _elHill, type: "hillshade", source: _elHill,
                paint: {"hillshade-exaggeration": h.exaggeration, "hillshade-shadow-color": h.shadow, "hillshade-highlight-color": h.highlight, "hillshade-accent-color": h.accent}}, before);
}
// rsTerrain(on): the 3D terrain on or off, no argument: whether it is on. The camera stays where it is (a flat camera shows the hillshade of the ground only)
export function rsTerrain(on){
  if(on === undefined) return _elOn;
  on = !!on;
  if(on === _elOn && (!on || map.getTerrain())) return _elOn;
  _elOn = on;
  if(on){
    if(!map.getSource(_elTerrain)) map.addSource(_elTerrain, _elSource());
    map.setTerrain({source: _elTerrain, exaggeration: O.terrain_exaggeration ?? O.ontop.terrain.exaggeration});       // the keyword, else the config's
  } else {
    map.setTerrain(null);
    if(map.getSource(_elTerrain)) map.removeSource(_elTerrain);
  }
  _emit("rs:terrainchange", {on});
  return _elOn;
}
// A person's switch of the terrain (the box's row): on, the map is tilted if it is flat, so that the switch shows something; off, it is flattened again
// if this switch tilted it. A script calls rsTerrain(on), which moves nothing.
export function _elTerrainByPerson(on){
  rsTerrain(on);
  if(on && map.getPitch() < 5){ _elTilted = true; map.easeTo({pitch: O.ontop.terrain.pitch, duration: 600}); }
  else if(!on && _elTilted){ _elTilted = false; map.easeTo({pitch: 0, duration: 400}); }
}

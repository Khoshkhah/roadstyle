// the tiles' generation against the style's (docs/reference/contract.md, roadstyle:generation). A road's row is valid in one generation
// only, so tiles of another road set would be coloured, filtered and picked as other roads. Then the dashboard says so, once, on the map,
// and hides the layers of the style's vector sources. The tiles' generation is the host's (the option tiles_generation, the document
// event rs:tiles-generation: the PMTiles metadata or the answer of a tile server), else the ?g= of the style's tile URLs.
let _map, _P = "", _style = null, _tiles = null, _hidden = [];
const _urlGeneration = st => {
  for(const s of Object.values((st && st.sources) || {}))
    for(const u of [...(s.tiles || []), s.url || ""]){ const m = /[?&]g=([0-9a-f]+)/.exec(u); if(m) return m[1]; }
  return null;
};
// the error of a style that has another generation than its tiles, else null (the generation of either is not known: no error)
export function _generationError(st, tiles){
  const g = ((st && st.metadata) || {})["roadstyle:generation"], t = tiles || _urlGeneration(st);
  return g && t && g !== t ? "roadstyle: the tiles are of road set " + t + ", and the style is of road set " + g +
    ". The dashboard draws no roads for this style: load the style and the tiles of one build." : null;
}
function _checkGeneration(){
  const error = _generationError(_style, _tiles);
  document.getElementById("rs-stale")?.remove();
  _hidden.splice(0).forEach(id => _map.getLayer(id) && _map.setLayoutProperty(id, "visibility", "visible"));
  if(!error) return null;
  const box = document.createElement("div");
  box.id = "rs-stale"; box.textContent = error;
  box.style.cssText = "position:fixed;z-index:9999;top:0;left:0;right:0;padding:8px 12px;background:#b91c1c;color:#fff;font:13px sans-serif";
  document.body.prepend(box);
  const vector = new Set(Object.keys(_style.sources || {}).filter(k => _style.sources[k].type === "vector"));
  const hide = () => _style.layers.filter(l => vector.has(l.source)).map(l => _P + l.id)
    .filter(id => _map.getLayer(id) && _map.getLayoutProperty(id, "visibility") !== "none")
    .forEach(id => { _map.setLayoutProperty(id, "visibility", "none"); _hidden.push(id); });
  _map.isStyleLoaded() ? hide() : _map.once("load", hide);
  return error;
}
export function initGeneration(map, o){
  _map = map; _P = o.prefix || "";
  _tiles = o.tiles_generation || (window.__rs_tiles && window.__rs_tiles.generation) || null;
  document.addEventListener("rs:tiles-generation", e => { _tiles = e.detail || null; _checkGeneration(); });
}
// the check for the style that the dashboard uses now (at the start, and by setStyle): its error text, or null
export function useGeneration(st){
  _style = st;
  return _checkGeneration();
}

// The roads of a page on its map, and the swap of their style (docs/design/level_part.md, step d). A road style from roadstyle's engine has sources, layers,
// images (`metadata["roadstyle:images"]`) and the start values of a live style's state. Every page that draws roads needs the same steps to put a new
// style on its map: take the old roads off, add the images with the page's prefix, add the sources and the layers with it, and tell the dashboard
// (`dashboard.setStyle`). roadstyle's design editor page, its level editor and duckOSM Studio each had its own copy of this code.
//
//   const roads = roadLayers({map, dashboard: rs, prefix: "rs-", before: "area-fill", also: ["rs-low-"]});
//   await roads.show(style, {after: (st) => addOverview(st)});    // the style on the map (the old roads go first)
//   roads.remove();                                               // the roads off the map
//   await roads.reloadTiles();                                    // the tiles of the vector sources again, when the answer of a relevel has no style
//   roads.layers, roads.sources, roads.images                     // what it put on the map (ids with the prefix)
//
// `prefix`: the start of the ids of the layers, the sources and the images of the roads. `before`: the id of a layer that the road layers go under (null:
// on top). `also`: more id prefixes that `remove` takes off (a page's own copies of the road layers, such as duckOSM Studio's "rs-low-").
const _rlIdle = (map, ms) => new Promise((ok) => { map.once("idle", ok); setTimeout(ok, ms); });

export function roadLayers({map, dashboard = globalThis.rs, prefix = "rs-", before = null, also = []}){
  const mine = {layers: [], sources: [], images: []};
  // an id of `also`: "rs-low-" is the layers "rs-low-fill" and the source "rs-low" (the prefix without its last dash)
  const inAlso = (id) => also.some(p => id.startsWith(p) || id === p.replace(/-$/, ""));
  const owns = (id) => id.startsWith(prefix) || inAlso(id);
  // an <img> reads an SVG icon too (map.loadImage does not)
  const image = (id, v) => new Promise((done) => {
    const im = typeof v === "string" ? {url: v} : v, img = new Image();
    img.onload = () => { if(map.hasImage(id)) map.removeImage(id); map.addImage(id, img, {sdf: !!im.sdf, pixelRatio: im.pixelRatio || 1}); mine.images.push(id); done(); };
    img.onerror = () => { console.warn(`roadLayers: the image ${id} could not be read`); done(); };
    img.src = im.url;
  });
  function remove(){
    const st = map.getStyle();
    if(!st) return;
    for(const l of st.layers) if(mine.layers.includes(l.id) || inAlso(l.id)) map.removeLayer(l.id);
    for(const id of Object.keys(st.sources)) if(mine.sources.includes(id) || inAlso(id)) map.removeSource(id);
    mine.layers = []; mine.sources = [];
  }
  async function show(style, {after = null} = {}){
    remove();
    const own = (style.metadata || {})["roadstyle:images"] || {};
    await Promise.all(Object.entries(own).map(([n, v]) => image(prefix + n, v)));
    // a live style's global state: its start values. A name that the map has keeps its value (the theme, what the person set)
    const have = map.getGlobalState ? map.getGlobalState() : {};
    for(const [k, v] of Object.entries(style.state || {})) if(!(k in have)) map.setGlobalStateProperty(k, v.default ?? null);
    for(const [id, src] of Object.entries(style.sources || {})) map.addSource(prefix + id, src);
    for(const l of style.layers || []){
      let json = JSON.stringify(l);
      for(const n of Object.keys(own)) json = json.replaceAll(`"${n}"`, `"${prefix}${n}"`);          // the image names in the layout
      const layer = JSON.parse(json);
      map.addLayer({...layer, id: prefix + l.id, ...(l.source ? {source: prefix + l.source} : {})}, before && map.getLayer(before) ? before : undefined);
    }
    mine.layers = (style.layers || []).map(l => prefix + l.id);
    mine.sources = Object.keys(style.sources || {}).map(id => prefix + id);
    if(after) await after(style);
    if(dashboard?.setStyle) dashboard.setStyle(style);      // the dashboard reads the new roads (its layers and metadata)
    return {layers: [...mine.layers], sources: [...mine.sources]};
  }
  // MapLibre 5 has no source.reload(): setTiles with the same URLs drops the tiles of the source and loads the visible ones again. `wait`: until the map is idle
  async function reloadTiles({wait = true, timeout = 30000} = {}){
    for(const [id, s] of Object.entries(map.getStyle().sources)) if(owns(id) && s.type === "vector") map.getSource(id).setTiles(s.tiles);
    if(wait) await _rlIdle(map, timeout);
  }
  return {show, remove, reloadTiles, get layers(){ return [...mine.layers]; }, get sources(){ return [...mine.sources]; }, get images(){ return [...mine.images]; }};
}

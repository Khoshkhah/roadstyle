// The map objects of a result that is not a road (docs/design/dock_kinds.md): a node, a building. The data dock gives their GeoJSON features; this module draws
// them in two sources of their own: `rs-dock-kinds` (the objects of the result, in the blue of the road light) and `rs-dock-kinds-sel` (the selected object:
// the select purple, with a ring for a point and a thicker outline for a line or an area). A change of the base map or of the theme can remove the layers:
// the module puts them back.
//
//   dockKinds(map) -> {draw(features), select(feature | null), fit(feature, bottom), recolour(), clear()}
const SRC = "rs-dock-kinds", SEL = "rs-dock-kinds-sel";
const BLUE = {light: "#2563eb", dark: "#5aa9f8"}, PURPLE = "#7c4dff";            // the same blue as the road light (data_dock.js), the select purple of roadstyle
const POINT = ["==", ["geometry-type"], "Point"], AREA = ["==", ["geometry-type"], "Polygon"], LINE = ["==", ["geometry-type"], "LineString"];

export function dockKinds(map){
  let feats = [], picked = null;
  const dark = () => document.documentElement.dataset.rsTheme === "dark";
  const blue = () => dark() ? BLUE.dark : BLUE.light, ring = () => dark() ? "#0e1113" : "#ffffff";
  const data = (f) => ({type: "FeatureCollection", features: f});
  function ensure(){
    if(!map.isStyleLoaded() || map.getSource(SRC)) return;
    map.addSource(SRC, {type: "geojson", data: data(feats)});
    map.addSource(SEL, {type: "geojson", data: data(picked ? [picked] : [])});
    // the result: an area (fill and outline), a line, a point (a dot with a ring of the map's colour)
    map.addLayer({id: SRC + "-fill", type: "fill", source: SRC, filter: AREA, paint: {"fill-color": blue(), "fill-opacity": 1}});
    map.addLayer({id: SRC + "-line", type: "line", source: SRC, filter: ["any", LINE, AREA], paint: {"line-color": blue(), "line-width": 2}});
    map.addLayer({id: SRC + "-dot", type: "circle", source: SRC, filter: POINT, paint: {"circle-radius": 5, "circle-color": blue(), "circle-stroke-width": 2, "circle-stroke-color": ring()}});
    // the selected object: over the result
    map.addLayer({id: SEL + "-fill", type: "fill", source: SEL, filter: AREA, paint: {"fill-color": PURPLE, "fill-opacity": 1}});
    map.addLayer({id: SEL + "-line", type: "line", source: SEL, filter: ["any", LINE, AREA], paint: {"line-color": PURPLE, "line-width": 4}});
    map.addLayer({id: SEL + "-ring", type: "circle", source: SEL, filter: POINT, paint: {"circle-radius": 12, "circle-color": PURPLE, "circle-opacity": 0.2, "circle-stroke-width": 2.5, "circle-stroke-color": PURPLE}});
    map.addLayer({id: SEL + "-dot", type: "circle", source: SEL, filter: POINT, paint: {"circle-radius": 6, "circle-color": PURPLE, "circle-stroke-width": 2, "circle-stroke-color": ring()}});
  }
  const put = () => { ensure(); map.getSource(SRC)?.setData(data(feats)); map.getSource(SEL)?.setData(data(picked ? [picked] : [])); };
  // a new style took the layers away, or the style was not ready when the objects came: put the layers back when the style is ready
  const back = () => { if((feats.length || picked) && !map.getSource(SRC)) put(); };
  map.on("styledata", back); map.on("idle", back);
  function recolour(){
    if(!map.getSource(SRC)) return;
    for(const l of ["fill", "line", "dot"]) map.setPaintProperty(`${SRC}-${l}`, l === "fill" ? "fill-color" : l === "line" ? "line-color" : "circle-color", blue());
    map.setPaintProperty(SRC + "-dot", "circle-stroke-color", ring()); map.setPaintProperty(SEL + "-dot", "circle-stroke-color", ring());
  }
  document.addEventListener("rs:themechange", recolour);
  // the bounds of a feature: a point gives a zoom of 18, an area or a line its box, clear of the dock at the bottom
  function fit(f, bottom = 0){
    const b = new window.maplibregl.LngLatBounds(), add = (c) => (typeof c[0] === "number" ? b.extend(c) : c.forEach(add));
    add(f.geometry.coordinates);
    if(f.geometry.type === "Point") map.easeTo({center: f.geometry.coordinates, zoom: Math.max(map.getZoom(), 18), duration: 500});
    else map.fitBounds(b, {padding: {top: 80, left: 60, right: 60, bottom: bottom + 60}, maxZoom: 19, duration: 500});
  }
  return {
    draw(f){ feats = f; put(); },
    select(f){ picked = f; put(); },
    fit, recolour,
    clear(){ feats = []; picked = null; put(); },
  };
}

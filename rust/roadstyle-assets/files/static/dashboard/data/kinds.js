// The map objects of a result that is not a road (docs/design/dock_kinds.md, dock_kinds_table_views.md): a node, a building, a cell, a turn. The data dock gives their
// GeoJSON features; this module draws them in two sources of their own: `rs-dock-kinds` (the objects of the result) and `rs-dock-kinds-sel` (the selected object: the
// select colour, with a ring for a point and a thicker outline for a line or an area). A change of the base map or of the theme can remove the layers: the module
// puts them back.
//
// The colours are the look's `dock` section (the palette; the page gives it as `window.RS_DOCK`): the result colour, the select colour, and one colour for each role of
// a part. A feature with `rs_role` is a part of an object (a turn is a `from` road, a `via` node and a `to` road): it has the colour of its role, and the selected object
// keeps these colours over a select-colour halo. A role that the palette does not name takes the next colour of `role_series`, in the order of first use.
//
//   dockKinds(map) -> {draw(features), select(feature | [feature] | null), fit(feature | [feature], bottom), colour(role), recolour(), clear()}
const SRC = "rs-dock-kinds", SEL = "rs-dock-kinds-sel";
const POINT = ["==", ["geometry-type"], "Point"], AREA = ["==", ["geometry-type"], "Polygon"], LINE = ["==", ["geometry-type"], "LineString"];
const ROLE = ["has", "rs_role"], PLAIN = ["!", ROLE];

// the colours of the dock's objects; a page without them is an error that the person can see, not a guess
function look(){
  const d = window.RS_DOCK;
  if(!d || !d.result || !d.selected) throw new Error("dataDock: the kinds need the colours of the look's dock section (window.RS_DOCK); the page's options must carry `dock`");
  return d;
}

export function dockKinds(map){
  let feats = [], picked = [], series = new Map();       // series: a role the palette does not name -> its colour pair
  const dark = () => document.documentElement.dataset.rsTheme === "dark";
  const pick = (pair) => dark() ? pair.dark : pair.light;
  const blue = () => pick(look().result), purple = () => look().selected, ring = () => dark() ? "#0e1113" : "#ffffff";
  const data = (f) => ({type: "FeatureCollection", features: f});
  // the colour of a role, else the colour of the plain result
  function colour(role){
    const d = look();
    if(role == null) return blue();
    if(d.roles && d.roles[role]) return pick(d.roles[role]);
    if(!series.has(role)) series.set(role, d.role_series[series.size % d.role_series.length]);
    return pick(series.get(role));
  }
  // the roles of some features in the order of their first use; the series follows this order
  function learn(list){
    series = new Map(); for(const f of list){ const r = f.properties.rs_role; if(r != null) colour(r); }
  }
  // the colour of a feature: its role's colour, else the plain colour (a match on rs_role)
  function paint(){
    const roles = [...new Set(feats.concat(picked).map((f) => f.properties.rs_role).filter((r) => r != null))];
    if(!roles.length) return blue();
    return ["match", ["get", "rs_role"], ...roles.flatMap((r) => [r, colour(r)]), blue()];
  }
  function ensure(){
    if(!map.isStyleLoaded() || map.getSource(SRC)) return;
    map.addSource(SRC, {type: "geojson", data: data(feats)});
    map.addSource(SEL, {type: "geojson", data: data(picked)});
    // the result: an area (fill and outline), a line, a point (a dot with a ring of the map's colour)
    map.addLayer({id: SRC + "-fill", type: "fill", source: SRC, filter: AREA, paint: {"fill-color": paint(), "fill-opacity": 1}});
    map.addLayer({id: SRC + "-line", type: "line", source: SRC, filter: ["any", LINE, AREA], paint: {"line-color": paint(), "line-width": 2}});
    map.addLayer({id: SRC + "-dot", type: "circle", source: SRC, filter: POINT, paint: {"circle-radius": 5, "circle-color": paint(), "circle-stroke-width": 2, "circle-stroke-color": ring()}});
    // the selected object, over the result. A plain object is all select colour. A part with a role keeps its colour over a halo of the select colour.
    map.addLayer({id: SEL + "-halo", type: "line", source: SEL, filter: ["all", ROLE, ["any", LINE, AREA]], paint: {"line-color": purple(), "line-width": 9}});
    map.addLayer({id: SEL + "-fill", type: "fill", source: SEL, filter: AREA, paint: {"fill-color": ["case", ROLE, paint(), purple()], "fill-opacity": 1}});
    map.addLayer({id: SEL + "-line", type: "line", source: SEL, filter: ["any", LINE, AREA], paint: {"line-color": ["case", ROLE, paint(), purple()], "line-width": 4}});
    map.addLayer({id: SEL + "-ring", type: "circle", source: SEL, filter: POINT, paint: {"circle-radius": 12, "circle-color": purple(), "circle-opacity": 0.2, "circle-stroke-width": 2.5, "circle-stroke-color": purple()}});
    map.addLayer({id: SEL + "-dot", type: "circle", source: SEL, filter: POINT, paint: {"circle-radius": 6, "circle-color": ["case", ROLE, paint(), purple()], "circle-stroke-width": 2, "circle-stroke-color": ring()}});
  }
  const put = () => { ensure(); map.getSource(SRC)?.setData(data(feats)); map.getSource(SEL)?.setData(data(picked)); };
  // a new style took the layers away, or the style was not ready when the objects came: put the layers back when the style is ready
  const back = () => { if((feats.length || picked.length) && !map.getSource(SRC)) put(); };
  map.on("styledata", back); map.on("idle", back);
  function recolour(){
    if(!map.getSource(SRC)) return;
    const c = paint();
    map.setPaintProperty(SRC + "-fill", "fill-color", c); map.setPaintProperty(SRC + "-line", "line-color", c); map.setPaintProperty(SRC + "-dot", "circle-color", c);
    map.setPaintProperty(SEL + "-fill", "fill-color", ["case", ROLE, c, purple()]); map.setPaintProperty(SEL + "-line", "line-color", ["case", ROLE, c, purple()]);
    map.setPaintProperty(SEL + "-dot", "circle-color", ["case", ROLE, c, purple()]);
    map.setPaintProperty(SRC + "-dot", "circle-stroke-color", ring()); map.setPaintProperty(SEL + "-dot", "circle-stroke-color", ring());
  }
  document.addEventListener("rs:themechange", recolour);
  // the bounds of some features (a feature, or all the parts of an object): a point gives a zoom of 18, an area or a line its box, clear of the dock at the bottom
  function fit(f, bottom = 0){
    const list = [].concat(f), b = new window.maplibregl.LngLatBounds(), add = (c) => (typeof c[0] === "number" ? b.extend(c) : c.forEach(add));
    const walk = (g) => (g.type === "GeometryCollection" ? g.geometries.forEach(walk) : add(g.coordinates));
    list.forEach((x) => walk(x.geometry));
    if(list.length === 1 && list[0].geometry.type === "Point") map.easeTo({center: list[0].geometry.coordinates, zoom: Math.max(map.getZoom(), 18), duration: 500});
    else map.fitBounds(b, {padding: {top: 80, left: 60, right: 60, bottom: bottom + 60}, maxZoom: 19, duration: 500});
  }
  return {
    draw(f){ feats = f; learn(f.concat(picked)); if(map.getSource(SRC)) recolour(); put(); },
    select(f){ picked = f == null ? [] : [].concat(f); learn(feats.concat(picked)); if(map.getSource(SRC)) recolour(); put(); },
    fit, recolour, colour,
    clear(){ feats = []; picked = []; series = new Map(); put(); },
  };
}

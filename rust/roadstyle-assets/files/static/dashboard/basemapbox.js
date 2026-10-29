// The base-map box (docs/design/dashboard_templates.md, 3.3): the heading "Base map", one radio row with a swatch for each map, a divider, and
// "On top": Hillshade, Labels and 3D buildings. A map with a dark twin is one row that follows the page's theme. The order on the map: the base
// map, the hillshade, the labels, the roads, the page's own layers, the buildings, the selection. The URLs of the layers on top are
// data/basemaps.json `ontop` (O.ontop).
//
// THE LABELS SWITCH is one state for the 2D map and the Google 3D window (window.rsLabelsOn): the window always follows it. The 2D map gets
// labels only from a base map that can show them: the style's own labels (a vector style), or Esri's label tiles (Esri Gray, Esri Satellite).
// Blank, OpenStreetMap, Esri Streets and CARTO get no label layer from the page. The choice is kept for each base map.
import {map, O, _emit} from "./core.js";
import {rsBuildings} from "./basemap.js";

const _bxEl = (tag, cls, txt) => { const e = document.createElement(tag); if(cls) e.className = cls; if(txt) e.textContent = txt; return e; };
const _bxGet = k => { try{ return localStorage.getItem("rs-top:" + k); }catch(e){ return null; } };
const _bxSet = (k, v) => { try{ localStorage.setItem("rs-top:" + k, v ? "1" : "0"); }catch(e){} };
const _bxTips = {
  hillshade: "Shaded relief: the hills drawn with shadows from the terrain heights, as if lit from the north-west, so slopes and valleys show.",
  labels: "Place and street names. The Google 3D window always follows this switch; the 2D map shows them only where the base map can (OpenFreeMap, Esri Gray, Esri Satellite).",
  buildings: "The buildings of an OpenFreeMap base map, raised to their heights in the tilted view.",
};
// a swatch is [land, road, water]: the land color, a diagonal road stroke, and a water triangle in the lower right corner (drawn in CSS)
const _bxSwatch = b => {
  const s = b.swatch;
  if(!Array.isArray(s)) return s || b.bg;
  return "linear-gradient(to top left," + s[2] + " 0 32%,transparent 32%),linear-gradient(135deg,transparent 0 40%," + s[1] + " 40% 54%,transparent 54%)," + s[0];
};
export function buildBox(menu){
  const bms = window.RS_BASEMAPS || [], root = document.documentElement, ontop = O.ontop || {};
  const byKey = k => bms.find(b => b.key === k);
  const isDark = () => root.dataset.rsTheme === "dark";
  let current = (bms[0] || {}).key;
  menu.classList.add("rs-bm-box"); menu.innerHTML = "";
  menu.appendChild(_bxEl("div", "rs-bm-h", "Base map"));
  const rows = [];
  bms.filter(b => !bms.some(x => x.dark === b.key)).sort((x, y) => (x.order ?? 99) - (y.order ?? 99)).forEach(b => {
    const lab = _bxEl("label", "rs-bm-row"), r = _bxEl("input"), sw = _bxEl("span", "rs-bm-sw");
    r.type = "radio"; r.name = "rs-bm"; r.value = b.key; sw.style.background = _bxSwatch(b);
    lab.append(r, sw, _bxEl("span", "rs-bm-n", b.title || b.label));
    r.onchange = () => window.rsSetBasemap(b.dark && isDark() ? b.dark : b.key);
    menu.appendChild(lab); rows.push([b, r, sw]);
  });
  menu.appendChild(_bxEl("hr"));
  menu.appendChild(_bxEl("div", "rs-bm-h", "On top"));
  const tops = {};
  const topRow = (id, label) => {
    const lab = _bxEl("label", "rs-bm-row"), c = _bxEl("input"); c.type = "checkbox"; c.id = "rs-top-" + id; lab.append(c, _bxEl("span", "rs-bm-n", label));
    lab.title = _bxTips[id]; const i = _bxEl("span", "rs-bm-i", "i"); i.title = _bxTips[id]; lab.append(i);
    menu.appendChild(lab); tops[id] = {lab, c}; return c;
  };
  // the first layer of the page that is not the backdrop, the base map or a layer of this box: the layers on top go under it
  const firstRoad = () => { const l = map.getStyle().layers.find(x => x.id !== "bg" && x.id !== "basemap" && !x.id.startsWith("vbm-") && !x.id.startsWith("rs-top-")); return l && l.id; };
  const raster = (id, on, spec) => {
    const lid = "rs-top-" + id, old = map.getSource(lid), stale = on && old && old.tiles && old.tiles[0] !== (spec && spec.url);      // another map needs other label tiles
    if(!on || stale){ if(map.getLayer(lid)) map.removeLayer(lid); if(old) map.removeSource(lid); if(!on) return; }
    if(map.getLayer(lid) || !spec) return;
    map.addSource(lid, {type: "raster", tiles: [spec.url], tileSize: 256, maxzoom: 16, attribution: spec.attr});
    map.addLayer({id: lid, type: "raster", source: lid, paint: {"raster-opacity": spec.opacity}}, firstRoad());
  };
  const vector = () => { const b = byKey(current); return !!(b && b.style_url); };
  const labelKind = () => vector() ? "style" : /^(satellite|esri_gray|esri_dark_gray)$/.test(current) ? "esri" : "none";
  // the choice is kept for each base map (a map and its dark twin share it); the default is on for a vector style, off elsewhere
  const baseKey = () => { const t = bms.find(x => x.dark === current); return t ? t.key : current; };
  const wantOf = () => { const v = _bxGet("labels2:" + baseKey()); return v == null ? vector() : v === "1"; };
  window.rsLabelsOn = wantOf;                       // one state for the map and the Google 3D window
  let lastOn = null;
  const apply = () => {
    const vec = vector(), kind = labelKind(), on = wantOf();
    tops.labels.c.checked = on;                       // the switches show the state of the map that is on
    tops.buildings.c.disabled = !vec; tops.buildings.c.checked = vec && rsBuildings();
    tops.buildings.lab.classList.toggle("rs-bm-off", !vec);
    if(lastOn !== on){ lastOn = on; _emit("rs:labelschange", {on}); }
    if(!map.isStyleLoaded()){ map.once("idle", apply); return; }       // the layers wait for the style: "idle" calls this again
    raster("hillshade", tops.hillshade.c.checked, ontop.hillshade);
    const gray = baseKey() === "esri_gray" ? (current === "esri_dark_gray" ? ontop.labels_gray_dark : ontop.labels_gray_light) : ontop.labels;
    raster("labels", kind === "esri" && on, gray);
    if(vec) for(const l of map.getStyle().layers.filter(x => x.id.startsWith("vbm-") && x.type === "symbol")) map.setLayoutProperty(l.id, "visibility", on ? "visible" : "none");
  };
  topRow("hillshade", "Hillshade").checked = _bxGet("hillshade") === "1";
  topRow("labels", "Labels");
  topRow("buildings", "3D buildings");
  tops.hillshade.c.onchange = () => { _bxSet("hillshade", tops.hillshade.c.checked); apply(); };
  tops.labels.c.onchange = () => { _bxSet("labels2:" + baseKey(), tops.labels.c.checked); apply(); };
  tops.buildings.c.onchange = () => rsBuildings(tops.buildings.c.checked);
  const mark = () => rows.forEach(([b, r]) => { r.checked = b.key === current || b.dark === current; });
  // a map with a twin shows the swatch of the twin of the current theme
  const swatches = () => rows.forEach(([b, , sw]) => { const tw = b.dark && byKey(b.dark); sw.style.background = _bxSwatch(isDark() && tw ? tw : b); });
  document.addEventListener("rs:basemapchange", e => { current = e.detail.basemap; mark(); setTimeout(apply, 0); });
  document.addEventListener("rs:basemapready", apply);
  document.addEventListener("rs:buildingschange", apply);
  document.addEventListener("rs:themechange", swatches);
  map.on("load", apply);
  mark(); swatches(); apply();
}

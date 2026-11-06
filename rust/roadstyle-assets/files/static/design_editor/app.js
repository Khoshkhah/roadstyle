// The design editor of `roadstyle design edit <roads>` (index.html): one road file on a map of its own, with the design panel
// (../dashboard/design/design_panel.js, docs/guides/design-panel.md). The engine (roadstyle-wasm) reads the file and makes the tiles in a worker
// (worker.js): a new look on the same tiles is LiveMap.setLook, and a look that needs new tiles is a new map (draw). The page is a host of the
// standard dashboard: its template (host_options.json), its panel (#sb with .sb-card, .sb-top and .sb-body) that the design panel draws into,
// and the hide and show buttons. The URL names the files under /area/: ?roads=<road file>&design=<design file>. A change of the design goes
// to the server (a PUT of the design file); the panel also keeps it in this browser.
import {rsDashboard} from "../dashboard/index.js";
import {rsFirstPaint} from "../dashboard/template.js";
import {designPanel} from "../dashboard/design/design_panel.js";
import {caller} from "../dashboard/worker/call.js";

const P = "rs-";                                                   // the prefix of the roads' layers, sources and images on the map
const ml = globalThis.maplibregl;
const q = new URLSearchParams(location.search), roadsName = q.get("roads"), designName = q.get("design") || "design.json";
const boot = document.getElementById("dz-boot");
const area = (name) => "/area/" + encodeURIComponent(name);
async function get(name, need = true){
  const r = await fetch(area(name), {cache: "no-store"});
  if(r.ok) return r;
  if(need) throw new Error(`${name}: not found (${r.status}). Open the address that roadstyle design edit gives.`);
  return null;
}

try { await main(); boot.remove(); }
catch(e){ boot.textContent = "The design editor could not start: " + e.message; throw e; }

async function main(){
  if(!roadsName) throw new Error("the address names no road file (?roads=...). Open the address that roadstyle design edit gives.");
  const opts = await (await fetch("../host_options.json")).json();
  opts.dashboard.panel.hide = [];                                  // none of roadstyle's own panel sections: the design panel fills the panel
  rsFirstPaint(opts.first_paint);
  const sb = document.getElementById("sb"), show = document.getElementById("sb-show");
  document.getElementById("sb-hide").onclick = () => { sb.classList.add("hidden"); show.style.display = "flex"; };
  show.onclick = () => { sb.classList.remove("hidden"); show.style.display = ""; };

  // the engine and the roads: a GeoParquet, GeoJSON or Shapefile (with its .dbf and .prj beside it) file
  const call = caller(new Worker(new URL("./worker.js", import.meta.url), {type: "module"}));
  await call({type: "init", pkgUrl: new URL("../level_editor/pkg/roadstyle_wasm.js", import.meta.url).href});
  const ext = roadsName.split(".").pop().toLowerCase(), stem = roadsName.replace(/\.[^.]+$/, "");
  const kind = ext === "shp" ? "shp" : ext === "geojson" || ext === "json" ? "geojson" : "parquet";
  const msg = {type: "open", kind, name: stem, bytes: await (await get(roadsName)).arrayBuffer(), options: {args: {state: "live", arrows: true, labels: true}}};
  if(kind === "shp"){
    msg.dbf = await (await get(stem + ".dbf")).arrayBuffer();
    msg.prj = await (await get(stem + ".prj", false))?.text();
  }
  boot.textContent = "Making the map …";
  const {look} = await call(msg, [msg.bytes, msg.dbf].filter(Boolean));

  // the map: a new map is a new generation of dz:// tiles (worker.js); its road table is the dashboard's RS_SIDE
  let lookText = null, map = null, rs = null, mine = {layers: [], sources: []};
  async function make(){
    const b = await call({type: "draw", text: lookText});
    window.RS_SIDE = JSON.parse(new TextDecoder().decode(b.table));
    document.dispatchEvent(new CustomEvent("rs:tableready"));
    return JSON.parse(b.style);
  }
  const image = (id, v) => new Promise((done) => {                 // an <img> reads an SVG icon too (map.loadImage does not)
    const im = typeof v === "string" ? {url: v} : v, img = new Image();
    img.onload = () => { if(map.hasImage(id)) map.removeImage(id); map.addImage(id, img, {sdf: !!im.sdf, pixelRatio: im.pixelRatio || 1}); done(); };
    img.onerror = () => { console.warn(`design editor: the image ${id} could not be read`); done(); };
    img.src = im.url;
  });
  // the roads style on the map in place of the one before (its layers first, then its sources); its images with the prefix P, as the panel's restyle has them
  async function showRoads(st){
    for(const id of mine.layers) if(map.getLayer(id)) map.removeLayer(id);
    for(const id of mine.sources) if(map.getSource(id)) map.removeSource(id);
    const own = (st.metadata || {})["roadstyle:images"] || {};
    await Promise.all(Object.entries(own).map(([n, v]) => image(P + n, v)));
    const have = map.getGlobalState();                             // a value that the map has (the theme, the person's switches) stays
    for(const [k, v] of Object.entries(st.state || {})) if(!(k in have)) map.setGlobalStateProperty(k, v.default ?? null);
    for(const [id, src] of Object.entries(st.sources)) map.addSource(P + id, src);
    for(const l of st.layers){
      let json = JSON.stringify(l);
      for(const n of Object.keys(own)) json = json.replaceAll(`"${n}"`, `"${P}${n}"`);
      const layer = JSON.parse(json);
      map.addLayer({...layer, id: P + l.id, ...(l.source ? {source: P + l.source} : {})});
    }
    mine = {layers: st.layers.map((l) => P + l.id), sources: Object.keys(st.sources).map((id) => P + id)};
    rs.setStyle(st);
  }

  const style = await make();
  const bb = window.RS_SIDE.bboxes.filter(Boolean).reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])], [180, 90, -180, -90]);
  if(bb[0] > bb[2]) throw new Error(`${roadsName} has no road with a line`);
  ml.addProtocol("dz", async (params) => ({data: (await call({type: "tile", url: params.url})).bytes}));
  const div = document.createElement("div");
  div.style.cssText = "position:absolute;inset:0";
  document.body.appendChild(div);
  map = window.map = new ml.Map({container: div, style: opts.style, bounds: [[bb[0], bb[1]], [bb[2], bb[3]]], attributionControl: {compact: true}});
  map.addControl(new ml.NavigationControl({visualizePitch: true}));
  map.addControl(new ml.ScaleControl({maxWidth: 120, unit: "metric"}), "bottom-left");
  rs = window.rs = rsDashboard(map, {style: null, prefix: P, tiles: true, basemaps: opts.basemaps, ontop: opts.ontop, dashboard: opts.dashboard});
  const f = rs.freeArea(), r = map.getContainer().getBoundingClientRect();     // the roads in the part of the map that the panel and the bar leave free
  map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {duration: 0, padding: {left: f.lo - r.left + 40, right: r.right - f.hi + 40, top: f.top - r.top + 40, bottom: r.bottom - f.bottom + 40}});
  while(!map.isStyleLoaded()) await new Promise((ok) => setTimeout(ok, 50));
  await showRoads(style);

  // the design panel: it owns the design; the page gives it the way to show a look (setLook: the same tiles; redraw: a new map)
  const dz = window.dz = await designPanel({panel: sb, dashboard: rs, map, look: JSON.parse(look), backLabel: null, restyle: {imagePrefix: P},
    storageKey: "roadstyle-design:" + roadsName,
    setLook: async (text) => { lookText = text; return (await call({type: "setLook", text})).style ?? undefined; },
    redraw: async (text, draw) => {
      lookText = text;
      if(!draw) return "";
      const t0 = performance.now();
      await showRoads(await make());
      return `The map shows this design: a new map, in ${((performance.now() - t0) / 1000).toFixed(2)} s.`;
    }});
  // the design file of the server wins over the design that this browser kept; either one is drawn at the start
  const saved = await get(designName, false);
  if(saved && !(await dz.load(await saved.text(), {draw: false}))) console.warn(`design editor: ${designName} is not a design file; the page does not change it until you change the design`);
  if(lookText) await showRoads(await make());
  let wait = null;
  dz.addEventListener("change", (e) => {
    clearTimeout(wait);
    wait = setTimeout(async () => {
      const r = await fetch(area(designName), {method: "PUT", body: e.detail.text}).catch((err) => ({ok: false, status: err.message}));
      if(!r.ok) console.warn(`design editor: ${designName} not saved (${r.status}); this browser keeps the design`);
    }, 500);
  });
  dz.open();
}

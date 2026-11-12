// roadstyle's map dashboard, the entry: rsDashboard(map, options) adds the map controls and the road interaction of roadstyle's page
// to a MapLibre map (docs/design/dashboard_module.md). The options have the names of render_web.render's keywords; the values are
// those the page reads (render_web.py makes them). Call it right after `new maplibregl.Map(...)`, before the map's "load" event.
import {initCore, useStyle, _contractError, _emit, setPrefix} from "./core.js";
import {requestsOf, setAdapter} from "./adapter.js";
import {httpAdapter, filesAdapter, engineAdapter} from "./ways.js";
import {initGeneration, useGeneration} from "./generation.js";
import {initTemplate, setSheet, getSheet} from "./template.js";
import {initWindows, freeArea} from "./windows.js";
import {initBoundary} from "./boundary.js";
import {initTheme} from "./theme.js";
import {mountColumn, rsTools} from "./tools.js";
import {initColorBox, useColorBox} from "./colorbox.js";
import {initNavBox} from "./navbox.js";
import {initRoadsBox, useRoadsBox} from "./roadsbox.js";
import {naturalBreaks} from "./breaks.js";
import {initSelectBox} from "./selectbox.js";
import {initColorPick} from "./colorpick.js";
import {initToolbar} from "./toolbar.js";
import {initSettings} from "./settings.js";
import {initPlacement} from "./placement.js";
import {initSections} from "./sections.js";
import {initTip} from "./tip.js";
import {initPanelScroll, initInnerScroll} from "./panelscroll.js";
import {initOverlay} from "./overlay.js";
import {initPanel, initPanelTab} from "./panel.js";
import {initZoom} from "./zoom.js";
import {initView3D} from "./view3d.js";
import {initStreetView} from "./streetview.js";
import {initGoogle3D} from "./google3d.js";
import {initBasemap} from "./basemap.js";
import {useTops} from "./basemapbox.js";
import {roadLayers} from "./roadlayers.js";
import {initFilter, useFilter} from "./filter.js";
import {initFind} from "./find.js";
import {initColor, useColor} from "./color.js";
import {useLegend} from "./legend.js";
import {initOverlays, useOverlays} from "./overlays.js";
import {initFeatures, useFeatures} from "./features.js";
import {initWalls} from "./walls.js";
import {initTunnel} from "./tunnel.js";
import {initBridgeMesh, useBridgeMesh, initBridgeApi} from "./bridgemesh.js";
import {initViews} from "./views.js";
import {initArrows} from "./arrows.js";
import {initSelect, useSelect} from "./select.js";
import {makeApi, fromUrl, refreshState} from "./api.js";
import {setData, clearData} from "./live.js";
import {vehiclesApi} from "./vehicles.js";
// an option left out: render's default. The theme's values (select_color, arrow_icon, arrow_color, arrow_rules) have none:
// they come from the look (roadstyle's profile and palette).
const RS_DEFAULTS = {
  style: null,                 // the roads style (the layer ids, the base map layer, the metadata); null: it comes later (rs.setStyle)
  prefix: "",                  // the prefix of the roads style's source and layer ids in the map ("rs-": the page added them so)
  adapter: null,               // the adapter of the page (adapter.js): {tile, rows, lines, query, schema, frames, style}, each optional; null: the page has its own road table
  road_table: null,            // the road table {props, mids, bboxes, lines} by row (stage 1); null: window.RS_SIDE, else none
  vehicles: null,              // a traffic microsimulation run to load at start: {wasm, fcd, net, routes} as URLs (vehicles.js); null: none
  vehicle_look: null,          // the look's vehicles section: the colour of each kind, each SUMO vClass, the numbers of a run (vehicles.js)
  sources: null,               // role -> {source, layer} (roadstyle:sources); null: the style's metadata, else its layers
  arrows: undefined,           // "points" | "line" | "line-center" | null (roadstyle:arrows); undefined: the metadata, else the style
  bridge_profile: null,        // the complete bridge profile of the 3D decks (roadstyle:bridge_profile), or null: rsBridgeGroups lists its chains and nodes
  live: null,                  // the live data (R22): {color: "rs_c", width: "rs_w", types, ramp, nodata}, or null (the page has none)
  dashboard: null,             // the template's typed options (roadstyle::dashboard::Dashboard): layout, panel, toolbar, windows, phone; null: none
  basemaps: [], ontop: {}, basemap_switcher: true, hillshade: false, terrain: false, terrain_exaggeration: null, buildings_opacity: null, terrain_tunnels: "fade",
  tiles: false,                // the roads are a vector source (the template's no-roads message); simple mode comes from the style
  tiles_generation: null,      // the generation of the tiles (the PMTiles metadata, a tile server's answer), else the ?g= of the style's tile URLs
  popup_mode: "popup", find_control: false, zoom_readout: true, pitch_3d: 55,
  street_view: "window", street_view_key: "", mapillary_token: "", google_3d: false,
  filter: {classes: []}, color_active: 0,
  legend: true,                 // the legend box of the colour options (render's keyword; the style always has the legend data)
  overlays: [], overlay_control: true, overlay_popup: true,
  overlays_label: "Map layers",  // the label of the one switch for the style's base-map layers (the base-map box) and of their list (the legend box)
  modes: [], box_layout: "corner",   // roadstyle:controls.modes [[mode, count], ...]; "stack": a base map's page (Layers under Roads, folded)
  tunnel: {layers: {}, steps: [], control: false}, fill_layers: [], pick: [], road_fill: {on: true, paint: {}},
  views: [], items: null, edge_id_col: "edge_id", arrow_icon: null,
  images: null,                 // {id: {url, sdf, pixelRatio}} (a page's base-map patterns and icons); null: the style's roadstyle:images
};
// the options that the page did not give and that the style's metadata gives: the road popup, the hover tooltip and the hover delay
// (roadstyle:interaction: export_style, the Rust engine), the colour options and their legends (roadstyle:color_options: the Rust
// engine, when the map has data colours), and the other controls of a style made with state "live" (roadstyle:controls, the interaction
// contract of docs/design/rust_library.md: the filter panel, the overlays, the tunnel look, the road fill, the arrows' rules, ...).
// The overlays' sources and layers there have no prefix: the page's prefix goes on them.
let _fromCtl = [];            // the options that the last style's controls gave
function fromStyle(o, given){
  const meta = (o.style && o.style.metadata) || {}, it = meta["roadstyle:interaction"] || {};
  const ctl = meta["roadstyle:controls"] || {}, P = o.prefix || "";
  for(const k of _fromCtl) if(!given.has(k)) o[k] = RS_DEFAULTS[k];      // a later style without a control takes the old style's value away (the filter, the overlays, the tunnels, ...)
  _fromCtl = Object.keys(ctl);
  for(const k in ctl) if(!given.has(k)) o[k] = ctl[k];
  if(!given.has("overlays") && ctl.overlays && P)
    o.overlays = ctl.overlays.map(ov=>({...ov, source: P+ov.source, layers: ov.layers.map(id=>P+id), hit: ov.hit && P+ov.hit, extrude: ov.extrude && P+ov.extrude,
                                        base: ov.base && Object.fromEntries(Object.entries(ov.base).map(([id, f])=>[P+id, f]))}));
  for(const ov of o.overlays || []){ const u = (it.base_props || {})[P ? ov.source.slice(P.length) : ov.source]; if(u) ov.props = u; }   // the rows by feature id (a page gives its own `props`)
  if(!given.has("road_popup")) o.road_popup = "popup" in it ? it.popup : null;           // false: none; null: every field; [fields]
  if(!given.has("road_tooltip")) o.road_tooltip = it.tooltip || false;                   // false | true | [fields]
  if(!given.has("hover_delay_ms")) o.hover_delay_ms = it.hover_delay_ms != null ? it.hover_delay_ms : 300;
  if(!given.has("color_options")) o.color_options = meta["roadstyle:color_options"] || [];
  if(!given.has("bridge_profile")) o.bridge_profile = meta["roadstyle:bridge_profile"] || null;
  if(!given.has("live")) o.live = meta["roadstyle:live"] || null;
  if(!given.has("images")) o.images = meta["roadstyle:images"] || null;
}
// returns the dashboard object (docs/design/rust_library.md, "The runtime API", api.js): setStyle, and the methods of the API
export function rsDashboard(map, options){
  const o = {...RS_DEFAULTS, ...options}, given = new Set(Object.keys(options));
  // a style of a newer contract, or of another generation than its tiles: an error (console, the result's `error`), and the dashboard
  // reads it as no style
  initGeneration(map, o);
  let error = _contractError(o.style) || useGeneration(o.style);
  if(error){ console.error(error); o.style = null; }
  fromStyle(o, given);
  initCore(map, o);
  window.RS_DOCK = o.dock || null;      // the look's dock section: the colours of the data dock's objects (data/kinds.js)
  initTemplate();
  initTheme();
  initPanel();
  initZoom();
  initView3D();
  initPanelTab();
  initStreetView();
  initGoogle3D();
  initBasemap();
  initBoundary();
  initFilter();
  initFind();
  initColor();
  useLegend();
  initOverlays();
  initFeatures();
  initWalls();
  initTunnel();
  initBridgeApi();
  initBridgeMesh();
  initViews();
  initArrows();
  initSelect();
  initColorBox();
  initNavBox();
  initRoadsBox();
  initSelectBox();
  initColorPick();
  initPanelScroll();
  initInnerScroll();
  initPlacement();
  initSettings();
  initSections();
  initWindows();
  initTip();
  initToolbar() || mountColumn();  // every control module has defined its tool: the bar or the column shows them (tools.js)
  initOverlay();
  const rs = makeApi({
    // roadLayers (roadlayers.js) on this map and this dashboard: a host page that puts a new roads style on its map (a server's tiled style, a LiveMap's)
    // the dashboard reads the roads with the prefix of their layers: a page made with no prefix (page_from) takes the prefix of roadLayers ("rs-" by default).
    // The controls of a style that it shows are the roads' own: they take the place of the page's first options (a page made with no roads gave empty ones)
    roadLayers(opts = {}){
      const prefix = opts.prefix ?? "rs-";
      setPrefix(prefix); o.prefix = prefix;
      const r = roadLayers({map, dashboard: rs, ...opts, prefix}), show = r.show;
      r.show = (style, more) => { for(const k of Object.keys((style?.metadata || {})["roadstyle:controls"] || {})) given.delete(k); return show(style, more); };
      return r;
    },
    // a new roads style: the page added its sources and layers to the map first (with the prefix). The controls stay; they read the
    // new style, its metadata and its layers. The selection and the hover go: they were the old roads'.
    setStyle(style, more){
      rs.error = _contractError(style) || useGeneration(style);
      if(rs.error){ console.error(rs.error); style = null; }
      o.style = style; fromStyle(o, given);
      if(more && "road_table" in more) o.road_table = more.road_table;      // the new style's road table (stage 1)
      useStyle(style); useOverlays(); useFeatures(); useSelect(); useFilter(); useBridgeMesh(); initTunnel(); initArrows(); initBoundary(); useColor(); useLegend(); useColorBox(); useRoadsBox(); useTops(); refreshState();
      _emit("rs:stylechange", {});     // a part that paints on the road layers (the design panel) paints again
    },
    // a new look on the same tiles (LiveMap.setLook, docs/guides/design-panel.md): each road layer on the map (the prefix and its id, and its copies with the
    // prefixes of `also`) takes the new style's paint, layout and filter, the style's images come again (with `imagePrefix` before their names, in the
    // layers too), and the controls read the new style. The sources, their tiles and the roads' feature state stay. false: the new style has other layers.
    async restyle(st, {also = [], imagePrefix = ""} = {}){
      const ids = s => (s ? s.layers.map(l => l.id) : []).sort().join("\n");
      if(!o.style || ids(o.style) !== ids(st)) return false;
      const own = (st.metadata || {})["roadstyle:images"] || {};
      await Promise.all(Object.entries(own).map(([n, v]) => new Promise(done => {
        const im = typeof v === "string" ? {url: v} : v, img = new Image();
        img.onload = () => { const id = imagePrefix + n; if(map.hasImage(id)) map.removeImage(id); map.addImage(id, img, {sdf: !!im.sdf, pixelRatio: im.pixelRatio || 1}); done(); };
        img.onerror = done;
        img.src = im.url;
      })));
      const same = (a, b) => JSON.stringify(a) === JSON.stringify(b), now = new Map(map.getStyle().layers.map(l => [l.id, l]));
      for(const l of st.layers){
        let json = JSON.stringify(l);
        if(imagePrefix) for(const n of Object.keys(own)) json = json.replaceAll(`"${n}"`, `"${imagePrefix}${n}"`);
        const layer = JSON.parse(json);
        for(const id of [(o.prefix || "") + l.id, ...also.map(p => p + l.id)]){
          const was = now.get(id);
          if(!was) continue;
          for(const k of new Set([...Object.keys(was.paint || {}), ...Object.keys(layer.paint || {})])) if(!same(was.paint?.[k], layer.paint?.[k])) map.setPaintProperty(id, k, layer.paint?.[k]);
          for(const k of new Set([...Object.keys(was.layout || {}), ...Object.keys(layer.layout || {})])) if(!same(was.layout?.[k], layer.layout?.[k])) map.setLayoutProperty(id, k, layer.layout?.[k]);
          if(!same(was.filter, layer.filter)) map.setFilter(id, layer.filter ?? null);
        }
      }
      rs.setStyle(st);
      return true;
    },
    // the phone's bottom sheet: rs.sheet() is its height (0 closed, 1 40 %, 2 full; null: no sheet), rs.sheet(n) sets it; rs.freeArea() is the part of
    // the map that the bar, the panel and the sheet leave free, in window coordinates ({lo, hi, top, bottom}): a host pads its map with it
    sheet: n => n === undefined ? getSheet() : setSheet(n),
    prefix: o.prefix || "",         // the prefix of the roads style's ids on the map (a part that paints the road layers finds them so)
    freeArea,
    // R22, live data: join a table to the roads and colour or size them from it, with no new style; clearData takes it away (live.js)
    setData, clearData,
    // the cut points of rs.setData, for a page that colours many calls the same way (an hour slider: the breaks of the whole day)
    naturalBreaks: (values, k) => naturalBreaks(values, k),
  });
  rs.error = error;               // null, or the text of the contract error of the style (setStyle sets it again)
  rs.request = requestsOf();      // the four requests (adapter.js): tile, rows (row), query (schema), frames, lines
  rs.setAdapter = setAdapter;     // the adapter of the page, later (null: none)
  window.rsHttpAdapter = httpAdapter;     // the adapters of ways D, B and C (ways.js; a one-file page cannot import the module)
  window.rsFilesAdapter = filesAdapter;
  window.rsEngineAdapter = engineAdapter;
  rs.vehicles = vehiclesApi();    // a traffic microsimulation run on the map (vehicles.js)
  // a page with the option `vehicles` ({wasm, fcd, net, routes}: URLs) loads its run at start; a failure is reported, never hidden
  if(o.vehicles) rs.vehicles.load(o.vehicles).catch(e => console.error("rs.vehicles: the run of the option vehicles did not load:", e));
  window.rsTools = rsTools;       // the alias of rs.tools
  window.rs = rs;                 // the page's one object (the window.rs* functions stay as they are)
  // `rs:ready`: window.rs is there and the panel's sections are in place (initSections runs at DOMContentLoaded, before this listener); window.rsReady is true
  // from then on, for a script that runs later. A page's own script (`page_script=`) waits for it.
  const ready = () => { window.rsReady = true; _emit("rs:ready", {}); };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", ready) : ready();
  fromUrl(rs);
  return rs;
}

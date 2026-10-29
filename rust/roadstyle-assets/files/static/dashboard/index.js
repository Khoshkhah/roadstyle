// roadstyle's map dashboard, the entry: rsDashboard(map, options) adds the map controls and the road interaction of roadstyle's page
// to a MapLibre map (docs/design/dashboard_module.md). The options have the names of render_web.render's keywords; the values are
// those the page reads (render_web.py makes them). Call it right after `new maplibregl.Map(...)`, before the map's "load" event.
import {initCore, useStyle, _contractError, _emit} from "./core.js";
import {initGeneration, useGeneration} from "./generation.js";
import {initTemplate} from "./template.js";
import {initBoundary} from "./boundary.js";
import {initTheme} from "./theme.js";
import {mountColumn, rsTools} from "./tools.js";
import {initColorBox} from "./colorbox.js";
import {initSelectBox} from "./selectbox.js";
import {initToolbar} from "./toolbar.js";
import {initSettings} from "./settings.js";
import {initPlacement} from "./placement.js";
import {initSections} from "./sections.js";
import {initWindows} from "./windows.js";
import {initTip} from "./tip.js";
import {initPanelScroll} from "./panelscroll.js";
import {initOverlay} from "./overlay.js";
import {initPanel, initPanelTab} from "./panel.js";
import {initZoom} from "./zoom.js";
import {initView3D} from "./view3d.js";
import {initStreetView} from "./streetview.js";
import {initGoogle3D} from "./google3d.js";
import {initBasemap} from "./basemap.js";
import {initFilter, initFilterBox, useFilter} from "./filter.js";
import {initFind} from "./find.js";
import {initColor, useColor} from "./color.js";
import {useLegend} from "./legend.js";
import {initOverlays} from "./overlays.js";
import {initFeatures} from "./features.js";
import {initTunnel} from "./tunnel.js";
import {initViews} from "./views.js";
import {initArrows} from "./arrows.js";
import {initSelect, useSelect} from "./select.js";
import {makeApi, fromUrl} from "./api.js";
import {setData, clearData} from "./live.js";
// an option left out: render's default. The theme's values (select_color, arrow_icon, arrow_color, arrow_rules) have none:
// they come from the look (roadstyle's profile and palette).
const RS_DEFAULTS = {
  style: null,                 // the roads style (the layer ids, the base map layer, the metadata); null: it comes later (rs.setStyle)
  prefix: "",                  // the prefix of the roads style's source and layer ids in the map ("rs-": the page added them so)
  road_table: null,            // the road table {props, mids, bboxes, lines} by row (stage 1); null: window.RS_SIDE, else none
  sources: null,               // role -> {source, layer} (roadstyle:sources); null: the style's metadata, else its layers
  arrows: undefined,           // "points" | "line" | "line-center" | null (roadstyle:arrows); undefined: the metadata, else the style
  live: null,                  // the live data (R22): {color: "rs_c", width: "rs_w", types, ramp, nodata}, or null (the page has none)
  dashboard: null,             // the template's typed options (roadstyle::dashboard::Dashboard): layout, panel, toolbar, windows, phone; null: none
  basemaps: [], ontop: {}, basemap_switcher: true,
  tiles: false,                // the roads are a vector source (the template's no-roads message); simple mode comes from the style
  tiles_generation: null,      // the generation of the tiles (the PMTiles metadata, a tile server's answer), else the ?g= of the style's tile URLs
  popup_mode: "popup", find_control: false, zoom_readout: true, pitch_3d: 55,
  street_view: "window", street_view_key: "", google_3d: false,
  filter: {on: false, classes: []}, color_active: 0,
  filter_control: true,         // the Roads box (render's keyword; a page key, not the style's)
  legend: true,                 // the legend box of the colour options (render's keyword; the style always has the legend data)
  overlays: [], overlay_control: true, overlay_popup: true,
  modes: [], box_layout: "corner",   // roadstyle:controls.modes [[mode, count], ...]; "stack": a base map's page (Layers under Roads, folded)
  tunnel: {layers: {}, steps: [], control: false}, fill_layers: [], pick: [], road_fill: {on: true, paint: {}},
  views: [], items: null, edge_id_col: "edge_id", arrow_icon: null,
};
// the options that the page did not give and that the style's metadata gives: the road popup, the hover tooltip and the hover delay
// (roadstyle:interaction: export_style, the Rust engine), the colour options and their legends (roadstyle:color_options: the Rust
// engine, when the map has data colours), and the other controls of a style made with state "live" (roadstyle:controls, the interaction
// contract of docs/design/rust_library.md: the filter panel, the overlays, the tunnel look, the road fill, the arrows' rules, ...).
// The overlays' sources and layers there have no prefix: the page's prefix goes on them.
function fromStyle(o, given){
  const meta = (o.style && o.style.metadata) || {}, it = meta["roadstyle:interaction"] || {};
  const ctl = meta["roadstyle:controls"] || {}, P = o.prefix || "";
  for(const k in ctl) if(!given.has(k)) o[k] = ctl[k];
  if(!given.has("overlays") && ctl.overlays && P)
    o.overlays = ctl.overlays.map(ov=>({...ov, source: P+ov.source, layers: ov.layers.map(id=>P+id), hit: ov.hit && P+ov.hit, extrude: ov.extrude && P+ov.extrude,
                                        base: ov.base && Object.fromEntries(Object.entries(ov.base).map(([id, f])=>[P+id, f]))}));
  for(const ov of o.overlays || []) ov.props = (it.base_props || {})[P ? ov.source.slice(P.length) : ov.source];   // the popup fields by row
  if(!given.has("road_popup")) o.road_popup = "popup" in it ? it.popup : null;           // false: none; null: every field; [fields]
  if(!given.has("road_tooltip")) o.road_tooltip = it.tooltip || false;                   // false | true | [fields]
  if(!given.has("hover_delay_ms")) o.hover_delay_ms = it.hover_delay_ms != null ? it.hover_delay_ms : 300;
  // the Roads box: the page option filter_control and a class to show. The facts of the filter (classes, col, access, swatches, minzoom)
  // are the style's (roadstyle:controls.filter); a style made before N32 step 2 has its own `on` there, which stays when the page gives
  // no filter_control
  const f = o.filter || {};
  if(given.has("filter_control") || !("on" in f)) o.filter = {...f, on: o.filter_control !== false && (f.classes || []).length > 0};
  if(!given.has("color_options")) o.color_options = meta["roadstyle:color_options"] || [];
  if(!given.has("live")) o.live = meta["roadstyle:live"] || null;
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
  initFilterBox();
  initColor();
  useLegend();
  initOverlays();
  initFeatures();
  initTunnel();
  initViews();
  initArrows();
  initSelect();
  initColorBox();
  initSelectBox();
  initPanelScroll();
  initPlacement();
  initSettings();
  initSections();
  initWindows();
  initTip();
  initToolbar() || mountColumn();  // every control module has defined its tool: the bar or the column shows them (tools.js)
  initOverlay();
  const rs = makeApi({
    // a new roads style: the page added its sources and layers to the map first (with the prefix). The controls stay; they read the
    // new style, its metadata and its layers. The selection and the hover go: they were the old roads'.
    setStyle(style, more){
      rs.error = _contractError(style) || useGeneration(style);
      if(rs.error){ console.error(rs.error); style = null; }
      o.style = style; fromStyle(o, given);
      if(more && "road_table" in more) o.road_table = more.road_table;      // the new style's road table (stage 1)
      useStyle(style); useSelect(); useFilter(); useColor(); useLegend();
    },
    // R22, live data: join a table to the roads and colour or size them from it, with no new style; clearData takes it away (live.js)
    setData, clearData,
  });
  rs.error = error;               // null, or the text of the contract error of the style (setStyle sets it again)
  window.rsTools = rsTools;       // the alias of rs.tools
  window.rs = rs;                 // the page's one object (the window.rs* functions stay as they are)
  // `rs:ready`: window.rs is there and the panel's sections are in place (initSections runs at DOMContentLoaded, before this listener); window.rsReady is true
  // from then on, for a script that runs later. A page's own script (`page_script=`) waits for it.
  const ready = () => { window.rsReady = true; _emit("rs:ready", {}); };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", ready) : ready();
  fromUrl(rs);
  return rs;
}

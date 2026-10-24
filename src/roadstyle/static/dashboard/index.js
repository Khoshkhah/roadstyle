// roadstyle's map dashboard, the entry: rsDashboard(map, options) adds the map controls and the road interaction of roadstyle's page
// to a MapLibre map (docs/design/dashboard_module.md). The options have the names of render_web.render's keywords; the values are
// those the page reads (render_web.py makes them). Call it right after `new maplibregl.Map(...)`, before the map's "load" event.
import {initCore, useStyle} from "./core.js";
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
  road_table: null,            // the road table {props, mids, bboxes, headings, lines} by row (stage 1); null: window.RS_SIDE, else none
  sources: null,               // role -> {source, layer} (roadstyle:sources); null: the style's metadata, else its layers
  arrows: undefined,           // "points" | "line" | "line-center" | null (roadstyle:arrows); undefined: the metadata, else the style
  live: null,                  // the live data (R22): {color: "rs_c", width: "rs_w", types, ramp, nodata}, or null (the page has none)
  basemaps: [], basemap_switcher: true,
  tiles: false,                // the roads are a vector source (the template's no-roads message); simple mode comes from the style
  popup_mode: "popup", find_control: false, zoom_readout: true, pitch_3d: 55,
  street_view: "window", street_view_key: "", google_3d: false,
  filter: {on: false, classes: []}, color_active: 0,
  overlays: [], overlay_control: true, overlay_popup: true,
  tunnel: {layers: {}, steps: [], control: false}, fill_layers: [], road_fill: {on: true, paint: {}},
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
    o.overlays = ctl.overlays.map(ov=>({...ov, source: P+ov.source, layers: ov.layers.map(id=>P+id), hit: ov.hit && P+ov.hit,
                                        base: ov.base && Object.fromEntries(Object.entries(ov.base).map(([id, f])=>[P+id, f]))}));
  if(!given.has("road_popup")) o.road_popup = "popup" in it ? it.popup : null;           // false: none; null: every field; [fields]
  if(!given.has("road_tooltip")) o.road_tooltip = it.tooltip || false;                   // false | true | [fields]
  if(!given.has("hover_delay_ms")) o.hover_delay_ms = it.hover_delay_ms != null ? it.hover_delay_ms : 300;
  if(!given.has("color_options")) o.color_options = meta["roadstyle:color_options"] || [];
  if(!given.has("live")) o.live = meta["roadstyle:live"] || null;
}
// returns the dashboard object (docs/design/rust_library.md, "The runtime API", api.js): setStyle, and the methods of the API
export function rsDashboard(map, options){
  const o = {...RS_DEFAULTS, ...options}, given = new Set(Object.keys(options));
  fromStyle(o, given);
  initCore(map, o);
  initPanel();
  initZoom();
  initView3D();
  initPanelTab();
  initStreetView();
  initGoogle3D();
  initBasemap();
  initFilter();
  initFind();
  initFilterBox();
  initColor();
  useLegend();
  initOverlays();
  initTunnel();
  initViews();
  initArrows();
  initSelect();
  const rs = makeApi({
    // a new roads style: the page added its sources and layers to the map first (with the prefix). The controls stay; they read the
    // new style, its metadata and its layers. The selection and the hover go: they were the old roads'.
    setStyle(style, more){
      o.style = style; fromStyle(o, given);
      if(more && "road_table" in more) o.road_table = more.road_table;      // the new style's road table (stage 1)
      useStyle(style); useSelect(); useFilter(); useColor(); useLegend();
    },
    // R22, live data: join a table to the roads and colour or size them from it, with no new style; clearData takes it away (live.js)
    setData, clearData,
  });
  window.rs = rs;                 // the page's one object (the window.rs* functions stay as they are)
  fromUrl(rs);
  return rs;
}

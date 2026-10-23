// roadstyle's map dashboard, the entry: rsDashboard(map, options) adds the map controls and the road interaction of roadstyle's page
// to a MapLibre map (docs/design/dashboard_module.md). The options have the names of render_web.render's keywords; the values are
// those the page reads (render_web.py makes them). Call it right after `new maplibregl.Map(...)`, before the map's "load" event.
import {initCore} from "./core.js";
import {initPanel, initPanelTab} from "./panel.js";
import {initZoom} from "./zoom.js";
import {initView3D} from "./view3d.js";
import {initStreetView} from "./streetview.js";
import {initGoogle3D} from "./google3d.js";
import {initBasemap} from "./basemap.js";
import {initFilter, initFilterBox} from "./filter.js";
import {initFind} from "./find.js";
import {initColor} from "./color.js";
import {initLegend} from "./legend.js";
import {initOverlays} from "./overlays.js";
import {initTunnel} from "./tunnel.js";
import {initViews} from "./views.js";
import {initArrows} from "./arrows.js";
import {initSelect} from "./select.js";
// an option left out: render's default. The theme's values (select_color, arrow_icon, arrow_color, arrow_rules) have none:
// they come from the look (roadstyle's profile and palette).
const RS_DEFAULTS = {
  style: null,                 // the style object the map was made with (the layer ids, the base map layer)
  basemaps: [], basemap_switcher: true,
  tiles: false, simple: false, // simple: the id of the one road layer of simple mode with inline data, else false
  popup_mode: "popup", find_control: false, zoom_readout: true, pitch_3d: 55,
  street_view: "window", street_view_key: "", google_3d: false,
  filter: {on: false, classes: []}, color_active: 0,
  overlays: [], overlay_control: true, overlay_popup: true,
  tunnel: {layers: {}, steps: [], control: false}, fill_layers: [], road_fill: {on: true, paint: {}},
  views: [], items: null, edge_id_col: "edge_id", arrow_icon: null,
};
export function rsDashboard(map, options){
  const o = {...RS_DEFAULTS, ...options};
  // the road popup, the hover tooltip and the hover delay: else the style's metadata roadstyle:interaction (export_style, the Rust engine)
  const meta = (o.style && o.style.metadata) || {}, it = meta["roadstyle:interaction"] || {};
  if(!("road_popup" in o)) o.road_popup = "popup" in it ? it.popup : null;           // false: none; null: every field; [fields]
  if(!("road_tooltip" in o)) o.road_tooltip = it.tooltip || false;                   // false | true | [fields]
  if(!("hover_delay_ms" in o)) o.hover_delay_ms = it.hover_delay_ms != null ? it.hover_delay_ms : 300;
  // the colour options and their legends: else the style's metadata roadstyle:color_options (the Rust engine, when the map has data colours)
  if(!("color_options" in o)) o.color_options = meta["roadstyle:color_options"] || [];
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
  initLegend();
  initOverlays();
  initTunnel();
  initViews();
  initArrows();
  initSelect();
  return map;
}

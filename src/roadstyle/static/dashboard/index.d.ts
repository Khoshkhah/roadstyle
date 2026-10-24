// The types of roadstyle's map dashboard (index.js, api.js). docs/design/dashboard_module.md has each option and the data it reads;
// docs/design/rust_library.md, "The runtime API", has the object that rsDashboard returns.
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";

/** An option left out takes render's default (index.js, RS_DEFAULTS), or the value in the style's metadata (roadstyle:interaction,
 *  roadstyle:color_options, roadstyle:controls). Most values are those that roadstyle's Python page or the Rust engine makes. */
export interface DashboardOptions {
  /** The roads style (its layers, its metadata). null: the roads come later, with setStyle. */
  style?: StyleSpecification | null;
  /** The prefix of the roads style's source and layer ids in the map, when the page added them with one ("rs-"). */
  prefix?: string;
  /** The road table of stage 1, by row: each road's fields, midpoint, bbox, heading and line (makeSources(...).roadTable()). null:
   *  window.RS_SIDE (every page of roadstyle has it). */
  road_table?: RoadTableData | null;
  /** The roads are a vector source (tiles). Simple mode and its road layer come from the style. */
  tiles?: boolean;
  /** Role -> {source, layer} (roadstyle:sources): the roads style's sources by role; layer null for a GeoJSON source. */
  sources?: Record<string, { source: string; layer: string | null }> | null;
  /** The style's arrows (roadstyle:arrows): "points" (the dashboard places them), "line", "line-center", or null (none). */
  arrows?: "points" | "line" | "line-center" | null;
  /** The live data that the road layer reads (render's live_data=True): the feature-state names and the ramp; null: none. */
  live?: { color: string; width: string; types?: Record<string, unknown>; ramp?: string[]; nodata?: string } | null;
  /** The base maps of the switcher: {key, label, tiles, bg, maxzoom, attr}. None: the dashboard does not touch the map's base map. */
  basemaps?: Array<{ key: string; label: string; tiles: string[]; bg: string; maxzoom?: number; attr?: string }>;
  basemap_switcher?: boolean;
  /** "popup" (a floating popup) or "panel" (a side panel with the record and the controls). */
  popup_mode?: "popup" | "panel";
  find_control?: boolean;
  zoom_readout?: boolean;
  /** The tilt of the 3D view, in degrees. */
  pitch_3d?: number;
  /** "window": a Street View window over the map; true: a link in the popup; false: none. */
  street_view?: "window" | boolean;
  /** A Google Maps JavaScript API key: Street View's Linked mode and Google 3D. */
  street_view_key?: string;
  google_3d?: boolean;
  /** The selection colour (the theme's selection.select). */
  select_color?: string;
  /** The Roads box: {on, col, classes, swatches, palettes, bridges, tunnels, access}. */
  filter?: { on: boolean; classes: string[]; col?: string; [k: string]: unknown };
  /** The colour options: [{name, prop, legend}]; the legend is categorical {title, entries} or continuous {title, ramp, vmin, vmax}. */
  color_options?: ColorOption[];
  /** The index of the colour option that shows first. */
  color_active?: number;
  overlays?: Array<Record<string, unknown>>;
  overlay_control?: boolean;
  overlay_popup?: boolean;
  tunnel?: Record<string, unknown>;
  fill_layers?: string[];
  road_fill?: { on: boolean; paint: Record<string, unknown> };
  views?: Array<{ name: string; set: Record<string, unknown> }>;
  items?: { label: string; popup: string[] | null; layer: string } | null;
  /** The popup's fields: false (no popup), null (every field) or a list. */
  road_popup?: false | null | string[];
  /** The hover tooltip: false, true (the popup's fields) or a list. */
  road_tooltip?: boolean | string[];
  /** How long the mouse rests on a road before it lights up, in ms. */
  hover_delay_ms?: number;
  /** The column of the road's id (the search always reads it). */
  edge_id_col?: string;
  arrow_icon?: Record<string, unknown> | null;
  arrow_color?: string;
  arrow_rules?: Record<string, unknown>;
}

export interface RoadTableData {
  props: Array<Record<string, unknown> | null>;
  mids?: Array<[number, number] | null>;
  bboxes?: Array<[number, number, number, number] | null>;
  lines?: Array<Array<[number, number]> | null>;
}

export interface ColorOption {
  name: string;
  prop: string;
  legend: null
    | { kind: "categorical"; title: string; entries: Array<[string, string]> }
    | { kind: "continuous"; title: string; ramp: string[]; vmin: number; vmax: number };
}

/** An edge id: the road's edge_id as text (a 64-bit hash stays exact). */
export type EdgeId = string;

export interface DashboardState {
  v: 1;
  selection: EdgeId | null;
  highlight: EdgeId[];
  colorBy: string | null;
  colors: Array<{ color: string; ids: EdgeId[] }>;
  filter: { classes: string[] | null; bridges: boolean; tunnels: boolean; access: string[]; ids: EdgeId[] | null };
  overlays: Record<string, { visible: boolean; colorBy?: string }>;
  roadFill: boolean;
  tunnel: { strength: number; toward: string; palette: string; ratio: [number, number] } | null;
  palette: string | null;
  view: string | null;
  basemap: string | null;
  view3d: boolean;
  camera: { center: [number, number]; zoom: number; pitch: number; bearing: number } | null;
  streetView: { mode: "off" | "window" | "panel" };
  google3d: boolean;
  panel: boolean | null;
}

export type DashboardEvent = "state" | "select" | "deselect" | "filter" | "color" | "overlay" | "tunnel" | "view" | "view3d"
  | "basemap" | "highlight" | "roadfill" | "streetview" | "google3d" | "data";

/** The object that rsDashboard returns (the Python page sets window.rs to it). */
export interface Dashboard {
  readonly contract: number;
  /** A new roads style: add its sources and layers to the map first (with the prefix). The controls stay. more.road_table: its road table. */
  setStyle(style: StyleSpecification, more?: { road_table?: RoadTableData | null }): void;
  select(id: EdgeId | null): void;
  highlight(ids: EdgeId[]): void;
  focus(ids: EdgeId | EdgeId[]): void;
  query(where: Record<string, unknown>): EdgeId[];
  find(text: string): EdgeId[];
  props(id: EdgeId): Record<string, unknown> | null;
  setColorBy(name: string): void;
  color(groups: DashboardState["colors"] | null): void;
  setFilter(filter: Partial<DashboardState["filter"]>): void;
  setOverlay(name: string, visible: boolean): void;
  setTunnelStyle(look: Partial<NonNullable<DashboardState["tunnel"]>>): void;
  setView(name: string): void;
  setBasemap(key: string): void;
  getState(): DashboardState;
  /** A part of the state (a saved view, a URL), applied through the controls' own functions. */
  setState(change: Partial<DashboardState>): void;
  /** false when the change needs an engine that the page does not have. */
  can(change: Partial<DashboardState>): boolean;
  /** The part of the state that differs from the start, as a URL fragment ("#rs=..."). */
  link(): string;
  /** Returns the function that removes the listener. */
  on(event: DashboardEvent, fn: (detail: any) => void): () => void;
  destroy(): void;
  /** Live data (R22): join a table to the roads by edge_id (key: a column, default edge_id_col) or by the row (key "row", the table's
   *  column row), and colour (colorBy) or size (widthBy) the roads from it, with no new style. A second call replaces the values. */
  setData(table: Array<Record<string, unknown>> | { toArray(): unknown[] } | string, options?: {
    key?: string; colorBy?: string; vmin?: number; vmax?: number; ramp?: string[]; widthBy?: string; widthRange?: [number, number];
    nodata?: string | null; legend?: false | { title?: string }; stepped?: boolean;
  }): Promise<{ rows: number; matched: number; ms: number }>;
  clearData(): void;
}

/** Add roadstyle's controls and road interaction to a MapLibre map. Call it right after new maplibregl.Map(...), before "load". */
export function rsDashboard(map: MapLibreMap, options?: DashboardOptions): Dashboard;

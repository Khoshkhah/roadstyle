// The design of the map (docs/guides/design-panel.md): the style of the roads and the base map, and the values of the host's tabs.
// This file has no page code, so a test can run it (tests/test_design_panel_browser.py). A design is one plain object. It holds every value, not only the
// changes, so a design file does not depend on the look that it was made from.
//
//   style    roads (fill, casing, width factor), labels, arrows, base map (water, land, buildings, railways), 3D buildings, dark mode
//   boundary the line and the fill of the boundary of the area on the map: `design.boundary` = {show, color, width, dash, fill, fillOpacity, fillOnRoads}.
//            It is not in the look (the host paints it: the option `boundary` of the panel), so a change draws no new map.
//            Other modules (the PNG and SVG exports) read this one object. `dash` is a key of BOUNDARY_DASH.
//   opacity  `design.roads.opacity` = {fill, casing, outline}: the opacity of the road fill and of the road casing (0 to 1, a factor of the style's own), and `outline`: the
//            casing is drawn only outside the fill, so a transparent fill shows the map under it. `design.labels.halo_opacity` and `design.arrows.opacity` are the opacity of the
//            text halo and of the arrows. They are not in the look: the panel writes them into the paint of the road layers (`roadOpacity`, `roadOutline`), so a change draws no new map.
//   ground   `design.ground` = {transparent, opacity}: the ground of the map (roadstyle's layer `bg`). The alpha of the ground is `groundAlpha(design)`:
//            1 when `transparent` is off, else `opacity` (0 to 1; 0 is fully transparent). A picture export gives no background rectangle at alpha 0.
//   visible  `design.visible` = one boolean for each layer that the map can show (VISIBLE_GROUPS): the road groups, bridges, tunnels, arrows, names, the
//            3D buildings, and the base-map layers. It is the state of roadstyle's switches too (the panel calls rsSetOverlay, rsSetClasses and the others, and
//            reads roadstyle's events), so there is one state in two places. The boundary has its own `boundary.show`.
//   walls    `design.walls` = {on, front, back, side, party, court, roof, roof_dark}: the 3D walls by type (roadstyle's rsSetWallStyle, walls.js), when the
//            host gives the walls (rsSetWalls). It is not in the look: the panel paints it at once, so a change draws no new map.
//   bridges  `design.bridges` = {casing, wing, shadow, shadow_color, shadow_opacity, shadow_blur}: the casing colour of a bridge (its deck edges), a factor of the
//            width of that casing, and its shadow. They are in the look (bridges.casing_color, bridges.wing_scale, bridges.shadow).
//   tunnels  `design.tunnels` = {strength, toward, palette, ratio}: the tunnel look of roadstyle's Tunnels box (0 to 100 toward a colour, the two dash colours, the
//            dash and gap). They are in the look (tunnels.*) and in the map's global state: the panel paints them at once with rsSetTunnelStyle, and reads the
//            event rs:tunnelchange of the Tunnels box, so there is one state in two places.
//   host     the value of each host tab (`design[tab.key]`, as the tile profile of the duckOSM page): the host gives `make` and `normalize` (`hosts`)
//
// The style is written into roadstyle's look (the sections of its version 2) with `applyToLook`. The host gives that look to its map (LiveMap.setLook on the
// same tiles, else a new map), so the map and the host's exports have the same design.

export const FORMAT = "roadstyle-design";
const OLD_FORMAT = "duckosm-design";                  // the duckOSM page wrote this format before the panel was a part of roadstyle
export const VERSION = 1;

/** The road classes that have a colour of their own, in the order of the list on the page. */
export const CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "pedestrian", "cycleway", "footway", "path", "track"];
/** The width groups of roadstyle's road model (roads.model.group): a width factor is for a group. */
export const GROUPS = [
  ["major", "Motorway, trunk"], ["primary", "Primary"], ["secondary", "Secondary"], ["tertiary", "Tertiary"], ["residential", "Residential, unclassified"],
  ["living_street", "Living street"], ["service", "Service"], ["pedestrian", "Pedestrian"], ["path", "Footway, path, cycleway, track"],
];
export const GROUP_OF = { motorway: "major", trunk: "major", primary: "primary", secondary: "secondary", tertiary: "tertiary", unclassified: "residential", residential: "residential",
  living_street: "living_street", service: "service", pedestrian: "pedestrian", cycleway: "path", footway: "path", path: "path", track: "path" };
/** The land-use classes of the base map (base_map.style.areas.landcover) that one colour on the page covers. */
export const LAND = {
  green: ["forest", "wood", "grass", "grassland", "meadow", "park", "garden", "allotments", "shrubbery", "zoo", "scrub", "heath", "recreation_ground", "village_green", "nature_reserve", "golf_course", "playground", "dog_park", "flowerbed", "orchard", "vineyard"],
  built: ["default", "residential", "commercial", "retail", "industrial", "railway", "farmland", "farmyard", "garages", "greenfield", "quarry", "brownfield", "religious", "military", "prison", "construction"],
  sand: ["sand", "beach", "beach_resort"],
};
/** The dash styles of the boundary line: the pattern in multiples of the line width (MapLibre's `line-dasharray`), or null for a solid line. */
export const BOUNDARY_DASH = { solid: null, dashed: [3, 2], dotted: [1, 1.5], "dash-dot": [4, 1.5, 1, 1.5] };
/** The boundary of the page before the design card: a solid blue line of 2.5 px on a white casing, a blue fill of 0.18 that shows only before the roads are drawn. */
export const defaultBoundary = () => ({ show: true, color: "#2563eb", width: 2.5, dash: "solid", fill: "#2563eb", fillOpacity: 0.18, fillOnRoads: false });
/** The road classes of each switch of `visible` (a class with `_link` is in the group of its main class). A class that is in no group (ferry, raceway) always shows. */
export const ROAD_GROUPS = {
  motorway: ["motorway", "trunk"], primary: ["primary"], secondary: ["secondary"], tertiary: ["tertiary"],
  residential: ["unclassified", "residential", "living_street", "road", "busway"], service: ["service"],
  paths: ["pedestrian", "footway", "path", "steps", "track", "bridleway", "corridor", "platform", "construction"], cycleway: ["cycleway"],
};
export const classGroup = (c) => { const m = String(c).replace(/_link$/, ""); return Object.keys(ROAD_GROUPS).find((g) => ROAD_GROUPS[g].includes(m)) ?? null; };
/** The base-map layers (the labels of roadstyle's overlays, `rsSetOverlay(label, on)`). */
export const OVERLAY_KEYS = ["landcover", "water", "waterways", "paved", "buildings", "raceway", "other_ways", "railways", "parking", "parking_p", "platform", "traffic_signals", "crossings", "bus_stations", "train_stations", "bicycle"];
/** The switches of `design.visible`, by section, with their names on the page. */
export const VISIBLE_GROUPS = [
  ["Roads", [["motorway", "Motorway and trunk"], ["primary", "Primary"], ["secondary", "Secondary"], ["tertiary", "Tertiary"], ["residential", "Residential and below"], ["service", "Service"], ["paths", "Paths and footways"], ["cycleway", "Cycleways"]]],
  ["On the roads", [["bridges", "Bridges"], ["tunnels", "Tunnels"], ["arrows", "One-way arrows"], ["names", "Street names"]]],
  ["Base map", [["buildings", "Buildings"], ["buildings3d", "3D buildings"], ["landcover", "Land use (green and built-up)"], ["water", "Water"], ["waterways", "Waterways"], ["paved", "Paved areas"], ["railways", "Railways"], ["raceway", "Race tracks"], ["other_ways", "Other ways"], ["platform", "Platforms"], ["parking", "Parking areas"]]],
  ["Points", [["parking_p", "Parking"], ["bus_stations", "Bus stops"], ["train_stations", "Train stations"], ["bicycle", "Bicycle points"], ["traffic_signals", "Traffic signals"], ["crossings", "Crossings"]]],
];
export const VISIBLE_KEYS = VISIBLE_GROUPS.flatMap(([, rows]) => rows.map(([k]) => k));
/** The layers at the first visit: the roads, bridges, tunnels and names show; the arrows and the 3D buildings are off (the page's first visit); a base-map layer is on unless the look unticks it (railways, points). */
export function defaultVisible(look) {
  const ticked = Object.fromEntries((look?.base_map?.layers_yaml?.layers ?? []).map((l) => [l.name, l.ticked !== false]));
  return Object.fromEntries(VISIBLE_KEYS.map((k) => [k, k === "arrows" || k === "buildings3d" ? false : OVERLAY_KEYS.includes(k) ? ticked[k] ?? true : true]));
}
export const defaultRoadOpacity = () => ({ fill: 1, casing: 1, outline: false });
/** The 3D walls: off; the colours of the wall types are those of duckOSM's fixes editor, so the 2D and the 3D map agree. */
export const defaultWalls = () => ({ on: false, front: "#16a34a", back: "#dc2626", side: "#6b7280", party: "#7c3aed", court: "#0891b2", roof: "#a8a29e", roof_dark: "#57534e" });
export const WALL_KEYS = ["front", "back", "side", "party", "court", "roof", "roof_dark"];
export const defaultGround = () => ({ transparent: false, opacity: 0 });
/** The alpha of the ground of the map (roadstyle's layer `bg`): 1, or the opacity when the ground is transparent. */
export const groundAlpha = (d) => (d.ground.transparent ? d.ground.opacity : 1);

const clone = (x) => JSON.parse(JSON.stringify(x));
const num = (v, d) => (Number.isFinite(+v) && v !== null && v !== "" ? +v : d);
const clamp = (v, [lo, hi]) => Math.min(hi, Math.max(lo, v));
const COLOR = /^#[0-9a-f]{6}$/i;
const hex = (v, d) => (typeof v === "string" && COLOR.test(v) ? v.toLowerCase() : d);
/** The alpha of a colour that the look holds ("rgba(0,0,0,0.25)" gives 0.25; a colour with no alpha gives 1), or `d` when it is not a colour. */
export function alphaOf(c, d) {
  if (typeof c !== "string") return d;
  const r = /^rgba\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*,\s*([\d.]+)\s*\)$/.exec(c);
  return r ? clamp(+r[1], [0, 1]) : toHex(c) ? 1 : d;
}
/** A colour that the look holds (hex, short hex, or rgba) as #rrggbb; the page's colour input takes only this form. */
export function toHex(c) {
  if (typeof c !== "string") return null;
  if (COLOR.test(c)) return c.toLowerCase();
  const s = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(c);
  if (s) return `#${s[1]}${s[1]}${s[2]}${s[2]}${s[3]}${s[3]}`.toLowerCase();
  const r = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/.exec(c);
  return r ? "#" + [r[1], r[2], r[3]].map((x) => (+x).toString(16).padStart(2, "0")).join("") : null;
}

// ---- the style: read from a look, written into a look ----

/** The design that a look (a version 2 look, as an object) has now. `hosts` = [{key, make}]: the host tabs, each with its start value. */
export function defaultsOf(look, hosts = []) {
  const bm = look.base_map?.style ?? {};                    // a look of roads alone has no base map: its colours are the defaults below, and applyToLook writes none
  const cls = look.roads.styles.classes, w = look.roads.model.width, areas = bm.areas ?? {}, lc = areas.landcover ?? {}, b3 = bm.buildings_3d;
  const first = (list) => toHex(lc[list.find((k) => lc[k])]) ?? "#e2ebd6";
  const br = look.bridges ?? {}, tu = look.tunnels ?? {};
  const d = {
    format: FORMAT, version: VERSION, name: "Light", theme: "light",
    roads: {
      fill: Object.fromEntries(CLASSES.map((c) => [c, toHex(cls[c]?.[0]?.fill) ?? "#ffffff"])),
      casing: Object.fromEntries(CLASSES.map((c) => [c, toHex(cls[c]?.[0]?.casing) ?? toHex(cls[c]?.[0]?.fill) ?? "#bbbbbb"])),
      width: Object.fromEntries(GROUPS.map(([g]) => [g, 1])),
      opacity: defaultRoadOpacity(),
    },
    labels: { color: toHex(look.labels.color) ?? "#5b5b5b", halo_color: toHex(look.labels.halo_color) ?? "#ffffff", halo_width: num(look.labels.halo_width, 0), halo_opacity: 1, minzoom: num(look.labels.minzoom, 14), size: 1 },
    arrows: { color: toHex(look.arrows.color) ?? "#5b5b5b", opacity: num(look.arrows.opacity, 0.7), minzoom: num(look.arrows.minzoom, 15), size: 1 },
    base: {
      background: toHex(look.background.light) ?? "#e8e6e1", water: toHex(areas.water?.fill) ?? "#9ebdff", green: first(LAND.green), land: first(LAND.built), sand: first(LAND.sand),
      buildings: toHex(areas.buildings?.fill) ?? "#e5e2df", buildingLine: toHex(areas.buildings?.outline) ?? "#cdcac6",
      railways: toHex(bm.lines?.railways?.color) ?? "#bbbbbb", waterways: toHex(bm.lines?.waterways?.color) ?? "#a0c8f0",
      m_per_level: num(b3?.m_per_level, 3.66), max_height: num(b3?.max_height, 200), height_opacity: num(b3?.opacity, 0.9),
    },
    bridges: { casing: toHex(br.casing_color) ?? "#64748b", wing: 1, shadow: br.shadow?.show !== false, shadow_color: toHex(br.shadow?.color) ?? "#000000",
               shadow_opacity: alphaOf(br.shadow?.color, 0.25), shadow_blur: num(br.shadow?.blur, 4) },
    tunnels: { strength: num(tu.strength, 60), toward: typeof tu.toward === "string" ? tu.toward : "Sand", palette: typeof tu.palette === "string" ? tu.palette : "One colour",
               ratio: tu.casing_dash?.length === 2 ? tu.casing_dash.map(Number) : [1, 1] },
    boundary: defaultBoundary(), ground: defaultGround(), visible: defaultVisible(look), walls: defaultWalls(),
    dark: { roads: [...look.dark.line.lightness], casing: [...look.dark.casing.lightness], areas: [...look.dark.area.lightness], labels: [...look.dark.label.lightness], background: toHex(look.background.dark) ?? "#0e1113" },
  };
  for (const h of hosts) d[h.key] = h.make();
  return d;
}

/** A design with every field right: the missing ones come from `base` (a design), the wrong ones are dropped. `hosts` = [{key, normalize}]: a host value of `d`, completed by the host. */
export function normalize(d, base, hosts = []) {
  const out = clone(base);
  if (!d || typeof d !== "object") return out;
  if (typeof d.name === "string" && d.name.trim()) out.name = d.name.trim().slice(0, 60);
  if (typeof d.theme === "string") out.theme = d.theme.slice(0, 30);
  for (const k of ["fill", "casing"]) for (const c of CLASSES) out.roads[k][c] = hex(d.roads?.[k]?.[c], out.roads[k][c]);
  for (const [g] of GROUPS) out.roads.width[g] = clamp(num(d.roads?.width?.[g], 1), [0.2, 4]);
  const ro = d.roads?.opacity ?? {};
  out.roads.opacity = { fill: clamp(num(ro.fill, out.roads.opacity.fill), [0, 1]), casing: clamp(num(ro.casing, out.roads.opacity.casing), [0, 1]), outline: !!(ro.outline ?? out.roads.opacity.outline) };
  const l = d.labels ?? {};
  Object.assign(out.labels, { color: hex(l.color, out.labels.color), halo_color: hex(l.halo_color, out.labels.halo_color), halo_width: clamp(num(l.halo_width, out.labels.halo_width), [0, 4]), halo_opacity: clamp(num(l.halo_opacity, out.labels.halo_opacity), [0, 1]),
    minzoom: clamp(Math.round(num(l.minzoom, out.labels.minzoom)), [0, 20]), size: clamp(num(l.size, 1), [0.5, 2]) });
  const a = d.arrows ?? {};
  Object.assign(out.arrows, { opacity: clamp(num(a.opacity, out.arrows.opacity), [0, 1]), color: hex(a.color, out.arrows.color), minzoom: clamp(Math.round(num(a.minzoom, out.arrows.minzoom)), [0, 20]), size: clamp(num(a.size, 1), [0.5, 3]) });
  const b = d.base ?? {};
  for (const k of ["background", "water", "green", "land", "sand", "buildings", "buildingLine", "railways", "waterways"]) out.base[k] = hex(b[k], out.base[k]);
  Object.assign(out.base, { m_per_level: clamp(num(b.m_per_level, out.base.m_per_level), [1, 10]), max_height: clamp(num(b.max_height, out.base.max_height), [10, 500]),
    height_opacity: clamp(num(b.height_opacity, out.base.height_opacity), [0.1, 1]) });
  for (const k of ["roads", "casing", "areas", "labels"]) {
    const r = d.dark?.[k];
    if (Array.isArray(r) && r.length === 2 && r.every((x) => Number.isFinite(+x))) out.dark[k] = [clamp(+r[0], [0, 1]), clamp(+r[1], [0, 1])];
  }
  out.dark.background = hex(d.dark?.background, out.dark.background);
  const br = d.bridges ?? {}, ob = out.bridges;
  Object.assign(ob, { casing: hex(br.casing, ob.casing), wing: clamp(num(br.wing, ob.wing), [0.5, 3]), shadow: !!(br.shadow ?? ob.shadow), shadow_color: hex(br.shadow_color, ob.shadow_color),
    shadow_opacity: clamp(num(br.shadow_opacity, ob.shadow_opacity), [0, 1]), shadow_blur: clamp(num(br.shadow_blur, ob.shadow_blur), [0, 12]) });
  const tu = d.tunnels ?? {}, ot = out.tunnels, name = (v, dv) => (typeof v === "string" && v.trim() && v.length <= 40 ? v.trim() : dv);
  const ratio = typeof tu.ratio === "string" ? tu.ratio.split(":").map(Number) : tu.ratio;
  Object.assign(ot, { strength: clamp(num(tu.strength, ot.strength), [0, 100]), toward: name(tu.toward, ot.toward), palette: name(tu.palette, ot.palette),
    ratio: Array.isArray(ratio) && ratio.length === 2 && ratio.every((x) => Number.isFinite(+x) && +x > 0 && +x <= 10) ? ratio.map(Number) : ot.ratio });
  const bd = d.boundary ?? {};
  out.boundary = {
    show: bd.show ?? out.boundary.show, color: hex(bd.color, out.boundary.color), width: clamp(num(bd.width, out.boundary.width), [0.5, 8]),
    dash: Object.hasOwn(BOUNDARY_DASH, bd.dash) ? bd.dash : out.boundary.dash, fill: hex(bd.fill, out.boundary.fill),
    fillOpacity: clamp(num(bd.fillOpacity, out.boundary.fillOpacity), [0, 1]), fillOnRoads: bd.fillOnRoads ?? out.boundary.fillOnRoads,
  };
  out.boundary.show = !!out.boundary.show; out.boundary.fillOnRoads = !!out.boundary.fillOnRoads;
  out.ground = { transparent: !!(d.ground?.transparent ?? out.ground.transparent), opacity: clamp(num(d.ground?.opacity, out.ground.opacity), [0, 1]) };
  out.walls = { on: !!(d.walls?.on ?? out.walls.on), ...Object.fromEntries(WALL_KEYS.map((k) => [k, hex(d.walls?.[k], out.walls[k])])) };
  out.visible = Object.fromEntries(VISIBLE_KEYS.map((k) => [k, typeof d.visible?.[k] === "boolean" ? d.visible[k] : out.visible[k]]));
  for (const h of hosts) out[h.key] = h.normalize(d[h.key] ?? out[h.key]);
  return out;
}

const scaleStops = (stops, f) => Object.fromEntries(Object.entries(stops).map(([z, v]) => [z, +(v * f).toFixed(3)]));

/**
 * The look (a version 2 look as an object) with the design written into it. The look is not changed: the result is a copy. The paths are those
 * that the engine reads: roads.styles.classes (the colours of a class, and of its link), roads.model.width (the width curve of a group),
 * labels, arrows, base_map.style (the base-map layers), dark and background. A host value is not in the look.
 */
export function applyToLook(look, d) {
  const L = clone(look), base = defaultsOf(look);
  d = normalize(d, base);
  const diff = (a, b) => JSON.stringify(a) !== JSON.stringify(b);       // a value that the design did not change keeps what the look has (a group colour covers classes that differ)
  for (const c of CLASSES) {
    const g = GROUP_OF[c], f = d.roads.width[g] / base.roads.width[g];
    for (const s of L.roads.styles.classes[c] ?? []) {
      if (diff(d.roads.fill[c], base.roads.fill[c])) s.fill = d.roads.fill[c];
      if (s.casing != null && diff(d.roads.casing[c], base.roads.casing[c])) s.casing = d.roads.casing[c];
      if (f !== 1) for (const k of ["width", "casing_width"]) if (s[k] != null) s[k] = +(s[k] * f).toFixed(3);
    }
  }
  for (const [g] of GROUPS) {
    const f = d.roads.width[g] / base.roads.width[g];
    if (f !== 1 && L.roads.model.width[g]) L.roads.model.width[g] = scaleStops(L.roads.model.width[g], f);
    if (f !== 1 && L.roads.width?.[g]) L.roads.width[g] = scaleStops(L.roads.width[g], f);
  }
  const lb = L.labels, lo = look.labels, la = d.labels, ba = base.labels;
  for (const k of ["color", "halo_color", "halo_width"]) if (diff(la[k], ba[k])) lb[k] = la[k];
  if (la.minzoom !== ba.minzoom) { lb.minor_minzoom = (lo.minor_minzoom ?? 16) + (la.minzoom - ba.minzoom); lb.minzoom = la.minzoom; }
  if (la.size !== 1) lb.base_size = lo.base_size.map(([z, s]) => [z, +(s * la.size).toFixed(2)]);
  const ar = L.arrows, ao = look.arrows, aa = d.arrows;
  if (diff(aa.color, base.arrows.color)) ar.color = aa.color;
  if (aa.minzoom !== base.arrows.minzoom) { ar.minor_minzoom = (ao.minor_minzoom ?? 16) + (aa.minzoom - base.arrows.minzoom); ar.minzoom = aa.minzoom; }
  if (aa.size !== 1) { ar.size.base = +(ao.size.base * aa.size).toFixed(3); ar.size.stops = ao.size.stops.map(([z, s]) => [z, +(s * aa.size).toFixed(3)]); }
  const st = L.base_map?.style ?? { areas: {} }, lc = st.areas.landcover ?? {}, bs = d.base, b0 = base.base;
  if (diff(bs.water, b0.water)) for (const k of ["ocean", "water"]) if (st.areas[k]) st.areas[k].fill = bs.water;
  for (const [key, list] of Object.entries(LAND)) {
    const name = key === "built" ? "land" : key;
    if (diff(bs[name], b0[name])) for (const k of list) if (k in lc) lc[k] = bs[name];
  }
  if (st.areas.buildings) for (const [k, to] of [["buildings", "fill"], ["buildingLine", "outline"]]) if (diff(bs[k], b0[k])) st.areas.buildings[to] = bs[k];
  if (st.lines?.railways && diff(bs.railways, b0.railways)) st.lines.railways.color = bs.railways;
  if (st.lines?.waterways && diff(bs.waterways, b0.waterways)) st.lines.waterways.color = bs.waterways;
  for (const o of [st.buildings_3d, L.base_map?.buildings_3d, st.areas.buildings_3d].filter(Boolean)) {
    for (const [k, to] of [["m_per_level", "m_per_level"], ["max_height", "max_height"], ["height_opacity", "opacity"]]) if (diff(bs[k], b0[k])) o[to] = bs[k];
  }
  if (diff(bs.background, b0.background)) L.background.light = bs.background;
  if (diff(d.dark.background, base.dark.background)) L.background.dark = d.dark.background;
  for (const [k, to] of [["roads", "line"], ["casing", "casing"], ["areas", "area"], ["labels", "label"]]) if (diff(d.dark[k], base.dark[k])) L.dark[to].lightness = d.dark[k];
  const bd = d.bridges, b1 = base.bridges, LB = L.bridges;
  if (LB) {
    if (diff(bd.casing, b1.casing)) LB.casing_color = bd.casing;
    if (bd.wing !== b1.wing) LB.wing_scale = +(look.bridges.wing_scale * bd.wing).toFixed(3);
    if (LB.shadow) {
      if (bd.shadow !== b1.shadow) LB.shadow.show = bd.shadow;
      if (diff(bd.shadow_color, b1.shadow_color) || bd.shadow_opacity !== b1.shadow_opacity) LB.shadow.color = withAlpha(bd.shadow_color, bd.shadow_opacity);
      if (bd.shadow_blur !== b1.shadow_blur) LB.shadow.blur = bd.shadow_blur;
    }
  }
  const td = d.tunnels, t1 = base.tunnels, LT = L.tunnels;
  if (LT) {
    for (const k of ["strength", "toward", "palette"]) if (diff(td[k], t1[k])) LT[k] = td[k];
    if (diff(td.ratio, t1.ratio)) LT.casing_dash = td.ratio;
  }
  return L;
}

// ---- the opacity of the roads: expressions for the paint of roadstyle's road layers ----
// roadstyle's road layer draws the casing (`__rs_k` 0) and the fill (`__rs_k` 1) of a road as two features with one `line-opacity` (0 or 1: its zoom stops hold the cases) and one
// `line-width` (a `let` of the row of the width table, then an `interpolate` of the zoom). The functions give new expressions from the originals and keep the zoom at the top.
const KIND = ["get", "__rs_k"];
const subst = (x, from, to) => (JSON.stringify(x) === JSON.stringify(from) ? to : Array.isArray(x) ? x.map((e) => subst(e, from, to)) : x);
const atStops = (expr, f) => [...expr.slice(0, 3), ...expr.slice(3).map((v, i) => (i % 2 === 1 ? f(v) : v))];          // an interpolate: [name, curve, input, stop, output, stop, output, ...]
const byZoom = (e) => Array.isArray(e) && e[0] === "interpolate" && JSON.stringify(e[2]) === '["zoom"]';
/** The `line-opacity` of the original with the fill and the casing at the factors `fill` and `casing` (the other kinds of piece stay as they are). */
export function roadOpacity(orig, fill, casing) {
  const f = ["case", ["==", KIND, 0], casing, ["==", KIND, 1], fill, 1];
  return byZoom(orig) ? atStops(orig, (o) => ["*", o, f]) : ["*", orig ?? 1, f];
}
/**
 * The paint of a casing that is drawn only outside the fill, from the original `line-width`: {width, gap} for `line-width` and `line-gap-width`. The casing piece gets the gap
 * of the fill width and a width of half the difference. Gives null when the original has not the shape that roadstyle makes now (then the casing stays under the fill).
 */
export function roadOutline(width) {
  if (!(Array.isArray(width) && width[0] === "let" && width.length === 4 && width[1] === "row" && byZoom(width[3]))) return null;
  const [, , rows, zoom] = width;
  const fillRows = subst(rows, KIND, 1), fillOf = (o) => subst(o, ["var", "row"], ["var", "row1"]);          // the same piece, as the fill: its width
  const make = (f) => ["let", "row", rows, "row1", fillRows, atStops(zoom, f)];
  return {
    width: make((o) => ["case", ["==", KIND, 0], ["max", 0, ["/", ["-", o, fillOf(o)], 2]], o]),
    gap: make((o) => ["case", ["==", KIND, 0], fillOf(o), 0]),
  };
}
/** The CSS color of a hex color with an alpha. */
export const withAlpha = (hexColor, a) => `rgba(${[1, 3, 5].map((i) => parseInt(hexColor.slice(i, i + 2), 16)).join(",")},${+a.toFixed(3)})`;

// ---- the ready themes ----
// A theme is one plain object (data, no code), in themes.json beside this file: a colour is a style value, so it is in a data file. It sets every style value: the fill
// and the casing of the road classes, the width of the groups, the text, the arrows, the boundary and the colors of the base map. In a map of classes (`fill`, `casing`,
// `width`) the key "*" is the value of every class that is not named. The Light theme has `look: true`: it is the design of the look itself. A theme keeps the host's
// values (a host tab, as the tile profile of the duckOSM page) and the dark ranges of the page.
// `group` and `dark` are for the filter of the theme list: group is "light", "dark", "print", "overlay" or "roadstyle"; `dark: true` is a dark ground. A theme with
// `roadsOnly: true` (a road palette) sets only the road colors and keeps the other values of the design that is on now.

const expand = (map, keys, now) => Object.fromEntries(keys.map((k) => [k, map[k] ?? map["*"] ?? now[k]]));
/**
 * The design of a theme (an object of themes.json) on top of `b`, the design of the look: it has every style value, and keeps the host values and the dark ranges of `b`.
 * A theme with `roadsOnly` (a road palette) changes only the road colors of `now`, the design that is on now (`b` when none): the base map stays. It draws the
 * roads with the full fill and casing (defaultRoadOpacity), because a palette on Roads hollow (fill 0) would change colors that do not show.
 */
export function makeTheme(b, t, now = b) {
  const d = clone(t.roadsOnly ? now : b);
  d.name = t.name; d.theme = t.id; d.walls = clone(now.walls ?? d.walls);          // a theme keeps the walls of the design that is on now
  if (t.look) return d;
  d.roads = { fill: expand(t.roads.fill, CLASSES, d.roads.fill), casing: expand(t.roads.casing, CLASSES, d.roads.casing), width: t.roads.width ? expand(t.roads.width, GROUPS.map(([g]) => g), d.roads.width) : d.roads.width,
    opacity: { ...defaultRoadOpacity(), ...t.roads.opacity } };
  if (t.roadsOnly) return d;
  Object.assign(d.labels, t.labels); Object.assign(d.arrows, t.arrows); Object.assign(d.boundary, t.boundary); Object.assign(d.base, t.base);
  Object.assign(d.ground, t.ground); Object.assign(d.visible, t.visible);          // a theme names the layers that it hides (visible: false) and the ground that it makes transparent
  return d;
}
/** The kinds of the ready themes, in the order of the theme list: what a theme changes when you pick it. */
export const THEME_KINDS = [
  ["map", "Whole map", "These set the roads, the base map, the text and the layers."],
  ["overlay", "Roads on any map", "These set the roads and hide the base map: the map under the roads shows through."],
  ["palette", "Road colors", "These change only the road colors. The base map, the text and the layers of the design that is on now stay."],
];
/** The kind of a ready theme (a key of THEME_KINDS). */
export const themeKind = (t) => (t.roadsOnly ? "palette" : t.group === "overlay" ? "overlay" : "map");
/** The filters of the theme list (the buttons above it). "yours" shows the themes that the person saved, and none of the ready themes. */
export const THEME_FILTERS = [["all", "All"], ["light", "Light"], ["dark", "Dark"], ["overlay", "Overlay"], ["print", "Print"], ["roads", "Roads only"], ["roadstyle", "roadstyle"], ["yours", "Yours"]];
/** Whether a ready theme (an object of themes.json, or of themesOf) is in a filter and has the words of a search (all the words are in its name, its note or its group). */
export function themeMatches(t, filter = "all", query = "") {
  const ok = { all: true, light: !t.dark && t.group !== "overlay", dark: !!t.dark, overlay: t.group === "overlay", print: t.group === "print", roads: !!t.roadsOnly || t.group === "overlay", roadstyle: t.group === "roadstyle", yours: false }[filter];
  const text = `${t.name} ${t.note} ${t.group}`.toLowerCase();
  return !!ok && String(query).toLowerCase().split(/\s+/).filter(Boolean).every((w) => text.includes(w));
}
/** The ready themes of `data` (the list of themes.json), for the panel: `make(base, now)` gives the design of a theme. */
export const themesOf = (data) => data.map((t) => ({ id: t.id, name: t.name, note: t.note, group: t.group, dark: t.dark, roadsOnly: !!t.roadsOnly, make: (b, now) => makeTheme(b, t, now) }));

// ---- the design file ----

/** The text of a design file. */
export const toFile = (d) => JSON.stringify({ ...d, format: FORMAT, version: VERSION }, null, 2);
/** A design from the text of a file, on top of `base`. An error is thrown with a message for the person. */
export function fromFile(text, base, hosts = []) {
  let o;
  try { o = JSON.parse(text); } catch (e) { throw new Error("the file is not JSON"); }
  if (o?.format !== FORMAT && o?.format !== OLD_FORMAT) throw new Error("the file is not a design file");
  if (!(o.version <= VERSION)) throw new Error(`the file has version ${o.version}; this page reads version ${VERSION} and lower`);
  return normalize(o, base, hosts);
}
/** The differences between a design and its base, as a list of paths (for the count on the tab). */
export function changes(d, base) {
  const out = [];
  const walk = (a, b, p) => {
    if (a && typeof a === "object") for (const k of Object.keys(a)) walk(a[k], b?.[k], p ? `${p}.${k}` : k);
    else if (JSON.stringify(a) !== JSON.stringify(b)) out.push(p);
  };
  walk(d, base, "");
  return out;
}

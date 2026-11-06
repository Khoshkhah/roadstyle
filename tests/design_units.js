// The checks of the design model (dashboard/design/design.js and user_themes.js), in a browser: tests/test_design_panel_browser.py serves this file next to the
// dashboard and gives it the look (a version 2 look, as the duckOSM page has it). `run(look, themes)` gives {failures, looks}: `looks` are the looks of the
// ready themes, for Python to read with roadstyle's Look.from_json. The checks came from duckosm-rust's design_units.mjs (without the tile profile).
import * as D from "./dashboard/design/design.js";
import * as UT from "./dashboard/design/user_themes.js";

export function run(look, data) {
  const failures = [];
  const key = (v) => JSON.stringify(v, (k, x) => (x && typeof x === "object" && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => (a < b ? -1 : 1))) : x));
  const ok = (c, m = "") => { if (!c) failures.push("not true: " + m); };
  const eq = (a, b, m = "") => { if (key(a) !== key(b)) failures.push(`${m}: ${key(a)} is not ${key(b)}`); };
  const throws = (f, re) => { try { f(); failures.push("no error: " + re); } catch (e) { if (!re.test(e.message)) failures.push(`error "${e.message}" is not ${re}`); } };
  const THEME_DATA = data.themes, THEMES = D.themesOf(THEME_DATA);
  const host = { key: "profile", make: () => ({ zoom: 14 }), normalize: (p) => ({ zoom: Math.min(18, Math.max(0, +p?.zoom || 14)) }) };
  const base = D.defaultsOf(look), hbase = D.defaultsOf(look, [host]);

  ok(JSON.stringify(D.applyToLook(look, base)) === JSON.stringify(look), "the default design changes nothing in the look");
  // the 3D walls: off with the fixes editor's colours; a bad colour keeps the default; not in the look; a theme keeps them
  eq(base.walls, D.defaultWalls(), "the walls at the start");
  const walls = D.normalize({ ...base, walls: { on: true, front: "#112233", back: "red" } }, base).walls;
  eq([walls.on, walls.front, walls.back], [true, "#112233", base.walls.back], "the walls normalized");
  ok(JSON.stringify(D.applyToLook(look, { ...base, walls })) === JSON.stringify(look), "the walls are not in the look");
  eq(THEMES.find((t) => !t.look).make(base, { ...base, walls }).walls, walls, "a theme keeps the walls");
  eq(D.changes(base, base), []);
  const looks = {};
  for (const t of THEMES) {
    const d = t.make(base), L = D.applyToLook(look, d);
    looks[t.id] = JSON.stringify(L);
    eq(L.roads.styles.classes.motorway[0].fill, d.roads.fill.motorway, `${t.id}: motorway fill`);
    eq(L.roads.styles.classes.motorway[1].fill, d.roads.fill.motorway, `${t.id}: the link has the colour of its class`);
    eq(L.base_map.style.areas.water.fill, d.base.water, `${t.id}: water`);
    eq(L.labels.color, d.labels.color, `${t.id}: labels`);
    if (t.id !== "light") ok(D.changes(d, base).length > 10, `${t.id}: the theme changes the design`);
  }
  // the boundary: the duckOSM page's blue line is the default; each theme, the file and a repair keep it in range
  eq(base.boundary, D.defaultBoundary());
  eq(base.boundary, { show: true, color: "#2563eb", width: 2.5, dash: "solid", fill: "#2563eb", fillOpacity: 0.18, fillOnRoads: false });
  for (const t of THEMES) { const d = t.make(base); eq(D.normalize(d, base).boundary, d.boundary, `${t.id}: the boundary is in range`); }
  eq(THEMES.find((t) => t.id === "print").make(base).boundary.color, "#000000");
  const bb = D.normalize({ boundary: { show: 0, color: "blue", width: 99, dash: "wavy", fill: "#ABCDEF", fillOpacity: -1, fillOnRoads: 1 } }, base).boundary;
  eq(bb, { show: false, color: "#2563eb", width: 8, dash: "solid", fill: "#abcdef", fillOpacity: 0, fillOnRoads: true });
  ok(JSON.stringify(D.applyToLook(look, { ...base, boundary: { ...base.boundary, color: "#000000", show: false } })) === JSON.stringify(look), "the boundary is not in the look");
  eq(Object.keys(D.BOUNDARY_DASH), ["solid", "dashed", "dotted", "dash-dot"]);

  // the themes are data: one plain object each, with every style value; the roads differ from theme to theme
  ok(THEME_DATA.length >= 13 && new Set(THEME_DATA.map((t) => t.id)).size === THEME_DATA.length, "ids are unique");
  const sig = new Set();
  for (const t of THEME_DATA) {
    if (!t.look) {
      ok(["light", "dark", "print", "overlay", "roadstyle"].includes(t.group) && typeof t.dark === "boolean", `${t.id}: group and dark`);
      for (const k of ["fill", "casing"]) ok(t.roadsOnly || t.roads[k]["*"], `${t.id}: roads.${k} has the key *`);
      if (t.roadsOnly) ok(!t.base && !t.labels && D.CLASSES.filter((c) => t.roads.fill[c] && t.roads.casing[c]).length >= 10, `${t.id}: a road palette names its classes and has no base map`);
    }
    if (!t.look && !t.roadsOnly) {
      ok(t.roads.width["*"] || D.GROUPS.every(([g]) => t.roads.width[g]), `${t.id}: width`);
      for (const k of ["color", "halo_color", "halo_width"]) ok(k in t.labels, `${t.id}: labels.${k}`);
      ok(t.arrows.color, `${t.id}: arrows.color`);
      for (const k of ["color", "width", "dash", "fill", "fillOpacity"]) ok(k in t.boundary, `${t.id}: boundary.${k}`);
      for (const k of Object.keys(base.base).filter((x) => !["m_per_level", "max_height", "height_opacity"].includes(x))) ok(t.base[k], `${t.id}: base.${k}`);
    }
    const d = D.makeTheme(hbase, t);
    ok(D.normalize(d, base).roads.fill.primary === d.roads.fill.primary, `${t.id}: the colors are valid`);
    eq(d.profile, hbase.profile, `${t.id} keeps the host value`);
    sig.add(JSON.stringify(d.roads));
  }
  eq(sig.size, THEME_DATA.length, "every theme has its own road colors");
  // a road palette keeps the base map and the other values of the design that is on now; a base-map theme sets them
  const T = (id, now) => D.makeTheme(base, THEME_DATA.find((t) => t.id === id), now);
  const nightD = T("night"), amberOnNight = T("amber", nightD);
  eq(amberOnNight.base, nightD.base); eq(amberOnNight.labels, nightD.labels);
  eq(amberOnNight.roads.fill.motorway, "#f28c28"); eq(amberOnNight.roads.fill.pedestrian, nightD.roads.fill.pedestrian, "a class that the palette lacks keeps its color");
  eq(T("google", nightD).base.background, "#f5f4f1");
  // a road palette draws the full fill: on Roads hollow (fill 0) its colors show
  const hollowD = T("hollow"), highsatOnHollow = T("highsat", hollowD);
  eq(highsatOnHollow.roads.opacity, D.defaultRoadOpacity()); eq(highsatOnHollow.base, hollowD.base);
  // each ready theme has one kind; the kinds are in the list's order
  eq(D.THEME_KINDS.map(([k]) => k), ["map", "overlay", "palette"]);
  eq(THEME_DATA.filter((t) => D.themeKind(t) === "palette").map((t) => t.id), ["amber", "cartoroads", "highsat", "monoroads"]);
  eq(THEME_DATA.filter((t) => D.themeKind(t) === "overlay").map((t) => t.id), ["overlay", "overlaydark", "hollow", "ghost"]);
  eq(THEME_DATA.filter((t) => t.group === "roadstyle").map((t) => t.id), ["google", "grey", "roadstyle", "osmcarto", "amber", "cartoroads", "highsat", "monoroads"]);
  eq(THEME_DATA.slice(0, 2).map((t) => t.id), ["light", "dark"], "Light and Dark are the first");
  // the ground and the layers
  eq(base.ground, { transparent: false, opacity: 0 }); eq(D.groundAlpha(base), 1);
  eq(D.groundAlpha({ ground: { transparent: true, opacity: 0.3 } }), 0.3);
  eq(base.visible.arrows, false); eq(base.visible.railways, false); eq(base.visible.buildings, true); eq(base.visible.motorway, true);
  eq(Object.keys(base.visible), D.VISIBLE_KEYS);
  eq(D.classGroup("motorway_link"), "motorway"); eq(D.classGroup("ferry"), null); eq(D.classGroup("footway"), "paths");
  const ov = T("overlay");
  eq(ov.ground.transparent, true); eq(D.groundAlpha(ov), 0);
  ok(D.OVERLAY_KEYS.every((k) => ov.visible[k] === false) && ov.visible.names === true && ov.visible.primary === true && ov.visible.buildings3d === false, "the overlay hides every base-map layer and keeps the roads and the names");
  eq(D.normalize({ visible: { water: "no", buildings: false } }, base).visible.water, true);
  eq(D.normalize({ visible: { buildings: false } }, base).visible.buildings, false);
  eq(D.normalize({ ground: { transparent: 1, opacity: 7 } }, base).ground, { transparent: true, opacity: 1 });
  ok(JSON.stringify(D.applyToLook(look, { ...base, ground: { transparent: true, opacity: 0 }, visible: { ...base.visible, water: false } })) === JSON.stringify(look), "the ground and the layers are not in the look");

  // a width factor scales the curve of its group only
  const w = structuredClone(base); w.roads.width.major = 2;
  const W = D.applyToLook(look, w);
  eq(W.roads.model.width.major["14"], look.roads.model.width.major["14"] * 2, "major width");
  eq(W.roads.model.width.primary["14"], look.roads.model.width.primary["14"], "primary width");
  // labels and arrows
  const x = structuredClone(base); x.labels.size = 2; x.labels.minzoom = 12; x.arrows.minzoom = 13; x.base.m_per_level = 5;
  const X = D.applyToLook(look, x);
  eq(X.labels.base_size[0][1], look.labels.base_size[0][1] * 2, "label size");
  eq(X.labels.minzoom, 12); eq(X.labels.minor_minzoom, 14); eq(X.arrows.minor_minzoom, 14);
  eq(X.base_map.style.buildings_3d.m_per_level, 5);
  // a design with wrong values is repaired, not thrown away; a host value goes through the host's normalize
  const bad = D.normalize({ name: "  ", roads: { fill: { motorway: "red", trunk: "#ABCDEF" }, width: { major: 99 } }, profile: { zoom: 30 } }, hbase, [host]);
  eq(bad.name, "Light"); eq(bad.roads.fill.motorway, base.roads.fill.motorway); eq(bad.roads.fill.trunk, "#abcdef");
  eq(bad.roads.width.major, 4); eq(bad.profile, { zoom: 18 }, "the host value is in range");
  eq(D.normalize({}, base).profile, undefined, "no host tab: no host value");
  ok(JSON.stringify(D.applyToLook(look, hbase)) === JSON.stringify(look), "a host value is not in the look");
  // the file, and the old file of the duckOSM page
  const back = D.fromFile(D.toFile(THEMES[1].make(base)), base);
  eq(back, D.normalize(THEMES[1].make(base), base), "the file");
  eq(JSON.parse(D.toFile(base)).format, "roadstyle-design");
  eq(D.fromFile(JSON.stringify({ ...THEMES[1].make(hbase), format: "duckosm-design", version: 1, profile: { zoom: 9 } }), hbase, [host]).profile, { zoom: 9 }, "an old duckOSM design file");
  throws(() => D.fromFile("{}", base), /not a design file/);
  throws(() => D.fromFile("x", base), /not JSON/);
  throws(() => D.fromFile(JSON.stringify({ format: D.FORMAT, version: 9 }), base), /version 9/);

  // the themes that a person saves (user_themes.js): a fake storage, a list in it
  const mem = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), m }; };
  const st = mem();
  eq(UT.readAll(st), []);
  let mine = UT.put([], "My print", THEMES.find((t) => t.id === "print").make(hbase));
  eq(mine.length, 1); eq(mine[0].id, "my-print"); eq(mine[0].design.profile, undefined, "no host value unless asked"); eq(mine[0].design.name, "My print");
  ok(UT.writeAll(mine, st)); eq(UT.readAll(st), mine, "the list is read back");
  ok(UT.writeAll(mine, st, "page.themes") && st.m.has("page.themes") && UT.readAll(st, "page.themes").length === 1, "a storage key of the page");
  mine = UT.put(mine, "my PRINT", hbase, true);                                            // the same name (any case) replaces: one theme, the same id, the host value now kept
  eq(mine.length, 1); eq(mine[0].id, "my-print"); eq(mine[0].keepProfile, true); ok(mine[0].design.profile, "the host value is kept");
  eq(UT.put([], "X", { ...hbase, tiles: 1 }, false, ["tiles"])[0].design.tiles, undefined, "the host keys of the page");
  mine = UT.put(mine, "Night 2", base);
  eq(mine.map((t) => t.id), ["my-print", "night-2"]);
  eq(UT.put(mine, "Night!", base).find((t) => t.name === "Night!").id, "night", "an id is a slug of the name");
  eq(UT.put(UT.put([], "A b", base), "A-b", base).map((t) => t.id).join(), "a-b,a-b-2", "two names with one slug have two ids");
  throws(() => UT.put(mine, "  ", base), /Give the theme a name/); throws(() => UT.put(mine, "x".repeat(41), base), /at most 40/);
  eq(UT.rename(mine, "night-2", "Evening").find((t) => t.id === "night-2").design.name, "Evening");
  throws(() => UT.rename(mine, "night-2", "my print"), /exists/);
  eq(UT.remove(mine, "my-print").map((t) => t.id), ["night-2"]);
  eq(UT.readAll({ getItem: () => "{bad" }), []); eq(UT.writeAll(mine, { setItem() { throw new Error("full"); } }), false);
  const file = UT.toFile(mine);
  eq(UT.fromFile(file), mine, "the themes file");
  eq(JSON.parse(file).format, "roadstyle-themes");
  eq(UT.fromFile(JSON.stringify({ format: "duckosm-themes", version: 1, themes: mine })), mine, "an old duckOSM themes file");
  throws(() => UT.fromFile("x"), /not JSON/); throws(() => UT.fromFile("{}"), /not a themes file/);
  throws(() => UT.fromFile(JSON.stringify({ format: UT.FILE_FORMAT, version: 9, themes: [] })), /version 9/);
  throws(() => UT.fromFile(JSON.stringify({ format: UT.FILE_FORMAT, version: 1, themes: [{ name: "x" }] })), /no theme in the file is complete/);
  const merged = UT.merge(UT.put([], "Night 2", base), mine);
  eq([merged.added, merged.replaced, merged.list.length], [1, 1, 2]);

  // the opacity of the roads: the defaults, the repair, the themes, and the expressions for roadstyle's road layers
  eq(base.roads.opacity, { fill: 1, casing: 1, outline: false }); eq(base.labels.halo_opacity, 1); eq(base.arrows.opacity, 0.7);
  const ov2 = D.normalize({ roads: { opacity: { fill: 9, casing: -1, outline: 1 } }, labels: { halo_opacity: "x" }, arrows: { opacity: 0.2 } }, base);
  eq(ov2.roads.opacity, { fill: 1, casing: 0, outline: true }); eq(ov2.labels.halo_opacity, 1); eq(ov2.arrows.opacity, 0.2);
  eq(T("overlay").roads.opacity, { fill: 0.6, casing: 0.85, outline: true }); eq(T("hollow").roads.opacity, { fill: 0, casing: 1, outline: true });
  eq(T("ghost").roads.opacity, { fill: 0.35, casing: 0.7, outline: true }); eq(T("print").roads.opacity, { fill: 1, casing: 1, outline: false }, "a theme with no opacity has the default");
  eq(T("amber", T("hollow")).roads.opacity, D.defaultRoadOpacity(), "a road palette draws the full fill and casing, also on Roads hollow");
  const rowExpr = ["+", ["*", ["at", ["+", ["*", ["get", "__rs_k"], 8], 0], ["literal", [0, 1, 2]]], 13], 5];
  const widthExpr = ["let", "row", rowExpr, ["interpolate", ["linear"], ["zoom"], 12, ["*", ["at", ["var", "row"], ["literal", [6, 4]]], 1], 14, ["*", ["at", ["var", "row"], ["literal", [12, 8]]], 1]]];
  const opExpr = ["interpolate", ["linear"], ["zoom"], 14, ["case", ["==", ["get", "__rs_k"], 2], 0, 1], 17, 1];
  const o1 = D.roadOpacity(opExpr, 0.4, 0.8);
  eq(o1.slice(0, 4), ["interpolate", ["linear"], ["zoom"], 14]); eq(o1[4][0], "*"); eq(o1[6][0], "*");
  eq(o1[4][2], ["case", ["==", ["get", "__rs_k"], 0], 0.8, ["==", ["get", "__rs_k"], 1], 0.4, 1], "casing at 0.8, fill at 0.4, other pieces as they are");
  eq(D.roadOpacity(0.7, 0.5, 1)[0], "*"); eq(D.roadOpacity(undefined, 0.5, 1)[1], 1);
  const out = D.roadOutline(widthExpr);
  eq(out.width[0], "let"); eq(out.width.length, 6); eq(out.width[3], "row1");
  ok(JSON.stringify(out.width[2]).includes("__rs_k") && !JSON.stringify(out.width[4]).includes("__rs_k"), "row has the kind of the piece; row1 has the kind 1 (the fill)");
  eq(out.gap[5].slice(0, 4), ["interpolate", ["linear"], ["zoom"], 12], "the zoom stays at the top");
  eq(D.roadOutline(["literal", 3]), null); eq(D.roadOutline(undefined), null);
  eq(D.withAlpha("#ff8000", 0.5), "rgba(255,128,0,0.5)");

  // the filter and the search of the theme list
  const ids = (f, q = "") => THEME_DATA.filter((t) => D.themeMatches(t, f, q)).map((t) => t.id);
  eq(ids("all").length, THEME_DATA.length); eq(ids("yours"), []);
  eq(ids("overlay"), ["overlay", "overlaydark", "hollow", "ghost"]);
  eq(ids("print"), ["print", "toner", "graytone"]);
  ok(ids("dark").every((i) => THEME_DATA.find((t) => t.id === i).dark) && ids("dark").includes("night") && !ids("dark").includes("light"), "dark");
  ok(ids("light").includes("waze") && !ids("light").includes("overlay"), "light");
  eq(ids("all", "Google LIKE"), ["google"], "a search finds the name, in any letters; all the words must match");
  eq(ids("dark", "google"), [], "the search works inside a filter");
  ok(ids("all", "satellite").includes("overlay") && ids("all", "roadstyle").length >= 8, "a search finds words of the note and of the group");
  eq(D.THEME_FILTERS.map(([k]) => k).join(), "all,light,dark,overlay,print,roads,roadstyle,yours");
  return { failures, looks };
}

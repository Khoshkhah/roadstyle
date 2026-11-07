// The design panel (docs/guides/design-panel.md): the style of the map, as a part that any page with a dashboard can hold. It draws into the host's standard
// dashboard panel (#sb > .sb-card with .sb-top and .sb-body) in roadstyle's editor frame (../frame.js): open() hides the host's title and body and shows the
// frame's title line, its tabs (Theme, Roads, Text, Layers and the host's own tabs), the body and the bar; close() shows the host's panel again. This file owns the
// design (design.js) and draws the tabs; the host gives the look, the way to show a new look (setLook: the same tiles; redraw: a new map) and its own values (host tabs, the boundary).
//
//   designPanel({ panel, dashboard, map, look, setLook, redraw, restyle, backLabel, storageKey, boundary, link, tabs })
//     -> EventTarget + { open, close, isOpen, tab, get, text, set, load, setHost, refresh, flush, base, state, restored }
//   events: "change" {design, text} after each change; "back" when the person clicks the back button
//
// A change of the style draws the map again after 0.5 s of quiet: setLook(text) gives a style for the same tiles (the panel shows it with rs.restyle), else
// redraw(text, true) draws a new map. The ground, the layers and the opacity are not in the look: the panel paints them at once with roadstyle's own calls, and
// again after each new style (rs:stylechange). A change that also changes the look (a theme) paints them when the new look shows: one change on the map.
import * as D from "./design.js";
import * as UT from "./user_themes.js";
import {editorFrame} from "../frame.js";

const TABS = [["theme", "Theme"], ["roads", "Roads"], ["text", "Text"], ["layers", "Layers"]];
const LABEL = { motorway: "Motorway", trunk: "Trunk", primary: "Primary", secondary: "Secondary", tertiary: "Tertiary", unclassified: "Unclassified", residential: "Residential",
  living_street: "Living street", service: "Service", pedestrian: "Pedestrian", cycleway: "Cycleway", footway: "Footway", path: "Path", track: "Track" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (v, d = 2) => (+v).toFixed(d);

const setPath = (o, path, v) => {
  const keys = path.split(".");
  const last = keys.pop();
  for (const k of keys) o = o[k];
  o[last] = v;
};

// ---- the controls (the host tabs get them too: the fourth argument of `draw`) ----
const color = (label, p, v) => `<label class="drow2"><span>${label}</span><input type="color" data-p="${p}" value="${v}"></label>`;
const shown = (v, unit) => (unit === "%" ? `${Math.round(v * 100)}%` : `${+(+v).toFixed(2)}${unit}`);          // the unit "%" shows a fraction (0 to 1) as a percent
const range = (label, p, v, min, max, step, unit = "") => `<label class="drow2 rng"><span>${label}</span><input type="range" data-unit="${unit}" data-p="${p}" min="${min}" max="${max}" step="${step}" value="${v}"><output>${shown(v, unit)}</output></label>`;
const number = (label, p, v, min, max, step = 1, extra = "") => `<label class="drow2"><span>${label}</span><input type="number" data-p="${p}" min="${min}" max="${max}" step="${step}" value="${v}" ${extra}></label>`;
const check = (label, p, v, note2 = "", extra = "") => `<label class="optrow"><input type="checkbox" data-p="${p}" ${v ? "checked" : ""} ${extra}><span class="t"><b>${label}</b>${note2 ? `<small>${note2}</small>` : ""}</span></label>`;
const sec = (title, body, why = "") => `<section class="rs-sec-box"><div class="rs-card-title">${title}</div>${why ? `<p class="why">${why}</p>` : ""}${body}</section>`;   // the dashboard's card
export const controls = { color, range, number, check, sec, esc };

export async function designPanel({ panel, dashboard = window.rs, map = window.map, look, setLook = null, redraw, restyle = {}, backLabel = "Steps", storageKey = "roadstyle",
                                    boundary = null, link = null, tabs: hostTabs = [] }) {
  const frame = editorFrame({ panel, title: "Edit design", back: backLabel, id: "design", tabs: [...TABS, ...hostTabs.map((h) => [h.id, h.name])] });          // a bad `panel` throws
  if (!look || typeof redraw !== "function") throw new Error("design panel: give `look` (the look of the map, as an object) and `redraw(text, draw)`");
  const r = await fetch(new URL("themes.json", import.meta.url));
  if (!r.ok) throw new Error(`design panel: the ready themes (themes.json, ${r.status})`);
  const THEMES = D.themesOf((await r.json()).themes);
  const HOSTS = hostTabs, hostKeys = HOSTS.map((h) => h.key);
  const TAB_IDS = [...TABS.map(([t]) => t), ...HOSTS.map((h) => h.id)];
  const P = () => dashboard?.prefix ?? "rs-";
  const events = new EventTarget();
  const base = D.defaultsOf(look, HOSTS), norm = (d) => D.normalize(d, base, HOSTS);
  const hostValues = (d) => Object.fromEntries(hostKeys.map((k) => [k, d[k]]));
  const noHost = (d) => ({ ...d, ...Object.fromEntries(hostKeys.map((k) => [k, 0])) });
  let themeFilter = "all", themeQuery = "";                                                 // the filter and the search above the theme list
  let mine = UT.readAll(undefined, `${storageKey}.themes`), origin = null, ask = null, armed = null, renaming = null, nameDraft = "", keepDraft = false, mineMsg = "";
  let design = structuredClone(base), tab = "theme", lastKey = null, timer = null, busy = false, again = false, note = "";
  const styleKey = (d) => {                                          // the boundary, the ground, the layers, the opacity and the host values are not in the look: they draw no new map
    const k = structuredClone({ ...noHost(d), name: 0, theme: 0, boundary: 0, ground: 0, visible: 0 });
    delete k.roads.opacity; delete k.labels.halo_opacity; delete k.arrows.opacity;
    return JSON.stringify(k);
  };
  lastKey = styleKey(base);                                          // the host's map shows `look` at the start

  // ---- the markup: the editor frame (../frame.js) gives the title line, the tabs, the body and the bar; the classes rs-dz* are for the panel's own content ----
  const { root, top: title, body, bar } = frame;
  root.classList.add("rs-dz"); root.id = "design-panel"; root.querySelector("#design-tabs").setAttribute("aria-label", "What to design");
  title.classList.add("rs-dz-title"); title.querySelector(".rs-frame-back")?.classList.add("rs-dz-back");
  title.insertAdjacentHTML("beforeend", '<span class="dname" id="design-name"></span>');
  body.classList.add("rs-dz-body"); bar.classList.add("rs-dz-bar");
  body.innerHTML = '<div id="design-pane"></div>';
  bar.innerHTML = `<div class="line"><b id="design-changes">Style: default</b>${link ? `<button type="button" class="rs-link" id="design-link">${esc(link.label)}</button>` : ""}</div><p class="st" id="design-state" role="status" aria-live="polite"></p><p class="st" id="design-notice" role="status"></p>`;
  const $ = (id) => root.querySelector("#" + id) ?? title.querySelector("#" + id);
  const pane = $("design-pane");

  // ---- the map: the layers, the ground, the opacity of the roads and the base map under the map, with roadstyle's own calls ----
  let painted = design, applying = false, restyling = false, held = false;                                     // painted: the design that the map shows now
  const roadOrig = new Map();                                                               // the original paint of the road layers (see paintRoads)
  const hasLayer = (k) => {                                                                 // true, false, or undefined (no roads on the map: not known)
    const ovs = window.RS_OVERLAYS ?? [], cls = window.RS_CLASSES ?? [];
    if (!cls.length && !ovs.length) return undefined;
    if (D.OVERLAY_KEYS.includes(k)) return ovs.some((o) => o.label === k);
    if (k === "buildings3d") return ovs.some((o) => o.label === "buildings" && o.extrude);
    if (D.ROAD_GROUPS[k]) return cls.some((c) => D.classGroup(c) === k);
    if (k === "arrows") return !!window.rsHasArrows?.();
    if (k === "names") return !!map.getLayer(P() + "roads-labels");
    return true;
  };
  function paintGround() {
    if (map.getLayer("bg")) map.setPaintProperty("bg", "background-opacity", D.groundAlpha(painted));
    paintPreview();
  }
  function applyVisible() {
    const v = painted.visible, ovs = window.RS_OVERLAYS ?? [];
    if (!window.RS_CLASSES?.length && !ovs.length) return;
    applying = true;
    try {
      if (window.RS_CLASSES?.length) window.rsSetClasses(window.RS_CLASSES.filter((c) => v[D.classGroup(c)] !== false));
      window.rsSetBridges?.(v.bridges); window.rsSetTunnels?.(v.tunnels);
      if (window.rsHasArrows?.()) window.rsSetArrows(v.arrows);
      for (const k of D.OVERLAY_KEYS) if (ovs.some((o) => o.label === k) && ovs.find((o) => o.label === k).visible !== v[k]) window.rsSetOverlay(k, v[k]);
      if (ovs.some((o) => o.label === "buildings" && o.extrude) && window.rsGetBuildings3D() !== v.buildings3d) window.rsSetBuildings3D(v.buildings3d);
      if (map.getLayer(P() + "roads-labels")) map.setLayoutProperty(P() + "roads-labels", "visibility", v.names ? "visible" : "none");
    } finally { applying = false; }
  }
  // roadstyle's road layers have one `line-opacity` and one `line-width` for the casing and the fill; the panel writes the design's opacity into them (D.roadOpacity),
  // and, with "Casing as an outline", a casing that has a gap of the fill width (D.roadOutline). The originals are kept when a layer is first seen, and come back for the default values.
  function paintRoads() {
    const d = painted, o = d.roads.opacity, simple = P() + "roads-simple";
    for (const l of map.getStyle()?.layers ?? []) {
      if (l.type !== "line" || !l.id.startsWith(simple)) continue;
      let orig = roadOrig.get(l.id);
      if (!orig) roadOrig.set(l.id, (orig = { op: l.paint?.["line-opacity"], w: l.paint?.["line-width"] }));
      map.setPaintProperty(l.id, "line-opacity", o.fill === 1 && o.casing === 1 ? orig.op : D.roadOpacity(orig.op, o.fill, o.casing));
      const hole = o.outline ? D.roadOutline(orig.w) : null;
      map.setPaintProperty(l.id, "line-width", hole ? hole.width : orig.w);
      map.setPaintProperty(l.id, "line-gap-width", hole ? hole.gap : 0);
    }
    if (map.getLayer(P() + "roads-labels") && d.labels.halo_opacity !== 1) map.setPaintProperty(P() + "roads-labels", "text-halo-color", D.withAlpha(d.labels.halo_color, d.labels.halo_opacity));
    if (map.getLayer(P() + "roads-arrows") && d.arrows.opacity !== 0.7) map.setPaintProperty(P() + "roads-arrows", "icon-opacity", d.arrows.opacity);
  }
  const paintMap = () => { paintGround(); applyVisible(); paintRoads(); };
  const announce = () => { painted = design; boundary?.(design.boundary); paintMap(); };
  const announceSoon = () => { if (styleKey(design) !== lastKey) held = true; else { held = false; announce(); } };
  const paintHeld = () => { if (held) { held = false; announce(); } };
  document.addEventListener("rs:stylechange", () => { roadOrig.clear(); paintHeld(); paintMap(); });          // a new style: its own paint is the original
  // a switch event is the person's choice only when the panel does not make it: not while it paints (applying), and not while a new style or a new map comes
  // in (restyling: rs.setStyle switches the layers of the old style again and sends their events before rs:stylechange; the held design is painted after it)
  const quiet = () => applying || restyling;
  for (const [ev, key] of [["rs:arrowschange", "arrows"], ["rs:buildings3dchange", "buildings3d"]]) document.addEventListener(ev, (e) => { if (!quiet()) setVisible(key, e.detail.on); });
  document.addEventListener("rs:overlaychange", (e) => { if (!quiet()) setVisible(e.detail.overlay, e.detail.visible); });
  document.addEventListener("rs:filterchange", (e) => {
    const d = e.detail;
    if (quiet()) return;
    if ("bridges" in d) setVisible("bridges", d.bridges);
    if ("tunnels" in d) setVisible("tunnels", d.tunnels);
    if (Array.isArray(d.visible)) for (const g of Object.keys(D.ROAD_GROUPS)) {
      const cs = (window.RS_CLASSES ?? []).filter((c) => D.classGroup(c) === g);
      if (cs.length) setVisible(g, cs.some((c) => d.visible.includes(c)));
    }
  });

  // ---- the preview under the map: "Preview on" is the base map of roadstyle's base-map box (one choice in two places). The checkerboard is the Blank base map with a
  // checkerboard under the ground; it shows by itself while the ground is transparent and the base map is Blank, until the person picks Blank or the checkerboard. ----
  let baseKey = dashboard?.getState?.().basemap ?? null, previewChecker;                    // previewChecker: undefined (automatic), true or false
  const isBlank = (k) => /^blank/.test(k ?? "");
  const keyOf = (v) => {                                                                    // the base map of a preview choice, of the base maps that the page has
    const keys = (window.RS_BASEMAPS ?? []).map((b) => b.key);
    if (v === "checkerboard" || v === "blank") return keys.find(isBlank) ?? null;
    if (v === "openfreemap") return keys.includes("ofm_positron") ? "ofm_positron" : keys.find((k) => /^ofm_/.test(k)) ?? null;
    return keys.includes("satellite") ? "satellite" : null;
  };
  const checkerOn = () => previewChecker ?? D.groundAlpha(painted) < 0.5;
  function previewValue() {
    if (isBlank(baseKey)) return checkerOn() ? "checkerboard" : "blank";
    return /^ofm_/.test(baseKey ?? "") ? "openfreemap" : baseKey === "satellite" ? "satellite" : "other";
  }
  function paintPreview() {
    map.getContainer().classList.toggle("rs-checker", isBlank(baseKey) && checkerOn());
    refresh();
  }
  function setPreview(v) {
    previewChecker = v === "checkerboard" ? true : v === "blank" ? false : undefined;
    const k = keyOf(v);
    if (k) window.rsSetBasemap(k);
    paintPreview();
  }
  document.addEventListener("rs:basemapchange", (e) => { baseKey = e.detail.basemap; paintGround(); });     // a base map changes the layer bg: the ground keeps its opacity

  // ---- the tabs ----
  // four cells: the ground, a road fill, its casing, the water; a transparent ground or a layer that is off shows as a checkerboard
  const swatches = (d) => [[d.base.background, d.ground.transparent && d.ground.opacity < 0.5], [d.roads.fill.primary], [d.roads.casing.primary], [d.base.water, d.visible.water === false]]
    .map(([c, none]) => `<i${none ? ' class="none"' : ` style="background:${c}"`}></i>`).join("");
  const themeCard = (t) => { const d = t.make(base); return `<button type="button" class="theme" role="radio" data-look="${t.id}" aria-checked="${design.theme === t.id}"><span class="sw5">${swatches(d)}</span><b>${t.name}</b><small>${esc(t.note)}</small></button>`; };
  const keeps = HOSTS.filter((h) => h.keep);
  const mineCard = (t) => {
    const on = design.theme === `mine:${t.id}`;
    if (renaming === t.id) return `<div class="theme mine" data-mine="${t.id}"><span class="sw5">${swatches(norm(t.design))}</span><input type="text" id="mine-rename" maxlength="${UT.MAX_NAME}" value="${esc(t.name)}" aria-label="New name"><span class="acts"><button type="button" class="sm" data-mine-do="rename-ok">Save</button><button type="button" class="sm" data-mine-do="rename-no">Cancel</button></span></div>`;
    return `<div class="theme mine" data-mine="${t.id}" aria-current="${on}"><span class="sw5">${swatches(norm(t.design))}</span><b>${esc(t.name)} <span class="yours">yours</span></b>
      <span class="acts"><button type="button" class="sm" data-mine-do="apply">Apply</button><button type="button" class="sm" data-mine-do="rename">Rename</button><button type="button" class="sm${armed === t.id ? " danger" : ""}" data-mine-do="delete">${armed === t.id ? "Delete?" : "Delete"}</button></span></div>`;
  };
  const paneMine = () => {
    const from = origin && UT.find(mine, origin.name), custom = design.theme === "custom";
    return sec("Your themes",
      (custom ? `<p class="small">The design is <b>custom</b>${origin ? ` (it began as "${esc(origin.name)}")` : ""}. ${from ? `<button type="button" class="sm" data-mine-do="update">Update "${esc(from.name)}"</button>` : ""}</p>` : "")
      + `<label class="drow2"><span>Name</span><input type="text" id="mine-name" maxlength="${UT.MAX_NAME}" value="${esc(nameDraft)}" placeholder="A name for this design" aria-label="Name of the theme"></label>`
      + keeps.map((h) => `<label class="optrow"><input type="checkbox" id="mine-keep" ${keepDraft ? "checked" : ""}><span class="t"><b>${esc(h.keep)}</b><small>Off: the theme keeps the value that the page has, as the ready themes do.</small></span></label>`).join("")
      + `<div class="row"><button type="button" id="mine-save">Save as a theme</button></div>`
      + (ask ? `<p class="small" role="alert">A theme named "${esc(ask.name)}" exists. Replace it? <button type="button" class="sm" data-mine-do="replace">Replace</button> <button type="button" class="sm" data-mine-do="keep-old">Cancel</button></p>` : "")
      + `<p class="small" id="mine-msg" role="status">${esc(mineMsg)}</p>`
      + (mine.length ? `<div class="themes" id="mine-list">${mineShown().map(mineCard).join("")}</div>` : '<p class="why">No saved theme yet. Pick a theme, change it, and save it here with a name.</p>')
      + `<div class="row"><button type="button" id="mine-download" ${mine.length ? "" : "disabled"}>Download all my themes</button><button type="button" id="mine-load">Load themes from a file</button></div><input id="mine-file" type="file" accept=".json,application/json" hidden>`,
      "Your themes are for all the maps of this page. They stay in this browser: download them to use them on another computer.");
  };
  const panePreview = () => {
    const v = previewValue(), opts = [["checkerboard", "Checkerboard"], ["blank", "Blank"], ["openfreemap", "OpenFreeMap"], ["satellite", "Satellite"]].filter(([k]) => keyOf(k));
    return sec("Preview on", `<label class="drow2"><span>Base map</span><select id="design-preview" aria-label="Preview on">${opts.map(([k, n]) => `<option value="${k}" ${v === k ? "selected" : ""}>${n}</option>`).join("")}${v === "other" ? '<option value="other" selected disabled>Other (base-map box)</option>' : ""}</select></label>`,
      "This changes only the map under the roads. It is the base map of the base-map box: one choice in two places. A transparent ground shows the checkerboard on the Blank map.");
  };
  const shownThemes = () => THEMES.filter((t) => D.themeMatches(t, themeFilter, themeQuery));
  const readyList = () => {
    const list = shownThemes();
    if (!list.length) return `<p class="why">No ready theme has these words in this filter.</p>`;
    return D.THEME_KINDS.map(([k, n, why]) => {
      const of = list.filter((t) => D.themeKind(t) === k);
      return of.length ? `<div class="kind" data-kind="${k}"><b>${n}</b><small>${why}</small></div>${of.map(themeCard).join("")}` : "";
    }).join("");
  };
  const paneTheme = () => sec("Ready themes", `<input type="search" id="theme-search" placeholder="Search themes: google, dark, print…" value="${esc(themeQuery)}" aria-label="Search themes">
      <div class="chips" role="group" aria-label="Filter themes">${D.THEME_FILTERS.map(([k, n]) => `<button type="button" class="chip" data-tf="${k}" aria-pressed="${themeFilter === k}">${n}</button>`).join("")}</div>
      <p class="small muted" id="theme-count" role="status"></p>
      <div class="themes" id="ready-list" role="radiogroup" aria-label="Ready themes">${readyList()}</div>`, "Pick a theme with one click, then change any value in the other tabs.")
    + panePreview() + paneMine()
    + sec("Your design", `<label class="drow2"><span>Name</span><input type="text" data-p="name" value="${esc(design.name)}" maxlength="60" aria-label="Name of the design"></label>
      <div class="row"><button type="button" id="design-download">Download</button><button type="button" id="design-load">Load a file</button><button type="button" id="design-reset">Reset</button></div>
      <input id="design-file" type="file" accept=".json,application/json" hidden>
      <p class="why" id="design-where">The page keeps the design in this browser. Download saves it as one .json file.</p>`);
  const paneRoads = () => sec("Colors", `<div class="rhead"><span></span><span>Fill</span><span>Casing</span></div>${D.CLASSES.map((c) => `<div class="drow2 cls"><span>${LABEL[c]}</span><input type="color" data-p="roads.fill.${c}" value="${design.roads.fill[c]}" aria-label="${LABEL[c]} fill"><input type="color" data-p="roads.casing.${c}" value="${design.roads.casing[c]}" aria-label="${LABEL[c]} casing"></div>`).join("")}`,
      "The casing is the outline of a road. A link road has the colors of its class.")
    + sec("Opacity", range("Fill opacity", "roads.opacity.fill", design.roads.opacity.fill, 0, 1, 0.05, "%") + range("Casing opacity", "roads.opacity.casing", design.roads.opacity.casing, 0, 1, 0.05, "%")
      + check("Casing as an outline", "roads.opacity.outline", design.roads.opacity.outline, "The casing is drawn only outside the fill, not under it. Use it when the fill is not opaque: the map under the road then shows through the fill."),
      "100 percent is the opacity of the style. A lower value lets the map under the roads show through.")
    + sec("Width", D.GROUPS.map(([g, n]) => range(n, `roads.width.${g}`, design.roads.width[g], 0.5, 2.5, 0.05, " ×")).join(""), "A factor for the whole width curve of a group. 1 is the width of the theme.")
    + sec("Dark mode", `<p class="why">The map in the dark theme changes each light color to a dark one. These ranges set how light the dark colors are (0 is black, 1 is white).</p>`
      + [["roads", "Road fill"], ["casing", "Casing"], ["areas", "Areas"], ["labels", "Text"]].map(([k, n]) => `<div class="drow2 two"><span>${n}</span><input type="number" data-p="dark.${k}.0" min="0" max="1" step="0.02" value="${design.dark[k][0]}" aria-label="${n}, darkest"><input type="number" data-p="dark.${k}.1" min="0" max="1" step="0.02" value="${design.dark[k][1]}" aria-label="${n}, lightest"></div>`).join("")
      + color("Dark ground", "dark.background", design.dark.background));
  const paneText = () => sec("Street names", color("Color", "labels.color", design.labels.color) + color("Halo color", "labels.halo_color", design.labels.halo_color)
      + range("Halo width", "labels.halo_width", design.labels.halo_width, 0, 4, 0.25, " px") + range("Halo opacity", "labels.halo_opacity", design.labels.halo_opacity, 0, 1, 0.05, "%") + range("Size", "labels.size", design.labels.size, 0.6, 1.8, 0.05, " ×")
      + number("From zoom", "labels.minzoom", design.labels.minzoom, 8, 20), "Smaller roads show their names two zooms later.")
    + sec("One-way arrows", color("Color", "arrows.color", design.arrows.color) + range("Size", "arrows.size", design.arrows.size, 0.5, 3, 0.1, " ×") + range("Opacity", "arrows.opacity", design.arrows.opacity, 0, 1, 0.05, "%") + number("From zoom", "arrows.minzoom", design.arrows.minzoom, 8, 20),
      "The switch for the arrows is in the Layers box of the map bar.");
  const paneVisible = () => {
    const v = design.visible, row = (k, n) => {
      const off = hasLayer(k) === false;
      return `<label class="col"><input type="checkbox" data-p="visible.${k}" ${v[k] ? "checked" : ""} ${off ? "disabled" : ""}>${n}${off ? ' <small class="muted">(not on this map)</small>' : ""}</label>`;
    };
    return sec("Show these layers", D.VISIBLE_GROUPS.map(([g, rows]) => `<p class="fix-group">${g}</p><div class="cols">${rows.map(([k, n]) => row(k, n)).join("")}</div>`).join("")
      + (boundary ? `<p class="fix-group">Area</p><div class="cols"><label class="col"><input type="checkbox" data-p="boundary.show" ${design.boundary.show ? "checked" : ""}>Area boundary</label></div>` : ""),
      "A switch is the same as the switch in the Layers box of the map bar: both show one state. A layer that the map does not have cannot show.");
  };
  const paneGround = () => sec("Ground", check("Transparent ground", "ground.transparent", design.ground.transparent, "The ground of the map has no color, so a base map shows under the roads. Use it with the theme Roads overlay.")
      + range("Opacity of the ground", "ground.opacity", design.ground.opacity, 0, 1, 0.05).replace("<input", `<input ${design.ground.transparent ? "" : "disabled"}`),
      "0 is fully transparent. The opacity counts only while the ground is transparent.");
  const paneBoundary = () => {
    if (!boundary) return "";
    const b = design.boundary, off = b.show ? "" : "disabled";
    return sec("Area boundary", (b.show ? "" : '<p class="small muted">The boundary is hidden. Turn it on in Show these layers.</p>')
      + color("Line color", "boundary.color", b.color).replace("<input", `<input ${off}`) + range("Line width", "boundary.width", b.width, 0.5, 6, 0.5, " px").replace("<input", `<input ${off}`)
      + `<label class="drow2"><span>Line style</span><select data-p="boundary.dash" ${off}>${Object.keys(D.BOUNDARY_DASH).map((k) => `<option value="${k}" ${b.dash === k ? "selected" : ""}>${k}</option>`).join("")}</select></label>`
      + color("Fill color", "boundary.fill", b.fill).replace("<input", `<input ${off}`) + range("Fill opacity", "boundary.fillOpacity", b.fillOpacity, 0, 1, 0.02).replace("<input", `<input ${off}`)
      + check("Fill over the roads", "boundary.fillOnRoads", b.fillOnRoads, "The fill covers the roads and changes their colors. It is off by default: the page hides the fill when the roads show.", off),
      "A fill opacity of 0 gives no fill.");
  };
  const paneLayers = () => paneVisible() + paneBoundary() + paneGround() + sec("Colors of the layers", color("Background", "base.background", design.base.background) + color("Water", "base.water", design.base.water) + color("Green areas", "base.green", design.base.green)
      + color("Built-up land", "base.land", design.base.land) + color("Sand and beach", "base.sand", design.base.sand), "Colors of the base-map layers. They show when the map has the base-map layers.")
    + sec("Buildings and lines", color("Buildings", "base.buildings", design.base.buildings) + color("Building outline", "base.buildingLine", design.base.buildingLine)
      + color("Railways", "base.railways", design.base.railways) + color("Waterways", "base.waterways", design.base.waterways))
    + sec("3D buildings", range("Meters for each floor", "base.m_per_level", design.base.m_per_level, 2, 6, 0.1, " m") + number("Highest building (m)", "base.max_height", design.base.max_height, 10, 500, 10)
      + range("Opacity", "base.height_opacity", design.base.height_opacity, 0.2, 1, 0.05), "The height of a building is its floors times this value, up to the highest building.");
  const PANES = { theme: paneTheme, roads: paneRoads, text: paneText, layers: paneLayers };

  // ---- draw ----
  // a host tab: the host draws its pane (draw(element, value, put, controls)); put(v) tells the panel of a new value
  const putHost = (h) => (v) => { design[h.key] = h.normalize(v); changed(); };
  function paint() {
    const h = HOSTS.find((x) => x.id === tab);
    if (h) { pane.innerHTML = `<div data-host="${h.key}"></div>`; h.draw(pane.firstElementChild, design[h.key], putHost(h), controls); }
    else pane.innerHTML = PANES[tab]();
    frame.tab(tab);
    if (tab === "theme") paintThemeList();
    pane.dataset.tab = tab;
    paintBar();
    if (isOpen()) document.dispatchEvent(new CustomEvent("rs:sectionchange", { detail: { id: "design", state: "show" } }));         // the panel's select lists in the look of the boxes (selectbox.js)
  }
  /** The list of ready themes again (a filter or a search changed): the search field keeps its focus. */
  function paintThemeList() {
    const list = $("ready-list");
    if (!list) return;
    const n = shownThemes().length, yours = themeFilter === "yours";
    list.innerHTML = yours ? '<p class="why">Your themes are below.</p>' : readyList();
    $("theme-count").textContent = yours ? `${mineShown().length} of ${mine.length} of your themes` : `${n} of ${THEMES.length} ready themes`;
    for (const b of pane.querySelectorAll("[data-tf]")) b.setAttribute("aria-pressed", String(b.dataset.tf === themeFilter));
    const m = $("mine-list");
    if (m) m.innerHTML = mineShown().map(mineCard).join("");
  }
  const mineShown = () => (themeFilter === "all" || themeFilter === "yours" ? mine.filter((t) => String(themeQuery).toLowerCase().split(/\s+/).filter(Boolean).every((w) => t.name.toLowerCase().includes(w))) : []);          // your themes show in All and Yours
  function paintBar() {
    $("design-name").textContent = design.name;
    $("design-changes").textContent = D.changes(noHost(design), noHost(base)).length ? "Style: changed" : "Style: default";
    $("design-state").textContent = note;
    const clear = D.groundAlpha(design) < 0.5 && ["checkerboard", "blank"].includes(previewValue());
    $("design-notice").textContent = clear ? "The ground is transparent: pick a base map in the base-map box to see it through." : "";
  }
  function tabTo(name) {
    tab = TAB_IDS.includes(name) ? name : "theme";
    const keep = body.scrollTop;
    paint();
    body.scrollTop = name === tab ? keep : 0;
  }

  // ---- apply: the style draws the map again; the change goes to the host ----
  function save() {
    const text = D.toFile(design);
    try { localStorage.setItem(`${storageKey}.design`, text); } catch (_) { /* a private window has no storage: the design stays on the page */ }
    events.dispatchEvent(new CustomEvent("change", { detail: { design, text } }));
  }
  /** The look of the design as text for the host, or null for the look itself (the default design). */
  const lookText = (key) => (key === styleKey(base) ? null : JSON.stringify(D.applyToLook(look, design)));
  async function run() {
    const key = styleKey(design);
    if (key === lastKey) return;
    if (busy) { again = true; return; }
    busy = true;
    note = "Drawing the map…"; paintBar();
    try {
      lastKey = key; restyling = true;
      const text = lookText(key), t0 = performance.now();
      let done = null;
      if (setLook) {
        try {
          const st = await setLook(text ?? JSON.stringify(look));
          if (st && await dashboard.restyle(typeof st === "string" ? JSON.parse(st) : st, restyle)) done = `The map shows this design: a new look on the same tiles, in ${num((performance.now() - t0) / 1000)} s.`;
        } catch (e) { console.warn("design panel: a new look on the same tiles failed, the map is drawn again:", e); }
      }
      note = done ?? (await redraw(text, true)) ?? "The map shows this design.";
    } catch (e) {
      lastKey = null; note = "The map could not draw this design: " + e.message;
    } finally {
      busy = false; restyling = false; paintHeld(); paintBar();
      if (again) { again = false; schedule(0); }
    }
  }
  function schedule(ms = 500) { clearTimeout(timer); timer = setTimeout(run, ms); }
  const changed = () => {
    design = norm(design);
    save(); schedule(); announceSoon(); paintBar();
  };

  // ---- events ----
  const fromHost = (e) => !!e.target.closest?.("[data-host]");                              // a host tab's own controls: the host reads them
  pane.addEventListener("input", (e) => {
    const el = e.target;
    if (fromHost(e)) return;
    if (el.id === "theme-search") { themeQuery = el.value; return paintThemeList(); }
    if (el.id === "mine-name") { nameDraft = el.value; return; }
    if (el.id === "mine-keep") { keepDraft = el.checked; return; }
    const p = el.dataset.p;
    if (!p) return;
    const v = el.type === "checkbox" ? el.checked : el.type === "range" || el.type === "number" ? (el.value === "" ? NaN : +el.value) : el.value;
    if (Number.isNaN(v)) return;
    setPath(design, p, v);
    if (el.type === "range") el.parentElement.querySelector("output").textContent = shown(v, el.dataset.unit);
    if (p === "boundary.show" || p === "ground.transparent") { design.theme = "custom"; return (changed(), paint()); }
    if (p !== "name") design.theme = "custom";
    changed();
  });
  pane.addEventListener("click", (e) => {
    if (fromHost(e)) return;
    const t = e.target.closest("[data-look]");
    if (t) {
      const keep = hostValues(design);
      design = THEMES.find((x) => x.id === t.dataset.look).make(base, design);          // a road palette keeps the base map of the design that is on now (D.THEME_KINDS)
      Object.assign(design, keep); origin = null; changed(); return paint();
    }
    const tf = e.target.closest("[data-tf]");
    if (tf) { themeFilter = tf.dataset.tf; return paintThemeList(); }
    const mb = e.target.closest("[data-mine-do]");
    if (mb) return mineAction(mb.dataset.mineDo, mb.closest("[data-mine]")?.dataset.mine);
    if (e.target.id === "mine-save") return mineSave();
    if (e.target.id === "mine-download") return download(`${storageKey}-themes.json`, UT.toFile(mine));
    if (e.target.id === "mine-load") return $("mine-file").click();
    if (e.target.id === "design-reset") { const keep = hostValues(design); design = structuredClone(base); Object.assign(design, keep); changed(); return paint(); }
    if (e.target.id === "design-download") return download(`${design.name.toLowerCase().replace(/[^a-z0-9_-]+/g, "_") || "design"}.design.json`, D.toFile(design));
    if (e.target.id === "design-load") return $("design-file").click();
  });
  function download(name, text) {
    const a = Object.assign(document.createElement("a"), { download: name, href: URL.createObjectURL(new Blob([text], { type: "application/json" })) });
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href));
  }
  // ---- your themes: save, apply, rename, delete (a second click), update, and the file of all of them ----
  const keepMine = () => { if (!UT.writeAll(mine, undefined, `${storageKey}.themes`)) mineMsg = "The browser cannot keep the themes. They stay on this page until you close it."; };
  const say = (t) => { mineMsg = t; paint(); };
  function mineSave(replace = false) {
    mineMsg = "";
    const name = $("mine-name").value;
    const err = UT.nameError(name);
    if (err) return say(err);
    if (UT.find(mine, name) && !replace) { ask = { name: name.trim() }; return say(""); }
    mine = UT.put(mine, name, design, keepDraft, hostKeys);
    const t = UT.find(mine, name);
    design.theme = `mine:${t.id}`; design.name = t.name; origin = { id: t.id, name: t.name }; ask = null; nameDraft = "";
    keepMine(); save(); paintBar();
    say(mineMsg || `Saved "${t.name}".`);
  }
  function mineAction(what, id) {
    mineMsg = "";                                           // `keepMine` can set a message: a message that is left is from an earlier action
    const t = mine.find((x) => x.id === id);
    if (what === "replace") return mineSave(true);
    if (what === "keep-old") { ask = null; return say(""); }
    if (what === "update" && origin) {
      const old = UT.find(mine, origin.name);
      if (!old) return say("");
      mine = UT.put(mine, old.name, design, old.keepProfile, hostKeys);
      design.theme = `mine:${old.id}`; design.name = old.name; keepMine(); save(); paintBar();
      return say(mineMsg || `Updated "${old.name}".`);
    }
    if (!t) return;
    if (what === "apply") {
      const keep = hostValues(design);
      design = norm(t.design);
      for (const h of HOSTS) design[h.key] = t.keepProfile && t.design[h.key] ? h.normalize(t.design[h.key]) : keep[h.key];
      design.theme = `mine:${t.id}`; design.name = t.name; origin = { id: t.id, name: t.name }; mineMsg = "";
      changed(); return paint();
    }
    if (what === "rename") { renaming = id; return say(""); }
    if (what === "rename-no") { renaming = null; return say(""); }
    if (what === "rename-ok") {
      try { mine = UT.rename(mine, id, $("mine-rename").value); } catch (err) { return say(err.message); }
      renaming = null; if (origin?.id === id) origin.name = UT.find(mine, $("mine-rename").value).name; keepMine(); return say(mineMsg || "Renamed.");
    }
    if (what === "delete") {
      if (armed !== id) { armed = id; setTimeout(() => { if (armed === id) { armed = null; if (isOpen() && tab === "theme") paint(); } }, 4000); return paint(); }
      armed = null; mine = UT.remove(mine, id); keepMine();
      if (origin?.id === id) origin = null;
      if (design.theme === `mine:${id}`) { design.theme = "custom"; save(); paintBar(); }
      return say(mineMsg || `Deleted "${t.name}".`);
    }
  }
  pane.addEventListener("change", async (e) => {
    if (fromHost(e)) return;
    if (e.target.id === "design-preview") { setPreview(e.target.value); return paintBar(); }
    if (e.target.dataset.p === "name") { design.name = e.target.value; changed(); return paintBar(); }
    if (e.target.id === "mine-file" && e.target.files[0]) {
      try {
        const r = UT.merge(mine, UT.fromFile(await e.target.files[0].text()), hostKeys);
        mineMsg = "";
        mine = r.list; keepMine(); mineMsg = mineMsg || `Loaded ${r.added + r.replaced} theme${r.added + r.replaced === 1 ? "" : "s"} (${r.replaced} replaced).`;
      } catch (err) { mineMsg = "The file was not loaded: " + err.message + "."; }
      e.target.value = ""; return paint();
    }
    if (e.target.id !== "design-file" || !e.target.files[0]) return;
    try { set(D.fromFile(await e.target.files[0].text(), base, HOSTS)); $("design-where").textContent = `Loaded "${design.name}".`; }
    catch (err) { $("design-where").textContent = "The file was not loaded: " + err.message + "."; }
    e.target.value = "";
  });
  frame.addEventListener("tab", (e) => tabTo(e.detail.tab));
  frame.addEventListener("back", () => events.dispatchEvent(new CustomEvent("back")));
  if (link) $("design-link").onclick = () => link.onClick();

  function set(d) { design = norm(d); save(); schedule(0); announceSoon(); paint(); }
  /** A host value changed outside the panel (the duckOSM Export card changes the tile profile). */
  function setHost(key, value) {
    const h = HOSTS.find((x) => x.key === key);
    if (!h) throw new Error(`design panel: no host tab has the key ${key}`);
    design[key] = h.normalize(value);
    save(); if (isOpen()) paint(); else paintBar();
  }
  /** A stored design (the text of a file). A bad text keeps the design that is now. `draw: false` only gives the look to the host (the next draw has it). */
  async function load(text, { draw = true } = {}) {
    try { design = D.fromFile(text, base, HOSTS); } catch (_) { return false; }
    if (draw) { announceSoon(); schedule(0); }
    else { announce(); lastKey = styleKey(design); await redraw(lookText(lastKey), false); }
    paint();
    return true;
  }
  /** Read the base map again: the Preview control and the notice follow it. */
  function refresh() {
    const sel = $("design-preview");
    if (sel) sel.value = previewValue();
    paintBar();
  }
  /** A layer switched somewhere else (roadstyle's Layers box, the arrows switch): the design follows, and the panel paints nothing. */
  function setVisible(key, on) {
    if (!(key in design.visible) || design.visible[key] === !!on) return;
    design.visible[key] = !!on; design.theme = "custom";
    save(); paintBar(); if (isOpen() && tab === "layers") { const el = pane.querySelector(`[data-p="visible.${key}"]`); if (el) el.checked = !!on; }
  }
  // ---- open and close: the frame hides the host's title, body and "Collapse all", and shows them again ----
  const isOpen = frame.isOpen, close = frame.close;
  function open(name) {
    frame.open();
    name ? tabTo(name) : paint();
  }
  // the design that this browser kept: it is the design at the start (the host's look gets it, no draw)
  let stored = null;
  try { stored = localStorage.getItem(`${storageKey}.design`); } catch (_) { /* no storage: the default design */ }
  const restored = !!stored && await load(stored, { draw: false });
  paintBar();
  return Object.assign(events, {
    open, close, isOpen, tab: tabTo, get: () => design, text: () => D.toFile(design), set, load, setHost, refresh, base: () => base, restored,
    flush: async () => { clearTimeout(timer); await run(); while (busy) await new Promise((r) => setTimeout(r, 50)); },
    state: () => note,
  });
}

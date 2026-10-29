// The tool registry (docs/design/dashboard_templates.md, 3.2). A control module defines its tool (`defineTool`); a renderer reads the
// registry: the column here (the MapLibre corner, template `map` and `dashboard`), the bar in bar.js. A tool is {id, kind, el, ...}: `el`
// is the element with its buttons, `kind` is button, toggle, box or window. The page's calls are `rs.tools` (api.js).
import {map, _emit} from "./core.js";
// the default order of the bar and of the column; a page tool goes after these, and `attribution` is the last one of a bar
export const ORDER = ["theme", "zoom_in", "zoom_out", "compass", "view3d", "panel_show", "street_view", "google_3d", "basemap", "buildings", "legend"];
// the compass: a fixed ring, and a needle that turns with the map (the north half is solid and the south half is light, all in the text color; chosen
// 2026-10-29: a dial with ticks was too small to read at 20 px). MapLibre turns the whole icon element, so the page cancels that (dashboard.css) and turns the needle.
const COMPASS_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto"><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="1.8"/><g class="rs-needle"><path d="M12 4.6 15.7 12H8.3z" fill="currentColor"/><path d="M12 19.4 8.3 12h7.4z" fill="currentColor" opacity=".3"/></g></svg>';
// the icon of the tool `basemap`: three tilted sheets, the top one filled
export const LAYERS_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"><path d="M12 3 3 8l9 5 9-5-9-5z" fill="currentColor"/><path d="M3 12.5l9 5 9-5" fill="none"/><path d="M3 17l9 5 9-5" fill="none"/></svg>';
// the icon of the tool `buildings`
export const BUILDINGS_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="2" ' +
  'stroke-linejoin="round"><path d="M3 21h18M5 21V8l6-3v16M11 21V10l8 2v9"/><path d="M8 10v1M8 14v1M14 14v1M17 14v1"/></svg>';
const tools = new Map();                    // id -> {id, kind, el, title, group, open, close, isOpen, onClick}
const LAST = ["settings", "attribution"];               // the last tool of a bar
let sink = null;                            // the renderer that is mounted: a function that takes a list of tools
export function defineTool(id, kind, el, more = {}){
  const t = {id, kind, el, title: "", ...more};
  tools.set(id, t);
  if(sink) sink([t]);
  return t;
}
// the tools in the default order, then the page's tools in the order they were added, then `attribution`
export function toolList(){
  const known = ORDER.filter(id => tools.has(id)).map(id => tools.get(id));
  return [...known, ...[...tools.values()].filter(t => !ORDER.includes(t.id) && !LAST.includes(t.id)), ...LAST.filter(id => tools.has(id)).map(id => tools.get(id))];
}
export const getTool = id => tools.get(id);
// MapLibre's navigation control (zoom in, zoom out, compass) is the host's: its three buttons become three tools of the group "nav"
function adoptNav(){
  const c = map.getContainer().querySelector(".maplibregl-ctrl-zoom-in");
  const ctrl = c && c.closest(".maplibregl-ctrl");
  if(!ctrl) return;
  for(const [id, sel, title] of [["zoom_in", ".maplibregl-ctrl-zoom-in", "Zoom in"], ["zoom_out", ".maplibregl-ctrl-zoom-out", "Zoom out"],
                                 ["compass", ".maplibregl-ctrl-compass", "Reset bearing"]]){
    const b = ctrl.querySelector(sel);
    if(id === "compass" && b){                      // our ring and needle in place of MapLibre's pale picture; the needle turns with the map and leans with its tilt, the ring does not
      const icon = b.querySelector(".maplibregl-ctrl-icon");
      if(icon){
        icon.innerHTML = COMPASS_ICON;
        // the needle turns with the bearing and is foreshortened by the tilt (it lies flat, seen from a low angle); the ring stays as it is. At a very low
        // angle the needle keeps a third of its height, so it can still be seen
        const needle = icon.querySelector(".rs-needle");
        const turn = () => needle.setAttribute("transform", "translate(12 12) scale(1 " + Math.max(0.35, Math.cos(map.getPitch() * Math.PI / 180)).toFixed(3) + ") rotate(" + (-map.getBearing()) + ") translate(-12 -12)");
        map.on("rotate", turn); map.on("pitch", turn); turn();
      }
    }
    if(b) tools.set(id, {id, kind: "button", el: b, title, group: "nav"});
  }
  ctrl.remove();
}
export const wrap = el => {                  // a tool's element as a control (a group of buttons)
  if(el.classList.contains("maplibregl-ctrl")) return el;
  const d = document.createElement("div"); d.className = "maplibregl-ctrl maplibregl-ctrl-group"; d.appendChild(el); return d;
};
// the column: each tool is one control of the top-right corner, in the registry's order; the tools of one group share a box
function addToColumn(list){
  let box = null, group = null;
  for(const t of list){
    if(t.group && t.group === group){ box.appendChild(t.el); continue; }
    group = t.group || null;
    const el = t.group ? (box = wrap(t.el)) : wrap(t.el);
    map.addControl({onAdd(){ return el; }, onRemove(){}});
  }
}
// a renderer takes the tools once (`mount`), and each tool that is defined later
function mount(render){
  if(sink) return;
  adoptNav();
  sink = render;
  render(toolList());
}
export const mountColumn = () => mount(addToColumn);
export const mountTools = render => mount(render);
const info = t => ({id: t.id, kind: t.kind, title: t.title, open: t.isOpen ? !!t.isOpen() : null});
const need = id => { const t = tools.get(id); if(!t) throw new Error("rs.tools: no tool '" + id + "'"); return t; };
// rs.tools (window.rsTools is the alias): the page's calls
export const rsTools = {
  list: () => toolList().map(info),
  // a page tool: {id, title, icon (the HTML of its button), onClick}; it goes after the built-in ones
  add(spec){
    if(!spec || !spec.id) throw new Error("rs.tools.add: a tool needs an id");
    if(tools.has(spec.id)) throw new Error("rs.tools.add: the tool '" + spec.id + "' exists");
    const b = document.createElement("button"); b.type = "button"; b.title = spec.title || spec.id; b.innerHTML = spec.icon || spec.id[0].toUpperCase();
    const t = defineTool(spec.id, spec.kind || "button", b, {title: b.title, page: true, onClick: spec.onClick});
    b.onclick = e => { _emit("rs:toolchange", {id: t.id, state: "press"}); if(t.onClick) t.onClick(e); };
    return info(t);
  },
  // the page has added its tools: the bar shows (`toolbar.hold`)
  ready(){ document.dispatchEvent(new Event("rs:toolsready")); },
  // a tool of the page gets its behavior: {onClick}
  bind(id, spec){ const t = need(id); if(spec && spec.onClick) t.onClick = spec.onClick; return info(t); },
  remove(id){ const t = need(id), c = !t.group && t.el.closest(".maplibregl-ctrl"); (c || t.el).remove(); tools.delete(id); },
  open(id){ const t = need(id); if(t.open) t.open(); _emit("rs:toolchange", {id, state: "open"}); },
  close(id){ const t = need(id); if(t.close) t.close(); _emit("rs:toolchange", {id, state: "close"}); },
};

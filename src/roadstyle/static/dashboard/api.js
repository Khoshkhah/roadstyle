// the runtime API of the interaction contract (docs/design/rust_library.md, "The runtime API"): one object for a host page, over the
// window.rs* functions of the controls. Its ids are the roads' edge ids (as text: a 64-bit hash stays exact); the window.rs* functions
// take the row. The state is what the controls report (the rs:* events) and the camera; setState applies a part of it through the same
// functions as the controls, so the page and the host never disagree. The page sets window.rs to it.
import {map, O} from "./core.js";

const EVENTS = {select: "rs:select", deselect: "rs:deselect", filter: "rs:filterchange", color: "rs:colorchange", overlay: "rs:overlaychange",
                tunnel: "rs:tunnelchange", view: "rs:viewselect", view3d: "rs:viewchange", basemap: "rs:basemapchange", highlight: "rs:highlightchange",
                roadfill: "rs:roadfillchange", streetview: "rs:streetviewchange", google3d: "rs:google3dchange"};

export function makeApi(extra){
  let rowOf = null, edgeOf = null;                    // edge id <-> row, made on the first use (every road's properties, once)
  const index = () => {
    if(rowOf) return;
    const rows = window.rsQuery ? window.rsQuery(() => true) : [], props = window.rsGetProps ? window.rsGetProps(rows) : [];
    rowOf = new Map(); edgeOf = new Map();
    rows.forEach((r, i) => { const e = props[i] && props[i][O.edge_id_col]; const k = e == null ? String(r) : String(e); rowOf.set(k, r); edgeOf.set(r, k); });
  };
  document.addEventListener("rs:tableready", () => { rowOf = null; edgeOf = null; });   // the road table came after a first use
  const row = id => { index(); return rowOf.has(String(id)) ? rowOf.get(String(id)) : id; };
  const edge = r => { index(); return edgeOf.has(r) ? edgeOf.get(r) : (r == null ? null : String(r)); };
  const rows = ids => ids == null ? null : Array.from(ids, row);
  const filt = O.filter || {};
  const state = {v: 1, selection: null, highlight: [], colorBy: ((O.color_options || [])[O.color_active] || {}).name || null, colors: [],
                 filter: {classes: null, bridges: true, tunnels: true, access: [], ids: null}, overlays: {},
                 roadFill: !O.road_fill || O.road_fill.on !== false, tunnel: null, palette: null, view: null,
                 basemap: ((O.basemaps || [])[0] || {}).key || null, view3d: false, streetView: {mode: "off"}, google3d: false, panel: null};
  (O.overlays || []).forEach(o => { state.overlays[o.label] = {visible: o.visible !== false}; });
  if(O.tunnel && O.tunnel.layers && Object.keys(O.tunnel.layers).length)
    state.tunnel = {strength: O.tunnel.strength, toward: O.tunnel.toward, palette: O.tunnel.palette, ratio: O.tunnel.ratio};
  const listeners = new Map();                        // our own document listeners, for destroy()
  const fns = {};                                     // on(): the host's functions by event name
  const emit = (name, detail) => (fns[name] || []).forEach(f => { try{ f(detail); }catch(e){ console.error(e); } });
  const track = (type, fn) => { const h = e => { const part = fn(e.detail || {}); if(part) emit("state", part); }; document.addEventListener(type, h); listeners.set(type + ":" + listeners.size, [type, h]); };
  track("rs:select", d => d.overlay ? null : {selection: state.selection = edge(d.id)});
  track("rs:deselect", () => ({selection: state.selection = null}));
  track("rs:highlightchange", d => d.overlay ? null : {highlight: state.highlight = (d.ids || []).map(edge)});
  track("rs:colorchange", d => {
    if(d.option) return {colorBy: state.colorBy = d.option.name};
    if(d.base || d.overlay) return null;
    state.colors = d.groups ? d.groups.map(g => ({color: g.color, ids: (g.ids || []).map(edge)})) : (d.ids && d.color ? [{color: d.color, ids: d.ids.map(edge)}] : []);
    return {colors: state.colors};
  });
  track("rs:filterchange", d => {
    const f = state.filter;
    if(d.visible) f.classes = d.visible.slice();
    if("bridges" in d) f.bridges = !!d.bridges;
    if("tunnels" in d) f.tunnels = !!d.tunnels;
    if("access" in d && window.rsGetAccess){ const a = window.rsGetAccess(); f.access = Object.keys(a).filter(k => !a[k]); }
    if("ids" in d && !d.overlay) f.ids = d.ids == null ? null : d.ids.map(edge);
    return {filter: f};
  });
  track("rs:overlaychange", d => { state.overlays[d.overlay] = {...(state.overlays[d.overlay] || {}), visible: !!d.visible}; return {overlays: state.overlays}; });
  track("rs:roadfillchange", d => ({roadFill: state.roadFill = !!d.road_fill}));
  track("rs:tunnelchange", d => ({tunnel: state.tunnel = {strength: d.strength, toward: d.toward, palette: d.palette, ratio: d.ratio}}));
  track("rs:viewselect", d => ({view: state.view = d.view}));
  track("rs:basemapchange", d => ({basemap: state.basemap = d.basemap}));
  track("rs:viewchange", d => ({view3d: state.view3d = !!d.view3d}));
  track("rs:streetviewchange", d => ({streetView: state.streetView = {mode: d.open ? "window" : "off"}}));
  track("rs:google3dchange", d => ({google3d: state.google3d = !!d.open}));
  const call = (name, ...a) => { if(typeof window[name] === "function") return window[name](...a); };
  const camera = () => { if(!map) return null; const c = map.getCenter(); return {center: [c.lng, c.lat], zoom: map.getZoom(), pitch: map.getPitch(), bearing: map.getBearing()}; };
  const KEYS = ["selection", "highlight", "colorBy", "colors", "filter", "overlays", "roadFill", "tunnel", "view", "basemap", "view3d", "camera",
                "streetView", "google3d", "panel"];
  const api = {
    contract: 1,
    select(id){ if(id == null) call("rsDeselect"); else call("rsSelect", row(id)); },
    highlight(ids){ call("rsHighlight", rows(ids) || []); },
    focus(ids){ call("rsFocus", rows(Array.isArray(ids) ? ids : [ids])); },
    query(where){ const w = where || {}; return (call("rsQuery", p => Object.keys(w).every(k => p[k] === w[k])) || []).map(edge); },
    find(text){ return (call("rsFind", text) || []).map(edge); },
    props(id){ const p = call("rsGetProps", [row(id)]); return p && p.length ? p[0] : null; },
    setColorBy(name){ call("rsSetColorField", name); },
    color(groups){ if(!groups || !groups.length) call("rsColor", null); else call("rsColor", groups.map(g => [rows(g.ids), g.color])); },
    setFilter(f){
      const x = f || {};
      if("classes" in x) call("rsSetClasses", x.classes == null ? (filt.classes || []) : x.classes);
      if("bridges" in x) call("rsSetBridges", !!x.bridges);
      if("tunnels" in x) call("rsSetTunnels", !!x.tunnels);
      if("access" in x && window.rsGetAccess){ const off = new Set(x.access || []); Object.keys(window.rsGetAccess()).forEach(k => call("rsSetAccess", k, !off.has(k))); }
      if("ids" in x) call("rsFilter", rows(x.ids));
    },
    setOverlay(name, visible){ call("rsSetOverlay", name, !!visible); },
    setTunnelStyle(look){ call("rsSetTunnelStyle", look || {}); },
    setView(name){ call("rsSetView", name); },
    setBasemap(key){ call("rsSetBasemap", key); },
    getState(){ return JSON.parse(JSON.stringify({...state, camera: camera()})); },
    // a part of the state: a saved view, a URL (#rs=); each key through the function of its control
    setState(change){
      const c = change || {};
      if("camera" in c && c.camera && map) map.jumpTo(c.camera);
      if("basemap" in c && c.basemap != null) api.setBasemap(c.basemap);
      if("view" in c && c.view != null) api.setView(c.view);
      if("colorBy" in c && c.colorBy != null) api.setColorBy(c.colorBy);
      if("colors" in c) api.color(c.colors);
      if("filter" in c) api.setFilter(c.filter);
      if("overlays" in c) Object.entries(c.overlays || {}).forEach(([n, o]) => api.setOverlay(n, o.visible));
      if("roadFill" in c) call("rsSetRoadFill", !!c.roadFill);
      if("tunnel" in c && c.tunnel) api.setTunnelStyle(c.tunnel);
      if("view3d" in c) call("rsSetView3D", !!c.view3d);
      if("streetView" in c) call("rsSetStreetView", !!c.streetView && c.streetView.mode !== "off");
      if("google3d" in c) call("rsSetGoogle3D", !!c.google3d);
      if("panel" in c && c.panel != null) call("rsPanelShow", !!c.panel);
      if("highlight" in c) api.highlight(c.highlight || []);
      if("selection" in c) api.select(c.selection);
    },
    // false for a change that needs an engine (a colour option the style does not have); this page has no engine port for it
    can(change){
      const c = change || {};
      if(Object.keys(c).some(k => !KEYS.includes(k))) return false;
      if("colorBy" in c && c.colorBy != null && !(O.color_options || []).some(o => o.name === c.colorBy)) return false;
      return true;
    },
    // the part of the state that differs from the start, as a URL fragment (#rs= and base64url JSON)
    link(){
      const now = api.getState(), out = {};
      for(const k of KEYS) if(JSON.stringify(now[k]) !== JSON.stringify(start[k])) out[k] = now[k];
      return "#rs=" + btoa(unescape(encodeURIComponent(JSON.stringify(out)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    },
    on(event, fn){
      if(event !== "state" && !(event in EVENTS)) throw new Error("rs.on: one of state, " + Object.keys(EVENTS).join(", "));
      (fns[event] = fns[event] || []).push(fn);
      let h = null;
      if(event !== "state"){ h = e => fn(e.detail || {}); document.addEventListener(EVENTS[event], h); }
      return () => { fns[event] = (fns[event] || []).filter(f => f !== fn); if(h) document.removeEventListener(EVENTS[event], h); };
    },
    destroy(){ listeners.forEach(([type, h]) => document.removeEventListener(type, h)); listeners.clear(); Object.keys(fns).forEach(k => delete fns[k]); },
    ...extra,
  };
  const start = api.getState();
  return api;
}

// a URL with #rs=: the state it names, once the map is loaded
export function fromUrl(api){
  const m = /[#&]rs=([A-Za-z0-9_-]+)/.exec(location.hash || "");
  if(!m || !map) return;
  try{
    const s = JSON.parse(decodeURIComponent(escape(atob(m[1].replace(/-/g, "+").replace(/_/g, "/")))));
    const go = () => api.setState(s);
    if(map.loaded()) go(); else map.once("load", go);
  }catch(e){ console.warn("roadstyle: #rs= is not a state", e); }
}

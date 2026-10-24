// The code panel: the render_edges(...), render_dashboard(...) or render_report(...) call that makes the page of the knobs, as Python text
// (the same text as the Python studio, src/roadstyle/studio/), so a user can copy it when the knobs are not enough.

// a JSON value as Python writes it with repr(): strings in single quotes, True / False / None
export function pyrepr(v){
  if(v === null || v === undefined) return "None";
  if(v === true) return "True";
  if(v === false) return "False";
  if(typeof v === "number") return Number.isInteger(v) ? String(v) : String(v);
  if(typeof v === "string") return "'" + v.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
  if(Array.isArray(v)) return "[" + v.map(pyrepr).join(", ") + "]";
  if(v instanceof Map) return "{" + [...v].map(([k, x]) => pyrepr(k) + ": " + pyrepr(x)).join(", ") + "}";   // keys of any type (a number, a bool)
  return "{" + Object.entries(v).map(([k, x]) => pyrepr(k) + ": " + pyrepr(x)).join(", ") + "}";
}

// kw: the keywords in the order of the knobs; loader: the line that reads the edges; overlays: [{path, args}] (args: Python text);
// fn: the call (render_edges, render_dashboard, render_report); file: the saved page's name
export function pythonCode(kw, loader, overlays, fn = "render_edges", file = "map.html"){
  const ovs = "[" + overlays.map((_, i) => `ov${i}`).join(", ") + "]";
  const args = Object.entries(kw).map(([k, v]) => `,\n                     ${k}=${k === "overlays" ? ovs : pyrepr(v)}`).join("");
  const prelude = !overlays.length ? loader
    : "import geopandas as gpd\n\n" + loader + "\n" + overlays.map((o, i) => `ov${i} = rs.Overlay(gpd.read_file(${pyrepr(o.path)}), ${o.args})`).join("\n");
  return `import roadstyle as rs\n\n${prelude}\nwm = rs.${fn}(edges${args})\nwm.save(${pyrepr(file)})`;
}

// The code panel: the render_edges(...) call that makes the map of the knobs, as Python text (the same text as the Python studio,
// src/roadstyle/studio/map.py), so a user can copy it when the knobs are not enough.

// a JSON value as Python writes it with repr(): strings in single quotes, True / False / None
export function pyrepr(v){
  if(v === null || v === undefined) return "None";
  if(v === true) return "True";
  if(v === false) return "False";
  if(typeof v === "number") return Number.isInteger(v) ? String(v) : String(v);
  if(typeof v === "string") return "'" + v.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
  if(Array.isArray(v)) return "[" + v.map(pyrepr).join(", ") + "]";
  return "{" + Object.entries(v).map(([k, x]) => pyrepr(k) + ": " + pyrepr(x)).join(", ") + "}";
}

// kw: render_edges' keywords in the order of the knobs; loader: the line that reads the edges; overlays: [{path, args}] (args: Python text)
export function pythonCode(kw, loader, overlays){
  const ovs = "[" + overlays.map((_, i) => `ov${i}`).join(", ") + "]";
  const args = Object.entries(kw).map(([k, v]) => `,\n                     ${k}=${k === "overlays" ? ovs : pyrepr(v)}`).join("");
  const prelude = !overlays.length ? loader
    : "import geopandas as gpd\n\n" + loader + "\n" + overlays.map((o, i) => `ov${i} = rs.Overlay(gpd.read_file(${pyrepr(o.path)}), ${o.args})`).join("\n");
  return `import roadstyle as rs\n\n${prelude}\nwm = rs.render_edges(edges${args})\nwm.save("map.html")`;
}

// The SVG helper of a page's charts (docs/guides/dashboard-panel.md): `rs.svg(parent, tag, attrs, text?)` makes one SVG element, sets its attributes and appends it.
// An SVG attribute does not read `var(--x)`, a style does: a value that starts with `var(` goes to the style, so a chart can use the theme's colours
// (`fill: "var(--rs-chart-band)"`, `stroke: "var(--line)"`) and follows the light and the dark theme with no code of its own.
const _svNS = "http://www.w3.org/2000/svg";
export function rsSvg(parent, tag, attrs, text){
  const e = document.createElementNS(_svNS, tag);
  for(const k in attrs || {}){
    const v = attrs[k];
    if(typeof v === "string" && v.startsWith("var(")) e.style.setProperty(k, v); else e.setAttribute(k, v);
  }
  if(text !== undefined) e.textContent = text;
  if(parent) parent.appendChild(e);
  return e;
}

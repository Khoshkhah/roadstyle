// The page's theme: <html data-rs-theme="light|dark">, which the popup, the tooltip and (later) the bar read (popup.css, dashboard.css).
// A sidebar of a template keeps its own switch (`data-theme` on #sb); this follows it. rsSetTheme(name) sets both.
export function rsSetTheme(name){
  const dark = name === "dark", root = document.documentElement;
  if(root.dataset.rsTheme === (dark ? "dark" : "light")) return;
  root.dataset.rsTheme = dark ? "dark" : "light";
  for(const el of document.querySelectorAll("#sb")) if(el.dataset.theme !== root.dataset.rsTheme) el.dataset.theme = root.dataset.rsTheme;
  document.dispatchEvent(new CustomEvent("rs:themechange", {detail: {theme: root.dataset.rsTheme}}));
}
export function initTheme(){
  window.rsSetTheme = rsSetTheme;
  document.documentElement.dataset.rsTheme = "light";
  // a base map with a dark twin (`dark` in data/basemaps.json) follows the theme: the twin in the dark theme, the light map again in the
  // light theme; and a dark base map that the person picks turns the page dark
  let current = null;         // the base map now: the first of the list (the page's own) until a change; the list is not there yet when this runs
  document.addEventListener("rs:basemapchange", e => {
    current = (window.RS_BASEMAPS || []).find(b => b.key === e.detail.basemap) || current;
    if(current && current.is_dark) rsSetTheme("dark");
  });
  document.addEventListener("rs:themechange", e => {
    const all = window.RS_BASEMAPS || [];
    current = current || all[0] || null;
    if(!current || !window.rsSetBasemap) return;
    if(e.detail.theme === "dark" && current.dark) window.rsSetBasemap(current.dark);
    else if(e.detail.theme === "light"){ const light = all.find(b => b.dark === current.key); if(light) window.rsSetBasemap(light.key); }
  });
  // the sidebar is injected after this script runs: look for it when the page is parsed
  const follow = () => {
    for(const el of document.querySelectorAll("#sb")){
      const mirror = () => { const t = el.dataset.theme === "dark" ? "dark" : "light"; if(document.documentElement.dataset.rsTheme !== t) rsSetTheme(t); };
      new MutationObserver(mirror).observe(el, {attributes: true, attributeFilter: ["data-theme"]});
      mirror();
    }
  };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", follow) : follow();
}

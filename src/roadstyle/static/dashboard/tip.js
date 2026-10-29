// The explanation of a button (docs/design/dashboard_templates.md, 3.3): the browser draws a `title` itself, in the system's style, so the page
// takes the `title` of a button of the bar, the boxes, the panels and the windows when the pointer comes (or the key focus), keeps its text in
// `data-rs-tip` and shows it in a box of the page's look. The box opens on the side of the button that faces the map's center, after 350 ms.
const _tpScope = ["#rs-toolbar", ".bm-menu", "#rs-attr-box", "#rs-color-box", "#rs-settings-box", "#sb", "#rp", ".rs-side", ".rs-svw", "#rs-show-right", "#sb-show", "#rp-show"].join(",");
let _tpBox = null, _tpTimer = 0, _tpFor = null;
function _tpTake(el){                                  // the text of the explanation: the `title`, moved
  if(el.hasAttribute("title")){
    const t = el.getAttribute("title");
    if(t){ el.dataset.rsTip = t; if(!el.getAttribute("aria-label") && !el.textContent.trim()) el.setAttribute("aria-label", t); }
    el.removeAttribute("title");
  }
  return el.dataset.rsTip || "";
}
function _tpHide(){ clearTimeout(_tpTimer); _tpFor = null; if(_tpBox) _tpBox.hidden = true; }
function _tpShow(el){
  const text = _tpTake(el); if(!text || !document.body.contains(el)) return;
  if(!_tpBox){ _tpBox = document.createElement("div"); _tpBox.id = "rs-tip"; _tpBox.setAttribute("role", "tooltip"); document.body.append(_tpBox); }
  _tpBox.textContent = text; _tpBox.hidden = false; _tpFor = el;
  _tpBox.style.left = "0px"; _tpBox.style.top = "0px";      // measured at the corner: a box that still stands where the last one was has less room, wraps narrower, and grows over the bar when it moves
  const r = el.getBoundingClientRect(), t = _tpBox.getBoundingClientRect(), gap = 8;
  const bar = el.closest("#rs-toolbar"), edge = bar ? bar.dataset.edge : "top";
  // the side that faces the map's center: a bar at the right opens its explanations to the left, and so on
  let x, y;
  const side = {right: "left", left: "right", top: "bottom", bottom: "top"}[edge] || "top";
  if(side === "left"){ x = r.left - t.width - gap; y = r.top + (r.height - t.height) / 2; }
  else if(side === "right"){ x = r.right + gap; y = r.top + (r.height - t.height) / 2; }
  else if(side === "bottom"){ x = r.left + (r.width - t.width) / 2; y = r.bottom + gap; }
  else { x = r.left + (r.width - t.width) / 2; y = r.top - t.height - gap; if(y < 8) y = r.bottom + gap; }
  _tpBox.style.left = Math.max(8, Math.min(innerWidth - t.width - 8, x)) + "px";
  _tpBox.style.top = Math.max(8, Math.min(innerHeight - t.height - 8, y)) + "px";
}
export function initTip(){
  const near = e => { const el = e.target.closest && e.target.closest("[title], [data-rs-tip]"); return el && el.closest(_tpScope) ? el : null; };
  document.addEventListener("pointerover", e => {
    if(e.pointerType === "touch") return;
    const el = near(e); if(!el || el === _tpFor) return;
    _tpTake(el);                                       // the native tooltip must not start
    _tpHide(); _tpFor = el; _tpTimer = setTimeout(() => _tpShow(el), 350);
  }, true);
  document.addEventListener("pointerout", e => { if(_tpFor && !(e.relatedTarget && _tpFor.contains(e.relatedTarget))) _tpHide(); }, true);
  document.addEventListener("focusin", e => { const el = near(e); if(el && e.target.matches(":focus-visible")) _tpShow(el); }, true);
  document.addEventListener("focusout", _tpHide, true);
  document.addEventListener("pointerdown", _tpHide, true);
  document.addEventListener("keydown", e => { if(e.key === "Escape") _tpHide(); }, true);
  addEventListener("scroll", _tpHide, true);
}

// The explanation of a button (docs/design/dashboard_templates.md, 3.3): the browser draws a `title` itself, in the system's style, so the page
// takes the `title` of a button of the bar, the boxes, the panels and the windows when the pointer comes (or the key focus), keeps its text in
// `data-rs-tip` and shows it in a box of the page's look. The box opens on the side of the button that faces the map's center, after 350 ms, and never over
// the button: the first side where it does not cover the button (the order: the side that faces the center, below, above, right, left). A button or a link that
// has a text of its own (the panel's "Build", a tab) shows no box: its text already says what it does, so a box would only cover it; its `title` becomes its
// accessible description (`aria-description`). A tool of the bar has a box always (an icon, or "3D"), and an icon button keeps its `aria-label`.
const _tpScope = ["#rs-toolbar", "#rs-scalebox", ".bm-menu", "#rs-attr-box", "#rs-color-box", "#rs-settings-box", "#sb", "#rp", ".rs-side", ".rs-svw", "#rs-show-right", "#sb-show", "#rp-show"].join(",");
let _tpBox = null, _tpTimer = 0, _tpFor = null;
// a button or a link with a text of its own, outside the bar: its text says what it does
const _tpSays = el => !el.closest("#rs-toolbar, #rs-scalebox") && el.matches("button, a, summary, [role=button], [role=tab], input[type=button], input[type=submit]") && el.textContent.trim().length >= 2;
function _tpTake(el){                                  // the text of the explanation: the `title`, moved
  if(el.hasAttribute("title")){
    const t = el.getAttribute("title");
    if(t){
      el.dataset.rsTip = t;
      if(_tpSays(el)){ if(!el.hasAttribute("aria-description")) el.setAttribute("aria-description", t); }       // the text is the name; the title describes it
      else if(!el.getAttribute("aria-label") && !el.textContent.trim()) el.setAttribute("aria-label", t);
    }
    el.removeAttribute("title");
  }
  return el.dataset.rsTip || "";
}
function _tpHide(){ clearTimeout(_tpTimer); _tpFor = null; if(_tpBox) _tpBox.hidden = true; }
// a button whose box is open shows no explanation: the box is what the person looks at, and the explanation would lie over it
const _tpIn = ["#rs-attr-box", "#rs-color-box", "#rs-nav-box", "#rs-roads-box", "#rs-settings-box", ".bm-menu"].join(",");       // the boxes of the bar: what is inside a box keeps its explanations
const _tpOpenBox = el => { if(el.closest(_tpIn)) return false; const w = el.closest(".maplibregl-ctrl"); return !!(w && w.querySelector("#rs-attr-box:not([hidden]), #rs-color-box:not([hidden]), #rs-nav-box:not([hidden]), #rs-roads-box:not([hidden]), #rs-settings-box:not([hidden]), .bm-menu.open")); };
function _tpShow(el){
  const text = _tpTake(el); if(!text || !document.body.contains(el) || _tpOpenBox(el) || _tpSays(el)) return;
  if(!_tpBox){ _tpBox = document.createElement("div"); _tpBox.id = "rs-tip"; _tpBox.setAttribute("role", "tooltip"); document.body.append(_tpBox); }
  _tpBox.textContent = text; _tpBox.hidden = false; _tpFor = el;
  _tpBox.style.left = "0px"; _tpBox.style.top = "0px";      // measured at the corner: a box that still stands where the last one was has less room, wraps narrower, and grows over the bar when it moves
  const r = el.getBoundingClientRect(), t = _tpBox.getBoundingClientRect(), gap = 8;
  const bar = el.closest("#rs-toolbar"), edge = bar ? bar.dataset.edge : "top";
  // the side that faces the map's center: a bar at the right opens its explanations to the left, and so on
  const first = {right: "left", left: "right", top: "bottom", bottom: "top"}[edge] || "top";
  const at = {
    bottom: [r.left + (r.width - t.width) / 2, r.bottom + gap], top: [r.left + (r.width - t.width) / 2, r.top - t.height - gap],
    right: [r.right + gap, r.top + (r.height - t.height) / 2], left: [r.left - t.width - gap, r.top + (r.height - t.height) / 2],
  };
  const inside = ([x, y]) => [Math.max(8, Math.min(innerWidth - t.width - 8, x)), Math.max(8, Math.min(innerHeight - t.height - 8, y))];
  const over = ([x, y]) => x < r.right && x + t.width > r.left && y < r.bottom && y + t.height > r.top;      // the box would cover the button
  const spots = [first, "bottom", "top", "right", "left"].map(s => inside(at[s]));
  const [x, y] = spots.find(s => !over(s)) || spots[0];
  _tpBox.style.left = x + "px";
  _tpBox.style.top = y + "px";
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

// The hover box of a page (docs/guides/dashboard-panel.md): the words that a page shows near the pointer over its own chart or its own map layer.
// `rs.hover.show(html, event)` puts the box beside the pointer (it flips to the other side at an edge), `rs.hover.hide()` takes it away, and
// `rs.hover.on(node, html | fn)` does both for a node: the text, or a function of the event, shows while the pointer moves over it. The box has the look
// of the popup (the box token, the blur, the border) in both themes, and it never takes the pointer. The text is HTML of the page's own.
let _hvBox = null;
function _hvEl(){
  if(!_hvBox){ _hvBox = document.createElement("div"); _hvBox.id = "rs-hover"; _hvBox.setAttribute("role", "tooltip"); _hvBox.hidden = true; document.body.append(_hvBox); }
  return _hvBox;
}
export const rsHover = {
  show(html, ev){
    const b = _hvEl(); b.innerHTML = html; b.hidden = false;
    b.style.left = "0px"; b.style.top = "0px";                // measured at the corner: a box that still stands where the last one was wraps narrower
    const t = b.getBoundingClientRect(), x = ev.clientX, y = ev.clientY, gap = 14;
    b.style.left = Math.max(8, x + gap + t.width > innerWidth - 8 ? x - gap - t.width : x + gap) + "px";
    b.style.top = Math.max(8, y + gap + t.height > innerHeight - 8 ? y - gap - t.height : y + gap) + "px";
  },
  hide(){ if(_hvBox) _hvBox.hidden = true; },
  on(node, what){
    node.addEventListener("mousemove", ev => { const h = typeof what === "function" ? what(ev) : what; h == null ? rsHover.hide() : rsHover.show(h, ev); });
    node.addEventListener("mouseleave", rsHover.hide);
  },
};

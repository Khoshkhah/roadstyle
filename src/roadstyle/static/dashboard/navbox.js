// The tool `navigate` (toolbar.navigation = "box"; docs/design/dashboard_templates.md, 3.2): the one button for the map's view. Its icon is the compass: the needle turns with the map and
// flattens with the tilt. A click opens one box of the bar: a zoom slider (with - and + at its ends), a turn slider, a tilt slider
// and a reset button. The compass is the quick way (drag: turn and tilt; click: reset); this box gives the exact angles, and it is what a touch screen can use.
// The sliders follow the map when it moves, and they move it with no animation.
import {map, O} from "./core.js";
import {defineTool, wrap, COMPASS_ICON, animateNeedle} from "./tools.js";

export function initNavBox(){
  if(!(O.dashboard && O.dashboard.toolbar && O.dashboard.toolbar.navigation === "box")) return;       // the other way: the buttons (zoom, compass, 2D/3D)
  const b = document.createElement("button"), d = wrap(b), box = document.createElement("div"), maxPitch = (map.getMaxPitch && map.getMaxPitch()) || 70;
  b.type = "button"; b.title = "Navigate: zoom, turn and tilt (Ctrl + drag on the map turns and tilts it)"; b.innerHTML = COMPASS_ICON; animateNeedle(b);
  d.classList.add("rs-nav-ctrl"); box.id = "rs-nav-box"; box.hidden = true; d.appendChild(box);
  box.innerHTML = '<div class="rs-bm-h">Navigate</div>' +
    '<div class="rs-nb-row"><span>Zoom</span><div class="rs-nb-zoom"><button type="button" data-z="-1" aria-label="Zoom out">&minus;</button>' +
    '<input data-k="z" type="range" min="0" max="22" step="0.1" aria-label="Zoom"><button type="button" data-z="1" aria-label="Zoom in">+</button></div><b data-v="z"></b></div>' +
    '<div class="rs-nb-row"><span>Turn</span><input data-k="b" type="range" min="-180" max="180" step="1" aria-label="Turn"><b data-v="b"></b></div>' +
    '<div class="rs-nb-row"><span>Tilt</span><input data-k="p" type="range" min="0" max="' + maxPitch + '" step="1" aria-label="Tilt"><b data-v="p"></b></div>' +
    '<button type="button" class="rs-nb-reset">North up, flat</button><div class="rs-nb-hint">Ctrl + drag on the map: turn and tilt</div>';
  const q = s => box.querySelector(s), z = q('[data-k=z]'), t = q('[data-k=b]'), p = q('[data-k=p]');
  const sync = () => {
    z.value = map.getZoom(); t.value = Math.round(((map.getBearing() + 540) % 360) - 180); p.value = Math.round(map.getPitch());
    q('[data-v=z]').textContent = map.getZoom().toFixed(1); q('[data-v=b]').textContent = t.value + "°"; q('[data-v=p]').textContent = p.value + "°";
  };
  map.on("move", sync); sync();
  z.oninput = () => map.jumpTo({zoom: +z.value});
  t.oninput = () => map.jumpTo({bearing: +t.value});
  p.oninput = () => map.jumpTo({pitch: +p.value});
  box.querySelectorAll("button[data-z]").forEach(x => { x.onclick = () => map.easeTo({zoom: map.getZoom() + (+x.dataset.z), duration: 200}); });
  q(".rs-nb-reset").onclick = () => map.easeTo({bearing: 0, pitch: 0, duration: 300});
  const open = () => { sync(); box.hidden = false; };
  b.onclick = e => { e.stopPropagation(); box.hidden ? open() : (box.hidden = true); };
  box.addEventListener("click", e => e.stopPropagation());                 // a click inside the box does not close it
  defineTool("navigate", "box", d, {title: b.title, open, close: () => { box.hidden = true; }, isOpen: () => !box.hidden});
}

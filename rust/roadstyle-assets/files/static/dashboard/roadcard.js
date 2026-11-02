// The part "road_card" (docs/guides/dashboard-panel.md): the selected road's fields, from the event rs:select, whether the click came from the
// map or from a list; with the interactive overlays under the click (the zone that a road lies in). A page adds it with `{id, part: "road_card",
// fields}` (fields: the columns that it shows; none: every column). It is one handler of the click: the popup (`road_popup`) is another.
import {_esc} from "../popup.js";
import {_both} from "./select.js";
import {_ovSections} from "./overlays.js";
const _RC_EMPTY = '<span class="rs-road-card-none">Click a road.</span>';
export function roadCardPart(spec){
  const w = document.createElement("div"); w.className = "rs-road-card"; w.innerHTML = _RC_EMPTY;
  const only = spec.fields || null;
  document.addEventListener("rs:select", e => {
    if(!w.isConnected) return;                       // the section was removed
    const d = e.detail;
    w.innerHTML = (d.overlay ? '<div class="rs-road-card-ov">' + _esc(d.overlay) + "</div>" : "") + _both(d.properties || {}, true, only) + _ovSections(d.overlays);
  });
  document.addEventListener("rs:deselect", () => { if(w.isConnected) w.innerHTML = _RC_EMPTY; });
  return w;
}

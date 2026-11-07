// A colour picker in the look of the boxes (docs/guides/dashboard-parts.md, "A colour picker"). The browser draws its own picker (its window, its
// corners and its colours are the system's), so the `<input type="color">` of a panel stays in the page, hidden, and a swatch button and a box take its
// place, as the select box does for a `<select>`. The page's code still reads and sets `input.value` and `disabled`, and hears `input` (while the person
// drags) and `change` (when the person is done): the button follows. The box has a square for the saturation and the lightness, a hue bar, the old and
// the new colour, a hex field, the colours used last, and an eyedropper where the browser has one (window.EyeDropper).
const _cpHex = /^#[0-9a-f]{6}$/i;
let _cpOpen = null;                                   // {close}: the box that is open (one at a time)
const _cpRecent = [];                                 // the colours that this page used last, newest first
const _cpClamp = (v, a, b) => Math.min(b, Math.max(a, v));
// hex <-> hsv (h 0..360, s and v 0..1)
function _cpToHsv(hex){
  const n = parseInt(hex.slice(1), 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if(d) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return {h: (h * 60 + 360) % 360, s: mx ? d / mx : 0, v: mx};
}
function _cpToHex({h, s, v}){
  const f = k => { const x = (k + h / 60) % 6; return v - v * s * Math.max(0, Math.min(x, 4 - x, 1)); };
  return "#" + [f(5), f(3), f(1)].map(c => Math.round(c * 255).toString(16).padStart(2, "0")).join("");
}
function _cpEnhance(inp){
  if(inp.dataset.rsCp) return;
  inp.dataset.rsCp = "1";
  const wrap = document.createElement("span"), btn = document.createElement("button"), chip = document.createElement("span");
  wrap.className = "rs-cp"; btn.type = "button"; btn.className = "rs-cp-btn"; chip.className = "rs-cp-sw";
  btn.setAttribute("aria-haspopup", "dialog"); btn.setAttribute("aria-expanded", "false");
  btn.append(chip); inp.after(wrap); wrap.append(btn, inp); inp.classList.add("rs-cp-native");
  const name = inp.getAttribute("aria-label") || inp.title || (inp.closest("label") && inp.closest("label").textContent.trim()) || "Colour";
  inp.removeAttribute("title");                       // the button has the name; the hidden input has no tip
  const sync = () => { chip.style.background = inp.value; btn.setAttribute("aria-label", name + ": " + inp.value); btn.disabled = inp.disabled; };
  // the page sets `value` and `disabled` from its code: the button follows
  const pv = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  Object.defineProperty(inp, "value", {get(){ return pv.get.call(inp); }, set(v){ pv.set.call(inp, v); sync(); }, configurable: true});
  const pd = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "disabled");
  Object.defineProperty(inp, "disabled", {get(){ return pd.get.call(inp); }, set(v){ pd.set.call(inp, v); sync(); }, configurable: true});
  let box = null, hsv = null, old = "";
  const emit = type => inp.dispatchEvent(new Event(type, {bubbles: true}));
  const set = (hex, live = true) => { pv.set.call(inp, hex); sync(); paint(); if(live) emit("input"); };
  function paint(){
    if(!box) return;
    const hex = inp.value;
    box.querySelector(".rs-cp-sv").style.background = `linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, hsl(${hsv.h} 100% 50%))`;
    Object.assign(box.querySelector(".rs-cp-dot").style, {left: hsv.s * 100 + "%", top: (1 - hsv.v) * 100 + "%", background: hex});
    Object.assign(box.querySelector(".rs-cp-hue i").style, {left: hsv.h / 360 * 100 + "%", background: `hsl(${hsv.h} 100% 50%)`});
    box.querySelector(".rs-cp-new").style.background = hex;
    const f = box.querySelector(".rs-cp-hex"); if(document.activeElement !== f) f.value = hex;
  }
  const close = (commit = true) => {
    if(!box) return;
    box.remove(); box = null; btn.setAttribute("aria-expanded", "false"); _cpOpen = null;
    document.removeEventListener("pointerdown", away, true); document.removeEventListener("keydown", keys, true);
    removeEventListener("resize", place); window.removeEventListener("scroll", place, true);
    if(commit && inp.value !== old){
      emit("change");
      const i = _cpRecent.indexOf(inp.value); if(i >= 0) _cpRecent.splice(i, 1);
      _cpRecent.unshift(inp.value); _cpRecent.length = Math.min(_cpRecent.length, 8);
    }
  };
  const away = e => { if(box && !box.contains(e.target) && !btn.contains(e.target)) close(); };
  const keys = e => {
    if(!box) return;
    if(e.key === "Escape"){ e.preventDefault(); set(old); close(false); btn.focus(); }      // Escape: back to the colour before the box opened
    else if(e.key === "Enter" && !e.target.matches(".rs-cp-hex")){ e.preventDefault(); close(); btn.focus(); }
  };
  // the box at the button: below it, or above it when there is no room below; inside the window
  function place(){
    if(!box) return;
    const r = btn.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
    const up = innerHeight - r.bottom - 8 < h && r.top > innerHeight - r.bottom;
    box.style.left = _cpClamp(r.left, 8, innerWidth - w - 8) + "px";
    box.style.top = (up ? Math.max(8, r.top - h - 6) : Math.min(innerHeight - h - 8, r.bottom + 6)) + "px";
  }
  // a drag on the square or on the hue bar: pointer capture, so the drag goes on outside the box
  const drag = (el, at) => {
    el.addEventListener("pointerdown", e => {
      e.preventDefault(); el.setPointerCapture(e.pointerId); el.focus();
      const move = ev => { const r = el.getBoundingClientRect(); at(_cpClamp((ev.clientX - r.left) / r.width, 0, 1), _cpClamp((ev.clientY - r.top) / r.height, 0, 1)); };
      move(e); el.onpointermove = move; el.onpointerup = () => { el.onpointermove = el.onpointerup = null; };
    });
  };
  function open(){
    if(inp.disabled) return;
    if(_cpOpen) _cpOpen.close();
    old = inp.value; hsv = _cpToHsv(_cpHex.test(old) ? old : "#000000");
    box = document.createElement("div"); box.className = "rs-cp-box"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", name);
    const recent = _cpRecent.filter(c => c !== old);
    box.innerHTML = '<div class="rs-cp-sv" tabindex="0" role="slider" aria-label="Saturation and lightness"><span class="rs-cp-dot"></span></div>'
      + '<div class="rs-cp-row">' + (window.EyeDropper ? '<button type="button" class="rs-cp-eye" aria-label="Pick a colour from the screen">'
        + '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m2 22 1-1h3l9-9"/><path d="M3 21v-3l9-9"/><path d="m15 6 3.4-3.4a2.1 2.1 0 1 1 3 3L18 9l.4.4a2.1 2.1 0 1 1-3 3l-3.8-3.8a2.1 2.1 0 1 1 3-3l.4.4Z"/></svg></button>' : "")
      + '<span class="rs-cp-pair"><button type="button" class="rs-cp-sw rs-cp-old" aria-label="The colour before: click to go back"></button><span class="rs-cp-sw rs-cp-new"></span></span>'
      + '<div class="rs-cp-hue" tabindex="0" role="slider" aria-label="Hue"><i></i></div></div>'
      + '<div class="rs-cp-row"><label class="rs-cp-hexl">Hex<input class="rs-cp-hex" spellcheck="false" maxlength="7"></label></div>'
      + (recent.length ? '<div class="rs-cp-recent" aria-label="Used last">' + recent.map(c => `<button type="button" class="rs-cp-sw" data-c="${c}" style="background:${c}" aria-label="${c}"></button>`).join("") + "</div>" : "");
    document.body.append(box);
    box.querySelector(".rs-cp-old").style.background = old;
    box.querySelector(".rs-cp-old").onclick = () => { hsv = _cpToHsv(old); set(old); };
    const sv = box.querySelector(".rs-cp-sv"), hue = box.querySelector(".rs-cp-hue"), hexf = box.querySelector(".rs-cp-hex");
    drag(sv, (x, y) => { hsv.s = x; hsv.v = 1 - y; set(_cpToHex(hsv)); });
    drag(hue, x => { hsv.h = x * 359.9; set(_cpToHex(hsv)); });
    sv.addEventListener("keydown", e => {                       // the arrow keys move the dot (Shift: ten times as far)
      const k = e.shiftKey ? .1 : .01, d = {ArrowLeft: [-k, 0], ArrowRight: [k, 0], ArrowUp: [0, k], ArrowDown: [0, -k]}[e.key];
      if(!d) return; e.preventDefault(); hsv.s = _cpClamp(hsv.s + d[0], 0, 1); hsv.v = _cpClamp(hsv.v + d[1], 0, 1); set(_cpToHex(hsv));
    });
    hue.addEventListener("keydown", e => {
      const d = {ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1}[e.key]; if(!d) return;
      e.preventDefault(); hsv.h = (hsv.h + d * (e.shiftKey ? 10 : 1) + 360) % 360; set(_cpToHex(hsv));
    });
    hexf.addEventListener("input", () => { let v = hexf.value.trim(); if(!v.startsWith("#")) v = "#" + v; if(_cpHex.test(v)){ hsv = _cpToHsv(v.toLowerCase()); set(v.toLowerCase()); } });
    hexf.addEventListener("keydown", e => { if(e.key === "Enter"){ e.preventDefault(); close(); btn.focus(); } });
    box.querySelectorAll(".rs-cp-recent button").forEach(b => b.onclick = () => { hsv = _cpToHsv(b.dataset.c); set(b.dataset.c); });
    const eye = box.querySelector(".rs-cp-eye");
    if(eye) eye.onclick = async () => { try { const r = await new window.EyeDropper().open(); hsv = _cpToHsv(r.sRGBHex.slice(0, 7)); set(r.sRGBHex.slice(0, 7).toLowerCase()); } catch(e){ /* the person pressed Escape */ } };
    paint(); place();
    btn.setAttribute("aria-expanded", "true"); _cpOpen = {close};
    document.addEventListener("pointerdown", away, true); document.addEventListener("keydown", keys, true);
    addEventListener("resize", place); window.addEventListener("scroll", place, true);
    sv.focus();
  }
  btn.onclick = () => box ? close() : open();
  sync();
}
// every colour input in `el` (an editor frame, a section that the page adds)
export function rsColorPickers(el){ el.querySelectorAll('input[type="color"]').forEach(_cpEnhance); }
// every colour input of a panel (the dashboard sidebar, the docked panel, a host panel), also one that a section adds later
export function initColorPick(){
  const run = () => document.querySelectorAll('#sb input[type="color"], .rs-side input[type="color"], .rs-host input[type="color"]').forEach(_cpEnhance);
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
  document.addEventListener("rs:sectionchange", run);
}

// The value fields of a page (docs/design/dashboard_parts_2.md): a slider (one value, or a range with two handles), a number field with -/+ and a
// colour picker. The page gives an empty element; each gives back {value(), set(v, quiet)}. `onChange(v)` comes when a value is set (at the release
// of a slider); a slider's `onInput(v)` comes while it moves.
//   rs.slider(el, {label: "Speed", min: 0, max: 130, step: 10, value: 50, unit: "km/h", onChange})
//   rs.slider(el, {label: "Hours", min: 0, max: 23, value: [7, 9], format: v => v + ":00"})
//   rs.number(el, {label: "Lanes", min: 1, max: 8, value: 2})
//   rs.colorPick(el, {label: "Fill", value: "#eb6834", palette: ["#eb6834", ...]})
import {rsPopAt, rsPopClose, rsPopKeys} from "./menu.js";
import {rsColorBox, rsColorPickers} from "./colorpick.js";
const _fdHead = cls => '<div class="' + cls + '-head"><span class="' + cls + '-l"></span><output class="' + cls + '-v"></output></div>';
export function rsSlider(el, opts = {}){
  if(!(el instanceof Element)) throw new Error("rs.slider: give the element that the slider goes in");
  const two = Array.isArray(opts.value), min = opts.min ?? 0, max = opts.max ?? 100, step = opts.step ?? 1;
  const fmt = opts.format || (v => v + (opts.unit ? " " + opts.unit : ""));
  el.classList.add("rs-slider"); el.classList.toggle("rs-slider-two", two);
  el.innerHTML = _fdHead("rs-slider") + '<div class="rs-slider-track"><div class="rs-slider-fill"></div></div>';
  el.querySelector(".rs-slider-l").textContent = opts.label || "";
  const track = el.querySelector(".rs-slider-track"), fill = el.querySelector(".rs-slider-fill"), out = el.querySelector(".rs-slider-v");
  const ins = (two ? ["From", "To"] : [opts.label || "Value"]).map(name => {
    const i = document.createElement("input"); i.type = "range"; i.min = min; i.max = max; i.step = step; i.setAttribute("aria-label", name);
    track.appendChild(i); return i;
  });
  const val = () => two ? ins.map(i => +i.value) : +ins[0].value;
  function paint(){
    const pc = v => (v - min) / (max - min || 1) * 100, v = val();
    if(two){ fill.style.left = pc(v[0]) + "%"; fill.style.width = pc(v[1]) - pc(v[0]) + "%"; out.textContent = fmt(v[0]) + " – " + fmt(v[1]); }
    else{ fill.style.left = "0"; fill.style.width = pc(v) + "%"; out.textContent = fmt(v); }
    ins.forEach(i => i.setAttribute("aria-valuetext", fmt(+i.value)));
  }
  ins.forEach((i, k) => {
    i.addEventListener("input", () => {
      if(two && +ins[0].value > +ins[1].value) i.value = ins[1 - k].value;      // the handles do not cross
      if(two) ins[0].style.zIndex = +ins[0].value >= max - step ? 3 : "";       // the left handle at the right end stays on top
      paint(); opts.onInput?.(val());
    });
    i.addEventListener("change", () => opts.onChange?.(val()));
  });
  function set(v, quiet){ (two ? v : [v]).forEach((x, k) => { ins[k].value = x; }); paint(); if(!quiet) opts.onChange?.(val()); }
  set(opts.value ?? (two ? [min, max] : min), true);
  return {value: val, set};
}
export function rsNumber(el, opts = {}){
  if(!(el instanceof Element)) throw new Error("rs.number: give the element that the field goes in");
  const min = opts.min ?? -Infinity, max = opts.max ?? Infinity, step = opts.step ?? 1;
  el.classList.add("rs-num");
  el.innerHTML = (opts.label ? '<div class="rs-num-l"></div>' : "") + '<div class="rs-num-box">' +
    '<button type="button" class="rs-num-st" data-d="-1" tabindex="-1">−</button><input type="number" inputmode="decimal">' +
    '<span class="rs-num-u"></span><button type="button" class="rs-num-st" data-d="1" tabindex="-1">+</button></div>';
  if(opts.label) el.querySelector(".rs-num-l").textContent = opts.label;
  const inp = el.querySelector("input"), [dn, up] = el.querySelectorAll(".rs-num-st"), unit = el.querySelector(".rs-num-u");
  unit.textContent = opts.unit || ""; unit.hidden = !opts.unit;
  if(isFinite(min)) inp.min = min; if(isFinite(max)) inp.max = max; inp.step = step;
  inp.setAttribute("aria-label", opts.label || "Number");
  dn.setAttribute("aria-label", "Less"); up.setAttribute("aria-label", "More");
  let cur = null;
  const fix = v => { const n = Math.round(Math.max(min, Math.min(max, v)) / step) * step; return +n.toFixed(10); };
  function set(v, quiet){
    const n = fix(+v); if(!isFinite(n)){ inp.value = cur; return; }
    const was = cur; cur = n; inp.value = n; dn.disabled = n <= min; up.disabled = n >= max;
    if(!quiet && n !== was) opts.onChange?.(n);
  }
  [dn, up].forEach(b => b.addEventListener("click", () => { set(cur + step * +b.dataset.d); inp.focus(); }));
  inp.addEventListener("change", () => set(inp.value === "" ? cur : inp.value));
  set(opts.value ?? (isFinite(min) ? min : 0), true);
  return {value: () => cur, set};
}
const _fcHex = /^#[0-9a-f]{6}$/i;
const _fcChev = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
export function rsColorPick(el, opts = {}){
  if(!(el instanceof Element)) throw new Error("rs.colorPick: give the element that the picker goes in");
  // the default palette: the chart colours of the theme (the colours that a page shows its data in)
  const css = () => getComputedStyle(document.documentElement);
  const palette = () => opts.palette || [1, 2, 3, 4, 5, 6, 7, 8].map(k => css().getPropertyValue("--rs-chart-" + k).trim()).filter(Boolean);
  el.classList.add("rs-color");
  el.innerHTML = (opts.label ? '<div class="rs-color-l"></div>' : "") +
    '<button type="button" class="rs-color-btn" aria-haspopup="dialog" aria-expanded="false"><span class="rs-color-sw"></span><span class="rs-color-hex"></span>' + _fcChev + "</button>";
  if(opts.label) el.querySelector(".rs-color-l").textContent = opts.label;
  const btn = el.querySelector(".rs-color-btn"), box = document.createElement("div");
  // "More…" opens the colour box of colorpick.js (the square, the hue bar, the hex field, the colours used last) on a hidden colour input, at this
  // part's button: one colour box for the whole dashboard, and no browser dialog. Its `input` sets the value while the person drags.
  const full = document.createElement("input"); full.type = "color"; full.setAttribute("aria-label", (opts.label || "Colour") + ": more colours");
  el.appendChild(full); rsColorPickers(el); full.closest(".rs-cp").style.display = "none";
  full.addEventListener("input", () => set(full.value));
  btn.setAttribute("aria-label", opts.label || "Colour");
  box.className = "rs-color-box"; box.hidden = true; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "Choose a colour");
  document.body.appendChild(box);
  let cur = null;
  function paint(){ el.querySelector(".rs-color-sw").style.background = cur; el.querySelector(".rs-color-hex").textContent = cur; }
  function set(v, quiet){
    v = String(v).trim().toLowerCase(); if(/^#[0-9a-f]{3}$/i.test(v)) v = "#" + [...v.slice(1)].map(c => c + c).join("");
    if(!_fcHex.test(v)) return false;
    const was = cur; cur = v; paint(); if(!quiet && v !== was) opts.onChange?.(v); return true;
  }
  function close(){ box.hidden = true; btn.setAttribute("aria-expanded", "false"); }
  function open(){
    box.innerHTML = '<div class="rs-color-grid">' + palette().map(c => '<button type="button" class="rs-color-c' + (c.toLowerCase() === cur ? " on" : "") +
      '" data-c="' + c + '" style="background:' + c + '" aria-label="' + c + '"></button>').join("") + "</div>" +
      '<div class="rs-color-row"><input type="text" class="rs-color-in" maxlength="7" spellcheck="false" aria-label="Hex colour">' +
      '<button type="button" class="rs-color-more">More…</button></div>';
    const hex = box.querySelector(".rs-color-in");
    hex.value = cur;
    hex.addEventListener("input", () => { hex.classList.toggle("bad", !_fcHex.test(hex.value)); if(_fcHex.test(hex.value)) set(hex.value); });
    hex.addEventListener("keydown", e => { if(e.key === "Enter" && set(hex.value)){ close(); btn.focus(); } });
    box.querySelector(".rs-color-more").addEventListener("click", () => { close(); full.value = cur; rsColorBox(full, btn); });
    box.hidden = false; btn.setAttribute("aria-expanded", "true"); rsPopAt(box, btn);
    (box.querySelector(".rs-color-c.on") || box.querySelector(".rs-color-c"))?.focus();
  }
  btn.addEventListener("click", e => { e.stopPropagation(); box.hidden ? open() : close(); });
  box.addEventListener("click", e => { const c = e.target.closest(".rs-color-c"); if(c){ set(c.dataset.c); close(); btn.focus(); } });
  rsPopKeys(box, ".rs-color-c", 4);
  rsPopClose(box, btn, close);
  set(opts.value || palette()[0] || "#000000", true);
  return {value: () => cur, set};
}

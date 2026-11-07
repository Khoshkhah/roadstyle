// The messages and the wait of a page (docs/design/dashboard_parts_2.md): a toast, the confirm dialog, a progress bar and the busy state of a button.
//   rs.toast("Saved 12 fixes.", {kind: "ok"})          kind: "info" (default), "ok", "warn", "error"; ms: the time on the screen (0: until it is closed)
//   if(await rs.confirm({title: "Delete 3 fixes?", text: "You cannot undo this.", ok: "Delete", danger: true})) remove();
//   const p = rs.progress(el, {label: "Build"}); p.set(0.42, "Roads 42 %"); p.set(null);   // null: the bar moves, with no value
//   rs.busy(button, fetch(url));                        // the button turns, and waits until the promise ends
const _ntIcon = {
  info: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6.5"/><path d="M8 7.2v4M8 4.8v.1" stroke-linecap="round"/></svg>',
  ok: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6.5"/><path d="m5.2 8.2 2 2 3.6-4"/></svg>',
  warn: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M8 1.8 15 14H1z"/><path d="M8 6.3v3.6M8 11.8v.1" stroke-linecap="round"/></svg>',
  error: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="8" cy="8" r="6.5"/><path d="m5.6 5.6 4.8 4.8m0-4.8-4.8 4.8"/></svg>',
};
const _ntMs = {info: 4000, ok: 4000, warn: 6000, error: 8000};
export function rsToast(text, opts = {}){
  const kind = _ntIcon[opts.kind] ? opts.kind : "info";
  let stack = document.getElementById("rs-toasts");
  if(!stack){ stack = document.createElement("div"); stack.id = "rs-toasts"; document.body.appendChild(stack); }
  const t = document.createElement("div"); t.className = "rs-toast " + kind;
  t.setAttribute("role", kind === "warn" || kind === "error" ? "alert" : "status");
  t.innerHTML = '<span class="rs-toast-i">' + _ntIcon[kind] + '</span><span class="rs-toast-t"></span>' +
    '<button type="button" class="rs-toast-x" aria-label="Close">×</button>';
  t.querySelector(".rs-toast-t").innerHTML = text;
  if(opts.action){
    const a = document.createElement("button"); a.type = "button"; a.className = "rs-toast-a"; a.textContent = opts.action.label;
    a.addEventListener("click", () => { close(); opts.action.onClick?.(); });
    t.insertBefore(a, t.lastChild);
  }
  const free = window.rs?.freeArea?.();               // over the middle of the map that the panel and the bar leave free
  stack.style.left = free && free.hi > free.lo ? (free.lo + free.hi) / 2 + "px" : "";
  stack.appendChild(t);
  let timer = 0, left = opts.ms ?? _ntMs[kind], start = 0;
  const run = () => { if(left > 0){ start = Date.now(); timer = setTimeout(close, left); } };
  const hold = () => { if(timer){ clearTimeout(timer); timer = 0; left -= Date.now() - start; } };
  function close(){ hold(); left = 0; t.classList.add("out"); setTimeout(() => t.remove(), 200); }
  t.querySelector(".rs-toast-x").addEventListener("click", close);
  t.addEventListener("pointerenter", hold); t.addEventListener("pointerleave", run);      // the toast stays while the pointer is on it
  t.addEventListener("focusin", hold); t.addEventListener("focusout", run);
  run();
  return {close};
}
// the confirm dialog: the browser's <dialog> (it keeps the focus in it, and Escape is Cancel). The promise gives true for the OK button.
export function rsConfirm(opts = {}){
  const d = document.createElement("dialog"); d.className = "rs-dialog";
  d.innerHTML = '<div class="rs-dialog-ttl"></div><div class="rs-dialog-text"></div><div class="rs-dialog-bar">' +
    '<button type="button" value="0"></button><button type="button" value="1"></button></div>';
  d.querySelector(".rs-dialog-ttl").textContent = opts.title || "Are you sure?";
  d.querySelector(".rs-dialog-text").innerHTML = opts.text || "";
  const [no, yes] = d.querySelectorAll("button");
  no.textContent = opts.cancel || "Cancel"; yes.textContent = opts.ok || "OK";
  yes.className = opts.danger ? "sb-danger" : "sb-primary";
  document.body.appendChild(d);
  return new Promise(done => {
    d.addEventListener("click", e => {
      const b = e.target.closest("button");
      if(b) d.close(b.value);
      else if(e.target === d) d.close("0");               // a click on the backdrop is Cancel
    });
    d.addEventListener("close", () => { d.remove(); done(d.returnValue === "1"); });
    d.showModal();
    (opts.danger ? no : yes).focus();                      // a danger action is never the default of Enter
  });
}
export function rsProgress(el, opts = {}){
  if(!(el instanceof Element)) throw new Error("rs.progress: give the element that the bar goes in");
  el.classList.add("rs-progress");
  el.innerHTML = '<div class="rs-progress-head"><span class="rs-progress-l"></span><span class="rs-progress-v"></span></div>' +
    '<div class="rs-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"><div class="rs-progress-fill"></div></div>';
  const bar = el.querySelector(".rs-progress-bar"), fill = el.querySelector(".rs-progress-fill");
  el.querySelector(".rs-progress-l").textContent = opts.label || "";
  bar.setAttribute("aria-label", opts.label || "Progress");
  function set(v, text){
    const on = v != null;
    el.classList.toggle("rs-progress-wait", !on);
    if(on){ const p = Math.round(Math.max(0, Math.min(1, v)) * 100); fill.style.width = p + "%"; bar.setAttribute("aria-valuenow", p); }
    else{ fill.style.width = ""; bar.removeAttribute("aria-valuenow"); }
    el.querySelector(".rs-progress-v").textContent = text ?? (on ? Math.round(v * 100) + " %" : "");
  }
  set(opts.value ?? null, opts.text);
  return {set};
}
// the busy state of a button: a turning ring before its text, and no click. With a promise it ends when the promise ends (and gives the promise back).
export function rsBusy(button, on = true){
  const go = b => { button.classList.toggle("rs-busy", b); button.disabled = b; b ? button.setAttribute("aria-busy", "true") : button.removeAttribute("aria-busy"); };
  if(on && typeof on.then === "function"){ go(true); return on.finally(() => go(false)); }
  go(!!on);
  return on;
}

// The help window of a page (docs/guides/dashboard-panel.md): `rs.help.set({title, intro, terms: [[term, text], ...], note})` puts an "i" button in the
// panel's title and keeps the window that it opens. The page gives the words, roadstyle gives the look (the card token, the blur and the border of the
// other floating windows), so every page's help window is the same window in both themes. The words are HTML of the page's own (`<b>` and so on).
import {_emit} from "./core.js";
const _hpIcon = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4.5"/><circle cx="12" cy="17.6" r=".6" fill="currentColor"/></svg>';
let _hpBox = null, _hpBtn = null, _hpMain = null;
function _hpClose(){ if(_hpBox && !_hpBox.hidden){ _hpBox.hidden = true; _emit("rs:helpchange", {open: false}); } }
const _hpEsc = t => String(t).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
// the one window, filled with the words of `spec` ({title, intro, terms, note}); the page's own HTML in the words stays as it is
function _hpRender(spec){
  if(!spec || !spec.title) throw new Error("rs.help: the window needs a title");
  if(!_hpBox){
    _hpBox = document.createElement("div"); _hpBox.id = "rs-help"; _hpBox.hidden = true;
    _hpBox.addEventListener("click", e => { if(e.target === _hpBox || e.target.closest(".rs-help-x")) _hpClose(); });
    document.body.append(_hpBox);
    document.addEventListener("keydown", e => { if(e.key === "Escape") _hpClose(); }, true);
  }
  const terms = (spec.terms || []).map(t => "<dt>" + t[0] + "</dt><dd>" + t[1] + "</dd>").join("");
  _hpBox.innerHTML = '<div class="rs-help-box" role="dialog" aria-label="' + _hpEsc(spec.title) + '"><button class="rs-help-x" aria-label="close">&times;</button>' +
    '<div class="rs-help-ttl">' + spec.title + "</div>" + (spec.intro ? '<p class="rs-help-intro">' + spec.intro + "</p>" : "") + (spec.html || "") +
    (terms ? '<dl class="rs-help-terms">' + terms + "</dl>" : "") + (spec.note ? '<div class="rs-help-note">' + spec.note + "</div>" : "") + "</div>";
}
// the window with the words of `spec` (the page's main words, `set`, when none is given)
function _hpOpen(spec){
  const w = spec || _hpMain;
  if(!w) throw new Error("rs.help.open: give {title, ...}, or set the page's words with rs.help.set first");
  _hpRender(w);
  if(_hpBox.hidden){ _hpBox.hidden = false; _emit("rs:helpchange", {open: true, title: w.title}); }
}
// a "?" button of the window's look (`.rs-help-btn`): its click opens the window with `spec`
function _hpButton(spec, id){
  const b = document.createElement("button"); b.type = "button"; b.className = "rs-help-btn"; if(id) b.id = id; b.innerHTML = _hpIcon;
  b.title = (spec && spec.button) || "How to read this page"; b.setAttribute("aria-label", b.title);
  b.addEventListener("click", e => { e.stopPropagation(); _hpOpen(spec); });          // no spec: the page's main words, as they are at the click
  return b;
}
export const rsHelp = {
  // the page's main words, with the button in the panel's title; called again, it replaces them
  set(spec){
    if(!spec || !spec.title) throw new Error("rs.help.set: the window needs a title");
    _hpMain = spec;
    if(!_hpBtn || !document.body.contains(_hpBtn)){
      const h = document.querySelector("#sb .sb-top h2");
      if(h){ _hpBtn = _hpButton(null, "rs-help-btn"); h.append(_hpBtn); }
    }
    if(_hpBtn){ _hpBtn.title = spec.button || "How to read this page"; _hpBtn.setAttribute("aria-label", _hpBtn.title); }
    if(_hpBox && !_hpBox.hidden) _hpRender(spec);
  },
  // one more "?" button, appended to `el` (a card's title, a label), with its own words: {title, intro, terms, note, html, button}. All the buttons open the one window.
  // It gives the button back.
  button(el, spec){
    if(!(el instanceof Element)) throw new Error("rs.help.button: give the element that the button goes in");
    if(!spec || !spec.title) throw new Error("rs.help.button: the words need a title");
    const b = _hpButton(spec); el.append(b); return b;
  },
  // the window with words of its own ({title, ...}), or with the page's main words: the page's own button, a link
  open: _hpOpen,
  close: _hpClose,
};

// The help window of a page (docs/guides/dashboard-panel.md): `rs.help.set({title, intro, terms: [[term, text], ...], note})` puts an "i" button in the
// panel's title and keeps the window that it opens. The page gives the words, roadstyle gives the look (the card token, the blur and the border of the
// other floating windows), so every page's help window is the same window in both themes. The words are HTML of the page's own (`<b>` and so on).
// `anchor` (an element) is where the button goes, in place of the panel's title `#sb .sb-top h2`; `get()` gives the words that are set now (a page that
// puts its own words in for a while sets them again), `clear()` takes the window and the button away.
import {_emit} from "./core.js";
const _hpIcon = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4.5"/><circle cx="12" cy="17.6" r=".6" fill="currentColor"/></svg>';
let _hpBox = null, _hpBtn = null, _hpSpec = null;
const _hpKey = e => { if(e.key === "Escape") _hpClose(); };       // heard only while the window is open: a page that took the help away has no listener left
function _hpClose(){ if(_hpBox && !_hpBox.hidden){ _hpBox.hidden = true; document.removeEventListener("keydown", _hpKey, true); _emit("rs:helpchange", {open: false}); } }
function _hpOpen(){ if(_hpBox && _hpBox.hidden){ _hpBox.hidden = false; document.addEventListener("keydown", _hpKey, true); _emit("rs:helpchange", {open: true}); } }
export const rsHelp = {
  // the page's words; called again, it replaces them
  set(spec){
    if(!spec || !spec.title) throw new Error("rs.help.set: the window needs a title");
    if(!_hpBox){
      _hpBox = document.createElement("div"); _hpBox.id = "rs-help"; _hpBox.hidden = true;
      _hpBox.addEventListener("click", e => { if(e.target === _hpBox || e.target.closest(".rs-help-x")) _hpClose(); });
      document.body.append(_hpBox);
    }
    _hpSpec = spec;
    const terms = (spec.terms || []).map(t => "<dt>" + t[0] + "</dt><dd>" + t[1] + "</dd>").join("");
    _hpBox.innerHTML = '<div class="rs-help-box" role="dialog" aria-label="' + spec.title.replace(/"/g, "&quot;") + '"><button class="rs-help-x" aria-label="close">&times;</button>' +
      '<div class="rs-help-ttl">' + spec.title + "</div>" + (spec.intro ? '<p class="rs-help-intro">' + spec.intro + "</p>" : "") +
      (terms ? '<dl class="rs-help-terms">' + terms + "</dl>" : "") + (spec.note ? '<div class="rs-help-note">' + spec.note + "</div>" : "") + "</div>";
    const h = spec.anchor || document.querySelector("#sb .sb-top h2");
    if(!_hpBtn || !document.body.contains(_hpBtn)){
      if(h){ _hpBtn = document.createElement("button"); _hpBtn.id = "rs-help-btn"; _hpBtn.type = "button"; _hpBtn.innerHTML = _hpIcon; h.append(_hpBtn); _hpBtn.onclick = _hpOpen; }
    } else if(h && _hpBtn.parentNode !== h) h.append(_hpBtn);
    if(_hpBtn){ _hpBtn.title = spec.button || "How to read this page"; _hpBtn.setAttribute("aria-label", _hpBtn.title); }
    // a page with no panel (dashboard={"panel": None}, street_view="dock") has no title to put the button in: the help is a tool of the bar
    else if(window.rs && window.rs.tools && !window.rs.tools.list().some(t => t.id === "help")) window.rs.tools.add({id: "help", title: spec.button || "How to read this page", icon: _hpIcon, onClick: _hpOpen});
  },
  get: () => _hpSpec,
  clear(){ _hpClose(); if(_hpBox) _hpBox.remove(); if(_hpBtn) _hpBtn.remove(); _hpBox = _hpBtn = _hpSpec = null; },
  open: _hpOpen,
  close: _hpClose,
};

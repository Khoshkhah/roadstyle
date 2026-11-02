// The scroll protocol of a panel (docs/design/dashboard_templates.md): the header stays, only the body scrolls. A line under the header shows when
// the body is scrolled, so the person sees that there is more above; the body has `data-more` while there is more below (a fade at its bottom edge), and
// `rs-scrolling` while it scrolls (the scrollbar shows). (The rest of the protocol is CSS: the body does not hand its scroll to the map.)
export function initPanelScroll(){
  const run = () => document.querySelectorAll(".sb-body, .rp-body, .rs-pbody").forEach(body => {
    const head = body.dataset.head ? document.querySelector(body.dataset.head) : body.previousElementSibling;   // data-head: the header of a body that is not just after it
    if(!head || body.dataset.rsScroll) return;
    body.dataset.rsScroll = "1";
    const mark = () => head.classList.toggle("scrolled", body.scrollTop > 0);
    const more = () => body.toggleAttribute("data-more", body.scrollTop + body.clientHeight < body.scrollHeight - 2);
    let t = 0;
    body.addEventListener("scroll", () => {
      mark(); more();
      body.classList.add("rs-scrolling"); clearTimeout(t); t = setTimeout(() => body.classList.remove("rs-scrolling"), 900);
    }, {passive: true});
    mark(); more();
    addEventListener("resize", more);
    new ResizeObserver(more).observe(body);                                              // a section that the page adds or hides changes the height
    new MutationObserver(more).observe(body, {childList: true, subtree: true});
  });
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
}
// Every other scroll area of the dashboard (a page's `rs-scroll`, the query part's list, the help window, the panel's select list, the boxes of the toolbox,
// the docked read-out; dashboard.css has the same list): the same protocol as the body, for each one. The scrollbar shows while the pointer is over the area or
// it scrolls (`rs-scrolling`), a fade at its bottom edge shows while there is more below (`data-more`), and its scroll never goes on to the map or to the body (CSS).
function _psInner(el){
  if(el.dataset.rsScroll) return;
  el.dataset.rsScroll = "1";
  const more = () => el.toggleAttribute("data-more", el.scrollTop + el.clientHeight < el.scrollHeight - 2);
  let t = 0;
  el.addEventListener("scroll", () => { more(); el.classList.add("rs-scrolling"); clearTimeout(t); t = setTimeout(() => el.classList.remove("rs-scrolling"), 900); }, {passive: true});
  more();
  new ResizeObserver(more).observe(el);
  new MutationObserver(more).observe(el, {childList: true, subtree: true});            // a table that gets its rows later
}
const _PS_AREAS = [".rs-scroll", ".rs-q-list", "#rs-help .rs-help-box", ".rs-sel-list", "#rs-toolbar .bm-menu", "#rs-attr-box", "#rs-color-box", "#rs-nav-box",
  "#rs-roads-box", "#rs-settings-box", ".rs-side-bd", ".rs-side-ctl", ".rs-side-q-res"].join(", ");
export function initInnerScroll(){
  const scan = () => document.querySelectorAll(_PS_AREAS).forEach(el => el.dataset.rsScroll || _psInner(el));
  let queued = false;          // a box or a window that opens later: one scan in the next frame for every change of the page
  const later = () => { if(!queued){ queued = true; requestAnimationFrame(() => { queued = false; scan(); }); } };
  const run = () => { scan(); new MutationObserver(later).observe(document.body, {childList: true, subtree: true}); };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
}

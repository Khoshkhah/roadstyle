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
// A scroll area INSIDE the panel (`class="rs-scroll"`: a list, a table): the same protocol as the body, for each one. The scrollbar shows while the pointer is over the area or
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
export function initInnerScroll(){
  const scan = () => document.querySelectorAll(".rs-scroll:not([data-rs-scroll])").forEach(_psInner);
  const run = () => {
    scan();
    for(const root of document.querySelectorAll("#sb, #rp")) new MutationObserver(scan).observe(root, {childList: true, subtree: true});
  };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
}

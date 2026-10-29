// The scroll protocol of a panel (docs/design/dashboard_templates.md): the header stays, only the body scrolls. A line under the header shows when
// the body is scrolled, so the person sees that there is more above. (The rest of the protocol is CSS: the body does not hand its scroll to the map.)
export function initPanelScroll(){
  const run = () => document.querySelectorAll(".sb-body, .rp-body").forEach(body => {
    const head = body.previousElementSibling;
    if(!head || body.dataset.rsScroll) return;
    body.dataset.rsScroll = "1";
    const mark = () => head.classList.toggle("scrolled", body.scrollTop > 0);
    body.addEventListener("scroll", mark, {passive: true}); mark();
  });
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
}

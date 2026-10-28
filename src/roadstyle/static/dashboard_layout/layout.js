// render_dashboard(layout="overlay", toolbar=...): see docs/guides/dashboard-layout.md. window.rsLayout = {layout, toolbar} is set by the page.
(function(){
  const opt = window.rsLayout || {}, overlay = opt.layout === "overlay", pos = opt.toolbar || false;
  const start = setInterval(()=>{
    if(!window.map || !window.map.loaded()) return;
    clearInterval(start);
    const map = window.map, root = document.documentElement;
    if(overlay){
      root.classList.add("rs-overlay");
      window.rsWindowRecentre = false;        // a window never moves the map
      // the map's box never changes: a panel is an overlay, so only the window's own resize resizes the map
      new ResizeObserver(()=>map.resize()).observe(map.getContainer());
      // a floating window stays inside the map at every drag move
      const mapRect = ()=>map.getContainer().getBoundingClientRect();
      const fit = w=>{ if(!w || w.hidden) return; const m = mapRect(), gap = 8;
        const W = Math.min(w.offsetWidth, m.width - 2*gap), H = Math.min(w.offsetHeight, m.height - 28);
        Object.assign(w.style, {width:W+"px", height:H+"px"});
        const r = w.getBoundingClientRect();
        Object.assign(w.style, {left:Math.max(m.left+gap, Math.min(r.left, m.right-W-gap))+"px", top:Math.max(m.top+gap, Math.min(r.top, m.bottom-H-gap))+"px", right:"auto", bottom:"auto"}); };
      const wins = ()=>document.querySelectorAll(".rs-svw");
      document.addEventListener("pointermove", ()=>document.querySelectorAll(".rs-svw.rs-drag").forEach(fit), true);
      // a window opens in the visible part: right of an open left panel, left of an open right panel and the toolbar's strip
      const vis = e=>e && getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0;
      const placeVisible = w=>{ if(!w || w.hidden) return; const m = mapRect(), sb = document.getElementById("sb"), side = document.querySelector(".rs-side");
        const left = vis(sb) && sb.getBoundingClientRect().left < innerWidth/2 ? sb.getBoundingClientRect().right : m.left;
        const right = vis(side) ? Math.min(m.right, side.getBoundingClientRect().left) : m.right - (pos === "right" ? 60 : 0);
        const r = w.getBoundingClientRect(), gap = 12;
        if(r.left >= left && r.right <= right) return;
        Object.assign(w.style, {left:Math.max(left+gap, Math.min(r.left, right-r.width-gap))+"px", top:Math.max(m.top+gap, r.top)+"px", right:"auto", bottom:"auto"}); };
      const opened = new MutationObserver(l=>l.forEach(x=>setTimeout(()=>placeVisible(x.target), 120)));
      wins().forEach(w=>opened.observe(w, {attributes:true, attributeFilter:["hidden"]}));
    }
    // the theme: the dashboard's light/dark switch (#sb[data-theme]) and a dark base map give the bar its dark colours
    const theme = ()=>{ const sb = document.getElementById("sb"), bm = (window.RS_BASEMAPS || []).find(b=>document.querySelector(".bm-menu .on") && b.label === document.querySelector(".bm-menu .on").textContent);
      const dark = (sb && sb.dataset.theme === "dark") || (bm && /dark|black/i.test(bm.key + " " + bm.label));
      root.dataset.rsTheme = dark ? "dark" : "light"; };
    const sbEl = document.getElementById("sb");
    if(sbEl) new MutationObserver(theme).observe(sbEl, {attributes:true, attributeFilter:["data-theme"]});
    document.addEventListener("rs:basemapchange", ()=>setTimeout(theme, 0));
    theme();
    if(pos){
      let tb = document.getElementById("rs-toolbar"); if(!tb){ tb = document.createElement("div"); tb.id = "rs-toolbar"; tb.className = "rs-tb-"+pos; document.body.appendChild(tb); }
      const col = document.querySelector(".maplibregl-ctrl-top-right");
      if(col){
        const take = c=>{
          const show = c.querySelector("button[title='Show panel']");
          if(show){                           // the chevron of a hidden panel is not a control of the bar
            const f = document.createElement("div"); f.id = "rs-show-right"; f.appendChild(show); document.body.appendChild(f);
            const sync = ()=>{ f.style.display = c.style.display === "none" ? "none" : "block"; };
            new MutationObserver(sync).observe(c, {attributes:true, attributeFilter:["style"]}); sync(); c.remove(); return; }
          tb.appendChild(c); const b = c.querySelector("button"); if(b && !b.title) b.title = b.getAttribute("aria-label") || b.textContent.trim() || "Control"; };
        [...col.children].forEach(take);
        new MutationObserver(l=>l.forEach(x=>x.addedNodes.forEach(n=>{ if(n.nodeType === 1) take(n); }))).observe(col, {childList:true});   // a control that the page adds later
        col.classList.add("rs-emptied");
      }
      tb.querySelectorAll("button").forEach(b=>{ if(!b.title) b.title = b.getAttribute("aria-label") || b.textContent.trim() || "Control"; });
      // A panel on the toolbar's side never covers the bar: when the panel is open, the bar slides to 8 px beside it (150 ms); when the panel
      // closes, the bar goes back to the edge. The bar's position along the edge does not change.
      if(overlay && (pos === "right" || pos === "left")){
        const panels = [...document.querySelectorAll("#sb, .rs-side")].filter(p=>{ const r = p.getBoundingClientRect(); return !r.width || (r.left + r.width/2 < innerWidth/2 ? "left" : "right") === pos; });
        const follow = ()=>{
          let off = 8;
          for(const p of panels){ const r = p.getBoundingClientRect(), shown = getComputedStyle(p).display !== "none" && r.width > 0;
            if(shown) off = Math.max(off, (pos === "right" ? innerWidth - r.left : r.right) + 8); }
          tb.style[pos] = off + "px"; root.style.setProperty("--rs-tb-off", (off - 8) + "px"); };
        const all = [...document.querySelectorAll("#sb, .rs-side")];
        all.forEach(p=>new MutationObserver(follow).observe(p, {attributes:true, attributeFilter:["style", "class"]}));
        new MutationObserver(follow).observe(document.body, {attributes:true, attributeFilter:["class"]});
        window.addEventListener("resize", follow); follow();
      }
    }
  }, 150);
})();

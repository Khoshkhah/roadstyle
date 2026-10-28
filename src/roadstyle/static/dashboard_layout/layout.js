// render_dashboard(layout="overlay", toolbar=...): see docs/guides/dashboard-layout.md. window.rsLayout = {layout, toolbar} is set by the page.
(function(){
  const opt = window.rsLayout || {}, overlay = opt.layout === "overlay", pos = opt.toolbar || false;
  // The bar is hidden until its buttons are in, so that no empty bar flashes at the load. A page that adds controls of its own sets
  // window.rsToolbarHold = true early and calls window.rsToolbarShow() when its controls are in (a hold ends after 6 s at the latest).
  let wanted = false, filled = false;
  const reveal = ()=>{ const b = document.getElementById("rs-toolbar"); if(b && filled && (wanted || !window.rsToolbarHold)) b.classList.add("rs-ready"); };
  window.rsToolbarShow = ()=>{ wanted = true; reveal(); };
  setTimeout(()=>{ wanted = true; reveal(); }, 6000);
  const start = setInterval(()=>{
    if(!window.map || !window.map.loaded()) return;
    clearInterval(start);
    const map = window.map, root = document.documentElement;
    if(overlay){
      root.classList.add("rs-overlay");
      window.rsWindowRecentre = false;        // a window never moves the map
      // the map's box never changes: a panel is an overlay, so only the window's own resize resizes the map
      new ResizeObserver(()=>map.resize()).observe(map.getContainer());
      // the scale bar and the zoom level: one small box in the bottom left corner, 28 px high, of a fixed width (the scale bar's longest state and a 56 px
      // slot for "z 15.7"), so that it never jumps on a zoom; its text cannot be selected and it ignores the pointer
      const scale = document.querySelector(".maplibregl-ctrl-scale"), zoom = document.querySelector(".rs-zoom");
      if(scale || zoom){
        const box = document.createElement("div"); box.id = "rs-scalebox"; document.body.appendChild(box);
        if(scale) box.appendChild(scale);
        if(zoom){ zoom.classList.add("rs-zoom-slot"); box.appendChild(zoom); }
      }
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
      // the attribution is the last button of the bar: a box with the text of the base map (and Google's, where a Google window is open)
      const at = document.createElement("div"); at.className = "maplibregl-ctrl maplibregl-ctrl-group rs-attr-ctrl";
      at.innerHTML = '<button type="button" id="rs-attr-btn" title="Attribution"><svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="9.25"/><path d="M12 11v5.5M12 7.8h.01"/></svg></button><div id="rs-attr-box" hidden></div>';
      tb.appendChild(at);
      const box = at.querySelector("#rs-attr-box");
      at.querySelector("button").onclick = e=>{ e.stopPropagation();
        if(box.hidden){ const inner = document.querySelector(".maplibregl-ctrl-attrib-inner"), g = [".rs-g3d", ".rs-svw:not(.rs-g3d)"].some(s=>{ const w = document.querySelector(s); return w && !w.hidden; });
          box.innerHTML = (inner ? inner.innerHTML : "") + (g ? "<div>Google Maps: map data \u00a9 Google</div>" : ""); }
        box.hidden = !box.hidden; };
      document.addEventListener("click", e=>{ if(!e.target.closest || !e.target.closest(".rs-attr-ctrl")) box.hidden = true; }, true);
      document.addEventListener("keydown", e=>{ if(e.key === "Escape") box.hidden = true; }, true);
      const col = document.querySelector(".maplibregl-ctrl-top-right");
      if(col){
        const take = c=>{
          const show = c.querySelector("button[title='Show panel']");
          if(show){                           // the chevron of a hidden panel is not a control of the bar
            const f = document.createElement("div"); f.id = "rs-show-right"; f.appendChild(show); document.body.appendChild(f);
            const sync = ()=>{ f.style.display = c.style.display === "none" ? "none" : "block"; };
            new MutationObserver(sync).observe(c, {attributes:true, attributeFilter:["style"]}); sync(); c.remove(); return; }
          tb.insertBefore(c, at); const b = c.querySelector("button"); if(b && !b.title) b.title = b.getAttribute("aria-label") || b.textContent.trim() || "Control"; };
        [...col.children].forEach(take);
        new MutationObserver(l=>l.forEach(x=>x.addedNodes.forEach(n=>{ if(n.nodeType === 1) take(n); }))).observe(col, {childList:true});   // a control that the page adds later
        col.classList.add("rs-emptied");
      }
      // The base-map box (design of duckOSM's #basepop): the heading "Base map", one radio row per map with a swatch (32x20) and its name, a divider, and
      // "On top": checkbox rows for the reference layers between the base map and the roads. A map with a dark twin is one entry that follows the page's
      // theme. The order on the map: base map, hillshade, labels, roadstyle's roads, the model, the buildings, the selection.
      const menu = document.querySelector(".bm-menu"), bms = window.RS_BASEMAPS || [];
      if(menu && bms.length){
        menu.classList.add("rs-bm-box"); menu.innerHTML = "";
        const el = (tag, cls, txt)=>{ const e = document.createElement(tag); if(cls) e.className = cls; if(txt) e.textContent = txt; return e; };
        const ls = k=>{ try{ return localStorage.getItem("rs-top:"+k); }catch(e){ return null; } }, ss = (k, v)=>{ try{ localStorage.setItem("rs-top:"+k, v ? "1" : "0"); }catch(e){} };
        const isDark = ()=>root.dataset.rsTheme === "dark";
        const byKey = k=>bms.findIndex(b=>b.key === k);
        let current = (bms[0] || {}).key;
        menu.appendChild(el("div", "rs-bm-h", "Base map"));
        const rows = [];
        bms.map((b, i)=>[b, i]).filter(([b])=>!b.twin).sort((x, y)=>(x[0].order ?? 99) - (y[0].order ?? 99) || x[1] - y[1]).forEach(([b, i])=>{
          const lab = el("label", "rs-bm-row"), r = el("input"); r.type = "radio"; r.name = "rs-bm"; r.value = b.key;
          const sw = el("span", "rs-bm-sw"); sw.style.background = b.bg;
          lab.append(r, sw, el("span", "rs-bm-n", b.title || b.label)); lab.dataset.key = b.key;
          r.onchange = ()=>{ window.rsSetBasemap(b.dark && isDark() ? b.dark : b.key); };
          menu.appendChild(lab); rows.push([b, r]);
        });
        menu.appendChild(el("hr"));
        menu.appendChild(el("div", "rs-bm-h", "On top"));
        const tops = {};
        const topRow = (id, label)=>{ const lab = el("label", "rs-bm-row"), c = el("input"); c.type = "checkbox"; c.id = "rs-top-"+id; lab.append(c, el("span", "rs-bm-n", label)); menu.appendChild(lab); tops[id] = {lab, c}; return c; };
        const roadsFirst = ()=>{ const l = map.getStyle().layers.find(x=>/^roads/.test(x.id)); return l ? l.id : undefined; };
        const RAS = {hillshade: ["https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}", 0.4, "Tiles © Esri"],
                     labels: ["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", 1, "Tiles © Esri"],
                     satlabels: ["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Reference_Overlay/MapServer/tile/{z}/{y}/{x}", 1, "Tiles © Esri"]};
        const raster = (id, on)=>{ const lid = "rs-top-"+id;
          if(!on){ if(map.getLayer(lid)) map.removeLayer(lid); if(map.getSource(lid)) map.removeSource(lid); return; }
          if(map.getLayer(lid)) return;
          map.addSource(lid, {type:"raster", tiles:[RAS[id][0]], tileSize:256, maxzoom:16, attribution:RAS[id][2]});
          map.addLayer({id:lid, type:"raster", source:lid, paint:{"raster-opacity":RAS[id][1]}}, roadsFirst()); };
        const vector = ()=>{ const b = bms[byKey(current)]; return !!(b && b.style_url); };
        const apply = ()=>{
          const vec = vector(), sat = current === "satellite";
          raster("hillshade", tops.hillshade.c.checked);
          raster("labels", !vec && tops.labels.c.checked);
          raster("satlabels", sat && tops.satlabels.c.checked);
          if(vec) for(const l of map.getStyle().layers.filter(x=>x.id.startsWith("vbm-") && x.type === "symbol")) map.setLayoutProperty(l.id, "visibility", tops.labels.c.checked ? "visible" : "none");
          tops.satlabels.lab.hidden = !sat;
          tops.buildings.c.disabled = !vec; tops.buildings.c.checked = vec && window.rsBuildings ? window.rsBuildings() : false; };
        topRow("hillshade", "Hillshade").checked = ls("hillshade") === "1";
        topRow("labels", "Labels").checked = ls("labels") === "1" || (ls("labels") == null && vector());
        topRow("buildings", "3D buildings");
        topRow("satlabels", "Satellite labels").checked = ls("satlabels") === "1";
        for(const id of ["hillshade", "labels", "satlabels"]) tops[id].c.onchange = ()=>{ ss(id, tops[id].c.checked); apply(); };
        tops.buildings.c.onchange = ()=>{ if(window.rsBuildings) window.rsBuildings(tops.buildings.c.checked); };
        const mark = ()=>{ rows.forEach(([b, r])=>{ r.checked = b.key === current || b.dark === current; }); };
        document.addEventListener("rs:basemapchange", e=>{ current = e.detail.basemap; mark(); setTimeout(apply, 0); });
        document.addEventListener("rs:basemapready", ()=>{ if(tops.labels.c.checked === false && ls("labels") == null) tops.labels.c.checked = true; apply(); });
        document.addEventListener("rs:buildingschange", apply);
        // the page's theme switch changes a map that has a twin at once, and leaves a map with no twin as it is
        const sbT = document.getElementById("sb");
        if(sbT) new MutationObserver(()=>{ const dark = sbT.dataset.theme === "dark", b = bms[byKey(current)]; if(!b) return;
          if(dark && b.dark) window.rsSetBasemap(b.dark);
          else if(!dark){ const light = bms.find(x=>x.dark === current); if(light) window.rsSetBasemap(light.key); } }).observe(sbT, {attributes:true, attributeFilter:["data-theme"]});
        mark(); apply();
        // the box opens inside the window: moved up or down by what it overhangs
        new MutationObserver(()=>{ if(!menu.classList.contains("open")) return; menu.style.marginTop = "0px";
          const r = menu.getBoundingClientRect(), over = r.bottom - (innerHeight - 8), under = 8 - r.top;
          menu.style.marginTop = (over > 0 ? -over : under > 0 ? under : 0) + "px"; }).observe(menu, {attributes:true, attributeFilter:["class"]});
        document.addEventListener("keydown", e=>{ if(e.key === "Escape") menu.classList.remove("open"); }, true);
      }
      filled = true; reveal();
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

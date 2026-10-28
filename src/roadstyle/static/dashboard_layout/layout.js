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
      // the side of a panel: by its own CSS (a hidden panel has no box), left when it is anchored to the left edge
      const sideOf = p=>{ const cs = getComputedStyle(p); return parseFloat(cs.left) === 0 && cs.left !== "auto" ? "left" : "right"; };
      window.rsFollow = (box, side)=>{
        const panels = [...document.querySelectorAll("#sb, .rs-side")].filter(p=>sideOf(p) === side);
        const run = ()=>{ let off = 8;
          for(const p of panels){ const r = p.getBoundingClientRect(); if(getComputedStyle(p).display !== "none" && r.width > 0) off = Math.max(off, (side === "right" ? innerWidth - r.left : r.right) + 8); }
          box.style[side] = off + "px"; if(side === "right") root.style.setProperty("--rs-tb-off", (off - 8) + "px"); };
        panels.forEach(p=>new MutationObserver(run).observe(p, {attributes:true, attributeFilter:["style", "class"]}));
        new MutationObserver(run).observe(document.body, {attributes:true, attributeFilter:["class"]});
        window.addEventListener("resize", run); box.style.transition = side + " .15s"; run(); };
      window.followPanels = (box, p)=>{ if(p === "right" || p === "left") window.rsFollow(box, p); };
      // the scale bar and the zoom level: one small box in the bottom left corner, 28 px high, of a fixed width (the scale bar's longest state and a 56 px
      // slot for "z 15.7"), so that it never jumps on a zoom; its text cannot be selected and it ignores the pointer
      const scale = document.querySelector(".maplibregl-ctrl-scale"), zoom = document.querySelector(".rs-zoom");
      if(scale || zoom){
        const box = document.createElement("div"); box.id = "rs-scalebox"; document.body.appendChild(box);
        if(scale){ const slot = document.createElement("div"); slot.className = "rs-scale-slot"; slot.appendChild(scale); box.appendChild(slot);
          // MapLibre's scale control has a longest bar (maxWidth); 140 px, so that the bar never leaves its slot of 150 px
          const ctl = (map._controls || []).find(c=>c && c.options && "maxWidth" in c.options && c._onMove); if(ctl){ ctl.options.maxWidth = 140; ctl._onMove(); } }
        if(zoom){ zoom.classList.add("rs-zoom-slot"); box.appendChild(zoom); }
        window.rsFollow(box, "left");       // beside an open left panel
      }
      // a floating window stays inside the map at every drag move
      const mapRect = ()=>map.getContainer().getBoundingClientRect();
      // the right edge of the free map: the toolbar's left edge less 8 px (the bar slides beside an open right panel, and so does this edge)
      const barLeft = m=>{ const t = document.getElementById("rs-toolbar"), r = t && getComputedStyle(t).display !== "none" && t.getBoundingClientRect();
        return r && r.width > 0 && pos === "right" && innerWidth > 520 ? Math.min(m.right - 8, r.left - 8) : m.right - 8; };
      const fit = w=>{ if(!w || w.hidden) return; const m = mapRect(), gap = 8, lim = barLeft(m);
        const W = Math.min(w.offsetWidth, lim - m.left - gap), H = Math.min(w.offsetHeight, m.height - 28);
        Object.assign(w.style, {width:W+"px", height:H+"px"});
        const r = w.getBoundingClientRect();
        Object.assign(w.style, {left:Math.max(m.left+gap, Math.min(r.left, lim-W))+"px", top:Math.max(m.top+gap, Math.min(r.top, m.bottom-H-gap))+"px", right:"auto", bottom:"auto"}); };
      const wins = ()=>document.querySelectorAll(".rs-svw");
      document.addEventListener("pointermove", ()=>document.querySelectorAll(".rs-svw.rs-drag").forEach(fit), true);
      // a window opens in the visible part: right of an open left panel, left of an open right panel and the toolbar's strip
      const vis = e=>e && getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0;
      const placeVisible = w=>{ if(!w || w.hidden) return; const m = mapRect(), sb = document.getElementById("sb"), side = document.querySelector(".rs-side");
        const left = vis(sb) && sb.getBoundingClientRect().left < innerWidth/2 ? sb.getBoundingClientRect().right : m.left;
        const right = Math.min(barLeft(m) + 8, vis(side) ? side.getBoundingClientRect().left : m.right);
        const r = w.getBoundingClientRect(), gap = 12;
        if(r.left >= left && r.right <= right) return;
        Object.assign(w.style, {left:Math.max(left+gap, Math.min(r.left, right-r.width-gap))+"px", top:Math.max(m.top+gap, r.top)+"px", right:"auto", bottom:"auto"}); };
      const opened = new MutationObserver(l=>l.forEach(x=>setTimeout(()=>placeVisible(x.target), 120)));
      wins().forEach(w=>opened.observe(w, {attributes:true, attributeFilter:["hidden"]}));
      // the windows follow the bar: when it slides (a right panel opens or closes) or the window is resized, a window that reaches under it moves left
      const keep = ()=>wins().forEach(w=>{ if(w.hidden || w.classList.contains("rs-drag")) return; const m = mapRect(), lim = barLeft(m), r = w.getBoundingClientRect();
        if(r.right > lim + 0.5) fit(w); });
      window.rsKeepWindows = keep;           // the bar is made later: it calls this when it exists
      addEventListener("resize", keep);
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
      at.innerHTML = '<button type="button" id="rs-attr-btn" title="Attribution"><svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg></button><div id="rs-attr-box" hidden></div>';
      tb.appendChild(at);
      const box = at.querySelector("#rs-attr-box");
      at.querySelector("button").onclick = e=>{ e.stopPropagation();
        if(box.hidden){ const inner = document.querySelector(".maplibregl-ctrl-attrib-inner"), g = [".rs-g3d", ".rs-svw:not(.rs-g3d)"].some(s=>{ const w = document.querySelector(s); return w && !w.hidden; });
          box.innerHTML = (inner ? inner.innerHTML : "") + (g ? "<div>Google Maps: map data \u00a9 Google</div>" : ""); }
        box.hidden = !box.hidden; };
      document.addEventListener("click", e=>{ if(!e.target.closest || !e.target.closest(".rs-attr-ctrl")) box.hidden = true; }, true);
      document.addEventListener("keydown", e=>{ if(e.key === "Escape") box.hidden = true; }, true);
      // the theme switch: the first button of the bar (above zoom in); it presses the dashboard's own "Light / dark" button, which is then hidden
      const thBtn = document.getElementById("sb-th"), sbTh = document.getElementById("sb");
      if(thBtn && sbTh){
        const th = document.createElement("div"); th.className = "maplibregl-ctrl maplibregl-ctrl-group rs-theme-ctrl";
        const SUN = '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
        const MOON = '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/></svg>';
        th.innerHTML = '<button type="button" id="rs-theme-btn" title="Light / dark"></button>';
        const tb2 = th.querySelector("button"), paint = ()=>{ const dark = sbTh.dataset.theme === "dark"; tb2.innerHTML = dark ? MOON : SUN; tb2.dataset.theme = dark ? "dark" : "light"; };
        tb2.onclick = ()=>thBtn.click();
        new MutationObserver(paint).observe(sbTh, {attributes:true, attributeFilter:["data-theme"]}); paint();
        tb.insertBefore(th, tb.firstChild); document.documentElement.classList.add("rs-theme-in-bar");
      }
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
        // a swatch is [land, road, water]: the land colour, a diagonal road stroke, and a water triangle in the lower right corner (drawn in CSS)
        const swatchCss = b=>{ const s = b.swatch; if(!Array.isArray(s)) return s || b.bg;
          return "linear-gradient(to top left," + s[2] + " 0 32%,transparent 32%)," + "linear-gradient(135deg,transparent 0 40%," + s[1] + " 40% 54%,transparent 54%)," + s[0]; };
        let current = (bms[0] || {}).key;
        menu.appendChild(el("div", "rs-bm-h", "Base map"));
        const rows = [];
        bms.map((b, i)=>[b, i]).filter(([b])=>!b.twin).sort((x, y)=>(x[0].order ?? 99) - (y[0].order ?? 99) || x[1] - y[1]).forEach(([b, i])=>{
          const lab = el("label", "rs-bm-row"), r = el("input"); r.type = "radio"; r.name = "rs-bm"; r.value = b.key;
          const sw = el("span", "rs-bm-sw"); sw.style.background = swatchCss(b); sw.dataset.key = b.key;
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
        // THE LABELS SWITCH works only where it can: on an OpenFreeMap style it shows or hides the style's own symbol layers; on Esri Satellite, Esri Gray
        // and Blank it adds Esri's reference labels; on a raster map with labels baked in (OpenStreetMap, Esri Streets, CARTO) it is greyed, so no name
        // shows twice. "want" is the reviewer's choice; the Google 3D view follows it only where the switch works.
        const labelKind = ()=>vector() ? "style" : /^(satellite|esri_gray|esri_dark_gray|blank|blank_dark)$/.test(current) ? "esri" : "baked";
        let want = ls("labels") == null ? null : ls("labels") === "1", lastOn = null;
        const labelsOn = ()=>labelKind() !== "baked" && (want == null ? vector() : want);
        window.rsLabelsOn = labelsOn;          // one state for the map and the Google 3D view (HYBRID with labels, SATELLITE without)
        const apply = ()=>{
          const vec = vector(), sat = current === "satellite", kind = labelKind(), on = labelsOn();
          raster("hillshade", tops.hillshade.c.checked);
          raster("labels", kind === "esri" && !sat && on);
          raster("satlabels", kind === "esri" && sat && on);
          if(vec) for(const l of map.getStyle().layers.filter(x=>x.id.startsWith("vbm-") && x.type === "symbol")) map.setLayoutProperty(l.id, "visibility", on ? "visible" : "none");
          tops.labels.c.disabled = kind === "baked"; tops.labels.c.checked = on;
          tops.labels.lab.title = kind === "baked" ? "This base map has its own labels" : ""; tops.labels.lab.classList.toggle("rs-bm-off", kind === "baked");
          tops.satlabels.lab.hidden = true;                  // the switch above does this one's work on Esri Satellite
          tops.buildings.c.disabled = !vec; tops.buildings.c.checked = vec && window.rsBuildings ? window.rsBuildings() : false;
          if(lastOn !== on){ lastOn = on; document.dispatchEvent(new Event("rs:labelschange")); } };
        topRow("hillshade", "Hillshade").checked = ls("hillshade") === "1";
        topRow("labels", "Labels");
        topRow("buildings", "3D buildings");
        topRow("satlabels", "Satellite labels");
        for(const id of ["hillshade", "labels"]) tops[id].c.onchange = ()=>{ if(id === "labels") want = tops.labels.c.checked; ss(id, tops[id].c.checked); apply(); };
        tops.buildings.c.onchange = ()=>{ if(window.rsBuildings) window.rsBuildings(tops.buildings.c.checked); };
        const mark = ()=>{ rows.forEach(([b, r])=>{ r.checked = b.key === current || b.dark === current; }); };
        document.addEventListener("rs:basemapchange", e=>{ current = e.detail.basemap; mark(); setTimeout(apply, 0); });
        document.addEventListener("rs:basemapready", apply);
        document.addEventListener("rs:buildingschange", apply);
        // the page's theme switch changes a map that has a twin at once, and leaves a map with no twin as it is
        const sbT = document.getElementById("sb");
        if(sbT) new MutationObserver(()=>{ const dark = sbT.dataset.theme === "dark", b = bms[byKey(current)]; if(!b) return;
          if(dark && b.dark) window.rsSetBasemap(b.dark);
          else if(!dark){ const light = bms.find(x=>x.dark === current); if(light) window.rsSetBasemap(light.key); } }).observe(sbT, {attributes:true, attributeFilter:["data-theme"]});
        // a map with a twin shows the swatch of the twin of the current theme
        const swatches = ()=>{ rows.forEach(([b, r])=>{ const sw = r.parentElement.querySelector(".rs-bm-sw"), tw = b.dark && bms[byKey(b.dark)]; sw.style.background = swatchCss(isDark() && tw ? tw : b); }); };
        new MutationObserver(()=>setTimeout(swatches, 0)).observe(root, {attributes:true, attributeFilter:["data-rs-theme"]}); swatches();
        mark(); apply();
        // the box opens inside the window: moved up or down by what it overhangs
        new MutationObserver(()=>{ if(!menu.classList.contains("open")) return; menu.style.marginTop = "0px";
          const r = menu.getBoundingClientRect(), over = r.bottom - (innerHeight - 8), under = 8 - r.top;
          menu.style.marginTop = (over > 0 ? -over : under > 0 ? under : 0) + "px"; }).observe(menu, {attributes:true, attributeFilter:["class"]});
        document.addEventListener("keydown", e=>{ if(e.key === "Escape") menu.classList.remove("open"); }, true);
      }
      // the base-map button: the layers icon (three tilted sheets: the top one filled, the two below as outlines)
      const bmBtn = tb.querySelector(".bm-icon");
      if(bmBtn){ bmBtn.title = "Base map and layers"; bmBtn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"><path class="rs-sheet" d="M12 3 3 8l9 5 9-5-9-5z" fill="currentColor"/><path class="rs-sheet" d="M3 12.5l9 5 9-5" fill="none"/><path class="rs-sheet" d="M3 17l9 5 9-5" fill="none"/></svg>'; }
      filled = true; reveal();
      tb.querySelectorAll("button").forEach(b=>{ if(!b.title) b.title = b.getAttribute("aria-label") || b.textContent.trim() || "Control"; });
      // A panel on the side of a corner box or of the bar never covers it: when the panel is open, the box slides to 8 px beside it (150 ms); when the
      // panel closes, it goes back to the edge. The position along the edge does not change.
      if(overlay) window.followPanels(tb, pos);
      if(window.rsKeepWindows){ const keep = window.rsKeepWindows; new MutationObserver(keep).observe(tb, {attributes:true, attributeFilter:["style", "class"]});
        tb.addEventListener("transitionrun", ()=>{ const t0 = performance.now(); (function f(){ keep(); if(performance.now() - t0 < 500) requestAnimationFrame(f); })(); }); }
    }
  }, 150);
})();

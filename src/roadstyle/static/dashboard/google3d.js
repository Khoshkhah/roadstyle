// GOOGLE 3D window (google_3d=True, with a key): Google's photorealistic 3D view in a floating window,
// opened by its map button (or rsSetGoogle3D(true)). The map leads, one way only: the page sets Google's camera from the map's
// (center = center, bearing = heading, pitch = tilt, zoom -> range: the metres from Google's camera to its center), and nothing moves the
// map from Google. A selected road is drawn in the 3D view. Google's 3D map exists only while the window is
// open: closing it drops it, as nothing is loaded from Google while it is closed.
import {map, O, _road, _rprops} from "./core.js";
import {_gmLoad, _rsFloat} from "./float.js";
import {_svKey} from "./streetview.js";
import {_svLine, _svDist, _svAt} from "./svspot.js";
export function rsSetGoogle3D(){}
export function initGoogle3D(){
  if(O.google_3d){
    const w=document.createElement("div"); w.className="rs-svw rs-g3d"; w.hidden=true;
    w.innerHTML='<div class="rs-svw-bar"><span class="rs-svw-t">Google 3D</span>'+
      '<span class="rs-g3d-note rs-g3d-tun" hidden>This road is in a tunnel: Google shows the surface above it</span>'+
      '<span class="rs-g3d-warn" hidden title="The ground heights did not load: on a hill, the 3D view can be closer than the map">\u26a0 no ground heights</span>'+
      '<a class="rs-g3d-src" href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noopener"'+
      ' title="Ground heights: Terrain Tiles on AWS (Mapzen; SRTM and other sources)">heights: Mapzen</a>'+
      '<button type="button" class="rs-g3d-follow on" title="Follow the map">Following</button>'+
      '<button type="button" title="Close">✕</button></div><div class="rs-svw-msg"></div>';
    document.body.appendChild(w);
    const bar=w.firstChild, ttl=w.querySelector(".rs-svw-t"), msg=w.querySelector(".rs-svw-msg"), tun=w.querySelector(".rs-g3d-tun");
    const {st, save, place}=_rsFloat(w, bar, "rs-google-3d-window", true);
    let m3=null, lib=null, line=null, btn=null;
    const say=html=>{ msg.innerHTML=html; msg.hidden=false; if(m3){ m3.remove(); m3=null; line=null; } };
    const SETUP='<a href="https://khoshkhah.github.io/roadstyle/guides/google-key/" target="_blank" rel="noopener">How to set up the key ↗</a>';
    const prevAuth=window.gm_authFailure;       // Google calls this when it refuses the key on this address
    window.gm_authFailure=()=>{ if(prevAuth) prevAuth();
      say("<b>Google refused the key on this page.</b><span>Add <code>"+location.origin+"/*</code> to the key's Websites list.</span>"+SETUP); };
    // the camera link
    const rad=d=>d*Math.PI/180, EARTH=40075016.686;
    const camPx=()=>map.getCanvas().clientHeight/2/Math.tan(rad(map.getVerticalFieldOfView())/2);  // the map's camera to its center, px
    // THE GROUND'S HEIGHT under the center. Google's center is in metres above SEA LEVEL, and the map's
    // center is on the ground: on a hill (Monaco, 120 m) a center at 0 m was under the ground, and Google's
    // camera came far too close. The height comes from the free Terrain Tiles on AWS (Terrarium PNGs, no
    // key, the bare ground): one zoom-14 tile per area, kept; a pixel's color is its height. Until a tile
    // is in, the last height found holds, and its arrival moves Google to the right height. The sea floor
    // counts as 0 m: the map's water is at sea level.
    const DEM_Z=14, dem=new Map(), warn=w.querySelector(".rs-g3d-warn");
    let lastGround=0;
    const ground=(lng, lat)=>{
      const n=2**DEM_Z, x=(lng+180)/360*n, y=(1-Math.log(Math.tan(rad(lat))+1/Math.cos(rad(lat)))/Math.PI)/2*n;
      const key=DEM_Z+"/"+Math.floor(x)+"/"+Math.floor(y);
      let t=dem.get(key);
      if(!t){ t={px:null}; dem.set(key, t);
        const img=new Image(); img.crossOrigin="anonymous";
        img.onload=()=>{ const c=document.createElement("canvas"); c.width=c.height=256;
          const g=c.getContext("2d", {willReadFrequently:true}); g.drawImage(img, 0, 0);
          t.px=g.getImageData(0, 0, 256, 256).data; if(m3 && follow) setGoogle(); };
        img.onerror=()=>{ warn.hidden=false; console.warn("rs google 3d: no ground heights from", img.src); };
        img.src="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"+key+".png"; }
      if(!t.px) return lastGround;
      const i=(Math.min(255, Math.floor(x%1*256))+Math.min(255, Math.floor(y%1*256))*256)*4;
      return lastGround=Math.max(0, t.px[i]*256+t.px[i+1]+t.px[i+2]/256-32768); };
    // THE RANGE. By default the range is the map's own camera distance (the map's fov of 36.9 degrees and its canvas height).
    // Google's 3D camera has its own, narrower field of view, so the window showed less ground than the map. A page can set
    // window.rsG3dFov (degrees, Google's vertical fov, measured): the range then makes the window's vertical extent on the
    // ground equal to the map's, whatever the window's height.
    const mpp=(lat, zoom)=>EARTH*Math.cos(rad(lat))/(512*Math.pow(2, zoom));
    const fov=()=>typeof window.rsG3dFov==="number" && window.rsG3dFov>0 ? window.rsG3dFov : 0;
    const winH=()=>Math.max(120, map.getCanvas().clientHeight);        // the map's canvas: the extent to cover
    const rangeOf=(lat, zoom)=> fov() ? winH()*mpp(lat, zoom)/2/Math.tan(rad(fov())/2) : camPx()*mpp(lat, zoom);
    const zoomOf=(lat, range)=> fov() ? Math.log2(EARTH*Math.cos(rad(lat))/(512*(2*range*Math.tan(rad(fov())/2)/winH())))
                                       : Math.log2(EARTH*Math.cos(rad(lat))*camPx()/(512*range));
    // Google will not put its camera into its own 3D tiles (over the imagery), and its drawn 3D map keeps its camera far away: then the view shows more than
    // the map. Nothing is shown on the window for it. window.rsG3dCamera() gives the numbers for a page's debug line: the camera's height above the ground
    // (range times cos tilt), Google's mode, and whether the camera is below the limit of the mode (MIN_ALT, or MIN_ZOOM_DRAWN in the drawn map).
    const MIN_ALT=80, MIN_ZOOM_DRAWN=17;      // MIN_ALT: metres above the ground, seen at Sainte-Devote, zoom 19.9 (73 m), the view widened
    const drawnMode=()=>!!m3 && !!m3.mode && !/^(HYBRID|SATELLITE)$/i.test(String(m3.mode));
    window.rsG3dCamera=()=>{ const r=m3 && m3.range || rangeOf(map.getCenter().lat, map.getZoom()), t=m3 ? (m3.tilt||0) : map.getPitch(), c=map.getCenter(), drawn=drawnMode();
      const minAlt=typeof window.rsG3dMinAlt==="number" ? window.rsG3dMinAlt : MIN_ALT, minZoom=typeof window.rsG3dMinZoomDrawn==="number" ? window.rsG3dMinZoomDrawn : MIN_ZOOM_DRAWN;
      return {above:r*Math.cos(rad(t)), range:r, tilt:t, ground:ground(c.lng, c.lat), sea:(m3 && m3.center && m3.center.altitude || 0)+r*Math.cos(rad(t)),
              drawn, limit:drawn ? "zoom above "+minZoom : "camera under "+minAlt+" m", low:drawn ? map.getZoom()>minZoom : r*Math.cos(rad(t))<minAlt}; };
    const toGoogle=()=>{ const c=map.getCenter();
      return {center:{lat:c.lat, lng:c.lng, altitude:ground(c.lng, c.lat)}, heading:(map.getBearing()+360)%360, tilt:map.getPitch(),
              range:rangeOf(c.lat, map.getZoom())}; };
    // THE MAP LEADS, ONE WAY ONLY. On every map move (coalesced to one per frame) the page sets Google's camera from the map: centre with the ground height,
    // heading, tilt, and the range from rsG3dFov. No code path moves the map from Google: Google moves its own camera by hidden rules (its limits, the mesh
    // under its target, inertia) and does not report it, so following it made an echo. The window is a viewer: the reviewer can drag, turn and zoom inside
    // it, and that moves only the 3D view. "Follow" (on by default) goes off at the reviewer's first input inside the window (a pointerdown, a wheel, a
    // touchstart or a keydown, captured on the window; its title bar is not "inside"). It goes on by a click on it (Google is then set to the map once),
    // by a road selection, or by a Guide step. Google's own view switch changes only the picture.
    const COUNT=window.rsG3dCount={m2g:0, follow:true};
    let follow=true, setQueued=false;
    const fbtn=w.querySelector(".rs-g3d-follow");
    const paintFollow=()=>{ COUNT.follow=follow; fbtn.classList.toggle("on", follow); fbtn.setAttribute("aria-pressed", follow);
      fbtn.textContent=follow ? "Following" : "Follow the map";
      fbtn.title=follow ? "Following the map: a drag in this window stops it" : "Not following the map: click to follow again"; };
    const setGoogle=()=>{ if(!m3) return; Object.assign(m3, toGoogle()); COUNT.m2g++; };
    const setFollow=on=>{ follow=!!on; paintFollow(); if(follow) setGoogle(); };
    window.rsG3dFollow=setFollow;
    map.on("move", ()=>{ if(!m3 || !follow || setQueued) return; setQueued=true; requestAnimationFrame(()=>{ setQueued=false; if(follow) setGoogle(); }); });
    // What turns Follow off: a drag (the pointer moves more than 6 px while down), a second finger (a pinch), a wheel, a touch with two fingers or a key, inside
    // the picture. A plain click, and a click on Google's own controls (the view switch, the compass, the expand button), do not.
    const inBar=e=>e.target && e.target.closest && e.target.closest(".rs-svw-bar");
    const stop=()=>{ if(follow){ follow=false; paintFollow(); } };
    const downs=new Map();
    w.addEventListener("pointerdown", e=>{ if(inBar(e)) return; if(downs.size>=1) stop(); downs.set(e.pointerId, [e.clientX, e.clientY]); }, true);
    w.addEventListener("pointermove", e=>{ const d=downs.get(e.pointerId); if(d && Math.hypot(e.clientX-d[0], e.clientY-d[1])>6) stop(); }, true);
    for(const t of ["pointerup", "pointercancel"]) window.addEventListener(t, e=>downs.delete(e.pointerId), true);
    w.addEventListener("wheel", e=>{ if(!inBar(e)) stop(); }, true);
    w.addEventListener("touchstart", e=>{ if(!inBar(e) && e.touches && e.touches.length>1) stop(); }, true);
    w.addEventListener("keydown", e=>{ if(!inBar(e)) stop(); }, true);
    // after a change of the view (Google's own switch or the Labels switch) with Follow on, Google is set to the map's camera once, 300 ms later
    let afterT=0;
    const afterSwitch=()=>{ clearTimeout(afterT); afterT=setTimeout(()=>{ if(m3 && follow) setGoogle(); }, 300); };
    fbtn.onclick=()=>setFollow(true);
    // THE MAP'S CENTER BESIDE THE WINDOW: while the window is open, the map's padding puts its center (the
    // point the two cameras share, where a clicked road comes to) in the middle of the map's free side, so
    // the window does not cover it. Phones keep the plain center: there the window docks at the bottom.
    const pad=()=>{
      const m=map.getContainer().getBoundingClientRect(), r=w.getBoundingClientRect(), p={...map.getPadding(), left:0, right:0};
      if(!w.hidden && innerWidth>520 && window.rsWindowRecentre!==false){      // a page can set window.rsWindowRecentre=false: the map then never moves for the window
        if(r.left+r.width/2 < m.left+m.width/2) p.left=Math.max(0, r.right-m.left);
        else p.right=Math.max(0, m.right-r.left); }
      const o=map.getPadding();
      if(Math.abs(o.left-p.left)>1 || Math.abs(o.right-p.right)>1) map.easeTo({padding:p, duration:300});
    };
    new ResizeObserver(pad).observe(w);          // opened, closed or resized
    bar.addEventListener("pointerup", pad);      // dragged
    map.on("resize", pad);
    // THE LABELS. SATELLITE has no labels or pins, HYBRID has them. The page's "Labels" switch (the base-map box, window.rsLabelsOn) rules both
    // the map and this view; without that switch the view has no labels.
    // THE MODE. The page sets the mode when the window opens and when the Labels switch changes (SATELLITE, or HYBRID with labels), and otherwise
    // leaves Google's own toggle alone (the round thumbnail at the top right of the window: imagery or Google's stylised 3D map). The reviewer's
    // last choice is kept for the next opening. window.rsG3dLog keeps Google's last console warnings, and window.rsG3dMode() the mode the
    // element reports (the debug line shows both).
    const modeOf=l=>{ const n=window.rsLabelsOn && window.rsLabelsOn() ? "HYBRID" : "SATELLITE"; return (l.MapMode && l.MapMode[n]) || n; };
    const MODE_KEY="rs-g3d-mode:"+location.pathname;
    const keptMode=()=>{ try{ return localStorage.getItem(MODE_KEY); }catch(e){ return null; } };
    const keepMode=()=>{ if(m3 && m3.mode){ try{ localStorage.setItem(MODE_KEY, String(m3.mode)); }catch(e){} } };
    const LOG=window.rsG3dLog=[];
    for(const k of ["warn", "error"]){ const f=console[k]; console[k]=function(...a){ try{ const t=a.map(String).join(" ");
      if(/google|maps|3d|gmp|tile/i.test(t)){ LOG.push(k+": "+t.slice(0, 160)); if(LOG.length>24) LOG.shift(); } }catch(e){} return f.apply(this, a); }; }
    window.rsG3dMode=()=>m3 ? String(m3.mode) : null;
    // THE LABELS SWITCH only adds or removes labels, never the view. In the imagery: HYBRID with labels, SATELLITE without. In Google's drawn map: the API's
    // label option (defaultLabelsDisabled) when the loaded version has one; if it has none the drawn map is left as it is, and the switch's tooltip says so.
    const hasLabelOption=()=>!!m3 && "defaultLabelsDisabled" in m3;
    window.rsLabelsTipExtra=()=>drawnMode() && !hasLabelOption() ? "Google's drawn 3D map keeps its labels" : "";
    const applyLabels=()=>{ if(!m3 || !lib) return false;
      if(drawnMode()){ if(hasLabelOption()) m3.defaultLabelsDisabled=!(window.rsLabelsOn && window.rsLabelsOn()); return false; }
      const mode=modeOf(lib); if(String(m3.mode)===String(mode)) return false; m3.mode=mode; return true; };
    // A MODE CHANGE (Google's own toggle or the page's): every polyline is removed from the 3D map and the selected entity's line is drawn again from the
    // build's geometry, 300 ms after the switch and again after Google's first camera event in the new mode. One line, the build's, in both views.
    let redrawT=0, redrawNext=false;
    const clearLines=()=>{ if(m3) m3.querySelectorAll("gmp-polyline-3d").forEach(x=>x.remove()); line=null; };
    const redrawRoad=()=>{ if(m3 && want) tryDraw(want.cs, want.name, want.lvl, true); };
    const modeChanged=()=>{ keepMode(); document.dispatchEvent(new Event("rs:g3dmodechange")); afterSwitch(); clearLines(); redrawNext=true; clearTimeout(redrawT); redrawT=setTimeout(redrawRoad, 300); };
    document.addEventListener("rs:labelschange", ()=>{ if(applyLabels()) modeChanged(); else document.dispatchEvent(new Event("rs:g3dmodechange")); });
    let lastMode=null;      // Google's own toggle changes the mode without the page: only the picture changes
    setInterval(()=>{ if(!m3){ lastMode=null; return; } const v=String(m3.mode); if(lastMode!==null && v!==lastMode) modeChanged(); lastMode=v; }, 200);
    const open=()=>{
      if(location.protocol==="file:"){
        say("<b>Google 3D needs this page served, not opened from disk.</b>"+
            "<span>Run <code>python -m http.server</code> in its folder and open it from an address in the key's Websites list.</span>"+SETUP);
        return; }
      msg.textContent="Loading Google 3D…"; msg.hidden=false;
      _gmLoad(_svKey).then(()=>google.maps.importLibrary("maps3d")).then(l=>{
        if(w.hidden || m3) return;               // closed while it loaded
        lib=l; m3=new l.Map3DElement(Object.assign(toGoogle(), {mode:(k=>k && !/^(HYBRID|SATELLITE)$/i.test(k) ? k : modeOf(l))(keptMode())}));
        m3.addEventListener("gmp-modechange", ()=>{ modeChanged(); lastMode=String(m3.mode); });
        for(const ev of ["gmp-centerchange", "gmp-headingchange", "gmp-tiltchange", "gmp-rangechange"])           // only to draw the road again: nothing moves from Google's camera
          m3.addEventListener(ev, ()=>{ if(redrawNext){ redrawNext=false; redrawRoad(); } });
        m3.addEventListener("gmp-error", e=>{ LOG.push("gmp-error: "+((e && (e.message || (e.detail && e.detail.message))) || "")); say("<b>Google 3D imagery did not load.</b><span>Google reported an error; the window does not show another style.</span>"); });
        msg.hidden=true; w.appendChild(m3); applyLabels(); document.dispatchEvent(new Event("rs:g3dmodechange"));
        if(want) setTimeout(()=>{ if(m3) tryDraw(want.cs, want.name, want.lvl, true); }, 0);
      }).catch(e=>{ console.warn("rs google 3d:", e); say("<b>Google 3D did not load.</b><span>"+String(e.message||e)+"</span>"+SETUP); });
    };
    // DRAW A ROAD in the 3D view. cs: the road's [lng, lat] points; lvl: its level. rs:select calls it for a click on a road;
    // a page with its own selection (a stepper, a list) calls window.rsG3dDraw(cs, name, lvl). A road asked for before the view exists is drawn when it opens.
    let want=null;
    const draw=(any, name, lvl, keep)=>{
      const parts=(Array.isArray(any[0]) && Array.isArray(any[0][0]) ? any : [any]).filter(c=>c.length>1);     // one line, or several
      want={cs:any, name, lvl};
      if(!m3 || !lib || !parts.length) return;
      if(!keep) setFollow(true);               // a road selection turns Follow on: the map leads (a redraw after a mode change does not)
      ttl.textContent=name||"Unnamed road";
      if(line) line.forEach(x=>x.remove());
      m3.querySelectorAll("[data-rs-sel]").forEach(x=>x.remove());       // one selection, one line: whatever an earlier draw left goes
      line=[]; tun.hidden=true;
      // THE LINE LIES ON GOOGLE'S MESH, not on its terrain model: RELATIVE_TO_MESH at 0.5 m, a vertex every 5 m so it follows the street between
      // the OSM nodes (streets cut into rock and built-up ground differ from the terrain, and a tilted camera showed the line shifted).
      // A hidden part shows faintly (drawsOccludedSegments). A tunnel (level below 0) is dashed, with a note: Google shows the surface only.
      const MESH=(lib.AltitudeMode||{}).RELATIVE_TO_MESH||"RELATIVE_TO_MESH";
      const mk=(r, o)=>new lib.Polyline3DElement(Object.assign({path:r.map(c=>({lat:c[1], lng:c[0], altitude:0.5})), altitudeMode:MESH, strokeColor:O.select_color,
        strokeWidth:4, outerColor:"#ffffff", outerWidth:0.3, drawsOccludedSegments:true}, o));
      // every original vertex is kept (a smooth arc stays an arc), and a segment longer than 5 m gets points in between
      const densify=cs=>{ const out=[cs[0]], k=Math.cos(cs[0][1]*Math.PI/180);
        for(let i=1; i<cs.length; i++){ const [x0, y0]=cs[i-1], [x1, y1]=cs[i], m=Math.hypot((x1-x0)*111320*k, (y1-y0)*111320), n=Math.ceil(m/5);
          for(let j=1; j<n; j++) out.push([x0+(x1-x0)*j/n, y0+(y1-y0)*j/n]); out.push(cs[i]); }
        return out; };
      for(const raw of parts){
        const cs=densify(raw), dd=_svDist(cs), total=dd[dd.length-1];
        const at=t=>{ let i=1; while(i<dd.length-1 && dd[i]<t) i++; const u=(t-dd[i-1])/((dd[i]-dd[i-1])||1); return [cs[i-1][0]+(cs[i][0]-cs[i-1][0])*u, cs[i-1][1]+(cs[i][1]-cs[i-1][1])*u]; };
        const run=(a, b)=>[at(a)].concat(cs.filter((c, i)=>dd[i]>a && dd[i]<b), [at(b)]);          // the part from a to b metres, with the line's own vertices
        if(lvl<0){ tun.hidden=false;
          for(let a=0; a<total; a+=12) line.push(mk(run(a, Math.min(a+7, total)), {strokeColor:"#7e57c2"})); }
        else line.push(mk(cs)); }
      line.forEach(x=>{ x.dataset.rsSel="1"; m3.appendChild(x); });
    };
    const tryDraw=(cs, name, lvl, keep)=>{ try{ draw(cs, name, lvl, keep); }catch(e){ LOG.push("draw: "+String(e&&e.message||e).slice(0, 140)); console.warn("rs google 3d: the road was not drawn:", e); } };
    window.rsG3dDraw=tryDraw;
    document.addEventListener("rs:select", e=>{  // a road: draw it in the 3D view and fly along it
      const d=e.detail; if(d.overlay) return;
      if(typeof window.rsG3dOwnDraw==="function" && window.rsG3dOwnDraw(d)) return;       // the page draws this road itself, from its own data
      const r=_road(d.id), cs=r ? _svLine(r) : []; if(cs.length<2) return;
      const p=d.properties||{}; tryDraw(cs, p.name||p.highway, (_rprops(d.id)||{}).lvl||0);
    });
    rsSetGoogle3D=function(on){
      w.hidden=!on;
      if(on){ follow=true; paintFollow(); if(innerWidth>520) place(); if(!m3) open(); }
      else { keepMode(); if(m3){ m3.remove(); m3=null; line=null; } ttl.textContent="Google 3D"; tun.hidden=true; }
      st.open=!!on; save(); if(btn) btn.classList.toggle("rs-on", !!on);
      document.dispatchEvent(new CustomEvent("rs:google3dchange", {detail:{open:!!on}}));
    };
    bar.lastChild.onclick=()=>rsSetGoogle3D(false);
    map.addControl({onAdd(){
      const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
      btn=document.createElement("button"); btn.type="button"; btn.title="Google 3D";
      btn.innerHTML='<svg viewBox="0 0 24 24" width="17" height="17" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">'+
        '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/></svg>';
      btn.onclick=()=>rsSetGoogle3D(w.hidden);
      d.appendChild(btn); return d;
    }, onRemove(){}});
    if(st.open) map.once("load", ()=>{ if(window.rsRestoreWindows!==false) rsSetGoogle3D(true); });      // a page can start with its windows closed: window.rsRestoreWindows=false
  }
  window.rsSetGoogle3D = rsSetGoogle3D;
}

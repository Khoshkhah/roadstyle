// GOOGLE 3D window (google_3d=True, with a key): Google's photorealistic 3D view in a floating window,
// opened by its map button (or rsSetGoogle3D(true)). The map leads, one way only: the page sets Google's camera from the map's
// (center = center, bearing = heading, pitch = tilt, zoom -> range: the metres from Google's camera to its center), and nothing moves the
// map from Google. A selected road is drawn in the 3D view. Google's 3D map exists only while the window is
// open: closing it drops it, as nothing is loaded from Google while it is closed.
import {_esc} from "../popup.js";
import {map, O, _road, _rprops, _emit} from "./core.js";
import {_gmLoad, _rsFloat} from "./float.js";
import {defineTool, GOOGLE3D_ICON} from "./tools.js";
import {_wPhone} from "./windows.js";
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
      '<span class="rs-svw-mode rs-g3d-view" role="group" aria-label="View"><button type="button" data-v="imagery" class="on" title="Google\'s 3D photos of the city">Imagery</button>'+
      '<button type="button" data-v="map" title="Google\'s drawn 3D map">Map</button></span>'+
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
    const fov=()=>G && G.fov_deg ? G.fov_deg : 0;
    const winH=()=>Math.max(120, map.getCanvas().clientHeight);        // the map's canvas: the extent to cover
    const rangeOf=(lat, zoom)=> fov() ? winH()*mpp(lat, zoom)/2/Math.tan(rad(fov())/2) : camPx()*mpp(lat, zoom);
    const zoomOf=(lat, range)=> fov() ? Math.log2(EARTH*Math.cos(rad(lat))/(512*(2*range*Math.tan(rad(fov())/2)/winH())))
                                       : Math.log2(EARTH*Math.cos(rad(lat))*camPx()/(512*range));
    // Google will not put its camera into its own 3D tiles (over the imagery), and its drawn 3D map keeps its camera far away: then the view shows more than
    // the map. Nothing is shown on the window for it. window.rsG3dCamera() gives the numbers for a page's debug line: the camera's height above the ground
    // (range times cos tilt), Google's mode, and whether the camera is below the limit of the mode (MIN_ALT, or MIN_ZOOM_DRAWN in the drawn map).
    const D=O.dashboard, G=D && D.google_3d;              // the template's typed options (roadstyle::dashboard::Google3d); no template: none
    const MIN_ALT=G ? G.min_alt_m : 80, MIN_ZOOM_DRAWN=G ? G.min_zoom_drawn : 17;      // MIN_ALT: metres above the ground, seen at Sainte-Devote, zoom 19.9 (73 m), the view widened
    const drawnMode=()=>!!m3 && !!m3.mode && !/^(HYBRID|SATELLITE)$/i.test(String(m3.mode));
    const rsG3dCamera=()=>{ const r=m3 && m3.range || rangeOf(map.getCenter().lat, map.getZoom()), t=m3 ? (m3.tilt||0) : map.getPitch(), c=map.getCenter(), drawn=drawnMode();
      const minAlt=MIN_ALT, minZoom=MIN_ZOOM_DRAWN;
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
    const COUNT={m2g:0, follow:true};
    let follow=G ? G.follow : true, setQueued=false;
    const fbtn=w.querySelector(".rs-g3d-follow");
    const paintFollow=()=>{ COUNT.follow=follow; fbtn.classList.toggle("on", follow); fbtn.setAttribute("aria-pressed", follow);
      fbtn.textContent=follow ? "Following" : "Follow the map";
      fbtn.title=follow ? "Following the map: a drag in this window stops it" : "Not following the map: click to follow again"; };
    // WHAT IS "THE REVIEWER MOVED THE 3D VIEW": any change of Google's camera that the page did not set, whatever the input was (a right-button or Ctrl drag, two
    // fingers, Google's compass or tilt control, a key). The page's own sets are remembered for 2 s: an event within 500 ms of one, or equal to one (1e-7
    // degrees, 0.5 m, 0.2 degrees), is its echo. Nothing counts in the first second after a mode change (Google draws again). The input detection below is a second trigger.
    const sets=[];
    let quietUntil=0;
    const setGoogle=()=>{ if(!m3 || !follow) return; const g=toGoogle(); Object.assign(m3, g); COUNT.m2g++; const now=performance.now();
      sets.push({t:now, lat:g.center.lat, lng:g.center.lng, range:g.range, heading:g.heading, tilt:g.tilt}); while(sets.length && now-sets[0].t>2000) sets.shift(); };
    const turn=(a, b)=>Math.abs(((a-b)%360+540)%360-180);
    const ours=()=>{ const now=performance.now(), c=m3.center||{}, h=m3.heading||0, t=m3.tilt||0, r=m3.range;
      return sets.some(x=>now-x.t<500 || (Math.abs(c.lat-x.lat)<1e-7 && Math.abs(c.lng-x.lng)<1e-7 && Math.abs(r-x.range)<0.5 && turn(h, x.heading)<0.2 && Math.abs(t-x.tilt)<0.2)); };
    let camQ=false;
    const onGoogleCamera=()=>{ if(camQ) return; camQ=true; requestAnimationFrame(()=>{ camQ=false;
      if(!m3 || !follow || performance.now()<quietUntil || !m3.center || !m3.range || ours()) return;
      follow=false; paintFollow(); }); };
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
      if(!w.hidden && !_wPhone() && (!D || D.windows.recenter_map)){      // a page can set window.rsWindowRecentre=false: the map then never moves for the window
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
    const viewBtns=[...w.querySelectorAll(".rs-g3d-view button")];
    const paintView=()=>viewBtns.forEach(b=>{ const on=b.dataset.v===(drawnMode() ? "map" : "imagery"); b.classList.toggle("on", !!m3 && on); b.disabled=!m3; b.setAttribute("aria-pressed", String(!!m3 && on)); });
    viewBtns.forEach(b=>b.onclick=()=>{ if(!m3 || !lib) return; m3.mode = b.dataset.v==="map" ? lib.MapMode.ROADMAP : modeOf(lib); paintView(); });
    const MODE_KEY="rs-g3d-mode:"+location.pathname;
    const keptMode=()=>{ try{ return localStorage.getItem(MODE_KEY); }catch(e){ return null; } };
    const keepMode=()=>{ if(m3 && m3.mode){ try{ localStorage.setItem(MODE_KEY, String(m3.mode)); }catch(e){} } };
    const LOG=[];
    for(const k of ["warn", "error"]){ const f=console[k]; console[k]=function(...a){ try{ const t=a.map(String).join(" ");
      if(/google|maps|3d|gmp|tile/i.test(t)){ LOG.push(k+": "+t.slice(0, 160)); if(LOG.length>24) LOG.shift(); } }catch(e){} return f.apply(this, a); }; }
    const rsG3dMode=()=>m3 ? String(m3.mode) : null;
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
    const clearLines=()=>{ if(m3) m3.querySelectorAll("gmp-polyline-3d, gmp-polygon-3d, gmp-marker-3d").forEach(x=>x.remove()); line=null; };
    const redrawRoad=()=>{ try{ drawLayers(); }catch(e){ LOG.push("redraw: "+String(e&&e.message||e).slice(0, 120)); } };
    const modeChanged=()=>{ quietUntil=performance.now()+1000; keepMode(); document.dispatchEvent(new Event("rs:g3dmodechange")); afterSwitch(); clearLines(); redrawNext=true; clearTimeout(redrawT); redrawT=setTimeout(redrawRoad, 300); };
    document.addEventListener("rs:labelschange", ()=>{ if(applyLabels()) modeChanged(); else document.dispatchEvent(new Event("rs:g3dmodechange")); });
    let lastMode=null;      // Google's own toggle changes the mode without the page: only the picture changes
    setInterval(()=>{ if(!m3){ lastMode=null; return; } const v=String(m3.mode); if(lastMode!==null && v!==lastMode) modeChanged(); lastMode=v; }, 200);
    const open=()=>{
      if(location.protocol==="file:"){
        say("<b>Google 3D needs this page served, not opened from disk.</b>"+
            "<span>Run <code>python -m http.server</code> in its folder and open it from an address in the key's Websites list.</span>"+SETUP);
        return; }
      if(!_svKey){
        say("<b>Google 3D needs a Google Maps key.</b><span>Add it in the settings (the gear button), then reload the page.</span>"+
            (window.rsOpenSettings ? '<button type="button" class="rs-open-settings">Open settings</button>' : "")+SETUP);
        const b=msg.querySelector(".rs-open-settings"); if(b) b.onclick=()=>window.rsOpenSettings();
        return; }
      msg.textContent="Loading Google 3D…"; msg.hidden=false;
      _gmLoad(_svKey).then(()=>google.maps.importLibrary("maps3d")).then(l=>{
        if(w.hidden || m3) return;               // closed while it loaded
        lib=l; m3=new l.Map3DElement(Object.assign(toGoogle(), {mode:(k=>k && !/^(HYBRID|SATELLITE)$/i.test(k) ? k : modeOf(l))(keptMode())}));
        m3.addEventListener("gmp-modechange", ()=>{ modeChanged(); lastMode=String(m3.mode); paintView(); });
        for(const ev of ["gmp-centerchange", "gmp-headingchange", "gmp-tiltchange", "gmp-rangechange"])           // nothing moves the map from Google's camera: they redraw the road once and stop Follow
          m3.addEventListener(ev, ()=>{ if(redrawNext){ redrawNext=false; redrawRoad(); } onGoogleCamera(); });
        m3.addEventListener("gmp-error", e=>{ LOG.push("gmp-error: "+((e && (e.message || (e.detail && e.detail.message))) || "")); say("<b>Google 3D imagery did not load.</b><span>Google reported an error; the window does not show another style.</span>"); });
        quietUntil=performance.now()+1500; msg.hidden=true; w.appendChild(m3); applyLabels(); paintView(); document.dispatchEvent(new Event("rs:g3dmodechange"));
        setTimeout(()=>{ if(m3){ if(want) ttl.textContent=want.name||"Unnamed road"; try{ paintMenu(); drawLayers(); }catch(e){ LOG.push("open: "+String(e&&e.message||e).slice(0, 120)); } } }, 0);
      }).catch(e=>{ console.warn("rs google 3d:", e); say("<b>Google 3D did not load.</b><span>"+_esc(e.message||e)+"</span>"+SETUP); });
    };
    // WHAT THE 3D WINDOW DRAWS: a registry of layers. A layer is {id, label, kind, features(selection, {bounds}) -> GeoJSON, style, arrows, available(), scope, max, on}.
    // kind: "line" (a polyline: style.color, style.width px, style.dash [on, off] metres, arrows: direction arrows along it), "ribbon" (a band around a line:
    // style.widthM metres, or the feature's property style.widthProp, style.fill, style.color for its edge), "polygon" (style.fill, style.color outline),
    // "points" (an octagon of style.radius metres). Every kind lies on Google's mesh (RELATIVE_TO_MESH, `google_3d.mesh_altitude_m`, 1.5 m), keeps every original vertex of a line,
    // gets points only on segments longer than 5 m, is drawn once per selection, and is drawn again on a mode change. By default a layer draws the features
    // tied to the selection; scope:"view" draws those in the visible area instead, at most `max` (500). The built-in layer "selected" is the selected road's
    // line; a page can register a layer of the same id to replace it. A "Show" menu in the window's bar has one checkbox per available layer (shown when
    // there are two or more), and the choice is kept per page. From Python: render_dashboard(google_3d_layers=[{id, label, kind, source, match, scope, max, on, arrows, style}]), a typed list (roadstyle::dashboard::Layer3d).
    const REG=new Map(), LKEY="rs-g3d-layers:"+location.pathname;
    const stored=()=>{ try{ return JSON.parse(localStorage.getItem(LKEY))||{}; }catch(e){ return {}; } };
    const layerOn=d=>{ const v=stored(); return d.id in v ? !!v[d.id] : d.on!==false; };
    const avail=d=>{ try{ return typeof d.available==="function" ? !!d.available() : true; }catch(e){ return false; } };
    const showWrap=document.createElement("span"); showWrap.className="rs-g3d-showwrap"; showWrap.hidden=true;
    showWrap.innerHTML='<button type="button" class="rs-g3d-show" title="What the window draws">Show ▾</button><div class="rs-g3d-menu" hidden></div>';
    bar.insertBefore(showWrap, fbtn);
    const showBtn=showWrap.querySelector(".rs-g3d-show"), menu=showWrap.querySelector(".rs-g3d-menu");
    const paintMenu=()=>{ const list=[...REG.values()].filter(avail); showWrap.hidden=list.length<2;
      menu.innerHTML=""; for(const d of list){ const lab=document.createElement("label"), c=document.createElement("input"); c.type="checkbox"; c.checked=layerOn(d); c.dataset.id=d.id;
        c.onchange=()=>{ const v=stored(); v[d.id]=c.checked; try{ localStorage.setItem(LKEY, JSON.stringify(v)); }catch(e){} drawLayers(); };
        lab.append(c, document.createTextNode(" "+(d.label||d.id))); menu.appendChild(lab); } };
    showBtn.onclick=e=>{ e.stopPropagation(); menu.hidden=!menu.hidden; };
    document.addEventListener("click", e=>{ if(!e.target.closest || !e.target.closest(".rs-g3d-showwrap")) menu.hidden=true; }, true);
    // THE SELECTION STYLE, in one place: the template's `google_3d.selection_style` (a page can change any of its keys). Every kind of a layer with `selection: true` (the built-in
    // "selected" layer, and a page's layer that draws the selected entity) uses it; other layers keep their own style. The core is the map's own selection cyan,
    // 8 px, with a near-black outline of 2 px on both sides, so it reads on dark, light and photo backgrounds; arrows are white with the same outline. Google
    // draws a covered part of a line fainter (drawsOccludedSegments); its strength is Google's.
    const SS=G ? G.selection_style : null;
    const selStyle=()=>({color:SS.color, width:SS.width, outline:SS.outline, outlineWidth:SS.outline_width, arrowColor:SS.arrow_color, arrowWidth:SS.arrow_width,
                         arrowEvery:SS.arrow_every, fill:SS.fill});
    let want=null;
    const selParts=()=>want && want.cs.length ? (Array.isArray(want.cs[0]) && Array.isArray(want.cs[0][0]) ? want.cs : [want.cs]).filter(c=>c.length>1) : [];
    REG.set("selected", {id:"selected", label:"Selected road", kind:"line", selection:true,
      features:()=>({type:"FeatureCollection", features:selParts().map(c=>({type:"Feature", geometry:{type:"LineString", coordinates:c}, properties:{lvl:want.lvl}}))})});
    const register=d=>{ if(!d || !d.id || typeof d.features!=="function") throw new Error("rsG3dLayers.register: a layer needs an id and a features(selection) function"); REG.set(d.id, {kind:"line", ...d}); paintMenu(); drawLayers(); };
    window.rsG3dLayers={register, list:()=>[...REG.values()].map(d=>({id:d.id, label:d.label, kind:d.kind, on:layerOn(d), available:avail(d)})),
      isOn:id=>REG.has(id) && layerOn(REG.get(id)), setOn:(id, on)=>{ const v=stored(); v[id]=!!on; try{ localStorage.setItem(LKEY, JSON.stringify(v)); }catch(e){} paintMenu(); drawLayers(); },
      refresh:()=>{ paintMenu(); drawLayers(); }};
    // a layer of the page (the typed list `google_3d.layers`, from the keyword google_3d_layers): its features are those of a GeoJSON source of the page whose
    // property `match` equals the same property of the selected feature (or the selection's key). The style keys are snake_case in the list and camelCase here.
    const CAMEL={outline_width:"outlineWidth", width_m:"widthM", width_prop:"widthProp"};
    const styleOf=st=>Object.fromEntries(Object.entries(st||{}).map(([k, v])=>[CAMEL[k]||k, v]));
    for(const c of (G ? G.layers : [])) REG.set(c.id, {...c, style:styleOf(c.style), features:(sel, ctx)=>{
      const src=map.getSource(c.source), data=src && src.serialize ? src.serialize().data : null; if(!data || typeof data==="string") return {type:"FeatureCollection", features:[]};
      const fs=data.features||[];
      if(c.scope==="view") return {type:"FeatureCollection", features:fs};
      const want_=sel && sel.props && c.match in sel.props ? sel.props[c.match] : sel && sel.key;
      return {type:"FeatureCollection", features:fs.filter(f=>f.properties && String(f.properties[c.match])===String(want_))}; }});
    // the geometry helpers
    // The altitude mode follows the view. Over the imagery (SATELLITE, HYBRID) a line lies on Google's mesh (RELATIVE_TO_MESH, `google_3d.mesh_altitude_m`, 1.5 m). Google's drawn map
    // (ROADMAP) does not show that mesh: its streets lie flat on the terrain, so there a line is 1 m above the ground (RELATIVE_TO_GROUND). Every kind uses this rule.
    // Google draws a CLAMP_TO_GROUND line as a thin draped line and does not honour its width (seen in the drawn map: 2 px for 8 px set). So in the drawn map a line is
    // RELATIVE_TO_GROUND at 1 m: Google's drawn streets lie on its terrain, and the line keeps its width.
    const drawnAlt=()=>"RELATIVE_TO_GROUND";
    const MESH=()=>drawnMode() ? ((lib.AltitudeMode||{})[drawnAlt()]||drawnAlt()) : ((lib.AltitudeMode||{}).RELATIVE_TO_MESH||"RELATIVE_TO_MESH");
    // over the imagery `mesh_altitude_m` above the mesh: at 0.5 m the mesh's bumps (cars, trees, kerbs) cut the line into pieces
    const MESH_ALT=G ? G.mesh_altitude_m : 1.5;
    const pts=r=>r.map(c=>({lat:c[1], lng:c[0], altitude:drawnMode() && drawnAlt()==='RELATIVE_TO_GROUND' ? 1 : MESH_ALT}));
    // every original vertex is kept (a smooth arc stays an arc), and a segment longer than 5 m gets points in between
    const densify=cs=>{ const out=[cs[0]], k=Math.cos(cs[0][1]*Math.PI/180);
      for(let i=1; i<cs.length; i++){ const [x0, y0]=cs[i-1], [x1, y1]=cs[i], m=Math.hypot((x1-x0)*111320*k, (y1-y0)*111320), n=Math.ceil(m/5);
        for(let j=1; j<n; j++) out.push([x0+(x1-x0)*j/n, y0+(y1-y0)*j/n]); out.push(cs[i]); }
      return out; };
    const along=cs=>{ const dd=_svDist(cs), total=dd[dd.length-1];
      const at=t=>{ let i=1; while(i<dd.length-1 && dd[i]<t) i++; const u=(t-dd[i-1])/((dd[i]-dd[i-1])||1); return [cs[i-1][0]+(cs[i][0]-cs[i-1][0])*u, cs[i-1][1]+(cs[i][1]-cs[i-1][1])*u]; };
      return {dd, total, at, run:(a, b)=>[at(a)].concat(cs.filter((c, i)=>dd[i]>a && dd[i]<b), [at(b)])}; };     // run: the part from a to b metres, with the line's own vertices
    const linesOf=g=>!g ? [] : g.type==="LineString" ? [g.coordinates] : g.type==="MultiLineString" ? g.coordinates : [];
    const ringsOf=g=>!g ? [] : g.type==="Polygon" ? [g.coordinates[0]] : g.type==="MultiPolygon" ? g.coordinates.map(p=>p[0]) : [];
    const pointsOf=g=>!g ? [] : g.type==="Point" ? [g.coordinates] : g.type==="MultiPoint" ? g.coordinates : [];
    const offsetRing=(cs, half)=>{ const k=Math.cos(cs[0][1]*Math.PI/180), L=[], R=[];       // the two edges of a band of half-width `half` metres around the line
      for(let i=0; i<cs.length; i++){ const a=cs[Math.max(0, i-1)], b=cs[Math.min(cs.length-1, i+1)], dx=(b[0]-a[0])*111320*k, dy=(b[1]-a[1])*111320, n=Math.hypot(dx, dy)||1, nx=-dy/n*half, ny=dx/n*half;
        L.push([cs[i][0]+nx/(111320*k), cs[i][1]+ny/111320]); R.push([cs[i][0]-nx/(111320*k), cs[i][1]-ny/111320]); }
      return L.concat(R.reverse()); };
    const circle=(c, r)=>{ const k=Math.cos(c[1]*Math.PI/180); return Array.from({length:8}, (_, i)=>[c[0]+Math.cos(i*Math.PI/4)*r/(111320*k), c[1]+Math.sin(i*Math.PI/4)*r/111320]); };
    let made=[];
    const add=el=>{ el.dataset.rsSel="1"; m3.appendChild(el); made.push(el); return el; };
    const polyline=(r, st, o)=>add(new lib.Polyline3DElement({path:pts(r), altitudeMode:MESH(), strokeColor:st.color||O.select_color, strokeWidth:st.width||4, outerColor:st.outline||"#202124", outerWidth:Math.min(0.5, (st.outlineWidth||1)/(st.width||4)),       // the outline, in px, as a fraction of the stroke: the line stands out on the dark drawn map and on the imagery
      drawsOccludedSegments:true, ...o}));
    const polygon=(ring, st)=>add(new lib.Polygon3DElement({outerCoordinates:pts(ring), altitudeMode:MESH(), fillColor:st.fill||"rgba(14,127,145,0.35)", strokeColor:st.color||"#0E7F91", strokeWidth:st.outlineWidth||2,
      drawsOccludedSegments:true}));
    const arrowsOn=(cs, st0)=>{ const {total, at}=along(cs), k=Math.cos(cs[0][1]*Math.PI/180), ev=st0.arrowEvery||20,     // a chevron every `arrowEvery` m, 3 m long, opening backward
        st={...st0, color:st0.arrowColor||st0.color, width:st0.arrowWidth||st0.width};
      for(let d=ev/2, n=0; d<total && n<40; d+=ev, n++){ const tip=at(d), back=at(Math.max(0, d-3)), dx=(tip[0]-back[0])*111320*k, dy=(tip[1]-back[1])*111320, m=Math.hypot(dx, dy)||1, px=-dy/m*1.2, py=dx/m*1.2;
        for(const sg of [1, -1]) polyline([tip, [back[0]+sg*px/(111320*k), back[1]+sg*py/111320]], st).dataset.rsArrow="1"; } };      // marked: an arrow is not a line of the layer
    const drawFeature=(def, f, st0)=>{ const g=f.geometry, pr=f.properties||{}, st={...(def.selection ? selStyle() : {}), ...st0, ...(pr._style||{})};      // a feature can carry its own style in _style; the selection style is the base of a selection layer
      if(def.kind==="polygon"){ for(const r of ringsOf(g)) polygon(r, st); return; }
      if(def.kind==="points"){ for(const c of pointsOf(g)) polygon(circle(c, st.radius||2), st); return; }
      for(const raw of linesOf(g)){ if(raw.length<2) continue; const cs=densify(raw);
        if(def.kind==="ribbon"){ const w=(st.widthProp && +pr[st.widthProp]) || st.widthM || 3; polygon(offsetRing(cs, w/2), st); continue; }
        const tunnel=pr.lvl<0, dash=tunnel && !def.selection ? [7, 5] : st.dash;      // the selected road is one solid line in both views: short dashes break up on the mesh (the bar's note says "tunnel")
        if(tunnel) tun.hidden=false;
        if(dash){ const {total, run}=along(cs);
          for(let a=0; a<total; a+=dash[0]+dash[1]) polyline(run(a, Math.min(a+dash[0], total)), tunnel && !def.selection ? {...st, color:"#7e57c2"} : st); }
        else polyline(cs, st);
        if(def.arrows) arrowsOn(cs, st); } };
    const inView=(f, b)=>{ const g=f.geometry; return [...linesOf(g).flat(), ...ringsOf(g).flat(), ...pointsOf(g)].some(c=>c[0]>=b.getWest() && c[0]<=b.getEast() && c[1]>=b.getSouth() && c[1]<=b.getNorth()); };
    const drawLayers=()=>{
      if(!m3 || !lib) return;
      m3.querySelectorAll("gmp-polyline-3d, gmp-polygon-3d, gmp-marker-3d").forEach(x=>x.remove());       // one selection, one set of lines: whatever an earlier draw left goes
      made=[]; line=made; tun.hidden=true;
      for(const def of REG.values()){ if(!avail(def) || !layerOn(def)) continue;
        try{ const view=def.scope==="view", b=map.getBounds(); if(!view && !want) continue;
          let fs=(def.features(want && want.sel || {key:want && want.name, props:{}}, {bounds:b, parts:selParts(), level:want ? want.lvl : 0}) || {}).features || [];
          if(view){ fs=fs.filter(f=>inView(f, b)).slice(0, def.max||500); }
          const st=def.style||{}; for(const f of fs) drawFeature(def, f, st);
        }catch(e){ LOG.push("layer "+def.id+": "+String(e&&e.message||e).slice(0, 120)); console.warn("rs google 3d: the layer", def.id, "was not drawn:", e); } }
      // the selected points (sel.points of rsG3dDraw, for example an event on the selected road): a Google pin on a stick, 6 m above the ground or the mesh
      for(const c of (want && want.points) || []){ try{ add(new lib.Marker3DElement({position:{lat:c[1], lng:c[0], altitude:6}, altitudeMode:MESH(), extruded:true})); }
        catch(e){ LOG.push("point: "+String(e&&e.message||e).slice(0, 120)); } } };
    let viewT=0;
    map.on("moveend", ()=>{ if(m3 && [...REG.values()].some(d=>d.scope==="view" && avail(d) && layerOn(d))){ clearTimeout(viewT); viewT=setTimeout(drawLayers, 400); } });
    // DRAW THE SELECTION in the 3D view. cs: the road's [lng, lat] points (or an array of lines, or [] for points only); lvl: its level; sel: {key, props} for the
    // layers tied to the selection, and sel.points: [lng, lat] points of the selection drawn as pins (an event and its road are one selection).
    // rs:select calls it for a click on a road; a page with its own selection (a stepper, a list) calls window.rsG3dDraw(cs, name, lvl, sel).
    // A selection asked for before the view exists is drawn when it opens.
    // the title of a road with no name: its class and length, "Service road, 42 m" or "Primary link, 120 m"
    const ROADY=new Set(["service", "residential", "tertiary", "secondary", "primary", "trunk", "motorway", "unclassified"]);
    const roadTitle=p=>{ p=p||{}; const h=String(p.highway||""), len=+(p.length_m ?? p.length ?? NaN);
      if(!h && !isFinite(len)) return "Unnamed road";
      const cls=h ? (h[0].toUpperCase()+h.slice(1)).replace(/_/g, " ")+(ROADY.has(h) ? " road" : "") : "Road";
      return cls+(isFinite(len) ? ", "+Math.round(len)+" m" : ""); };
    const draw=(any, name, lvl, keep, sel)=>{
      const parts=(Array.isArray(any[0]) && Array.isArray(any[0][0]) ? any : [any]).filter(c=>c.length>1);     // one line, or several
      want={cs:any, name, lvl, sel:sel||(keep && want ? want.sel : null)}; want.points=(want.sel && want.sel.points) || [];
      if(!m3 || !lib || (!parts.length && !want.points.length)) return;
      if(!keep) setFollow(true);               // a road selection turns Follow on: the map leads (a redraw after a mode change does not)
      ttl.textContent=name || roadTitle(want.sel && want.sel.props);
      drawLayers();
    };
    const tryDraw=(cs, name, lvl, keep, sel)=>{ try{ draw(cs, name, lvl, keep, sel); }catch(e){ LOG.push("draw: "+String(e&&e.message||e).slice(0, 140)); console.warn("rs google 3d: the road was not drawn:", e); } };
    window.rsG3dDraw=(cs, name, lvl, sel)=>tryDraw(cs, name, lvl, false, sel);
    document.addEventListener("rs:select", e=>{  // a road: draw it in the 3D view
      const d=e.detail; if(d.overlay) return;
      if(typeof window.rsG3dOwnDraw==="function" && window.rsG3dOwnDraw(d)) return;       // the page draws this road itself, from its own data
      const r=_road(d.id), cs=r ? _svLine(r) : []; if(cs.length<2) return;
      const p=d.properties||{}; tryDraw(cs, p.name||null, (_rprops(d.id)||{}).lvl||0, false, {key:String(d.id), props:p});
    });
    rsSetGoogle3D=function(on){
      w.hidden=!on;
      if(on){ follow=true; paintFollow(); if(!_wPhone()) place(); if(!m3) open(); }
      else { keepMode(); if(m3){ m3.remove(); m3=null; line=null; } paintView(); ttl.textContent="Google 3D"; tun.hidden=true; }
      st.open=!!on; save(); if(btn) btn.classList.toggle("rs-on", !!on);
      _emit("rs:google3dchange", {open:!!on});
    };
    bar.lastChild.onclick=()=>rsSetGoogle3D(false);
    const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
    btn=document.createElement("button"); btn.type="button"; btn.title="Google 3D";
    btn.innerHTML=GOOGLE3D_ICON;
    btn.onclick=()=>rsSetGoogle3D(w.hidden);
    d.appendChild(btn);
    defineTool("google_3d", "window", d, {title: btn.title, open: ()=>rsSetGoogle3D(true), close: ()=>rsSetGoogle3D(false), isOpen: ()=>!w.hidden});
    if(st.open) map.once("load", ()=>{ if(!D || D.windows.restore_open) rsSetGoogle3D(true); });      // a page can start with its windows closed: window.rsRestoreWindows=false
    // the one read-out, behind ?debug=1 (docs/design/dashboard_templates.md, question 5): the camera's numbers, the counters, Google's last warnings and the mode
    if(/[?&]debug=1/.test(location.search)) Object.assign(window, {rsG3dCamera, rsG3dCount: COUNT, rsG3dLog: LOG, rsG3dMode});
  }
  window.rsSetGoogle3D = rsSetGoogle3D;
}

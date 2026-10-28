// GOOGLE 3D window (google_3d=True, with a key): Google's photorealistic 3D view in a floating window,
// opened by its map button (or rsSetGoogle3D(true)). Its camera and the map's are linked both ways:
// center = center, bearing = heading, pitch = tilt, and zoom <-> range (the metres from Google's camera
// to its center: the map's own camera distance at that zoom). A clicked road is drawn in the 3D view
// and the camera flies along it (the map follows). Google's 3D map exists only while the window is
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
      '<span class="rs-g3d-note" hidden></span>'+
      '<span class="rs-g3d-note rs-g3d-tun" hidden>This road is in a tunnel: Google shows the surface above it</span>'+
      '<span class="rs-g3d-warn" hidden title="The ground heights did not load: on a hill, the 3D view can be closer than the map">\u26a0 no ground heights</span>'+
      '<a class="rs-g3d-src" href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noopener"'+
      ' title="Ground heights: Terrain Tiles on AWS (Mapzen; SRTM and other sources)">heights: Mapzen</a>'+
      '<button type="button" title="Close">✕</button></div><div class="rs-svw-msg"></div>';
    document.body.appendChild(w);
    const bar=w.firstChild, ttl=w.querySelector(".rs-svw-t"), msg=w.querySelector(".rs-svw-msg"), tun=w.querySelector(".rs-g3d-tun");
    const {st, save, place}=_rsFloat(w, bar, "rs-google-3d-window", true);
    let m3=null, lib=null, line=null, btn=null, queued=false;
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
          t.px=g.getImageData(0, 0, 256, 256).data; if(m3) setGoogle(); };
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
    // THE CAMERA ABOVE THE BUILDINGS. Google will not put its camera into its own 3D tiles: where the range set from the map's zoom puts the
    // camera lower than the tiles (a roundabout with buildings of 20 to 40 m, zoom 19.9), Google keeps the camera above them,
    // the view shows more than the map, and map3d.range still reports the value set. The camera's height above the ground is the range
    // times cos(tilt). Below window.rsG3dMinAlt (metres, default MIN_ALT: 80) the title bar says so; the page does not stop the map's zoom.
    const NOTE="Google keeps its camera above the buildings: the 3D view shows more than the map", note=w.querySelector(".rs-g3d-note");
    note.textContent=NOTE; note.title=NOTE;
    // The limit depends on the mode. Over the imagery (SATELLITE, HYBRID) it is the camera's height above the ground (MIN_ALT). Google's drawn 3D map
    // (ROADMAP, the dark-blue blocks) keeps its camera much farther away whatever the range set, so there the note shows from a map zoom (MIN_ZOOM_DRAWN;
    // a first value from one screenshot: the view showed 300 to 400 m at zoom 19.3; window.rsG3dMinZoomDrawn sets it).
    const NOTE_DRAWN="Google's drawn 3D map does not come closer: the view shows more than the map; switch to the imagery for a close view";
    const MIN_ALT=80, MIN_ZOOM_DRAWN=17;      // MIN_ALT: metres above the ground, seen at Sainte-Devote, zoom 19.9 (73 m), the view widened
    const drawnMode=()=>!!m3 && !!m3.mode && !/^(HYBRID|SATELLITE)$/i.test(String(m3.mode));
    window.rsG3dCamera=()=>{ const r=m3 && m3.range || rangeOf(map.getCenter().lat, map.getZoom()), t=m3 ? (m3.tilt||0) : map.getPitch(), c=map.getCenter(), drawn=drawnMode();
      const minAlt=typeof window.rsG3dMinAlt==="number" ? window.rsG3dMinAlt : MIN_ALT, minZoom=typeof window.rsG3dMinZoomDrawn==="number" ? window.rsG3dMinZoomDrawn : MIN_ZOOM_DRAWN;
      return {above:r*Math.cos(rad(t)), range:r, tilt:t, ground:ground(c.lng, c.lat), sea:(m3 && m3.center && m3.center.altitude || 0)+r*Math.cos(rad(t)),
              drawn, limit:drawn ? "zoom above "+minZoom : "camera under "+minAlt+" m", low:drawn ? map.getZoom()>minZoom : r*Math.cos(rad(t))<minAlt}; };
    const lowCam=()=>{ const c=window.rsG3dCamera(), text=c.drawn ? NOTE_DRAWN : NOTE; note.hidden=w.hidden || !c.low;
      if(note.textContent!==text){ note.textContent=text; note.title=text; } };
    map.on("move", lowCam); map.on("zoom", lowCam); new MutationObserver(lowCam).observe(w, {attributes:true, attributeFilter:["hidden"]});
    setInterval(()=>{ if(!w.hidden) lowCam(); }, 400);       // Google changes its own range without a map move
    const toGoogle=()=>{ const c=map.getCenter();
      return {center:{lat:c.lat, lng:c.lng, altitude:ground(c.lng, c.lat)}, heading:(map.getBearing()+360)%360, tilt:map.getPitch(),
              range:rangeOf(c.lat, map.getZoom())}; };
    // GOOGLE'S TARGET IS ON ITS MESH, not on the ground: while a user drags in the 3D view, m3.center (and its altitude) hops between roofs,
    // trees and the street, 0 to 40 m from frame to frame, and the range is measured from it. So the map's camera is not read from the target:
    // the camera's position is (target minus the range along the view direction), the ray from it along the view direction meets the ground
    // (the DEM) at the map's centre, and the zoom comes from the camera's distance to that ground point.
    const KM=111320;
    const toMap=()=>{ const c=m3.center, h=rad(m3.heading||0), t=rad(m3.tilt||0), r=m3.range, plain=()=>({center:[c.lng, c.lat], bearing:m3.heading||0, pitch:m3.tilt||0, zoom:zoomOf(c.lat, r)});
      if(typeof c.altitude!=="number" || Math.cos(t)<0.05) return plain();                // no altitude, or a view near the horizon: the plain target
      const kx=KM*Math.cos(rad(c.lat)), dx=Math.sin(t)*Math.sin(h), dy=Math.sin(t)*Math.cos(h);       // the view's horizontal step per metre of range
      const cam={lng:c.lng-r*dx/kx, lat:c.lat-r*dy/KM, alt:c.altitude+r*Math.cos(t)};
      let hit={lng:c.lng, lat:c.lat}, s=r;
      for(let i=0; i<24; i++){ const g=ground(hit.lng, hit.lat); if(cam.alt-g<=1) return plain();       // a fixed point: the ground under the hit
        s=(cam.alt-g)/Math.cos(t); const n={lng:cam.lng+s*dx/kx, lat:cam.lat+s*dy/KM}, d=Math.hypot((n.lng-hit.lng)*kx, (n.lat-hit.lat)*KM); hit=n; if(d<0.02) break; }
      return {center:[hit.lng, hit.lat], bearing:m3.heading||0, pitch:m3.tilt||0, zoom:zoomOf(hit.lat, s)}; };
    const turn=(a, b)=>Math.abs(((a-b)%360+540)%360-180);
    // the map is at t, to the eye: the centre within 0.05 m on the ground, the zoom within 0.01, the bearing and the pitch within 0.1 degree.
    // Returns the name of the first thing that differs, or "" (the centre's altitude is not checked).
    const miss=t=>{ const c=map.getCenter(), k=111320;
      if(Math.hypot((c.lat-t.center[1])*k, (c.lng-t.center[0])*k*Math.cos(rad(c.lat)))>0.05) return "centre";
      if(turn(map.getBearing(), t.bearing)>=0.1) return "bearing";
      if(Math.abs(map.getPitch()-t.pitch)>=0.1) return "pitch";
      if(Math.abs(map.getZoom()-t.zoom)>=0.01) return "zoom"; return ""; };
    const there=t=>!miss(t);
    // TAGGED MOVES, NO GESTURE DETECTION (Google's element keeps its pointer events inside its own canvas, and its inertia goes on after the
    // pointer is up). Each camera is moved by the page in one place, and the echo is dropped where it comes back:
    //  - the 3D camera moves the map with map.jumpTo(cam, {rsSync:true}); the map's "move" handler ignores a move with rsSync, so it is not sent back;
    //  - the map moves the 3D camera with setGoogle(), which keeps the values it set for a second; a camera-change of Google within a small
    //    tolerance of one of them (1e-7 degrees, 0.5 m, 0.2 degrees) is the echo of that set, and is ignored.
    // Each direction runs at most once per frame. window.rsG3dCount counts both (the debug line shows them per second).
    const COUNT=window.rsG3dCount={g2m:0, m2g:0, back:0, lastMiss:""}, sets=[];
    let lastGoogle=-1e9, ignoreUntil=0, rec=0;       // lastGoogle: the last camera change of Google that was not an echo
    const setGoogle=()=>{ if(!m3) return; const g=toGoogle(), now=performance.now(); Object.assign(m3, g); COUNT.m2g++;
      sets.push({t:now, lat:g.center.lat, lng:g.center.lng, range:g.range, heading:g.heading, tilt:g.tilt});
      while(sets.length && now-sets[0].t>1000) sets.shift(); };
    const echo=()=>{ const c=m3.center||{}, h=m3.heading||0, t=m3.tilt||0, r=m3.range;
      return sets.some(x=>Math.abs(c.lat-x.lat)<1e-7 && Math.abs(c.lng-x.lng)<1e-7 && Math.abs(r-x.range)<0.5 && turn(h, x.heading)<0.2 && Math.abs(t-x.tilt)<0.2); };
    let toGQueued=false, smooth=null, rawLast=null, settleT=0;
    map.on("move", e=>{                          // the map moved (mouse, keys, buttons): Google follows, once a frame
      if(!m3 || e.rsSync || e.rsG3d || toGQueued) return; toGQueued=true;
      requestAnimationFrame(()=>{ toGQueued=false; if(performance.now()-lastGoogle>=300) setGoogle(); }); });   // while Google leads, the map's own moves are not sent
    // WHILE GOOGLE LEADS, NOTHING GOES BACK. The map follows as far as it can (its limits: maxPitch, maxZoom, maxBounds). When Google has been
    // still for 300 ms, a map that could not follow is reconciled once: Google flies to the map's camera in 250 ms.
    const reconcile=()=>{ rec=0; if(!m3 || performance.now()-lastGoogle<300 || leave()) return;
      const t=toMap(), g=toGoogle(); if(!(m3.center && m3.range) || there(t)) return;
      ignoreUntil=performance.now()+450; COUNT.m2g++;
      try{ m3.flyCameraTo({endCamera:g, durationMillis:250}); }catch(e){ Object.assign(m3, g); }
      sets.push({t:performance.now(), lat:g.center.lat, lng:g.center.lng, range:g.range, heading:g.heading, tilt:g.tilt}); };
    // THE MAP FOLLOWS GOOGLE ONLY WHILE THE REVIEWER MOVES IT: from a pointerdown, a wheel, a touchstart or a keydown on the window (captured: these
    // events are composed and cross Google's shadow root) until 1.5 s after the last pointerup or wheel (Google's inertia). Any other camera change of
    // Google (a switch of the mode, its own limits, a tile load, a resize) is not followed: 300 ms after it Google is set back to the map's camera once
    // (at most twice in a row), and the change goes into window.rsJumpLog with the reason "not user".
    let userDown=false, userUntil=0, notUserT=0, resets=0;
    const userNow=()=>userDown || performance.now()<userUntil;
    const heard=(k, hold)=>()=>{ COUNT.input=(COUNT.input||0)+1; resets=0; if(k==="down") userDown=true; userUntil=Math.max(userUntil, performance.now()+(hold||0)); };
    for(const t of ["pointerdown"]) w.addEventListener(t, heard("down", 1500), true);
    for(const t of ["wheel", "touchstart", "keydown"]) w.addEventListener(t, heard("", 1500), true);
    for(const t of ["pointerup", "pointercancel", "touchend"]) window.addEventListener(t, ()=>{ if(userDown){ userDown=false; userUntil=performance.now()+1500; } }, true);
    const notUser=()=>{
      COUNT.ignored=(COUNT.ignored||0)+1;
      (window.rsJumpLog=window.rsJumpLog||[]).push({t:(performance.now()/1000).toFixed(1), reason:"not user", mode:String(m3.mode), range:Math.round(m3.range), tilt:Math.round(m3.tilt||0), heading:Math.round(m3.heading||0)});
      clearTimeout(notUserT);
      notUserT=setTimeout(()=>{ if(!m3 || userNow() || resets>=2 || leave()) return; resets++; setGoogle(); }, 300); };
    const fromGoogle=()=>{                       // Google moved: the map follows, once a frame
      if(queued) return; queued=true;
      requestAnimationFrame(()=>{ queued=false;
        if(!m3 || !m3.center || !m3.range || echo() || performance.now()<ignoreUntil) return;
        if(!userNow()) return notUser();
        const now=performance.now(), raw=toMap(), dt=now-lastGoogle; lastGoogle=now; rawLast=raw;
        // while Google leads, the centre and the zoom go through an exponential filter (100 ms); the first change after a rest goes straight
        let t=raw;
        if(smooth && dt<300){ const k=1-Math.exp(-dt/100);
          t={...raw, center:[smooth.center[0]+(raw.center[0]-smooth.center[0])*k, smooth.center[1]+(raw.center[1]-smooth.center[1])*k], zoom:smooth.zoom+(raw.zoom-smooth.zoom)*k}; }
        smooth=t; clearTimeout(settleT); settleT=setTimeout(()=>{ smooth=null; if(m3 && rawLast && !there(rawLast)) map.jumpTo(rawLast, {rsG3d:true, rsSync:true}); }, 120);
        if(there(t)) return;
        map.jumpTo(t, {rsG3d:true, rsSync:true}); COUNT.g2m++;
        const m=miss(t); if(m){ COUNT.back++; COUNT.lastMiss=m; }       // the map could not follow: judged back (the debug line counts it)
        clearTimeout(rec); rec=setTimeout(reconcile, 320); }); };
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
    const redraw=()=>{ if(m3 && line) line.forEach(x=>{ x.remove(); m3.appendChild(x); }); };      // the selected road is drawn again in the new mode
    // A change of mode makes Google draw again, and it may report a stale or reset camera: for 1 s after the page sets the mode (or Google's own toggle
    // does) its camera changes are ignored, and then Google is set to the map's camera once. The map's camera never moves for a switch.
    // WHO CHANGES THE VIEW AFTER A MODE CHANGE? 0.2 s, 1 s and 3 s after it, Google's range, tilt and centre altitude go into window.rsG3dLog with the number of
    // sets the page made (m2g), of Google's changes it did not follow (ignored) and of input (input) since the change. With ?g3d=leave the page sets nothing
    // in Google's drawn map (the first view of Google stays).
    const leave=()=>/[?&]g3d=leave/.test(location.search) && drawnMode();
    let probeAt=-1e9;
    const probe=why=>{ const now=performance.now(); if(now-probeAt<600) return; probeAt=now; const c0={m2g:COUNT.m2g, ign:COUNT.ignored||0, inp:COUNT.input||0};
      const mapz=map.getZoom();
      for(const d of [200, 1000, 3000]) setTimeout(()=>{ if(!m3) return; const c=m3.center||{};
        LOG.push("mode "+String(m3.mode)+" +"+d/1000+"s ("+why+"): range "+Math.round(m3.range)+" tilt "+Math.round(m3.tilt||0)+" alt "+Math.round(c.altitude||0)+" | page sets "+(COUNT.m2g-c0.m2g)+", not followed "+((COUNT.ignored||0)-c0.ign)+", input "+((COUNT.input||0)-c0.inp)+" | map zoom "+mapz.toFixed(2)+", set range "+Math.round(rangeOf(map.getCenter().lat, mapz)));
        if(LOG.length>24) LOG.shift(); }, d); };
    window.rsG3dProbe=probe;
    const modeQuiet=()=>{ probe("mode change"); ignoreUntil=performance.now()+1000; clearTimeout(modeT); modeT=setTimeout(()=>{ if(m3 && !leave()) setGoogle(); }, 1050); };
    let modeT=0, lastMode=null;
    // Google's own toggle changes the mode without the page: a watcher (every 200 ms) opens the same quiet second, and keeps the choice
    setInterval(()=>{ if(!m3){ lastMode=null; return; } const v=String(m3.mode);
      if(lastMode!==null && v!==lastMode){ modeQuiet(); keepMode(); redraw(); } lastMode=v; }, 200);
    document.addEventListener("rs:labelschange", ()=>{ if(m3 && lib){ modeQuiet(); m3.mode=modeOf(lib); keepMode(); } });
    const open=()=>{
      if(location.protocol==="file:"){
        say("<b>Google 3D needs this page served, not opened from disk.</b>"+
            "<span>Run <code>python -m http.server</code> in its folder and open it from an address in the key's Websites list.</span>"+SETUP);
        return; }
      msg.textContent="Loading Google 3D…"; msg.hidden=false;
      _gmLoad(_svKey).then(()=>google.maps.importLibrary("maps3d")).then(l=>{
        if(w.hidden || m3) return;               // closed while it loaded
        lib=l; m3=new l.Map3DElement(Object.assign(toGoogle(), {mode:(k=>k && !/^(HYBRID|SATELLITE)$/i.test(k) ? k : modeOf(l))(keptMode())}));
        m3.addEventListener("gmp-modechange", ()=>{ modeQuiet(); keepMode(); redraw(); });
        for(const ev of ["gmp-centerchange", "gmp-headingchange", "gmp-tiltchange", "gmp-rangechange"]) m3.addEventListener(ev, fromGoogle);
        m3.addEventListener("gmp-error", e=>{ LOG.push("gmp-error: "+((e && (e.message || (e.detail && e.detail.message))) || "")); say("<b>Google 3D imagery did not load.</b><span>Google reported an error; the window does not show another style.</span>"); });
        msg.hidden=true; w.appendChild(m3);
        if(want) setTimeout(()=>{ if(m3) tryDraw(want.cs, want.name, want.lvl, false); }, 0);
      }).catch(e=>{ console.warn("rs google 3d:", e); say("<b>Google 3D did not load.</b><span>"+String(e.message||e)+"</span>"+SETUP); });
    };
    // DRAW A ROAD in the 3D view and fly along it. cs: the road's [lng, lat] points; lvl: its level. rs:select calls it for a click on a road;
    // a page with its own selection (a stepper, a list) calls window.rsG3dDraw(cs, name, lvl). A road asked for before the view exists is drawn when it opens.
    let want=null;
    const draw=(any, name, lvl, fly)=>{
      const parts=(Array.isArray(any[0]) && Array.isArray(any[0][0]) ? any : [any]).filter(c=>c.length>1);     // one line, or several
      want={cs:any, name, lvl};
      if(!m3 || !lib || !parts.length) return;
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
      if(!fly) return;                        // a page with its own selection moves the map, and the 3D camera follows the map
      userUntil=performance.now()+1700;       // this flight is the page's own: the map follows it
      const cs=parts.reduce((a, c)=>_svDist(c).slice(-1)[0]>_svDist(a).slice(-1)[0] ? c : a), len=_svDist(cs).slice(-1)[0], mid=_svAt({geometry:{type:"LineString", coordinates:cs}}, len/2);
      m3.flyCameraTo({endCamera:{center:{lat:mid.lat, lng:mid.lng, altitude:ground(mid.lng, mid.lat)}, heading:mid.h, tilt:62, range:Math.max(180, len*1.6)},
                      durationMillis:1500});
    };
    const tryDraw=(cs, name, lvl, fly)=>{ try{ draw(cs, name, lvl, fly); }catch(e){ LOG.push("draw: "+String(e&&e.message||e).slice(0, 140)); console.warn("rs google 3d: the road was not drawn:", e); } };
    window.rsG3dDraw=tryDraw;
    document.addEventListener("rs:select", e=>{  // a road: draw it in the 3D view and fly along it
      const d=e.detail; if(d.overlay) return;
      if(typeof window.rsG3dOwnDraw==="function" && window.rsG3dOwnDraw(d)) return;       // the page draws this road itself, from its own data
      const r=_road(d.id), cs=r ? _svLine(r) : []; if(cs.length<2) return;
      const p=d.properties||{}; tryDraw(cs, p.name||p.highway, (_rprops(d.id)||{}).lvl||0, true);
    });
    rsSetGoogle3D=function(on){
      w.hidden=!on;
      if(on){ if(innerWidth>520) place(); if(!m3) open(); }
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

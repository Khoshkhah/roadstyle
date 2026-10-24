// GOOGLE 3D window (google_3d=True, with a key): Google's photorealistic 3D view in a floating window,
// opened by its map button (or rsSetGoogle3D(true)). Its camera and the map's are linked both ways:
// center = center, bearing = heading, pitch = tilt, and zoom <-> range (the metres from Google's camera
// to its center: the map's own camera distance at that zoom). A clicked road is drawn in the 3D view
// and the camera flies along it (the map follows). Google's 3D map exists only while the window is
// open: closing it drops it, as nothing is loaded from Google while it is closed.
import {map, O, _road} from "./core.js";
import {_gmLoad, _rsFloat} from "./float.js";
import {_svKey} from "./streetview.js";
import {_svLine, _svDist, _svAt} from "./svspot.js";
export function rsSetGoogle3D(){}
export function initGoogle3D(){
  if(O.google_3d){
    const w=document.createElement("div"); w.className="rs-svw rs-g3d"; w.hidden=true;
    w.innerHTML='<div class="rs-svw-bar"><span class="rs-svw-t">Google 3D</span>'+
      '<span class="rs-g3d-warn" hidden title="The ground heights did not load: on a hill, the 3D view can be closer than the map">\u26a0 no ground heights</span>'+
      '<a class="rs-g3d-src" href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noopener"'+
      ' title="Ground heights: Terrain Tiles on AWS (Mapzen; SRTM and other sources)">heights: Mapzen</a>'+
      '<button type="button" title="Close">✕</button></div><div class="rs-svw-msg"></div>';
    document.body.appendChild(w);
    const bar=w.firstChild, ttl=w.querySelector(".rs-svw-t"), msg=w.querySelector(".rs-svw-msg");
    const {st, save, place}=_rsFloat(w, bar, "rs-google-3d-window", true);
    let m3=null, lib=null, line=null, btn=null, lastMap=0, queued=false;
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
          t.px=g.getImageData(0, 0, 256, 256).data; if(m3) Object.assign(m3, toGoogle()); };
        img.onerror=()=>{ warn.hidden=false; console.warn("rs google 3d: no ground heights from", img.src); };
        img.src="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"+key+".png"; }
      if(!t.px) return lastGround;
      const i=(Math.min(255, Math.floor(x%1*256))+Math.min(255, Math.floor(y%1*256))*256)*4;
      return lastGround=Math.max(0, t.px[i]*256+t.px[i+1]+t.px[i+2]/256-32768); };
    const toGoogle=()=>{ const c=map.getCenter();
      return {center:{lat:c.lat, lng:c.lng, altitude:ground(c.lng, c.lat)}, heading:(map.getBearing()+360)%360, tilt:map.getPitch(),
              range:camPx()*EARTH*Math.cos(rad(c.lat))/(512*Math.pow(2, map.getZoom()))}; };
    const toMap=()=>{ const c=m3.center;
      return {center:[c.lng, c.lat], bearing:m3.heading||0, pitch:m3.tilt||0,
              zoom:Math.log2(EARTH*Math.cos(rad(c.lat))*camPx()/(512*m3.range))}; };
    const turn=(a, b)=>Math.abs(((a-b)%360+540)%360-180);
    const there=t=>{ const c=map.getCenter();     // the map is already at t: Google's change came from the map
      return Math.abs(c.lng-t.center[0])<1e-7 && Math.abs(c.lat-t.center[1])<1e-7 && turn(map.getBearing(), t.bearing)<0.05 &&
             Math.abs(map.getPitch()-t.pitch)<0.05 && Math.abs(map.getZoom()-t.zoom)<0.002; };
    map.on("move", e=>{                          // the map moved (mouse, keys, buttons): Google follows
      if(!m3 || e.rsG3d) return;
      lastMap=performance.now(); Object.assign(m3, toGoogle()); });
    const fromGoogle=()=>{                       // Google moved: the map follows, once a frame
      if(queued) return; queued=true;
      requestAnimationFrame(()=>{ queued=false;
        // Google's late reports of a map move would pull the map back while it is dragged
        if(!m3 || !m3.center || !m3.range || performance.now()-lastMap<300) return;
        const t=toMap(); if(there(t)) return;
        map.jumpTo(t, {rsG3d:true});
        // THE MAP IS THE JUDGE: where it cannot follow (its maxBounds box, its maximum pitch) it stops at
        // its limit, and Google goes back to the map's camera. Google's own bounds limit the position of
        // its camera, not the point it looks at: a tilted, far camera left the box and moved the view.
        if(!there(t)) Object.assign(m3, toGoogle()); }); };
    // THE MAP'S CENTER BESIDE THE WINDOW: while the window is open, the map's padding puts its center (the
    // point the two cameras share, where a clicked road comes to) in the middle of the map's free side, so
    // the window does not cover it. Phones keep the plain center: there the window docks at the bottom.
    const pad=()=>{
      const m=map.getContainer().getBoundingClientRect(), r=w.getBoundingClientRect(), p={...map.getPadding(), left:0, right:0};
      if(!w.hidden && innerWidth>520){
        if(r.left+r.width/2 < m.left+m.width/2) p.left=Math.max(0, r.right-m.left);
        else p.right=Math.max(0, m.right-r.left); }
      const o=map.getPadding();
      if(Math.abs(o.left-p.left)>1 || Math.abs(o.right-p.right)>1) map.easeTo({padding:p, duration:300});
    };
    new ResizeObserver(pad).observe(w);          // opened, closed or resized
    bar.addEventListener("pointerup", pad);      // dragged
    map.on("resize", pad);
    const open=()=>{
      if(location.protocol==="file:"){
        say("<b>Google 3D needs this page served, not opened from disk.</b>"+
            "<span>Run <code>python -m http.server</code> in its folder and open it from an address in the key's Websites list.</span>"+SETUP);
        return; }
      msg.textContent="Loading Google 3D…"; msg.hidden=false;
      _gmLoad(_svKey).then(()=>google.maps.importLibrary("maps3d")).then(l=>{
        if(w.hidden || m3) return;               // closed while it loaded
        lib=l; m3=new l.Map3DElement(Object.assign(toGoogle(), {mode:l.MapMode.HYBRID}));
        for(const ev of ["gmp-centerchange", "gmp-headingchange", "gmp-tiltchange", "gmp-rangechange"]) m3.addEventListener(ev, fromGoogle);
        msg.hidden=true; w.appendChild(m3);
      }).catch(e=>{ console.warn("rs google 3d:", e); say("<b>Google 3D did not load.</b><span>"+String(e.message||e)+"</span>"+SETUP); });
    };
    document.addEventListener("rs:select", e=>{  // a road: draw it in the 3D view and fly along it
      const d=e.detail; if(d.overlay || !m3) return;
      const cs=_svLine(_road(d.id)); if(cs.length<2) return;
      const p=d.properties||{}; ttl.textContent=p.name||p.highway||"Unnamed road";
      if(line) line.remove();
      line=new lib.Polyline3DElement({path:cs.map(c=>({lat:c[1], lng:c[0]})), strokeColor:O.select_color, strokeWidth:8,
                                      outerColor:"#ffffff", outerWidth:0.3, drawsOccludedSegments:true});
      m3.appendChild(line);
      const dist=_svDist(cs), len=dist[dist.length-1], mid=_svAt({geometry:{type:"LineString", coordinates:cs}}, len/2);
      m3.flyCameraTo({endCamera:{center:{lat:mid.lat, lng:mid.lng, altitude:ground(mid.lng, mid.lat)}, heading:mid.h, tilt:62, range:Math.max(180, len*1.6)},
                      durationMillis:1500});
    });
    rsSetGoogle3D=function(on){
      w.hidden=!on;
      if(on){ if(innerWidth>520) place(); if(!m3) open(); }
      else { if(m3){ m3.remove(); m3=null; line=null; } ttl.textContent="Google 3D"; }
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
    if(st.open) map.once("load", ()=>rsSetGoogle3D(true));
  }
  window.rsSetGoogle3D = rsSetGoogle3D;
}

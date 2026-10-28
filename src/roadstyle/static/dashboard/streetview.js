// Street View window (street_view="window"): hidden until the map button (or
// rsSetStreetView(true)) opens it; then a draggable, resizable window over the map that follows
// every road selection. Nothing is loaded from Google while it is closed. Whether it is open, its
// position and its size are remembered in this browser.
import {map, O} from "./core.js";
import {_gmLoad, _rsFloat} from "./float.js";
import {rsSetStreetViewMarkerAt, rsSetStreetViewMarker, rsStreetViewStep} from "./svspot.js";
export let _svWindow = false;
// with a Maps JavaScript API key (street_view_key=) the window offers Linked - a real panorama that
// reports every step and turn, so the map marker walks with the viewer - beside Classic, the embed
export let _svKey = "";
export function rsSetStreetView(){}
export function initStreetView(){
  _svWindow = O.street_view==="window"; _svKey = O.street_view_key || "";
  if(_svWindow){
    const fromDisk=location.protocol==="file:";
    const w=document.createElement("div"); w.className="rs-svw"; w.hidden=true;
    w.innerHTML='<div class="rs-svw-bar"><span class="rs-svw-t">Street View</span>'+
      '<span class="rs-svw-mode" hidden><button type="button" data-m="linked" title="The map marker walks and turns with you; Google\'s street photos only">Linked</button>'+
      '<button type="button" data-m="classic" title="Google\'s plain Street View: the marker stays where you clicked">Classic</button></span>'+
      '<button type="button" data-step="-15" title="Back 15 m along the road">\u25c0</button>'+
      '<button type="button" data-step="15" title="Forward 15 m along the road">\u25b6</button>'+
      '<button type="button" title="Close">\u2715</button></div>'+
      '<div class="rs-svw-msg">Click a road to see it in Street View.</div>'+
      '<iframe title="Google Street View" allowfullscreen hidden></iframe><div class="rs-svw-pano" hidden></div>';
    document.body.appendChild(w);
    const bar=w.firstChild, ttl=w.querySelector(".rs-svw-t"), msg=w.querySelector(".rs-svw-msg"),
          fr=w.querySelector("iframe"), pdiv=w.querySelector(".rs-svw-pano"), flip=w.querySelector(".rs-svw-mode");
    const {st, save, place}=_rsFloat(w, bar, "rs-street-view-window", false);
    // Linked or Classic, remembered in this browser (the same choice as the Street View page's)
    const MODE_KEY="rs-street-view-mode";
    let mode="classic", pano=null, svc=null;
    if(_svKey){ mode="linked"; try{ mode=localStorage.getItem(MODE_KEY)||"linked"; }catch(e){}
      flip.hidden=false;
      const mark=()=>flip.querySelectorAll("button").forEach(b=>b.classList.toggle("on", b.dataset.m===mode));
      mark();
      flip.querySelectorAll("button").forEach(b=>b.onclick=()=>{
        if(b.dataset.m===mode) return;
        mode=b.dataset.m; mark(); try{ localStorage.setItem(MODE_KEY, mode); }catch(e){}
        if(mode==="classic"){ hideP(); rsSetStreetViewMarkerAt(null); }
        // the same spot in the other panel: where the viewer has walked to, where the marker stands
        if(!rsStreetViewStep(0)) show();
      }); }
    const gload=()=>_gmLoad(_svKey);
    // THE PANORAMA EXISTS ONLY WHILE IT IS ON SCREEN. One that sat hidden - Classic showing, or the
    // window closed - came back black with a single tile in a corner, and showing it again first did
    // not cure that in a real browser. So hiding it drops it, and the next Linked view builds a new one
    // inside a box that is already visible: every return is a first load, and a first load works.
    const hideP=()=>{ pdiv.hidden=true;
      if(pano){ google.maps.event.clearInstanceListeners(pano); pano.setVisible(false); pano=null; pdiv.textContent=""; } };
    const panoAt=(lat, lng, h)=>gload().then(()=>{
      const g=google.maps; svc=svc || new g.StreetViewService();
      return svc.getPanorama({location:{lat:+lat, lng:+lng}, radius:50, preference:g.StreetViewPreference.NEAREST,
                              sources:[g.StreetViewSource.GOOGLE]}).then(r=>{
        if(mode!=="linked" || w.hidden) return;   // flipped to Classic or closed while it was asked for
        const id=r.data.location.pano, pov={heading:+h||0, pitch:0};
        fr.hidden=true; msg.hidden=true; pdiv.hidden=false;
        if(pano){ pano.setPano(id); pano.setPov(pov); return; }
        pano=new g.StreetViewPanorama(pdiv, {pano:id, pov:pov, visible:true,
                                             motionTracking:false, addressControl:false, fullscreenControl:true});
        const report=()=>{ const p=pano && pano.getPosition(); if(p) rsSetStreetViewMarkerAt(p.lng(), p.lat(), pano.getPov().heading); };
        pano.addListener("position_changed", report); pano.addListener("pov_changed", report); },
        ()=>{ hideP(); msg.hidden=false; msg.textContent="No street photos within 50 m of this spot."; }); });
    let last=null, btn=null;                   // the latest road selection: {name, url}
    const esc=t=>String(t).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);
    const show=()=>{
      if(w.hidden || !last) return;
      ttl.textContent=last.name;
      if(!last.url || fromDisk){               // Google's embed stays grey in a file:// page
        fr.hidden=true; hideP(); msg.hidden=false;
        msg.innerHTML = !last.url ? "No Street View for this road." :
          "<b>Street View needs this page served, not opened from disk.</b>"+
          "<span>Run <code>python -m http.server</code> in its folder and open it from localhost.</span>"+
          '<a href="'+esc(last.url)+'" target="_blank" rel="noopener">Open this spot in Google Maps \u2197</a>';
        return; }
      // Google won't frame last.url; this is its embeddable twin (Google's "Share > Embed a map" form)
      const u=new URL(last.url), vp=u.searchParams.get("viewpoint").split(",");
      const src="https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d"+vp[0]+"!2d"+vp[1]+
                "!3f"+(u.searchParams.get("heading")||0)+"!4f0!5f1";
      const embed=()=>{ if(fr.getAttribute("src")!==src) fr.src=src; fr.hidden=false; msg.hidden=true; hideP(); };
      if(_svKey && mode==="linked"){ fr.hidden=true; panoAt(vp[0], vp[1], u.searchParams.get("heading")||0).catch(e=>{ console.warn("rs street view:", e); embed(); }); return; }
      embed();
    };
    const steps=[...bar.querySelectorAll("button[data-step]")];
    const ends=(a, z)=>{ steps[0].disabled=!!a; steps[1].disabled=!!z; };
    steps.forEach(b=>{ b.onclick=()=>rsStreetViewStep(+b.dataset.step); });
    document.addEventListener("rs:select", e=>{
      const d=e.detail; if(d.overlay) return;  // roads only
      const p=d.properties||{}; last={name:p.name||p.highway||"Unnamed road", url:d.streetView};
      ends(false, false); show();
    });
    document.addEventListener("rs:streetviewmove", e=>{   // the step buttons: same road, new spot
      if(!last) return; last.url=e.detail.streetView; ends(e.detail.atStart, e.detail.atEnd); show();
    });
    rsSetStreetView=function(on){
      if(!on){ hideP();                          // closed: drop the panorama (see hideP)
        // and forget the road: opened again it waits for a road, not the last one (Kaveh, 2026-10-14)
        last=null; fr.hidden=true; msg.hidden=false; msg.textContent="Click a road to see it in Street View."; ttl.textContent="Street View"; }
      w.hidden=!on; if(on && innerWidth>520) place(); rsSetStreetViewMarker(!!on);
      st.open=!!on; save(); if(btn) btn.classList.toggle("rs-on", !!on); show();
      document.dispatchEvent(new CustomEvent("rs:streetviewchange", {detail:{open:!!on}}));
    };
    bar.lastChild.onclick=()=>rsSetStreetView(false);
    map.addControl({onAdd(){
      const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
      btn=document.createElement("button"); btn.type="button"; btn.title="Street View";
      btn.innerHTML='<svg viewBox="0 0 24 24" width="17" height="17" style="display:block;margin:auto">'+
        '<circle cx="12" cy="4.5" r="3" fill="currentColor"/>'+
        '<path d="M8.5 9h7l-1.2 7h-1.8l-.6 6.5h-1.8L9.5 16H7.7z" fill="currentColor"/></svg>';
      btn.onclick=()=>rsSetStreetView(w.hidden);
      d.appendChild(btn); return d;
    }, onRemove(){}});
    // reopen a window left open last time only once the map is up: this code runs before the Street View
    // spot (svspot.js) is set up, and throwing here stopped the page before any road was drawn
    if(st.open) map.once("load", ()=>{ if(window.rsRestoreWindows!==false) rsSetStreetView(true); });      // a page can start with its windows closed: window.rsRestoreWindows=false
  }
  window.rsSetStreetView = rsSetStreetView;
}

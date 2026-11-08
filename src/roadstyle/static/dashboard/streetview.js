// Street View window (street_view="window"): hidden until the map button (or
// rsSetStreetView(true)) opens it; then a draggable, resizable window over the map that follows
// every road selection. Nothing is loaded from Google while it is closed. Whether it is open, its
// position and its size are remembered in this browser.
import {_esc} from "../popup.js";
import {map, O, _emit} from "./core.js";
import {_gmLoad, _rsFloat} from "./float.js";
import {defineTool, STREETVIEW_ICON} from "./tools.js";
import {savedKey} from "./settings.js";
import {SV_PROVIDERS, _spFind, _spCoverage, _spNeedsToken, _spPrefetch, _spOnDot, _spMark} from "./svproviders.js";
import {_wPhone} from "./windows.js";
import {rsSetStreetViewMarkerAt, rsSetStreetViewMarker, rsStreetViewStep, rsStreetViewLine} from "./svspot.js";
const SV_COV_ICON='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/></svg>';   // a folded map
export let _svWindow = false;
// with a Maps JavaScript API key (street_view_key=) the window offers Linked - a real panorama that
// reports every step and turn, so the map marker walks with the viewer - beside Classic, the embed
export let _svKey = "";
export function rsSetStreetView(){}
// street_view="dock": the window is a side of the page, not a floating window. It takes the right part of the screen (on a phone, the lower part) with a divider
// that the person drags, and the map takes the rest. The share is remembered per page in this browser.
function _svDock(w){
  const KEY="rs-street-view-dock:"+location.pathname, root=document.documentElement;
  const st=(()=>{ try{ return JSON.parse(localStorage.getItem(KEY))||{}; }catch(e){ return {}; } })();
  const save=()=>{ try{ localStorage.setItem(KEY, JSON.stringify(st)); }catch(e){} };
  const drag=document.createElement("div"); drag.className="rs-svw-drag"; drag.title="Drag to resize"; drag.hidden=true; document.body.appendChild(drag);
  const share=p=>{ st.pct=Math.max(20, Math.min(80, p)); root.style.setProperty("--rs-sv-w", st.pct+"%"); };
  const place=()=>{ root.classList.add("rs-sv-docked"); share(st.pct||42); drag.hidden=_wPhone(); map.resize(); };
  w.__rsUnplace=()=>{ root.classList.remove("rs-sv-docked"); drag.hidden=true; map.resize(); };
  drag.addEventListener("pointerdown", e=>{
    drag.setPointerCapture(e.pointerId); w.classList.add("rs-dragging");      // the frame must not swallow the pointer (not `rs-drag`: windows.js moves a window with that class)
    const mv=ev=>{ share(100*(innerWidth-ev.clientX)/innerWidth); map.resize(); };
    drag.addEventListener("pointermove", mv);
    drag.addEventListener("pointerup", ()=>{ drag.removeEventListener("pointermove", mv); w.classList.remove("rs-dragging"); save(); }, {once:true});
  });
  return {st, save, place};
}
export function initStreetView(){
  const dock=O.street_view==="dock";
  _svWindow = O.street_view==="window" || dock; _svKey = savedKey("google") || O.street_view_key || "";           // the key that the person saved (settings) is over the page's
  if(_svWindow){
    const fromDisk=location.protocol==="file:";
    const w=document.createElement("div"); w.className="rs-svw"+(dock?" rs-svw-dock":""); w.hidden=true;
    w.innerHTML='<div class="rs-svw-bar"><span class="rs-svw-t">Street View</span>'+
      '<span class="rs-svw-prov"></span>'+
      // the coverage of the provider that is open: an icon button right after the switch (a text button made the bar wrap in a 380 px window)
      '<button type="button" class="rs-svw-cov" title="Coverage on the map: where this provider has photos" aria-label="Coverage on the map" hidden>'+SV_COV_ICON+'</button>'+
      '<span class="rs-svw-mode" hidden><button type="button" data-m="linked" title="The map marker walks and turns with you; Google\'s street photos only">Linked</button>'+
      '<button type="button" data-m="classic" title="Google\'s plain Street View: the marker stays where you clicked">Classic</button></span>'+
      '<span class="rs-svw-step"><button type="button" data-step="-15" title="Back 15 m along the road">\u25c0</button>'+
      '<button type="button" data-step="15" title="Forward 15 m along the road">\u25b6</button></span>'+
      '<button type="button" class="rs-svw-x" title="Close">\u2715</button></div>'+
      '<div class="rs-svw-msg">Click a road to see it in Street View.</div>'+
      '<iframe title="Google Street View" allowfullscreen hidden></iframe><div class="rs-svw-pano" hidden></div><div class="rs-svw-alt" hidden></div>';
    document.body.appendChild(w);
    const bar=w.firstChild, ttl=w.querySelector(".rs-svw-t"), msg=w.querySelector(".rs-svw-msg"),
          fr=w.querySelector("iframe"), pdiv=w.querySelector(".rs-svw-pano"), adiv=w.querySelector(".rs-svw-alt"), flip=w.querySelector(".rs-svw-mode"),
          provBox=w.querySelector(".rs-svw-prov"), covBtn=w.querySelector(".rs-svw-cov");
    const {st, save, place}=dock ? _svDock(w) : _rsFloat(w, bar, "rs-street-view-window", false);
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
        pano.addListener("position_changed", report); pano.addListener("pov_changed", report);
        // a panorama does not see its box change size (the docked window, dragged by its divider): it is told
        if(dock){ const p0=pano; new ResizeObserver(()=>{ if(pano===p0) g.event.trigger(p0, "resize"); }).observe(pdiv); } },
        ()=>{ hideP(); msg.hidden=false; msg.textContent="No street photos within 50 m of this spot."; }); });
    // THE PROVIDER: Google (above), or Panoramax / Mapillary: the nearest photo to the spot in their own viewer (svproviders.js).
    // The choice and the coverage switch are remembered in this browser.
    const PROV_KEY="rs-street-view-provider", COV_KEY="rs-street-view-cov";
    let prov="google", cov=false, altTok=0, alt=null;   // alt: the open viewer {prov, ctl}
    try{ prov=localStorage.getItem(PROV_KEY)||"google"; cov=localStorage.getItem(COV_KEY)==="1"; }catch(e){}
    if(!SV_PROVIDERS[prov]) prov="google";
    const chrome=()=>{                          // what the bar offers for the provider that is chosen
      provBox.querySelectorAll("button").forEach(b=>b.classList.toggle("on", b.dataset.p===prov));
      flip.hidden = !_svKey || prov!=="google";
      covBtn.hidden = prov==="google"; covBtn.style.color=""; covBtn.title="Coverage on the map: where this provider has photos"; covBtn.classList.toggle("on", cov);
      fr.title = SV_PROVIDERS[prov].title+" Street View"; w.dataset.prov=prov; };
    const drawCov=()=>_spCoverage(!w.hidden && cov ? prov : null, e=>{ covBtn.style.color="#e03131"; covBtn.title="The coverage tiles did not load: "+((e&&e.message)||"check the token in Settings \u2192 Keys"); });
    for(const k in SV_PROVIDERS){
      const b=document.createElement("button"); b.type="button"; b.dataset.p=k; b.textContent=SV_PROVIDERS[k].title;
      b.onclick=()=>{ if(k===prov) return; prov=k; try{ localStorage.setItem(PROV_KEY, k); }catch(e){}
        hideP(); altTok++; dropAlt(); _spMark(null); exact=false; ahead=false; rsSetStreetViewMarkerAt(null); chrome(); drawCov(); if(!rsStreetViewStep(0)) show(); };
      provBox.appendChild(b); }
    covBtn.onclick=()=>{ if(_spNeedsToken(prov)){ altTok++; dropAlt(); return note(NEED_TOKEN); }
      cov=!cov; try{ localStorage.setItem(COV_KEY, cov?"1":"0"); }catch(e){} chrome(); drawCov(); };
    chrome();
    const NEED_TOKEN="<b>Mapillary needs a free token.</b>"+
      "<span>Make one at <a href=\"https://www.mapillary.com/developer\" target=\"_blank\" rel=\"noopener\">mapillary.com/developer</a> (a client token), then paste it in Settings \u2192 Keys (Save, then Reload). Coverage needs it too.</span>";
    const dropAlt=()=>{ if(alt){ alt.ctl.destroy(); alt=null; } adiv.hidden=true; };
    const note=(html, keep)=>{ fr.hidden=true; hideP(); if(!keep) dropAlt(); else adiv.hidden=true; msg.hidden=false; msg.innerHTML=html; };
    const failAt=(tok, e)=>{ if(tok===altTok) note("<b>"+_esc(SV_PROVIDERS[prov].title)+" is not reachable.</b><span>"+_esc(e.message||String(e))+"</span>"); };
    // r (a photo as _spFind answers) in the provider's viewer, looking h (null: the way the photo looks)
    const present=(r, h, tok)=>{
      const fail=e=>failAt(tok, e);
      const go=()=>{
        if(tok!==altTok || w.hidden) return;
        if(r && r.lng!=null) _spMark([r.lng, r.lat]);          // the ring shows which dot of the coverage this photo is (it can be on the other carriageway)
        fr.hidden=true; hideP(); msg.hidden=true; adiv.hidden=false;
        alt.ctl.go(r, h).catch(fail); };
      if(alt && alt.prov===prov) return go();
      dropAlt(); const mine=tok; adiv.hidden=false;
      _spOpen(prov, adiv, (lng, lat, hd)=>{ if(alt && alt.ctl===ctlRef) rsSetStreetViewMarkerAt(lng, lat, hd, exact); }).then(c=>{
        if(mine!==altTok || w.hidden){ c.destroy(); return; }
        ctlRef=c; alt={prov:prov, ctl:c}; go(); }, fail);
    };
    // a click on a photo's dot on the map: that photo, and the marker where it was taken, turned the way it looks
    _spOnDot((provider, photo)=>{
      if(w.hidden || provider!==prov) return;
      const tok=++altTok; exact=true; photo.then(r=>{ if(tok===altTok && !w.hidden) present(r, null, tok); }, e=>failAt(tok, e)); });
    const showAlt=()=>{                         // Panoramax / Mapillary for the spot of the last selection
      const P=SV_PROVIDERS[prov], tok=++altTok; _spMark(null); exact=false;
      if(!last.url) return note("No Street View for this road.");
      if(_spNeedsToken(prov)) return note(NEED_TOKEN);
      const u=new URL(last.url), vp=u.searchParams.get("viewpoint").split(","), h=+u.searchParams.get("heading")||0;
      if(!alt) note("Looking for photos\u2026");   // a viewer that is open stays on screen while the next photo is found
      if(!ahead){ ahead=true; _spPrefetch(prov, rsStreetViewLine(), +vp[0], +vp[1]); }   // the road's other photos, loaded in the background
      const fail=e=>failAt(tok, e);
      _spFind(prov, +vp[0], +vp[1], h).then(r=>{
        if(tok!==altTok || w.hidden) return;    // a newer spot, another provider, or the window closed meanwhile
        if(!r) return note("No "+P.title+" photos within 30 m of this spot looking along the road.");
        present(r, h, tok); }, fail);
    };
    let last=null, btn=null, ctlRef=null, ahead=false, exact=false;                   // the latest road selection: {name, url}
    const show=()=>{
      if(w.hidden || !last) return;
      ttl.textContent=last.name;
      if(prov!=="google") return showAlt();
      if(!last.url || fromDisk){               // Google's embed stays grey in a file:// page
        fr.hidden=true; hideP(); msg.hidden=false;
        msg.innerHTML = !last.url ? "No Street View for this road." :
          "<b>Street View needs this page served, not opened from disk.</b>"+
          "<span>Run <code>python -m http.server</code> in its folder and open it from localhost.</span>"+
          '<a href="'+_esc(last.url)+'" target="_blank" rel="noopener">Open this spot in Google Maps \u2197</a>';
        return; }
      // Google no longer serves a keyless embed (HTTP 404, x-frame-options SAMEORIGIN), so Classic is a link
      const u=new URL(last.url), vp=u.searchParams.get("viewpoint").split(",");
      const link=()=>note("<b>Google does not allow this page to show Classic Street View.</b>"+
        '<a href="'+_esc(last.url)+'" target="_blank" rel="noopener">Open this spot in Google Maps \u2197</a>');
      if(_svKey && mode==="linked"){ fr.hidden=true; panoAt(vp[0], vp[1], u.searchParams.get("heading")||0).catch(e=>{ console.warn("rs street view:", e); link(); }); return; }
      link();
    };
    const steps=[...bar.querySelectorAll("button[data-step]")];
    const ends=(a, z)=>{ steps[0].disabled=!!a; steps[1].disabled=!!z; };
    steps.forEach(b=>{ b.onclick=()=>rsStreetViewStep(+b.dataset.step); });
    document.addEventListener("rs:select", e=>{
      const d=e.detail; if(d.overlay) return;  // roads only
      const p=d.properties||{}; last={name:p.name||p.highway||"Unnamed road", url:d.streetView}; ahead=false;
      ends(false, false); show();
    });
    document.addEventListener("rs:streetviewmove", e=>{   // the step buttons: same road, new spot
      if(!last) return; last.url=e.detail.streetView; ends(e.detail.atStart, e.detail.atEnd); show();
    });
    rsSetStreetView=function(on){
      if(!on){ hideP(); altTok++; dropAlt();                          // closed: drop the panorama (see hideP)
        // and forget the road: opened again it waits for a road, not the last one (Kaveh, 2026-10-14)
        last=null; fr.hidden=true; msg.hidden=false; msg.textContent="Click a road to see it in Street View."; ttl.textContent="Street View"; }
      w.hidden=!on; if(on && (dock || !_wPhone())) place(); if(!on && dock) w.__rsUnplace(); rsSetStreetViewMarker(!!on); drawCov();
      st.open=!!on; save(); if(btn) btn.classList.toggle("rs-on", !!on); show();
      _emit("rs:streetviewchange", {open:!!on});
    };
    bar.lastChild.onclick=()=>rsSetStreetView(false);
    const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
    btn=document.createElement("button"); btn.type="button"; btn.title="Street View";
    btn.innerHTML=STREETVIEW_ICON;
    btn.onclick=()=>rsSetStreetView(w.hidden);
    d.appendChild(btn);
    defineTool("street_view", "window", d, {title: btn.title, open: ()=>rsSetStreetView(true), close: ()=>rsSetStreetView(false), isOpen: ()=>!w.hidden});
    // reopen a window left open last time only once the map is up: this code runs before the Street View
    // spot (svspot.js) is set up, and throwing here stopped the page before any road was drawn
    if(dock ? st.open!==false : st.open) map.once("load", ()=>{ if(!O.dashboard || O.dashboard.windows.restore_open) rsSetStreetView(true); });      // a template can start with its windows closed
  }
  window.rsSetStreetView = rsSetStreetView;
}

// Street View window (street_view="window"): hidden until the map button (or
// rsSetStreetView(true)) opens it; then a draggable, resizable window over the map that follows
// every road selection. Nothing is loaded from Google while it is closed. Whether it is open, its
// position and its size are remembered in this browser.
import {_esc} from "../popup.js";
import {map, O, _emit} from "./core.js";
import {_gmLoad, _rsFloat} from "./float.js";
import {defineTool, STREETVIEW_ICON} from "./tools.js";
import {savedKey} from "./settings.js";
import {SV_PROVIDERS, _spFind, _spOpen, _spCoverage, _spNeedsToken, _spPrefetch, _spOnDot, _spMark, _spAround, _spWarm, _spLoadAround, _spSnap} from "./svproviders.js";
import {_wPhone} from "./windows.js";
import {holdPopup} from "./select.js";
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
      '<span class="rs-svw-step"><button type="button" data-step="-15" title="Back 15 m along the road">\u25c0</button>'+
      '<button type="button" data-step="15" title="Forward 15 m along the road">\u25b6</button></span>'+
      '<button type="button" class="rs-svw-x" title="Close">\u2715</button></div>'+
      '<div class="rs-svw-msg">Click a road to see it in Street View.</div>'+
      '<iframe title="Google Street View" allowfullscreen credentialless hidden></iframe><div class="rs-svw-pano" hidden></div><div class="rs-svw-alt" hidden></div><div class="rs-svw-aside" hidden></div>'+
      // Panoramax has no arrows in its picture: these are made over a Panoramax photo, one for each photo near it (dashboard.css; built by buildNav)
      '<div class="rs-svw-nav"><div class="rs-svw-ground"></div></div>';
    document.body.appendChild(w);
    const bar=w.firstChild, ttl=w.querySelector(".rs-svw-t"), msg=w.querySelector(".rs-svw-msg"),
          fr=w.querySelector("iframe"), pdiv=w.querySelector(".rs-svw-pano"), adiv=w.querySelector(".rs-svw-alt"), aside=w.querySelector(".rs-svw-aside"),
          provBox=w.querySelector(".rs-svw-prov"), covBtn=w.querySelector(".rs-svw-cov"), stepBox=w.querySelector(".rs-svw-step"), navBox=w.querySelector(".rs-svw-ground");
    const {st, save, place}=dock ? _svDock(w) : _rsFloat(w, bar, "rs-street-view-window", false);
    // Linked (a real panorama, with a Google key) or Classic (Google's keyless embed): the page's option `street_view_mode`; none: Linked with a key, else Classic
    let mode=_svKey && O.street_view_mode!=="classic" ? "linked" : "classic", pano=null, svc=null;
    // a narrow window (under 440 px): the header stays one row, the name of the road is cut with "…" (its tooltip has the whole name) (rs-svw-narrow, dashboard.css)
    new ResizeObserver(()=>w.classList.toggle("rs-svw-narrow", w.clientWidth>0 && w.clientWidth<440)).observe(w);
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
        if(mode!=="linked" || w.hidden || prov!=="google") return;   // closed, or switched to Panoramax / Mapillary, while it was asked for: the late answer must not draw over their viewer
        const id=r.data.location.pano, pov={heading:+h||0, pitch:0};
        fr.hidden=true; msg.hidden=true; pdiv.hidden=false;
        if(pano){ pano.setPano(id); pano.setPov(pov); return; }
        pano=new g.StreetViewPanorama(pdiv, {pano:id, pov:pov, visible:true,
                                             motionTracking:false, addressControl:false, fullscreenControl:true});
        const report=()=>{ const p=pano && pano.getPosition(); if(p) rsSetStreetViewMarkerAt(p.lng(), p.lat(), pano.getPov().heading); };
        pano.addListener("position_changed", report); pano.addListener("pov_changed", report);
        // a panorama does not see its box change size (the docked window, dragged by its divider): it is told
        if(dock){ const p0=pano; new ResizeObserver(()=>{ if(pano===p0) g.event.trigger(p0, "resize"); }).observe(pdiv); } },
        ()=>{ if(prov!=="google") return; hideP(); msg.hidden=false; msg.textContent="No street photos within 50 m of this spot."; }); });
    // THE PROVIDER: Google (above), or Panoramax / Mapillary: the nearest photo to the spot in their own viewer (svproviders.js).
    // The choice and the coverage switch are remembered in this browser.
    const PROV_KEY="rs-street-view-provider", COV_KEY="rs-street-view-cov";
    let prov="google", cov=false, altTok=0, alt=null;   // alt: the open viewer {prov, ctl}
    try{ prov=localStorage.getItem(PROV_KEY)||"google"; cov=localStorage.getItem(COV_KEY)==="1"; }catch(e){}
    if(!SV_PROVIDERS[prov]) prov="google";
    const chrome=()=>{                          // what the bar offers for the provider that is chosen
      provBox.querySelectorAll("button").forEach(b=>b.classList.toggle("on", b.dataset.p===prov));
      stepBox.hidden = !(prov==="google" && mode==="classic");      // only the keyless embed needs the bar's steps: Linked and Mapillary have arrows in their picture, and Panoramax has the two buttons over its picture (rs-svw-nav); rsStreetViewStep stays in the API
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
    const dropAlt=()=>{ aside.hidden=true; if(alt){ alt.ctl.destroy(); alt=null; } adiv.hidden=true; };
    const note=(html, keep)=>{ aside.hidden=true; fr.hidden=true; hideP(); if(!keep) dropAlt(); else adiv.hidden=true; msg.hidden=false; msg.innerHTML=html; };
    const failAt=(tok, e)=>{ if(tok===altTok) note("<b>"+_esc(SV_PROVIDERS[prov].title)+" is not reachable.</b><span>"+_esc(e.message||String(e))+"</span>"); };
    // r (a photo as _spFind answers) in the provider's viewer, looking h (null: the way the photo looks)
    // Panoramax has no arrows of its own, as Mapillary's viewer has: one arrow on the picture for each photo near the one on screen (a step forward or back, a side street),
    // turning with the picture; a click goes to that photo, looks the way of the move, and the marker goes where it was taken
    // The arrows are laid out as Mapillary's viewer does (mapillary-js 4.1.2, DirectionDOMCalculator and DirectionDOMRenderer): one container at the bottom centre of the picture,
    // 260 to 460 px wide by the size of the picture and 0.77 of that high, its bottom 8% of its height below the picture's bottom; the container is tilted (CSS perspective, rotateX 60).
    // An arrow is a circle of 0.34 of its height, on a ring of radius 0.31 of its height, at the angle of the move to the camera's heading (so that it turns with the picture), turned
    // to point that way, with a shadow to the lower side. The picture's own bar (zoom) is the bottom 40 px, and the container stands on it.
    const aimNav=yaw=>{
      const W=adiv.clientWidth, H=adiv.clientHeight; if(!W || !H) return;
      const c=Math.max(0, Math.min(1, Math.min((W-320)/(1480-320), (H-240)/(820-240)))), cw=260+0.04*Math.round(25*c)*(460-260), ch=0.77*cw, circle=0.34*ch, radius=0.31*ch;
      navBox.parentNode.style.top=adiv.offsetTop+"px"; navBox.parentNode.style.height=H+"px";
      Object.assign(navBox.style, {width:cw+"px", height:ch+"px", marginLeft:(-cw/2)+"px", bottom:(40-0.08*ch)+"px", transform:"perspective("+cw+"px) rotateX(60deg)"});
      navBox.querySelectorAll("button").forEach(b=>{
        const rel=(((+b.dataset.bearing-yaw)%360)+540)%360-180, a=rel*Math.PI/180;
        b.style.width=b.style.height=circle+"px"; b.style.marginLeft=b.style.marginTop=(-circle/2)+"px";
        b.style.transform="translate("+Math.round(radius*Math.sin(a)+cw/2)+"px,"+Math.round(-radius*Math.cos(a)+ch/2)+"px) rotate("+rel+"deg)";
        b.firstChild.style.filter="drop-shadow("+(3*Math.sin(a)).toFixed(2)+"px "+(3*Math.cos(a)).toFixed(2)+"px 1px rgba(0,0,0,0.8))"; }); };
    // the arrow of Mapillary's viewer, as it is in mapillary-js 4.1.2 (dist/mapillary.css, .mapillary-direction-arrow-step): a rounded white chevron in a round, transparent hit area, which
    // is shaded on hover (dashboard.css); the ground plane there lays it down in perspective
    const NAV_ARROW='<svg viewBox="0 0 100 58.77" aria-hidden="true"><path d="M97.44,43.82L56.18,2.56a8.75,8.75,0,0,0-12.37,0h0L2.56,43.8A8.75,8.75,0,0,0,14.94,56.18l35-35L85.05,56.2A8.75,8.75,0,1,0,97.44,43.82h0Z"/></svg>';
    let navPh=null, navYaw=null;                // the Panoramax photo on screen, and the heading of the view
    const buildNav=r=>{ drawNav(r); _spLoadAround(r).then(()=>{ if(navPh===r && prov==="panoramax" && !w.hidden) drawNav(r); }); };      // the photos around it may still have to be loaded
    const drawNav=r=>{
      navPh=r; navBox.textContent=""; const list=_spAround(r); _spWarm(list);
      list.forEach(t=>{ const b=document.createElement("button"); b.type="button"; b.dataset.bearing=t.bearing; b.innerHTML=NAV_ARROW;
        b.title="The photo "+Math.round(t.d)+" m away"; b.setAttribute("aria-label", b.title);
        b.onclick=()=>{ const tok=++altTok; exact=true;
          const on=_spSnap(rsStreetViewLine(), t.lat, t.lng, 15);      // the marker stays on the selected road: a photo's own position is a GPS fix, often beside the road
          present(on ? {...t, sx:on.lng, sy:on.lat} : t, t.bearing, tok); }; navBox.appendChild(b); });
      aimNav(navYaw==null ? r.azimuth||0 : navYaw); };
    const present=(r, h, tok)=>{
      const fail=e=>failAt(tok, e);
      const go=()=>{
        if(tok!==altTok || w.hidden) return;
        if(r && r.lng!=null) _spMark([r.lng, r.lat]);          // the ring shows which dot of the coverage this photo is (it can be on the other carriageway)
        fr.hidden=true; hideP(); msg.hidden=true; adiv.hidden=false;
        // a photo that looks aside from the road (nothing here looks along it): the window says so
        aside.hidden=!(r && r.aside); if(r && r.aside){ aside.style.top=(adiv.offsetTop+8)+"px"; aside.textContent="This photo looks "+r.aside+"\u00b0 aside from the road. No photo here looks along the road."; }
        if(prov==="panoramax"){ if(navPh!==r) navYaw=h==null ? null : +h; buildNav(r); }      // the arrows to the photos near it, and their images loaded ahead
        alt.ctl.go(r, h).catch(fail); };
      if(alt && alt.prov===prov) return go();
      dropAlt(); const mine=tok; adiv.hidden=false;
      _spOpen(prov, adiv, (lng, lat, hd)=>{ if(alt && alt.ctl===ctlRef){ rsSetStreetViewMarkerAt(lng, lat, hd, exact); if(prov==="panoramax"){ navYaw=hd; aimNav(hd); } } }).then(c=>{
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
      if(!ahead){ ahead=true; _spPrefetch(prov, rsStreetViewLine(), +vp[0], +vp[1]).then(()=>{ if(navPh && prov==="panoramax" && !w.hidden) drawNav(navPh); }); }      // the arrows are made again when the photos along the road have been loaded   // the road's other photos, loaded in the background
      const fail=e=>failAt(tok, e);
      _spFind(prov, +vp[0], +vp[1], h).then(r=>{
        if(tok!==altTok || w.hidden) return;    // a newer spot, another provider, or the window closed meanwhile
        if(!r) return note("No "+P.title+" photos within 30 m of this spot looking along the road.");
        present(r, h, tok); }, fail);
    };
    let last=null, btn=null, ctlRef=null, ahead=false, exact=false;                   // the latest road selection: {name, url}
    const show=()=>{
      if(w.hidden || !last) return;
      ttl.textContent=last.name; ttl.title=last.name;
      if(prov!=="google") return showAlt();
      if(!last.url || fromDisk){               // Google's embed stays grey in a file:// page
        fr.hidden=true; hideP(); msg.hidden=false;
        msg.innerHTML = !last.url ? "No Street View for this road." :
          "<b>Street View needs this page served, not opened from disk.</b>"+
          "<span>Run <code>python -m http.server</code> in its folder and open it from localhost.</span>"+
          '<a href="'+_esc(last.url)+'" target="_blank" rel="noopener">Open this spot in Google Maps \u2197</a>';
        return; }
      // Google won't frame last.url; this is its embeddable twin (Google's "Share > Embed a map" form)
      const u=new URL(last.url), vp=u.searchParams.get("viewpoint").split(",");
      const src="https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d"+vp[0]+"!2d"+vp[1]+
                "!3f"+(u.searchParams.get("heading")||0)+"!4f0!5f1";
      const embed=()=>{ if(fr.getAttribute("src")!==src) fr.src=src; fr.hidden=false; msg.hidden=true; hideP(); };
      if(_svKey && mode==="linked"){ fr.hidden=true; panoAt(vp[0], vp[1], u.searchParams.get("heading")||0).catch(e=>{ console.warn("rs street view:", e); if(prov==="google") embed(); }); return; }
      embed();
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
      holdPopup("street-view", !!on);                                // Street View shows the road: no road popup over it while it is open
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

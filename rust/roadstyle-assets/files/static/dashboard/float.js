// shared by the Street View and Google 3D windows
import {map} from "./core.js";
// GOOGLE'S MAPS JAVASCRIPT API, loaded once for every window that needs it (Street View's Linked
// panorama, Google 3D): a page may load Google's script only once
let _gmLoading=null;
export function _gmLoad(key){ return _gmLoading || (_gmLoading=new Promise((ok, no)=>{
  window.__rsGmReady=ok; const s=document.createElement("script");
  s.src="https://maps.googleapis.com/maps/api/js?key="+encodeURIComponent(key)+"&v=weekly&loading=async&callback=__rsGmReady";
  s.async=true; s.onerror=no; document.head.appendChild(s); })); }
// A FLOATING WINDOW over the map (Street View, Google 3D): dragged by its bar, resized by its corner,
// always inside the map. Its place, size and open state are remembered per PAGE in this browser:
// every map on a site shares one localStorage, and a window enlarged on a big page must not reopen
// over a small embedded one. The first open puts it in the map's bottom-right corner (left: bottom-left).
export function _rsFloat(w, bar, name, left){
  const KEY=name+":"+location.pathname;
  const st=(()=>{ try{ return JSON.parse(localStorage.getItem(KEY))||{}; }catch(e){ return {}; } })();
  const save=()=>{ try{ localStorage.setItem(KEY, JSON.stringify(st)); }catch(e){} };
  if(st.w) Object.assign(w.style, {width:st.w+"px", height:st.h+"px"});
  // anchor by the top-left once visible, so the corner grip grows the window toward the pointer
  // (right/bottom anchoring grows it the other way); keep a remembered spot on this screen
  const place=()=>{
    const m=map.getContainer().getBoundingClientRect();
    // never bigger than most of the map, so the map stays clickable beside it
    const W=Math.min(w.offsetWidth, Math.max(220, m.width*0.6)), H=Math.min(w.offsetHeight, Math.max(150, m.height*0.6));
    Object.assign(w.style, {width:W+"px", height:H+"px"});
    if(st.left==null){    // first open: a bottom corner of the map, whatever panels the page adds
      st.left=left ? m.left+12 : m.right-W-56; st.top=m.bottom-H-40; }
    // ...and inside the map, whatever screen it was placed on before
    st.left=Math.max(m.left, Math.min(m.right-W, st.left)); st.top=Math.max(m.top, Math.min(m.bottom-H, st.top));
    Object.assign(w.style, {left:st.left+"px", top:st.top+"px", right:"auto", bottom:"auto"});
  };
  bar.addEventListener("pointerdown", e=>{    // drag by the title bar
    if(e.target.tagName==="BUTTON") return;
    const r=w.getBoundingClientRect(), dx=e.clientX-r.left, dy=e.clientY-r.top;
    bar.setPointerCapture(e.pointerId); w.classList.add("rs-drag");   // the iframe mustn't swallow it
    // inside the MAP, not the browser window: a page's side panel covers the rest, and a window
    // dragged under it could not be reached again
    const mv=ev=>{ const m=map.getContainer().getBoundingClientRect();
                   st.left=Math.max(m.left, Math.min(m.right-w.offsetWidth, ev.clientX-dx));
                   st.top=Math.max(m.top, Math.min(m.bottom-30, ev.clientY-dy));
                   Object.assign(w.style, {left:st.left+"px", top:st.top+"px", right:"auto", bottom:"auto"}); };
    bar.addEventListener("pointermove", mv);
    bar.addEventListener("pointerup", ()=>{ bar.removeEventListener("pointermove", mv);
      w.classList.remove("rs-drag"); save(); }, {once:true});
  });
  new ResizeObserver(()=>{ if(!w.hidden && innerWidth>520){ st.w=w.offsetWidth; st.h=w.offsetHeight; save(); } }).observe(w);
  // THE MAP CHANGED SIZE (a side panel shown again, the browser narrowed): pull the window back
  // inside it, or it sits under the panel where no one can reach it
  map.on("resize", ()=>{ if(!w.hidden && innerWidth>520){ place(); save(); } });
  return {st, save, place};
}

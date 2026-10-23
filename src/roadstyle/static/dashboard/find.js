// FIND: substring over the curated popup fields (or every public prop) — matched against each
// field's VALUE, or its column NAME when the field is set, so "bridge" finds bridge=yes roads (no
// value literally contains "bridge"), likewise tunnel/oneway. The road's id is ALWAYS searched,
// whatever the popup lists: a page with its own popup fields (road_popup=[...] without edge_id)
// found no road by its id, the one search a review needs. rsFind(text) returns the matching ids
// (as rsQuery does); the search box of the panel and of find_control=True is UI over it.
import {O, rsQuery, rsFocus} from "./core.js";
import {_popupMode, _tlHost} from "./panel.js";
import {_popupFields, _ID_KEYS, rsSelect} from "./select.js";
function _findRows(q){
  q=(q||"").trim().toLowerCase();
  if(q.length<2) return {ids:[], info:[]};
  const only=(_popupFields&&_popupFields.length)
    ?_popupFields.concat(_ID_KEYS.filter(function(k){ return _popupFields.indexOf(k)<0; })):null, info=[];
  const ids=rsQuery(function(p){
    const ks=only||Object.keys(p);
    for(const k of ks){ if(k[0]==="_"||k==="lvl") continue;
      const v=p[k]; if(v==null) continue; const t=(""+v).toLowerCase();
      const set=t&&t!=="nan"&&t!=="no"&&t!=="false"&&t!=="none"&&t!=="0";
      if((t!=="nan"&&t.indexOf(q)>=0)||(k.toLowerCase().indexOf(q)>=0&&set)){ info.push([k, ""+v, p.name!=null?""+p.name:""]); return true; } }
    return false;
  });
  return {ids:ids, info:info};
}
export function rsFind(text){ return _findRows(text).ids; }
// the box: type, 250 ms later up to 30 rows; a click on a row selects the road (record + highlight,
// exactly like a map click) and flies to it
export function _findWire(qin, qres){
  function run(q){
    const r=_findRows(q), ids=r.ids, info=r.info;
    if(!ids.length && (q||"").trim().length<2){ qres.innerHTML=""; return; }
    const n=Math.min(ids.length,30); let h="";
    for(let i=0;i<n;i++){ const k=info[i][0], v=info[i][1], nm=info[i][2];
      const lab=(nm&&nm.toLowerCase()!=="nan")?nm:v;
      h+='<div class="rs-qrow" data-id="'+ids[i]+'"><b>'+lab+'</b><span>'+k+': '+v+'</span></div>'; }
    if(!ids.length) h='<div class="rs-qmore">no match</div>';
    else if(ids.length>n) h+='<div class="rs-qmore">'+ids.length+' matches \u2014 showing '+n+'</div>';
    qres.innerHTML=h;
    qres.querySelectorAll(".rs-qrow").forEach(function(r){
      r.onclick=function(){ const id=+r.dataset.id; rsSelect(id); rsFocus(id); }; });
  }
  let t=0;
  qin.oninput=function(){ clearTimeout(t); t=setTimeout(function(){ run(qin.value); },250); };
  qin.onkeydown=function(e){ if(e.key==="Escape"){ qin.value=""; run(""); } };
}
export function initFind(){
  window.rsFind = rsFind;
  if(O.find_control && _popupMode!=="panel"){    // find_control=True: the search box on a page with no docked panel
    const fb=document.createElement("div"); fb.className="rs-find rs-side-q";
    fb.innerHTML='<input type="search" placeholder="Search roads\u2026" spellcheck="false"><div class="rs-side-q-res"></div>';
    _findWire(fb.querySelector("input"), fb.querySelector(".rs-side-q-res"));
    _tlHost().prepend(fb);
  }
}

// road-class filtering: window.rsSetClasses([...]) shows exactly those classes and hides the
// rest across every road layer; the collapsible checkbox panel is just UI over it. The class
// filter composes (AND) with the id filter from rsFilter below.
import {map, O, RS_TILED, _has, _itemOv, _rprops, _sfeats, _lyr} from "./core.js";
import {_popupMode, _tlHost} from "./panel.js";
export let FILTER = {on:false, classes:[]};
const _fltCbs={}, _fltBase={};
let _fltVis=null;   // Set of visible classes; null = all
let _qIds=null;     // id-set filter from rsFilter; null = off
let ACCESS = [];   // access_col: [[kind, colour, label, count], ...] for the kinds the data has (docs/design/sensor_matching_requests.md)
const _accHid = new Set();            // the access kinds switched off (rsSetAccess)
let _bridgesOn=true;   // rsSetBridges: hide every elevated (lvl>0) road and its 3D deck ribbons
let _tunnelsOn=true;   // rsSetTunnels: hide every below-ground (lvl<0) road, its names and arrows
const _ovIds={};       // an attached overlay's own rsFilter(ids, label) id set, by label (composed with its edges' filter below)
// the overlay attached to edges (Overlay(edge_col=...)) that a layer draws: core.js, _itemOv
const _fltLayers=()=>map.getStyle().layers.filter(l=>l.id.indexOf("roads")===0 || _itemOv(l.id));
// the one lookup (docs/design/edge_items.md): the class, bridge, tunnel and rsFilter switches decide which edges show, and every layer that
// draws a piece of a road, or an item attached to one, shows exactly the pieces and items of those edges. The class and level tests stay
// short property tests: every piece and item carries its edge's class (__rs_cls: FILTER.col of the edge, also on a name or an arrow,
// which carry the chain's highway) and level (lvl; an attached item has it baked as __rs_lvl). The rsFilter id set goes through the label: __rs_edge, or __rs_edge2 (a two-way pair's shared piece shows while
// either edge shows). A shadow line or a 3D deck covers several edges (__rs_edges): it shows while any of them shows, decided here.
export function _applyRoadFilters(){
  const hidden = _fltVis===null ? [] : FILTER.classes.filter(c=>!_fltVis.has(c)), hid=new Set(hidden), q=_qIds && new Set(_qIds);
  const edgeOn = i=>{ const p=_rprops(i), v=p.lvl||0;
    return !hid.has(p.__rs_cls) && !(p.__rs_access && _accHid.has(p.__rs_access)) && (_bridgesOn || v<1) && (_tunnelsOn || v>=0) && (!q || q.has(i)); };
  const multi = {};   // decks / shadows: the ids of the features with at least one edge shown (null = no switch is on)
  ["decks","shadows"].forEach(src=>{ multi[src] = !_bridgesOn ? [] : (hidden.length || q || !_tunnelsOn || _accHid.size)
    ? _sfeats(src).map((f,k)=>(f.properties.__rs_edges||[]).some(edgeOn) ? k : -1).filter(k=>k>=0) : null; });
  const and = (f,c)=>f?["all",f,c]:c;
  const qr = q && ["any",_has(["id"],_qIds),_has(["get","__rs_edge2"],_qIds)], qe = q && ["any",_has(["get","__rs_edge"],_qIds),_has(["get","__rs_edge2"],_qIds)];   // once per change
  _fltLayers().forEach(l=>{
    if(!(l.id in _fltBase)) _fltBase[l.id]=map.getFilter(l.id)||null;
    let f=_fltBase[l.id];
    // the layer's data: roads, casings, halves, ends, slots, arrows, decks, shadows or an overlay; in tiles mode the slots share the archive
    // source, so the tile layer name is what separates them
    const kind = RS_TILED && l.source==="roads" ? l["source-layer"] : l.source, ov=_itemOv(l.id);
    if(kind==="decks" || kind==="shadows"){
      if(multi[kind]) f=and(f, multi[kind].length ? _has(["id"], multi[kind]) : false);
    }else{
      const lvl=ov?"__rs_lvl":"lvl";
      if(hidden.length) f=and(f, ["!",["in",["get","__rs_cls"],["literal",hidden]]]);
      if(_accHid.size) f=and(f, ["!",["in",["coalesce",["get","__rs_access"],""],["literal",[..._accHid]]]]);
      if(!_bridgesOn) f=and(f, ["<",["coalesce",["get",lvl],0],1]);
      if(!_tunnelsOn) f=and(f, [">=",["coalesce",["get",lvl],0],0]);
      if(q) f=and(f, kind==="roads" ? qr : qe);
      if(ov && _ovIds[ov.label]) f=and(f, _has(["id"],_ovIds[ov.label]));
    }
    // validate:false: our own filters need no grammar check, which cost ~6 ms a layer (a mode or class switch on a page of ~500 layers froze it ~3 s)
    try{ map.setFilter(l.id,f,{validate:false}); }catch(e){}
  });
  return hidden;
}
export function rsSetClasses(visible){
  _fltVis=new Set(visible);
  const hidden=_applyRoadFilters();
  FILTER.classes.forEach(c=>{ if(_fltCbs[c]) _fltCbs[c].checked=_fltVis.has(c); });
  document.dispatchEvent(new CustomEvent("rs:filterchange",
    {detail:{visible:FILTER.classes.filter(c=>_fltVis.has(c)), hidden:hidden}}));
}
export const _fltSw = {};   // class -> its swatch element in the Roads panel
export function rsSetBridges(on){
  _bridgesOn=!!on; _applyRoadFilters();
  const cb=document.getElementById("rs-flt-br"); if(cb) cb.checked=_bridgesOn;
  document.dispatchEvent(new CustomEvent("rs:filterchange",{detail:{bridges:_bridgesOn}}));
}
export function rsSetTunnels(on){
  _tunnelsOn=!!on; _applyRoadFilters();
  const cb=document.getElementById("rs-flt-tn"); if(cb) cb.checked=_tunnelsOn;
  document.dispatchEvent(new CustomEvent("rs:filterchange",{detail:{tunnels:_tunnelsOn}}));
}
export function rsFilter(ids, layer){   // show only these features; rsFilter(null) resets
  const L=_lyr(layer); if(!L) return;
  if(L.ov){
    // an overlay attached to edges: its own ids AND its edges' filter (the one lookup above)
    if(L.ov.base){ if(ids==null) delete _ovIds[L.ov.label]; else _ovIds[L.ov.label]=Array.from(ids); _applyRoadFilters(); }
    else{ const f = ids==null ? null : _has(["id"],ids);
      L.ov.layers.forEach(id=>{ if(map.getLayer(id)) try{ map.setFilter(id, f, {validate:false}); }catch(e){} }); }
    document.dispatchEvent(new CustomEvent("rs:filterchange",
      {detail:{overlay:L.ov.label, ids:ids==null?null:Array.from(ids)}}));
    return;
  }
  _qIds = ids==null ? null : Array.from(ids);
  _applyRoadFilters();
  document.dispatchEvent(new CustomEvent("rs:filterchange",{detail:{ids:_qIds}}));
}
export function rsSetAccess(kind, on){      // show / hide the roads of one access kind
  on ? _accHid.delete(kind) : _accHid.add(kind); _applyRoadFilters();
  const cb=document.getElementById("rs-flt-acc-"+kind); if(cb) cb.checked=!!on;
  document.dispatchEvent(new CustomEvent("rs:filterchange",{detail:{access:kind, visible:!!on}}));
}
export function initFilter(){
  FILTER = O.filter; ACCESS = FILTER.access || [];
  map.on("load",()=>{ _fltLayers().forEach(l=>{ if(!(l.id in _fltBase)) _fltBase[l.id]=map.getFilter(l.id)||null; }); });
  window.rsSetClasses = rsSetClasses;
  window.RS_CLASSES = FILTER.classes;
  window.RS_CLASS_COL = FILTER.col;          // the column RS_CLASSES came from (for custom UIs / stats)
  window.RS_CLASS_COLORS = FILTER.swatches || {};   // class -> its baked fill colour
  window.rsSetBridges = rsSetBridges;
  window.rsSetTunnels = rsSetTunnels;
  window.rsFilter = rsFilter;
}
// the Roads box: a checkbox for each class, then Bridges / Tunnels and the access kinds
export function initFilterBox(){
  if(FILTER.on){
    const box=document.createElement("div"); box.className="flt-ctrl";
    const hd=document.createElement("div"); hd.className="flt-hd"; hd.textContent="Roads ▾";
    const body=document.createElement("div"); body.className="flt-body";
    hd.onclick=()=>{ const c=box.classList.toggle("collapsed"); hd.textContent="Roads "+(c?"▸":"▾"); };
    if(_popupMode==="panel"){ box.classList.add("collapsed"); hd.textContent="Roads ▸"; }  // panel: collapse to save space
    box.appendChild(hd); box.appendChild(body);
    FILTER.classes.forEach(c=>{      // _fltSw: the swatch of each class (a view's palette sets their colours, FILTER.palettes)
      const lab=document.createElement("label");
      const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=true;
      cb.onchange=()=> rsSetClasses(FILTER.classes.filter(k=>_fltCbs[k].checked));
      _fltCbs[c]=cb; lab.appendChild(cb);
      const sw=document.createElement("span"); sw.className="flt-sw"; _fltSw[c]=sw;
      sw.style.background=(FILTER.swatches||{})[c]||"#888"; lab.appendChild(sw);
      lab.appendChild(document.createTextNode(" "+c)); body.appendChild(lab);
    });
    // grade-separated data: Bridges / Tunnels on/off rows under the classes (the first one ruled off)
    [["bridges","rs-flt-br"," Bridges",rsSetBridges],["tunnels","rs-flt-tn"," Tunnels",rsSetTunnels]]
      .filter(r=>FILTER[r[0]]).forEach((r,i)=>{
        const lab=document.createElement("label"); lab.className="flt-grade";
        if(i===0) lab.style.cssText="margin-top:4px;padding-top:4px;border-top:1px solid #ddd";
        const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=true; cb.id=r[1];
        cb.onchange=()=> r[3](cb.checked);
        lab.appendChild(cb); lab.appendChild(document.createTextNode(r[2]));
        body.appendChild(lab);
      });
    // restricted roads (access_col): a row each after Bridges / Tunnels, with the kind's colour
    ACCESS.forEach((a,i)=>{
      const lab=document.createElement("label"); lab.className="flt-grade";
      if(i===0) lab.style.cssText="margin-top:4px;padding-top:4px;border-top:1px solid #ddd";
      const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=true; cb.id="rs-flt-acc-"+a[0];
      cb.onchange=()=> rsSetAccess(a[0], cb.checked);
      const sw=document.createElement("span"); sw.className="flt-sw"; sw.style.background=a[1];
      lab.appendChild(cb); lab.appendChild(sw); lab.appendChild(document.createTextNode(" "+a[2]));
      body.appendChild(lab);
    });
    _tlHost().appendChild(box);
  }
  window.rsSetAccess = rsSetAccess;
  window.rsGetAccess = ()=>Object.fromEntries(ACCESS.map(a=>[a[0], !_accHid.has(a[0])]));
  window.RS_ACCESS = Object.fromEntries(ACCESS.map(a=>[a[0], a[3]]));
}

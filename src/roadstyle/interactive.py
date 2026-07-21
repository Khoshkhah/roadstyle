"""Interactive JS road layer for folium — the single folium rendering path.

Draws the casing + fill geometry sandwich in the browser (Leaflet) from per-edge ``__rs_*`` style
props baked in Python (see :func:`roadstyle.stylers.bake_props`) — the *exact same* props the
canonical web renderer ``roadstyle.js`` reads, so the folium and web backends can't drift. Because
the styling is baked, this one layer serves every styling mode (road class, categorical, numeric):
it highlights an edge white on hover, pins a tooltip on click (with copy-to-clipboard), and —
for class styling — toggles types via a filter.
"""
from __future__ import annotations

from branca.element import MacroElement
from jinja2 import Template

from .palettes import ORDER

_TEMPLATE = Template("""
{% macro header(this, kwargs) %}
<style>
.rs-filter{background:rgba(20,24,30,.82);backdrop-filter:blur(6px);border-radius:12px;
  padding:8px 10px;box-shadow:0 3px 14px rgba(0,0,0,.45);font:600 11px/1.5 system-ui,sans-serif;
  color:#cfd6dd;max-height:60vh;overflow:auto;}
.rs-filter h4{margin:0 0 6px;font-size:11px;letter-spacing:.3px;color:#9fb0bf;
  text-transform:uppercase;}
.rs-filter label{display:flex;align-items:center;gap:7px;cursor:pointer;padding:2px 0;
  white-space:nowrap;}
.rs-filter input{accent-color:#00E5FF;}
.rs-sw{width:14px;height:4px;border-radius:2px;display:inline-block;}
.rs-filter .rs-all{margin-top:6px;border-top:1px solid rgba(255,255,255,.12);padding-top:6px;
  display:flex;gap:8px;}
.rs-filter .rs-all button{flex:1;background:rgba(255,255,255,.08);border:none;color:#cfd6dd;
  border-radius:6px;padding:3px 0;cursor:pointer;font:inherit;}
.leaflet-tooltip.rs-tip-pinned{background:rgba(20,24,30,.92);color:#e6edf3;border:1px solid #38bdf8;
  box-shadow:0 3px 14px rgba(0,0,0,.5);font:600 11px/1.4 system-ui,sans-serif;
  pointer-events:auto;user-select:text;-webkit-user-select:text;cursor:auto;}
.leaflet-tooltip.rs-tip-pinned b{color:#9fb0bf;}
.leaflet-tooltip-top.rs-tip-pinned::before{border-top-color:rgba(20,24,30,.92);}
</style>
{% endmacro %}
{% macro script(this, kwargs) %}
(function(){
  var map = {{ this._parent.get_name() }};
  var DATA = {{ this.data }};                // GeoJSON whose features carry baked __rs_* props
  var TIP  = {{ this.tooltip|tojson }};
  var COPY = {{ this.copy_field|tojson }};
  var ORDER = {{ this.order|tojson }};       // road classes by importance (most important first)
  var disabled = {};
  var OIDX = {}; ORDER.forEach(function(t,i){ OIDX[t]=i; });

  function cls(f){ return f.properties.__rs_class; }
  function on(f){ var c=cls(f); return c==null || !disabled[c]; }   // null class = always visible

  function styleFill(f){
    var p=f.properties;
    return {color:p.__rs_fill, weight:p.__rs_w, opacity: on(f)?p.__rs_op:0,
            dashArray:p.__rs_dash, lineCap:'round', lineJoin:'round', interactive:on(f)};
  }
  function styleCasing(f){
    // One casing colour per edge (baked __rs_casing), constant on every base map.
    var p=f.properties, c = p.__rs_casing;
    if(c==null || !(p.__rs_cw>0)) return {opacity:0, weight:0};
    return {color:c, weight:p.__rs_cw, opacity: on(f)?p.__rs_cop:0,
            lineCap:'round', lineJoin:'round'};
  }

  // ── click-to-copy a field (default edge_id) to the clipboard ────────────────
  function rsExec(t){var a=document.createElement('textarea');a.value=t;a.style.position='fixed';
    a.style.opacity='0';document.body.appendChild(a);a.select();
    try{document.execCommand('copy');}catch(e){}document.body.removeChild(a);}
  function rsCopy(t){if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(t).catch(function(){rsExec(t);});}else{rsExec(t);}}
  function rsToast(msg){var el=document.getElementById('rs-toast');
    if(!el){el=document.createElement('div');el.id='rs-toast';el.style.cssText=
      'position:fixed;z-index:9999;left:50%;bottom:20px;transform:translateX(-50%);'+
      'background:rgba(0,0,0,.82);color:#fff;font:12px system-ui;padding:6px 13px;'+
      'border-radius:14px;pointer-events:none;opacity:0;transition:opacity .15s';
      document.body.appendChild(el);}
    el.textContent=msg;el.style.opacity='1';clearTimeout(window.__rsToastT);
    window.__rsToastT=setTimeout(function(){el.style.opacity='0';},1300);}

  // ── click-to-pin a tooltip open (survives mouseout; click again / the map to unpin) ──────────
  function tipHtml(props){
    return TIP.map(function(k){
      return '<b>'+k+'</b>: '+(props[k]==null?'':props[k]); }).join('<br>');
  }
  var pinned=null, pinnedLayer=null;
  function rsUnpin(){ if(pinned){ map.removeLayer(pinned); pinned=null; } pinnedLayer=null; }
  function rsPin(layer, props, latlng){
    rsUnpin();
    if(!TIP.length || !latlng) return;
    pinnedLayer=layer;
    pinned=L.tooltip({permanent:true, interactive:true, direction:'top', offset:[0,-4],
                      className:'rs-tip-pinned'})
           .setLatLng(latlng).setContent('📌 '+tipHtml(props)).addTo(map);
    var el=pinned.getElement(); if(el && L.DomEvent) L.DomEvent.disableClickPropagation(el);
  }
  map.on('click', function(){ rsUnpin(); });   // click the map background to unpin

  var casingLayer = L.geoJSON(DATA, {style: styleCasing}).addTo(map);
  var fillLayer = L.geoJSON(DATA, {style: styleFill, onEachFeature: function(feat, layer){
    if(TIP.length){
      var html = tipHtml(feat.properties);
      if(COPY) html += '<br><i>click to copy '+COPY+'</i>';
      layer.bindTooltip(html, {sticky:true});
    }
    layer.on('mouseover', function(e){
      if(!on(feat)) return;
      if(pinnedLayer===layer){ e.target.closeTooltip(); return; }   // pinned: don't stack hover tip
      e.target.setStyle({color:'#ffffff', weight:feat.properties.__rs_w+2, opacity:1});
      e.target.bringToFront();
    });
    layer.on('mouseout', function(e){ fillLayer.resetStyle(e.target); });
    layer.on('click', function(e){
      if(L.DomEvent) L.DomEvent.stopPropagation(e);    // keep the map-click handler from unpinning
      if(pinnedLayer===layer){ rsUnpin(); }            // click the pinned edge again -> unpin
      else { rsPin(layer, feat.properties, e.latlng); }
      if(COPY){ var v=feat.properties[COPY];
        if(v!=null){ rsCopy(String(v)); rsToast('copied '+COPY+' '+v); } }
    });
  }}).addTo(map);

  // base-switcher hook (kept for the switcher's call; casing is constant per edge now)
  window.{{ this.hook }} = function(isDark){};

  // ── highway-type filter panel (class styling only) ─────────────────────────
  {% if this.show_filter %}
  var swatch = {}, types = {};               // class -> a representative fill colour
  DATA.features.forEach(function(f){ var c=f.properties.__rs_class;
    if(c!=null){ types[c]=true; if(!(c in swatch)) swatch[c]=f.properties.__rs_fill; } });
  types = Object.keys(types).sort(function(a,b){
    var ia=(a in OIDX)?OIDX[a]:999, ib=(b in OIDX)?OIDX[b]:999;
    return ia-ib || (a<b?-1:(a>b?1:0));            // by importance, then alphabetical
  });
  function refresh(){ casingLayer.setStyle(styleCasing); fillLayer.setStyle(styleFill); }
  var Filter = L.Control.extend({ options:{position:'topright'}, onAdd:function(){
    var d=L.DomUtil.create('div','rs-filter');
    d.innerHTML='<h4>Road types</h4>';
    types.forEach(function(t){
      var row=L.DomUtil.create('label','',d);
      var cb=document.createElement('input'); cb.type='checkbox'; cb.checked=true; cb.dataset.t=t;
      cb.onchange=function(){ if(cb.checked) delete disabled[t]; else disabled[t]=1; refresh(); };
      var sw=document.createElement('span'); sw.className='rs-sw';
      sw.style.background=swatch[t]||'#888';
      var tx=document.createElement('span'); tx.textContent=t;
      row.appendChild(cb); row.appendChild(sw); row.appendChild(tx);
    });
    var bar=L.DomUtil.create('div','rs-all',d);
    var ba=document.createElement('button'); ba.textContent='All';
    var bn=document.createElement('button'); bn.textContent='None';
    ba.onclick=function(){ disabled={};
      d.querySelectorAll('input').forEach(function(c){c.checked=true;}); refresh(); };
    bn.onclick=function(){ types.forEach(function(t){disabled[t]=1;});
      d.querySelectorAll('input').forEach(function(c){c.checked=false;}); refresh(); };
    bar.appendChild(ba); bar.appendChild(bn);
    L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
    return d;
  }});
  if(types.length) map.addControl(new Filter());
  {% endif %}

  // fit to data
  try { map.fitBounds(fillLayer.getBounds(), {padding:[20,20]}); } catch(e){}
})();
{% endmacro %}
""")


class InteractiveRoads(MacroElement):
    """Single folium road layer: reads baked ``__rs_*`` props; hover/pin/copy/filter/dynamic casing.

    ``geojson_str`` is a GeoJSON string whose features already carry the per-edge ``__rs_*`` style
    props (from :func:`roadstyle.stylers.bake_props`). ``show_filter`` adds the road-type filter
    panel (meaningful only for class styling — data-driven maps carry a legend instead).
    """

    def __init__(self, geojson_str, tooltip=None, show_filter=True,
                 hook="__rsCasing", copy_field=None, order=None):
        super().__init__()
        self._name = "InteractiveRoads"
        self.data = geojson_str                  # baked GeoJSON string (inserted as a JS literal)
        self.tooltip = tooltip or []
        self.copy_field = copy_field             # click an edge -> copy this field (None = off)
        self.order = order if order is not None else list(reversed(ORDER))
        self.show_filter = show_filter
        self.hook = hook
        self._template = _TEMPLATE

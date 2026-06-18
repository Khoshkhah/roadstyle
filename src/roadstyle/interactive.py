"""Interactive JS road layer for folium — dynamic casing, hover highlight, live filter.

Builds the casing + fill GeoJSON layers in the browser (Leaflet) from an embedded palette,
so we can: re-style casing when the base map changes (light casing on light maps, black on
dark/satellite), highlight an edge white on hover, and toggle highway types on/off via a
checkbox panel. Mirrors the osm-traffic-enrichment web renderer.
"""
from __future__ import annotations

from branca.element import MacroElement
from jinja2 import Template

from .palettes import FALLBACK, ORDER, PALETTES
from .style import CASING_OPACITY, FILL_OPACITY, LINK_SCALE


def _palette_js(palette: str) -> dict:
    out = {}
    for hw, rs in PALETTES[palette].items():
        out[hw] = {
            "fill": rs.fill, "w": rs.width, "cw": rs.casing_width,
            "cl": rs.casing_light, "cd": rs.casing_dark,
            "dash": ",".join(map(str, rs.dash)) if rs.dash else None,
        }
    return out


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
</style>
{% endmacro %}
{% macro script(this, kwargs) %}
(function(){
  var map = {{ this._parent.get_name() }};
  var DATA = {{ this.data }};
  var PAL  = {{ this.palette|tojson }};
  var HCOL = {{ this.highway_col|tojson }};
  var TIP  = {{ this.tooltip|tojson }};
  var FILLOP = {{ this.fill_op }}, CASOP = {{ this.casing_op }}, LINK = {{ this.link }};
  var FALLBACK = {{ this.fallback|tojson }};
  var ORDER = {{ this.order|tojson }};      // road types by importance (most important first)
  var IS_DARK = {{ 'true' if this.initial_dark else 'false' }};
  var disabled = {};
  var OIDX = {}; ORDER.forEach(function(t,i){ OIDX[t]=i; });

  function norm(hw){ hw=(hw==null?'':String(hw)).trim().toLowerCase();
    var link=hw.slice(-5)==='_link'; if(link) hw=hw.slice(0,-5); return [hw,link]; }
  function pal(hw){ return PAL[norm(hw)[0]] || PAL[FALLBACK]; }
  function on(hw){ return !disabled[norm(hw)[0]]; }

  function styleFill(f){
    var hw=f.properties[HCOL], p=pal(hw), link=norm(hw)[1];
    return {color:p.fill, weight:p.w*(link?LINK:1), opacity: on(hw)?FILLOP:0,
            dashArray:p.dash, lineCap:'round', lineJoin:'round', interactive:on(hw)};
  }
  function styleCasing(f){
    var hw=f.properties[HCOL], p=pal(hw), link=norm(hw)[1];
    var c = IS_DARK ? p.cd : p.cl;
    if(p.cw<=0 || c==null) return {opacity:0, weight:0};
    return {color:c, weight:p.cw*(link?LINK:1), opacity: on(hw)?CASOP:0,
            lineCap:'round', lineJoin:'round'};
  }

  // ── click-to-copy a field (default edge_id) to the clipboard ────────────────
  var COPY = {{ this.copy_field|tojson }};
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

  var casingLayer = L.geoJSON(DATA, {style: styleCasing}).addTo(map);
  var fillLayer = L.geoJSON(DATA, {style: styleFill, onEachFeature: function(feat, layer){
    if(TIP.length){
      var html = TIP.map(function(k){
        return '<b>'+k+'</b>: '+(feat.properties[k]==null?'':feat.properties[k]); }).join('<br>');
      if(COPY) html += '<br><i>click to copy '+COPY+'</i>';
      layer.bindTooltip(html, {sticky:true});
    }
    layer.on('mouseover', function(e){
      var hw=feat.properties[HCOL], p=pal(hw), link=norm(hw)[1];
      if(!on(hw)) return;
      e.target.setStyle({color:'#ffffff', weight:p.w*(link?LINK:1)+2, opacity:1});
      e.target.bringToFront();
    });
    layer.on('mouseout', function(e){ fillLayer.resetStyle(e.target); });
    if(COPY){ layer.on('click', function(){
      var v=feat.properties[COPY];
      if(v!=null){ rsCopy(String(v)); rsToast('copied '+COPY+' '+v); }
    }); }
  }}).addTo(map);

  // dynamic casing on base-map change (called by the base switcher)
  window.{{ this.hook }} = function(isDark){
    IS_DARK = !!isDark; casingLayer.setStyle(styleCasing); };

  // ── highway-type filter panel ──────────────────────────────────────────────
  var types = {};
  DATA.features.forEach(function(f){ types[norm(f.properties[HCOL])[0]] = true; });
  types = Object.keys(types).sort(function(a,b){
    var ia=(a in OIDX)?OIDX[a]:999, ib=(b in OIDX)?OIDX[b]:999;
    return ia-ib || (a<b?-1:(a>b?1:0));            // by importance, then alphabetical
  });
  function refresh(){ casingLayer.setStyle(styleCasing); fillLayer.setStyle(styleFill); }
  var Filter = L.Control.extend({ options:{position:'topright'}, onAdd:function(){
    var d=L.DomUtil.create('div','rs-filter');
    d.innerHTML='<h4>Road types</h4>';
    types.forEach(function(t){
      var p=PAL[t]||PAL[FALLBACK];
      var row=L.DomUtil.create('label','',d);
      var cb=document.createElement('input'); cb.type='checkbox'; cb.checked=true; cb.dataset.t=t;
      cb.onchange=function(){ if(cb.checked) delete disabled[t]; else disabled[t]=1; refresh(); };
      var sw=document.createElement('span'); sw.className='rs-sw'; sw.style.background=p.fill;
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
  {% if this.show_filter %}map.addControl(new Filter());{% endif %}

  // fit to data
  try { map.fitBounds(fillLayer.getBounds(), {padding:[20,20]}); } catch(e){}
})();
{% endmacro %}
""")


class InteractiveRoads(MacroElement):
    def __init__(self, geojson_str, palette="highsat", highway_col="highway",
                 tooltip=None, initial_dark=True, show_filter=True, hook="__rsCasing",
                 copy_field=None):
        super().__init__()
        self._name = "InteractiveRoads"
        self.data = geojson_str                  # raw GeoJSON string (inserted as JS literal)
        self.palette = _palette_js(palette)
        self.highway_col = highway_col
        self.tooltip = tooltip or []
        self.copy_field = copy_field             # click an edge -> copy this field (None = off)
        self.fill_op = FILL_OPACITY
        self.casing_op = CASING_OPACITY
        self.link = LINK_SCALE
        self.fallback = FALLBACK
        self.order = list(reversed(ORDER))       # most important first
        self.initial_dark = initial_dark
        self.show_filter = show_filter
        self.hook = hook
        self._template = _TEMPLATE

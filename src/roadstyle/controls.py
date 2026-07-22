"""Base-layer selector for folium maps — a layers FAB that opens a thumbnail-card popover,
matching the osm-traffic-enrichment website (not the default Leaflet box)."""
from __future__ import annotations

from branca.element import MacroElement
from jinja2 import Template

from .basemaps import get_basemap

# stacked-layers icon (same as the website FAB)
_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
         'width="18" height="18"><path stroke-linecap="round" stroke-linejoin="round" '
         'd="M12 3l9 5-9 5-9-5 9-5z"/><path stroke-linecap="round" stroke-linejoin="round" '
         'd="M3 13l9 5 9-5"/><path stroke-linecap="round" stroke-linejoin="round" '
         'd="M3 18l9 5 9-5"/></svg>')

_TEMPLATE = Template("""
{% macro header(this, kwargs) %}
<style>
.rs-ctrl{position:relative;}
.rs-fab{width:44px;height:44px;border-radius:22px;background:rgba(22,26,32,.82);
  backdrop-filter:blur(20px) saturate(160%);-webkit-backdrop-filter:blur(20px) saturate(160%);
  border:1px solid rgba(255,255,255,.14);color:#dfe6ee;cursor:pointer;display:flex;
  align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,.3);transition:.15s;}
.rs-fab:hover{border-color:rgba(255,255,255,.30);}
.rs-fab.active{background:#22d3a3;border-color:#22d3a3;color:#04140d;}
.rs-pop{position:absolute;right:0;bottom:52px;background:rgba(22,26,32,.88);
  backdrop-filter:blur(20px) saturate(160%);-webkit-backdrop-filter:blur(20px) saturate(160%);
  border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:10px;min-width:220px;
  box-shadow:0 8px 24px rgba(0,0,0,.35);}
.rs-pop.hidden{display:none;}
.rs-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;}
.rs-card{padding:8px;border-radius:10px;border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.05);cursor:pointer;transition:background .12s,border-color .12s;}
.rs-card:hover{border-color:rgba(255,255,255,.26);}
.rs-card.active{background:rgba(34,211,163,.12);border-color:#22d3a3;}
.rs-prev{height:36px;border-radius:6px;margin-bottom:5px;position:relative;overflow:hidden;}
.rs-prev svg{position:absolute;inset:0;width:100%;height:100%;}
.rs-label{font:500 11px/1.3 system-ui,-apple-system,sans-serif;color:#dfe6ee;}
.rs-sat .leaflet-tile-pane{filter:saturate(.80) brightness(.90);}
</style>
{% endmacro %}
{% macro script(this, kwargs) %}
(function(){
  var map = {{ this._parent.get_name() }};
  var defs = {{ this.defs|tojson }};
  var layers = {};
  defs.forEach(function(d){
    layers[d.key] = d.url ? L.tileLayer(d.url,
      {attribution:d.attr||'', maxZoom:20, subdomains:d.sub||'abc'})
      : L.layerGroup();   // tile-less (blank): nothing to draw, bg colour set in switchTo
  });
  var container = map.getContainer();

  function switchTo(key){
    defs.forEach(function(d){ if(map.hasLayer(layers[d.key])) map.removeLayer(layers[d.key]); });
    layers[key].addTo(map);
    var d = defs.find(function(x){return x.key===key;});
    container.classList.toggle('rs-sat', !!(d && d.sat));
    container.style.background = (d && !d.url) ? d.bg : '';
    if(window.__rsCasing) window.__rsCasing(!!(d && d.is_dark));   // dynamic road casing
    var pop = document.getElementById('{{ this.cid }}');
    if(pop) pop.querySelectorAll('.rs-card').forEach(
      function(c){ c.classList.toggle('active', c.dataset.key===key); });
  }

  var Ctl = L.Control.extend({
    options:{position:'{{ this.position }}'},
    onAdd:function(){
      var wrap = L.DomUtil.create('div','rs-ctrl');
      var fab = L.DomUtil.create('button','rs-fab',wrap);
      fab.title='Base layer'; fab.innerHTML={{ this.icon|tojson }};
      var pop = L.DomUtil.create('div','rs-pop hidden',wrap); pop.id='{{ this.cid }}';
      var grid = L.DomUtil.create('div','rs-grid',pop);
      defs.forEach(function(d){
        var card = L.DomUtil.create('div','rs-card',grid); card.dataset.key=d.key;
        card.innerHTML =
          '<div class="rs-prev" style="background:'+d.bg+'">'+
          '<svg viewBox="0 0 80 40" preserveAspectRatio="none">'+
          '<path d="M0 22 Q20 12 40 22 T80 18" stroke="'+d.roads[0]+
            '" stroke-width="3" fill="none" stroke-linecap="round"/>'+
          '<path d="M16 0 L30 40" stroke="'+d.roads[1]+
            '" stroke-width="2.2" fill="none" stroke-linecap="round"/>'+
          '<path d="M52 4 L66 40" stroke="'+d.roads[2]+
            '" stroke-width="2" fill="none" stroke-linecap="round"/>'+
          '</svg></div><div class="rs-label">'+d.label+'</div>';
        card.onclick = function(){
          switchTo(d.key); pop.classList.add('hidden'); fab.classList.remove('active'); };
      });
      fab.onclick = function(e){ e.stopPropagation();
        var hidden = pop.classList.toggle('hidden'); fab.classList.toggle('active', !hidden); };
      document.addEventListener('click', function(e){
        if(!wrap.contains(e.target)){
          pop.classList.add('hidden'); fab.classList.remove('active'); } });
      L.DomEvent.disableClickPropagation(wrap);
      L.DomEvent.disableScrollPropagation(wrap);
      return wrap;
    }
  });
  map.addControl(new Ctl());
  switchTo('{{ this.default_key }}');
})();
{% endmacro %}
""")


class BaseLayerSwitcher(MacroElement):
    """Layers FAB + thumbnail-card popover; switches base tiles and toggles the satellite
    filter + dynamic road casing (via ``window.__rsCasing``)."""

    def __init__(self, keys, default_key, position="bottomright"):
        super().__init__()
        self._name = "BaseLayerSwitcher"
        self.position = position
        self.default_key = default_key
        self.icon = _ICON
        self.cid = f"rs-pop-{id(self)}"
        self.defs = []
        for k in keys:
            b = get_basemap(k)
            self.defs.append({
                "key": b.key, "label": b.label, "url": b.url, "attr": b.attr,
                "sat": b.satellite, "is_dark": b.is_dark, "bg": b.bg,
                "roads": list(b.preview), "sub": b.subdomains,
            })
        self._template = _TEMPLATE

"""Render styled edges to a self-contained **MapLibre** (vector) HTML map.

Unlike the folium/lonboard backends (fixed-pixel widths), this backend uses MapLibre's native
zoom expressions, matching the openstreetmap-carto look:

  * **per-zoom road widths** — a smooth ``interpolate(zoom)`` curve per width-group (the
    osm_carto width table), so roads widen as you zoom in instead of being a fixed pixel weight;
  * **two-way lanes** — a pixel-proportional ``line-offset`` fans each two-way street's two
    directed edges into parallel lanes. Because the two directed edges have *reversed* geometry,
    offsetting both to the same side puts them on opposite sides. The offset is a fraction of the
    *pixel* width, so the overlap is constant at every zoom (no gap, no merge).

Road *colours* come from roadstyle's palette/theme (the resolved per-edge ``__rs_fill`` /
``__rs_casing``). Data is **inlined** into the HTML, so the file opens with no web server (MapLibre
GL JS is loaded from CDN). Returns a :class:`WebMap` with ``.save(path)`` and notebook display.
"""
from __future__ import annotations

import collections
import html as _html
import json
import os

from .basemaps import DEFAULT_SWITCHER, get_basemap
from .stylers import bake_props, build_styler
from .themes import get_theme

_VENDOR = os.path.join(os.path.dirname(__file__), "vendor")


def _asset(fname):
    """Read a vendored front-end asset (the MapLibre js/css) to inline into the saved HTML, so the
    page needs no CDN — it opens offline, straight from disk, with no web server."""
    with open(os.path.join(_VENDOR, fname), encoding="utf-8") as fh:
        return fh.read()

# --- openstreetmap-carto width model (px by zoom, per width-group) -----------------------------
WIDTH = {
    "major":         {8: 0.8, 10: 1.3, 12: 3.5, 13: 6, 14: 8, 15: 10, 16: 13, 17: 17, 18: 22},
    "primary":       {8: 0.7, 10: 1.2, 12: 3.5, 13: 5, 14: 7, 15: 9, 16: 12, 17: 15, 18: 19},
    "secondary":     {10: 0.8, 12: 2.5, 13: 4, 14: 6, 15: 8, 16: 10, 17: 13, 18: 17},
    "tertiary":      {12: 2, 13: 3, 14: 4.5, 15: 6, 16: 8, 17: 11, 18: 14},
    "residential":   {12: 0.5, 13: 1.5, 14: 2.5, 15: 4, 16: 6, 17: 9, 18: 13},
    "living_street": {13: 2, 14: 2.5, 15: 4, 16: 6, 17: 9, 18: 13},
    "service":       {13: 0.8, 14: 1.2, 15: 2, 16: 2.8, 17: 4, 18: 5},
    "pedestrian":    {13: 2, 14: 3, 15: 4, 16: 6, 17: 9, 18: 13},
    "path":          {12: 0.4, 13: 0.6, 14: 0.8, 15: 1, 16: 1.4, 17: 2, 18: 2.6, 19: 3},
}
HI_RATE = {"major": 2.0, "primary": 2.0, "secondary": 2.0, "tertiary": 1.95, "residential": 1.9,
           "living_street": 1.9, "service": 1.9, "pedestrian": 1.85, "path": 1.3}
CASING_RATIO = {"major": 1.17, "primary": 1.18, "secondary": 1.19, "tertiary": 1.21,
                "residential": 1.24, "living_street": 1.24, "service": 1.27, "pedestrian": 1.21,
                "path": 1.0}
# highway class -> width-group
ROAD_GROUP = {
    "motorway": "major", "trunk": "major", "primary": "primary", "secondary": "secondary",
    "tertiary": "tertiary", "unclassified": "residential", "residential": "residential",
    "road": "residential", "busway": "residential", "raceway": "tertiary",
    "living_street": "living_street", "service": "service", "pedestrian": "pedestrian",
    "footway": "path", "path": "path", "cycleway": "path", "steps": "path", "bridleway": "path",
    "track": "path", "corridor": "path", "construction": "path",
}
_LINKS = ["motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"]
_CLASSES = list(ROAD_GROUP) + _LINKS
_ZSTOPS = [12, 13, 14, 15, 16, 17, 18, 19, 20]

# draw priority (OSM z_order): higher = on top, so a motorway draws over a residential at a junction
ROAD_Z = {
    "motorway": 9, "trunk": 8, "primary": 7, "secondary": 6, "tertiary": 5,
    "unclassified": 4, "residential": 4, "road": 4, "busway": 4, "raceway": 5,
    "living_street": 3, "service": 3, "pedestrian": 2,
    "footway": 1, "path": 1, "cycleway": 1, "steps": 1, "bridleway": 1, "track": 1,
    "corridor": 1, "construction": 0,
}


def _sort_key(col):
    """line-sort-key: grade (tunnel/bridge) dominates, then road class.

    ``lvl*1000`` puts every tunnel (lvl -1) below every surface road and every bridge (lvl +1)
    above, so a tunnel passing *under* a street no longer looks connected to it; within a grade,
    higher-class roads still draw on top (links just under their through road)."""
    m = ["match", ["get", col]]
    for c in _CLASSES:
        b, lk = _base(c)
        m += [c, ROAD_Z.get(b, 4) - (0.5 if lk else 0)]
    m.append(4)
    return ["+", ["*", ["coalesce", ["get", "lvl"], 0], 1000], m]


def _base(c):
    return (c[:-5], True) if c.endswith("_link") else (c, False)


def _gwidth(t, hi, z):
    ks = sorted(t)
    if z <= ks[0]:
        return t[ks[0]]
    if z >= ks[-1]:
        return t[ks[-1]] * (hi ** (z - ks[-1]))
    for i in range(len(ks) - 1):
        if z <= ks[i + 1]:
            f = (z - ks[i]) / (ks[i + 1] - ks[i])
            return t[ks[i]] + (t[ks[i + 1]] - t[ks[i]]) * f
    return t[ks[-1]]


def _width_expr(col, casing=False, split_zoom=15, split_frac=0.6, scale=1.0):
    """interpolate(zoom) of match(class -> width). Two-way lanes shrink to ``split_frac`` of the
    full width once the directions have fanned apart (ramped from full at split_zoom to split_frac
    at split_zoom+2), so the two lanes together read as one road of the right width.

    ``scale`` multiplies every output width (e.g. 1.25 for a heavier bridge casing). It scales the
    per-stop *values*, not the whole expression, because MapLibre forbids a ``zoom`` interpolate
    nested inside ``["*", ...]`` — the zoom input must stay top-level."""
    e = ["interpolate", ["linear"], ["zoom"]]
    for z in _ZSTOPS:
        m = ["match", ["get", col]]
        for c in _CLASSES:
            b, lk = _base(c)
            g = ROAD_GROUP.get(b, "residential")
            w = _gwidth(WIDTH[g], HI_RATE[g], z) * (CASING_RATIO[g] if casing else 1) * scale
            if lk:
                w *= 0.6
            m += [c, round(w, 2)]
        dw = _gwidth(WIDTH["residential"], HI_RATE["residential"], z) * (CASING_RATIO["residential"] if casing else 1) * scale
        m.append(round(dw, 2))
        f = 1.0 if z <= split_zoom else (split_frac if z >= split_zoom + 2 else 1.0 - (1 - split_frac) * (z - split_zoom) / 2.0)
        if f < 1.0:
            m = ["*", m, ["case", ["to-boolean", ["get", "twoway"]], round(f, 3), 1]]
        e += [z, m]
    return e


def _offset_expr(col, offset_frac=0.28, offset_zoom=15):
    """line-offset (px) = offset_frac * the road's pixel width, for two-way edges (0 for one-way),
    ramped in from offset_zoom. Pixel-proportional -> constant overlap at every zoom."""
    e = ["interpolate", ["linear"], ["zoom"]]
    for z in _ZSTOPS:
        ramp = 0.0 if z <= offset_zoom else (1.0 if z >= offset_zoom + 2 else (z - offset_zoom) / 2.0)
        m = ["match", ["get", col]]
        for c in _CLASSES:
            b, lk = _base(c)
            g = ROAD_GROUP.get(b, "residential")
            w = _gwidth(WIDTH[g], HI_RATE[g], z) * (0.6 if lk else 1)
            m += [c, round(w * offset_frac * ramp, 3)]
        dw = _gwidth(WIDTH["residential"], HI_RATE["residential"], z)
        m.append(round(dw * offset_frac * ramp, 3))
        e += [z, ["case", ["to-boolean", ["get", "twoway"]], m, 0]]
    return e


def _mark_twoway(geo):
    """Flag each edge that has a reverse-geometry twin (i.e. a two-way street's other direction),
    so the style fans those into two lanes. Endpoints only — robust to vertex order."""
    cnt, keys = collections.Counter(), []
    for ft in geo["features"]:
        g = ft.get("geometry") or {}
        c = g.get("coordinates") or []
        if g.get("type") == "LineString" and len(c) >= 2:
            a = (round(c[0][0], 6), round(c[0][1], 6))
            z = (round(c[-1][0], 6), round(c[-1][1], 6))
            k = (a, z) if a <= z else (z, a)
        else:
            k = id(ft)
        keys.append(k)
        cnt[k] += 1
    for ft, k in zip(geo["features"], keys):
        ft.setdefault("properties", {})["twoway"] = cnt[k] >= 2


def _truthy(v):
    return v not in (None, "", "no", "false", "0", 0, False)


def _mark_lvl(geo, tunnel_col, bridge_col, layer_col):
    """Elevation per edge: bridge -> +1 (drawn on top), tunnel -> -1 (drawn underneath), else the
    sign of the OSM `layer` tag, else 0. Lets the sort key keep grade-separated roads from looking
    connected. Defaults to 0 when the columns aren't present (no tunnel/bridge info)."""
    for ft in geo["features"]:
        p = ft.setdefault("properties", {})
        if _truthy(p.get(bridge_col)):
            lvl = 1
        elif _truthy(p.get(tunnel_col)):
            lvl = -1
        else:
            try:
                l = int(float(p.get(layer_col)))
                lvl = 1 if l > 0 else (-1 if l < 0 else 0)
            except (TypeError, ValueError):
                lvl = 0
        p["lvl"] = lvl


def _boundary_fc(boundary):
    """Normalise a boundary overlay into a GeoJSON FeatureCollection in EPSG:4326. Accepts a shapely
    geometry, a GeoSeries / GeoDataFrame (reprojected to 4326), or a GeoJSON mapping (geometry,
    Feature, or FeatureCollection — assumed already lon/lat)."""
    if hasattr(boundary, "to_crs"):                          # GeoSeries / GeoDataFrame
        try:
            boundary = boundary.to_crs(4326)
        except Exception:
            pass
    gj = boundary.__geo_interface__ if hasattr(boundary, "__geo_interface__") else boundary
    t = (gj or {}).get("type")
    if t == "FeatureCollection":
        return gj
    if t == "Feature":
        return {"type": "FeatureCollection", "features": [gj]}
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": gj}]}


def _tiles(bm):
    """Leaflet {s}/{r} tile template -> a MapLibre raster `tiles` list (expand subdomains, drop @2x)."""
    if "{s}" in bm.url:
        return [bm.url.replace("{s}", s).replace("{r}", "") for s in (bm.subdomains or "a")]
    return [bm.url.replace("{r}", "")]


def _basemap_style(bm):
    """A minimal MapLibre style wrapping a raster base map."""
    return {"version": 8, "sources": {"bm": {"type": "raster", "tiles": _tiles(bm), "tileSize": 256,
                                             "attribution": bm.attr}},
            "layers": [{"id": "basemap", "type": "raster", "source": "bm"}]}


_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"/>
<title>__TITLE__</title>
<meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no"/>
<style>__MAPLIBRE_CSS__</style>
<script>__MAPLIBRE_JS__</script>
<style>html,body{margin:0;height:100%}#map{position:absolute;inset:0}
.bm-ctrl{position:absolute;top:10px;left:10px;z-index:2;background:#fff;border-radius:5px;
box-shadow:0 1px 4px rgba(0,0,0,.3);padding:4px 7px;font:13px system-ui,sans-serif}
.bm-ctrl select{font:inherit;border:0;background:transparent;cursor:pointer;outline:none}
.flt-ctrl{position:absolute;top:48px;left:10px;z-index:2;background:#fff;border-radius:5px;
box-shadow:0 1px 4px rgba(0,0,0,.3);font:13px system-ui,sans-serif;max-height:70%;overflow:auto}
.flt-ctrl .flt-hd{padding:5px 9px;cursor:pointer;font-weight:600;user-select:none}
.flt-ctrl .flt-body{padding:0 9px 7px;display:flex;flex-direction:column;gap:2px}
.flt-ctrl.collapsed .flt-body{display:none}
.flt-ctrl label{cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:4px}
</style></head><body>
<div id="map"></div><script>
const style = __STYLE__, BASEMAPS = __BASEMAPS__;
const map = new maplibregl.Map({container:"map", style:style, center:__CENTER__, zoom:13,
  attributionControl:{compact:true}});
map.addControl(new maplibregl.NavigationControl());
// base-layer switcher (swaps the raster source's tiles; the road layers stay put)
if(BASEMAPS.length > 1){
  const sel = document.createElement("select");
  BASEMAPS.forEach((b,i)=>{ const o=document.createElement("option"); o.value=i; o.textContent=b.label; sel.appendChild(o); });
  sel.onchange = ()=>{ const s=map.getSource("bm"); if(s) s.setTiles(BASEMAPS[sel.value].tiles); };
  const w=document.createElement("div"); w.className="bm-ctrl"; w.appendChild(sel); document.body.appendChild(w);
}
// road-class filter panel (collapsible): checkboxes hide/show each class across every road layer
const FILTER = __FILTER__;
if(FILTER.on){
  const box=document.createElement("div"); box.className="flt-ctrl";
  const hd=document.createElement("div"); hd.className="flt-hd"; hd.textContent="Roads ▾";
  const body=document.createElement("div"); body.className="flt-body";
  hd.onclick=()=>{ const c=box.classList.toggle("collapsed"); hd.textContent="Roads "+(c?"▸":"▾"); };
  box.appendChild(hd); box.appendChild(body);
  const cbs={};
  const baseF={};
  const roadIds=()=>map.getStyle().layers.filter(l=>l.id.indexOf("roads")===0).map(l=>l.id);
  function applyFilter(){
    const hidden=FILTER.classes.filter(c=>!cbs[c].checked);
    roadIds().forEach(id=>{
      let f=baseF[id]||null;
      if(hidden.length){ const cf=["!",["in",["get",FILTER.col],["literal",hidden]]]; f=f?["all",f,cf]:cf; }
      try{ map.setFilter(id,f); }catch(e){}
    });
  }
  FILTER.classes.forEach(c=>{
    const lab=document.createElement("label");
    const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=true; cb.onchange=applyFilter;
    cbs[c]=cb; lab.appendChild(cb); lab.appendChild(document.createTextNode(" "+c)); body.appendChild(lab);
  });
  document.body.appendChild(box);
  map.on("load",()=>{ roadIds().forEach(id=>{ baseF[id]=map.getFilter(id)||null; }); });
}
// oneway direction-arrow icon (openstreetmap-carto)
function addArrow(){
  if(map.hasImage("oneway")) return;
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="24" height="10" viewBox="0 0 12 5">'
    +'<path d="M 0,2 7,2 7,0 12,2.5 7,5 7,3 0,3 z" fill="#5b5b5b"/></svg>';
  const img=new Image(24,10);
  img.onload=()=>{ if(!map.hasImage("oneway")) map.addImage("oneway",img,{pixelRatio:2}); };
  img.src="data:image/svg+xml;base64,"+btoa(svg);
}
map.on("load", addArrow);
map.on("styleimagemissing", e=>{ if(e.id==="oneway") addArrow(); });
// hover + click-to-select + info popup (feature-state, tolerance box, throttled to one query/frame)
const HIT = 4;
function box(p){ return [[p.x-HIT,p.y-HIT],[p.x+HIT,p.y+HIT]]; }
function pick(p){ const l = map.queryRenderedFeatures(box(p), {layers:["roads-fill","roads-tunnel-fill","roads-bridge-fill"]}); return l.length ? l[0] : null; }
function setS(id, st){ if(id!=null) map.setFeatureState({source:"roads", id:id}, st); }
let _hov=null, _pt=null, _raf=0;
function hoverFrame(){ _raf=0; if(!_pt) return;
  const f = pick(_pt); map.getCanvas().style.cursor = f ? "pointer" : "";
  const id = f ? f.id : null;
  if(id !== _hov){ setS(_hov,{hover:false}); _hov=id; setS(_hov,{hover:true}); }
}
map.on("mousemove", e=>{ _pt=e.point; if(!_raf) _raf=requestAnimationFrame(hoverFrame); });
map.on("mouseout", ()=>{ _pt=null; if(_raf){cancelAnimationFrame(_raf);_raf=0;} setS(_hov,{hover:false}); _hov=null; });
let _sel=null;
map.on("click", e=>{ const f = pick(e.point);
  if(!f){ if(_sel!=null){ setS(_sel,{select:false}); _sel=null; } return; }   // click empty -> deselect (restore colour)
  if(_sel!=null) setS(_sel,{select:false}); _sel=f.id; setS(_sel,{select:true});
  const p = f.properties||{}, r = ["<b>"+(p.name||"(unnamed)")+"</b>"];
  for(const k in p){ if(k[0]==="_"||k==="twoway"||k==="name") continue;
    if(p[k]!=null && p[k]!=="") r.push(k+": "+p[k]); }
  new maplibregl.Popup({closeButton:true, maxWidth:"260px"}).setLngLat(e.lngLat).setHTML(r.join("<br>")).addTo(map);
});
map.on("load", ()=>{ try{ map.fitBounds(__BOUNDS__, {padding:30, duration:0}); }catch(e){} });
window.map = map;
</script></body></html>"""


class WebMap:
    """A self-contained MapLibre HTML map. ``.save(path)`` writes the file; displays inline in a
    notebook (as an iframe). No web server needed — the data is inlined."""

    def __init__(self, html: str):
        self.html = html

    def save(self, path):
        from pathlib import Path
        Path(path).write_text(self.html, encoding="utf-8")
        return path

    def _repr_html_(self):
        return (f'<iframe srcdoc="{_html.escape(self.html, quote=True)}" '
                'style="width:100%;height:640px;border:0;border-radius:6px"></iframe>')


def render(gdf, palette: str = "highsat", theme: str = "dark", highway_col: str = "highway",
           styler=None, basemap=None, basemaps=None, name: str = "roadstyle",
           offset_frac: float = 0.28, width_frac: float = 0.6, offset_zoom: int = 15,
           tunnel_col: str = "tunnel", bridge_col: str = "bridge", layer_col: str = "layer",
           arrows: bool = True, labels: bool = True, filter_control: bool = True,
           basemap_switcher: bool = True, boundary=None, **_ignore):
    """Build a self-contained MapLibre map of the styled edges.

    If the data carries ``tunnel`` / ``bridge`` / ``layer`` columns (named via ``tunnel_col`` /
    ``bridge_col`` / ``layer_col``), grade-separated roads are ordered by elevation so tunnels draw
    underneath and bridges on top — otherwise every edge is treated as ground level.

    UI toggles (all on by default):
      - ``arrows`` — one-way direction chevrons along each one-way edge;
      - ``labels`` — curved street-name labels (from the ``name`` column);
      - ``filter_control`` — a collapsible checkbox panel to show/hide each road class;
      - ``basemap_switcher`` — the in-map base-layer dropdown (uses ``basemap`` / ``basemaps``).

    ``boundary`` (optional) overlays a dashed outline — a shapely geometry, a GeoSeries /
    GeoDataFrame, or a GeoJSON mapping (assumed lon/lat) — e.g. the area the network was clipped
    to."""
    th = get_theme(theme)
    g = gdf.to_crs(4326)
    if styler is None:
        styler = build_styler(palette=palette, highway_col=highway_col)
    rf = styler.resolve_frame(g, theme)
    geo = bake_props(json.loads(g.to_json()), rf, th.casing == "dark")   # per-edge __rs_fill/__rs_casing
    _mark_twoway(geo)
    _mark_lvl(geo, tunnel_col, bridge_col, layer_col)

    # active base map + the set offered to the in-map switcher (active shown first)
    active = basemap or th.default_basemap
    bkeys = list(basemaps) if basemaps else list(DEFAULT_SWITCHER)
    if isinstance(active, str):
        bkeys = [active] + [k for k in bkeys if k != active]
    bms = [{"label": get_basemap(k).label, "tiles": _tiles(get_basemap(k))} for k in bkeys]
    if not basemap_switcher:
        bms = bms[:1]                                     # one entry -> the JS hides the dropdown
    style = _basemap_style(get_basemap(active))
    style["sources"]["roads"] = {"type": "geojson", "data": geo, "generateId": True}
    lay = {"line-cap": "round", "line-join": "round", "line-sort-key": _sort_key(highway_col)}
    tlay = {**lay, "line-cap": "butt"}                    # butt cap -> clean dash ticks on tunnel casing
    blay = {**lay, "line-cap": "butt"}                    # butt cap -> square bridge deck ends
    off = _offset_expr(highway_col, offset_frac, offset_zoom)
    sw = dict(split_zoom=offset_zoom, split_frac=width_frac)
    surface = ["==", ["coalesce", ["get", "lvl"], 0], 0]  # lvl == 0
    tunnel = ["<", ["coalesce", ["get", "lvl"], 0], 0]    # lvl == -1
    bridge = [">", ["coalesce", ["get", "lvl"], 0], 0]    # lvl == +1
    cw = _width_expr(highway_col, casing=True, **sw)      # casing width expr (reused across layers)
    fw = _width_expr(highway_col, **sw)                   # fill width expr
    bcw = _width_expr(highway_col, casing=True, scale=1.25, **sw)   # heavier bridge casing ("wings")
    style["layers"] += [
        # Tunnels first, so the surface roads above paint over them at crossings. The dashed casing +
        # faded fill make a tunnel read as "underground" even where nothing crosses it (osm-carto look).
        {"id": "roads-tunnel-casing", "type": "line", "source": "roads", "layout": tlay,
         "filter": tunnel,
         "paint": {"line-color": ["coalesce", ["get", "__rs_casing"], "#000000"],
                   "line-width": cw, "line-offset": off, "line-dasharray": [2, 2]}},
        {"id": "roads-tunnel-fill", "type": "line", "source": "roads", "layout": lay,
         "filter": tunnel,
         "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                   "line-width": fw, "line-offset": off, "line-opacity": 0.72}},
        {"id": "roads-casing", "type": "line", "source": "roads", "layout": lay, "filter": surface,
         "paint": {"line-color": ["coalesce", ["get", "__rs_casing"], "#000000"],
                   "line-width": cw, "line-offset": off}},
        {"id": "roads-fill", "type": "line", "source": "roads", "layout": lay, "filter": surface,
         "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                   "line-width": fw, "line-offset": off}},
        # Bridges last (on top): a heavier, square-capped casing reads as a deck spanning what's below.
        {"id": "roads-bridge-casing", "type": "line", "source": "roads", "layout": blay,
         "filter": bridge,
         "paint": {"line-color": ["coalesce", ["get", "__rs_casing"], "#000000"],
                   "line-width": bcw, "line-offset": off}},
        {"id": "roads-bridge-fill", "type": "line", "source": "roads", "layout": lay, "filter": bridge,
         "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                   "line-width": fw, "line-offset": off}},
        # hover/select highlight, driven by feature-state set from the viewer (GPU recolour, no relayout)
        {"id": "roads-highlight", "type": "line", "source": "roads", "layout": lay,
         "paint": {
             "line-color": ["case", ["boolean", ["feature-state", "select"], False], "#ff6600", "#ffd000"],
             "line-opacity": ["case", ["any", ["boolean", ["feature-state", "hover"], False],
                                       ["boolean", ["feature-state", "select"], False]], 0.85, 0],
             "line-width": fw, "line-offset": off}},
    ]
    # oneway direction arrows (on edges with no reverse twin) + line-placed street names, on top
    if arrows:
        style["layers"].append(
            {"id": "roads-arrows", "type": "symbol", "source": "roads", "minzoom": 15,
             "filter": ["!", ["to-boolean", ["get", "twoway"]]],   # one-way edge = no reverse twin
             "layout": {"symbol-placement": "line", "icon-image": "oneway", "symbol-spacing": 120,
                        "icon-rotation-alignment": "map", "icon-allow-overlap": True,
                        "icon-ignore-placement": True,
                        "icon-size": ["interpolate", ["linear"], ["zoom"], 15, 0.5, 19, 1.0]},
             "paint": {"icon-opacity": 0.7}})
    if labels:
        style["glyphs"] = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"
        style["layers"].append(
            {"id": "roads-labels", "type": "symbol", "source": "roads", "minzoom": 14,
             "filter": ["to-boolean", ["get", "name"]],
             "layout": {"symbol-placement": "line", "text-field": ["get", "name"],
                        "text-font": ["Noto Sans Regular"], "symbol-spacing": 250,
                        "text-size": ["interpolate", ["linear"], ["zoom"], 14, 10, 18, 14],
                        "text-max-angle": 40, "text-padding": 2},
             "paint": {"text-color": "#33332e", "text-halo-color": "#ffffff", "text-halo-width": 1.2}})

    # clip/area boundary outline, drawn on top of the roads (a dashed line tracing the polygon rings)
    if boundary is not None:
        style["sources"]["boundary"] = {"type": "geojson", "data": _boundary_fc(boundary)}
        style["layers"].append(
            {"id": "boundary", "type": "line", "source": "boundary",
             "layout": {"line-cap": "round", "line-join": "round"},
             "paint": {"line-color": "#6a0dad", "line-width": 2.5, "line-opacity": 0.9,
                       "line-dasharray": [3, 2]}})

    # road-class filter panel: the distinct classes present, most important first
    classes, seen = [], set()
    for ft in geo["features"]:
        c = ft.get("properties", {}).get(highway_col)
        if c and c not in seen:
            seen.add(c)
            classes.append(c)
    classes.sort(key=lambda c: (-ROAD_Z.get(_base(c)[0], 4), c))
    flt = {"on": bool(filter_control and classes), "col": highway_col, "classes": classes}

    minx, miny, maxx, maxy = (float(v) for v in g.total_bounds)
    html = (_HTML.replace("__TITLE__", _html.escape(name))
            .replace("__STYLE__", json.dumps(style))
            .replace("__BASEMAPS__", json.dumps(bms))
            .replace("__FILTER__", json.dumps(flt))
            .replace("__CENTER__", json.dumps([(minx + maxx) / 2, (miny + maxy) / 2]))
            .replace("__BOUNDS__", json.dumps([[minx, miny], [maxx, maxy]]))
            # inject MapLibre last so its 800 KB blob isn't scanned for the other placeholders
            .replace("__MAPLIBRE_CSS__", _asset("maplibre-gl.css"))
            .replace("__MAPLIBRE_JS__", _asset("maplibre-gl.js").replace("</script>", "<\\/script>")))
    return WebMap(html)

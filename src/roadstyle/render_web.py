"""Render styled edges to a self-contained **MapLibre** (vector) HTML map.

Unlike the folium/lonboard backends (fixed-pixel widths), this backend uses MapLibre's native
zoom expressions, matching the openstreetmap-carto look:

  * **per-zoom road widths** — a smooth ``interpolate(zoom)`` curve per width-group (the
    osm_carto width table), so roads widen as you zoom in instead of being a fixed pixel weight;
  * **two-way lanes** — a pixel-proportional ``line-offset`` fans each two-way street's two
    directed edges into parallel lanes. Because the two directed edges have *reversed* geometry,
    offsetting both to the same side puts them on opposite sides. The offset is a fraction of the
    *pixel* width, so the overlap is constant at every zoom (no gap, no merge).

Road *colours* come from roadstyle's palette (the resolved per-edge ``__rs_fill`` /
``__rs_casing``). Data is **inlined** into the HTML, so the file opens with no web server (MapLibre
GL JS is loaded from CDN). Returns a :class:`WebMap` with ``.save(path)`` and notebook display.
"""
from __future__ import annotations

import collections
import html as _html
import json
import math
import os
from collections.abc import Mapping

from . import _settings
from .basemaps import DEFAULT_SWITCHER, get_basemap
from .config import DEFAULT as CONFIG
from .overlays import Overlay, detect_kind, to_fc
from .stylers import bake_color_options, bake_props, build_styler, option_styler

_VENDOR = os.path.join(os.path.dirname(__file__), "vendor")


def _asset(fname):
    """Read a vendored front-end asset (the MapLibre js/css) to inline into the saved HTML, so the
    page needs no CDN — it opens offline, straight from disk, with no web server."""
    with open(os.path.join(_VENDOR, fname), encoding="utf-8") as fh:
        return fh.read()

# --- openstreetmap-carto road model — loaded from data/defaults.json "roads" (+ any user
# roadstyle.json override), like every other styling table. Edit the JSON, not this file.
def _load_road_model() -> None:
    """(Re)build the module road tables from :func:`_settings.roads`.

    Runs at import and again from :func:`roadstyle.use_settings` after a programmatic override —
    every expression builder below reads these module globals at call time, so a rebuild is all a
    new setting set needs."""
    global WIDTH, HI_RATE, CASING_RATIO, ROAD_GROUP, _LINKS, _CLASSES, _ZSTOPS, ROAD_Z
    r = _settings.roads()
    WIDTH = {g: {int(z): w for z, w in t.items()} for g, t in r["width"].items()}   # px by zoom, per group
    HI_RATE = dict(r["width_zoom_rate"])       # per-group growth rate per zoom past the last stop
    CASING_RATIO = dict(r["casing_ratio"])     # casing width = fill width * ratio, per group
    ROAD_GROUP = dict(r["group"])              # highway class -> width-group
    _LINKS = list(r["links"])
    _CLASSES = list(ROAD_GROUP) + _LINKS
    _ZSTOPS = list(r["zoom_stops"])
    ROAD_Z = dict(r["z_order"])                # draw priority: higher = on top at a junction


_load_road_model()


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
    """Flag each edge that has a reverse twin (i.e. a two-way street's other direction), so the
    style fans those into two lanes and drops the one-way arrows. The match is DIRECTED — the twin
    must run end->start. Two same-direction edges between one node pair (a street split into
    parallel one-way carriageways) are siblings, not a pair: each keeps its arrows."""
    cnt, keys = collections.Counter(), []
    for ft in geo["features"]:
        g = ft.get("geometry") or {}
        c = g.get("coordinates") or []
        if g.get("type") == "LineString" and len(c) >= 2:
            a = (round(c[0][0], 6), round(c[0][1], 6))
            z = (round(c[-1][0], 6), round(c[-1][1], 6))
            k = (a, z)
        else:
            k = (id(ft), None)
        keys.append(k)
        cnt[k] += 1
    for ft, k in zip(geo["features"], keys):
        rev = (k[1], k[0])
        n = cnt.get(rev, 0)
        # a loop edge (start == end) is its own reverse key; it needs a second feature to pair up
        ft.setdefault("properties", {})["twoway"] = n >= 2 if rev == k else n >= 1


def _annotation_slots(geo, slot_m):
    """Divide every road chain into equal ``slot_m``-metre slots — the annotation plan.

    Chains walk same-name, same-grade, same-directionness edges through degree-2 nodes (a two-way
    street's reverse twin is skipped — its twin carries the geometry). Slots are indexed 0..
    along the chain; street names take the even slots and one-way arrows the odd ones, so the two
    alternate along the road and can never stack. Symbol zoom ramps + collision culling handle
    density per zoom automatically. Unnamed roads leave their name slots empty. Returns a
    FeatureCollection of slot pieces: {slot, name, highway, oneway}.
    """
    from shapely.geometry import LineString
    from shapely.ops import substring

    reps = []                                    # (start, end, coords, props), twins collapsed
    for ft in geo["features"]:
        g, p = ft.get("geometry") or {}, ft.get("properties", {})
        c = g.get("coordinates") or []
        if g.get("type") != "LineString" or len(c) < 2:
            continue
        a = (round(c[0][0], 6), round(c[0][1], 6))
        z = (round(c[-1][0], 6), round(c[-1][1], 6))
        if p.get("twoway") and (z, a) < (a, z):
            continue
        reps.append((a, z, c, p))

    groups = collections.defaultdict(list)       # (name, lvl, oneway) -> edge list
    for e in reps:
        p = e[3]
        groups[(p.get("name") or None, p.get("lvl", 0), 0 if p.get("twoway") else 1)].append(e)

    feats = []
    for (name, lvl, oneway), edges in groups.items():
        n = len(edges)
        used = [False] * n
        at = collections.defaultdict(list)       # node -> [edge index] (either endpoint)
        for i, (a, z, _, _) in enumerate(edges):
            at[a].append(i)
            at[z].append(i)

        def walk(start):
            """Greedy chain from edge `start` through degree-2 nodes. Two-way segments flip as
            needed for continuity; one-way chains only extend through DIRECTED continuations, so
            the chain (and its arrows) never reverses mid-way."""
            a, z, c, _ = edges[start]
            used[start] = True
            chain = list(c)
            for prepend in (False, True):
                node = a if prepend else z
                while True:
                    cand = [j for j in at[node] if not used[j]]
                    if len(at[node]) != 2 or len(cand) != 1:
                        break
                    j = cand[0]
                    ja, jz, jc, _ = edges[j]
                    if prepend:                  # need a segment ENDING at the chain head
                        if jz == node:
                            seg, nxt = jc, ja
                        elif not oneway:
                            seg, nxt = jc[::-1], jz
                        else:
                            break                # opposing one-way: not a continuation
                        used[j] = True
                        chain = seg[:-1] + chain
                    else:                        # need a segment STARTING at the chain tail
                        if ja == node:
                            seg, nxt = jc, jz
                        elif not oneway:
                            seg, nxt = jc[::-1], ja
                        else:
                            break
                        used[j] = True
                        chain = chain + seg[1:]
                    node = nxt
            return chain

        chains = [walk(i) for i in range(n) if not used[i]]
        hw = collections.Counter(e[3].get("highway") for e in edges).most_common(1)[0][0]
        for chain in chains:
            lon0, lat0 = chain[0]
            kx = 111320.0 * math.cos(math.radians(lat0))
            local = LineString([((x - lon0) * kx, (y - lat0) * 111320.0) for x, y in chain])
            total = local.length
            pieces = max(1, int(total // slot_m) + (1 if total % slot_m > slot_m * 0.3 else 0))
            for i in range(pieces):
                part = substring(local, i * slot_m, min((i + 1) * slot_m, total))
                if part.geom_type != "LineString" or part.length < slot_m * 0.2:
                    continue
                coords = [[round(x / kx + lon0, 6), round(y / 111320.0 + lat0, 6)]
                          for x, y in part.coords]
                feats.append({"type": "Feature",
                              "properties": {"slot": i, "name": name,
                                             "highway": hw, "oneway": oneway},
                              "geometry": {"type": "LineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats}


def _bridge_decks(geo, dk):
    """Bridge chains (lvl +1) as RAMPED deck ribbons for the 3D view's extrusions.

    Connected bridge edges are walked into chains, sliced every ``step_m`` metres, and each slice
    is buffered into a polygon carrying its own ``base``/``height``: 0 at the chain ends, rising
    over ``ramp_m`` to ``base_m`` mid-span — the deck takes off from the connecting ground road
    instead of floating disconnected above it. Slices inherit the fills of the edge under their
    midpoint (colour options included) plus highway/name; a two-way bridge's reverse twin is
    skipped so decks don't double-stack.
    """
    from shapely.geometry import LineString
    from shapely.ops import substring

    reps = []
    for ft in geo["features"]:
        g, p = ft.get("geometry") or {}, ft.get("properties", {})
        c = g.get("coordinates") or []
        if p.get("lvl") != 1 or g.get("type") != "LineString" or len(c) < 2:
            continue
        a = (round(c[0][0], 6), round(c[0][1], 6))
        z = (round(c[-1][0], 6), round(c[-1][1], 6))
        if p.get("twoway") and (z, a) < (a, z):
            continue
        reps.append((a, z, c, p))

    n = len(reps)
    used = [False] * n
    at = collections.defaultdict(list)
    for i, (a, z, _, _) in enumerate(reps):
        at[a].append(i)
        at[z].append(i)

    def walk(start_i):
        """Undirected chain of connected bridge edges through degree-2 nodes.
        Returns (coords, spans) where spans = [(end_index_in_coords, props), ...]."""
        a, z, c, p = reps[start_i]
        used[start_i] = True
        chain = list(c)
        spans = [[len(chain) - 1, p]]
        for prepend in (False, True):
            node = a if prepend else z
            while True:
                cand = [j for j in at[node] if not used[j]]
                if len(at[node]) != 2 or len(cand) != 1:
                    break
                j = cand[0]
                ja, jz, jc, jp = reps[j]
                used[j] = True
                if prepend:
                    seg = jc if jz == node else jc[::-1]
                    chain = seg[:-1] + chain
                    grown = len(seg) - 1
                    spans = [[e + grown, pp] for e, pp in spans]
                    spans.insert(0, [grown, jp])
                    node = ja if jz == node else jz
                else:
                    seg = jc if ja == node else jc[::-1]
                    chain = chain + seg[1:]
                    spans.append([len(chain) - 1, jp])
                    node = jz if ja == node else ja
        return chain, spans

    feats = []
    base_m, thick = dk["base_m"], dk["thickness_m"]
    ramp, step = max(dk["ramp_m"], 1.0), max(dk["step_m"], 1.0)
    for i in range(n):
        if used[i]:
            continue
        chain, spans = walk(i)
        lon0, lat0 = chain[0]
        kx = 111320.0 * math.cos(math.radians(lat0))
        pts = [((x - lon0) * kx, (y - lat0) * 111320.0) for x, y in chain]
        local = LineString(pts)
        L = local.length
        # cumulative distance at each span boundary, to give every slice its edge's props
        cum = [0.0]
        for k in range(1, len(pts)):
            dx = pts[k][0] - pts[k - 1][0]
            dy = pts[k][1] - pts[k - 1][1]
            cum.append(cum[-1] + (dx * dx + dy * dy) ** 0.5)
        bounds = [(cum[e], pp) for e, pp in spans]

        def props_at(d):
            for b, pp in bounds:
                if d <= b + 1e-6:
                    return pp
            return bounds[-1][1]

        def lanes_of(pp):
            try:
                return max(int(float(pp.get("lanes"))), 1)
            except (TypeError, ValueError):
                return 2

        pieces = max(1, round(L / step))
        for k in range(pieces):
            d0, d1 = L * k / pieces, L * (k + 1) / pieces
            part = substring(local, d0, d1)
            if part.geom_type != "LineString" or part.length <= 0:
                continue
            mid = (d0 + d1) / 2
            pp = props_at(mid)
            half = max(dk["lane_m"] * lanes_of(pp) / 2.0, 2.5)
            poly = part.buffer(half, cap_style=2, join_style=2)
            if poly.geom_type != "Polygon":
                continue
            t = min(mid, L - mid, ramp) / ramp        # 0 at the ends -> 1 mid-span
            t = t * t * (3 - 2 * t)                   # smoothstep: gentle takeoff + level-off;
            #                                           with step_m << thickness the ~0.1-0.3 m
            #                                           per-slice height delta hides inside the
            #                                           deck body -> reads as a continuous ramp
            coords = [[round(x / kx + lon0, 6), round(y / 111320.0 + lat0, 6)]
                      for x, y in poly.exterior.coords]
            props = {k2: v for k2, v in pp.items()
                     if k2.startswith("__rs_fill") or k2 in ("highway", "name")}
            props["base"] = round(base_m * t, 2)
            props["height"] = round(base_m * t + thick, 2)
            feats.append({"type": "Feature", "properties": props,
                          "geometry": {"type": "Polygon", "coordinates": [coords]}})
    return {"type": "FeatureCollection", "features": feats}


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


_JS_MAX_SAFE_INT = 2 ** 53 - 1

# Curated default fields for the road click-popup (used when road_popup=True), instead of every
# column. `name` renders as the bold title (no label); every other field shows as "key: value".
# Blank / "nan" values are dropped, and `bridge`/`tunnel` show only when the road actually is one.
# `edge_id` stays a string (see _stringify_unsafe_ints) so oversized content-hash ids are exact.
# Override per call: road_popup=<list> for specific fields, road_popup="all" for every column.
DEFAULT_ROAD_POPUP = ["name", "edge_id", "edge_ref", "highway", "lanes", "bridge", "tunnel"]


def _stringify_unsafe_ints(geo):
    """Emit oversized integer properties (``|v| > 2**53``) as JSON strings.

    Properties are inlined as JSON numbers, and the browser's ``JSON.parse`` silently rounds any
    integer past ``Number.MAX_SAFE_INTEGER`` — so a BIGINT id (e.g. a content-hash ``edge_id``)
    would show a wrong value in a popup / tooltip. Stringifying keeps it exact and readable. The
    feature *id* is generated by MapLibre (``generateId``), not taken from these properties, so this
    is display-only — it does not affect feature-state, filtering, styling, or ``color_options``."""
    for ft in geo.get("features", []):
        p = ft.get("properties")
        if not p:
            continue
        for k, v in p.items():
            if type(v) is int and abs(v) > _JS_MAX_SAFE_INT:   # bool is excluded (type check)
                p[k] = str(v)


# Inflated in the browser from a gzipped base64 blob, one per GeoJSON source. A styled road network
# is enormously repetitive — every property KEY is spelled out on every feature — so the page is
# dominated by its data, not its geometry (measured on a 100k-edge map: properties 40 MB,
# coordinates 7 MB) and gzip takes it down ~13x.
#
# Safe because nothing in the page reads FEATURES at load: the style, colour options, filter classes,
# legend and fitBounds bounds are all computed here in Python and baked in, and popup/tooltip read
# `feature.properties` only on user interaction, long after the data lands.
_INFLATE_JS = """
<script id="rs-gz" type="application/json">__RS_GZ__</script>
<script>
(async function(){
  var el=document.getElementById("rs-gz");
  var blobs=JSON.parse(el.textContent);
  var data={};
  try{
    for(var sid in blobs){
      // atob + Blob.stream, NOT fetch("data:..."): sandboxed webviews (VS Code notebooks) ship a
      // CSP whose connect-src blocks data: fetches — tiles load but the roads never appear.
      var b=atob(blobs[sid]), arr=new Uint8Array(b.length);
      for(var i=0;i<b.length;i++) arr[i]=b.charCodeAt(i);
      data[sid]=await new Response(new Blob([arr]).stream()
                  .pipeThrough(new DecompressionStream("gzip"))).json();
    }
    el.textContent="";                                   // release the base64 copies
  }catch(e){
    window.__rs_gz={ok:false, stage:"inflate", error:String(e)};
    document.body.insertAdjacentHTML("afterbegin",
      '<div style="position:fixed;z-index:9999;top:0;left:0;right:0;padding:10px;background:#c00;'+
      'color:#fff;font:13px sans-serif">Could not decompress the map data: '+e+
      ' \u2014 this page needs a browser with DecompressionStream.</div>');
    return;
  }
  // `window.map` is the CONTAINER DIV until MapLibre finishes constructing (an element id
  // auto-creates a global), so a handle grabbed too early has no getSource and the data is silently
  // never attached. Poll for the real Map; never call through an unchecked handle.
  var tries=0;
  (function fill(){
    var m=window.map, sids=Object.keys(data);
    if(!(m && typeof m.getSource==="function") || !sids.every(function(s){return m.getSource(s);})){
      if(++tries>600){ window.__rs_gz={ok:false, stage:"attach", error:"map never appeared"}; return; }
      return setTimeout(fill,100);
    }
    var n=0;
    sids.forEach(function(s){ m.getSource(s).setData(data[s]); n+=data[s].features.length; });
    window.__rs_gz={ok:true, sources:sids, features:n};
    data=null;
  })();
})();
</script>
"""


def _minzoom_filter(col, table):
    """A filter clause keeping a feature only at/above its class's minzoom.

    MapLibre allows ``["zoom"]`` inside ``filter`` (evaluated at integer zoom levels), so this rides
    the EXISTING road layers — no extra layers, no layer-id changes, nothing downstream to update.
    A class the table omits gets 0, i.e. always drawn: the table is a list of things to *hide early*,
    never a whitelist, so an unknown class can never silently vanish.
    """
    match = ["match", ["coalesce", ["get", col], ""]]
    for cls, z in sorted(table.items()):
        match += [cls, float(z)]
    match += [0.0]
    return [">=", ["zoom"], match]


def _compress_sources(style, min_bytes: int = 262144):
    """Move every GeoJSON source's data out of ``style`` into gzipped base64 blobs.

    Returns ``{source_id: base64}``; ``style`` is mutated so each moved source starts EMPTY and is
    filled at load. Sources below ``min_bytes`` are left inline — a boundary polygon is a few hundred
    bytes and not worth a round trip.
    """
    import base64
    import gzip

    blobs = {}
    for sid, src in style.get("sources", {}).items():
        if src.get("type") != "geojson" or not isinstance(src.get("data"), dict):
            continue
        raw = json.dumps(src["data"], separators=(",", ":")).encode()
        if len(raw) < min_bytes:
            continue
        blobs[sid] = base64.b64encode(gzip.compress(raw, 6)).decode()
        src["data"] = {"type": "FeatureCollection", "features": []}
    return blobs


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


def _ov_hl(base, hc, sc, interactive):
    """An overlay paint colour that brightens to ``hc`` on hover / ``sc`` on select (feature-state),
    falling back to ``base``. Static ``base`` for non-interactive overlays (no feature-state)."""
    if not interactive:
        return base
    return ["case",
            ["boolean", ["feature-state", "select"], False], sc,
            ["boolean", ["feature-state", "hover"], False], hc,
            base]


def _overlay_layers(sid, ov, kind, hover_color="#b388ff", select_color="#7c4dff"):
    """The MapLibre layer spec(s) for one overlay source: a fill (+ outline), a circle, or a line.

    Interactive overlays (those with a popup) recolour on hover / select via feature-state, the same
    way roads do, so the hovered / clicked feature highlights."""
    op = ov.opacity
    interactive = ov.popup is None or bool(ov.popup)
    col = _ov_hl(ov.color, hover_color, select_color, interactive)
    lay = {"visibility": "visible" if getattr(ov, "visible", True) else "none"}
    if kind == "fill":
        return [
            {"id": f"{sid}-fill", "type": "fill", "source": sid, "layout": dict(lay),
             "paint": {"fill-color": col, "fill-opacity": 0.15 if op is None else op}},
            {"id": f"{sid}-outline", "type": "line", "source": sid, "layout": dict(lay),
             "paint": {"line-color": ov.outline or ov.color, "line-width": ov.width,
                       "line-opacity": 0.9}},
        ]
    if kind == "circle":
        return [{"id": f"{sid}-circle", "type": "circle", "source": sid, "layout": dict(lay),
                 "paint": {"circle-radius": ov.radius, "circle-color": col,
                           "circle-opacity": 0.85 if op is None else op,
                           "circle-stroke-color": "#ffffff", "circle-stroke-width": 1}}]
    return [{"id": f"{sid}-line", "type": "line", "source": sid,
             "layout": {**lay, "line-cap": "round"},
             "paint": {"line-color": col, "line-width": ov.width,
                       "line-opacity": 0.9 if op is None else op}}]


def _build_overlays(style, overlays, hover_color="#b388ff", select_color="#7c4dff"):
    """Add each overlay as its own source + layer(s) to ``style``. Returns ``(under, over, meta)``:
    the layer specs to splice below / above the roads, and the JS metadata (label / source / clickable
    layer ids / popup fields) the page reads to wire popups, hover/select highlight, and the Layers
    toggle. Overlay sources carry ``generateId`` so interactive features can take feature-state."""
    under, over, meta = [], [], []
    for i, item in enumerate(overlays or []):
        ov = item if isinstance(item, Overlay) else Overlay(data=item)
        fc = to_fc(ov.data)
        kind = ov.kind or detect_kind(fc)
        sid = f"ov{i}"
        style["sources"][sid] = {"type": "geojson", "data": fc, "generateId": True}
        layers = _overlay_layers(sid, ov, kind, hover_color, select_color)
        (under if ov.placement == "under" else over).extend(layers)
        # the topmost layer is the click target (fill body / circle / line)
        meta.append({"label": ov.label or f"Layer {i + 1}",
                     "source": sid,
                     "layers": [lyr["id"] for lyr in layers],
                     "hit": layers[0]["id"],
                     "visible": getattr(ov, "visible", True),
                     "color": ov.color,
                     "popup": list(ov.popup) if ov.popup is not None else None,
                     "interactive": ov.popup is None or bool(ov.popup)})
    return under, over, meta


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
.co-ctrl{position:absolute;top:10px;right:10px;z-index:2;background:#fff;border-radius:5px;
box-shadow:0 1px 4px rgba(0,0,0,.3);padding:4px 7px;font:13px system-ui,sans-serif;color:#555}
.co-ctrl select{font:inherit;border:0;background:transparent;cursor:pointer;outline:none;color:#111}
.co-lg{position:absolute;left:10px;bottom:24px;z-index:2;background:rgba(255,255,255,.94);
border-radius:5px;box-shadow:0 1px 4px rgba(0,0,0,.3);padding:6px 9px;font:12px system-ui,sans-serif;color:#222}
.co-lg .lg-title{font-weight:600;margin-bottom:4px}
.co-lg .lg-row{display:flex;align-items:center;gap:6px;white-space:nowrap}
.co-lg .lg-sw{width:14px;height:8px;border-radius:2px;display:inline-block}
.co-lg .lg-bar{height:10px;width:150px;border-radius:3px;margin:2px 0}
.co-lg .lg-ends{display:flex;justify-content:space-between;color:#555}
.ov-ctrl{position:absolute;bottom:24px;right:10px;z-index:2;background:#fff;border-radius:5px;
box-shadow:0 1px 4px rgba(0,0,0,.3);font:13px system-ui,sans-serif;color:#222}
.ov-ctrl .ov-hd{padding:5px 9px;font-weight:600}
.ov-ctrl .ov-body{padding:0 9px 7px;display:flex;flex-direction:column;gap:2px}
.ov-ctrl label{display:flex;align-items:center;gap:5px;white-space:nowrap;cursor:pointer}
.ov-ctrl .ov-sw{width:12px;height:12px;border-radius:3px;display:inline-block;flex:none}
</style></head><body>
<div id="map"></div><script>
const style = __STYLE__, BASEMAPS = __BASEMAPS__;
const map = new maplibregl.Map({container:"map", style:style, center:__CENTER__, zoom:13,
  pitch:__PITCH__, bearing:__BEARING__, attributionControl:{compact:true}});
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}));
// 2D/3D camera toggle: tilting hides behind right-drag otherwise. Shows the view it will
// switch TO; 2D also squares the bearing back to north.
const PITCH3D = __PITCH3D__;
map.addControl({onAdd(m){
  const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
  const b=document.createElement("button"); b.type="button";
  b.style.cssText="font:700 11px/1 system-ui;letter-spacing:.03em";
  const upd=()=>{ b.textContent = m.getPitch()<5 ? "3D" : "2D";
                  b.title = m.getPitch()<5 ? "Tilt the view" : "Back to flat"; };
  b.onclick=()=>{ m.getPitch()<5 ? m.easeTo({pitch:PITCH3D, duration:600})
                                 : m.easeTo({pitch:0, bearing:0, duration:600}); };
  m.on("pitchend", upd); m.on("pitch", upd); upd();
  d.appendChild(b); return d;
}, onRemove(){}});
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
// "colour by" recolouring: swap which baked fill prop the road layers read (no re-render). Each
// option's fill is baked per edge (__rs_fill / __rs_fill__1 …); setPaintProperty repoints the
// road-fill layers' line-color at the chosen prop. window.rsSetColorField drives it from your UI.
const COLOR_OPTIONS = __COLOR_OPTIONS__;
const RS_FILL_LAYERS = ["roads-fill","roads-tunnel-fill","roads-bridge-fill"];
let _coActive = __CO_ACTIVE__, _coLegendEl = null;
function coLegendHtml(lg){
  if(!lg) return "";
  let h = lg.title ? '<div class="lg-title">'+lg.title+'</div>' : "";
  if(lg.kind==="categorical"){ (lg.entries||[]).forEach(e=>{
    h+='<div class="lg-row"><span class="lg-sw" style="background:'+e[1]+'"></span>'+e[0]+'</div>'; }); }
  else if(lg.kind==="continuous"){
    h+='<div class="lg-bar" style="background:linear-gradient(90deg,'+(lg.ramp||[]).join(",")+')"></div>'
      +'<div class="lg-ends"><span>'+lg.vmin+'</span><span>'+lg.vmax+'</span></div>'; }
  return h;
}
function coUpdateLegend(){
  if(!_coLegendEl) return;
  const h = coLegendHtml((COLOR_OPTIONS[_coActive]||{}).legend);
  _coLegendEl.innerHTML = h; _coLegendEl.style.display = h ? "" : "none";
}
function rsSetColorField(nameOrIdx){
  let idx = typeof nameOrIdx==="number" ? nameOrIdx : COLOR_OPTIONS.map(o=>o.name).indexOf(nameOrIdx);
  const o = COLOR_OPTIONS[idx]; if(!o) return;
  _coActive = idx;
  RS_FILL_LAYERS.forEach(id=>{ if(map.getLayer(id))
    map.setPaintProperty(id,"line-color",["coalesce",["get",o.prop],"#888888"]); });
  if(map.getLayer("roads-bridge-decks"))
    map.setPaintProperty("roads-bridge-decks","fill-extrusion-color",
                         ["coalesce",["get",o.prop],"#888888"]);
  const sel=document.getElementById("co-select"); if(sel) sel.value=String(idx);
  coUpdateLegend();
  document.dispatchEvent(new CustomEvent("rs:colorchange",{detail:{option:o,index:idx}}));
}
window.rsSetColorField = rsSetColorField;
window.RS_COLOR_OPTIONS = COLOR_OPTIONS;
if(COLOR_OPTIONS.length > 1){
  const w=document.createElement("div"); w.className="co-ctrl";
  w.appendChild(document.createTextNode("Colour by "));
  const sel=document.createElement("select"); sel.id="co-select";
  COLOR_OPTIONS.forEach((o,i)=>{ const op=document.createElement("option");
    op.value=i; op.textContent=o.name; sel.appendChild(op); });
  sel.onchange=()=> rsSetColorField(parseInt(sel.value,10));
  w.appendChild(sel); document.body.appendChild(w);
}
if(_coActive){ const _ap=()=>rsSetColorField(_coActive);   // display the requested option on load
  if(map.isStyleLoaded && map.isStyleLoaded()) _ap(); else map.on("load", _ap); }
if(COLOR_OPTIONS.some(o=>o.legend)){
  _coLegendEl=document.createElement("div"); _coLegendEl.className="co-lg";
  document.body.appendChild(_coLegendEl); coUpdateLegend();
}
// extra overlay layers (zones / POIs / lines): click an interactive overlay -> popup of its
// fields; a Layers control toggles each overlay's visibility. Road clicks take precedence (an
// overlay is only consulted when the click misses every road).
const OVERLAYS = __OVERLAYS__;
let _ovSel=null, _ovHov=null;                              // {source,id} of the selected / hovered overlay feature
function _ovState(ref, st){ if(ref) map.setFeatureState({source:ref.source, id:ref.id}, st); }
function clearOvSel(){ _ovState(_ovSel,{select:false}); _ovSel=null; }
function handleOverlayClick(e){                            // info popup only on SELECT (click), not hover
  for(const ov of OVERLAYS){
    if(!ov.interactive) continue;
    const ids = ov.layers.filter(id=>map.getLayer(id));
    const hits = ids.length ? map.queryRenderedFeatures(e.point, {layers:ids}) : [];
    if(hits.length){
      const f = hits[0], p = f.properties||{};
      _ovState(_ovSel,{select:false}); _ovSel={source:ov.source, id:f.id}; _ovState(_ovSel,{select:true});
      const fields = ov.popup && ov.popup.length ? ov.popup : Object.keys(p);
      const rows = fields.filter(k=>p[k]!=null && p[k]!=="").map(k=>"<b>"+k+"</b>: "+p[k]);
      new maplibregl.Popup({closeButton:true,maxWidth:"260px"})
        .setLngLat(e.lngLat).setHTML(rows.join("<br>")||"(no data)").addTo(map)
        .on("close", clearOvSel);
      return true;
    }
  }
  return false;
}
OVERLAYS.forEach(ov=>{ if(!ov.interactive) return; ov.layers.forEach(id=>{
  map.on("mousemove", id, e=>{ map.getCanvas().style.cursor="pointer";   // hover -> recolour (no popup)
    const f = e.features && e.features[0]; if(!f) return;
    if(_ovHov && !(_ovHov.source===ov.source && _ovHov.id===f.id)) _ovState(_ovHov,{hover:false});
    _ovHov={source:ov.source, id:f.id}; _ovState(_ovHov,{hover:true}); });
  map.on("mouseleave", id, ()=>{ map.getCanvas().style.cursor="";
    _ovState(_ovHov,{hover:false}); _ovHov=null; });
}); });
if(OVERLAYS.length){
  const box=document.createElement("div"); box.className="ov-ctrl";
  const hd=document.createElement("div"); hd.className="ov-hd"; hd.textContent="Layers";
  const body=document.createElement("div"); body.className="ov-body"; box.appendChild(hd); box.appendChild(body);
  OVERLAYS.forEach(ov=>{
    const lab=document.createElement("label");
    const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=ov.visible!==false;
    cb.onchange=()=>{ ov.layers.forEach(id=>{ if(map.getLayer(id))
      map.setLayoutProperty(id,"visibility", cb.checked?"visible":"none"); }); };
    lab.appendChild(cb);
    if(ov.color){ const sw=document.createElement("span"); sw.className="ov-sw";
      sw.style.background=ov.color; lab.appendChild(sw); }
    lab.appendChild(document.createTextNode(" "+ov.label)); body.appendChild(lab);
  });
  document.body.appendChild(box);
}
// oneway direction-arrow icon (openstreetmap-carto)
function addArrow(){
  if(map.hasImage("oneway")) return;
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="24" height="10" viewBox="0 0 12 5">'
    +'<path d="M 0,2 7,2 7,0 12,2.5 7,5 7,3 0,3 z" fill="__ARROW_COLOR__"/></svg>';
  const img=new Image(24,10);
  img.onload=()=>{ if(!map.hasImage("oneway")) map.addImage("oneway",img,{pixelRatio:2}); };
  img.src="data:image/svg+xml;base64,"+btoa(svg);
}
map.on("load", addArrow);
// Self-diagnosis: a map with zero road features is a broken page, not an empty area — say WHY
// on the map itself (frontends like notebook webviews surface no console). Amber banner reports
// the inflate state so a screenshot alone pinpoints the failing stage.
map.on("load", function(){ setTimeout(function(){
  try{
    var src = map.getSource("roads");
    var n = (src && src._data && src._data.features) ? src._data.features.length : 0;
    if(n) return;
    var gz = window.__rs_gz ? JSON.stringify(window.__rs_gz) : "inflate script did not run";
    document.body.insertAdjacentHTML("afterbegin",
      '<div style="position:fixed;z-index:9999;top:0;left:0;right:0;padding:8px 12px;'+
      'background:#b45309;color:#fff;font:12px monospace">roadstyle: 0 road features — '+gz+
      ' | DecompressionStream: '+(typeof DecompressionStream)+'</div>');
  }catch(e){}
}, 2500); });
map.on("styleimagemissing", e=>{ if(e.id==="oneway") addArrow(); });
// hover + click-to-select + info popup (feature-state, tolerance box, throttled to one query/frame)
const HIT = 4;
function box(p){ return [[p.x-HIT,p.y-HIT],[p.x+HIT,p.y+HIT]]; }
function pick(p){ const l = map.queryRenderedFeatures(box(p), {layers:["roads-fill","roads-tunnel-fill","roads-bridge-fill"]}); return l.length ? l[0] : null; }
function setS(id, st){ if(id!=null) map.setFeatureState({source:"roads", id:id}, st); }
let _hov=null, _pt=null, _raf=0;
function _rfields(p, only){ const r=[];
  if(p.name!=null && (""+p.name)!=="" && (""+p.name).toLowerCase()!=="nan") r.push("<b>"+p.name+"</b>");  // name on top, bold, no label
  const ks = (only && only.length) ? only : Object.keys(p);
  for(const k of ks){ if(k[0]==="_"||k==="twoway"||k==="lvl"||k==="name") continue;  // lvl/twoway are roadstyle-injected internals
    var v=p[k]; if(v==null) continue; var s=""+v, sl=s.toLowerCase();
    if(s===""||sl==="nan"||sl==="none") continue;
    if((k==="bridge"||k==="tunnel") && (sl==="no"||sl==="0"||sl==="false")) continue;  // bridge/tunnel only when it IS one
    r.push(k+": "+s); } return r.join("<br>"); }
const _popupFields = __ROAD_POPUP_FIELDS__;   // curated field list, or null => all columns
const _ttip = __ROAD_TOOLTIP__, _ttipOnly = Array.isArray(_ttip) ? _ttip : null;  // false | true | [fields]
const _tip = _ttip ? new maplibregl.Popup(
  {closeButton:false, closeOnClick:false, maxWidth:"260px", offset:10, className:"rs-tip"}) : null;
function hoverFrame(){ _raf=0; if(!_pt) return;
  const f = pick(_pt); map.getCanvas().style.cursor = f ? "pointer" : "";
  const id = f ? f.id : null;
  if(id !== _hov){ setS(_hov,{hover:false}); _hov=id; setS(_hov,{hover:true}); }
  if(_tip){ if(f){ _tip.setLngLat(map.unproject(_pt)).setHTML(_rfields(f.properties||{}, _ttipOnly));
      if(!_tip.isOpen()) _tip.addTo(map); } else if(_tip.isOpen()) _tip.remove(); }
}
map.on("mousemove", e=>{ _pt=e.point; if(!_raf) _raf=requestAnimationFrame(hoverFrame); });
map.on("mouseout", ()=>{ _pt=null; if(_raf){cancelAnimationFrame(_raf);_raf=0;} setS(_hov,{hover:false}); _hov=null; if(_tip) _tip.remove(); });
let _sel=null;
map.on("click", e=>{
  if(handleOverlayClick(e)){ if(_sel!=null){ setS(_sel,{select:false}); _sel=null; } return; }  // visible "over" overlay (front) wins
  const f = pick(e.point);
  if(!f){ if(_sel!=null){ setS(_sel,{select:false}); _sel=null; } return; }   // click empty -> deselect (restore colour)
  clearOvSel();
  if(_sel!=null) setS(_sel,{select:false}); _sel=f.id; setS(_sel,{select:true});
  if(__ROAD_POPUP__){
    new maplibregl.Popup({closeButton:true, maxWidth:"260px"})
      .setLngLat(e.lngLat).setHTML(_rfields(f.properties||{}, _popupFields)).addTo(map);
  }
});
map.on("load", ()=>{ try{ map.fitBounds(__BOUNDS__,
  {padding:30, duration:0, pitch:__PITCH__, bearing:__BEARING__}); }catch(e){} });
window.map = map;
</script></body></html>"""


# Notebook previews pin MapLibre v3: v4+ silently never finishes style loading inside Jupyter
# Notebook 7's page (data lands, zero features render) — reproduced against a live server; v3
# renders the identical style JSON fine. Saved files keep the vendored 4.7.1 (unaffected in a
# normal browser tab).
_MAPLIBRE_CDN = "https://cdn.jsdelivr.net/npm/maplibre-gl@3.6.2/dist"


class WebMap:
    """A self-contained MapLibre HTML map. ``.save(path)`` / ``.html`` inline the vendored
    MapLibre (the file opens offline, no CDN); the notebook display swaps in CDN tags instead —
    an inline output must stay small enough for notebook frontends' output limits, and the
    preview needs the network for its basemap tiles anyway."""

    def __init__(self, html: str):
        self._tpl = html                     # full page, MapLibre still a placeholder

    @property
    def html(self) -> str:
        """The complete self-contained page (vendored MapLibre inlined)."""
        return (self._tpl
                .replace("__MAPLIBRE_CSS__", _asset("maplibre-gl.css"))
                .replace("__MAPLIBRE_JS__", _asset("maplibre-gl.js").replace("</script>", "<\\/script>")))

    def save(self, path):
        from pathlib import Path
        Path(path).write_text(self.html, encoding="utf-8")
        return path

    def _repr_html_(self):
        slim = (self._tpl
                .replace("<style>__MAPLIBRE_CSS__</style>",
                         f'<link rel="stylesheet" href="{_MAPLIBRE_CDN}/maplibre-gl.css"/>')
                .replace("<script>__MAPLIBRE_JS__</script>",
                         f'<script src="{_MAPLIBRE_CDN}/maplibre-gl.js"></script>'))
        return (f'<iframe srcdoc="{_html.escape(slim, quote=True)}" '
                'style="width:100%;height:640px;border:0;border-radius:6px"></iframe>')


def render(gdf, palette: str = "highsat", highway_col: str = "highway",
           filter_col: str = None,
           styler=None, basemap=None, basemaps=None, name: str = "roadstyle",
           offset_frac: float = 0.28, width_frac: float = 0.6, offset_zoom: int = 15,
           tunnel_col: str = "tunnel", bridge_col: str = "bridge", layer_col: str = "layer",
           pitch: float = None, bearing: float = None, view_3d: bool = False,
           arrows: bool = True, labels: bool = True, filter_control: bool = True,
           basemap_switcher: bool = True, road_popup=True, road_tooltip=False,
           tooltip=None, hover_color: str = "#b388ff", select_color: str = "#7c4dff", boundary=None,
           color_options=None, color_active=0, overlays=None, compress: bool = False,
           minzoom=None, **_ignore):
    """Build a self-contained MapLibre map of the styled edges.

    If the data carries ``tunnel`` / ``bridge`` / ``layer`` columns (named via ``tunnel_col`` /
    ``bridge_col`` / ``layer_col``), grade-separated roads are ordered by elevation so tunnels draw
    underneath and bridges on top — otherwise every edge is treated as ground level.

    UI toggles (all on by default):
      - ``arrows`` — one-way direction chevrons along each one-way edge;
      - ``labels`` — curved street-name labels (from the ``name`` column);
      - ``filter_control`` — a collapsible checkbox panel to show/hide each road class;
      - ``basemap_switcher`` — the in-map base-layer dropdown (uses ``basemap`` / ``basemaps``);
      - ``road_popup`` — the info popup shown when a road is clicked (click-to-select is kept either
        way). ``True`` (default) shows the curated :data:`DEFAULT_ROAD_POPUP` fields; pass a list of
        field names for a custom set, ``"all"`` for every column, or ``False`` to disable and drive
        your own readout from ``window.map`` events. ``name`` is the bold title; ``bridge`` /
        ``tunnel`` appear only when the road is one.
      - ``hover_color`` / ``select_color`` — the highlight colours for a hovered / selected road (the
        ``roads-highlight`` feature-state); default light-violet ``#b388ff`` / violet ``#7c4dff``.

    ``boundary`` (optional) overlays a dashed outline — a shapely geometry, a GeoSeries /
    GeoDataFrame, or a GeoJSON mapping (assumed lon/lat) — e.g. the area the network was clipped
    to.

    ``color_options`` (optional) bakes several "colour by" fill sets — an ordered mapping
    ``{name: {styler kwargs}}`` (or a list of ``{"name": ..., **kwargs}``) — and adds a *Colour by*
    dropdown that recolours the roads client-side with no re-render (each road keeps its width /
    casing / lanes; only the fill swaps). A neutral base reads best — pair the class option with
    ``palette="mono"``. ``window.rsSetColorField(name|index)`` drives the same swap from your own
    UI.

    ``overlays`` (optional) draws extra layers the caller brings — a list of :class:`Overlay`
    (zone polygons, POI circles, any geometry). Each becomes its own source + layer(s), placed
    ``under`` or ``over`` the roads, clickable for a popup of its fields, and toggled from a
    *Layers* control.

    ``tooltip`` is a convenience alias for the shared backend arg (folium / CLI ``--tooltip``): when
    given and ``road_tooltip`` is unset, its value drives the hover tooltip here too, so the same
    call works across backends."""
    # `tooltip=` is the folium/CLI hover arg; the web backend's own name is `road_tooltip`. Alias it
    # through so a shared `tooltip=`/`--tooltip` works on the web backend instead of being ignored.
    if tooltip is not None and not road_tooltip:
        road_tooltip = tooltip
    # road_popup: True -> curated DEFAULT_ROAD_POPUP; a list/tuple -> those fields; "all" -> every
    # column; False -> no popup. Baked into the page as (enabled flag, field list-or-null).
    if road_popup is False:
        popup_on, popup_fields = False, None
    elif road_popup is True:
        popup_on, popup_fields = True, list(DEFAULT_ROAD_POPUP)
    elif isinstance(road_popup, str):
        popup_on, popup_fields = True, None
    else:
        popup_on, popup_fields = True, list(road_popup)
    g = gdf.to_crs(4326)

    color_opts_meta = None
    if color_options:
        # one pre-resolved fill set per "colour by" option; option 0 is active (drives the shared
        # width/casing via bake_props), the rest bake only their fill under __rs_fill__<i>.
        items = (list(color_options.items()) if isinstance(color_options, Mapping)
                 else [(o["name"], {k: v for k, v in o.items() if k != "name"})
                       for o in color_options])
        frames = [(name, option_styler(highway_col, palette, opts).resolve_frame(g))
                  for name, opts in items]
        geo, color_opts_meta = bake_color_options(json.loads(g.to_json()), frames)
        _names = [n for n, _ in items]
        _active = (color_active if isinstance(color_active, int)
                   else _names.index(color_active) if color_active in _names else 0)
    else:
        _active = 0
        if styler is None:
            styler = build_styler(palette=palette, highway_col=highway_col)
        rf = styler.resolve_frame(g)
        geo = bake_props(json.loads(g.to_json()), rf)   # per-edge __rs_fill/__rs_casing
    _mark_twoway(geo)
    _mark_lvl(geo, tunnel_col, bridge_col, layer_col)
    _stringify_unsafe_ints(geo)   # BIGINT ids (e.g. edge_id) -> string so JS doesn't round them

    # active base map + the set offered to the in-map switcher (active shown first)
    # the primary base map layer is a *setting* (config.basemap, defaults.json), overridable
    # per call with `basemap=`
    active = basemap or CONFIG.basemap
    bkeys = list(basemaps) if basemaps else list(DEFAULT_SWITCHER)
    if isinstance(active, str):
        bkeys = [active] + [k for k in bkeys if k != active]
    bms = [{"label": get_basemap(k).label, "tiles": _tiles(get_basemap(k))} for k in bkeys]
    if not basemap_switcher:
        bms = bms[:1]                                     # one entry -> the JS hides the dropdown
    style = _basemap_style(get_basemap(active))
    # tolerance 0.05 (default 0.375): the source re-tiles at every integer zoom and re-simplifies
    # the geometry — at the default tolerance the roads visibly ripple ("wave") on each zoom
    # crossing. Near-zero simplification keeps zooming smooth; ~5k features can afford it.
    style["sources"]["roads"] = {"type": "geojson", "data": geo, "generateId": True,
                                 "tolerance": 0.05}

    # extra overlay layers (zones / POIs / any geometry the caller brings); each gets its own source
    # + paint layer(s), placed under or over the roads, and (if `popup` is set) clickable.
    under_layers, over_layers, ov_meta = _build_overlays(style, overlays)

    # Round caps + joins everywhere: consecutive edges are separate LineStrings, and a round cap is
    # the only rendering primitive that seals the seam where two of them connect (line-join only
    # works *within* a feature). Network continuity outranks end-cap shape — a round blob at a
    # dead end is cosmetic, a notch at a connection or junction is a break in the network.
    lay = {"line-cap": "round", "line-join": "round", "line-sort-key": _sort_key(highway_col)}
    tlay = {**lay, "line-cap": "butt"}                    # butt cap -> clean dash ticks on tunnel casing
    blay = {**lay, "line-cap": "butt"}                    # butt cap -> square bridge deck ends
    off = _offset_expr(highway_col, offset_frac, offset_zoom)
    sw = dict(split_zoom=offset_zoom, split_frac=width_frac)
    surface = ["==", ["coalesce", ["get", "lvl"], 0], 0]  # lvl == 0
    tunnel = ["<", ["coalesce", ["get", "lvl"], 0], 0]    # lvl == -1
    bridge = [">", ["coalesce", ["get", "lvl"], 0], 0]    # lvl == +1
    # minzoom: hide minor classes when zoomed out (config.DEFAULT.minzoom, or a caller override).
    # AND-ed onto each road filter rather than given its own layers, so layer ids are untouched.
    mz = ({**CONFIG.minzoom} if minzoom is True else
          {**CONFIG.minzoom, **minzoom} if isinstance(minzoom, dict) else None)
    if mz:
        _z = _minzoom_filter(highway_col, mz)
        surface, tunnel, bridge = (["all", _z, surface], ["all", _z, tunnel], ["all", _z, bridge])
    dk = {"base_m": 5.0, "thickness_m": 1.0, "lane_m": 3.5, **(CONFIG.bridge_decks or {})}
    decks = _bridge_decks(geo, dk) if view_3d else {"features": []}
    if decks["features"]:
        style["sources"]["decks"] = {"type": "geojson", "data": decks}
    cw = _width_expr(highway_col, casing=True, **sw)      # casing width expr (reused across layers)
    fw = _width_expr(highway_col, **sw)                   # fill width expr
    bcw = _width_expr(highway_col, casing=True, scale=1.25, **sw)   # heavier bridge casing ("wings")
    style["layers"] += under_layers            # caller overlays drawn beneath the roads (e.g. zones)
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
        # Bridges last (on top). Flat view: heavier square-capped casing reads as a deck.
        # 3D view: the flat lines are replaced by extruded deck ribbons (added after this list).
        *([] if decks["features"] else [
            {"id": "roads-bridge-casing", "type": "line", "source": "roads", "layout": blay,
             "filter": bridge,
             "paint": {"line-color": CONFIG.bridge_casing_color,
                       "line-width": bcw, "line-offset": off}},
            {"id": "roads-bridge-fill", "type": "line", "source": "roads", "layout": lay,
             "filter": bridge,
             "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                       "line-width": fw, "line-offset": off}}]),
        # hover/select highlight, driven by feature-state set from the viewer (GPU recolour, no relayout)
        {"id": "roads-highlight", "type": "line", "source": "roads", "layout": lay,
         "paint": {
             "line-color": ["case", ["boolean", ["feature-state", "select"], False], select_color, hover_color],
             "line-opacity": ["case", ["any", ["boolean", ["feature-state", "hover"], False],
                                       ["boolean", ["feature-state", "select"], False]], 0.85, 0],
             "line-width": fw, "line-offset": off}},
    ]
    if decks["features"]:
        # extruded bridge decks: physical ribbons floating base_m above ground — in the tilted
        # view you look UNDER a bridge and see the roads passing beneath it
        style["layers"].append(
            {"id": "roads-bridge-decks", "type": "fill-extrusion", "source": "decks",
             "paint": {"fill-extrusion-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                       "fill-extrusion-base": ["get", "base"],
                       "fill-extrusion-height": ["get", "height"],
                       "fill-extrusion-opacity": 0.95}})

    # oneway direction arrows (on edges with no reverse twin) + line-placed street names, on top.
    # Both read their cosmetics from data/style.json "config" (labels / arrows blocks), so a user
    # roadstyle.json can restyle them without touching the library; missing keys keep the bundled
    # defaults (a partial override dict is fine).
    cam = {"pitch": 0, "bearing": 0, "pitch_3d": 55, **(CONFIG.camera or {})}
    if view_3d:
        cam["pitch"] = cam["pitch_3d"]     # perspective camera only — no terrain data added
    if pitch is not None:
        cam["pitch"] = pitch
    if bearing is not None:
        cam["bearing"] = bearing
    arw = {"color": "#5b5b5b", "opacity": 0.7, **(CONFIG.arrows or {})}
    lbl = {"color": "#5b5b5b", "halo_color": None, "halo_width": 0, **(CONFIG.labels or {})}
    slot_m = (CONFIG.annotations or {}).get("slot_m", 100)
    if arrows or labels:
        slots = _annotation_slots(geo, slot_m)
        if slots["features"]:
            style["sources"]["slots"] = {"type": "geojson", "data": slots}
            lpaint = {"text-color": lbl["color"]}
            if lbl["halo_color"] and lbl["halo_width"]:
                lpaint["text-halo-color"] = lbl["halo_color"]
                lpaint["text-halo-width"] = lbl["halo_width"]
            # one symbol centred on each slot piece; even slots = names, odd = oneway arrows.
            # Text/icon zoom ramps size the symbols; collision culling thins them when zoomed out
            # (a label that outgrows its piece is dropped by MapLibre automatically).
            if labels:
                style["glyphs"] = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"
                style["layers"].append(
                    {"id": "roads-labels", "type": "symbol", "source": "slots", "minzoom": 14,
                     "filter": ["all", ["==", ["%", ["get", "slot"], 2], 0],
                                ["to-boolean", ["get", "name"]]],
                     "layout": {"symbol-placement": "line-center",
                                "text-field": ["get", "name"],
                                "text-font": ["Noto Sans Regular"],
                                "text-size": ["interpolate", ["linear"], ["zoom"],
                                              14, 10, 18, 14],
                                "text-max-angle": 40, "text-padding": 2},
                     "paint": lpaint})
            if arrows:
                style["layers"].append(
                    {"id": "roads-arrows", "type": "symbol", "source": "slots", "minzoom": 14,
                     "filter": ["all", ["==", ["%", ["get", "slot"], 2], 1],
                                ["==", ["get", "oneway"], 1]],
                     "layout": {"symbol-placement": "line-center", "icon-image": "oneway",
                                "icon-rotation-alignment": "map",
                                "icon-size": ["interpolate", ["linear"], ["zoom"],
                                              15, 0.5, 19, 1.0]},
                     "paint": {"icon-opacity": arw["opacity"]}})

    # clip/area boundary outline, drawn on top of the roads (a dashed line tracing the polygon rings)
    if boundary is not None:
        style["sources"]["boundary"] = {"type": "geojson", "data": _boundary_fc(boundary)}
        style["layers"].append(
            {"id": "boundary", "type": "line", "source": "boundary",
             "layout": {"line-cap": "round", "line-join": "round"},
             "paint": {"line-color": "#6a0dad", "line-width": 2.5, "line-opacity": 0.9,
                       "line-dasharray": [3, 2]}})

    style["layers"] += over_layers             # caller overlays drawn on top of the roads (e.g. POIs)

    # road-class filter panel: the distinct classes present, most important first. `filter_col`
    # (optional) drives the filter from a different column than the styling `highway_col` — e.g. a
    # source's own road class while widths/casing follow an OSM-highway proxy. The web filter reads
    # this raw property directly (["get", col]), so no re-bake is needed.
    fcol = filter_col or highway_col
    classes, seen = [], set()
    for ft in geo["features"]:
        c = ft.get("properties", {}).get(fcol)
        if c and c not in seen:
            seen.add(c)
            classes.append(c)
    classes.sort(key=lambda c: (-ROAD_Z.get(_base(c)[0], 4), c))
    flt = {"on": bool(filter_control and classes), "col": fcol, "classes": classes}

    minx, miny, maxx, maxy = (float(v) for v in g.total_bounds)
    # after every style/filter/bounds decision above — those read the features, the browser never does
    gz = _compress_sources(style) if compress else {}
    html = (_HTML.replace("__TITLE__", _html.escape(name))
            .replace("__ARROW_COLOR__", str(arw["color"]))
            .replace("__STYLE__", json.dumps(style))
            .replace("__BASEMAPS__", json.dumps(bms))
            .replace("__FILTER__", json.dumps(flt))
            .replace("__CENTER__", json.dumps([(minx + maxx) / 2, (miny + maxy) / 2]))
            .replace("__PITCH3D__", json.dumps(cam["pitch_3d"]))
            .replace("__PITCH__", json.dumps(cam["pitch"]))
            .replace("__BEARING__", json.dumps(cam["bearing"]))
            .replace("__BOUNDS__", json.dumps([[minx, miny], [maxx, maxy]]))
            .replace("__COLOR_OPTIONS__", json.dumps(color_opts_meta or []))
            .replace("__CO_ACTIVE__", str(_active))
            .replace("__OVERLAYS__", json.dumps(ov_meta))
            .replace("__ROAD_POPUP__", "true" if popup_on else "false")
            .replace("__ROAD_POPUP_FIELDS__", json.dumps(popup_fields))
            .replace("__ROAD_TOOLTIP__", json.dumps(road_tooltip)))
    if gz:
        html = html.replace("</body>", _INFLATE_JS.replace("__RS_GZ__", json.dumps(gz)) + "</body>", 1)
    # MapLibre stays a placeholder here: WebMap inlines the vendored copy on save (offline file)
    # and swaps in CDN tags for the notebook preview (small enough for notebook output limits).
    return WebMap(html)

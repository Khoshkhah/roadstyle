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
    for ft, k in zip(geo["features"], keys, strict=False):
        rev = (k[1], k[0])
        n = cnt.get(rev, 0)
        # a loop edge (start == end) is its own reverse key; it needs a second feature to pair up
        p = ft.setdefault("properties", {})
        p["twoway"] = n >= 2 if rev == k else n >= 1
        # arrows follow an EXPLICIT `oneway` column when the data has one (undirected networks
        # included); otherwise a one-way edge = an edge with no reverse twin
        ow = p.get("oneway")
        p["__rs_oneway"] = _truthy(ow) if ow is not None else not p["twoway"]


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
        groups[(p.get("name") or None, p.get("lvl", 0),
                1 if p.get("__rs_oneway") else 0)].append(e)

    feats = []
    for (name, _lvl, oneway), edges in groups.items():
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

    Connected bridge edges are walked into chains — ONLY to shape the ramp profile (0 at the
    chain ends, rising over ``ramp_m`` to ``base_m`` mid-span, so the deck takes off from the
    connecting ground road instead of floating disconnected above it). The emitted ribbons stay
    per directed edge: every slice carries its own edge's props/fills and ``__rs_edges`` = that
    single road feature id, and a two-way bridge splits into two half-width ribbons side by side
    (one per twin, each on its travel side) — hover/select works per edge, never per whole
    structure. Total ribbon width = the road's own class width (the px-by-zoom table) converted
    to metres at ``match_zoom``, so a deck is exactly as wide as the flat road of its class at
    that zoom.
    """
    from shapely.geometry import LineString
    from shapely.ops import substring

    reps = []
    # endpoint pair -> ALL bridge feature indices there (both twins of a two-way), so every
    # deck ribbon can be tied to its OWN directed edge (__rs_edges: the hover/select unit)
    pair_edges = collections.defaultdict(list)
    for fi, ft in enumerate(geo["features"]):
        g, p = ft.get("geometry") or {}, ft.get("properties", {})
        c = g.get("coordinates") or []
        if p.get("lvl") != 1 or g.get("type") != "LineString" or len(c) < 2:
            continue
        a = (round(c[0][0], 6), round(c[0][1], 6))
        z = (round(c[-1][0], 6), round(c[-1][1], 6))
        pair_edges[min((a, z), (z, a))].append(fi)
        if p.get("twoway") and (z, a) < (a, z):
            continue
        reps.append((a, z, c, p, fi))

    def twin_of(fi, a, z):
        for f in pair_edges[min((a, z), (z, a))]:
            if f != fi:
                return f
        return None

    n = len(reps)
    used = [False] * n
    at = collections.defaultdict(list)
    for i, (a, z, *_) in enumerate(reps):
        at[a].append(i)
        at[z].append(i)

    def walk(start_i):
        """Undirected chain of connected bridge edges through degree-2 nodes — the chain exists
        ONLY to shape the ramp profile (grounded at true structure ends, level in between); the
        emitted ribbons stay per directed edge. spans = [(end_index, props, fwd_fi, rev_fi)]
        where fwd_fi is the road feature id of the edge running WITH the chain direction and
        rev_fi its reverse twin (None when one-way). The ramp flags say whether each chain end
        is a TRUE ground end (no other bridge edge continues there); at a bridge fork/junction
        the structure carries on, so that end stays at full deck height instead of dipping to
        the ground mid-structure."""
        a, z, c, p, fi = reps[start_i]
        used[start_i] = True
        chain = list(c)
        spans = [[len(chain) - 1, p, fi, twin_of(fi, a, z)]]
        ends = {}
        for prepend in (False, True):
            node = a if prepend else z
            while True:
                cand = [j for j in at[node] if not used[j]]
                if len(at[node]) != 2 or len(cand) != 1:
                    break
                j = cand[0]
                ja, jz, jc, jp, jfi = reps[j]
                jt = twin_of(jfi, ja, jz)
                used[j] = True
                if prepend:
                    fwd, rev = (jfi, jt) if jz == node else (jt, jfi)
                    seg = jc if jz == node else jc[::-1]
                    chain = seg[:-1] + chain
                    grown = len(seg) - 1
                    spans = [[e + grown, pp, ff, rr] for e, pp, ff, rr in spans]
                    spans.insert(0, [grown, jp, fwd, rev])
                    node = ja if jz == node else jz
                else:
                    fwd, rev = (jfi, jt) if ja == node else (jt, jfi)
                    seg = jc if ja == node else jc[::-1]
                    chain = chain + seg[1:]
                    spans.append([len(chain) - 1, jp, fwd, rev])
                    node = jz if ja == node else ja
            ends[prepend] = len(at[node]) == 1     # sole incident bridge edge = ground end
        return chain, spans, ends[True], ends[False]

    feats = []
    chain_i = 0
    base_m, thick = dk["base_m"], dk["thickness_m"]
    ramp, step = max(dk["ramp_m"], 1.0), max(dk["step_m"], 0.25)
    for i in range(n):
        if used[i]:
            continue
        chain, spans, ramp_head, ramp_tail = walk(i)
        chain_i += 1
        lon0, lat0 = chain[0]
        kx = 111320.0 * math.cos(math.radians(lat0))
        mpp = 156543.03392 * math.cos(math.radians(lat0)) / (2 ** dk["match_zoom"])
        pts = [((x - lon0) * kx, (y - lat0) * 111320.0) for x, y in chain]
        local = LineString(pts)
        L = local.length
        # cumulative distance at each span boundary, to give every slice its edge's props
        cum = [0.0]
        for k in range(1, len(pts)):
            dx = pts[k][0] - pts[k - 1][0]
            dy = pts[k][1] - pts[k - 1][1]
            cum.append(cum[-1] + (dx * dx + dy * dy) ** 0.5)
        bounds = [(cum[e], pp, ff, rr) for e, pp, ff, rr in spans]

        def props_at(d):
            for b, pp, ff, rr in bounds:
                if d <= b + 1e-6:
                    return pp, ff, rr
            return bounds[-1][1], bounds[-1][2], bounds[-1][3]


        # slice ONLY where the ramp changes height (and only at true ground ends); the level
        # spans stay whole, split just at edge-span boundaries so per-edge colours survive
        rh = min(ramp, L) if ramp_head else 0.0
        rt = min(ramp, L - rh) if ramp_tail else 0.0
        cuts = {0.0, L}
        d = step
        while d < rh:
            cuts.add(d)
            d += step
        d = step
        while d < rt:
            cuts.add(L - d)
            d += step
        cuts.add(rh)
        cuts.add(L - rt)
        cuts.update(b for b, *_ in bounds if rh < b < L - rt)
        cuts = sorted(cuts)
        for d0, d1 in zip(cuts, cuts[1:], strict=False):
            part = substring(local, d0, d1)
            if part.geom_type != "LineString" or part.length <= 0:
                continue
            mid = (d0 + d1) / 2
            pp, ffi, rfi = props_at(mid)
            grp = ROAD_GROUP.get(str(pp.get("highway", "")), "residential")
            px = _gwidth(WIDTH[grp], HI_RATE[grp], dk["match_zoom"])
            # width_scale trims the ribbon: at a tilted camera the extruded side walls (and a
            # dual carriageway's second chain) add apparent width, so 1.0 reads too fat
            half = max(px * mpp / 2.0, 2.0) * dk.get("width_scale", 1.0)
            up = mid / ramp if ramp_head else 1.0     # 0 only at TRUE ground ends -> 1 mid-span
            dn = (L - mid) / ramp if ramp_tail else 1.0
            t = min(up, dn, 1.0)
            t = t * t * (3 - 2 * t)                   # smoothstep: gentle takeoff + level-off;
            #                                           with step_m << thickness the ~0.1-0.3 m
            #                                           per-slice height delta hides inside the
            #                                           deck body -> reads as a continuous ramp
            # one ribbon per DIRECTED edge: a two-way bridge splits into two half-width ribbons
            # side by side (each on its travel side, like the flat two-way offset) so hover and
            # select work per edge id, never per whole structure. shapely offset_curve positive
            # = LEFT of the line direction; the with-chain edge drives on the right.
            ribbons = []
            if pp.get("twoway") and ffi is not None and rfi is not None:
                for dlt, fdir in ((-1.0, ffi), (1.0, rfi)):
                    try:
                        ol = part.offset_curve(dlt * half / 2.0)
                    except Exception:
                        continue
                    for ln in ([ol] if ol.geom_type == "LineString" else
                               list(ol.geoms) if ol.geom_type == "MultiLineString" else []):
                        if ln.length > 0:
                            ribbons.append(
                                (ln.buffer(half / 2.0, cap_style=2, join_style=2), fdir))
            else:
                fdir = ffi if ffi is not None else rfi
                ribbons.append((part.buffer(half, cap_style=2, join_style=2), fdir))
            for poly, fdir in ribbons:
                if poly.geom_type != "Polygon":
                    continue
                coords = [[round(x / kx + lon0, 6), round(y / 111320.0 + lat0, 6)]
                          for x, y in poly.exterior.coords]
                props = dict((geo["features"][fdir].get("properties") or pp)
                             if fdir is not None else pp)
                props["__rs_base"] = round(base_m * t, 2)
                props["__rs_height"] = round(base_m * t + thick, 2)
                props["__rs_chain"] = chain_i
                props["__rs_edges"] = str(fdir)   # the ONE directed edge this ribbon belongs to
                feats.append({"type": "Feature", "properties": props,
                              "geometry": {"type": "Polygon", "coordinates": [coords]}})
            # casing: two strips along the deck's LONG sides, topping out just below the deck
            # top — the black rim line casing gives the 2D bridges (extrusions have no stroke).
            # Side strips, NOT a ring around the slice: a ring's transverse ends would draw
            # black cross-bars over the deck at every slice cut (ramps are cut every step_m).
            if dk.get("casing_px"):
                cw = dk["casing_px"] * mpp
                for sgn in (1.0, -1.0):
                    try:
                        sline = part.offset_curve(sgn * (half + cw / 2.0))
                    except Exception:
                        continue
                    parts_ = ([sline] if sline.geom_type == "LineString"
                              else list(sline.geoms) if sline.geom_type == "MultiLineString"
                              else [])
                    for sl in parts_:
                        if sl.length <= 0:
                            continue
                        sp = sl.buffer(cw / 2.0, cap_style=2, join_style=2)
                        for gp in ([sp] if sp.geom_type == "Polygon" else
                                   list(sp.geoms) if sp.geom_type == "MultiPolygon" else []):
                            rings = [gp.exterior.coords] + [i.coords for i in gp.interiors]
                            cc = [[[round(x / kx + lon0, 6), round(y / 111320.0 + lat0, 6)]
                                   for x, y in r] for r in rings]
                            feats.append({"type": "Feature", "properties": {
                                "highway": pp.get("highway"), "__rs_chain": chain_i,
                                "__rs_casing_slab": 1,
                                "__rs_base": round(max(base_m * t - 0.5, 0.0), 2),
                                "__rs_height": round(base_m * t + thick * 0.35, 2)},
                                "geometry": {"type": "Polygon", "coordinates": cc}})
    return {"type": "FeatureCollection", "features": feats}


def _truthy(v):
    return v not in (None, "", "no", "false", "0", 0, False)


def _mark_lvl(geo, tunnel_col, bridge_col, layer_col):
    """Elevation per edge: bridge -> +1 (drawn on top), tunnel -> -1 (drawn underneath), else a
    negative OSM `layer` tag -> -1, else 0. Lets the sort key keep grade-separated roads from
    looking connected. Defaults to 0 when the columns aren't present (no tunnel/bridge info).

    A positive `layer` alone does NOT promote to bridge level: only the bridge column earns the
    bridge treatment (2D deck styling, 3D extrusions) — a `layer=1` embankment isn't a bridge."""
    for ft in geo["features"]:
        p = ft.setdefault("properties", {})
        if _truthy(p.get(bridge_col)):
            lvl = 1
        elif _truthy(p.get(tunnel_col)):
            lvl = -1
        else:
            try:
                lvl = -1 if int(float(p.get(layer_col))) < 0 else 0
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


# tiles=True bootstrap, injected before the main map script: decode the embedded PMTiles
# archive, register the pmtiles:// protocol serving it from memory (must exist before the Map
# is constructed), and asynchronously inflate the sidecar table (full per-edge properties +
# midpoints + bboxes) that keeps rsQuery / popups / rsFocus working without inline GeoJSON.
_TILES_JS = """
<script id="rs-side" type="application/json">__RS_SIDE_B64__</script>
<script>
window.RS_SIDE=null;
(function(){
  var b=atob("__RS_PMTILES_B64__"), arr=new Uint8Array(b.length);
  for(var i=0;i<b.length;i++) arr[i]=b.charCodeAt(i);
  var buf=arr.buffer;
  var src={getKey:function(){return "roads";},
           getBytes:function(o,l){return Promise.resolve({data:buf.slice(o,o+l)});}};
  var proto=new pmtiles.Protocol();
  proto.add(new pmtiles.PMTiles(src));
  maplibregl.addProtocol("pmtiles", proto.tile);
  window.__rs_tiles={ok:true, bytes:arr.length};
  (async function(){
    var el=document.getElementById("rs-side");
    try{
      var s=atob(el.textContent.trim()), a=new Uint8Array(s.length);
      for(var i=0;i<s.length;i++) a[i]=s.charCodeAt(i);
      window.RS_SIDE=await new Response(new Blob([a]).stream()
        .pipeThrough(new DecompressionStream("gzip"))).json();
      el.textContent="";
    }catch(e){ window.__rs_tiles={ok:false, stage:"sidecar", error:String(e)}; }
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
        # mtime=0: no timestamp in the gzip header, so the same map renders byte-identical
        blobs[sid] = base64.b64encode(gzip.compress(raw, 6, mtime=0)).decode()
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
    if not bm.url:                                  # tile-less base map (blank / blank_dark)
        return []
    if "{s}" in bm.url:
        return [bm.url.replace("{s}", s).replace("{r}", "") for s in (bm.subdomains or "a")]
    return [bm.url.replace("{r}", "")]


def _bg_color(bm):
    """The plain canvas colour behind (or instead of) the tiles: ``bm.bg`` when it's a flat
    colour; the thumbnail gradients of the tiled built-ins fall back to a light/dark neutral."""
    return bm.bg if bm.bg.startswith("#") else ("#0e1113" if bm.is_dark else "#e8e6e1")


def _basemap_style(bm):
    """A minimal MapLibre style wrapping a raster base map — or, for a tile-less base map
    (``blank`` / ``blank_dark``), just a background colour: no tile requests, fully offline."""
    style = {"version": 8, "sources": {},
             "layers": [{"id": "bg", "type": "background",
                         "paint": {"background-color": _bg_color(bm)}}]}
    tiles = _tiles(bm)
    if tiles:
        style["sources"]["bm"] = {"type": "raster", "tiles": tiles, "tileSize": 256,
                                  "attribution": bm.attr}
        style["layers"].append({"id": "basemap", "type": "raster", "source": "bm"})
    return style


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
    C = {"color": "#6aa9ff", "radius": 6.0, "width": 2.0, "fill_opacity": 0.15,
         "circle_opacity": 0.85, "line_opacity": 0.9, "outline_opacity": 0.9,
         "circle_stroke": "#ffffff", **(CONFIG.overlays or {})}
    base = ov.color or C["color"]                     # per-Overlay value wins over the setting
    width = C["width"] if ov.width is None else ov.width
    radius = C["radius"] if ov.radius is None else ov.radius
    op = ov.opacity
    interactive = ov.popup is None or bool(ov.popup)
    col = _ov_hl(base, hover_color, select_color, interactive)
    lay = {"visibility": "visible" if getattr(ov, "visible", True) else "none"}
    if kind == "fill":
        return [
            {"id": f"{sid}-fill", "type": "fill", "source": sid, "layout": dict(lay),
             "paint": {"fill-color": col, "fill-opacity": C["fill_opacity"] if op is None else op}},
            {"id": f"{sid}-outline", "type": "line", "source": sid, "layout": dict(lay),
             "paint": {"line-color": ov.outline or base, "line-width": width,
                       "line-opacity": C["outline_opacity"]}},
        ]
    if kind == "circle":
        return [{"id": f"{sid}-circle", "type": "circle", "source": sid, "layout": dict(lay),
                 "paint": {"circle-radius": radius, "circle-color": col,
                           "circle-opacity": C["circle_opacity"] if op is None else op,
                           "circle-stroke-color": C["circle_stroke"], "circle-stroke-width": 1}}]
    return [{"id": f"{sid}-line", "type": "line", "source": sid,
             "layout": {**lay, "line-cap": "round"},
             "paint": {"line-color": col, "line-width": width,
                       "line-opacity": C["line_opacity"] if op is None else op}}]


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


# The page template lives in static/web_template.html (placeholders: __TITLE__, __STYLE__, …)
# so the HTML/JS is editable and lintable as HTML, not as a Python string.
with open(os.path.join(os.path.dirname(__file__), "static", "web_template.html"),
          encoding="utf-8") as _fh:
    _HTML = _fh.read()


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
           color_options=None, color_active=0, overlays=None, compress: bool = True,
           tiles: bool = False,
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
    popup_mode = "popup"
    if road_popup is False:
        popup_on, popup_fields = False, None
    elif road_popup is True:
        popup_on, popup_fields = True, list(DEFAULT_ROAD_POPUP)
    elif road_popup == "panel":                       # docked side panel instead of a popup
        popup_on, popup_fields, popup_mode = True, list(DEFAULT_ROAD_POPUP), "panel"
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
    bms = [{"key": b.key, "label": b.label, "tiles": _tiles(b), "bg": _bg_color(b)}
           for b in (get_basemap(k) for k in bkeys)]
    if not basemap_switcher and not basemaps:
        # no dropdown and no explicit set -> bake only the fixed backdrop. An explicit
        # `basemaps=` list stays fully addressable via window.rsSetBasemap (custom UI).
        bms = bms[:1]
    style = _basemap_style(get_basemap(active))
    if "bm" not in style["sources"]:
        # a blank base map is active but the switcher offers tiled ones: pre-create the raster
        # layer hidden, so switching is a visibility flip (hidden layers fetch no tiles)
        _t = next((b["tiles"] for b in bms if b["tiles"]), None)
        if _t:
            style["sources"]["bm"] = {"type": "raster", "tiles": _t, "tileSize": 256}
            style["layers"].append({"id": "basemap", "type": "raster", "source": "bm",
                                    "layout": {"visibility": "none"}})
    # roads source: inline GeoJSON by default; with `tiles=True` a PMTiles archive embedded in
    # the page instead (MapLibre parses only the tiles in view — the client-side scale path).
    # Feature ids are the feature's index either way (generateId / baked MVT id), so
    # feature-state, rsFilter/rsColor and the sidecar table share one id space.
    _tiler = tc = None
    if tiles:
        try:
            from . import tiles as _tiler
        except ImportError as err:                     # pragma: no cover
            raise ImportError(
                'tiles=True needs the tiles extra: pip install "roadstyle[tiles]"') from err
        tc = {"minzoom": 6, "maxzoom": 15, "extent": 4096, "buffer_px": 80,
              **(CONFIG.tiles or {})}
        # the archive itself is built later, once the annotation slots exist (they ride along
        # as a second tile layer); the source just points at the embedded pmtiles:// protocol
        style["sources"]["roads"] = {"type": "vector", "url": "pmtiles://roads",
                                     "minzoom": tc["minzoom"], "maxzoom": tc["maxzoom"]}
    else:
        # tolerance 0.05 (default 0.375): the source re-tiles at every integer zoom and
        # re-simplifies the geometry — at the default tolerance the roads visibly ripple
        # ("wave") on each zoom crossing. Near-zero simplification keeps zooming smooth;
        # ~5k features can afford it.
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
    dk = {"base_m": 5.0, "thickness_m": 1.0, "ramp_m": 40.0, "step_m": 2.5,
          "match_zoom": 18.0, "opacity": 0.7, "width_scale": 0.6, "flat_below": 16.0,
          "casing_px": 2.0, **(CONFIG.bridge_decks or {})}
    # ONE deck geometry (width anchored at match_zoom, trimmed by width_scale). A fixed polygon
    # can't track the stylized px road widths across zooms — multi-width band variants were
    # tried and looked worse (double-deck halos / width pops), so slightly-narrow-when-zoomed-
    # out is the accepted trade. Tune with bridge_decks.width_scale / match_zoom in settings.
    decks = _bridge_decks(geo, dk) if view_3d else {"features": []}
    if decks["features"]:
        style["sources"]["decks"] = {"type": "geojson", "data": decks, "generateId": True}
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
        # 3D view: below bridge_decks.flat_below the SAME flat lines draw (full stylized width,
        # matching the roads — a fixed deck polygon reads too narrow zoomed out); from
        # flat_below up, the extruded deck ribbons take over (added after this list).
        {"id": "roads-bridge-casing", "type": "line", "source": "roads", "layout": blay,
         "filter": bridge,
         "paint": {"line-color": CONFIG.bridge_casing_color,
                   "line-width": bcw, "line-offset": off}},
        {"id": "roads-bridge-fill", "type": "line", "source": "roads", "layout": lay,
         "filter": bridge,
         "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                   "line-width": fw, "line-offset": off}},
        # hover/select highlight, driven by feature-state set from the viewer (GPU recolour, no relayout)
        {"id": "roads-highlight", "type": "line", "source": "roads", "layout": lay,
         "paint": {
             "line-color": ["case", ["boolean", ["feature-state", "select"], False], select_color, hover_color],
             "line-opacity": ["case", ["any", ["boolean", ["feature-state", "hover"], False],
                                       ["boolean", ["feature-state", "select"], False]], 0.85, 0],
             "line-width": fw, "line-offset": off}},
    ]
    if decks["features"]:
        # 2D flat bridge lines below flat_below, extruded decks from it up — one representation
        # at a time. The flat-line layers (and the bridge slice of the highlight layer) get a
        # maxzoom; the deck layer a matching minzoom.
        _fb = dk["flat_below"]
        for l in style["layers"]:
            if l["id"] in ("roads-bridge-casing", "roads-bridge-fill"):
                l["maxzoom"] = _fb
            elif l["id"] == "roads-highlight":
                # bridges glow on the flat line only while the flat line is shown; the deck
                # carries its own feature-state glow above flat_below
                l["filter"] = ["<", ["coalesce", ["get", "lvl"], 0], 1]
                style["layers"].append(
                    {**l, "id": "roads-highlight-bridge", "maxzoom": _fb,
                     "filter": [">", ["coalesce", ["get", "lvl"], 0], 0]})
                break
        # extruded bridge decks: physical ribbons floating base_m above ground — in the tilted
        # view you look UNDER a bridge and see the roads passing beneath it. The casing ring
        # draws first (below), the body over it.
        style["layers"].append(
            {"id": "roads-deck-casing", "type": "fill-extrusion", "source": "decks",
             "minzoom": _fb, "filter": ["has", "__rs_casing_slab"],
             "paint": {"fill-extrusion-color": CONFIG.bridge_casing_color,
                       "fill-extrusion-base": ["get", "__rs_base"],
                       "fill-extrusion-height": ["get", "__rs_height"],
                       "fill-extrusion-opacity": dk["opacity"]}})
        style["layers"].append(
            {"id": "roads-bridge-decks", "type": "fill-extrusion", "source": "decks",
             "minzoom": _fb, "filter": ["!", ["has", "__rs_casing_slab"]],
             "paint": {"fill-extrusion-color":
                           ["case", ["boolean", ["feature-state", "select"], False], select_color,
                            ["boolean", ["feature-state", "hover"], False], hover_color,
                            ["coalesce", ["get", "__rs_fill"], "#888888"]],
                       "fill-extrusion-base": ["get", "__rs_base"],
                       "fill-extrusion-height": ["get", "__rs_height"],
                       "fill-extrusion-opacity": dk["opacity"]}})

    # per-class dashed fills (footway/path/steps/cycleway …): the styling compiler bakes
    # __rs_dash ("4,4") from the palette, but line-dasharray can't be data-driven — so every
    # distinct dash value gets its own sibling fill layer (butt caps: round caps would seal the
    # gaps), and dashed classes drop out of the solid fill + casing layers (a dash gap must show
    # the ground, not a casing band).
    dashes = sorted({(f.get("properties") or {}).get("__rs_dash")
                     for f in geo["features"]} - {None, ""})
    if dashes:
        nod = ["!", ["has", "__rs_dash"]]
        relayered = []
        for l in style["layers"]:
            relayered.append(l)
            lid, base_f = l["id"], l.get("filter")
            if lid in ("roads-fill", "roads-tunnel-fill", "roads-bridge-fill"):
                for di, ds in enumerate(dashes):
                    relayered.append(
                        {**l, "id": f"{lid}-dash{di}",
                         "layout": {**l.get("layout", {}), "line-cap": "butt"},
                         "filter": ["all", base_f, ["==", ["get", "__rs_dash"], ds]],
                         "paint": {**l["paint"],
                                   "line-dasharray": [float(x) for x in ds.split(",")]}})
                l["filter"] = ["all", base_f, nod]
            elif lid in ("roads-casing", "roads-tunnel-casing", "roads-bridge-casing"):
                l["filter"] = ["all", base_f, nod]
        style["layers"] = relayered

    # oneway direction arrows (on edges with no reverse twin) + line-placed street names, on top.
    # Both read their cosmetics from data/style.json "config" (labels / arrows blocks), so a user
    # roadstyle.json can restyle them without touching the library; missing keys keep the bundled
    # defaults (a partial override dict is fine).
    cam = {"pitch": 0, "bearing": 0, "pitch_3d": 55, "max_pitch": 70, **(CONFIG.camera or {})}
    if view_3d:
        cam["pitch"] = cam["pitch_3d"]     # perspective camera only — no terrain data added
    if pitch is not None:
        cam["pitch"] = pitch
    if bearing is not None:
        cam["bearing"] = bearing
    arw = {"color": "#5b5b5b", "opacity": 0.7, **(CONFIG.arrows or {})}
    lbl = {"color": "#5b5b5b", "halo_color": None, "halo_width": 0, **(CONFIG.labels or {})}
    slot_m = (CONFIG.annotations or {}).get("slot_m", 100)
    slots = {"features": []}
    if arrows or labels:
        slots = _annotation_slots(geo, slot_m)
        if slots["features"]:
            if not tiles:   # tiles=True ships the slots as a layer of the pmtiles archive
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
    classes, seen, swatches = [], set(), {}
    for ft in geo["features"]:
        p_ = ft.get("properties", {})
        c = p_.get(fcol)
        if c and c not in seen:
            seen.add(c)
            classes.append(c)
            swatches[c] = p_.get("__rs_fill") or "#888888"
    classes.sort(key=lambda c: (-ROAD_Z.get(_base(c)[0], 4), c))
    flt = {"on": bool(filter_control and classes), "col": fcol, "classes": classes,
           "swatches": swatches}

    pmt = side = None
    if tiles:
        # labels/arrows read the "slots" layer of the same archive (an inline slots source at
        # 100k+ edges is exactly the bottleneck tiling removes); slots only matter from their
        # symbol minzoom (14) up
        for lyr in style["layers"]:
            if lyr.get("source") == "slots":
                lyr["source"] = "roads"
                lyr["source-layer"] = "slots"
        # every remaining layer on the (now vector) roads source draws the "roads" tile layer
        for lyr in style["layers"]:
            if lyr.get("source") == "roads" and "source-layer" not in lyr:
                lyr["source-layer"] = "roads"
        extra = ([{"name": "slots", "fc": slots, "minzoom": 14}]
                 if slots["features"] else None)
        pmt = _tiler.build_pmtiles(
            geo, class_col=highway_col,
            keep={highway_col, filter_col or highway_col, "twoway", "lvl"},
            minzoom_table=CONFIG.minzoom, minzoom=tc["minzoom"], maxzoom=tc["maxzoom"],
            extent=tc["extent"], buffer_px=tc["buffer_px"], extra_layers=extra)
        side = _tiler.sidecar(geo)

    minx, miny, maxx, maxy = (float(v) for v in g.total_bounds)
    # after every style/filter/bounds decision above — those read the features, the browser never does
    gz = _compress_sources(style) if compress else {}
    html = (_HTML.replace("__TITLE__", _html.escape(name))
            .replace("__ARROW_COLOR__", str(arw["color"]))
            .replace("__STYLE__", json.dumps(style))
            .replace("__BASEMAPS__", json.dumps(bms))
            .replace("__BM_SWITCHER__", json.dumps(bool(basemap_switcher)))
            .replace("__FILTER__", json.dumps(flt))
            .replace("__CENTER__", json.dumps([(minx + maxx) / 2, (miny + maxy) / 2]))
            .replace("__PITCH3D__", json.dumps(cam["pitch_3d"]))
            .replace("__MAX_PITCH__", json.dumps(cam["max_pitch"]))
            .replace("__HOVER_COLOR__", json.dumps(hover_color))
            .replace("__SELECT_COLOR__", json.dumps(select_color))
            .replace("__PITCH__", json.dumps(cam["pitch"]))
            .replace("__BEARING__", json.dumps(cam["bearing"]))
            .replace("__BOUNDS__", json.dumps([[minx, miny], [maxx, maxy]]))
            .replace("__COLOR_OPTIONS__", json.dumps(color_opts_meta or []))
            .replace("__CO_ACTIVE__", str(_active))
            .replace("__OVERLAYS__", json.dumps(ov_meta))
            .replace("__ROAD_POPUP__", "true" if popup_on else "false")
            .replace("__ROAD_POPUP_MODE__", json.dumps(popup_mode))
            .replace("__ROAD_POPUP_FIELDS__", json.dumps(popup_fields))
            .replace("__ROAD_TOOLTIP__", json.dumps(road_tooltip))
            .replace("__RS_TILED__", "true" if tiles else "false"))
    if tiles:
        import base64
        setup = (_TILES_JS.replace("__RS_PMTILES_B64__", base64.b64encode(pmt).decode())
                 .replace("__RS_SIDE_B64__", _tiler._b64gz(side)))
        html = html.replace("<script>__RS_TILES__</script>",
                            "<script>"
                            + _asset("pmtiles.js").replace("</script>", "<\\/script>")
                            + "</script>" + setup, 1)
    else:
        html = html.replace("<script>__RS_TILES__</script>", "", 1)
    if gz:
        html = html.replace("</body>", _INFLATE_JS.replace("__RS_GZ__", json.dumps(gz)) + "</body>", 1)
    # MapLibre stays a placeholder here: WebMap inlines the vendored copy on save (offline file)
    # and swaps in CDN tags for the notebook preview (small enough for notebook output limits).
    return WebMap(html)

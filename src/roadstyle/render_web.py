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
import re
import warnings
from collections.abc import Mapping

from . import _settings
from ._na import missing
from .basemaps import DEFAULT_SWITCHER, get_basemap
from .config import DEFAULT as CONFIG
from .fastjson import fc_dict
from .overlays import Overlay, detect_kind, to_fc
from .palettes import DEFAULT_PALETTE
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
    """symbol-sort-key of the labels: grade (tunnel/bridge) dominates, then road class.

    ``lvl*1000`` puts every tunnel (lvl -1) below every surface road and every bridge (lvl +1)
    above, so a tunnel passing *under* a street no longer looks connected to it; within a grade,
    higher-class roads still draw on top. Links come from the z_order table too: every link below
    every non-link street, as in openstreetmap-carto and every established style
    (docs/design/junction_order.md); a link the table doesn't list sits just under its parent."""
    m = ["match", ["get", col]]
    for c in _CLASSES:
        b, lk = _base(c)
        m += [c, ROAD_Z[c] if c in ROAD_Z else ROAD_Z.get(b, 4) - (0.5 if lk else 0)]
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


def class_width_px(cls, zoom, casing=True):
    """The width a road of class ``cls`` is drawn with at ``zoom``, in pixels: its whole width with the casing (``casing``), or its fill.
    The page's width expression, read at one zoom (linear between its stops, the end values outside); one line per road, no two-way narrowing."""
    e = _width_expr("highway", casing=casing)
    zs, ms = e[3::2], e[4::2]
    def at(m):
        m = m[1] if m[0] == "*" else m                          # ["*", match, two-way case]: the match
        return dict(zip(m[2:-1:2], m[3:-1:2], strict=True)).get(cls, m[-1])
    if zoom <= zs[0]:
        return float(at(ms[0]))
    if zoom >= zs[-1]:
        return float(at(ms[-1]))
    i = max(k for k in range(len(zs)) if zs[k] <= zoom)
    f = (zoom - zs[i]) / (zs[i + 1] - zs[i])
    return float(at(ms[i]) + (at(ms[i + 1]) - at(ms[i])) * f)


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
            m = ["*", m, ["case", ["to-boolean", ["get", "__rs_twoway"]], round(f, 3), 1]]
        e += [z, m]
    return e


def _width_m_expr(col, kind, width_m_zoom=16, bridge_m=0.0, bridge_px=0.0, casing_px=0.0, **kw):
    """_width_expr, but a line with a metre width (``__rs_wm``, _mark_width_m) is drawn at exactly
    that width from ``width_m_zoom`` on (docs/design/metre_widths.md). ``kind``: ``"fill"`` = width
    - 2 casings, ``"casing"`` = the width, ``"wings"`` (bridge casing) = width + 2 casings.

    Base-2 exponential interpolation, so the width is exact between stops too (pixels per metre
    double per zoom). Lines without a metre width keep their class widths, frozen past the last
    class stop as today; the stops go on to 22, MapLibre's max zoom."""
    casing = kind != "fill"
    cls = dict(zip(_ZSTOPS, _width_expr(col, casing=casing, scale=1.25 if kind == "wings" else 1.0, **kw)[4::2],
                   strict=True))
    k = {"fill": -2, "casing": 0, "wings": 2}[kind]
    cm = ["max", ["get", "__rs_cm"], bridge_m] if kind == "wings" and bridge_m else ["get", "__rs_cm"]   # a bridge's deck shows
    w = ["get", "__rs_wm"]
    if casing:      # a two-way pair's one casing (__rs_pair) with metres on both (__rs_twm): both directions, their two casings in the middle once
        w = ["case", ["all", ["to-boolean", ["get", "__rs_pair"]], ["has", "__rs_twm"]], ["+", w, ["get", "__rs_twm"], ["*", -2, ["get", "__rs_cm"]]], w]
    wm = ["max", ["+", w, ["*", k, cm]], 0] if k else w
    e = ["interpolate", ["exponential", 2], ["zoom"]]
    for z in sorted(set(_ZSTOPS) | {width_m_zoom, 22}):
        zz = min(max(z, _ZSTOPS[0]), _ZSTOPS[-1])
        lo, hi = max(s for s in _ZSTOPS if s <= zz), min(s for s in _ZSTOPS if s >= zz)
        c = cls[lo] if lo == hi else ["+", ["*", cls[lo], round((hi - zz) / (hi - lo), 4)],
                                      ["*", cls[hi], round((zz - lo) / (hi - lo), 4)]]
        px = 512 * 2 ** z / 40075016.686                 # pixels per metre at the equator
        m = ["*", wm, round(px, 4)]
        if kind == "casing" and casing_px:      # a casing never thinner than casing_px each side of its fill (0.14 m is under a pixel at zoom 18, 2026-10-10)
            m = ["max", m, ["+", ["*", ["max", ["+", w, ["*", -2, ["get", "__rs_cm"]]], 0], round(px, 4)], 2 * casing_px]]
        if kind == "wings" and bridge_px:       # never thinner than fill + bridge_px each side: metres go sub-pixel zoomed out
            fill = ["max", ["+", ["get", "__rs_wm"], ["*", -2, ["get", "__rs_cm"]]], 0]
            m = ["max", m, ["+", ["*", fill, round(px, 4)], 2 * bridge_px]]
        e += [z, c if z < width_m_zoom else ["case", ["has", "__rs_wm"], m, c]]
    return e


def _mark_width_m(geo, col, casing_m):
    """``__rs_wm`` / ``__rs_cm``: the line's width and casing in metres over cos(latitude), at the
    line's own mean latitude, so ``× 512·2^z / C`` is its width in pixels at zoom z. Only for a
    finite, positive width; any other value keeps the class width."""
    for ft in geo["features"]:
        p, g = ft.setdefault("properties", {}), ft.get("geometry") or {}
        try:
            w = float(p.get(col))
        except (TypeError, ValueError):
            continue
        cs = g.get("coordinates") or []
        pts = [c for part in cs for c in part] if g.get("type") == "MultiLineString" else cs
        if not (w > 0 and math.isfinite(w)) or not pts:
            continue
        sec = 1 / math.cos(math.radians(sum(c[1] for c in pts) / len(pts)))
        p["__rs_wm"], p["__rs_cm"] = round(w * sec, 4), round(casing_m * sec, 4)


def _end_radius_expr(col, casing=False, offset_frac=0.28, offset_zoom=15, split_frac=0.6):
    """circle-radius (px) of a two-way pair's end cap (docs/design/twin_ends.md): the pair's outer
    half-width, i.e. the lane offset (_offset_expr) plus half a lane's width (_width_expr, split to
    ``split_frac`` like a two-way lane), per class, at every zoom stop. So the cap is exactly as
    wide as the two lanes together, with the lane split ramping in from ``offset_zoom``."""
    e = ["interpolate", ["linear"], ["zoom"]]
    for z in _ZSTOPS:
        ramp = 0.0 if z <= offset_zoom else (1.0 if z >= offset_zoom + 2 else (z - offset_zoom) / 2.0)
        f = 1.0 - (1 - split_frac) * ramp            # the lane width factor (_width_expr's split)

        def r(g, lk):
            w = _gwidth(WIDTH[g], HI_RATE[g], z) * (0.6 if lk else 1)
            lane = w * (CASING_RATIO[g] if casing else 1) * f
            return round(w * offset_frac * ramp + lane / 2, 3)
        m = ["match", ["get", col]]
        for c in _CLASSES:
            b, lk = _base(c)
            m += [c, r(ROAD_GROUP.get(b, "residential"), lk)]
        m.append(r("residential", False))
        e += [z, m]
    return e


def _offset_match(col, z, offset_frac=0.28, offset_zoom=15):
    """A two-way direction's offset (px) at zoom ``z``, per class: offset_frac * the road's pixel width, ramped in from offset_zoom."""
    ramp = 0.0 if z <= offset_zoom else (1.0 if z >= offset_zoom + 2 else (z - offset_zoom) / 2.0)
    m = ["match", ["get", col]]
    for c in _CLASSES:
        b, lk = _base(c)
        g = ROAD_GROUP.get(b, "residential")
        w = _gwidth(WIDTH[g], HI_RATE[g], z) * (0.6 if lk else 1)
        m += [c, round(w * offset_frac * ramp, 3)]
    dw = _gwidth(WIDTH["residential"], HI_RATE["residential"], z)
    m.append(round(dw * offset_frac * ramp, 3))
    return m


def _offset_expr(col, offset_frac=0.28, offset_zoom=15, pairs=False, width_m_zoom=None):
    """line-offset (px) = offset_frac * the road's pixel width, for two-way edges (0 for one-way),
    ramped in from offset_zoom. Pixel-proportional -> constant overlap at every zoom. ``pairs``: a two-way pair's one casing
    (``__rs_pair``, :func:`_mark_twin_casing`) is not shifted. From ``width_m_zoom`` on, a direction whose pair has metres on both
    (``__rs_twm``) is shifted by metres: half the other direction's fill, so the two fills together are centred on the line (2026-10-10)."""
    two = ["to-boolean", ["get", "__rs_twoway"]]
    if pairs:
        two = ["all", two, ["!", ["to-boolean", ["get", "__rs_pair"]]]]
    if width_m_zoom is None:
        e = ["interpolate", ["linear"], ["zoom"]]
        for z in _ZSTOPS:
            e += [z, ["case", two, _offset_match(col, z, offset_frac, offset_zoom), 0]]
        return e
    e = ["interpolate", ["exponential", 2], ["zoom"]]          # as _width_m_expr: the metres exact between stops
    for z in sorted(set(_ZSTOPS) | {width_m_zoom, 22}):
        c = _offset_match(col, min(max(z, _ZSTOPS[0]), _ZSTOPS[-1]), offset_frac, offset_zoom)
        if z >= width_m_zoom:
            px = round(512 * 2 ** z / 40075016.686, 4)
            c = ["case", ["has", "__rs_twm"], ["*", ["-", ["*", 0.5, ["get", "__rs_twm"]], ["get", "__rs_cm"]], px], c]
        e += [z, ["case", two, c, 0]]
    return e


def _pair_width(expr, col, offset_frac=0.28, offset_zoom=15, width_m_zoom=None):
    """A casing width curve, with a two-way pair's one casing (``__rs_pair``) as wide as its two directions together: a direction's casing
    width (the two-way width of ``expr``) plus twice the direction's offset, at each stop of the curve (docs/design/twin_ends.md). From
    ``width_m_zoom`` on, a pair with metres on both (``__rs_twm``) has its width in ``expr`` already (_width_m_expr)."""
    def px(z):
        add = ["*", 2, _offset_match(col, min(max(z, _ZSTOPS[0]), _ZSTOPS[-1]), offset_frac, offset_zoom)]
        return ["case", ["has", "__rs_twm"], 0, add] if width_m_zoom is not None and z >= width_m_zoom else add
    return _plus_px(expr, px, when=["to-boolean", ["get", "__rs_pair"]])


def _class_key(v):
    """A road's class as a grouping key: a missing class (None, NaN, "") is one value, so both directions of an unclassed road still pair (NaN != NaN)."""
    return "" if missing(v) else v


def _mark_twoway(geo, directed_col=None, kind_col="highway", driving_col=None):
    """Flag each edge that has a reverse twin (i.e. a two-way street's other direction), so the
    style fans those into two lanes, and each edge that gets a one-way arrow (``__rs_oneway``). Two
    separate questions (2026-10-09): the DRAWING (two directions or one line) is ``directed_col``
    alone; the ARROW is one-way (``oneway``, else no twin) AND driving (``driving_col``, null = driving). The match is DIRECTED — the twin
    must run end->start — and of one kind (``kind_col``): a footway lying on a street the other way
    round is no lane of it (2026-10-07: the street was drawn as one narrow, shifted lane). Two same-direction edges between one node pair (a street split into
    parallel one-way carriageways) are siblings, not a pair: each keeps its arrows."""
    cnt, keys = collections.Counter(), []
    for ft in geo["features"]:
        g = ft.get("geometry") or {}
        c = g.get("coordinates") or []
        if g.get("type") == "LineString" and len(c) >= 2:
            a = (round(c[0][0], 6), round(c[0][1], 6))
            z = (round(c[-1][0], 6), round(c[-1][1], 6))
            k = (a, z, _class_key((ft.get("properties") or {}).get(kind_col)))
        else:
            k = (id(ft), None, None)
        keys.append(k)
        cnt[k] += 1
    for ft, k in zip(geo["features"], keys, strict=False):
        rev = (k[1], k[0], k[2])
        n = cnt.get(rev, 0)
        # a loop edge (start == end) is its own reverse key; it needs a second feature to pair up
        p = ft.setdefault("properties", {})
        p["__rs_twoway"] = n >= 2 if rev == k else n >= 1
        # arrows follow an EXPLICIT `oneway` column when the data has one (undirected networks
        # included); otherwise a one-way edge = an edge with no reverse twin
        ow = p.get("oneway")
        p["__rs_oneway"] = _truthy(ow) if ow is not None else not p["__rs_twoway"]
    if directed_col:
        # a pair is two lanes only when neither edge is undirected (directed_col false: a footway's
        # other direction, a one-way street's walking-only reverse); null = directed. Checked on
        # both edges, so no lane is ever drawn shifted without its twin (docs/design/twin_ends.md).
        # Only directed_col decides the drawing (rs.is_directed: open to cars or bikes, not a path), never driving_col: a one-way
        # street's bus / bike lane the other way is a half of its own, its arrow on the car edge only (2026-10-09)
        und = lambda ft: (ft.get("properties") or {}).get(directed_col) is not None and not _truthy(  # noqa: E731
            ft["properties"][directed_col])
        by = collections.defaultdict(list)
        for ft, k in zip(geo["features"], keys, strict=False):
            by[k].append(ft)
        for ft, k in zip(geo["features"], keys, strict=False):
            p = ft["properties"]
            if p["__rs_twoway"] and (und(ft) or all(und(t) for t in by[(k[1], k[0], k[2])] if t is not ft)):
                p["__rs_twoway"] = False
                if p.get("oneway") is None:      # no `oneway` column: a directed edge with an
                    p["__rs_oneway"] = not und(ft)   # undirected reverse is a one-way road
    if driving_col:      # arrows only on driving edges (null = driving): a one-way edge cars may not drive gets none
        for ft in geo["features"]:
            p = ft["properties"]
            if p.get(driving_col) is not None and not _truthy(p[driving_col]):
                p["__rs_oneway"] = False


def _mark_single_line(geo, kind_col, classes):
    """A reverse pair of a class in ``classes`` (config ``single_line_classes``: a footway, a path ...) is drawn as ONE line at full width, no
    lanes: the later edge of the pair is flagged ``__rs_dup`` (it draws nothing, no piece, no layer feature), the first keeps all the drawing
    and both name each other in ``__rs_edge2`` (their positions in ``geo``: the page's one lookup, the popup, rsFilter, rsColor). The pair has
    no one-way arrows. Matched like :func:`_mark_twoway` (end -> start, one class), but whether the pair is directed does not matter."""
    first = {}
    for i, ft in enumerate(geo["features"]):
        p, g = ft.setdefault("properties", {}), ft.get("geometry") or {}
        c = g.get("coordinates") or []
        if p.get(kind_col) not in classes or g.get("type") != "LineString" or len(c) < 2:
            continue
        a, z = (round(c[0][0], 6), round(c[0][1], 6)), (round(c[-1][0], 6), round(c[-1][1], 6))
        j = first.pop((z, a, p[kind_col]), None)
        if j is None:
            first.setdefault((a, z, p[kind_col]), i)
            continue
        q = geo["features"][j]["properties"]
        p["__rs_dup"], p["__rs_edge2"], q["__rs_edge2"] = True, j, i
        for r in (p, q):
            r["__rs_twoway"] = r["__rs_oneway"] = False


def _mark_twin_casing(geo, kind_col, id_col=None, head_m=5.0):
    """Config ``twin_casing`` "one" (2026-10-08): a two-way road given as two directed edges (``__rs_twoway``, :func:`_mark_twoway`) has ONE
    casing around both directions, drawn once at the pair's full width, unshifted; each direction keeps its own fill. Pairs each two-way edge
    with one reverse edge of its class whose line is its own line backwards (two different lines between the same two points are two roads:
    each keeps its own casing) and sets ``__rs_twin`` (the other edge's position in ``geo``) on both: :func:`_casing_parts` cuts the casing
    of the first of the two only, from its own numbers, heads and caps (its start is the other's end). The two must agree, reversed:
    casing numbers (start head, main, end head), head lengths and end shapes; a pair that does not is named in a warning (the first
    edge's are drawn). Returns whether any pair was found."""
    first, bad, found = {}, [], False
    for i, ft in enumerate(geo["features"]):
        p, g = ft["properties"], ft.get("geometry") or {}
        c = g.get("coordinates") or []
        if not p.get("__rs_twoway") or g.get("type") != "LineString" or len(c) < 2:
            continue
        line = tuple((round(x[0], 7), round(x[1], 7)) for x in c)
        j = first.pop((line[::-1], _class_key(p.get(kind_col))), None)
        if j is None:
            first.setdefault((line, _class_key(p.get(kind_col))), i)
            continue
        q = geo["features"][j]["properties"]
        p["__rs_twin"], q["__rs_twin"] = j, i
        found = True
        def ends(r):            # (start, end) of each: casing number, head length, end shape
            whole = r.get("__rs_cap")
            return ((r["__rs_cs"], r.get("__rs_hs", head_m), r.get("__rs_cap0", whole)), (r["__rs_ce"], r.get("__rs_he", head_m), r.get("__rs_cap1", whole)))
        if (ends(q), q["__rs_cl"]) != (ends(p)[::-1], p["__rs_cl"]):
            bad.append((q.get(id_col, j) if id_col else j, p.get(id_col, i) if id_col else i))
    if bad:
        warnings.warn(f"twin_casing: {len(bad)} two-way pair(s) whose two directions disagree on their casing numbers, heads or end shapes "
                      f"(reversed); the first edge of each is drawn: " + ", ".join(f"{a} / {b}" for a, b in bad[:10]) + (" ..." if len(bad) > 10 else ""),
                      stacklevel=3)
    return found


_NAME_MARGIN_M = 2.0       # names and arrows stay this far (metres) beyond a crossing road's drawn half-width
_ZEBRA_HALF_M = 2.0        # ... and at least this far from a footway or path line: a zebra's stripes are about 4 m wide along the street
_ARROW_MIN_M = 8.0         # a one-way stretch too short for a name slot (20 % of slot_m) still gets an arrow slot from this length (2026-10-09)


def _crossing_half_m(cls, lat):
    """How far along a street a name or arrow keeps from a road crossing or joining it: half that road's drawn width (with casing) at zoom 20,
    in metres at latitude ``lat`` (a footway, path, cycleway or steps: at least a zebra's half-width), plus _NAME_MARGIN_M."""
    half = 0.5 * class_width_px(cls, 20) * 40075016.686 * math.cos(math.radians(lat)) / (512 * 2 ** 20)
    return (max(half, _ZEBRA_HALF_M) if cls in ("footway", "path", "cycleway", "steps") else half) + _NAME_MARGIN_M


def _annotation_slots(geo, slot_m, class_col="highway"):
    """Divide every road chain into equal ``slot_m``-metre slots — the annotation plan.

    Chains walk same-name, same-grade, same-directionness edges through degree-2 nodes (a two-way
    street's reverse twin is skipped — its twin carries the geometry). Slots are indexed 0..
    along the chain; street names take the even slots and one-way arrows the odd ones, so the two
    alternate along the road and can never stack. Symbol zoom ramps + collision culling handle
    density per zoom automatically. Unnamed roads leave their name slots empty. Returns a
    FeatureCollection of slot pieces: {slot, chain, name, highway, oneway}; ``chain`` numbers the chain a piece is part of (the page
    puts one arrow on the visible part of each one-way chain, docs/design/arrows_and_names.md).
    """
    import numpy as np
    import shapely
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    all_lines = [None] * len(geo["features"])          # every road's line, twins and footways too: what a name or arrow keeps away from
    for i, ft in enumerate(geo["features"]):
        g = ft.get("geometry") or {}
        if g.get("type") == "LineString" and len(g.get("coordinates") or []) >= 2:
            all_lines[i] = LineString([c[:2] for c in g["coordinates"]])
    all_tree = STRtree(all_lines)
    reps = []                                    # (start, end, coords, props), twins collapsed
    by_ends, owner = {}, {}                      # (start, end) -> feature index; id(props) -> (feature index, its twin's index): the road a slot belongs to
    lines = []
    for i, ft in enumerate(geo["features"]):
        g, p = ft.get("geometry") or {}, ft.get("properties", {})
        c = g.get("coordinates") or []
        if g.get("type") != "LineString" or len(c) < 2:
            continue
        a = (round(c[0][0], 6), round(c[0][1], 6))
        z = (round(c[-1][0], 6), round(c[-1][1], 6))
        by_ends[(a, z, _class_key(p.get(class_col)))] = i               # with the class: a footway on a street the other way round is not its twin
        lines.append((i, a, z, c, p))
    for i, a, z, c, p in lines:
        if p.get("__rs_dup"):
            continue
        if p.get("__rs_twoway"):
            # a two-direction pair has one representative: its one-way direction when only one is (cars one way, a bus / bike lane the
            # other: the arrow is that edge's, pointing its way; the page puts it in that edge's half, _rsArrowLane), else the edge
            # with the lower ends
            j = by_ends.get((z, a, _class_key(p.get(class_col))))
            q = geo["features"][j]["properties"] if j is not None else {}
            if (not q.get("__rs_oneway"), (z, a)) < (not p.get("__rs_oneway"), (a, z)):
                continue
        reps.append((a, z, c, p))
        owner[id(p)] = (i, by_ends.get((z, a, _class_key(p.get(class_col)))) if p.get("__rs_twoway") else p.get("__rs_edge2"))

    # class is part of the key: a cycleway running along "Götgatan" carries the street's name
    # too, and without the class it chained INTO the roadway's group — slots then labelled the
    # street's class onto the cycleway's geometry and vice versa, so names and arrows appeared
    # to sit on the wrong line.
    groups = collections.defaultdict(list)       # (name, lvl, oneway, class) -> edge list
    for e in reps:
        p = e[3]
        groups[(p.get("name") or None, p.get("lvl", 0),
                1 if p.get("__rs_oneway") else 0, _class_key(p.get(class_col)), p.get("__rs_fl"), bool(p.get("__rs_tunnel")))].append(e)

    feats, cid = [], 0
    for (name, lvl, oneway, _cls, fl, tun), edges in groups.items():
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
            members.append(start)
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
                        members.append(j)
                        chain = seg[:-1] + chain
                    else:                        # need a segment STARTING at the chain tail
                        if ja == node:
                            seg, nxt = jc, jz
                        elif not oneway:
                            seg, nxt = jc[::-1], ja
                        else:
                            break
                        used[j] = True
                        members.append(j)
                        chain = chain + seg[1:]
                    node = nxt
            return chain

        chains = []
        for i in range(n):
            if not used[i]:
                members = []
                chains.append((walk(i), members))
        etree = STRtree([LineString(e[2]) for e in edges]) if n > 1 else None          # which edge of the group a slot lies on (a group of one edge: that edge)
        # the caller's class column ("highway" only by convention — e.g. Overture data styles by
        # "class"); stored under the slots' own fixed "highway" key either way, which is what the
        # arrow/label minzoom filters and sort keys read. Hardcoding the lookup dropped the
        # property entirely on non-"highway" data (None is stripped), silently disabling both.
        hw = collections.Counter(e[3].get(class_col) for e in edges).most_common(1)[0][0]
        for chain, members in chains:
            cid += 1
            lon0, lat0 = chain[0]
            kx = 111320.0 * math.cos(math.radians(lat0))
            ch = np.asarray(chain, dtype=float)
            xy = np.column_stack([(ch[:, 0] - lon0) * kx, (ch[:, 1] - lat0) * 111320.0])
            cum = _cum_lengths(xy)
            total = float(cum[-1])

            # the stretches of the chain between its crossings: every other road's line that meets or crosses it (a junction, a bridge or tunnel
            # over it, a zebra) takes half its drawn width plus a margin out of the chain, so no name or arrow sits across a crossing
            mine = {k for e in members for k in owner[id(edges[e][3])] if k is not None}
            chain_ll, local = LineString(chain), LineString(xy)
            # an edge lying on a member's line the other way round (a one-way street's walking-only reverse) is no crossing
            back = {tuple(map(tuple, edges[e][2]))[::-1] for e in members}
            cuts = []
            for k in all_tree.query(chain_ll):
                k = int(k)
                if k in mine or tuple((x[0], x[1]) for x in geo["features"][k]["geometry"]["coordinates"]) in back:
                    continue
                hit = chain_ll.intersection(all_lines[k])
                if hit.is_empty:
                    continue
                half = _crossing_half_m(geo["features"][k]["properties"].get(class_col), lat0)
                for part in shapely.get_parts(hit):
                    d = [local.project(Point((x - lon0) * kx, (y - lat0) * 111320.0)) for x, y in shapely.get_coordinates(part)]
                    cuts.append((min(d) - half, max(d) + half))
            free, at_ = [], 0.0
            for lo, hi in sorted(cuts):
                if lo > at_:
                    free.append((at_, lo))
                at_ = max(at_, hi)
            if at_ < total:
                free.append((at_, total))
            nxt = 0
            for lo, hi in free:         # each stretch is divided into slots on its own, starting with a name slot (an even number)
                nxt += nxt % 2
                length = hi - lo
                pieces = max(1, int(length // slot_m) + (1 if length % slot_m > slot_m * 0.3 else 0))
                for j in range(pieces):
                    a, b = lo + j * slot_m, lo + min((j + 1) * slot_m, length)
                    if b - a < slot_m * 0.2:
                        if not (oneway and b - a >= _ARROW_MIN_M):
                            continue
                        nxt += 1 - nxt % 2          # too short for a name, long enough for an arrow: an arrow slot (an odd number)
                    i, nxt = nxt, nxt + 1
                    pts = _part(xy, cum, a, b)
                    coords = np.column_stack([np.round(pts[:, 0] / kx + lon0, 6), np.round(pts[:, 1] / 111320.0 + lat0, 6)]).tolist()
                    if etree is None:
                        road, twin = owner[id(edges[0][3])]
                    else:
                        mx, my = _at(xy, cum, (a + b) / 2)
                        road, twin = owner[id(edges[int(etree.nearest(Point(mx / kx + lon0, my / 111320.0 + lat0)))][3])]
                    feats.append({"type": "Feature",
                                  "properties": {"slot": i, "chain": cid, "rank": ROAD_Z.get(hw, 0), "name": name, "highway": hw,
                                                 "oneway": oneway, "lvl": lvl, "__rs_edge": road,
                                                 **({"__rs_edge2": twin} if twin is not None else {}),
                                                 **({"fl": fl} if fl is not None else {}),
                                                 **({"__rs_tunnel": True} if tun else {})},
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
        # any bridge level (lvl carries the OSM layer: 1, 2, 3…) earns a deck ribbon
        if not p.get("__rs_bridge") or (p.get("lvl") or 0) < 1 or g.get("type") != "LineString" or len(c) < 2:
            continue
        a = (round(c[0][0], 6), round(c[0][1], 6))
        z = (round(c[-1][0], 6), round(c[-1][1], 6))
        pair_edges[min((a, z), (z, a))].append(fi)
        if (p.get("__rs_twoway") and (z, a) < (a, z)) or p.get("__rs_dup"):
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
            if pp.get("__rs_twoway") and ffi is not None and rfi is not None:
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
                props["__rs_edges"] = [fdir] if fdir is not None else []   # the ONE directed edge this ribbon belongs to (a list, like every multi-edge piece)
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
                                "__rs_casing_slab": 1, "__rs_edges": sorted({f for _, f in ribbons if f is not None}),
                                "__rs_base": round(max(base_m * t - 0.5, 0.0), 2),
                                "__rs_height": round(base_m * t + thick * 0.35, 2)},
                                "geometry": {"type": "Polygon", "coordinates": cc}})
    return {"type": "FeatureCollection", "features": feats}


def _truthy(v):
    return not missing(v) and v not in ("", "no", "false", "0", 0, False)


def _mark_lvl(geo, tunnel_col, bridge_col, layer_col):
    """Draw order per edge (``lvl``), from the OSM ``layer`` tag, OSM's own vertical order where ways
    cross: a tagged non-zero ``layer`` is the level; untagged (or 0), a bridge is 1, a tunnel -1,
    anything else 0. Carrying the layer number (not just ±1) lets the sort key order STACKED
    structures: a viaduct at layer=3 draws over a footbridge at layer=1.

    The LOOK comes from the tags, separately: ``__rs_bridge`` / ``__rs_tunnel`` pick the deck and
    tunnel styling (and 3D decks). A raised walkway (``layer=1``, no bridge tag) is drawn above
    the street it crosses, in the plain look; a road with a negative layer and no tunnel tag is
    drawn below, plain. Defaults to 0 when the columns aren't present."""
    for ft in geo["features"]:
        p = ft.setdefault("properties", {})
        try:
            ly = int(float(p.get(layer_col)))
        except (TypeError, ValueError):
            ly = 0
        br, tu = _truthy(p.get(bridge_col)), _truthy(p.get(tunnel_col))
        p["lvl"] = ly or (1 if br else -1 if tu else 0)
        p["__rs_bridge"], p["__rs_tunnel"] = br, tu


def _mark_levels(geo, casing_col, fill_col, start_col=None, end_col=None):
    """``__rs_cl`` / ``__rs_fl``: the drawing-order positions of an edge's casing and fill (integers, null = 0), and band 0 for every
    edge (a bridge too), so the surface layers are the ones drawn per position. Returns the sorted positions that occur (0 always)."""
    def num(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0
        return 0 if math.isnan(v) else int(round(v))
    levels = {0}
    for ft in geo["features"]:
        p = ft["properties"]
        c, f = num(p.get(casing_col)) if casing_col else 0, num(p.get(fill_col)) if fill_col else 0
        c, f = min(c, f), max(c, f)
        cs = min(num(p.get(start_col)), f) if start_col else c          # the casing numbers of the two heads (default: the main one)
        ce = min(num(p.get(end_col)), f) if end_col else c
        p["__rs_cl"], p["__rs_fl"], p["__rs_cs"], p["__rs_ce"] = c, f, cs, ce
        p["__rs_band"] = 0
        levels |= {c, f, cs, ce}
    return sorted(levels)


def _cum_lengths(xy):
    """The cumulative lengths along a polyline (n x 2 array, metres), starting at 0."""
    import numpy as np
    return np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]


def _at(xy, cum, d):
    """The point of the polyline ``xy`` (cumulative lengths ``cum``) at the distance ``d``."""
    import numpy as np
    j = min(max(int(np.searchsorted(cum, d, side="right")) - 1, 0), len(cum) - 2)
    w = cum[j + 1] - cum[j]
    return xy[j] + ((d - cum[j]) / w if w > 0 else 0.0) * (xy[j + 1] - xy[j])


def _part(xy, cum, a, b):
    """The points of the polyline ``xy`` (cumulative lengths ``cum``) between the distances ``a`` and ``b`` (``a < b``), as an array: the cut points and the vertices
    between them. The same line as ``shapely.ops.substring``, without building geometries (it is the slow part of the casing pieces and the annotation slots)."""
    import numpy as np
    return np.vstack([_at(xy, cum, a), xy[np.searchsorted(cum, a, side="right"):np.searchsorted(cum, b, side="left")], _at(xy, cum, b)])


_SEAM_M = 0.5        # a seam reaches this far each way from its cut, at most a quarter of either piece (see _casing_parts)
_LAP_M = 2.0         # a lap (the flat seam below _SEAM_MINZOOM) reaches this far each way, at most half of either piece


def _casing_parts(geo, head_m, cols):
    """The casing of every edge as pieces, for its own source (docs/design/levels_split_casing.md): an edge whose
    three casing numbers (``__rs_cs`` start head, ``__rs_cl`` main, ``__rs_ce`` end head) are not all equal is cut into the first ``head_m`` metres,
    the middle and the last ``head_m`` metres, each with its own ``__rs_cl`` (a road shorter than ``2 * head_m``: two halves, docs/design/short_road_heads.md); any other edge is one piece. A piece carries the properties the casing
    layers read (``__rs_*`` except the fills, ``cols``, ``lvl``) and ``__rs_edge``, the id of its edge."""
    import numpy as np
    keep = {c for c in cols if c} | {"lvl"}
    out = []
    for i, ft in enumerate(geo["features"]):
        p, g = ft["properties"], ft.get("geometry") or {}
        if p.get("__rs_dup"):                           # one line for a reverse pair (_mark_single_line): its twin draws it
            continue
        base = {k: v for k, v in p.items() if (k in keep or k.startswith("__rs_")) and not k.startswith("__rs_fill")}
        base["__rs_edge"] = p.get("__rs_edge", i)      # render numbers the roads (a part of them: render(_edges=...) keeps their numbers)
        tw = p.get("__rs_twin")
        if tw is not None:                              # a two-way pair's one casing (_mark_twin_casing): the first edge's pieces, full width,
            if tw < base["__rs_edge"]:                  # unshifted (__rs_pair), shown while either edge is (__rs_edge2); the other edge has none
                continue
            base["__rs_pair"], base["__rs_edge2"] = True, tw
        cs, cm, ce = p["__rs_cs"], p["__rs_cl"], p["__rs_ce"]
        c = g.get("coordinates") or []
        split = p.get("__rs_split")
        if g.get("type") != "LineString" or len(c) < 2 or (cs == cm == ce and not split):
            out.append({"type": "Feature", "properties": base, "geometry": g})
            continue
        lon0, lat0 = c[0][0], c[0][1]
        kx, ky = 111320.0 * math.cos(math.radians(lat0)), 111320.0
        xy = np.asarray([(x - lon0) * kx for x, y, *_ in c]), np.asarray([(y - lat0) * ky for x, y, *_ in c])
        xy = np.column_stack(xy)
        cum = _cum_lengths(xy)
        n = float(cum[-1])
        h0, h1 = p.get("__rs_hs", head_m), p.get("__rs_he", head_m)       # this edge's head lengths (head_start_m_col / head_end_m_col)
        if h0 + h1 >= n - 0.05:         # a short road (or main part under 5 cm) is two pieces, one at each head's number, cut in the heads' ratio (docs/design/short_road_heads.md)
            h0, h1 = n * h0 / (h0 + h1), n * h1 / (h0 + h1)
        cuts = [(0.0, h0, cs), (h0, n - h1, cm), (n - h1, n, ce)]
        for k, (a, b, num) in enumerate(cuts):
            pts = _part(xy, cum, a, b)
            if len(pts) < 2 or not (np.diff(pts, axis=0) != 0).any():
                continue
            coords = np.column_stack([np.round(pts[:, 0] / kx + lon0, 7), np.round(pts[:, 1] / ky + lat0, 7)]).tolist()
            flat = {"__rs_cap": True, "__rs_main": True} if k == 1 else {}   # the main piece ends at two cuts: flat ends (a round end would reach into the heads)
            if split and k != 1:                                # a head of an edge with two different ends: that end's cap
                flat = {"__rs_cap": p["__rs_cap0" if k == 0 else "__rs_cap1"]}
            q = {**base, "__rs_cl": num, **flat}
            if q.get("__rs_cap") is None:
                q.pop("__rs_cap", None)
            out.append({"type": "Feature", "properties": q, "geometry": {"type": "LineString", "coordinates": coords}})
        # a seam at each cut inside the edge: a round dot of casing at the lower of the two pieces' numbers. Two pieces ending flat at a cut
        # on a curve left a wedge open in the outline (2026-10-06: "not smooth in the middle"); the piece drawn above covers the rest.
        # Up to 0.5 m each way (a quarter of the shorter side at most): a 2 cm seam fell on one or two steps of the map's tile grid
        # (about 1.3 cm), lost its direction and was drawn as a square block sticking out of the outline at zoom 21 (2026-10-08)
        cut_at = sorted({h0, n - h1} - {0.0, n})
        for c in cut_at:
            near = [(a, b, num) for a, b, num in cuts if b - a > 1e-9 and (abs(b - c) < 1e-9 or abs(a - c) < 1e-9)]
            sides = [num for a, b, num in near]
            half = min([_SEAM_M] + [(b - a) / 4 for a, b, num in near])
            pts = _part(xy, cum, max(0.0, c - half), min(n, c + half))
            if len(sides) < 2 or len(pts) < 2:
                continue
            coords = np.column_stack([np.round(pts[:, 0] / kx + lon0, 8), np.round(pts[:, 1] / ky + lat0, 8)]).tolist()
            q = {**base, "__rs_cl": min(sides), "__rs_seam": True}
            q.pop("__rs_cap", None)
            out.append({"type": "Feature", "properties": q, "geometry": {"type": "LineString", "coordinates": coords}})
            # below _SEAM_MINZOOM a lap instead (2026-10-08): flat, up to _LAP_M each way (half of either piece at most). The two flat ends
            # at a cut take their directions from their own pieces' segments after the map snaps them to its tile grid (22 cm at zoom 14,
            # 5 cm at 16), so they stand a few degrees apart and a thin gap opens across the outline; a lap at the lower number lies across it.
            # None on a dashed or tunnel casing: a solid lap would fill its gaps
            if base.get("__rs_dash") or base.get("__rs_tunnel"):
                continue
            half = min([_LAP_M] + [(b - a) / 2 for a, b, num in near])
            pts = _part(xy, cum, max(0.0, c - half), min(n, c + half))
            coords = np.column_stack([np.round(pts[:, 0] / kx + lon0, 7), np.round(pts[:, 1] / ky + lat0, 7)]).tolist()
            out.append({"type": "Feature", "properties": {**q, "__rs_cap": True, "__rs_lap": True}, "geometry": {"type": "LineString", "coordinates": coords}})
    return out


# street names: 9/10 of the road's fill width, at most the old 10 -> 14 px ramp, and none where that is under 8 px (2026-10-07: 3/4 and
# 9 px left the names of tertiary and residential streets out until zoom 18; now from 17)
_LABEL_FRACTION, _LABEL_MIN_PX = 0.9, 8.0


def _label_base_px(z):
    return 10.0 + 4.0 * min(max((z - 14.0) / 4.0, 0.0), 1.0)         # the size every name had: 10 px at z14 to 14 px at z18


def _label_px(cls, z):
    return min(_label_base_px(z), _LABEL_FRACTION * class_width_px(cls, z, casing=False))


def _label_size_expr():
    """text-size: a name's size follows its road's fill width (a name as tall as a narrow road touched its outline), at most the old ramp."""
    e = ["interpolate", ["linear"], ["zoom"]]
    for z in sorted({z for z in _ZSTOPS if z >= 14} | {14, 18}):
        m = ["match", ["get", "highway"]]
        for c in _CLASSES:
            m += [c, round(_label_px(c, z), 2)]
        e += [z, m + [round(_label_px(None, z), 2)]]
    return e


def _label_readable_filter():
    """The first whole zoom from which a class's name is at least _LABEL_MIN_PX tall (filters see whole zooms): no tiny name below it."""
    m = ["match", ["get", "highway"]]
    first = lambda c: next((z for z in range(0, 23) if _label_px(c, z) >= _LABEL_MIN_PX), 99)          # noqa: E731
    for c in _CLASSES:
        m += [c, first(c)]
    return [">=", ["zoom"], m + [first(None)]]


_SEAM_MINZOOM = 17      # the casing seams (2026-10-06): a primary's casing is 12 m wide on the ground at zoom 16, so a seam reaches past a head


def _seam_filter():
    """The casing seams' filter: every piece, the round seams from _SEAM_MINZOOM, the flat laps below it (_casing_parts)."""
    seam, lap = ["to-boolean", ["get", "__rs_seam"]], ["to-boolean", ["get", "__rs_lap"]]
    return ["any", ["!", seam], ["all", ["!", lap], [">=", ["zoom"], _SEAM_MINZOOM]], ["all", lap, ["<", ["zoom"], _SEAM_MINZOOM]]]


def _bridge_shadows(geo, parts, highway_col, trim_m, max_turn=45.0):
    """The bridge shadow (2026-10-06), an extra casing: every part of a bridge (start head, main part, end head: ``parts``, the divided
    casing; undivided, each edge) casts its shadow at its own casing number, so it is over what the part crosses and under what its head joins
    (never on its own road at a joint); the parts at one number that touch are joined into one line, and where three or more meet the two
    going on most straight (turning ``max_turn`` degrees at most) at one number go on through; no shadow over the last ``trim_m`` metres where
    the bridge comes down to the road. Lines meet end to end (flat ends). Each line has its widest class."""
    import numpy as np
    import shapely
    from shapely.ops import linemerge, unary_union
    order = list(_CLASSES)
    feats = geo["features"]
    br = [i for i, ft in enumerate(feats) if ft["properties"].get("__rs_bridge") and (ft.get("geometry") or {}).get("type") == "LineString"]
    if not br:
        return []
    line = {i: shapely.LineString([c[:2] for c in feats[i]["geometry"]["coordinates"]]) for i in br}
    tree = shapely.STRtree([line[i] for i in br])
    def at(p):                                                 # the bridge edges at a point
        return [br[k] for k in tree.query(p.buffer(1e-7)) if line[br[k]].distance(p) < 1e-7]
    # every part of a bridge casts its shadow at its own casing number, like its casing (2026-10-06: "there is no better option"): the
    # casing pieces (start head, main part, end head; ``parts``, the divided casing) or, undivided, each edge at its number; the parts at
    # one number that touch are joined into one line
    bset = set(br)
    if parts is not None:
        pieces = [(f["properties"].get("__rs_cl", 0), shapely.LineString([c[:2] for c in f["geometry"]["coordinates"]])) for f in parts
                  if f["properties"].get("__rs_edge") in bset and not f["properties"].get("__rs_seam")]
    else:
        pieces = [(feats[i]["properties"].get("__rs_cl", 0), line[i]) for i in br]
    chains, clvl = [], []
    for lvl in sorted({lv for lv, _ in pieces}):
        u = unary_union([g for lv, g in pieces if lv == lvl])  # also drops a two-way bridge's second direction
        merged = linemerge(u) if u.geom_type == "MultiLineString" else u
        for ch in (merged.geoms if hasattr(merged, "geoms") else [merged]):
            chains.append(list(ch.coords))
            clvl.append(lvl)
    key = lambda xy: (round(xy[0], 7), round(xy[1], 7))                                    # noqa: E731
    kx0 = math.cos(math.radians(chains[0][0][1]))
    def heading(c, end):                                       # leaving the node along the chain
        a, b = (c[0], c[1]) if end == 0 else (c[-1], c[-2])
        return math.atan2(b[1] - a[1], (b[0] - a[0]) * kx0)
    node = {}
    for k, c in enumerate(chains):
        for end in (0, -1):
            node.setdefault(key(c[end]), []).append((k, end))
    near = {i: line[i].buffer(1e-7) for i in br}               # with a tolerance: the union nodes the lines and moves their points a hair
    link = {}                                                  # (chain, end) -> (chain, end) it goes on into through a junction
    for here in node.values():
        if len(here) < 3:
            continue
        free = list(here)
        while len(free) >= 2:
            best = None
            for x in range(len(free)):
                for y in range(x + 1, len(free)):
                    (k1, e1), (k2, e2) = free[x], free[y]
                    if k1 == k2 or clvl[k1] != clvl[k2]:      # only at one number: joined, a chain would take the other's lower one
                        continue
                    turn = 180 - abs((math.degrees(heading(chains[k1], e1) - heading(chains[k2], e2)) + 180) % 360 - 180)
                    if turn <= max_turn and (best is None or turn < best[0]):
                        best = (turn, x, y)
            if best is None:
                break
            _, x, y = best
            link[free[x]], link[free[y]] = free[y], free[x]
            free = [f for j, f in enumerate(free) if j not in (x, y)]
    lines, seen = [], set()                                    # walk each run of linked chains into one line
    for k in range(len(chains)):
        if k in seen:
            continue
        start, end = k, 0                                      # go back to the first chain of the run
        guard = 0
        while (start, end) in link and guard < len(chains):
            nk, ne = link[(start, end)]
            if nk == k:
                break
            start, end = nk, (-1 if ne == 0 else 0)
            guard += 1
        coords, ck, entry = [], start, end                     # entry: the end of chain ck the run comes in by
        while ck is not None and ck not in seen:
            seen.add(ck)
            c = chains[ck] if entry == 0 else chains[ck][::-1]
            coords += c if not coords else c[1:]
            out_end = -1 if entry == 0 else 0
            nxt = link.get((ck, out_end))
            ck, entry = (nxt if nxt else (None, None))
        lines.append((coords, clvl[start]))
    out = []
    for c, lvl in lines:
        ch = shapely.LineString(c)
        member = [i for i in br if ch.intersection(near[i]).length > 1e-6]
        if not member:
            continue
        def cut(xy):                                           # metres to leave out at this line end: the head where the bridge comes down
            p = shapely.Point(xy)
            here = at(p)
            ends = [i for i in here if min(shapely.Point(line[i].coords[0]).distance(p), shapely.Point(line[i].coords[-1]).distance(p)) < 1e-7]
            if len(ends) != len(here) or not here:            # inside an edge (a cut between its head and main part): no trim
                return 0.0
            if len({frozenset([tuple(line[i].coords[0]), tuple(line[i].coords[-1])]) for i in here}) > 1:
                return 0.0                                     # another bridge edge goes on from here
            return trim_m                                      # a fixed few metres, not the head: a long head left a short bridge almost no shadow
        lon0, lat0 = c[0]
        kx, ky = 111320.0 * math.cos(math.radians(lat0)), 111320.0
        xy = np.column_stack([np.asarray([(x - lon0) * kx for x, _ in c]), np.asarray([(y - lat0) * ky for _, y in c])])
        cum = _cum_lengths(xy)
        n = float(cum[-1])
        keep = [(cut(c[0]), n - cut(c[-1]))]                   # 3 m off where the bridge comes down to the road
        for a, b in keep:
            if b - a <= 0.5:
                continue
            pts = _part(xy, cum, a, b)
            cls = min((feats[i]["properties"].get(highway_col) for i in member), key=lambda v: order.index(v) if v in order else len(order))
            out.append({"type": "Feature", "properties": {highway_col: cls, "__rs_cl": lvl, "__rs_fl": lvl, "__rs_edges": sorted(member)},
                        "geometry": {"type": "LineString", "coordinates": np.column_stack([np.round(pts[:, 0] / kx + lon0, 7),
                                                                                          np.round(pts[:, 1] / ky + lat0, 7)]).tolist()}})
    return out


def _cap_value(v):
    """One end's cap from a column value: "square" (flat, as long as a round end), True (flat, at the end point) or None (round)."""
    if isinstance(v, str) and v.strip().lower() in ("square", "round"):
        return "square" if v.strip().lower() == "square" else None
    return True if _truthy(v) else None


def _mark_caps(geo, cap_col=None, start_col=None, end_col=None):
    """``__rs_cap`` from ``cap_col`` (docs/design/square_ends.md): ``"square"`` -> "square" (a flat end as long as a round one), any other
    true value -> True (flat, at the end point). ``start_col`` / ``end_col`` set one end each (null: ``cap_col``'s); an edge whose two ends
    differ gets ``__rs_cap0`` / ``__rs_cap1`` and ``__rs_split`` instead (drawn in two halves, :func:`_halves`). Nothing baked for round."""
    for ft in geo["features"]:
        p = ft["properties"]
        whole = _cap_value(p.get(cap_col)) if cap_col else None
        s0 = _cap_value(p[start_col]) if start_col and p.get(start_col) is not None and p.get(start_col) == p.get(start_col) else whole
        s1 = _cap_value(p[end_col]) if end_col and p.get(end_col) is not None and p.get(end_col) == p.get(end_col) else whole
        if s0 == s1:
            if s0 is not None:
                p["__rs_cap"] = s0
        else:
            p["__rs_cap0"], p["__rs_cap1"], p["__rs_split"] = s0, s1, True


def _mark_twin_dead_ends(geo, cap_col=None, start_col=None, end_col=None):
    """Config ``twin_casing`` "one": a twin pair's dead end is SQUARE (one casing round both directions + two half-width round fills leave a notch
    at the tip), for the casing and both fills, wherever the data gives that end no cap (its cap columns null or absent: a given cap, "round"
    too, wins). A dead end is a point where no end point of any edge lies but the pair's own two (lines that cross or touch mid-line do not
    count; points rounded to 6 places as in :func:`_mark_twoway`). Returns the number of dead ends made square."""
    pt = lambda c: (round(c[0], 6), round(c[1], 6))  # noqa: E731
    ends, cs = collections.Counter(), {}
    for i, ft in enumerate(geo["features"]):
        c = (ft.get("geometry") or {}).get("coordinates") or []
        if (ft.get("geometry") or {}).get("type") == "LineString" and len(c) >= 2:
            cs[i] = (pt(c[0]), pt(c[-1]))
            ends.update(cs[i])
    given = lambda p, col: bool(col) and p.get(col) is not None and p.get(col) == p.get(col)  # noqa: E731
    n = 0
    for i, ft in enumerate(geo["features"]):
        p = ft["properties"]
        if p.get("__rs_twin") is None or i not in cs:
            continue
        s0, s1 = (p.get("__rs_cap0", p.get("__rs_cap")), p.get("__rs_cap1", p.get("__rs_cap"))) if p.get("__rs_split") else (p.get("__rs_cap"),) * 2
        new = [s0, s1]
        for k, (col, pnt) in enumerate(((start_col, cs[i][0]), (end_col, cs[i][1]))):
            if cs[i][0] != cs[i][1] and ends[pnt] == 2 and not given(p, col) and not given(p, cap_col):
                new[k] = "square"
                n += i < p["__rs_twin"]
        if new[0] == new[1]:
            p.pop("__rs_cap0", None), p.pop("__rs_cap1", None), p.pop("__rs_split", None)
            if new[0] is not None:
                p["__rs_cap"] = new[0]
        elif new != [s0, s1] or p.get("__rs_split"):
            p.pop("__rs_cap", None)
            p["__rs_cap0"], p["__rs_cap1"], p["__rs_split"] = new[0], new[1], True
    return n


def _halves(geo):
    """The fill of every edge with two different ends (``__rs_split``) as two halves cut at the middle, each with its end's ``__rs_cap``
    and all the edge's properties: MapLibre sets line-cap per layer, so each end shape needs its own piece (docs/design/square_ends.md).
    At the cut the two halves overlap or meet in the same colour. A half carries ``__rs_edge``, its edge's feature id (the "roads" source's
    generated one), for the page's recolouring: the halves source has no id of its own."""
    import numpy as np
    out = []
    for i, ft in enumerate(geo["features"]):
        p, g = ft["properties"], ft.get("geometry") or {}
        c = g.get("coordinates") or []
        if not p.get("__rs_split") or p.get("__rs_dup") or g.get("type") != "LineString" or len(c) < 2:
            continue
        lon0, lat0 = c[0][0], c[0][1]
        kx, ky = 111320.0 * math.cos(math.radians(lat0)), 111320.0
        xy = np.column_stack([np.asarray([(x - lon0) * kx for x, y, *_ in c]), np.asarray([(y - lat0) * ky for x, y, *_ in c])])
        cum = _cum_lengths(xy)
        n = float(cum[-1])
        for k, (a, b) in enumerate([(0.0, n / 2), (n / 2, n)]):
            pts = _part(xy, cum, a, b)
            coords = np.column_stack([np.round(pts[:, 0] / kx + lon0, 7), np.round(pts[:, 1] / ky + lat0, 7)]).tolist()
            q = {kk: v for kk, v in p.items() if kk not in ("__rs_cap0", "__rs_cap1", "__rs_split")}
            q["__rs_edge"] = p.get("__rs_edge", i)
            if p[f"__rs_cap{k}"] is not None:
                q["__rs_cap"] = p[f"__rs_cap{k}"]
            out.append({"type": "Feature", "properties": q, "geometry": {"type": "LineString", "coordinates": coords}})
    return out


def _twin_ends(geo, cols):
    """One point per end of each two-way pair (docs/design/twin_ends.md): where its two lanes end
    side by side, a road-wide round cap under them fills the dip between the lanes' own round
    ends. Only plain pairs: a bridge or tunnel has butt-capped casings, and a dashed class has no
    casing and butt-capped dashes. Each point carries its pair's styling properties and both
    twins' feature ids (``__rs_edge`` / ``__rs_edge2``) for recolouring and id filters. Every fill
    prop comes twice, the first twin's and the second's (``<prop>__b``): a cap draws only where the
    two lanes have the same colour, so a map coloured per direction never shows one direction's
    colour at a street's end. Where another road is drawn in a lower band at the end point (a
    tunnel mouth, a low road, a sidewalk moved by its band) the cap is fill only
    (``__rs_nocase``): its casing ring would cross that road, which draws under it."""

    keys, where, at = [], collections.defaultdict(list), collections.defaultdict(list)
    for i, ft in enumerate(geo["features"]):
        g = ft.get("geometry") or {}
        c = g.get("coordinates") or []
        k = None
        if g.get("type") == "LineString" and len(c) >= 2:
            k = ((round(c[0][0], 6), round(c[0][1], 6)), (round(c[-1][0], 6), round(c[-1][1], 6)))
            if k[0] != k[1]:
                where[k].append(i)
            for pt in k:
                at[pt].append(i)
        keys.append(k)
    keep = [c for c in cols if c] + ["lvl", "__rs_band", "__rs_cl", "__rs_fl"]
    def below(q, casing):    # is road q drawn entirely below the casing ring of a pair? ``casing``: the head number at the end
        return (q.get("__rs_fl") or 0) < casing      # q's fill is painted before the ring's casing
    used, out = set(), []
    for i, ft in enumerate(geo["features"]):
        p, k = ft["properties"], keys[i]
        if (i in used or k is None or not p.get("__rs_twoway") or p.get("__rs_bridge")
                or p.get("__rs_tunnel") or p.get("__rs_dash") or p.get("__rs_cap") or p.get("__rs_split")):
            continue
        j = next((j for j in where.get((k[1], k[0]), []) if j != i and j not in used           # its twin: the other way round, the same class
                  and geo["features"][j]["properties"].get("__rs_twoway") and geo["features"][j]["properties"].get(cols[0]) == p.get(cols[0])), None)
        if j is None:
            continue
        used.update((i, j))
        props = {c: p[c] for c in keep if p.get(c) is not None}
        props.update({c: v for c, v in p.items() if c.startswith("__rs_fill") or c == "__rs_casing"})
        q = geo["features"][j]["properties"]
        props.update({c + "__b": q.get(c) for c in list(props) if c.startswith("__rs_fill")})
        props.update(__rs_edge=i, __rs_edge2=j)
        c = ft["geometry"]["coordinates"]
        for end, (pt, kp) in enumerate(((c[0], k[0]), (c[-1], k[1]))):
            head = p.get("__rs_cs" if end == 0 else "__rs_ce")         # the casing number of the lane's head at this end
            if head is None:
                head = p.get("__rs_cl") or 0
            low = any(below(geo["features"][n]["properties"], head) for n in at[kp] if n not in (i, j))
            ex = {"__rs_nocase": True} if low else {}
            ex["__rs_cl"] = head                                      # the cap's casing ring is painted at the head's number
            out.append({"type": "Feature", "properties": {**props, **ex},
                        "geometry": {"type": "Point", "coordinates": list(pt[:2])}})
    return out


# the tunnel look (docs/design/tunnel_look.md): everything on a tunnel moves toward one colour as the slider rises, v2's slate (the
# fade is the same for every item, however it was added); the casing dashes start from v2's lighter slate
_TUN_TO = {"fill": "#64748b", "dash": "#94a3b8"}


_HEX6 = re.compile(r"#[0-9a-fA-F]{6}")


def _tun_settings():
    """``(colour, toward, strength)`` of the tunnel look from the settings, checked: ``tunnel_toward`` is a name in ``tunnel_towards`` or a ``#rrggbb``."""
    towards, toward = CONFIG.tunnel_towards, CONFIG.tunnel_toward
    for n, c in towards.items():
        if not (isinstance(c, str) and _HEX6.fullmatch(c)):
            raise ValueError(f"tunnel_towards {n!r}: {c!r} is not a '#rrggbb' colour")
    if toward in towards:
        colour = towards[toward]
    elif isinstance(toward, str) and _HEX6.fullmatch(toward):
        colour = toward
    else:
        raise ValueError(f"tunnel_toward {toward!r} is not a colour name in {list(towards)} or a '#rrggbb' colour")
    return colour, toward, float(CONFIG.tunnel_strength)


def _tun_mix(expr, toward, s):
    """A tunnel feature's colour: ``expr`` moved toward ``toward`` by the slider ``s`` (0-100); any other feature keeps ``expr``
    (docs/design/tunnel_look.md). The page builds the same expression again when the slider moves (_tunMix)."""
    return ["case", ["to-boolean", ["get", "__rs_tunnel"]], ["interpolate", ["linear"], s, 0, expr, 100, toward], expr]


def _tunnel_look(layers, edge_ids, s, arrow_color, to=_TUN_TO):
    """The tunnel look on the finished layer list (docs/design/tunnel_look.md), at slider ``s``: everything on a tunnel (its fill, its street
    names, its arrows, every item attached to it) moves toward the same slate. Its casing is two layers, both 3 px wider than a casing: the
    position's casing layer draws the gap colour (transparent for One colour), the dash layer the dashes on top. Returns
    ``(colours, dash layers, casing layers)``: ``{layer id: [[paint property, its colour without the look, target key], ...]}``, the ids of
    the dash layers and ``{casing layer id: its colour without the look}``, for the page."""
    out, dash, casing = {}, [], {}
    tun = ["to-boolean", ["get", "__rs_tunnel"]]
    clear = "rgba(0,0,0,0)"

    def mix(l, k, base, to_key):
        out.setdefault(l["id"], []).append([k, base, to_key])
        l["paint"][k] = _tun_mix(base, to[to_key], s)

    for l in layers:
        lid = l["id"]
        if l.get("source") not in ("roads", "casings", "halves", "slots", "arrows") and lid not in edge_ids:
            continue
        l["paint"] = dict(l.get("paint") or {})           # a new paint: the copies of a layer for each position share theirs
        if lid.startswith("roads-casing") and lid.endswith("-dash"):
            dash.append(lid)
        elif lid.startswith("roads-casing") and "-bridge" not in lid:
            casing[lid] = l["paint"]["line-color"]
            l["paint"]["line-color"] = ["case", tun, clear, l["paint"]["line-color"]]     # One colour: empty gaps; the page sets a palette's gap colour
            l["paint"]["line-width"] = _plus_px(l["paint"]["line-width"], 3, tun)          # as wide as the dash layer
        elif lid.startswith("roads-fill") and not lid.endswith("-pat"):
            mix(l, "line-color", l["paint"]["line-color"], "fill")
        elif lid.startswith("roads-labels"):
            mix(l, "text-color", l["paint"]["text-color"], "fill")
        elif lid.startswith("roads-arrows"):
            mix(l, "icon-color", arrow_color, "fill")    # on a map with tunnels the arrow icon is an SDF one (addArrow): coloured here
        elif lid in edge_ids:
            for k in ("fill-color", "line-color", "circle-color", "text-color"):
                if k in l["paint"]:
                    mix(l, k, l["paint"][k], "fill")
    return out, dash, casing


_CASING_FAMILY = ("roads-casing", "roads-casing-sq", "roads-casing-sx", "roads-casing-dash", "roads-casing-bridge-shadow", "roads-casing-bridge",
                  "roads-casing-sq-bridge", "roads-casing-sx-bridge")
_FILL_FAMILY = ("roads-fill", "roads-fill-sq", "roads-fill-sx", "roads-fill-h", "roads-fill-hsq", "roads-fill-hsx", "roads-fill-pat")


_VIEW_BOOLS = ("road_fill", "bridges", "tunnels", "view3d")


def _check_views(views, colors, overlays, classes, basemaps):
    """``views`` as the page reads it, ``[{"name", "set"}]``; a setting that is not known, or names a colour option, an overlay, a class or a
    base map the page does not have, is an error (docs/design/core_model_and_views.md)."""
    out = []
    for name, sets in (views or {}).items():
        unknown = set(sets) - {"color", "overlays", "classes", "basemap", *_VIEW_BOOLS}
        if unknown:
            raise ValueError(f"view {name!r}: unknown setting(s) {sorted(unknown)}")
        for k in _VIEW_BOOLS:
            if k in sets and not isinstance(sets[k], bool):
                raise ValueError(f"view {name!r}: {k} must be True or False, got {sets[k]!r}")
        for k, have, given in (("color", colors, [sets["color"]] if "color" in sets else []),
                               ("overlays", overlays, list(sets.get("overlays") or {})),
                               ("classes", classes, list(sets.get("classes") or [])),
                               ("basemap", basemaps, [sets["basemap"]] if "basemap" in sets else [])):
            missing = [x for x in given if x not in have]
            if missing:
                raise ValueError(f"view {name!r}: {k} {missing} not in the page (it has {have})")
        out.append({"name": name, "set": sets})
    return out


def _fill_layer_ids(levels):
    """The layers the page recolours (colour-by, rsColor): every road fill layer, and the fill layers of each drawing-order position."""
    fills = ("roads-fill", "roads-fill-sq", "roads-fill-sx", "roads-fill-h", "roads-fill-hsq", "roads-fill-hsx")
    ids = list(fills)
    for level in levels or ():
        if level != 0:
            ids += [_level_id(i, level) for i in fills]
    return ids


def _level_id(lid, level):
    """The id of a ground layer for a position: unchanged for 0; else ``-lv<n>`` after the family root (roads-fill-lv2-sq)."""
    if level == 0:
        return lid
    root = "roads-casing" if lid.startswith("roads-casing") else "roads-fill"
    return f"{root}-lv{level}{lid[len(root):]}"


def _level_layers(layers, levels, casing_source=None):
    block = [l for l in layers if l["id"] in _CASING_FAMILY or l["id"] in _FILL_FAMILY or l["id"].startswith("roads-fill-dash")]
    if not block:
        return layers
    first = next(i for i, l in enumerate(layers) if l["id"] == block[0]["id"])
    ids = {l["id"] for l in block}
    rest = [l for l in layers if l["id"] not in ids]
    groups = []
    for level in levels:
        for l in block:
            key = "__rs_cl" if l["id"] in _CASING_FAMILY else "__rs_fl"
            groups.append({**l, **({"source": casing_source} if casing_source and key == "__rs_cl" and l.get("source", "roads") == "roads" else {}),
                           "id": _level_id(l["id"], level),
                           "filter": ["all", l["filter"], ["==", ["coalesce", ["get", key], 0], level]]})
    return rest[:first] + groups + rest[first:]


_MAYBE = object()      # a value only the page knows (the zoom), or an expression _ev does not read: the layer may draw
_MISSING = object()
_OPS = {"<": lambda x, y: x < y, ">": lambda x, y: x > y, "<=": lambda x, y: x <= y, ">=": lambda x, y: x >= y,
        "%": lambda x, y: x % y, "*": lambda x, y: x * y, "+": lambda x, y: x + y, "-": lambda x, y: x - y}


def _same(a, b):
    """MapLibre's ``==``: a boolean never equals a number."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _ev(e, p):
    """A MapLibre expression on a feature's properties ``p``: its value, or _MAYBE where only the page can tell (three-valued logic)."""
    if not isinstance(e, list) or not e:
        return e
    op, a = e[0], e[1:]
    if op == "literal":
        return a[0]
    if op == "get" and len(a) == 1:
        v = p.get(a[0], _MISSING)
        return None if v is _MISSING else v
    if op == "has" and len(a) == 1:
        return p.get(a[0], _MISSING) is not _MISSING
    if op in ("all", "any"):
        out = op == "all"
        for x in a:
            v = _ev(x, p)
            if v is _MAYBE:
                out = _MAYBE
            elif bool(v) != (op == "all"):
                return not (op == "all")
        return out
    if op in ("!", "to-boolean", "==", "!=", *_OPS):
        vals = [_ev(x, p) for x in a]
        if any(v is _MAYBE for v in vals):
            return _MAYBE
        if op == "!":
            return not vals[0]
        if op == "to-boolean":
            return _truthy(vals[0])
        if op in ("==", "!="):
            return _same(*vals) == (op == "==")
        try:
            return _OPS[op](*vals)
        except (TypeError, ZeroDivisionError):
            return _MAYBE
    if op == "coalesce":
        for x in a:
            v = _ev(x, p)
            if v is _MAYBE or v is not None:
                return v
        return None
    if op == "case":
        for c, o in zip(a[:-1:2], a[1:-1:2], strict=True):
            v = _ev(c, p)
            if v is _MAYBE:
                return _MAYBE
            if v:
                return _ev(o, p)
        return _ev(a[-1], p)
    if op == "match":
        v = _ev(a[0], p)
        if v is _MAYBE:
            return _MAYBE
        for lab, o in zip(a[1:-1:2], a[2:-1:2], strict=True):
            if any(_same(v, x) for x in (lab if isinstance(lab, list) else [lab])):
                return _ev(o, p)
        return _ev(a[-1], p)
    return _MAYBE                       # ["zoom"], and any operator not read here


def _keys(e, out):
    """The property names an expression reads."""
    if isinstance(e, list) and e and e[0] != "literal":
        if e[0] in ("get", "has") and len(e) == 2 and isinstance(e[1], str):
            out.add(e[1])
        for x in e[1:]:
            _keys(x, out)
    return out


def _drop_empty_layers(layers, feats, keep=("roads-fill",)):
    """The layers without the road layers no feature can draw: a road layer stays when its filter holds, or may hold (it reads the zoom), for
    some feature of its source (``feats``: {source: features}). A position has a whole family of layers (casing, fill, their square, flat and
    bridge twins, halves, shadows, dashes, ends, arrows, names) and most of them are empty at most positions, while MapLibre walks every
    layer on every frame. The layers that stay keep their order; ``keep`` stays always (the page reads roads-fill's line offset)."""
    seen = {}

    def draws(l):
        f = l.get("filter")
        if f is None or l["id"] in keep or l.get("source") not in feats:
            return True
        ks = tuple(sorted(_keys(f, set())))
        if (l["source"], ks) not in seen:     # the distinct values of the properties the filter reads (a few hundred, not every feature)
            seen[l["source"], ks] = [dict(zip(ks, c, strict=True)) for c in {tuple(_hashable((ft.get("properties") or {}).get(k, _MISSING)) for k in ks)
                                                                 for ft in feats[l["source"]]}]
        return any(v is _MAYBE or bool(v) for v in (_ev(f, p) for p in seen[l["source"], ks]))

    return [l for l in layers if not l["id"].startswith("roads-") or draws(l)]


def _hashable(v):
    return tuple(v) if isinstance(v, list) else v


def _plus_px(expr, px, when=None):
    """A width expression ``px`` pixels wider (only for the features where ``when`` holds, if given): inside each stop of a top-level zoom
    curve (MapLibre allows ``["zoom"]`` only there). ``px`` may be a function of the stop's zoom."""
    wider = (lambda v, p: ["+", v, p]) if when is None else (lambda v, p: ["case", when, ["+", v, p], v])
    if isinstance(expr, list) and expr and expr[0] in ("interpolate", "step"):
        first = 4 if expr[0] == "interpolate" else 2
        return [*expr[:first], *[wider(v, px(expr[i - 1]) if callable(px) else px) if (i - first) % 2 == 0 else v
                                 for i, v in enumerate(expr[first:], first)]]
    return wider(expr, px)


def _tunnel_casing_dash(lid, flt, tlay, cw, off, on):
    """The dashes of a tunnel's two-tone casing, a sublayer on the band's casing (``on``: the band has a tunnel)."""
    return [{"id": lid, "type": "line", "source": "roads", "layout": tlay, "filter": flt,
             "paint": {"line-color": _TUN_TO["dash"], "line-width": _plus_px(cw, 3), "line-offset": off,      # as v2: 1.5 px wider each side, so its colours show
                       "line-dasharray": list(CONFIG.tunnel_casing_dash or [1, 1])}}] if on else []


def _tunnel_fill_dash(lid, flt, tlay, fw, off, on):
    """Light dashes along a tunnel's fill (2026-09-30, among three samples: "light dash is
    ok"); a translucent colour, so it suits any road colour. A dashed class keeps only its own
    dashes. Nothing without tunnels or with ``tunnel_fill_dash: []``."""
    dash = list(CONFIG.tunnel_fill_dash or [])
    if not (on and dash):
        return []
    return [{"id": lid, "type": "line", "source": "roads", "layout": tlay,
             "filter": ["all", flt, ["!", ["to-boolean", ["get", "__rs_dash"]]]],
             "paint": {"line-color": CONFIG.tunnel_fill_dash_color or "rgba(255,255,255,0.55)",
                       "line-width": fw, "line-offset": off, "line-dasharray": [float(x) for x in dash]}}]


def _rgb(hex_color):
    """``#rgb`` / ``#rrggbb`` -> [r, g, b]; None for anything else (a named or rgba() colour)."""
    h = (hex_color or "").lstrip("#")
    h = "".join(ch * 2 for ch in h) if len(h) == 3 else h
    try:
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] if len(h) == 6 else None
    except ValueError:
        return None


def _is_light(hex_color):
    rgb = _rgb(hex_color)
    return rgb is not None and sum(rgb) / 3 > 110


def _darker(hex_color, amount):
    """``hex_color`` darkened by ``amount`` (0..1); None when it isn't ``#rgb`` / ``#rrggbb``."""
    rgb = _rgb(hex_color)
    return None if rgb is None else "#" + "".join(f"{round(v * (1 - amount)):02x}" for v in rgb)







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
    feature *id* is the feature's index (its own ``id``), not taken from these properties, so this
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
  // never attached. Poll for the real Map; never call through an unchecked handle. Never give up:
  // MapLibre builds its sources on an animation frame, and browsers pause those while a page is
  // off screen (a background tab, a notebook output scrolled away), so the sources can appear
  // minutes late. After the first minute keep checking once a second, and tell the banner.
  var tries=0;
  (function fill(){
    var m=window.map, sids=Object.keys(data);
    if(!(m && typeof m.getSource==="function") || !sids.every(function(s){return m.getSource(s);})){
      if(++tries>600) window.__rs_gz={ok:false, stage:"attach", waiting:true, error:"still waiting for the map"};
      return setTimeout(fill, tries>600 ? 1000 : 100);
    }
    var n=0;
    sids.forEach(function(s){ m.getSource(s).setData(data[s]); n+=data[s].features.length; });
    window.__rs_gz={ok:true, sources:sids, features:n};
    var banner=document.getElementById("rs-diag"); if(banner) banner.remove();   // late, but here
    data=null;
  })();
})();
</script>
"""


# simple=True (render's docstring), injected after the main map script, so a full-look page stays as it was: the page's own
# recolouring (_applyFill), painted-road order (_applySort) and road fill switch (rsSetRoadFill) also set the one road layer. A
# function of the main script is a global: assigning it here is what the main script calls from then on.
_SIMPLE_JS = """
<script>
const RS_SIMPLE = __RS_SIMPLE__;
function _simpleColor(){        // render_web._simple_color, with the active colouring, the rsColor groups and the tunnel slider
  const sh=["==",["get","__rs_k"],2];
  const c=["==",["get","__rs_k"],0], b=["to-boolean",["get","__rs_bridge"]];
  const base=["coalesce",["get","__rs_casing"],"#000000"];
  let fill=_fillExpr(["get","__rs_edge"]), item=["coalesce",["get","__rs_ic"],"#888888"], cases=[sh,RS_SIMPLE.shadow,c,["case",b,RS_SIMPLE.bridge,base]];
  // a road painted by rsColor shows it on its items too: where items replace a road's fill (lanes), the fill alone would show nothing
  // (2026-10-10: the level editor's picked roads were not visible with lanes); unpainted, an item keeps its own colour
  if(typeof _qColor!=="undefined" && _qColor) for(let i=_qColor.length-1;i>=0;i--)
    item=["case",["any",_has(["get","__rs_edge"],_qColor[i].ids),_has(["get","__rs_edge2"],_qColor[i].ids)],_qColor[i].color,item];
  if(RS_SIMPLE.tunnels){                 // a tunnel's fill: the tunnel look; its casing: the palette's gap and dash colours (the gap clear for One colour)
    fill=_tunMix(fill, TUNNEL.to.fill); item=_tunMix(item, TUNNEL.to.fill);
    const pair=TUNNEL.palettes[TUNNEL.palette], k=TUNNEL.strength/100;
    cases.push(["==",["get","__rs_k"],3], pair ? _tunHex(pair[1], TUNNEL.to.fill, k) : "rgba(0,0,0,0)",
               ["==",["get","__rs_k"],4], _tunHex(pair ? pair[0] : TUNNEL.to.dash, TUNNEL.to.fill, k));
  }
  return ["case",...cases,["==",["get","__rs_k"],5],item,fill];    // an item (__rs_k 5) keeps its own colour
}
function _simpleDash(){         // render_web._simple_dasharray, with the tunnel dash ratio
  const solid=["literal",[1,0]], by=["match",["to-string",["coalesce",["get","__rs_dash"],""]]];
  RS_SIMPLE.dashes.forEach(d=>by.push(d,["literal",d.split(",").map(Number)])); by.push(solid);
  return ["case",["==",["get","__rs_k"],4],["literal",TUNNEL.ratio.map(Number)],RS_SIMPLE.dashes.length ? by : solid];
}
const _rsFullFill=_applyFill, _rsFullSort=_applySort, _rsFullRoadFill=rsSetRoadFill;
_applyFill=function(){ _rsFullFill();
  if(map.getLayer(RS_SIMPLE.layer)) map.setPaintProperty(RS_SIMPLE.layer,"line-color",_simpleColor()); };
// a painted road's fill (and its items) above the other fills of its position, under the casings of the next (line-sort-key 2 * position + 1.5)
_applySort=function(){ _rsFullSort();
  const all=_qColor ? [].concat(..._qColor.map(g=>g.ids)) : null, k=["get","__rs_s"];
  if(map.getLayer(RS_SIMPLE.layer)) map.setLayoutProperty(RS_SIMPLE.layer,"line-sort-key",
    all ? ["+",k,["case",["all",["any",["==",["get","__rs_k"],1],["==",["get","__rs_k"],5]],["any",_has(["get","__rs_edge"],all),_has(["get","__rs_edge2"],all)]],0.5,0]] : k); };
const _rsFullTunnel=rsSetTunnelStyle;
rsSetTunnelStyle=function(o){ _rsFullTunnel(o);       // the palette (colours, in _applyFill) and the dash ratio
  if(RS_SIMPLE.tunnels && map.getLayer(RS_SIMPLE.layer)) map.setPaintProperty(RS_SIMPLE.layer,"line-dasharray",_simpleDash()); };
window.rsSetTunnelStyle=rsSetTunnelStyle;
rsSetRoadFill=function(on){
  if(map.getLayer(RS_SIMPLE.layer)) map.setPaintProperty(RS_SIMPLE.layer,"line-opacity",on ? 1 : ["case",["==",["get","__rs_k"],1],0,1]);
  _rsFullRoadFill(on); };
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
                                  "maxzoom": bm.maxzoom, "attribution": bm.attr}
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


def _styled(ov):
    """The overlay with the fields of its ``style`` (``config.overlays.styles`` of the settings) filled in where it gives none (docs/design/overlay_styles.md)."""
    if not ov.style:
        return ov
    import dataclasses
    styles = (CONFIG.overlays or {}).get("styles") or {}
    if ov.style not in styles:
        raise ValueError(f"overlay style {ov.style!r} is not in the settings (config.overlays.styles); known: {sorted(styles)}")
    fields = {f.name for f in dataclasses.fields(type(ov))} - {"data", "style", "edge_col", "order_col", "select"}
    bad = set(styles[ov.style]) - fields
    if bad:
        raise ValueError(f"overlay style {ov.style!r}: unknown field(s) {sorted(bad)}; the fields are {sorted(fields)}")
    return dataclasses.replace(ov, **{k: v for k, v in styles[ov.style].items() if getattr(ov, k) is None})


def _wm_width_expr(min_zoom):
    """A line width in px for the metre width baked in ``__rs_wm``: exact from ``min_zoom`` (default 0) to 22, because the width doubles with each zoom (base-2 interpolation)."""
    e = ["interpolate", ["exponential", 2], ["zoom"]]
    for z in sorted({max(float(min_zoom or 0), 0.0), 22.0}):
        e += [z, ["*", ["get", "__rs_wm"], round(512 * 2 ** z / 40075016.686, 6)]]
    return e


def _bake_wm(fc, width_m):
    """``__rs_wm`` on every feature: the width in metres over cos(latitude), at the feature's first point (as ``_mark_width_m`` does for the roads)."""
    def first(c):
        while isinstance(c, (list, tuple)) and c and isinstance(c[0], (list, tuple)):
            c = c[0]
        return c
    for ft in fc["features"]:
        pt = first((ft.get("geometry") or {}).get("coordinates") or [0, 0])
        ft.setdefault("properties", {})["__rs_wm"] = float(width_m) / max(math.cos(math.radians(pt[1])), 0.01)


def _overlay_layers(sid, ov, kind, hover_color="#b388ff", select_color="#7c4dff", along=True):
    """The MapLibre layer spec(s) for one overlay source: a fill (+ outline), a circle, a line or a text (``along``: the text follows a line).

    Interactive overlays (those with a popup) recolour on hover / select via feature-state, the same
    way roads do, so the hovered / clicked feature highlights."""
    C = {"color": "#6aa9ff", "radius": 6.0, "width": 2.0, "fill_opacity": 0.15,
         "circle_opacity": 0.85, "line_opacity": 0.9, "outline_opacity": 0.9,
         "circle_stroke": "#ffffff", **(CONFIG.overlays or {})}
    base = ov.color or C["color"]                     # per-Overlay value wins over the setting
    if ov.color_col:                                  # a colour per feature (null / missing: the overlay's)
        base = ["coalesce", ["get", ov.color_col], base]
    width = C["width"] if ov.width is None else ov.width
    if ov.width_m is not None:                        # a width in metres, baked in __rs_wm by _build_overlays
        width = _wm_width_expr(ov.min_zoom)
    radius = C["radius"] if ov.radius is None else ov.radius
    op = ov.opacity
    interactive = ov.popup is None or bool(ov.popup) or (ov.select == "item" and bool(ov.edge_col))   # an item selected itself takes the highlight
    col = _ov_hl(base, hover_color, select_color, interactive)
    lay = {"visibility": "visible" if getattr(ov, "visible", True) else "none"}
    dash = {"line-dasharray": [float(x) for x in ov.dash]} if ov.dash else {}
    zooms = {**({"minzoom": float(ov.min_zoom)} if ov.min_zoom is not None else {}), **({"maxzoom": float(ov.max_zoom)} if ov.max_zoom is not None else {})}
    if kind == "text":
        if not ov.text_col:
            raise ValueError("an overlay of kind 'text' needs text_col (the property that holds the text)")
        return [{"id": f"{sid}-text", "type": "symbol", "source": sid, **zooms,
                 "layout": {**lay, "symbol-placement": "line-center" if along else "point", "text-field": ["get", ov.text_col],
                            "text-font": ["Noto Sans Regular"], "text-size": ov.text_size or 12, "text-max-angle": 40, "text-padding": 2},
                 "paint": {"text-color": ov.text_color or base,
                           **({"text-halo-color": ov.text_halo, "text-halo-width": 1.5} if ov.text_halo else {})}}]
    if kind == "fill":
        return [
            {"id": f"{sid}-fill", "type": "fill", "source": sid, "layout": dict(lay), **zooms,
             "paint": {"fill-color": col, "fill-opacity": C["fill_opacity"] if op is None else op}},
            {"id": f"{sid}-outline", "type": "line", "source": sid, "layout": dict(lay), **zooms,
             "paint": {"line-color": ov.outline or base, "line-width": width, **dash,
                       "line-opacity": C["outline_opacity"]}},
        ]
    if kind == "circle":
        return [{"id": f"{sid}-circle", "type": "circle", "source": sid, "layout": dict(lay), **zooms,
                 "paint": {"circle-radius": radius, "circle-color": col,
                           "circle-opacity": C["circle_opacity"] if op is None else op,
                           "circle-stroke-color": C["circle_stroke"], "circle-stroke-width": 1}}]
    return [{"id": f"{sid}-line", "type": "line", "source": sid, **zooms,
             "layout": {**lay, "line-cap": "butt" if ov.dash else "round"},
             "paint": {"line-color": col, "line-width": width, **dash,
                       "line-opacity": C["line_opacity"] if op is None else op}}]


def _eid(v):
    """An edge id as text, the same for an int, a float with a whole value and a string, so ids past 2**53 match."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _edge_overlay(ov, fc, roads, edge_id_col, fcol):
    """Bake on the features of an overlay with ``edge_col`` (docs/design/edge_overlays.md, edge_items.md) what they take from their edge:
    ``__rs_edge`` (the edge's index in the ``roads`` source, the label every piece of a road carries), ``__rs_fl`` (its fill number),
    ``__rs_ord`` (the feature's order), ``__rs_cls`` / ``__rs_lvl`` (its class in ``fcol`` and its level, for the class, bridge and tunnel
    switches) and ``__rs_tunnel``. ``roads``: ``{edge id as text: the edge's properties}``. An edge id that is not among the roads is an error."""
    if roads is None:
        raise ValueError(f"an overlay with edge_col needs the roads' id column {edge_id_col!r} (edge_id_col): it is not in the edges")
    unknown, orders = [], set()
    for ft in fc["features"]:
        p = ft.setdefault("properties", {}) or {}
        ft["properties"] = p
        e = _eid(p.get(ov.edge_col))
        r = roads.get(e)
        if r is None:
            unknown.append(e)
            continue
        o = p.get(ov.order_col) if ov.order_col else 0
        o = 0 if o is None or (isinstance(o, float) and math.isnan(o)) else int(o)
        fl = r.get("__rs_fl") or 0
        p.update(__rs_edge=r["__rs_edge"], __rs_fl=fl, __rs_ord=o, __rs_cls=r.get(fcol), __rs_lvl=r.get("lvl", 0))
        if r.get("__rs_tunnel"):
            p["__rs_tunnel"] = True          # the item of a tunnel takes its look (docs/design/tunnel_look.md)
        orders.add((fl, o))
    if unknown:
        raise ValueError(f"overlay {ov.label or ''}: {len(unknown)} feature(s) have an {ov.edge_col!r} that is not an edge of the roads (first: {unknown[:5]})")
    return sorted(orders)


def _item_pieces(ov, i, fc):
    """Simple mode: the line items of an overlay attached to edges as pieces of the one road layer (``__rs_k`` 5, docs/design/edge_items.md):
    what the filters read from their edge (baked by :func:`_edge_overlay`), ``lvl``, their colour ``__rs_ic`` and their width / offset in
    metres over cos(latitude) (``__rs_iwm`` / ``__rs_iom``, as ``_mark_width_m``). ``__rs_s`` is set by :func:`_simple_pieces`."""
    C = {"color": "#6aa9ff", **(CONFIG.overlays or {})}
    out = []
    for j, ft in enumerate(fc["features"]):
        p, g = ft["properties"], ft.get("geometry") or {}
        w = p.get(ov.width_m_col) if ov.width_m_col else ov.width_m
        if w is None or missing(w):
            raise ValueError(f"overlay {ov.label or i}: item {j} has no width in metres ({ov.width_m_col or 'width_m'})")
        o = p.get(ov.offset_m_col) if ov.offset_m_col else None
        cs = g.get("coordinates") or []
        pts = [c for part in cs for c in part] if g.get("type") == "MultiLineString" else cs
        sec = 1 / max(math.cos(math.radians(sum(c[1] for c in pts) / len(pts))), 0.01)
        d = p.get(ov.dash_col) if ov.dash_col else None
        d = ov.dash if d is None or (not isinstance(d, (list, tuple)) and missing(d)) else d
        p.update(__rs_iwm=round(float(w) * sec, 4), __rs_iom=0 if o is None or missing(o) else round(float(o) * sec, 4))   # the item's own layer reads them too
        q = {k: v for k, v in p.items() if k.startswith("__rs_")}
        q.update(lvl=p.get("__rs_lvl", 0), __rs_k=5, __rs_ov=i, __rs_item=j,
                 __rs_ic=(p.get(ov.color_col) if ov.color_col else None) or ov.color or C["color"])
        if d:     # the road layer's dash pattern is a text ("3,3": a property cannot hold an array), as a dashed class's __rs_dash
            q["__rs_dash"] = ",".join(f"{float(x):g}" for x in (d.split(",") if isinstance(d, str) else d))
        out.append({"type": "Feature", "geometry": g, "properties": q})
    return out


def _build_overlays(style, overlays, hover_color="#b388ff", select_color="#7c4dff", roads=None, edge_id_col="edge_id", fcol="highway", fill=False):
    """Add each overlay as its own source + layer(s) to ``style``. Returns ``(under, over, meta, edge, items)``:
    the layer specs to splice below / above the roads, the JS metadata (label / source / clickable
    layer ids / popup fields) the page reads to wire popups, hover/select highlight, and the Layers
    toggle, and the layers of the overlays attached to edges, ``[(position, order, overlay index, [layer specs])]``, which go
    between the fills of their position and its arrows (``_place_edge_overlays``). Overlay sources carry ``generateId``
    so interactive features can take feature-state.
    ``fill`` (simple mode): the line items attached to edges also come back as ``items``, pieces of the one road layer (:func:`_item_pieces`);
    their own layers stay, invisible but on hover / select, for the pick, the popup and the highlight."""
    under, over, meta, edge, items = [], [], [], [], []
    for i, item in enumerate(overlays or []):
        ov = _styled(item if isinstance(item, Overlay) else Overlay(data=item))
        fc = to_fc(ov.data)
        kind = ov.kind or detect_kind(fc)
        sid = f"ov{i}"
        if ov.width_m is not None:
            _bake_wm(fc, ov.width_m)
        along = detect_kind(fc) != "circle"
        if kind == "text":
            style.setdefault("glyphs", "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf")
        base_filters = None
        if ov.edge_col:
            layers, base_filters = [], {}
            metres = ov.width_m is not None or bool(ov.width_m_col)   # only items with a width in metres join the road layer; a px-wide line keeps its own layer (2026-10-09)
            for pos, order in _edge_overlay(ov, fc, roads, edge_id_col, fcol):
                flt = ["all", ["==", ["get", "__rs_fl"], pos], ["==", ["get", "__rs_ord"], order]]
                mine = []
                for lyr in _overlay_layers(sid, ov, kind, hover_color, select_color, along):
                    lyr = {**lyr, "id": f"{lyr['id']}-lv{pos}-o{order}", "filter": flt}
                    if fill and kind == "line" and metres:   # drawn by the road layer: this one is the pick and shows the hover / select highlight
                        on = ["any", ["boolean", ["feature-state", "select"], False], ["boolean", ["feature-state", "hover"], False]]
                        m = lambda prop: ["interpolate", ["exponential", 2], ["zoom"], *[x for z in (0, 22) for x in
                                          (z, ["*", ["get", prop], round(512 * 2 ** z / 40075016.686, 6)])]]   # the item's own metres, exact
                        lyr["layout"] = {**lyr["layout"], "line-cap": "butt"}
                        lyr["paint"] = {**{k: v for k, v in lyr["paint"].items() if k != "line-dasharray"}, "line-opacity": ["case", on, 1, 0],
                                        "line-width": m("__rs_iwm"), "line-offset": m("__rs_iom")}
                    base_filters[lyr["id"]] = flt
                    mine.append(lyr)
                edge.append((pos, order, i, mine))
                layers += mine
            if fill and kind == "line" and metres:
                items += _item_pieces(ov, i, fc)
        else:
            layers = _overlay_layers(sid, ov, kind, hover_color, select_color, along)
            (under if ov.placement == "under" else over).extend(layers)
        style["sources"][sid] = {"type": "geojson", "data": fc, "generateId": True}
        # the topmost layer is the click target (fill body / circle / line)
        meta.append({"label": ov.label or f"Layer {i + 1}",
                     "source": sid,
                     "layers": [lyr["id"] for lyr in layers],
                     "hit": layers[0]["id"] if layers else None,
                     "visible": getattr(ov, "visible", True),
                     "color": ov.color,
                     "popup": list(ov.popup) if ov.popup is not None else None,
                     "tooltip": list(ov.tooltip) if ov.tooltip else None,
                     "under": ov.placement == "under" and not ov.edge_col,
                     "base": base_filters,              # the layers' own filters (position and order) that rsFilter must keep
                     "select": ov.select,               # an item attached to a road: a click picks its "road" or the "item"
                     "interactive": ov.popup is None or bool(ov.popup)})
    return under, over, meta, edge, items


def _square_end(q, line_of):
    """A casing head with a square end (``__rs_cap`` "square"): MapLibre caps a line at both of its ends, so the head's other end, the cut, was square
    too and stuck out where the road bends there (2026-10-10, a service road's bend: a square green corner). The head flat (``__rs_cap`` True) and
    a 1 cm piece at the road end that carries the square cap: ``[head, cap]``; a piece that is not a head (both ends or no end of its edge) as it is."""
    g = q["geometry"]
    c = g.get("coordinates") or []
    e = line_of.get(q["properties"]["__rs_edge"]) or []           # the edge's line, by its number (the editor draws a part of the roads)
    if g.get("type") != "LineString" or len(c) < 2 or len(e) < 2 or (c[0] == e[0]) == (c[-1] == e[-1]):
        return [q]
    end, prev = (c[0], c[1]) if c[0] == e[0] else (c[-1], c[-2])
    k = 0.01 / max(math.hypot((prev[0] - end[0]) * 111320 * math.cos(math.radians(end[1])), (prev[1] - end[1]) * 111320), 1e-6)
    stub = [[end[0] + (prev[0] - end[0]) * min(k, 1), end[1] + (prev[1] - end[1]) * min(k, 1)], list(end)]
    return [{**q, "properties": {**q["properties"], "__rs_cap": True}}, {**q, "geometry": {"type": "LineString", "coordinates": stub}}]


def _simple_pieces(geo, parts, cols, shadows=True, items=()):
    """The features of simple mode's one road layer: every casing piece (``__rs_k`` 0; the heads and seams as ``_casing_parts`` cuts them) and every fill
    (``__rs_k`` 1), with ``__rs_s``, the line-sort-key: ``2 * position``, a bridge's casing a quarter more (the full look draws it after the other
    casings of its position), a fill ``2 * position + 1``. A dashed class has no casing and its fill comes before the casings of its position
    (``2 * position - 0.5``), as in the full look. A fill keeps only what the layer reads (``cols``, ``lvl``, ``__rs_*``).
    A bridge's shadow (``__rs_k`` 2): a copy of its main casing piece (or its whole casing, an edge not cut), just under it (``__rs_s`` 0.1
    less); the heads, where the bridge comes down to the road, have none.
    A tunnel's casing (docs/design/tunnel_look.md) is two pieces instead of one, as the full look's two layers: the gap colour (``__rs_k`` 3, at the
    casing's key) and the dashes on top (``__rs_k`` 4, 0.1 more, still under the fill).
    Ends: the layer reads ``__rs_cap`` per piece (line-cap: none round, True flat, "square" square). As in the full look, a casing's main piece
    (between two cuts) ends flat and each cut gets its seam (a round dot at the lower number): a round main piece reached past a short head
    into the junction (2026-10-08). An edge with two different ends draws its fill as two halves (:func:`_halves`).
    ``items`` (:func:`_item_pieces`, ``__rs_k`` 5): the line items attached to edges, each at its edge's fill: ``2 * position + 1`` plus
    _ITEM_STEP per rank on its edge (by order, overlay, feature), above every fill of the position and under the next casings (see _ITEM_STEP).
    An edge with items has no fill piece (left out, so rsSetRoadFill and a view's road_fill cannot bring it back): its items are its fill."""
    keep = {c for c in cols if c} | {"lvl"}
    halves = collections.defaultdict(list)
    for h in _halves(geo):
        halves[h["properties"]["__rs_edge"]].append(h)
    out = []
    line_of = {(f.get("properties") or {}).get("__rs_edge", i): (f.get("geometry") or {}).get("coordinates") for i, f in enumerate(geo["features"])}
    for q in (x for q0 in parts for x in (_square_end(q0, line_of) if q0["properties"].get("__rs_cap") == "square" and not q0["properties"].get("__rs_seam") else [q0])):
        p = q["properties"]
        if p.get("__rs_dash") or (p.get("__rs_seam") and p.get("__rs_tunnel")):     # a tunnel's casing is its dashes alone, no seam dots
            continue
        k = 2 * p["__rs_cl"] + (0.25 if p.get("__rs_bridge") else 0)
        if shadows and p.get("__rs_bridge") and (p.get("__rs_main") or p["__rs_cs"] == p["__rs_cl"] == p["__rs_ce"]):
            out.append({"type": "Feature", "geometry": q["geometry"], "properties": {**p, "__rs_k": 2, "__rs_s": k - 0.1}})
        if p.get("__rs_tunnel") and not p.get("__rs_bridge"):
            out.append({"type": "Feature", "geometry": q["geometry"], "properties": {**p, "__rs_k": 3, "__rs_s": k}})
            out.append({"type": "Feature", "geometry": q["geometry"], "properties": {**p, "__rs_k": 4, "__rs_s": k + 0.1}})
        else:
            out.append({"type": "Feature", "geometry": q["geometry"], "properties": {**p, "__rs_k": 0, "__rs_s": k}})
    itemed = {f["properties"]["__rs_edge"] for f in items}     # an edge with items draws no fill of its own: its items are its fill (2026-10-09)
    for i, ft in enumerate(geo["features"]):
        p = ft["properties"]
        if p.get("__rs_dup") or p.get("__rs_edge", i) in itemed:
            continue
        for g, p in ([(h["geometry"], h["properties"]) for h in halves[p.get("__rs_edge", i)]] if p.get("__rs_split") else [(ft["geometry"], p)]):
            out.append({"type": "Feature", "geometry": g,
                        "properties": {**{k: v for k, v in p.items() if k in keep or k.startswith("__rs_")}, "__rs_k": 1,
                                       "__rs_s": 2 * p["__rs_fl"] + (-0.5 if p.get("__rs_dash") else 1)}})
    n = collections.Counter()           # a feature id per piece, _PIECES per edge, so the page can swap one road's pieces (GeoJSONSource.updateData)
    for f in out:
        e = f["properties"]["__rs_edge"]
        if n[e] == _PIECES:
            raise ValueError(f"simple=True: edge {e} has more than {_PIECES} pieces")
        if e >= _MAX_EDGES:
            raise ValueError(f"simple=True: more than {_MAX_EDGES:,} edges; the line-sort-key's tie-breaker would reach the next key step (pass simple=False)")
        f["id"], n[e] = e * _PIECES + n[e], n[e] + 1
        f["properties"]["__rs_s"] += e * _TIE   # same key: by edge, not by feature order, so a road redrawn in place (updateData) keeps its place
    rank = collections.Counter()
    for j, f in enumerate(sorted(items, key=lambda f: (f["properties"]["__rs_edge"], f["properties"]["__rs_ord"], f["properties"]["__rs_ov"], f["properties"]["__rs_item"]))):
        p = f["properties"]
        e, rank[p["__rs_edge"]] = p["__rs_edge"], rank[p["__rs_edge"]] + 1
        if rank[e] > _MAX_ITEMS:
            raise ValueError(f"simple=True: edge {e} has more than {_MAX_ITEMS} items; they do not fit between its fill and the next casings (pass simple=False)")
        out.append({**f, "id": _MAX_EDGES * _PIECES + j, "properties": {**p, "__rs_s": 2 * p["__rs_fl"] + 1 + rank[e] * _ITEM_STEP + e * _TIE}})
    return {"type": "FeatureCollection", "features": out}


_PIECES = 24        # the most pieces of one edge in simple mode (20): 3 casing pieces, 2 seams, 2 laps and 2 square-end stubs (_square_end), each with a shadow or a second tunnel piece, 2 fill halves
# the line-sort-key's tie-breaker per edge (2026-10-08): keys differ by at least 0.05 (offsets -0.5, -0.1, 0, 0.1, 0.15, 0.25, 1, 1.5 of
# 2 * position; a painted fill + 0.5), so _MAX_EDGES * _TIE (0.01) never reaches the next key
_TIE, _MAX_EDGES = 1e-8, 1_000_000
# an item's step above its edge's fill (2026-10-09): more than the whole tie-breaker range, so every item of a position is above every fill of it;
# a painted road (rsColor) moves its fill and items up 0.5, and its last item must stay under the next position's bridge shadow (2 * position + 1.9):
# 1.5 + _MAX_ITEMS * _ITEM_STEP + _TIE range < 1.9
_ITEM_STEP, _MAX_ITEMS = 0.01, 38


def _edge_features(geo, edges, head_m, cols, fcol, slots):
    """The features of the edges ``edges`` (their numbers) in each source a simple page draws them in, built as :func:`render` builds them for
    the whole page: ``roads`` (the edges), ``simple`` (their pieces) and, with ``slots``, the whole ``slots`` (names and arrows: their chains
    follow the fill numbers, so one road can change them along a street). The level editor's update in place (level_editor.Area). An edge of a
    two-way pair with one casing (``__rs_twin``) comes with its twin: the casing is cut from one of the two."""
    tw = {geo["features"][i]["properties"].get("__rs_twin") for i in edges} - {None}
    sub = {"type": "FeatureCollection", "features": [geo["features"][i] for i in sorted(set(edges) | tw)]}
    out = {"roads": sub["features"], "simple": _simple_pieces(sub, _casing_parts(sub, head_m, cols), cols, CONFIG.bridge_shadow)["features"]}
    if slots:
        out["slots"] = _annotation_slots(geo, (CONFIG.annotations or {}).get("slot_m", 100), cols[0])["features"]
    _mark_cls(geo, out.values(), fcol)
    return out


def _mark_cls(geo, feature_lists, fcol):
    """``__rs_cls`` on every piece of a road (docs/design/edge_items.md): its edge's ``fcol`` value. A name or an arrow carries the chain's
    ``highway``, not ``filter_col``: the class filter reads __rs_cls on every piece (the shadows and 3D decks, which cover several edges, are
    decided per edge in the page)."""
    cls_of = [ft["properties"].get(fcol) for ft in geo["features"]]
    for fs in feature_lists:
        for ft in fs:
            ft["properties"]["__rs_cls"] = cls_of[ft["properties"]["__rs_edge"]]


def _simple_cap():
    """Simple mode's line-cap per piece: a dashed piece butt (a round cap would seal the gaps), else the piece's ``__rs_cap`` (square, flat or round)."""
    return ["case", ["to-boolean", ["get", "__rs_dash"]], "butt", ["==", ["get", "__rs_k"], 4], "butt", ["==", ["get", "__rs_k"], 5], "butt",
            ["==", ["get", "__rs_cap"], "square"], "square", ["to-boolean", ["get", "__rs_cap"]], "butt", "round"]


def _simple_dasharray(dashes, ratio):
    """Simple mode's line-dasharray per piece (in line widths, as the full look's): a tunnel's dash piece ``ratio``, a dashed class's fill its own
    ``__rs_dash`` ("4,4"), any other piece solid ([1, 0]). A property cannot hold an array on a GeoJSON source, hence the match on the text."""
    solid = ["literal", [1, 0]]
    by = ["match", ["to-string", ["coalesce", ["get", "__rs_dash"], ""]], *[x for d in dashes for x in (d, ["literal", [float(v) for v in d.split(",")]])], solid]
    return ["case", ["==", ["get", "__rs_k"], 4], ["literal", [float(v) for v in ratio]], by if dashes else solid]


def _simple_color(bridge_color, tunnels=False):
    """Simple mode's line-color: a bridge shadow ``bridge_shadow_color``, a casing piece its casing colour (a bridge's ``bridge_color``), a fill its fill; on a map with
    ``tunnels`` a tunnel's fill takes the tunnel look (_tun_mix toward ``tunnel_toward`` at ``tunnel_strength``) and its casing pieces the palette's
    two colours moved the same way (gap ``__rs_k`` 3, dashes 4; the gap clear for "One colour"). The page builds the same again on every
    recolouring (the simple-mode script)."""
    c, b = ["==", ["get", "__rs_k"], 0], ["to-boolean", ["get", "__rs_bridge"]]
    base, fill = ["coalesce", ["get", "__rs_casing"], "#000000"], ["coalesce", ["get", "__rs_fill"], "#888888"]
    item = ["coalesce", ["get", "__rs_ic"], "#888888"]                  # an item (__rs_k 5) its own colour, not the road's colouring
    cases = [["==", ["get", "__rs_k"], 2], CONFIG.bridge_shadow_color, c, ["case", b, bridge_color, base]]
    if tunnels:
        to, _, s = _tun_settings()                             # the chosen tunnel colour (tunnel_toward), as the full look and the page's _simpleColor
        pair = CONFIG.tunnel_palettes[CONFIG.tunnel_palette]
        toward = lambda x: ["interpolate", ["linear"], s, 0, x, 100, to]
        fill, item = _tun_mix(fill, to, s), _tun_mix(item, to, s)
        cases += [["==", ["get", "__rs_k"], 3], toward(pair[1]) if pair else "rgba(0,0,0,0)",
                  ["==", ["get", "__rs_k"], 4], toward(pair[0] if pair else _TUN_TO["dash"])]
    return ["case", *cases, ["==", ["get", "__rs_k"], 5], item, fill]


def _by_feature(cases, default):
    """One zoom curve that picks a curve per feature: ``cases`` [(condition, curve), ...], else ``default``. MapLibre allows ``["zoom"]``
    only in a top-level curve, so the choice goes inside each stop; the curves must share their stops."""
    curves = [c for _, c in cases] + [default]
    if any(c[:3] != default[:3] or c[3::2] != default[3::2] for c in curves):
        raise ValueError("simple=True: the width curves do not share their zoom stops")
    out = list(default[:3])
    for i, z in enumerate(default[3::2]):
        out += [z, ["case", *[x for cond, c in cases for x in (cond, c[4 + 2 * i])], default[4 + 2 * i]]]
    return out


def _exp2(curve, top=22):
    """A zoom curve as a base-2 exponential one with a stop at ``top`` (its last value, as it was frozen past its last stop), so a metre curve
    (:func:`_metre_curve`) on its stops is exact at every zoom (2026-10-09: on the linear class curves, items' widths and offsets were linear
    between stops and stopped growing past zoom 20, so the lanes overlapped zoomed in). The class curves between their whole-zoom stops move
    a few per cent at most."""
    out = ["interpolate", ["exponential", 2], ["zoom"], *curve[3:]]
    return out + [top, curve[-1]] if curve[-2] < top else out


def _metre_curve(like, prop):
    """A zoom curve in px for the metres in ``prop`` (over cos(latitude), null 0) on the stops and interpolation of ``like``, for
    :func:`_by_feature`: exact at each stop (512 * 2^z / C px per metre), and between them too where ``like`` is base-2 exponential."""
    out = list(like[:3])
    for z in like[3::2]:
        out += [z, ["*", ["coalesce", ["get", prop], 0], round(512 * 2 ** z / 40075016.686, 6)]]
    return out


def _place_edge_overlays(layers, edge, levels, pat_over=False):
    """Splice the layers of the overlays attached to edges into ``layers``: for each position, after its fills and before its one-way arrows (else its street
    names, else right after its fills), by order, then by the order of the overlays (docs/design/edge_overlays.md).
    ``pat_over``: the tunnel pattern of a position (its ``-pat`` fill layer) is drawn after the overlays of the position, over them."""
    for pos in levels:
        mine = [x for x in edge if x[0] == pos]
        if not mine:
            continue
        ids = [l["id"] for l in layers]
        stop = next((f for f in ("roads-arrows" if pos == 0 else f"roads-arrows-lv{pos}", "roads-labels" if pos == 0 else f"roads-labels-lv{pos}") if f in ids), None)
        if stop:
            at = ids.index(stop)
        else:
            fam = {_level_id(x, pos) for x in _FILL_FAMILY}
            dash = _level_id("roads-fill", pos) + "-dash"
            at = max(i for i, n in enumerate(ids) if n in fam or n.startswith(dash)) + 1
        group = [lyr for _, _, _, group in sorted(mine, key=lambda x: (x[1], x[2])) for lyr in group]
        layers[at:at] = group
        if pat_over:
            pid = _level_id("roads-fill-pat", pos)
            pats = [l for l in layers if l["id"] == pid]
            layers[:] = [l for l in layers if l["id"] != pid]
            at = max(i for i, l in enumerate(layers) if l is group[-1]) + 1
            layers[at:at] = pats
    return layers


# The page template lives in static/web_template.html (placeholders: __TITLE__, __STYLE__, …)
# so the HTML/JS is editable and lintable as HTML, not as a Python string.
with open(os.path.join(os.path.dirname(__file__), "static", "web_template.html"),
          encoding="utf-8") as _fh:
    _HTML = _fh.read()


# The notebook preview loads MapLibre from the CDN at the vendored version (test pins the match;
# simple mode's per-feature line-cap / line-dasharray need >= 5.22). The preview is an
# <iframe srcdoc>, whose location.origin is "null" (the URL about:srcdoc), while MapLibre's blob
# worker reports the notebook server's origin; MapLibre 4.0 - 5.19 drops worker messages whose
# origin differs, so every GeoJSON / vector source stalls: style never finishes loading, zero
# roads (Notebook 7, JupyterLab, Streamlit, any srcdoc). 5.20 accepts the "null" origin.
# Checked headless against Jupyter Notebook 7.5 and JupyterLab 4.5 (2026-10-07).
_MAPLIBRE_CDN = "https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist"


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
        # tiles=True too: pmtiles.js's Protocol.tile takes the promise-style call of MapLibre 4+.
        slim = (self._tpl
                .replace("<style>__MAPLIBRE_CSS__</style>",
                         f'<link rel="stylesheet" href="{_MAPLIBRE_CDN}/maplibre-gl.css"/>')
                .replace("<script>__MAPLIBRE_JS__</script>",
                         f'<script src="{_MAPLIBRE_CDN}/maplibre-gl.js"></script>'))
        return (f'<iframe srcdoc="{_html.escape(slim, quote=True)}" '
                'style="width:100%;height:640px;border:0;border-radius:6px"></iframe>')


def render(gdf, palette: str = DEFAULT_PALETTE, highway_col: str = "highway",
           filter_col: str = None,
           styler=None, basemap=None, basemaps=None, name: str = "roadstyle",
           offset_frac: float = 0.28, width_frac: float = 0.6, offset_zoom: int = 15,
           tunnel_col: str = "tunnel", bridge_col: str = "bridge", layer_col: str = "layer",
           edge_id_col: str = "edge_id", road_fill: bool = True, cap_col: str = None, cap_start_col: str = None, cap_end_col: str = None, casing_level_col: str = None, fill_level_col: str = None, casing_start_col: str = None, casing_end_col: str = None, head_m: float = 5.0, head_start_m_col: str = None, head_end_m_col: str = None, directed_col: str = None, driving_col: str = None,
           width_m_col: str = None, width_m_zoom: float = 16, casing_m: float = 0.15, casing_min_px: float = 0.0,
           pitch: float = None, bearing: float = None, view_3d: bool = False,
           arrows: bool = True, labels: bool = True, filter_control: bool = True,
           basemap_switcher: bool = True, zoom_readout: bool = True,
           road_popup=True, road_tooltip=False, hover_delay_ms: int = 300, popup_mode: str = None,
           street_view: bool | str = "window", street_view_key: str | None = None,
           tooltip=None, hover_color: str = "#b388ff", select_color: str = "#7c4dff", boundary=None,
           color_options=None, color_active=0, views=None, overlays=None, compress: bool = True, tunnel_control: bool = False,
           tiles: bool = False, simple: bool = True,
           minzoom=None, legend: bool = True,
           api_key: str | None = None, _edges=None, **_ignore):
    """Build a self-contained MapLibre map of the styled edges.

    Every edge is drawn by two **positions**, the number where its casing is drawn and the number where its fill is drawn
    (docs/design/levels_split_casing.md): lowest first, at each position all casings before all fills. Without level columns
    they are computed here by ``compute_levels(method="solve")`` with its defaults (bands from the ``tunnel`` / ``bridge`` / ``layer``
    columns, the priority order). The renderer takes no band and no order (docs/design/level_input.md): to give them, compute the levels
    first (``compute_levels(edges, band_col=..., order=...)``, or ``level_input`` + ``solve_levels``) and pass the columns. Needs scipy.
    ``casing_level_col`` / ``fill_level_col`` (and
    ``casing_start_col`` / ``casing_end_col``, ``head_m``) name columns you computed yourself, with ``compute_levels`` or
    anything else, and draw them as they are. ``head_start_m_col`` / ``head_end_m_col``: an edge's own head lengths in metres
    (``solve_levels``' ``head_start_m`` / ``head_end_m``; null = ``head_m``). Null = 0. A bridge keeps its look (heavier casing), a tunnel its look (faded, dashed).
    ``cap_col`` names a column: a true value draws that edge's casing and fill with **square** ends
    (butt caps) instead of round ones, where an edge is one piece of a longer road and meets its
    other piece (docs/design/square_ends.md). The value ``"square"`` draws a flat end that reaches as
    far past the end point as a round one (MapLibre's square cap): the road keeps its drawn length.
    Null / false = round ends, as always. ``cap_start_col`` / ``cap_end_col`` set one end each, with the
    same values (``"round"`` too); null = ``cap_col``'s. An edge whose two ends differ is drawn from its
    casing heads and two fill halves; needs the level columns.

    ``road_fill=False`` draws each road's casing but not its fill: the road's own fill layers stay (so a click and a hover still find the road) but are invisible, and the things attached to
    the roads with ``Overlay(edge_col=...)`` are the fill (docs/design/edge_overlays.md, "Three ways to use it").

    ``directed_col`` names a column saying whether an edge is a direction of travel of its own
    (true / null) or an undirected edge (false: a footway stored both ways, a one-way street's
    walking-only reverse). An edge and its reverse are drawn as two lanes only when neither is
    false; otherwise both are drawn centred, full width, as one line. :func:`roadstyle.is_directed` makes
    it from duckOSM-like edges: an edge open to cars or bikes that is not a path.

    ``driving_col`` names a boolean column saying whether cars may drive an edge (duckOSM's ``driving``); null = every edge counts as driving
    (null values too). It decides the arrows only, never the drawing: an edge gets a one-way arrow only if it is one-way and driving.

    ``width_m_col`` names a column of widths in metres (a lane, a road with a ``width`` tag, a
    canal): from ``width_m_zoom`` on, such a line is drawn exactly that wide, its casing
    ``casing_m`` metres inside each edge; null = the class width (docs/design/metre_widths.md). ``casing_min_px``: a casing
    in metres is never thinner than this many pixels each side of its fill (0 = exact metres; a thin casing goes under a pixel).

    UI toggles (all on by default):
      - ``arrows`` — one-way direction chevrons along each one-way edge;
      - ``labels`` — curved street-name labels (from the ``name`` column);
      - ``filter_control`` — a collapsible checkbox panel to show/hide each road class;
      - ``zoom_readout`` — the small "z 13.2" zoom level beside the scale bar (default on);
      - ``basemap_switcher`` — the in-map base-layer dropdown (uses ``basemap`` / ``basemaps``);
      - ``road_popup`` — the info popup shown when a road is clicked (click-to-select is kept either
        way). ``True`` (default) shows the curated :data:`DEFAULT_ROAD_POPUP` fields; pass a list of
        field names for a custom set, ``"all"`` for every column, or ``False`` to disable and drive
        your own readout from ``window.map`` events. ``name`` is the bold title; ``bridge`` /
        ``tunnel`` appear only when the road is one.
      - ``street_view`` — Google Street View of the clicked road, facing the way the clicked edge
        runs (a road's two directions get opposite headings); no API key. ``"window"`` (default):
        a Street View button on the map opening a floating, draggable, resizable window that
        follows each clicked road (nothing is loaded from Google while it is closed). ``True``: a
        plain link in the road read-out instead (opens Google Maps in a new tab). ``False``: none.
      - ``street_view_key`` — a Google Maps JavaScript API key for the ``"window"``: its bar then
        offers Linked (a real panorama; the map marker walks and turns with the viewer, street
        imagery only) and Classic (the keyless embed), as on :func:`render_street_view`. The key
        is written into the page - restrict it to your site's addresses. Default: the environment
        variable ``GOOGLE_MAPS_KEY``, so every map built where it is set has it. Without a key, unchanged.
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

    ``tunnel_control`` (default False: it was the tool for choosing the tunnel look, 2026-10-07): on a map with tunnels, a *Tunnels* box with v2's tunnel slider (0 = normal colours, 100 = the full
    tunnel colours), its presets, the casing palette and the dash ratio; ``window.rsSetTunnelStyle({strength, palette, ratio})`` does the
    same from your own UI. The starting values are the settings ``tunnel_strength``, ``tunnel_palette`` and ``tunnel_casing_dash``
    (docs/design/tunnel_look.md).

    ``views`` (optional) adds a *View* menu next to *Colour by*: ``{name: {setting: value}}``, each view a set of settings
    applied together (docs/design/core_model_and_views.md). The settings are ``color`` (a ``color_options`` name), ``road_fill``
    (bool), ``overlays`` (``{label: bool}``), ``classes`` (a list of road classes), ``bridges``, ``tunnels``, ``view3d`` (bool)
    and ``basemap`` (a key); a view sets only what it names. The page opens with the first view. ``window.rsSetView(name|index)``
    applies one from your own UI.

    ``overlays`` (optional) draws extra layers the caller brings — a list of :class:`Overlay`
    (zone polygons, POI circles, any geometry). Each becomes its own source + layer(s), placed
    ``under`` or ``over`` the roads, clickable for a popup of its fields, and toggled from a
    *Layers* control.

    ``simple=True`` (the default; ``simple=False`` draws the full look) draws every road piece in ONE line layer: the casings, cut into their heads as here,
    and the fills of every position, ordered by ``line-sort-key`` (position by position, at each position every casing, then every
    fill), with colour and width per feature. Much faster to load and zoom on a big page. A bridge's casing is ``bridge_casing_extra`` px
    wider each side than in the full look, and its shadow (``bridge_shadow``) lies evenly around its main part, blurred, not offset; both grow with the zoom (no shadow and the full look's bridge casing below zoom 14, full from 17). The tunnel casing dashes (two pieces: the palette's gap colour, then the dashes), the dashed classes' dashes and each road's end shapes (``cap_col`` ...) are per feature (MapLibre 5.8 and 5.22; the notebook preview's MapLibre 3.6 draws them solid and round). It leaves out the twin end caps;
    street names and one-way arrows are one layer each, above all roads (a name of a road under a bridge can show on the bridge),
    and the items of ``Overlay(edge_col=...)`` are drawn above all roads too. With ``tiles=True`` the pieces are a layer (``simple``) of the archive. ``tunnel_control=True`` works: the colour, strength, palette and dash ratio recolour the one road layer.

    ``tooltip`` is a convenience alias for the shared backend arg (folium / CLI ``--tooltip``): when
    given and ``road_tooltip`` is unset, its value drives the hover tooltip here too, so the same
    call works across backends."""
    # `tooltip=` is the folium/CLI hover arg; the web backend's own name is `road_tooltip`. Alias it
    # through so a shared `tooltip=`/`--tooltip` works on the web backend instead of being ignored.
    if tooltip is not None and not road_tooltip:
        road_tooltip = tooltip
    # road_popup: True -> curated DEFAULT_ROAD_POPUP; a list/tuple -> those fields; "all" -> every
    # column; False -> no popup. Baked into the page as (enabled flag, field list-or-null).
    # popup_mode="panel" docks the read-out as a side panel and combines with ANY field spec;
    # road_popup="panel" stays as shorthand for panel mode with the default fields.
    if street_view not in (True, False, "window"):
        raise ValueError(f'street_view must be True, False or "window", got {street_view!r}')
    street_view_key = street_view_key or os.environ.get("GOOGLE_MAPS_KEY") or None     # every page, not only those that pass it (2026-10-10)
    mode = popup_mode or "popup"
    if road_popup is False:
        popup_on, popup_fields = False, None
    elif road_popup is True:
        popup_on, popup_fields = True, list(DEFAULT_ROAD_POPUP)
    elif road_popup == "panel":                       # docked side panel instead of a popup
        popup_on, popup_fields, mode = True, list(DEFAULT_ROAD_POPUP), "panel"
    elif isinstance(road_popup, str):
        popup_on, popup_fields = True, None
    else:
        popup_on, popup_fields = True, list(road_popup)
    for k in ("band_col", "order"):                     # inputs of the level step, not of the drawing (docs/design/level_input.md)
        if k in _ignore:
            raise ValueError(f"render_edges takes no {k}: compute the levels first (rs.compute_levels(edges, {k}=...), or rs.level_input + "
                             "rs.solve_levels) and pass casing_level_col / fill_level_col / casing_start_col / casing_end_col")
    g = gdf.to_crs(4326)
    if not (casing_level_col or fill_level_col):       # the only way of drawing: positions, computed here with the level step's defaults
        from .levels import compute_levels
        g = compute_levels(g, layer_col=layer_col, bridge_col=bridge_col, tunnel_col=tunnel_col, method="solve",
                           highway_col=highway_col, head_m=head_m)
        casing_level_col, fill_level_col = "casing_level", "fill_level"
        casing_start_col, casing_end_col = "casing_start", "casing_end"

    color_opts_meta = None
    if color_options:
        # one pre-resolved fill set per "colour by" option — options bake only their FILLS; the
        # shared width/casing/dash comes from the road palette's own styler, so a data-coloured
        # map keeps the palette's plate casing (a data styler has none of its own).
        items = (list(color_options.items()) if isinstance(color_options, Mapping)
                 else [(o["name"], {k: v for k, v in o.items() if k != "name"})
                       for o in color_options])
        frames = [(name, option_styler(highway_col, palette, opts).resolve_frame(g))
                  for name, opts in items]
        style_rf = (styler or build_styler(palette=palette, highway_col=highway_col)).resolve_frame(g)
        geo, color_opts_meta = bake_color_options(fc_dict(g), frames, style_rf=style_rf)
        _names = [n for n, _ in items]
        _active = (color_active if isinstance(color_active, int)
                   else _names.index(color_active) if color_active in _names else 0)
    else:
        _active = 0
        if styler is None:
            styler = build_styler(palette=palette, highway_col=highway_col)
        rf = styler.resolve_frame(g)
        geo = bake_props(fc_dict(g), rf)   # per-edge __rs_fill/__rs_casing
        if legend and getattr(rf, "legend", None):
            # a data styler (color_by / cmap / colors) stashes legend metadata on its resolved
            # frame; surface it as a single legend-only "colour by" entry so the page draws the
            # legend (one entry ⇒ no dropdown, just the key). Class styling carries none, and
            # legend=False opts out — matching the folium backend's `legend` arg.
            color_opts_meta = [{"name": rf.legend.get("title") or "data",
                                "prop": "__rs_fill", "legend": rf.legend}]
    _mark_twoway(geo, directed_col, highway_col, driving_col)
    if CONFIG.single_line_classes:
        _mark_single_line(geo, highway_col, set(CONFIG.single_line_classes))
    _mark_lvl(geo, tunnel_col, bridge_col, layer_col)
    _mark_caps(geo, cap_col, cap_start_col, cap_end_col)
    for ft in geo["features"] if (head_start_m_col or head_end_m_col) else ():          # this edge's head lengths (null: head_m)
        p = ft["properties"]
        for col, k in ((head_start_m_col, "__rs_hs"), (head_end_m_col, "__rs_he")):
            v = p.get(col) if col else None
            if v is not None and v == v and float(v) > 0:
                p[k] = float(v)
    levels = _mark_levels(geo, casing_level_col, fill_level_col, casing_start_col, casing_end_col) if (casing_level_col or fill_level_col) else None
    if CONFIG.twin_casing not in ("one", "each"):
        raise ValueError(f'twin_casing must be "one" or "each", got {CONFIG.twin_casing!r}')
    pairs = CONFIG.twin_casing == "one" and _mark_twin_casing(geo, highway_col, edge_id_col, head_m)   # one casing per two-way pair (levels given or computed above)
    if pairs:
        _mark_twin_dead_ends(geo, cap_col, cap_start_col, cap_end_col)      # a pair's dead end without a given cap: square
    if width_m_col:
        _mark_width_m(geo, width_m_col, casing_m)
        for ft in geo["features"] if pairs else ():     # a pair with metres on both: the other direction's (_width_m_expr, _offset_expr)
            p, tw = ft["properties"], ft["properties"].get("__rs_twin")
            q = geo["features"][tw]["properties"] if tw is not None else {}
            if "__rs_wm" in p and "__rs_wm" in q:
                p["__rs_twm"] = q["__rs_wm"]
    _stringify_unsafe_ints(geo)   # BIGINT ids (e.g. edge_id) -> string so JS doesn't round them

    # active base map + the set offered to the in-map switcher (active shown first)
    # the primary base map layer is a *setting* (config.basemap, defaults.json), overridable
    # per call with `basemap=`
    active = basemap or CONFIG.basemap
    active_bm = get_basemap(active, api_key=api_key)
    bkeys = list(basemaps) if basemaps else list(DEFAULT_SWITCHER)
    bms_list = [active_bm] + [get_basemap(k, api_key=api_key) for k in bkeys if k != active_bm.key and k != active]
    # maxzoom + attr: switching rebuilds the raster source, whose maxzoom is fixed at creation
    bms = [{"key": b.key, "label": b.label, "tiles": _tiles(b), "bg": _bg_color(b),
            "maxzoom": b.maxzoom, "attr": b.attr}
           for b in bms_list]
    if not basemap_switcher and not basemaps:
        # no dropdown and no explicit set -> bake only the fixed backdrop. An explicit
        # `basemaps=` list stays fully addressable via window.rsSetBasemap (custom UI).
        bms = bms[:1]
    style = _basemap_style(active_bm)
    if "bm" not in style["sources"]:
        # a blank base map is active but the switcher offers tiled ones: pre-create the raster
        # layer hidden, so switching is a visibility flip (hidden layers fetch no tiles)
        _b = next((b for b in bms if b["tiles"]), None)
        if _b:
            style["sources"]["bm"] = {"type": "raster", "tiles": _b["tiles"], "tileSize": 256,
                                      "maxzoom": _b["maxzoom"], "attribution": _b["attr"]}
            style["layers"].append({"id": "basemap", "type": "raster", "source": "bm",
                                    "layout": {"visibility": "none"}})
    # roads source: inline GeoJSON by default; with `tiles=True` a PMTiles archive embedded in
    # the page instead (MapLibre parses only the tiles in view — the client-side scale path).
    # Feature ids are the feature's index either way (the feature's id / baked MVT id), so
    # feature-state, rsFilter/rsColor and the sidecar table share one id space. Every piece of a road names its edge by
    # that same index (``__rs_edge``, docs/design/edge_items.md): the roads carry it themselves.
    for _i, _ft in enumerate(geo["features"]):
        _ft["properties"]["__rs_edge"] = _i
        if not tiles:                                   # the feature id, given (not generateId): the page can swap one road (updateData)
            _ft["id"] = _i
    if _edges is not None:        # not a page: the features of these edges (_edge_features), for the level editor's update in place
        if not simple:
            raise ValueError("_edges: only simple=True")
        return _edge_features(geo, _edges, head_m, (highway_col, filter_col, width_m_col), filter_col or highway_col, arrows or labels)
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
        style["sources"]["roads"] = {"type": "geojson", "data": geo, "tolerance": 0.05}
    ends = _twin_ends(geo, (highway_col, filter_col)) if CONFIG.twin_end_caps and CONFIG.twin_casing == "each" and not simple else []   # one casing: its own caps
    if ends:
        style["sources"]["ends"] = {"type": "geojson",
                                    "data": {"type": "FeatureCollection", "features": ends}}

    # extra overlay layers (zones / POIs / any geometry the caller brings); each gets its own source
    # + paint layer(s), placed under or over the roads, and (if `popup` is set) clickable.
    by_id = None
    if overlays and any(getattr(o, "edge_col", None) for o in overlays) and edge_id_col in g.columns:
        by_id = {_eid(ft["properties"].get(edge_id_col)): ft["properties"] for ft in geo["features"]}
    under_layers, over_layers, ov_meta, edge_layers, items = _build_overlays(style, overlays, hover_color, select_color, roads=by_id,
                                                                             edge_id_col=edge_id_col, fcol=filter_col or highway_col, fill=simple)

    # Round caps + joins everywhere: consecutive edges are separate LineStrings, and a round cap is
    # the only rendering primitive that seals the seam where two of them connect (line-join only
    # works *within* a feature). Network continuity outranks end-cap shape — a round blob at a
    # dead end is cosmetic, a notch at a connection or junction is a break in the network.
    lay = {"line-cap": "round", "line-join": "round",
           "line-sort-key": 0}   # positions only: no class, level or order
    tlay = {**lay, "line-cap": "butt"}                    # butt cap -> clean dash ticks on tunnel casing
    blay = {**lay, "line-cap": "butt"}                    # butt cap -> square bridge deck ends
    wmz = width_m_zoom if width_m_col and pairs else None
    off = _offset_expr(highway_col, offset_frac, offset_zoom, pairs, wmz)
    sw = dict(split_zoom=offset_zoom, split_frac=width_frac)
    # Three bands by draw order (docs/design/levels_and_looks.md): below ground, ground, above, from the level (lvl, the
    # OSM layer) or a caller's band_col, and nothing else. A tunnel or a bridge is only a LOOK on a road of its band:
    # sublayers and data (the tunnel's two-tone casing and light dashes, the bridge's deck casing), never another rule.
    lv = ["coalesce", ["get", "lvl"], 0]
    is_t, is_b = ["to-boolean", ["get", "__rs_tunnel"]], ["to-boolean", ["get", "__rs_bridge"]]
    # the bands come from the levels (position mode bakes __rs_band 0); the renderer takes no band_col (docs/design/level_input.md)
    auto = any(ft["properties"].get("__rs_band") is not None for ft in geo["features"])
    bd = ["coalesce", ["get", "__rs_band"], ["case", ["<", lv, 0], -1, [">", lv, 0], 1, 0]] if auto else lv
    any_tunnel = any(ft["properties"].get("__rs_tunnel") for ft in geo["features"])
    surface = ["==", bd, 0]
    low = ["<", bd, 0]
    bridge = ["!", ["to-boolean", 1]] if levels else ["all", [">", lv, 0], is_b]     # position mode: a bridge is drawn at its positions, no layers of its own
    high = ["all", [">", bd, 0], ["!", is_b]]
    # minzoom: hide minor classes when zoomed out (config.DEFAULT.minzoom, or a caller override).
    # AND-ed onto each road filter rather than given its own layers, so layer ids are untouched.
    mz = ({**CONFIG.minzoom} if minzoom is True else
          {**CONFIG.minzoom, **minzoom} if isinstance(minzoom, dict) else None)
    tunnel = ["all", low, is_t]                     # the tunnel look, inside the low band
    # a tunnel drawn in another band (a caller's band_col: a stretch of it at ground level) keeps its look
    tunnel_g, tunnel_h = ["all", surface, is_t], ["all", high, is_t]
    if mz:
        _z = _minzoom_filter(highway_col, mz)
        surface, low, bridge, high, tunnel, tunnel_g, tunnel_h = (
            ["all", _z, f] for f in (surface, low, bridge, high, tunnel, tunnel_g, tunnel_h))
    def _band_of(p):
        b = p.get("__rs_band")
        if b is None:
            b = p.get("lvl") or 0
        return (b > 0) - (b < 0)
    tun_band = {_band_of(ft["properties"]) for ft in geo["features"] if ft["properties"].get("__rs_tunnel")}
    tun_g, tun_h = 0 in tun_band, 1 in tun_band
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
    if width_m_col:     # metre widths from width_m_zoom on (docs/design/metre_widths.md)
        cw, fw, bcw = (_width_m_expr(highway_col, k, width_m_zoom, bridge_m=CONFIG.bridge_casing_m,
                                     bridge_px=CONFIG.bridge_casing_px, casing_px=casing_min_px, **sw)
                       for k in ("casing", "fill", "wings"))
    style["layers"] += under_layers            # caller overlays drawn beneath the roads (e.g. zones)
    style["layers"] += [
        # The low band first, so the ground roads above paint over it at crossings. A tunnel is a road of this band with the
        # tunnel LOOK: its casing drawn by the dash sublayer alone, light dashes on the fill (a sublayer), and the colours of
        # v2's tunnel slider (_tunnel_look, docs/design/tunnel_look.md).
        {"id": "roads-low-casing", "type": "line", "source": "roads", "layout": lay, "filter": low,
         "paint": {"line-color": ["coalesce", ["get", "__rs_casing"], "#000000"],
                   "line-width": cw, "line-offset": off}},
        *_tunnel_casing_dash("roads-low-casing-dash", tunnel, tlay, cw, off, any_tunnel),
        {"id": "roads-low-fill", "type": "line", "source": "roads", "layout": lay, "filter": low,
         "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                   "line-width": fw, "line-offset": off}},
        *_tunnel_fill_dash("roads-low-fill-pat", tunnel, tlay, fw, off, any_tunnel),
        {"id": "roads-casing", "type": "line", "source": "roads", "layout": lay, "filter": surface,
         "paint": {"line-color": ["coalesce", ["get", "__rs_casing"], "#000000"],
                   "line-width": cw, "line-offset": off}},
        *_tunnel_casing_dash("roads-casing-dash", tunnel_g, tlay, cw, off, tun_g),
        {"id": "roads-fill", "type": "line", "source": "roads", "layout": lay, "filter": surface,
         "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                   "line-width": fw, "line-offset": off}},
        *_tunnel_fill_dash("roads-fill-pat", tunnel_g, tlay, fw, off, tun_g),
        # above ground, not a bridge (a positive layer alone: a raised walkway): over the ground roads it crosses
        {"id": "roads-high-casing", "type": "line", "source": "roads", "layout": lay, "filter": high,
         "paint": {"line-color": ["coalesce", ["get", "__rs_casing"], "#000000"],
                   "line-width": cw, "line-offset": off}},
        *_tunnel_casing_dash("roads-high-casing-dash", tunnel_h, tlay, cw, off, tun_h),
        {"id": "roads-high-fill", "type": "line", "source": "roads", "layout": lay, "filter": high,
         "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"],
                   "line-width": fw, "line-offset": off}},
        *_tunnel_fill_dash("roads-high-fill-pat", tunnel_h, tlay, fw, off, tun_h),
        # The bridge LOOK, last (on top). Flat view: heavier square-capped casing reads as a deck.
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
    if ends:
        # two-way pairs end like one road (_twin_ends): per plain band, a road-wide cap's casing
        # just under the band's casings and its fill just under the band's fills, so every lane
        # fill still covers it and a crossing road still covers it too
        ekw = dict(offset_frac=offset_frac, offset_zoom=offset_zoom, split_frac=width_frac)
        rad = {False: _end_radius_expr(highway_col, **ekw), True: _end_radius_expr(highway_col, casing=True, **ekw)}

        # only where both lanes share a colour (a map coloured per direction keeps today's ends);
        # the page's _applyFill rebuilds these when the colour option or a recolour changes
        same = ["==", ["get", "__rs_fill"], ["get", "__rs_fill__b"]]

        def _end(lid, flt, casing):
            col = ["coalesce", ["get", "__rs_casing" if casing else "__rs_fill"], "#000000" if casing else "#888888"]
            if casing:     # no ring where a lower band meets the end (__rs_nocase, _twin_ends)
                flt = ["all", flt, ["!", ["to-boolean", ["get", "__rs_nocase"]]]]
            return {"id": lid, "type": "circle", "source": "ends", "filter": flt,
                    "paint": {"circle-color": ["case", same, col, "rgba(0,0,0,0)"],
                              "circle-radius": rad[casing], "circle-pitch-alignment": "map"}}
        for band, flt in (() if levels else (("low-", low), ("", surface), ("high-", high))):
            for part, casing in (("casing", True), ("fill", False)):
                at = next(n for n, l in enumerate(style["layers"]) if l["id"] == f"roads-{band}{part}")
                style["layers"].insert(at, _end(f"roads-ends-{band}{part}", flt, casing))
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
                l["filter"] = ["!", bridge]
                style["layers"].append(
                    {**l, "id": "roads-highlight-bridge", "maxzoom": _fb, "filter": bridge})
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
        # NOT-dashed. Null-safe on purpose: __rs_dash is baked as null on solid edges, and
        # MapLibre's ["has"] counts a present-null as true — an ["!",["has",…]] filter silently
        # dropped every solid road from the fill/casing layers of any map with dashed classes.
        nod = ["!", ["to-boolean", ["get", "__rs_dash"]]]
        relayered = []
        for l in style["layers"]:
            relayered.append(l)
            lid, base_f = l["id"], l.get("filter")
            if lid in ("roads-fill", "roads-low-fill", "roads-high-fill", "roads-bridge-fill"):
                for di, ds in enumerate(dashes):
                    if lid == "roads-bridge-fill":
                        # a dashed BRIDGE still needs a deck: solid underlay in the class's own
                        # (light) casing colour beneath the dashes — with the black bridge
                        # casing kept below, that's the osm-carto footbridge sandwich. Without
                        # it the ground shows through the gaps and a path crossing UNDER the
                        # bridge reads as if it ran over it.
                        relayered.append(
                            {**l, "id": f"{lid}-deck{di}",
                             "layout": {**l.get("layout", {}), "line-cap": "butt"},
                             "filter": ["all", base_f, ["==", ["get", "__rs_dash"], ds]],
                             "paint": {**l["paint"],
                                       "line-color": ["coalesce", ["get", "__rs_casing"],
                                                      "#f2f2f2"]}})
                    relayered.append(
                        {**l, "id": f"{lid}-dash{di}",
                         "layout": {**l.get("layout", {}), "line-cap": "butt"},
                         "filter": ["all", base_f, ["==", ["get", "__rs_dash"], ds]],
                         "paint": {**l["paint"],
                                   "line-dasharray": [float(x) for x in ds.split(",")]}})
                l["filter"] = ["all", base_f, nod]
            elif lid in ("roads-casing", "roads-casing-dash", "roads-low-casing", "roads-low-casing-dash", "roads-high-casing",
                         "roads-high-casing-dash"):
                # surface/tunnel dashed classes stay casing-less (gaps show the ground); the
                # BRIDGE casing deliberately keeps them — the deck edge is what says "bridge"
                l["filter"] = ["all", base_f, nod]
        # Dashed classes sit at the BOTTOM of the z_order table (footway/path/cycleway ≈ 1),
        # so their layers must draw UNDER the solid casing+fill of the same grade — a street
        # covers a footpath crossing it, exactly as osm-carto orders it. (Bridge-bucket dashes
        # keep their deck sandwich above the solid bridge fill: a footbridge's deck is a
        # structure, not a surface marking.)
        for casing_id, dash_prefix in (("roads-low-casing", "roads-low-fill-dash"),
                                       ("roads-high-casing", "roads-high-fill-dash"),
                                       ("roads-casing", "roads-fill-dash")):
            moved = [l for l in relayered if l["id"].startswith(dash_prefix)]
            if moved:
                rest = [l for l in relayered if not l["id"].startswith(dash_prefix)]
                at = next(i for i, l in enumerate(rest) if l["id"] == casing_id)
                relayered = rest[:at] + moved + rest[at:]
        style["layers"] = relayered

    # square ends (cap_col, docs/design/square_ends.md): MapLibre sets line-cap per layer, not per feature, so
    splits = any(ft["properties"].get("__rs_split") for ft in geo["features"])      # an edge with two different ends (cap_start_col / cap_end_col)
    if splits and not levels:
        raise ValueError("cap_start_col / cap_end_col need the level columns (casing_level_col / fill_level_col): one end at a time is drawn from the casing heads")
    divided = bool(levels and (casing_start_col or casing_end_col or splits or pairs))      # a pair's one casing: a piece of the casings source
    parts = _casing_parts(geo, head_m, (highway_col, filter_col, width_m_col)) if divided else None      # the pieces of a divided casing
    # each band's casing and fill get a butt-capped twin for the edges that ask for it, drawn right after the
    # round layer (a band's casings stay under its fills). Dashed classes draw butt-capped already.
    # A "square" value gets a square-capped twin (-sx): flat, but as far past the end point as a round end.
    # An edge with two different ends draws its fill from "halves" (two pieces, -h / -hsq / -hsx twins of roads-fill) and its casing
    # from the heads; the whole-edge fill layers keep it, transparent: a click, a hover and a selection still find the edge itself.
    if splits or any(ft["properties"].get("__rs_cap") for ft in geo["features"]) or (parts and any(f["properties"].get("__rs_cap") for f in parts)):
        sq = ["to-boolean", ["get", "__rs_cap"]]
        sx = ["==", ["get", "__rs_cap"], "square"]
        squares = any("square" in (p.get("__rs_cap"), p.get("__rs_cap0"), p.get("__rs_cap1")) for p in (ft["properties"] for ft in geo["features"]))
        whole = ["!", ["to-boolean", ["get", "__rs_split"]]]
        if splits:
            style["sources"]["halves"] = {"type": "geojson", "data": {"type": "FeatureCollection", "features": _halves(geo)},
                                          "tolerance": style["sources"]["roads"].get("tolerance", 0.375)}   # the same line as the roads' fill
        capped = []
        for l in style["layers"]:
            if l["id"] in ("roads-low-casing", "roads-low-fill", "roads-casing", "roads-fill",
                           "roads-high-casing", "roads-high-fill"):
                own = []
                if splits and l["id"] == "roads-fill":
                    l = {**l, "paint": {**l["paint"], "line-opacity": ["case", ["!", whole], 0, l["paint"].get("line-opacity", 1)]}}
                capped.append({**l, "filter": ["all", l["filter"], ["!", sq], *own]})
                capped.append({**l, "id": l["id"] + "-sq", "layout": {**l["layout"], "line-cap": "butt"},
                               "filter": ["all", l["filter"], sq, ["!", sx], *own]})
                if squares:
                    capped.append({**l, "id": l["id"] + "-sx", "layout": {**l["layout"], "line-cap": "square"},
                                   "filter": ["all", l["filter"], sx, *own]})
                if splits and l["id"] == "roads-fill":
                    for sfx, cap, f in (("-h", "round", ["!", sq]), ("-hsq", "butt", ["all", sq, ["!", sx]]), ("-hsx", "square", sx)):
                        capped.append({**l, "id": l["id"] + sfx, "source": "halves", "layout": {**l["layout"], "line-cap": cap},
                                       "filter": ["all", l["filter"], f]})
            else:
                capped.append(l)
        style["layers"] = capped

    # drawing-order positions (casing_level_col / fill_level_col, docs/design/level_columns.md): the ground band's casing layers and fill
    # layers are repeated for each position, in position order; an edge is in the casing layers of its casing position and the
    # fill layers of its fill position. Position 0 keeps the layer ids.
    if levels:
        style["layers"] = [l for l in style["layers"] if not l["id"].startswith(("roads-low-", "roads-high-")) and l["id"] not in ("roads-bridge-casing", "roads-bridge-fill")]   # the three bands are gone: positions only
        if divided:       # the divided casing: its own source of pieces (one casing piece per head and for the main part)
            # simplified like the roads (their fill): with MapLibre's default (0.375, 7x coarser) the outline followed a more angular line than
            # the fill it surrounds and wobbled along curves (2026-10-06: "not smooth")
            style["sources"]["casings"] = {"type": "geojson", "data": {"type": "FeatureCollection", "features": parts},
                                           "tolerance": style["sources"]["roads"].get("tolerance", 0.375)}
        if any(ft["properties"].get("__rs_bridge") for ft in geo["features"]):
            # the bridge look in position mode: a heavier black casing, in the casing layers of the edge's position (docs/design/
            # levels_split_casing.md, section 9), one twin of each casing layer so a bridge piece keeps its end's cap (round, flat, square;
            # 2026-10-06: flat ends only, two bridge pieces could not close at a bend or a junction); the other casing layers leave
            # the bridge edges to them
            layers, at, twins = [], 0, []
            for l in style["layers"]:
                if l["id"] in ("roads-casing", "roads-casing-sq", "roads-casing-sx", "roads-casing-dash"):
                    if l["id"] != "roads-casing-dash":
                        twins.append({"id": l["id"] + "-bridge", "type": "line", "source": "roads", "layout": l["layout"],
                                      "filter": ["all", l["filter"], is_b],
                                      "paint": {"line-color": CONFIG.bridge_casing_color, "line-width": bcw, "line-offset": off}})
                    l = {**l, "filter": ["all", l["filter"], ["!", is_b]]}
                    at = len(layers)
                layers.append(l)
            shadows = _bridge_shadows(geo, parts, highway_col, CONFIG.bridge_shadow_trim_m) if CONFIG.bridge_shadow and not simple else []
            if shadows:                    # the bridge shadow: lines through junctions, each at the lowest casing number of its edges
                style["sources"]["shadows"] = {"type": "geojson", "data": {"type": "FeatureCollection", "features": shadows}, "generateId": True,
                                               "tolerance": style["sources"]["roads"].get("tolerance", 0.375)}
                # flat ends: where two shadow lines meet (a casing number changes, a junction) they meet end to end, so the half-transparent
                # shadow does not double into a dark disc (round ends overlapped)
                twins.insert(0, {"id": "roads-casing-bridge-shadow", "type": "line", "source": "shadows", "layout": {**lay, "line-cap": "butt"},
                                 "filter": ["literal", True],
                                 "paint": {"line-color": CONFIG.bridge_shadow_color, "line-blur": CONFIG.bridge_shadow_blur,
                                           "line-width": _width_expr(highway_col, casing=True, scale=1.6, **sw),
                                           "line-translate": list(CONFIG.bridge_shadow_offset), "line-translate-anchor": "viewport"}})
            layers[at + 1:at + 1] = twins
            style["layers"] = layers
        if divided:     # the round seams at the cuts only from zoom 17: below it a seam reaches past a 5 m head and shows as a bump on a flat end
            seam_ok = _seam_filter()        # (and the flat laps only below 17: they ride in the flat-ended -sq layers)
            style["layers"] = [{**l, "filter": ["all", l["filter"], seam_ok]} if l["id"] in ("roads-casing", "roads-casing-bridge", "roads-casing-sq", "roads-casing-sq-bridge") else l
                               for l in style["layers"]]
        style["layers"] = _level_layers(style["layers"], levels, "casings" if divided else None)
        if pairs:          # a two-way pair's one casing as wide as its two directions (casing, bridge casing, tunnel dashes)
            style["layers"] = [{**l, "paint": {**l["paint"], "line-width": _pair_width(l["paint"]["line-width"], highway_col, offset_frac, offset_zoom, wmz)}}
                               if l.get("source") == "casings" else l for l in style["layers"]]
        if decks["features"]:        # 3D: the flat bridge line below flat_below, the extruded deck from it up
            for l in style["layers"]:
                if l["id"].endswith("-bridge") and l["id"].startswith("roads-casing"):
                    l["maxzoom"] = dk["flat_below"]
                elif l["id"].startswith(("roads-casing", "roads-fill")) and l.get("source") in ("roads", "casings"):
                    l["filter"] = ["all", l["filter"], ["any", ["<", ["zoom"], dk["flat_below"]], ["!", is_b]]]
    end_fill_ids, end_casing_ids = ["roads-ends-low-fill", "roads-ends-fill", "roads-ends-high-fill"], ["roads-ends-low-casing", "roads-ends-casing", "roads-ends-high-casing"]
    if levels:        # position mode: a cap's casing is drawn right before its position's casing layers, its fill right before its position's fill layers
        end_fill_ids, end_casing_ids = [], []
        for pos in levels if ends else ():
            for casing, key, root, ids in ((True, "__rs_cl", "roads-casing", end_casing_ids), (False, "__rs_fl", "roads-fill", end_fill_ids)):
                lid = ("roads-ends-casing" if casing else "roads-ends-fill") + ("" if pos == 0 else f"-lv{pos}")
                here = ["==", ["coalesce", ["get", key], 0], pos]
                flt = ["all", _z, here] if mz else here
                at = next(n for n, l in enumerate(style["layers"]) if l["id"] == _level_id(root, pos))
                style["layers"].insert(at, _end(lid, flt, casing))
                ids.append(lid)

    if simple:        # one line layer for every road piece (render's docstring): the full look's road layers and their sources go
        if parts is None:
            parts = _casing_parts(geo, head_m, (highway_col, filter_col, width_m_col))
        style["sources"]["simple"] = {"type": "geojson", "data": _simple_pieces(geo, parts, (highway_col, filter_col, width_m_col), CONFIG.bridge_shadow, items)}
        if not tiles:     # tiles=True: the pieces go into the archive as its "simple" layer
            style["sources"]["simple"]["tolerance"] = style["sources"]["roads"]["tolerance"]
        for k in ("casings", "halves", "shadows", "ends"):
            style["sources"].pop(k, None)
        is_c, is_it = ["==", ["get", "__rs_k"], 0], ["==", ["get", "__rs_k"], 5]
        if items:     # items in metres: every curve of the layer base-2 exponential, so theirs is exact at every zoom (_exp2)
            cw, fw, bcw = _exp2(cw), _exp2(fw), _exp2(bcw)
        soff = _by_feature([(is_it, _metre_curve(_exp2(off), "__rs_iom"))], _exp2(off)) if items else off   # an item: its own metres, not a direction's shift
        flt = [f for f in ((_minzoom_filter(highway_col, mz) if mz else None),
                           _seam_filter(),     # the full look's rule: a seam only from zoom 17 (below it a bridge's seams are dark dots at every head)
                           (["any", ["<", ["zoom"], dk["flat_below"]], ["!", is_b]] if decks["features"] else None)) if f]
        flt = {"filter": ["all", *flt]} if flt else {}
        # a bridge: its casing bridge_casing_extra px wider each side than the full look's, and its shadow (__rs_k 2) bridge_shadow_blur px
        # wider each side again, blurred that much, evenly around it (line-translate is not per feature)
        is_sh, blur = ["==", ["get", "__rs_k"], 2], float(CONFIG.bridge_shadow_blur)
        # both grow with the zoom: none below zoom 14 (the full look's plain bridge casing, no shadow), full from 17 (a stop at each, so linear)
        ramp = lambda z: min(max((z - 14) / 3, 0), 1)
        bwide = _plus_px(bcw, lambda z: 2 * float(CONFIG.bridge_casing_extra) * ramp(z))
        wide = [(is_sh, _plus_px(bcw, lambda z: 2 * (float(CONFIG.bridge_casing_extra) + blur) * ramp(z))), (["all", is_c, is_b], bwide),
                *([(["any", ["==", ["get", "__rs_k"], 3], ["==", ["get", "__rs_k"], 4]], _plus_px(cw, 3))] if any_tunnel else []), (is_c, cw),
                *([(is_it, _plus_px(_metre_curve(fw, "__rs_iwm"), 1))] if items else [])]   # 1 px over: two lanes side by side show no antialiased seam
        op = [1] if road_fill else [["==", ["get", "__rs_k"], 1], 0, 1]
        sdashes = sorted({(f.get("properties") or {}).get("__rs_dash") for f in geo["features"] + items} - {None, ""})
        sdash = {"line-dasharray": _simple_dasharray(sdashes, CONFIG.tunnel_casing_dash or [1, 1])} if sdashes or any_tunnel else {}
        road = {"id": "roads-simple", "type": "line", "source": "simple", "layout": {**lay, "line-cap": _simple_cap(), "line-sort-key": ["get", "__rs_s"]}, **flt,
                "paint": {**sdash, "line-color": _simple_color(CONFIG.bridge_casing_color, bool(any_tunnel)),
                          "line-width": _pair_width(_by_feature(wide, fw), highway_col, offset_frac, offset_zoom, wmz) if pairs else _by_feature(wide, fw), "line-offset": soff,
                          "line-blur": ["interpolate", ["linear"], ["zoom"], 14, 0, 17, ["case", is_sh, blur, 0]],
                          "line-opacity": ["interpolate", ["linear"], ["zoom"], 14, ["case", is_sh, 0, *op], 17, op[-1] if road_fill else ["case", *op]]}}
        # the edges themselves, invisible: what a click, a hover, Street View and the page's fill code find (the roads source, its ids)
        pick = {"id": "roads-fill", "type": "line", "source": "roads", "layout": lay, **flt,
                "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], "#888888"], "line-width": fw, "line-offset": off, "line-opacity": 0}}
        at = next(n for n, l in enumerate(style["layers"]) if l["id"].startswith(("roads-casing", "roads-fill")))
        style["layers"] = [l for l in style["layers"] if not l["id"].startswith(("roads-casing", "roads-fill", "roads-ends"))]
        style["layers"][at:at] = [road, pick]

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
        slots = _annotation_slots(geo, slot_m, highway_col)
        if slots["features"]:
            if not tiles:   # tiles=True ships the slots as a layer of the pmtiles archive
                style["sources"]["slots"] = {"type": "geojson", "data": slots}
                if arrows:     # the page fills it: one arrow per one-way road in the window
                    style["sources"]["arrows"] = {"type": "geojson", "data": {"type": "FeatureCollection", "features": []}}
            # labels take the ARROWS' opacity by default: both are #5b5b5b, but full-opacity
            # text reads near-black next to 70%-opacity icons — "same colour" must mean same
            # rendered colour, not same hex. labels.opacity in settings overrides.
            lpaint = {"text-color": lbl["color"],
                      "text-opacity": lbl.get("opacity", arw["opacity"])}
            if lbl["halo_color"] and lbl["halo_width"]:
                lpaint["text-halo-color"] = lbl["halo_color"]
                lpaint["text-halo-width"] = lbl["halo_width"]
            # one symbol centred on each slot piece; even slots = names, odd = oneway arrows.
            # Text/icon zoom ramps size the symbols; collision culling thins them when zoomed out
            # (a label that outgrows its piece is dropped by MapLibre automatically).
            # ARROWS BEFORE LABELS on purpose: MapLibre resolves symbol collisions in favour of
            # the LATER style layer, so the layer order is the culling priority and names are placed
            # first. An arrow (one per road, placed by the page between two names) that would still touch
            # a name is left out: docs/design/arrows_and_names.md.
            _MINOR = ["footway", "cycleway", "path", "steps",
                      "service", "track", "pedestrian"]
            if arrows:
                # Every one-way slot, repeated along the line — not one arrow per odd slot
                # (line-center on odd slots put ONE arrow per 200 m of chain, so at street zoom
                # a road's only arrow was usually outside the viewport and one-way streets read
                # as unmarked). One arrow layer PER GRADE TIER, each inserted right beside its
                # road tier, so a bridge covers the arrows of the road it crosses instead of
                # every arrow floating above everything.
                def _arrow_layer(lid, tier):
                    # class-aware like the roads themselves: the minzoom table thins arrows
                    # with their road (no arrow floating where the class is still hidden), and
                    # the negated road sort key decides collisions — symbol-sort-key places
                    # LOWER keys first and first-placed wins, so a trunk's arrow beats a
                    # service road's instead of tile order deciding.
                    #
                    # Minor classes wait until z16: below that, a cycleway or service road
                    # running beside a wider road sits INSIDE its stroke — the line loses the
                    # draw order, but its arrows would still paint on top of the big road
                    # (symbols cannot be occluded by lines within a tier). By z16 parallel
                    # lines have separated on screen and the arrows land on their own road.
                    f = ["all", ["==", ["get", "oneway"], 1],
                         tier,
                         ["any", ["!", ["match", ["get", "highway"], _MINOR, True, False]],
                          [">=", ["zoom"], 16]]]
                    if mz:
                        f.append(_minzoom_filter("highway", mz))
                    # minzoom 15, not 14: arrows are a street-scale affordance — at z14 they
                    # were hundreds of unreadable specks (labels start there because names
                    # thin themselves via collision; line-placed icons do not)
                    # one arrow per one-way road in the window (2026-10-06, docs/design/arrows_and_names.md): the page
                    # puts a point in the middle of each chain's visible part into the "arrows" source after every move,
                    # rotated along the road. ponytail: a tiled map (tiles=True) has no slot geometry in the page and keeps the
                    # arrows repeated along every slot; give it the chains' lines too if one arrow per road matters there
                    where = ({"source": "slots", "layout": {"symbol-placement": "line",
                                                            "symbol-spacing": ["interpolate", ["linear"], ["zoom"], 15, 200, 18, 320, 22, 900]}}
                             if tiles else
                             {"source": "arrows", "layout": {"symbol-placement": "point", "icon-rotate": ["get", "b"],
                                                             # where it would touch a name the arrow is left out (2026-10-06): the names are
                                                             # placed first (a later layer), and an arrow never pushes a name away
                                                             "icon-allow-overlap": False, "icon-ignore-placement": True}})
                    return {"id": lid, "type": "symbol", "source": where["source"], "minzoom": 15,
                            "filter": f,
                            "layout": {**where["layout"],
                                       "icon-image": "oneway",
                                       "icon-rotation-alignment": "map",
                                       "symbol-sort-key": ["*", -1, _sort_key("highway")],
                                       # gentle growth, sized like a lane marking, not a
                                       # banner: flat sizes read as "arrows don't scale" but
                                       # tracking road widths 1:1 (~2x/zoom past 18) overshot
                                       # the other way. The narrow classes take 60% so a
                                       # cycleway's arrow does not dwarf its own line. (The
                                       # class factor sits inside the stops: MapLibre only
                                       # allows ["zoom"] in a TOP-LEVEL interpolate.)
                                       "icon-size": ["interpolate", ["exponential", 1.8],
                                                     ["zoom"]] + [
                                           part for z, base in ((15, 0.5), (18, 0.9),
                                                                (22, 3.0))
                                           for part in (z, ["*", base,
                                               ["match", ["get", "highway"],
                                                _MINOR, 0.6, 1.0]])]},
                            "paint": {"icon-opacity": arw["opacity"]}}
                # insert after the LAST layer of the tier's fill family, not after the first
                # "-fill": tiled multi-level bridges append deck sub-layers (roads-bridge-
                # fill-deck0/1, -dash0/1) after roads-bridge-fill, and an arrow inserted before
                # them ends up under its own road's deck — a level-3 cycleway on Skanstullsbron
                # rendered arrowless exactly that way.
                fams = (("roads-arrows-tunnel", "<",       # the low band's: a tunnel's too, above its fill
                         lambda i: i.startswith("roads-low-")),
                        ("roads-arrows", "==",
                         lambda i: i in ("roads-casing", "roads-casing-sq", "roads-casing-sx", "roads-fill")
                         or i.startswith("roads-fill-")),
                        ("roads-arrows-bridge", ">",
                         lambda i: i.startswith(("roads-high-", "roads-bridge-"))))
                if simple:        # one arrow layer, above all roads (under the highlight, as the positions' arrows are)
                    style["layers"].insert(next(n for n, l in enumerate(style["layers"]) if l["id"] == "roads-highlight"),
                                           _arrow_layer("roads-arrows", True))
                elif levels:        # position mode: one arrow layer per position, right after that position's fill layers
                    for pos in levels:
                        fam = {_level_id(x, pos) for x in _FILL_FAMILY}
                        dash = _level_id("roads-fill", pos) + "-dash"
                        members = [i for i, l in enumerate(style["layers"]) if l["id"] in fam or l["id"].startswith(dash)]
                        if members:
                            style["layers"].insert(max(members) + 1, _arrow_layer(
                                "roads-arrows" if pos == 0 else f"roads-arrows-lv{pos}",
                                ["==", ["coalesce", ["get", "fl"], 0], pos]))
                else:
                    for lid, cmp, fam in fams:
                        members = [i for i, l in enumerate(style["layers"]) if fam(l["id"])]
                        if members:
                            style["layers"].insert(max(members) + 1, _arrow_layer(lid, [cmp, ["coalesce", ["get", "lvl"], 0], 0]))
            if labels:
                style["glyphs"] = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"
                lf = ["all", ["==", ["%", ["get", "slot"], 2], 0],
                      ["to-boolean", ["get", "name"]],
                      # minor classes wait for z16, like their arrows: a cycleway named after
                      # the street it runs beside would duplicate the street's name onto a
                      # line still hugging the roadway's stroke
                      ["any", ["!", ["match", ["get", "highway"], _MINOR, True, False]],
                       [">=", ["zoom"], 16]]]
                if mz:   # a hidden class must not keep its street name floating either
                    lf.append(_minzoom_filter("highway", mz))
                lf.append(_label_readable_filter())     # no name where it would be under 9 px (its road too narrow at that zoom)
                def _label_layer(lid, flt):
                    return {"id": lid, "type": "symbol", "source": "slots", "minzoom": 14,
                            "filter": flt,
                            "layout": {"symbol-placement": "line-center",
                                       "text-field": ["get", "name"],
                                       "text-font": ["Noto Sans Regular"],
                                       "text-size": _label_size_expr(),          # about 3/4 of the road's fill width
                                       "text-max-angle": 40, "text-padding": 2,
                                       # major streets' names win label-vs-label collisions too
                                       "symbol-sort-key": ["*", -1, _sort_key("highway")]},
                            "paint": lpaint}
                if simple:        # one name layer, above all roads and their arrows
                    style["layers"].insert(next(n for n, l in enumerate(style["layers"]) if l["id"] == "roads-highlight"),
                                           _label_layer("roads-labels", lf))
                elif levels:        # position mode: the names of a position sit right after its arrows (or its fill layers), so a road above covers them
                    for pos in levels:
                        after = "roads-arrows" if pos == 0 else f"roads-arrows-lv{pos}"
                        ids = [l["id"] for l in style["layers"]]
                        if after in ids:
                            at = ids.index(after) + 1
                        else:
                            fam = {_level_id(x, pos) for x in _FILL_FAMILY}
                            dash = _level_id("roads-fill", pos) + "-dash"
                            at = max(i for i, n in enumerate(ids) if n in fam or n.startswith(dash)) + 1
                        style["layers"].insert(at, _label_layer("roads-labels" if pos == 0 else f"roads-labels-lv{pos}",
                                                                ["all", lf, ["==", ["coalesce", ["get", "fl"], 0], pos]]))
                else:
                    style["layers"].append(_label_layer("roads-labels", lf))

    # clip/area boundary outline, drawn on top of the roads (a dashed line tracing the polygon rings)
    if boundary is not None:
        style["sources"]["boundary"] = {"type": "geojson", "data": _boundary_fc(boundary)}
        style["layers"].append(
            {"id": "boundary", "type": "line", "source": "boundary",
             "layout": {"line-cap": "round", "line-join": "round"},
             "paint": {"line-color": "#6a0dad", "line-width": 2.5, "line-opacity": 0.9,
                       "line-dasharray": [3, 2]}})

    # no road layer that nothing can draw (a position without bridges has no bridge layers, ...): the arrows source is filled by the page
    # from the slots, with their properties
    if any(ft["properties"].get("__rs_dup") for ft in geo["features"]):     # a reverse pair drawn as one line (_mark_single_line): its second edge draws nowhere
        nd = ["!", ["to-boolean", ["get", "__rs_dup"]]]
        style["layers"] = [{**l, "filter": ["all", l["filter"], nd] if l.get("filter") else nd}
                           if l.get("source") in ("roads", "casings", "halves") else l for l in style["layers"]]
    feats = {"roads": geo["features"], "slots": slots["features"], "arrows": slots["features"]}
    for sid, src in style["sources"].items():
        if src.get("type") == "geojson" and isinstance(src.get("data"), dict):
            feats.setdefault(sid, src["data"].get("features", []))
    style["layers"] = _drop_empty_layers(style["layers"], feats)

    # the road's own fill: its layers and their opacity as drawn, so that rsSetRoadFill (and a view's road_fill) can put it back
    fill_paint = {}
    for lyr in style["layers"]:
        if lyr["id"].startswith("roads-fill") and not lyr["id"].endswith("-pat"):      # the tunnel pattern stays: over the items (_place_edge_overlays)
            fill_paint[lyr["id"]] = {k: lyr["paint"].get(k) for k in ("line-opacity",)}
        elif lyr["id"].startswith("roads-ends-fill"):
            fill_paint[lyr["id"]] = {k: lyr["paint"].get(k) for k in ("circle-opacity", "circle-stroke-opacity")}
    if not road_fill:     # the casing of the road, not its fill: the fill layers stay for clicks and hovers, invisible
        for lyr in style["layers"]:
            if lyr["id"] in fill_paint:
                lyr["paint"] = {**lyr["paint"], **dict.fromkeys(fill_paint[lyr["id"]], 0)}
    if edge_layers and simple:     # one road layer: the items above all roads, position by position, before the arrows and names
        at = next(n for n, l in enumerate(style["layers"]) if l["id"] in ("roads-arrows", "roads-labels", "roads-highlight"))
        style["layers"][at:at] = [lyr for _, _, _, group in sorted(edge_layers, key=lambda x: x[:3]) for lyr in group]
    elif edge_layers:       # the overlays attached to edges: after the fills of their position, before its arrows (docs/design/edge_overlays.md)
        style["layers"] = _place_edge_overlays(style["layers"], edge_layers, levels, pat_over=not road_fill)
    style["layers"] += over_layers             # caller overlays drawn on top of the roads (e.g. POIs)
    tun_colour, tun_toward, tun_strength = _tun_settings()
    tun_paint, tun_dash, tun_casing = {}, [], {}
    if any(ft["properties"].get("__rs_tunnel") for ft in geo["features"]):      # the tunnel look (docs/design/tunnel_look.md)
        if CONFIG.tunnel_palette not in CONFIG.tunnel_palettes:
            raise ValueError(f"tunnel_palette {CONFIG.tunnel_palette!r} is not in tunnel_palettes {list(CONFIG.tunnel_palettes)}")
        tun_to = {**_TUN_TO, "fill": tun_colour}
        tun_paint, tun_dash, tun_casing = _tunnel_look(style["layers"], {l["id"] for _, _, _, grp in edge_layers for l in grp},
                                           tun_strength, arw["color"], tun_to)

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
           "swatches": swatches,
           # any elevated / below-ground feature ⇒ the panel offers a Bridges / Tunnels on/off row
           # (rsSetBridges / rsSetTunnels)
           "bridges": any((f.get("properties") or {}).get("lvl", 0) > 0
                          for f in geo.get("features", [])),
           "tunnels": any((f.get("properties") or {}).get("lvl", 0) < 0
                          for f in geo.get("features", []))}

    view_list = _check_views(views, [o["name"] for o in color_opts_meta or []] if color_options else [],
                             [o["label"] for o in ov_meta], classes, [b["key"] for b in bms])

    # the class every piece of a road is filtered by: its edge's ``filter_col`` value, else ``highway_col``
    _mark_cls(geo, [fc["features"] for fc in [geo, slots] + [style["sources"][k]["data"] for k in ("casings", "halves", "ends", "simple")
                                                              if k in style["sources"]]], fcol)

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
        extra = [{"name": "slots", "fc": slots, "minzoom": 14}] if slots["features"] else []
        keep = {highway_col, filter_col or highway_col, "__rs_twoway", "__rs_edge", "lvl", width_m_col}
        line_layers = []
        # the casing pieces, simple mode's pieces and the twin end caps ride in the same archive (docs/design/levels_split_casing.md, 12.1);
        # a simple piece's tile id is its index in the layer, not the inline 16 * edge + k (only the level editor's updateData reads that)
        for name, kind in (("casings", "line"), ("simple", "line"), ("ends", "point")):
            src = style["sources"].pop(name, None)
            for lyr in style["layers"]:
                if lyr.get("source") == name:
                    lyr["source"], lyr["source-layer"] = "roads", name
            if src and src["data"]["features"]:
                if kind == "line":
                    line_layers.append({"name": name, "fc": src["data"], "keep": keep})
                else:
                    extra.append({"name": name, "fc": src["data"], "minzoom": tc["minzoom"]})
        pmt = _tiler.build_pmtiles(
            geo, class_col=highway_col, keep=keep,
            minzoom_table=mz, minzoom=tc["minzoom"], maxzoom=tc["maxzoom"],
            extent=tc["extent"], buffer_px=tc["buffer_px"], extra_layers=extra or None,
            line_layers=line_layers or None)
        side = _tiler.sidecar(geo)

    minx, miny, maxx, maxy = (float(v) for v in g.total_bounds)
    # after every style/filter/bounds decision above — those read the features, the browser never does
    gz = _compress_sources(style) if compress else {}
    html = (_HTML.replace("__TITLE__", _html.escape(name))
            .replace("__ARROW_COLOR__", str(arw["color"]))
            .replace("__STYLE__", json.dumps(style))
            .replace("__BASEMAPS__", json.dumps(bms))
            .replace("__BM_SWITCHER__", json.dumps(bool(basemap_switcher)))
            .replace("__ZOOM_READOUT__", json.dumps(bool(zoom_readout)))
            .replace("__FILTER__", json.dumps(flt))
            .replace("__CENTER__", json.dumps([(minx + maxx) / 2, (miny + maxy) / 2]))
            .replace("__PITCH3D__", json.dumps(cam["pitch_3d"]))
            .replace("__MAX_PITCH__", json.dumps(cam["max_pitch"]))
            .replace("__HOVER_COLOR__", json.dumps(hover_color))
            .replace("__SELECT_COLOR__", json.dumps(select_color))
            .replace("__PITCH__", json.dumps(cam["pitch"]))
            .replace("__BEARING__", json.dumps(cam["bearing"]))
            .replace("__BOUNDS__", json.dumps([[minx, miny], [maxx, maxy]]))
            .replace("__RS_FILL_LAYERS__", json.dumps(_fill_layer_ids(levels)))
            .replace("__RS_END_LAYERS__", json.dumps(end_fill_ids)).replace("__RS_END_CASING_LAYERS__", json.dumps(end_casing_ids))
            .replace("__COLOR_OPTIONS__", json.dumps(color_opts_meta or []))
            .replace("__CO_ACTIVE__", str(_active))
            .replace("__OVERLAYS__", json.dumps(ov_meta))
            .replace("__TUNNEL__", json.dumps({"layers": tun_paint, "dash": tun_dash, "casing": tun_casing, "strength": tun_strength,
                                               "palette": CONFIG.tunnel_palette, "palettes": CONFIG.tunnel_palettes,
                                               "ratio": list(CONFIG.tunnel_casing_dash or [1, 1]), "bg": _bg_color(active_bm),
                                               "toward": tun_toward, "towards": CONFIG.tunnel_towards,
                                               "to": {**_TUN_TO, "fill": tun_colour}, "control": bool(tunnel_control and tun_paint)}))
            .replace("__VIEWS__", json.dumps(view_list))
            .replace("__RS_ROAD_FILL__", json.dumps({"on": bool(road_fill), "paint": fill_paint}))
            .replace("__ROAD_POPUP__", "true" if popup_on else "false")
            .replace("__ROAD_POPUP_MODE__", json.dumps(mode))
            .replace("__ROAD_POPUP_FIELDS__", json.dumps(popup_fields))
            .replace("__ROAD_TOOLTIP__", json.dumps(road_tooltip))
            .replace("__HOVER_DELAY_MS__", json.dumps(int(hover_delay_ms)))
            .replace("__STREET_VIEW__", "true" if street_view else "false")
            .replace("__SV_WINDOW__", "true" if street_view == "window" else "false")
            .replace("__SV_WINDOW_KEY__", json.dumps(street_view_key or ""))
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
    if simple:
        html = html.replace("</body>", _SIMPLE_JS.replace("__RS_SIMPLE__", json.dumps({"layer": "roads-simple", "bridge": CONFIG.bridge_casing_color, "shadow": CONFIG.bridge_shadow_color,
                                                                                       "tunnels": bool(any_tunnel),
                                                                                       "dashes": sdashes})) + "</body>", 1)
    if gz:
        html = html.replace("</body>", _INFLATE_JS.replace("__RS_GZ__", json.dumps(gz)) + "</body>", 1)
    # MapLibre stays a placeholder here: WebMap inlines the vendored copy on save (offline file)
    # and swaps in CDN tags for the notebook preview (small enough for notebook output limits).
    return WebMap(html)

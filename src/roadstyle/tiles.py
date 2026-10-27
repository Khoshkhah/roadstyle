"""Vector tiles for the web backend — pack the styled road features into a PMTiles archive.

The archive is embedded base64 into the saved HTML and served to MapLibre from memory via the
vendored ``pmtiles.js`` (``addProtocol``), so the single-file / open-from-disk property is kept.
The win over inline GeoJSON is client-side scale: MapLibre parses only the tiles in view, and
low zooms carry simplified geometry (sub-pixel pieces drop out) instead of every vertex of
every service road. Class thinning is opt-in via the render ``minzoom`` parameter — the
default tiles carry every class at every zoom, matching the inline look.

Tiles carry ONLY the properties the style expressions read (``__rs_*`` paints, the class/filter
columns, ``__rs_twoway``, ``lvl``) plus the feature ``id`` (= the feature's index, the same id space
as the inline roads' own ``id``). Everything else — full attributes for popups/`rsQuery`, per-edge
midpoints and bboxes for `rsSelect`/`rsFocus` — travels in a small gzipped sidecar table the
page inflates separately (see render_web).

Needs the ``tiles`` extra: ``pip install "roadstyle[tiles]"`` (mapbox-vector-tile + pmtiles).
"""
from __future__ import annotations

import functools
import gzip
import io
import json
import math

from . import _assets

# Web-mercator world half-width (m); tile (z,x,y) spans WORLD/2**z starting at (-R, R)
_R = 20037508.342789244


def _tile_bounds(z, x, y):
    s = 2 * _R / (1 << z)
    return (-_R + x * s, _R - (y + 1) * s, -_R + (x + 1) * s, _R - y * s)   # minx,miny,maxx,maxy


def _merc(lon, lat):
    x = lon * _R / 180.0
    lat = max(-89.9, min(89.9, lat))
    y = math.log(math.tan((90 + lat) * math.pi / 360.0)) * _R / math.pi
    return x, y


def _tile_range(bounds, z):
    """Tile x/y index range covering a mercator bbox at zoom z."""
    s = 2 * _R / (1 << z)
    n = (1 << z) - 1
    x0 = max(0, min(n, int((bounds[0] + _R) // s)))
    x1 = max(0, min(n, int((bounds[2] + _R) // s)))
    y0 = max(0, min(n, int((_R - bounds[3]) // s)))
    y1 = max(0, min(n, int((_R - bounds[1]) // s)))
    return x0, x1, y0, y1


def tile_props(props: dict, keep: set) -> dict:
    """The slim per-feature property set baked into the tiles (style reads only these). A false ``__rs_*`` flag is left out: every reader of
    a flag takes a missing key as false (``to-boolean``, a truthy check)."""
    return {k: v for k, v in props.items() if (k.startswith("__rs_") or k in keep) and _kept(k, v)}


def _kept(k, v) -> bool:
    """A value that goes into a tile: not None, and not a ``__rs_*`` flag that is false."""
    return v is not None and not (v is False and k.startswith("__rs_"))


def _prep(fc: dict, keep: set | None, rules=None):
    """Project features to mercator; return ([(idx, geom, bounds, (from, until) zooms, props)], world_bbox). ``rules``: the layer's zoom_rules."""
    from shapely.geometry import shape
    from shapely.ops import transform as shp_transform

    feats, world = [], [1e30, 1e30, -1e30, -1e30]
    for i, ft in enumerate(fc.get("features", [])):
        g = ft.get("geometry")
        if not g:
            continue
        geom = shp_transform(lambda x, y: _merc(x, y), shape(g))
        if geom.is_empty:
            continue
        p = ft.get("properties") or {}
        b = geom.bounds
        world[0] = min(world[0], b[0])
        world[1] = min(world[1], b[1])
        world[2] = max(world[2], b[2])
        world[3] = max(world[3], b[3])
        props = tile_props(p, keep) if keep is not None else \
            {k: v for k, v in p.items() if _kept(k, v)}
        feats.append((i, geom, b, zoom_span(rules, props) if rules else (0, float("inf")), props))
    return feats, world


def zoom_rules(layers, name):
    """A feature's zooms from the style (roadstyle-tiles rules.rs): for each layer that draws the tile layer ``name``, the clauses at the top of
    its filter that read the zoom (``[">=", ["zoom"], E]``, ``["<", ["zoom"], E]``, and an "all" or "any" of them and of clauses on the
    feature). None when a layer draws every feature at every zoom, or no layer draws it."""
    out = []
    for lyr in layers or []:
        if (lyr.get("source-layer") or lyr.get("source")) != name:
            continue
        cs = [c for c in _tops(lyr.get("filter")) if _reads_zoom(c)]
        if not cs:
            return None
        out.append(cs)
    return out or None


def _tops(f):
    """The clauses of a filter that must all hold: the items of its "all", and of an "all" in it."""
    return [c for x in f[1:] for c in _tops(x)] if isinstance(f, list) and f[:1] == ["all"] else [f]


def _reads_zoom(e):
    return isinstance(e, list) and (e[:1] == ["zoom"] or any(_reads_zoom(x) for x in e))


_ALL, _NONE = (0.0, float("inf")), (float("inf"), 0.0)


def _meet(a, b):
    return (max(a[0], b[0]), min(a[1], b[1]))


def _span(c, p):
    """The zooms [from, until) where the clause ``c`` holds for the feature ``p`` (rules.rs span); every zoom for a clause that is not known."""
    def num(e, default):
        v = _ev(e, p) if not _reads_zoom(e) else None
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default
    if isinstance(c, list) and len(c) == 3 and c[1] == ["zoom"] and c[0] == ">=":
        return (num(c[2], 0.0), float("inf"))
    if isinstance(c, list) and len(c) == 3 and c[1] == ["zoom"] and c[0] == "<":
        return (0.0, num(c[2], float("inf")))
    if isinstance(c, list) and c[:1] == ["all"]:
        out = _ALL
        for x in c[1:]:
            out = _meet(out, _span(x, p))
        return out
    if isinstance(c, list) and c[:1] == ["any"]:
        sp = [s for s in (_span(x, p) for x in c[1:]) if s[0] < s[1]]
        return (min(s[0] for s in sp), max(s[1] for s in sp)) if sp else _NONE
    if not _reads_zoom(c) and _known(c):
        return _ALL if _truthy(_ev(c, p)) else _NONE
    return _ALL


def _known(e):
    """An expression of only the operators that ``_ev`` knows (rules.rs known)."""
    if not isinstance(e, list):
        return True
    if e[:1] in (["get"], ["literal"]):
        return True
    return bool(e) and e[0] in ("coalesce", "to-boolean", "!", "all", "any", "==", "!=", "at", "case", "match") and all(_known(x) for x in e[1:])


def zoom_span(rules, p):
    """The zooms [from, until) at which a layer draws a feature with the properties ``p``: the lowest from and the highest until over the layers."""
    sp = [functools.reduce(_meet, (_span(c, p) for c in cs), _ALL) for cs in rules]
    return (min(s[0] for s in sp), max(s[1] for s in sp))


def _truthy(v):
    return v not in (None, False, 0, "") if not isinstance(v, (list, dict)) else True


def _same(a, b):
    num = (int, float)
    if isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        return float(a) == float(b)
    return a == b and type(a) is type(b)


def _ev(e, p):
    """A MapLibre expression's value on a feature, for the operators of the clauses (rules.rs ev); None for another operator."""
    if not isinstance(e, list):
        return e
    if not e or not isinstance(e[0], str):
        return None
    op, a = e[0], e[1:]
    if op == "get":
        return p.get(a[0])
    if op == "literal":
        return a[0]
    if op == "coalesce":
        return next((v for v in (_ev(x, p) for x in a) if v is not None), None)
    if op == "to-boolean":
        return _truthy(_ev(a[0], p))
    if op == "!":
        return not _truthy(_ev(a[0], p))
    if op in ("all", "any"):
        return (all if op == "all" else any)(_truthy(_ev(x, p)) for x in a)
    if op in ("==", "!="):
        return _same(_ev(a[0], p), _ev(a[1], p)) == (op == "==")
    if op == "at":
        i, lst = _ev(a[0], p), _ev(a[1], p)
        return lst[int(i)] if isinstance(i, (int, float)) and isinstance(lst, list) and 0 <= int(i) < len(lst) else None
    if op == "case":
        for c, v in zip(a[:-1:2], a[1:-1:2], strict=True):
            if _truthy(_ev(c, p)):
                return _ev(v, p)
        return _ev(a[-1], p)
    if op == "match":
        x = _ev(a[0], p)
        for lab, v in zip(a[1:-1:2], a[2:-1:2], strict=True):
            if any(_same(lb, x) for lb in (lab if isinstance(lab, list) else [lab])):
                return _ev(v, p)
        return _ev(a[-1], p)
    return None


LIVE_WIDTH_MAX = 3.0      # roadstyle_tiles::buffer::LIVE_WIDTH_MAX: a width that reads a feature state, at most this factor (widthRange [1, 3])


def _bound(e, z, live):
    """roadstyle_tiles::buffer::bound: an upper bound of |e| at the zoom z for every feature, or None."""
    if isinstance(e, bool):
        return None
    if isinstance(e, (int, float)):
        return abs(float(e))
    if not isinstance(e, list) or not e or not isinstance(e[0], str):
        return None
    op, a = e[0], e

    def mx(es):
        m = 0.0
        for x in es:
            v = _bound(x, z, live)
            if v is None:
                return None
            m = max(m, v)
        return m

    if op == "literal":
        x = a[1]
        if isinstance(x, list):
            return mx(x) if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in x) else None
        return _bound(x, z, live)
    if op == "zoom":
        return z
    if op == "feature-state":
        return live
    if op == "at":
        return _bound(a[2], z, live) if len(a) > 2 else None
    if op == "abs":
        return _bound(a[1], z, live) if len(a) > 1 else None
    if op in ("*", "+", "-"):
        m = 1.0 if op == "*" else 0.0
        for x in a[1:]:
            v = _bound(x, z, live)
            if v is None:
                return None
            m = m * v if op == "*" else m + v
        return m
    if op == "/":
        d = a[2] if len(a) > 2 else None
        if not isinstance(d, (int, float)) or isinstance(d, bool) or d == 0:
            return None
        v = _bound(a[1], z, live)
        return None if v is None else v / abs(float(d))
    if op in ("max", "coalesce"):
        return mx(a[1:])
    if op == "min":
        vs = [v for v in (_bound(x, z, live) for x in a[1:]) if v is not None]
        return min(vs) if vs else None
    if op == "case":
        return mx(a[2::2] + a[-1:])
    if op == "match":
        return mx(a[3::2] + a[-1:])
    if op == "step":
        outs = [a[2]] + a[4::2]
        if a[1] == ["zoom"]:
            at = 0
            for st in a[3::2]:
                if isinstance(st, (int, float)) and st <= z:
                    at += 1
                else:
                    break
            return _bound(outs[at], z, live)
        return mx(outs)
    if op == "interpolate":
        pairs = a[3:]
        if len(pairs) % 2 or not all(isinstance(x, (int, float)) for x in pairs[0::2]):
            return None
        stops = list(zip([float(x) for x in pairs[0::2]], pairs[1::2], strict=True))
        if a[2] != ["zoom"]:
            return mx([v for _, v in stops])
        i = 0
        while i < len(stops) and stops[i][0] <= z:
            i += 1
        if i == 0:
            return _bound(stops[0][1], z, live)
        if i == len(stops):
            return _bound(stops[i - 1][1], z, live)
        (z0, e0), (z1, e1) = stops[i - 1], stops[i]
        v0, v1 = _bound(e0, z, live), _bound(e1, z, live)
        if v0 is None or v1 is None:
            return None
        kind = a[1][0] if isinstance(a[1], list) and a[1] else None
        if kind == "linear":
            t = (z - z0) / (z1 - z0)
        elif kind == "exponential":
            base = a[1][1]
            t = (z - z0) / (z1 - z0) if base == 1 else (base ** (z - z0) - 1.0) / (base ** (z1 - z0) - 1.0)
        else:
            return max(v0, v1)
        return v0 + min(max(t, 0.0), 1.0) * (v1 - v0)
    return None


def _reach(layer, z, live):
    """roadstyle_tiles::buffer::reach: how far a layer's stroke reaches from its line or point at the map zoom z, in px."""
    lo, hi = layer.get("minzoom"), layer.get("maxzoom")
    if (lo is not None and z < lo) or (hi is not None and z >= hi) or "slots" in (layer.get("source"), layer.get("source-layer")):
        return 0.0
    paint = layer.get("paint") or {}

    def ub(k, none):
        return none if paint.get(k) is None else _bound(paint[k], z, live)

    if layer.get("type") == "line":
        w, gap, off, blur = ub("line-width", 1.0), ub("line-gap-width", 0.0), ub("line-offset", 0.0), ub("line-blur", 0.0)
        if None in (w, gap, off, blur):
            return None
        return (gap / 2.0 + w if gap > 0.0 else w / 2.0) + off + blur / 2.0
    if layer.get("type") == "circle":
        r, sw, blur = ub("circle-radius", 5.0), ub("circle-stroke-width", 0.0), ub("circle-blur", 0.0)
        return None if None in (r, sw, blur) else r + sw + blur
    return 0.0


def buffers_px(layers, max_zoom, live=LIVE_WIDTH_MAX, fallback=80.0):
    """roadstyle_tiles::buffer::buffers_px: the buffer of each tile zoom 0 to max_zoom in px of the tile, from the widest stroke at the
    map zooms that draw that tile (a tile of zoom z: z to z + 1, scaled up by 2^(Z - z); the last zoom: to 24), plus 1 px; ``fallback``
    where a stroke's width cannot be bounded."""
    out = []
    for z in range(max_zoom + 1):
        top = z + 1.0 if z < max_zoom else 24.0
        steps = math.ceil((top - z) * 16.0)
        need, unknown = 0.0, False
        for k in range(steps + 1):
            zz = z + (top - z) * k / steps
            for layer in layers or []:
                px = _reach(layer, zz, live)
                if px is None:
                    unknown = True
                    break
                need = max(need, px / 2.0 ** (zz - z))
            if unknown:
                break
        out.append(float(fallback) if unknown else need + 1.0)
    return out


def _drop_tiny(rows, tb, extent=4096):
    """Rule B for the "simple" pieces of one tile below the last zoom (roadstyle_tiles::drop_tiny): ``rows`` is ``[(row, clipped geometry)]``.
    A road (``__rs_edge``) whose pieces are together under 1 px (8 units of 4096; the casing and the fill each count, the longer decides)
    is left out unless a point of it is out of the tile; a casing end piece (``__rs_seam``) under 1 px is left out. The lengths are
    those of the tile's rounded units (what the encoder writes), as the Rust engine's."""
    px = extent / 512

    def units(g):
        lines = []
        for part in (g.geoms if hasattr(g, "geoms") else [g]):
            pts = [(round(extent * (x - tb[0]) / (tb[2] - tb[0])), round(extent * (y - tb[1]) / (tb[3] - tb[1]))) for x, y in part.coords]
            pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
            if len(pts) >= 2:
                lines.append(pts)
        return lines

    shapes = [units(g) for _, g in rows]
    length = [sum(math.dist(a, b) for l in ls for a, b in zip(l, l[1:])) for ls in shapes]
    roads = {}          # edge -> ({kind: length}, a point is out of the tile)
    for (row, _), ls, n in zip(rows, shapes, length):
        p = row["properties"]
        kinds, out = roads.setdefault(p.get("__rs_edge"), ({}, [False]))
        kinds[p.get("__rs_k")] = kinds.get(p.get("__rs_k"), 0.0) + n
        out[0] = out[0] or any(not 0 <= v <= extent for l in ls for pt in l for v in pt)

    def tiny_road(p):
        kinds, out = roads[p.get("__rs_edge")]
        return p.get("__rs_edge") is not None and not out[0] and max(kinds.values()) < px
    return [row for (row, _), n in zip(rows, length)
            if not tiny_road(row["properties"]) and not (row["properties"].get("__rs_seam") and n < px)]


def build_pmtiles(fc: dict, *, keep: set, layers: list | None = None,
                  minzoom: int = 6, maxzoom: int = 15, extent: int = 4096,
                  buffer_px: int = 80, layer: str = "roads",
                  extra_layers: list | None = None, line_layers: list | None = None) -> bytes:
    """Encode GeoJSON FeatureCollections (lon/lat) into a PMTiles archive (bytes).

    Feature ``id`` = index in ``fc["features"]`` — the exact id space the inline version gives each feature (its own ``id``), so feature-state, ``rsFilter``/``rsColor`` id filters and the sidecar table
    all line up. A feature that every layer of ``layers`` (the style's) drawing its tile layer hides at every zoom of a tile is left out of
    it (zoom_rules: the class minzoom, casing.drop_below_px; the last zoom's tiles keep every feature), geometry is
    simplified to ~half a tile pixel and clipped to the tile + buffer (skipped when the feature
    already fits inside — the common case at street zooms).

    ``extra_layers``: ``[{"name", "fc", "minzoom", "keep" (None = all props)}]`` — additional
    tile layers in the same archive (e.g. the annotation slots). Their features are written
    WHOLE into every tile they touch, never clipped: MapLibre renders a symbol only in the tile
    that owns its anchor, so a duplicated small feature yields exactly one label.

    ``line_layers``: ``[{"name", "fc", "keep", "minzoom" (optional)}]`` — further tile layers made exactly like the main one
    (simplified per zoom, clipped to the tile): the casing pieces of a divided casing. ``minzoom``: the layer's first zoom.
    """
    import mapbox_vector_tile
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    from shapely import clip_by_rect, wkb

    feats, world = _prep(fc, keep, zoom_rules(layers, layer))
    lines = [(layer, feats, minzoom)]
    for ln in (line_layers or []):
        lf, lw = _prep(ln["fc"], ln.get("keep"), zoom_rules(layers, ln["name"]))
        world = [min(world[0], lw[0]), min(world[1], lw[1]), max(world[2], lw[2]), max(world[3], lw[3])]
        lines.append((ln["name"], lf, int(ln.get("minzoom", minzoom))))
    extras = []          # (name, from_zoom, prepped features)
    for ex in (extra_layers or []):
        efeats, ew = _prep(ex["fc"], ex.get("keep"), zoom_rules(layers, ex["name"]))
        world = [min(world[0], ew[0]), min(world[1], ew[1]),
                 max(world[2], ew[2]), max(world[3], ew[3])]
        extras.append((ex["name"], int(ex.get("minzoom", minzoom)), efeats))

    buf = io.BytesIO()
    writer = Writer(buf)
    buffers = buffers_px(layers, maxzoom, LIVE_WIDTH_MAX, buffer_px)    # each zoom's buffer, as the Rust engine's TileOptions::tiles
    for z in range(minzoom, maxzoom + 1):
        s = 2 * _R / (1 << z)
        tol = s / extent / 2                       # ~half a tile pixel
        pad = s * buffers[z] / 512                 # px of a 512 px tile (it was 80 units, 10 px: a wide road lost its casing)
        cells = {}                                 # (x, y) -> {layer_name: [feature rows]}
        for lname, lfeats, from_zoom in lines:
            if z < from_zoom:
                continue
            for i, geom, b, fmz, props in lfeats:
                if z < maxzoom and z + 1 <= fmz[0] or z >= fmz[1]:
                    continue        # no layer draws it at a zoom of this tile
                g = geom.simplify(tol) if z < maxzoom else geom
                if g.is_empty or g.length < tol:
                    continue
                gb = g.bounds
                # the tiles whose buffer the box touches: a road out of a tile whose stroke reaches into it is in the tile
                x0, x1, y0, y1 = _tile_range((b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad), z)
                for tx in range(x0, x1 + 1):
                    for ty in range(y0, y1 + 1):
                        tb = _tile_bounds(z, tx, ty)
                        if (gb[0] >= tb[0] - pad and gb[1] >= tb[1] - pad
                                and gb[2] <= tb[2] + pad and gb[3] <= tb[3] + pad):
                            c = g                       # fully inside the padded tile: no clip
                        else:
                            c = clip_by_rect(g, tb[0] - pad, tb[1] - pad, tb[2] + pad, tb[3] + pad)
                            if c.is_empty:
                                continue
                        # the pieces ("simple") have no id: the vector source's promoteId (__rs_edge) is their feature id
                        cells.setdefault((tx, ty), {}).setdefault(lname, []).append(
                            {"geometry": c.wkb, "properties": props, **({} if lname == "simple" else {"id": i})})
        for name, from_zoom, efeats in extras:
            if z < from_zoom:
                continue
            for i, geom, b, fmz, props in efeats:
                if z < maxzoom and z + 1 <= fmz[0] or z >= fmz[1]:
                    continue
                x0, x1, y0, y1 = _tile_range(b, z)
                for tx in range(x0, x1 + 1):
                    for ty in range(y0, y1 + 1):
                        cells.setdefault((tx, ty), {}).setdefault(name, []).append(
                            {"geometry": geom.wkb, "properties": props, "id": i})
        for (tx, ty), by_layer in sorted(cells.items()):
            tb = _tile_bounds(z, tx, ty)
            if z < maxzoom and "simple" in by_layer:
                by_layer["simple"] = _drop_tiny([(r, wkb.loads(r["geometry"])) for r in by_layer["simple"]], tb, extent)
                if not by_layer["simple"]:
                    del by_layer["simple"]
                    if not by_layer:
                        continue
            data = mapbox_vector_tile.encode(
                [{"name": n, "features": rows} for n, rows in by_layer.items()],
                default_options={"extents": extent,
                                 "quantize_bounds": (tb[0], tb[1], tb[2], tb[3])})
            writer.write_tile(zxy_to_tileid(z, tx, ty), gzip.compress(data, 6, mtime=0))

    def _e7(merc_x, merc_y):
        lon = merc_x / _R * 180.0
        lat = math.degrees(2 * math.atan(math.exp(merc_y * math.pi / _R)) - math.pi / 2)
        return int(lon * 1e7), int(lat * 1e7)

    lo = _e7(world[0], world[1])
    hi = _e7(world[2], world[3])
    writer.finalize(
        {"tile_type": TileType.MVT,
         "tile_compression": Compression.GZIP,
         "min_zoom": minzoom, "max_zoom": maxzoom,
         "min_lon_e7": lo[0], "min_lat_e7": lo[1],
         "max_lon_e7": hi[0], "max_lat_e7": hi[1],
         "center_zoom": (minzoom + maxzoom) // 2,
         "center_lon_e7": (lo[0] + hi[0]) // 2, "center_lat_e7": (lo[1] + hi[1]) // 2},
        {"vector_layers": [{"id": n, "fields": {}}
                           for n in [n for n, *_ in lines] + [e[0] for e in extras]]},
    )
    return buf.getvalue()


def page_reads() -> dict:
    """The page's declaration of the feature properties that its modules read (static/dashboard/reads.json: ``pieces`` and ``table``)."""
    return json.loads(_assets.text("static/dashboard/reads.json"))


def table_keeps(k: str) -> bool:
    """A property of a road that the road table keeps (R1, props::table_keeps in Rust): every public field, the stage values that the
    page's modules read on a row (reads.json ``table``), and the fills (``__rs_fill*``: the filter's swatches of a view's palette)."""
    return not k.startswith("__rs_") or k.startswith("__rs_fill") or k in _TABLE_READS


_TABLE_READS = set(page_reads()["table"])


def sidecar(fc: dict) -> dict:
    """The road table of the page (gzipped), one row for each road: its properties for rsQuery / popups (``table_keeps``), its midpoint
    (by length: rsSelect's popup anchor and Street View's spot), its bbox for rsFocus and its line (Street View's heading comes from it).
    Stage 1 of the Rust engine makes the same table (roadstyle::write_road_table)."""
    from shapely.geometry import LineString

    props, mids, bboxes, lines = [], [], [], []
    for ft in fc.get("features", []):
        props.append({k: v for k, v in (ft.get("properties") or {}).items() if table_keeps(k)})
        g = ft.get("geometry") or {}
        cs = g.get("coordinates") or []
        if g.get("type") == "MultiLineString" and cs:
            cs = cs[0]
        # the middle of the length, not the middle vertex: a two-point edge's middle vertex is its end
        mids.append(list(LineString(cs).interpolate(0.5, normalized=True).coords[0])
                    if len(cs) >= 2 else (list(cs[0]) if cs else None))
        xs = [c[0] for c in (cs or [])]
        ys = [c[1] for c in (cs or [])]
        bboxes.append([min(xs), min(ys), max(xs), max(ys)] if xs else None)
        lines.append(cs or None)
    return {"props": props, "mids": mids, "bboxes": bboxes, "lines": lines}


def _b64gz(obj) -> str:
    import base64
    raw = obj if isinstance(obj, (bytes, bytearray)) else json.dumps(
        obj, separators=(",", ":")).encode()
    return base64.b64encode(gzip.compress(bytes(raw), 6, mtime=0)).decode()

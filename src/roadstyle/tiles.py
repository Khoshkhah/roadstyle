"""Vector tiles for the web backend — pack the styled road features into a PMTiles archive.

The archive is embedded base64 into the saved HTML and served to MapLibre from memory via the
vendored ``pmtiles.js`` (``addProtocol``), so the single-file / open-from-disk property is kept.
The win over inline GeoJSON is client-side scale: MapLibre parses only the tiles in view, and
low zooms carry simplified geometry (sub-pixel pieces drop out) instead of every vertex of
every service road. Class thinning is opt-in via the render ``minzoom`` parameter — the
default tiles carry every class at every zoom, matching the inline look.

Tiles carry ONLY the properties the style expressions read (``__rs_*`` paints, the class/filter
columns, ``twoway``, ``lvl``) plus the feature ``id`` (= the feature's index, the same id space
as ``generateId`` today). Everything else — full attributes for popups/`rsQuery`, per-edge
midpoints and bboxes for `rsSelect`/`rsFocus` — travels in a small gzipped sidecar table the
page inflates separately (see render_web).

Needs the ``tiles`` extra: ``pip install "roadstyle[tiles]"`` (mapbox-vector-tile + pmtiles).
"""
from __future__ import annotations

import gzip
import io
import json
import math

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
    """The slim per-feature property set baked into the tiles (style reads only these)."""
    return {k: v for k, v in props.items() if (k.startswith("__rs_") or k in keep) and v is not None}


def _prep(fc: dict, class_col: str | None, keep: set | None, minzoom_table: dict | None):
    """Project features to mercator; return ([(idx, geom, bounds, class_minzoom, props)], world_bbox)."""
    from shapely.geometry import shape
    from shapely.ops import transform as shp_transform

    mz = {str(k): int(v) for k, v in (minzoom_table or {}).items()}
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
            {k: v for k, v in p.items() if v is not None}
        feats.append((i, geom, b, mz.get(str(p.get(class_col, ""))) if class_col else 0, props))
    return feats, world


def build_pmtiles(fc: dict, *, class_col: str, keep: set, minzoom_table: dict | None = None,
                  minzoom: int = 6, maxzoom: int = 15, extent: int = 4096,
                  buffer_px: int = 80, layer: str = "roads",
                  extra_layers: list | None = None) -> bytes:
    """Encode GeoJSON FeatureCollections (lon/lat) into a PMTiles archive (bytes).

    Feature ``id`` = index in ``fc["features"]`` — the exact id space ``generateId`` gives the
    inline version, so feature-state, ``rsFilter``/``rsColor`` id filters and the sidecar table
    all line up. Per zoom, features whose class sits below its ``minzoom_table`` entry are left
    out (they pop in when zooming — same rule the visual ``minzoom`` filter uses), geometry is
    simplified to ~half a tile pixel and clipped to the tile + buffer (skipped when the feature
    already fits inside — the common case at street zooms).

    ``extra_layers``: ``[{"name", "fc", "minzoom", "keep" (None = all props)}]`` — additional
    tile layers in the same archive (e.g. the annotation slots). Their features are written
    WHOLE into every tile they touch, never clipped: MapLibre renders a symbol only in the tile
    that owns its anchor, so a duplicated small feature yields exactly one label.
    """
    import mapbox_vector_tile
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    from shapely import clip_by_rect

    feats, world = _prep(fc, class_col, keep, minzoom_table)
    extras = []          # (name, from_zoom, prepped features)
    for ex in (extra_layers or []):
        efeats, ew = _prep(ex["fc"], None, ex.get("keep"), None)
        world = [min(world[0], ew[0]), min(world[1], ew[1]),
                 max(world[2], ew[2]), max(world[3], ew[3])]
        extras.append((ex["name"], int(ex.get("minzoom", minzoom)), efeats))

    buf = io.BytesIO()
    writer = Writer(buf)
    for z in range(minzoom, maxzoom + 1):
        s = 2 * _R / (1 << z)
        tol = s / extent / 2                       # ~half a tile pixel
        pad = s * buffer_px / extent
        cells = {}                                 # (x, y) -> {layer_name: [feature rows]}
        for i, geom, b, fmz, props in feats:
            if z < (fmz or 0):
                continue
            g = geom.simplify(tol) if z < maxzoom else geom
            if g.is_empty or g.length < tol:
                continue
            gb = g.bounds
            x0, x1, y0, y1 = _tile_range(b, z)
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
                    cells.setdefault((tx, ty), {}).setdefault(layer, []).append(
                        {"geometry": c.wkb, "properties": props, "id": i})
        for name, from_zoom, efeats in extras:
            if z < from_zoom:
                continue
            for i, geom, b, _fmz, props in efeats:
                x0, x1, y0, y1 = _tile_range(b, z)
                for tx in range(x0, x1 + 1):
                    for ty in range(y0, y1 + 1):
                        cells.setdefault((tx, ty), {}).setdefault(name, []).append(
                            {"geometry": geom.wkb, "properties": props, "id": i})
        for (tx, ty), by_layer in sorted(cells.items()):
            tb = _tile_bounds(z, tx, ty)
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
                           for n in [layer] + [e[0] for e in extras]]},
    )
    return buf.getvalue()


def sidecar(fc: dict) -> dict:
    """The per-edge lookup the page keeps inline (gzipped): full properties for rsQuery /
    popups, a midpoint vertex for the floating popup anchor, and a bbox for rsFocus."""
    props, mids, bboxes = [], [], []
    for ft in fc.get("features", []):
        props.append(ft.get("properties") or {})
        g = ft.get("geometry") or {}
        cs = g.get("coordinates") or []
        if g.get("type") == "MultiLineString" and cs:
            cs = cs[0]
        mids.append(list(cs[len(cs) // 2]) if cs else None)
        xs = [c[0] for c in (cs or [])]
        ys = [c[1] for c in (cs or [])]
        bboxes.append([min(xs), min(ys), max(xs), max(ys)] if xs else None)
    return {"props": props, "mids": mids, "bboxes": bboxes}


def _b64gz(obj) -> str:
    import base64
    raw = obj if isinstance(obj, (bytes, bytearray)) else json.dumps(
        obj, separators=(",", ":")).encode()
    return base64.b64encode(gzip.compress(bytes(raw), 6, mtime=0)).decode()

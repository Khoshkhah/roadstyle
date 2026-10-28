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

import html as _html

from . import _assets, _settings
from ._na import missing


def _asset(fname):
    """Read a vendored front-end asset (the MapLibre js/css) to inline into the saved HTML, so the
    page needs no CDN — it opens offline, straight from disk, with no web server."""
    return _assets.text("vendor/" + fname)

# --- openstreetmap-carto road model — loaded from data/defaults.json "roads" (+ any user
# roadstyle.json override), like every other styling table. Edit the JSON, not this file.
_CW = {}        # class_width_px by (class, zoom, casing): emptied whenever the road tables are built again


def _load_road_model() -> None:
    """(Re)build the module road tables from :func:`_settings.roads`.

    Runs at import and again from :func:`roadstyle.use_settings` after a programmatic override —
    every expression builder below reads these module globals at call time, so a rebuild is all a
    new setting set needs."""
    global WIDTH, HI_RATE, CASING_RATIO, ROAD_GROUP, _LINKS, _CLASSES, _ZSTOPS, ROAD_Z, THEME, _FB, _LINK_W, _SPLIT, _MINOR, _TUN_TO
    _CW.clear()
    THEME = _settings.theme()                  # every style value (docs/design/style_config.md)
    _FB = dict(THEME["roads"]["fallback"])     # a class or a value with no entry: its fill, casing, group and order
    _LINK_W = float(THEME["roads"]["links"]["width"])     # a link's width: this part of its main class's
    _SPLIT = dict(THEME["roads"]["split"])     # two-way roads: offset_frac, width_frac, offset_zoom, ramp_zooms
    _MINOR = [c for c, e in THEME["roads"]["classes"].items() if e.get("minor")]     # arrows and names later, smaller arrows
    _TUN_TO = dict(THEME["tunnels"]["to"])
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


def _base(c):
    return (c[:-5], True) if c.endswith("_link") else (c, False)


def class_order(c):
    """The draw order of a class (theme roads.classes.<class>.order): the table's value, else a link just under its main class."""
    b, lk = _base(c)
    return ROAD_Z[c] if c in ROAD_Z else ROAD_Z.get(b, _FB["order"]) + (_FB["link_order"] if lk else 0)


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
    The page's width expression, read at one zoom (linear between its stops, the end values outside); one line per road, no two-way narrowing.
    Kept per (class, zoom, casing) until the road tables change (2026-10-09: the name slots asked once per crossing, 39,000 times on Monaco,
    and building the expression each time took 25 of the editor's 30 s per page)."""
    key = (cls, zoom, casing)
    if key not in _CW:
        _CW[key] = _class_width_px(cls, zoom, casing)
    return _CW[key]


def _class_width_px(cls, zoom, casing):
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


def _width_expr(col, casing=False, split_zoom=None, split_frac=None, scale=1.0):
    """interpolate(zoom) of match(class -> width). Two-way lanes shrink to ``split_frac`` of the
    full width once the directions have fanned apart (ramped from full at split_zoom to split_frac
    at split_zoom+2), so the two lanes together read as one road of the right width.

    ``scale`` multiplies every output width (e.g. 1.25 for a heavier bridge casing). It scales the
    per-stop *values*, not the whole expression, because MapLibre forbids a ``zoom`` interpolate
    nested inside ``["*", ...]`` — the zoom input must stay top-level."""
    split_zoom = _SPLIT["offset_zoom"] if split_zoom is None else split_zoom
    split_frac = _SPLIT["width_frac"] if split_frac is None else split_frac
    e = ["interpolate", ["linear"], ["zoom"]]
    for z in _ZSTOPS:
        m = ["match", ["get", col]]
        for c in _CLASSES:
            b, lk = _base(c)
            g = ROAD_GROUP.get(b, _FB["group"])
            w = _gwidth(WIDTH[g], HI_RATE[g], z) * (CASING_RATIO[g] if casing else 1) * scale
            if lk:
                w *= _LINK_W
            m += [c, round(w, 2)]
        g = _FB["group"]
        dw = _gwidth(WIDTH[g], HI_RATE[g], z) * (CASING_RATIO[g] if casing else 1) * scale
        m.append(round(dw, 2))
        f = 1.0 if z <= split_zoom else (split_frac if z >= split_zoom + 2 else 1.0 - (1 - split_frac) * (z - split_zoom) / 2.0)
        if f < 1.0:
            m = ["*", m, ["case", ["to-boolean", ["get", "__rs_twoway"]], round(f, 3), 1]]
        e += [z, m]
    return e


def _truthy(v):
    return not missing(v) and v not in ("", "no", "false", "0", 0, False)


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


"""The choice of the engine, and the calls into roadstyle's Rust engine (docs/design/rust_library.md, phase P5).

``engine="python"`` (the default) runs the Python code. ``engine="rust"`` runs the Rust engine, the extension module
``roadstyle._rust`` (built from ``rust/roadstyle-py``). The environment variable ``ROADSTYLE_ENGINE`` sets the default. A part that
the Rust engine does not have gives an error with ``engine="rust"``; it never goes back to Python without a message. Without level
columns the Rust engine computes the levels, as ``render`` does (``compute_levels``, method "solve").
"""
from __future__ import annotations

import io
import json
import os

ENGINES = ("python", "rust")

# what the Rust engine needs in the roads
RUST_COLUMNS = ("highway",)


def engine(name: str | None = None) -> str:
    """The engine to use: ``name``, else ``ROADSTYLE_ENGINE``, else "python"."""
    e = (name or os.environ.get("ROADSTYLE_ENGINE") or "python").lower()
    if e not in ENGINES:
        raise ValueError(f"engine={e!r}: use one of {', '.join(ENGINES)}")
    return e


def rust():
    """The Rust extension module, or an ImportError that says how to build it."""
    try:
        from . import _rust
    except ImportError as e:
        raise ImportError("engine='rust' needs the Rust extension roadstyle._rust: build it with "
                          "`python rust/roadstyle-py/build.py` (or install a roadstyle wheel that has it)") from e
    return _rust


def available() -> bool:
    try:
        rust()
        return True
    except ImportError:
        return False


def _geoparquet(edges) -> bytes:
    """The roads as GeoParquet bytes (the geometry as WKB), as the Rust reader reads them."""
    buf = io.BytesIO()
    edges.to_parquet(buf, index=False)
    return buf.getvalue()


def look(*, palette=None, profile=None, settings=None, args=None, features=None) -> dict:
    """The resolved look (look.json) of render_edges' palette, profile and settings, made by the Rust engine."""
    o = {"palette": palette, "profile": profile, "settings": settings, "args": args or {}}
    if features is not None:
        o["features"] = features
    return json.loads(rust().make_look(json.dumps(o)))


def export_inline(edges, **kwargs) -> dict:
    """``roadstyle.export_inline`` made by the Rust engine: the same style, from the same keywords."""
    missing = [c for c in RUST_COLUMNS if (kwargs.get(f"{c}_col") or c) not in edges.columns]
    if missing:
        raise ValueError(f"engine='rust': the roads have no column {', '.join(missing)}")
    kwargs = dict(kwargs)
    kwargs.pop("engine", None)
    kwargs.setdefault("view_3d", True)      # as export_inline
    lk = _look_of(kwargs)
    text = rust().make_style(_geoparquet(edges), json.dumps(lk), None, None, kwargs.get("name"))
    return json.loads(text)


def _look_of(kwargs) -> dict:
    """The resolved look of render's keywords, with what the engine reads as JSON: the boundary as GeoJSON (_boundary_fc) and each overlay
    as its fields, its style of the settings filled in (_styled), its data as a FeatureCollection (``fc``)."""
    kwargs = dict(kwargs)
    palette, profile, settings = kwargs.pop("palette", None), kwargs.pop("profile", None), kwargs.pop("settings", None)
    features, overlays, items = kwargs.pop("features", None), kwargs.pop("overlays", None), kwargs.pop("items", None)
    if kwargs.get("boundary") is not None:   # a shapely geometry or a GeoDataFrame: GeoJSON, as render does (_boundary_fc)
        from .render_web import _boundary_fc
        kwargs["boundary"] = json.loads(json.dumps(_boundary_fc(kwargs["boundary"])))
    lk = look(palette=palette, profile=profile, settings=settings, args=kwargs, features=features)
    if overlays:
        lk["args"]["overlays"] = [_overlay_json(o, (lk["config"].get("overlays") or {}).get("styles") or {}) for o in overlays]
    if items is not None:          # render's items=: the road's own line items, as GeoJSON
        from .overlays import to_fc
        lk["args"]["items"] = json.loads(json.dumps(to_fc(items)))
    return lk


def _overlay_json(ov, styles) -> dict:
    """An rs.Overlay (or its data) as the engine reads it: its fields (render_web._styled: a style's fields where the overlay gives none), and
    its data as GeoJSON in ``fc`` (overlays.to_fc)."""
    import dataclasses

    from .overlays import Overlay, to_fc

    ov = ov if isinstance(ov, Overlay) else Overlay(data=ov)
    if ov.style:
        if ov.style not in styles:
            raise ValueError(f"overlay style {ov.style!r} is not in the settings (config.overlays.styles); known: {sorted(styles)}")
        fields = {f.name for f in dataclasses.fields(Overlay)} - {"data", "style", "edge_col", "order_col", "select"}
        bad = set(styles[ov.style]) - fields
        if bad:
            raise ValueError(f"overlay style {ov.style!r}: unknown field(s) {sorted(bad)}; the fields are {sorted(fields)}")
        ov = dataclasses.replace(ov, **{k: v for k, v in styles[ov.style].items() if getattr(ov, k) is None})
    out = {f.name: getattr(ov, f.name) for f in dataclasses.fields(Overlay) if f.name != "data"}
    out["fc"] = json.loads(json.dumps(to_fc(ov.data)))
    return out


# compute_levels' keywords that the Rust engine has only at their defaults
_LEVEL_DEFAULTS = {"band_col": None, "order": "priority", "band_dist": 10.0, "head_m": 5.0, "max_level": 20, "margin": 1.0,
                   "min_positions": True, "near_rules": False}


def compute_levels(edges, *, layer_col="layer", bridge_col="bridge", tunnel_col="tunnel", method="solve", highway_col="highway",
                   junction_col="junction", time_limit=60.0, **kw):
    """``roadstyle.compute_levels`` by the Rust engine: the same four columns (casing_start, casing_level, casing_end, fill_level).
    The attrs have ``levels_params`` and ``levels_info`` (with the counts; the lists of given-up pairs are Python's only)."""
    other = {k: v for k, v in kw.items() if v != _LEVEL_DEFAULTS.get(k, object())}
    if other:
        raise ValueError(f"engine='rust': compute_levels has {', '.join(sorted(other))} only at the defaults; use engine='python'")
    rows, info = rust().compute_levels(_geoparquet(edges), method, [highway_col, layer_col, bridge_col, tunnel_col, junction_col])
    g = edges.copy()
    for i, c in enumerate(("casing_start", "casing_level", "casing_end", "fill_level")):
        g[c] = [r[i] for r in rows]
    from .levels_store import levels_params
    d = _LEVEL_DEFAULTS
    g.attrs["levels_params"] = levels_params(method, d["head_m"], d["band_dist"], d["margin"], d["max_level"], d["band_col"], d["order"],
                                             d["min_positions"] and method == "solve")
    g.attrs["levels_info"] = {"engine": "rust", **dict(info)}
    return g


def export_style(edges, out_dir, *, base_url: str, format: str = "xyz", **kwargs):
    """``roadstyle.export_style`` by the Rust engine: the style and the tiles from ``Tiler``; the files around them as Python writes them.
    ``format``: "xyz" (a tile folder) or "pmtiles" (one archive, roads.pmtiles)."""
    import gzip  # noqa: F401  (the same imports as export.py)
    from importlib.resources import files
    from pathlib import Path

    from . import _settings
    from .export import _camera, _plugin_css
    from .tiles import _merc, _tile_range

    if format not in ("xyz", "pmtiles"):
        raise ValueError(f"format must be 'xyz' or 'pmtiles', got {format!r}")
    kwargs = dict(kwargs)
    name = kwargs.get("name") or "roads"
    kwargs.setdefault("view_3d", True)
    kwargs["tiles"] = True                                 # render's tiled look: the roads source draws (no lean mode)
    lk = _look_of(kwargs)
    t = rust().Tiler(_geoparquet(edges), json.dumps(lk), None, name, "", [str(c) for c in edges.columns])   # every column: a click shows the data
    style, base = json.loads(t.style), base_url.rstrip("/")
    bounds = tuple(float(v) for v in edges.total_bounds)
    roads = style["sources"]["roads"]
    at = {"tiles": [f"{base}/tiles/{{z}}/{{x}}/{{y}}.pbf"]} if format == "xyz" else {"url": f"pmtiles://{base}/roads.pmtiles"}
    roads = style["sources"]["roads"] = {**{k: roads[k] for k in ("type", "minzoom", "maxzoom")}, **at, "bounds": list(bounds)}
    meta = style.pop("metadata", {})
    style = {k: style[k] for k in ("version", "sources", "layers", "glyphs") if k in style}     # Python's key order: the same bytes
    style["sprite"], style["name"] = f"{base}/sprite", name
    style["center"], style["zoom"] = _camera(bounds)
    style["metadata"] = meta
    for lyr in style["layers"]:                                         # Python tags a layer's group after its source-layer
        if "metadata" in lyr:
            lyr["metadata"] = lyr.pop("metadata")
    style.setdefault("metadata", {}).pop("roadstyle:images", None)     # export_style draws the arrow from the sprite
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    lo, hi = _merc(*bounds[:2]), _merc(*bounds[2:])
    if format == "pmtiles":
        names = sorted({lyr["source-layer"] for lyr in style["layers"] if "source-layer" in lyr})
        (d / "roads.pmtiles").write_bytes(_pmtiles(t, int(roads["minzoom"]), int(roads["maxzoom"]), bounds, names))
    for z in range(int(roads["minzoom"]), int(roads["maxzoom"]) + 1) if format == "xyz" else ():   # every tile in the bounds; an empty one: an empty file
        x0, x1, y0, y1 = _tile_range((lo[0], lo[1], hi[0], hi[1]), z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                p = d / "tiles" / str(z) / str(x) / f"{y}.pbf"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(t.tile(z, x, y))
    (d / "popup.css").write_text(_plugin_css())
    (d / "popup.js").write_text(files("roadstyle").joinpath("static/popup.js").read_text())
    style["metadata"]["roadstyle:interaction"] = {**style["metadata"].get("roadstyle:interaction", {}), "css": f"{base}/popup.css",
                                                  "js": f"{base}/popup.js"}
    png = files("roadstyle").joinpath("data/sprite.png").read_bytes()
    icon = _settings.theme_value("arrows.icon")
    index = json.dumps({"oneway": {"x": 0, "y": 0, "width": icon["width"], "height": icon["height"], "pixelRatio": icon["pixel_ratio"], "sdf": True}})
    for n in ("sprite", "sprite@2x"):
        (d / f"{n}.png").write_bytes(png)
        (d / f"{n}.json").write_text(index)
    path = d / "style.json"
    path.write_text(json.dumps(style, separators=(",", ":")))
    return path


def render_page(gdf, *, palette=None, profile=None, settings=None, highway_col="highway", include=None, exclude=None, match_links=True,
                levels_db=None, **kwargs):
    """``render_edges(backend="web", engine="rust")``: the roads' style from the Rust engine (state "live": the state in the expressions and
    the interaction contract in the metadata), the base map and the page as Python writes them (render_web._page_basemaps, _page_html),
    with the settings of the call in force. ``tiles=True``: the roads, their pieces and their names in an embedded PMTiles archive of the
    Rust engine's tiles (_tiled_page). ``simple=False`` (the full look) is Python's only."""
    import inspect
    import os

    from . import _settings as _s
    from . import render_web as rw
    from . import use_settings as _use
    from .edges import as_edges
    from .filters import filter_edges

    for k, why in (("style", "a Styler object is Python's"), ("styler", "a Styler object is Python's")):
        if kwargs.get(k):
            raise ValueError(f"engine='rust': {k}= ({why}); use engine='python'")
    if kwargs.get("simple") is False:
        raise ValueError("engine='rust': simple=False (the full look) is Python's; use engine='python'")
    g = as_edges(gdf, class_col=highway_col).gdf
    if include is not None or exclude is not None:
        g = filter_edges(g, include=include, exclude=exclude, highway_col=highway_col, match_links=match_links)
    if levels_db is not None:
        if any(kwargs.get(k) for k in ("casing_level_col", "fill_level_col", "casing_start_col", "casing_end_col")):
            raise ValueError("levels_db and level columns of your own (casing_level_col, fill_level_col, ...) are two drawing orders: use one")
        from .levels_store import stored_levels
        g, level_kw = stored_levels(levels_db, g, kwargs.get("edge_id_col", "edge_id"))
        kwargs = {**kwargs, **level_kw}
    tiled = bool(kwargs.get("tiles"))
    lk = _look_of({**kwargs, "palette": palette, "profile": profile, "settings": settings, "highway_col": highway_col, "state": "live"})
    pq = _geoparquet(g)
    style = json.loads(rust().make_style(pq, json.dumps(lk), None, None, kwargs.get("name")))
    dashes = sorted({f["properties"].get("__rs_dash") for f in style["sources"]["simple"]["data"]["features"]} - {None, ""})
    archive = _tiled_page(pq, lk, style, highway_col, kwargs) if tiled else None
    meta, ctl = style.pop("metadata"), None
    ctl, inter = meta["roadstyle:controls"], meta["roadstyle:interaction"]
    for lyr in style["layers"]:
        lyr.pop("metadata", None)          # the page gives the dashboard its options; its style has no metadata
    a = {k: p.default for k, p in inspect.signature(rw.render).parameters.items() if p.default is not inspect.Parameter.empty}
    a.update(kwargs)
    mode = "panel" if a["road_popup"] == "panel" else (a["popup_mode"] or "popup")
    if a["side_panel_html"] is not None and mode == "panel":
        raise ValueError("side_panel_html and popup_mode='panel' are two panels on the right: use one")
    if a["street_view"] not in (True, False, "window"):
        raise ValueError(f'street_view must be True, False or "window", got {a["street_view"]!r}')
    key = a["street_view_key"] or os.environ.get("GOOGLE_MAPS_KEY") or None
    if a["google_3d"] and not key:
        raise ValueError("google_3d=True needs a Google Maps JavaScript API key: pass street_view_key=... or set GOOGLE_MAPS_KEY")
    # the page's own parts with the settings of the call in force (the base map, its canvas colour), as render_edges applies them
    pick = {k: v for k, v in (("profile", profile), ("palette", palette)) if v is not None and v != _s.theme()["active"][k]
            and (k == "profile" or v in _s.style_names("palettes"))}
    srcs = [*(settings if isinstance(settings, list) else [settings] if settings is not None else []), *([pick] if pick else [])]
    prev = list(_s._EXTRA)
    try:
        _use(*prev, *srcs)
        active_bm, bms, base = rw._page_basemaps(a["basemap"], a["basemaps"], a["api_key"], a["basemap_switcher"])
        bg = rw._bg_color(active_bm)
    finally:
        _use(*prev)
    for lyr in base["layers"]:
        lyr.setdefault("paint", {})        # as render_web._state_expressions gives every layer of the page
    page_style = {"version": 8, "sources": {**base["sources"], **style["sources"]}, "layers": base["layers"] + style["layers"],
                  **{k: style[k] for k in ("glyphs", "state") if k in style}}
    cfg, th = lk["config"], lk["theme"]
    cam = {"pitch": 0, "bearing": 0, "pitch_3d": 55, "max_pitch": 70, **(cfg.get("camera") or {})}
    if a["view_3d"]:
        cam["pitch"] = cam["pitch_3d"]
    for k in ("pitch", "max_pitch", "bearing"):
        if a[k] is not None:
            cam[k] = a[k]
    page = {"basemaps": bms, "basemap_switcher": bool(a["basemap_switcher"]), "tiles": ctl["tiles"], "simple": ctl["simple"], "popup_mode": mode,
            "find_control": bool(a["find_control"]), "zoom_readout": bool(a["zoom_readout"]), "pitch_3d": ctl["pitch_3d"],
            "street_view": a["street_view"], "street_view_key": key or "", "google_3d": bool(a["google_3d"]), "select_color": ctl["select_color"],
            "filter": ctl["filter"], "color_options": meta.get("roadstyle:color_options") or [], "color_active": ctl["color_active"],
            "overlays": ctl["overlays"], "overlay_control": bool(a["overlay_control"]), "overlay_popup": bool(a["overlay_popup"]),
            "tunnel": {**ctl["tunnel"], "bg": bg}, "fill_layers": ctl["fill_layers"], "road_fill": ctl["road_fill"], "views": ctl["views"],
            "items": ctl["items"], "road_popup": inter["popup"], "road_tooltip": inter["tooltip"], "hover_delay_ms": inter["hover_delay_ms"],
            "edge_id_col": ctl["edge_id_col"], "arrow_icon": ctl["arrow_icon"], "arrow_color": ctl["arrow_color"], "arrow_rules": ctl["arrow_rules"]}
    simple_js = {"layer": "roads-simple", "bridge": cfg["bridge_casing_color"], "shadow": cfg["bridge_shadow_color"], "select": ctl["select_color"],
                 "hover": a["hover_color"] or th["selection"]["hover"], "tunnels": bool(ctl["tunnel"]["layers"]), "dashes": dashes}
    x0, y0, x1, y1 = (float(v) for v in g.total_bounds)
    return rw.WebMap(rw._page_html(page_style, page, name=a["name"], cam=cam, bounds=(x0, y0, x1, y1), side_panel_html=a["side_panel_html"],
                                   host_panel_width=a["host_panel_width"], compress=a["compress"], tiles=archive, simple_js=simple_js))


def _tiled_page(pq, lk, style, highway_col, kwargs):
    """render(tiles=True) by the Rust engine: (the PMTiles archive, the sidecar table) of the page, and ``style`` made as the tiled page's
    (render_web's tiled branch): one vector source ``roads`` with the layers ``roads``, ``simple`` and ``slots``. The tiles are the Rust
    Tiler's, with the columns of tiles.build_pmtiles (``keep`` and every ``__rs_*``; the slots whole, from zoom 14); the sidecar is
    tiles.sidecar of the roads (every column, for the popups)."""
    from .tiles import sidecar

    srcs = style["sources"]
    side = sidecar(srcs["roads"]["data"])
    tc = lk["config"]["tiles"]
    z0, z1 = int(tc["minzoom"]), int(tc["maxzoom"])
    keep = sorted({highway_col, kwargs.get("filter_col") or highway_col, "__rs_twoway", "__rs_edge", "lvl", kwargs.get("width_m_col")} - {None})
    names = [n for n in ("roads", "simple", "slots") if n in srcs and srcs[n]["data"]["features"]]
    t = rust().Tiler(pq, json.dumps({**lk, "args": {**lk["args"], "tile_keep": keep, "tile_layers": names}}), None, None, "", [])
    pts = [c for n in names for f in srcs[n]["data"]["features"] for c in ((f.get("geometry") or {}).get("coordinates") or [])]
    bounds = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    archive = _pmtiles(t, z0, z1, bounds, names)
    # the style: the roads source a vector one; the pieces and the slots its layers
    srcs["roads"] = {"type": "vector", "url": "pmtiles://roads", "minzoom": z0, "maxzoom": z1}
    for n in ("simple", "slots"):
        srcs.pop(n, None)
    for lyr in style["layers"]:
        if lyr.get("source") in ("simple", "slots"):
            lyr["source"], lyr["source-layer"] = "roads", lyr["source"]
        elif lyr.get("source") == "roads":
            lyr["source-layer"] = "roads"
    return archive, side


def _pmtiles(t, z0, z1, bounds, names) -> bytes:
    """A PMTiles archive (gzipped tiles, as tiles.build_pmtiles) of the Tiler ``t``'s tiles in ``bounds`` (lon / lat) from zoom ``z0`` to
    ``z1``; an empty tile is left out. ``names``: the tile layers, for the archive's metadata."""
    import gzip
    import io

    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer

    from .tiles import _merc, _tile_range

    (mx0, my0), (mx1, my1) = _merc(*bounds[:2]), _merc(*bounds[2:])
    buf = io.BytesIO()
    w = Writer(buf)
    for z in range(z0, z1 + 1):
        x0, x1, y0, y1 = _tile_range((mx0, my0, mx1, my1), z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                data = t.tile(z, x, y)
                if data:
                    w.write_tile(zxy_to_tileid(z, x, y), gzip.compress(data, 6, mtime=0))
    e7 = [int(v * 1e7) for v in bounds]
    w.finalize({"tile_type": TileType.MVT, "tile_compression": Compression.GZIP, "min_zoom": z0, "max_zoom": z1,
                "min_lon_e7": e7[0], "min_lat_e7": e7[1], "max_lon_e7": e7[2], "max_lat_e7": e7[3],
                "center_zoom": (z0 + z1) // 2, "center_lon_e7": (e7[0] + e7[2]) // 2, "center_lat_e7": (e7[1] + e7[3]) // 2},
               {"vector_layers": [{"id": n, "fields": {}} for n in names]})
    return buf.getvalue()

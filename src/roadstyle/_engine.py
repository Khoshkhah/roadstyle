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


def _warn():
    """The Rust engine's warnings of the last call, as Python's (render_web's warnings.warn)."""
    import warnings
    for w in rust().take_warnings():
        warnings.warn(w, stacklevel=4)


def fallback(name: str | None, reason: str) -> bool:
    """A part that the Rust engine does not have: with ``engine="rust"`` given, an error; with the default (``ROADSTYLE_ENGINE=rust``),
    a warning, and the Python engine makes this one (it never changes engine without a message). Returns True: use Python."""
    if name is not None:
        raise ValueError(f"engine='rust': {reason}; use engine='python'")
    import warnings
    warnings.warn(f"roadstyle: {reason}: the Python engine makes this one (ROADSTYLE_ENGINE=rust)", stacklevel=3)
    return True


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
    """The roads as GeoParquet bytes (the geometry as WKB), as the Rust reader reads them. A column of mixed values (True and "square" in a
    cap column) is text: true and false as "true" and "false", which the engine reads as Python's truth (render_web._truthy)."""
    import pyarrow as pa

    buf = io.BytesIO()
    try:
        edges.to_parquet(buf, index=False)
    except (pa.ArrowInvalid, pa.ArrowTypeError):
        g = edges.copy()
        gone = lambda v: v is None or (isinstance(v, float) and v != v)       # noqa: E731
        for c in g.columns:
            if c != g.geometry.name and g[c].dtype == object and len({type(v) for v in g[c] if not gone(v)}) > 1:
                g[c] = [None if gone(v) else "true" if v is True else "false" if v is False else str(v) for v in g[c]]
        buf = io.BytesIO()
        g.to_parquet(buf, index=False)
    return buf.getvalue()


def _check_tunnels(cfg):
    """render_web._tun_settings' checks of the tunnel look: each colour of tunnel_towards a '#rrggbb', tunnel_toward one of them or one."""
    import re
    hexc = re.compile(r"#[0-9a-fA-F]{6}")
    towards, toward = cfg.get("tunnel_towards") or {}, cfg.get("tunnel_toward")
    for n, c in towards.items():
        if not (isinstance(c, str) and hexc.fullmatch(c)):
            raise ValueError(f"tunnel_towards {n!r}: {c!r} is not a '#rrggbb' colour")
    if toward not in towards and not (isinstance(toward, str) and hexc.fullmatch(toward)):
        raise ValueError(f"tunnel_toward {toward!r} is not a colour name in {list(towards)} or a '#rrggbb' colour")


def look(*, palette=None, profile=None, settings=None, args=None, features=None) -> dict:
    """The resolved look (look.json) of render_edges' palette, profile and settings, made by the Rust engine."""
    o = {"palette": palette, "profile": profile, "settings": settings, "args": args or {}}
    if features is not None:
        o["features"] = features
    files = _own_files()
    if files:
        o["files"] = files
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
    text = rust().make_style(_geoparquet(edges), json.dumps(lk), None, None, kwargs.get("name") or "roads")     # export_inline's name
    _warn()
    return json.loads(text)


def export_geojson(edges, out_dir, *, format="geojson", keep=None, **kwargs) -> dict:
    """``roadstyle.export_geojson``: stage 1 of the Rust engine, its files in ``out_dir``; {file name: size in bytes}."""
    if format not in ("geojson", "geoparquet"):
        raise ValueError(f"format must be 'geojson' or 'geoparquet', got {format!r}")
    missing = [c for c in RUST_COLUMNS if (kwargs.get(f"{c}_col") or c) not in edges.columns]
    if missing:
        raise ValueError(f"export_geojson: the roads have no column {', '.join(missing)}")
    kwargs = dict(kwargs)
    kwargs.pop("engine", None)
    kwargs.setdefault("view_3d", True)      # as export_inline
    lk = _look_of(kwargs)
    s = rust().make_sources(_geoparquet(edges), json.dumps(lk), None, None, kwargs.get("name") or "roads")
    files = s.save(str(out_dir), format, [str(c) for c in (keep or [])])
    _warn()
    return dict(files)


def tile_geojson(src_dir, out, *, format="pmtiles", keep=None, base_url=""):
    """``roadstyle.tile_geojson``: stage 2 of the Rust engine from ``export_geojson``'s files; the path written."""
    from pathlib import Path

    from .tiles import _merc, _tile_range

    if format not in ("pmtiles", "xyz"):
        raise ValueError(f"format must be 'pmtiles' or 'xyz', got {format!r}")
    prefix = f"{base_url.rstrip('/')}/" if base_url else ""
    t = rust().tile_files(str(src_dir), [str(c) for c in (keep or [])], prefix)
    _warn()
    bounds = t.bounds()
    if bounds is None:
        raise ValueError(f"tile_geojson: no feature in the files of {src_dir}")
    out = Path(out)
    if format == "pmtiles":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(t.archive(list(bounds), t.layers()))
        return out
    z0, z1 = t.zooms()
    lo, hi = _merc(*bounds[:2]), _merc(*bounds[2:])
    for z in range(z0, z1 + 1):              # the style's tile URL: <base_url>/roads/{z}/{x}/{y}
        x0, x1, y0, y1 = _tile_range((lo[0], lo[1], hi[0], hi[1]), z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                b = t.tile(z, x, y)
                if b:
                    p = out / "roads" / str(z) / str(x) / str(y)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b)
    (out / "style.json").write_text(t.style)
    return out


def _look_of(kwargs) -> dict:
    """The resolved look of render's keywords, with what the engine reads as JSON: the boundary as GeoJSON (_boundary_fc) and each overlay
    as its fields, its style of the settings filled in (_styled), its data as a FeatureCollection (``fc``)."""
    kwargs = dict(kwargs)
    palette, profile, settings = kwargs.pop("palette", None), kwargs.pop("profile", None), kwargs.pop("settings", None)
    features, overlays, items = kwargs.pop("features", None), kwargs.pop("overlays", None), kwargs.pop("items", None)
    if kwargs.get("boundary") is not None:   # a shapely geometry or a GeoDataFrame: GeoJSON, as render does (_boundary_fc)
        from .render_web import _boundary_fc
        kwargs["boundary"] = json.loads(json.dumps(_boundary_fc(kwargs["boundary"])))
    # the settings in force (roadstyle.json, $ROADSTYLE_CONFIG, use_settings), then the call's, as render_edges stacks them
    from . import _settings as _s
    given = _settings_data(settings)
    active = _s._sources()
    if active:
        given = [*active, *(given if isinstance(given, list) else [given] if given is not None else [])]
    lk = look(palette=palette, profile=profile, settings=given, args=kwargs, features=features)
    _check_tunnels(lk["config"])
    if lk["config"].get("twin_casing") not in ("one", "each"):
        raise ValueError(f'twin_casing must be "one" or "each", got {lk["config"].get("twin_casing")!r}')
    if overlays:
        lk["args"]["overlays"] = [_overlay_json(o, (lk["config"].get("overlays") or {}).get("styles") or {}) for o in overlays]
    if items is not None:          # render's items=: the road's own line items, as GeoJSON
        from .overlays import to_fc
        lk["args"]["items"] = json.loads(json.dumps(to_fc(items)))
    return lk


def _settings_data(settings):
    """render's settings for the engine: a mapping, or a list of them; a file (JSON or YAML) is read here, as use_settings reads it."""
    from pathlib import Path

    if isinstance(settings, (list, tuple)):
        return [_settings_data(x) for x in settings]
    if isinstance(settings, (str, Path)):
        from ._settings import _read_settings
        try:
            return _read_settings(Path(settings))
        except Exception as e:      # missing, not JSON / YAML, not a mapping: an error that names the file (_settings._sources)
            raise ValueError(f"settings file {settings}: {e}") from e
    return settings


def _own_files() -> dict:
    """The user's own profiles and palettes (_settings._style_dirs: ./profiles, ./palettes, then the user config; the first file of a name
    wins) as text, for the engine's look."""
    from . import _settings as _s
    out = {}
    for kind in ("profiles", "palettes"):
        found = {}
        for d in _s._style_dirs(kind):
            for f in sorted(d.glob("*.yaml")) if d.is_dir() else ():
                found.setdefault(f.stem, f.read_text(encoding="utf-8"))
        if found:
            out[kind] = found
    return out


def own_style_names(palette=None, profile=None) -> list[str]:
    """The palette and profile names that are files of the user (./palettes, ./profiles), not bundled: the engine has the bundled ones."""
    from . import _settings as _s
    out = []
    for kind, name in (("palettes", palette), ("profiles", profile)):
        bundled = [f.stem for f in (_s.data_dir() / kind).glob("*.yaml")]
        if isinstance(name, str) and name in _s.style_names(kind) and name not in bundled:
            out.append(f"{kind[:-1]} {name!r}")
    return out


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


def compute_levels(edges, *, layer_col="layer", bridge_col="bridge", tunnel_col="tunnel", method="solve", highway_col="highway",
                   junction_col="junction", time_limit=60.0, band_col=None, order="priority", band_dist=10.0, head_m=5.0, max_level=20,
                   margin=1.0, min_positions=True, near_rules=False):
    """``roadstyle.compute_levels`` by the Rust engine: the same four columns (casing_start, casing_level, casing_end, fill_level).
    The attrs have ``levels_params`` and ``levels_info`` (with the counts). The Rust solver has no time limit: ``time_limit`` is not used."""
    rows, info = rust().compute_levels(_geoparquet(edges), method, [highway_col, layer_col, bridge_col, tunnel_col, junction_col],
                                       band_col=band_col, order=order, band_dist=band_dist, head_m=head_m, max_level=max_level, margin=margin,
                                       min_positions=min_positions, near_rules=near_rules)
    info = json.loads(info)
    pairs = {k: [tuple(p) for p in info.pop(k, [])] for k in ("given_up_pairs", "orders_not_kept_pairs", "near_not_kept")}
    g = edges.copy()
    for i, c in enumerate(("casing_start", "casing_level", "casing_end", "fill_level")):
        g[c] = [r[i] for r in rows]
    from .levels_store import levels_params
    g.attrs["levels_params"] = levels_params(method, head_m, band_dist, margin, max_level, band_col, order, min_positions and method == "solve")
    g.attrs["levels_info"] = {"engine": "rust", **info}
    if method == "solve":         # as Python's: the pairs and parts by road id (the parts of a given-up pair are Python's)
        g.attrs["levels_given_up"] = pairs["given_up_pairs"]
        g.attrs["levels_orders_not_kept"] = pairs["orders_not_kept_pairs"]
        g.attrs["levels_near"] = sorted((u, l, ("start", "main", "end")[h]) for u, l, h in pairs["near_not_kept"])
        if not g.attrs["levels_given_up"]:
            g.attrs["levels_given_up_parts"] = []
        if g.attrs["levels_given_up"]:
            import warnings
            warnings.warn(f"compute_levels: {len(g.attrs['levels_given_up'])} stack pair(s) could not be satisfied; see result.attrs['levels_given_up']",
                          stacklevel=3)
    return g


def solve_intervals(n, meets, stacks, orders, max_level, margin, min_positions, near, fixed):
    """``levels._solve_intervals`` by the Rust solver: the same rules on road indexes, the same ``(parts, given_up, info)``. ``fixed``:
    {road index: its four numbers around the ground 0}. The parts are in steps of ``margin`` (only their order matters: solve_levels
    makes them small consecutive numbers)."""
    import math
    import time
    t0 = time.time()
    ends, part = {"start": 0, "end": 2}, {"s": 0, "m": 1, "e": 2}
    steps = math.floor(2 * max_level / margin + 1e-9)
    parts, broken, not_kept, near_broken = rust().solve_rules(
        n, [(x, ends[ex], y, ends[ey]) for x, ex, y, ey in meets], [(u, l, part[h]) for u, l, h in stacks],
        [(u, l, part[h]) for u, l, h in near], list(orders), [(r, [x + max_level for x in v]) for r, v in fixed.items()], steps, min_positions)
    word = ("start", "main", "end")
    info = {"pairs": len({(u, l) for u, l, _ in [*stacks, *near]}), "roads": n, "meets": len(meets), "order_pairs": len(set(orders)),
            "order_violations": len(not_kept), "orders_not_kept": [tuple(p) for p in not_kept],
            "given_up_parts": sorted({(u, l, word[h]) for u, l, h in broken}), "near_parts": sorted({(u, l, word[h]) for u, l, h in near_broken}),
            "near_warnings": len({(u, l) for u, l, _ in near_broken}), "solves": 1, "solver": "rust", "status": "OPTIMAL",
            "seconds": round(time.time() - t0, 1)}
    return [tuple(p) for p in parts], sorted({(u, l) for u, l, _ in broken}), info


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
    _warn()
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
                levels_db=None, engine=None, **kwargs):
    """``render_edges(backend="web", engine="rust")``: the roads' style from the Rust engine (state "live": the state in the expressions and
    the interaction contract in the metadata), the base map and the page as Python writes them (render_web._page_basemaps, _page_html),
    with the settings of the call in force. ``tiles=True``: the roads, their pieces and their names in an embedded PMTiles archive of the
    Rust engine's tiles (_tiled_page)."""
    import inspect
    import os

    from . import _settings as _s
    from . import render_web as rw
    from . import use_settings as _use
    from .edges import as_edges
    from .filters import filter_edges

    for k in ("band_col", "order"):                     # inputs of the level step, not of the drawing (docs/design/level_input.md)
        if k in kwargs:
            raise ValueError(f"render_edges takes no {k}: compute the levels first (rs.compute_levels(edges, {k}=...), or rs.level_input + "
                             "rs.solve_levels) and pass casing_level_col / fill_level_col / casing_start_col / casing_end_col")
    for k, why in (("style", "a Styler object is Python's"), ("styler", "a Styler object is Python's")):
        if kwargs.get(k):
            raise ValueError(f"engine='rust': {k}= ({why}); use engine='python'")
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
    _warn()
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
    # the page's own parts with the settings of the call in force (the base map, its canvas colour, the views' names), as render_edges
    # applies them
    pick = {k: v for k, v in (("profile", profile), ("palette", palette)) if v is not None and v != _s.theme()["active"][k]
            and (k == "profile" or v in _s.style_names("palettes"))}
    srcs = [*(settings if isinstance(settings, list) else [settings] if settings is not None else []), *([pick] if pick else [])]
    prev = list(_s._EXTRA)
    try:
        _use(*prev, *srcs)
        active_bm, bms, base = rw._page_basemaps(a["basemap"], a["basemaps"], a["api_key"], a["basemap_switcher"])
        bg = rw._bg_color(active_bm)
        views = _views(style, pq, kwargs, [b["key"] for b in bms], palette, profile, settings, highway_col) if a["views"] else []
    finally:
        _use(*prev)
    if tiled and any("palette" in v["set"] for v in views):
        raise ValueError("engine='rust': tiles=True with a view's palette (the tiles have one palette); use engine='python'")
    dashes = sorted({f["properties"].get("__rs_dash") for f in (style["sources"].get("simple") or {"data": {"features": []}})["data"]["features"]} - {None, ""})
    archive = _tiled_page(pq, lk, style, highway_col, kwargs) if tiled else None
    meta = style.pop("metadata")
    ctl, inter = meta["roadstyle:controls"], meta["roadstyle:interaction"]
    for lyr in style["layers"]:
        lyr.pop("metadata", None)          # the page gives the dashboard its options; its style has no metadata
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
            "tunnel": {**ctl["tunnel"], "bg": bg}, "fill_layers": ctl["fill_layers"], "road_fill": ctl["road_fill"], "views": views,
            "items": ctl["items"], "road_popup": inter["popup"], "road_tooltip": inter["tooltip"], "hover_delay_ms": inter["hover_delay_ms"],
            "edge_id_col": ctl["edge_id_col"], "arrow_icon": ctl["arrow_icon"], "arrow_color": ctl["arrow_color"], "arrow_rules": ctl["arrow_rules"]}
    simple_js = {"layer": "roads-simple", "bridge": cfg["bridge_casing_color"], "shadow": cfg["bridge_shadow_color"], "select": ctl["select_color"],
                 "hover": a["hover_color"] or th["selection"]["hover"], "tunnels": bool(ctl["tunnel"]["layers"]), "dashes": dashes}
    x0, y0, x1, y1 = (float(v) for v in g.total_bounds)
    # the page by the Rust page writer (roadstyle::page); the gzip blobs by Python's zlib, so the page is Python's byte for byte
    from .tiles import _b64gz, sidecar
    pmt, side = archive if archive else (None, sidecar(page_style["sources"]["roads"]["data"]))     # the road table, before the gzip
    gz = rw._compress_sources(page_style) if a["compress"] else {}
    parts = {"name": a["name"], "cam": cam, "bounds": [x0, y0, x1, y1], "side_panel_html": a["side_panel_html"],
             "host_panel_width": a["host_panel_width"], "compress": False, "gz": gz, "simple_js": simple_js if a["simple"] else None}
    parts["side_b64"] = _b64gz(side)       # the road table, in both ways
    return rw.WebMap(rust().make_page(json.dumps(page_style), json.dumps(page), json.dumps(parts), pmt))


def _views(style, pq, kwargs, basemaps, palette, profile, settings, highway_col):
    """render's ``views``, checked (render_web._check_views), as the page reads them; a palette that a view names other than the page's
    is merged into ``style`` (render_web._merge_palettes: the colours that differ, one copy per palette, picked by the state rs_palette),
    from a Rust style of that palette, and the filter panel gets each class's colour in each palette."""
    from . import _settings as _s
    from . import render_web as rw

    meta, ctl = style["metadata"], style["metadata"]["roadstyle:controls"]
    colors = [o["name"] for o in meta.get("roadstyle:color_options") or []] if kwargs.get("color_options") else []
    views = rw._check_views(kwargs["views"], colors, [o["label"] for o in ctl["overlays"]], ctl["filter"]["classes"], basemaps,
                            _s.style_names("palettes"))
    pals = [p for p in dict.fromkeys(v["set"]["palette"] for v in views if "palette" in v["set"]) if p != palette]
    if pals:
        def build(n):
            lk = _look_of({**kwargs, "palette": n, "profile": profile, "settings": settings, "highway_col": highway_col, "state": "live"})
            st = json.loads(rust().make_style(pq, json.dumps(lk), None, None, kwargs.get("name")))
            return {"style": st, "geo": st["sources"]["roads"]["data"], "slots": (st["sources"].get("slots") or {}).get("data") or {"features": []}}
        slots = (style["sources"].get("slots") or {}).get("data") or {"features": []}
        rw._merge_palettes(style, style["sources"]["roads"]["data"], slots, {n: build(n) for n in pals}, palette)
        fb = rw._FB["fill"]
        first = {}
        for ft in style["sources"]["roads"]["data"]["features"]:
            first.setdefault(ft["properties"].get(ctl["filter"]["col"]), ft["properties"])
        flt = ctl["filter"]
        flt["palettes"] = {n: {c: first[c].get(f"__rs_fill@{n}", first[c].get("__rs_fill")) or fb for c in flt["classes"]} for n in pals}
        flt["palettes"][style["metadata"]["roadstyle:state"]["rs_palette"]] = dict(flt["swatches"])
    return views


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
    def points(g):            # a LineString's points, a Point itself
        c = (g or {}).get("coordinates") or []
        return [c] if (g or {}).get("type") == "Point" else c
    pts = [c for n in names for f in srcs[n]["data"]["features"] for c in points(f.get("geometry"))]
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
    """A PMTiles archive (gzipped tiles, as tiles.build_pmtiles) of the Tiler ``t``'s tiles in ``bounds`` (lon / lat), from its first to its
    last zoom (``z0``, ``z1``: the same); an empty tile is left out. ``names``: the tile layers, for the archive's metadata. The crate writes
    it (roadstyle_tiles::pmtiles), the format of the pmtiles package's Writer."""
    return t.archive([float(v) for v in bounds], list(names))

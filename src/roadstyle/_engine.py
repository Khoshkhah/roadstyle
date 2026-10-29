"""The calls into roadstyle's Rust engine, the extension module ``roadstyle._rust`` (built from ``rust/roadstyle-py``).

The page, the style, the tiles and the exports are the Rust engine's. The drawing-order solver of ``roadstyle.levels`` also has a Python
form (``engine="python"``, or ``ROADSTYLE_ENGINE=python``) for the parts the Rust solver does not have. Without level columns the Rust
engine computes the levels (``compute_levels``, method "solve").
"""
from __future__ import annotations

import json
import math
import os

ENGINES = ("python", "rust")

# what the Rust engine needs in the roads
RUST_COLUMNS = ("highway",)


def engine(name: str | None = None) -> str:
    """The engine of the level solver: ``name``, else ``ROADSTYLE_ENGINE``, else "rust"."""
    e = (name or os.environ.get("ROADSTYLE_ENGINE") or "rust").lower()
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


def _arrow(edges):
    """The roads as an Arrow table (the geometry as WKB), which the Rust binding reads through ``__arrow_c_stream__``. A column of mixed
    values (True and "square" in a cap column) is text: true and false as "true" and "false", which the engine reads as Python's truth
    (render_web._truthy)."""
    import pyarrow as pa

    try:
        return edges.to_arrow(index=False, geometry_encoding="WKB")
    except (pa.ArrowInvalid, pa.ArrowTypeError):
        g = edges.copy()
        gone = lambda v: v is None or (isinstance(v, float) and v != v)       # noqa: E731
        for c in g.columns:
            if c != g.geometry.name and g[c].dtype == object and len({type(v) for v in g[c] if not gone(v)}) > 1:
                g[c] = [None if gone(v) else "true" if v is True else "false" if v is False else str(v) for v in g[c]]
        return g.to_arrow(index=False, geometry_encoding="WKB")


def look(*, palette=None, profile=None, settings=None, args=None, features=None):
    """The resolved look of render_edges' palette, profile and settings, made by the Rust engine: a ``Look`` handle (roadstyle-look),
    parsed one time; ``.json()`` gives its text, ``.part("sections")`` the JSON text of one part (map, sections, palette, settings,
    features, other, base_map_page)."""
    return rust().resolve_look(json.dumps(_look_options(palette, profile, settings, args, features)))


def _look_options(palette, profile, settings, args, features):
    """The options that ``look`` resolves (roadstyle-look's Options), with the user's own profiles and palettes as text."""
    o = {"palette": palette, "profile": profile, "settings": settings, "args": args or {}}
    if features is not None:
        o["features"] = features
    files = _own_files()
    if files:
        o["files"] = files
    return o


def export_inline(edges, **kwargs) -> dict:
    """``roadstyle.export_inline`` made by the Rust engine: the same style, from the same keywords."""
    missing = [c for c in RUST_COLUMNS if (kwargs.get(f"{c}_col") or c) not in edges.columns]
    if missing:
        raise ValueError(f"the roads have no column {', '.join(missing)}")
    kwargs = dict(kwargs)
    kwargs.pop("engine", None)
    kwargs.setdefault("view_3d", True)      # as export_inline
    kwargs["export"] = True                 # an app with no road table: the roads source, its pick and highlight (audit N2)
    lk = _look_of(kwargs)
    text = rust().inline_style(_arrow(edges), lk, None, None, kwargs.get("name") or "roads")     # export_inline's name
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
    kwargs["export"] = True                 # stage 1 of export_style: the roads source too (audit N2)
    lk = _look_of(kwargs)
    s = rust().style_sources(_arrow(edges), lk, None, None, kwargs.get("name") or "roads")
    files = s.save(str(out_dir), format, [str(c) for c in (keep or [])])
    _warn()
    return dict(files)


def tile_geojson(src_dir, out, *, format="pmtiles", keep=None, base_url=""):
    """``roadstyle.tile_geojson``: stage 2 of the Rust engine from ``export_geojson``'s files; the path written."""
    from pathlib import Path

    if format not in ("pmtiles", "xyz"):
        raise ValueError(f"format must be 'pmtiles' or 'xyz', got {format!r}")
    prefix = f"{base_url.rstrip('/')}/" if base_url else ""
    t = rust().tiles_of_files(str(src_dir), [str(c) for c in (keep or [])], prefix)
    _warn()
    bounds = t.bounds()
    if bounds is None:
        raise ValueError(f"tile_geojson: no feature in the files of {src_dir}")
    out = Path(out)
    if format == "pmtiles":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(t.archive(list(bounds), t.layers()))
        return out
    t.write_xyz(str(out / "roads"), list(bounds), "")          # the style's tile URL: <base_url>/roads/{z}/{x}/{y}
    (out / "style.json").write_text(t.style)
    return out


def _look_of(kwargs):
    """The resolved look of render's keywords (a ``Look`` handle), with what the engine reads as JSON: the boundary as GeoJSON
    (_boundary_fc) and each overlay as its fields, its style of the settings filled in (_styled), its data as a FeatureCollection
    (``fc``)."""
    return _look_and_options(kwargs)[0]


def _look_and_options(kwargs):
    """_look_of's look and the options that it was resolved from (their args: the look's, ``page_from`` takes them from the look)."""
    kwargs = dict(kwargs)
    palette, profile, settings = kwargs.pop("palette", None), kwargs.pop("profile", None), kwargs.pop("settings", None)
    features, overlays, items = kwargs.pop("features", None), kwargs.pop("overlays", None), kwargs.pop("items", None)
    if items is not None:          # render's items=: the road's own line items, as GeoJSON (read with items_popup)
        from .overlays import to_fc
        kwargs["items"] = to_fc(items)
    if kwargs.get("boundary") is not None:   # a shapely geometry or a GeoDataFrame: GeoJSON, as render does (_boundary_fc)
        from .render_web import _boundary_fc
        kwargs["boundary"] = json.loads(json.dumps(_boundary_fc(kwargs["boundary"])))
    # the settings in force (roadstyle.json, $ROADSTYLE_CONFIG, use_settings), then the call's, as render_edges stacks them
    from . import _settings as _s
    given = _settings_data(settings)
    active = _s._sources()
    if active:
        given = [*active, *(given if isinstance(given, list) else [given] if given is not None else [])]
    o = _look_options(palette, profile, given, kwargs, features)
    lk = rust().resolve_look(json.dumps(o))
    # the tunnel look is checked by the look (the texts of render_web._tun_settings)
    sec = json.loads(lk.part("sections"))
    if sec["roads"]["twin_casing"] not in ("one", "each"):
        raise ValueError(f'twin_casing must be "one" or "each", got {sec["roads"]["twin_casing"]!r}')
    if overlays:
        lk = lk.with_arg("overlays", json.dumps([_overlay_json(ov, sec["overlays"].get("styles") or {}) for ov in overlays]))
    return lk, o


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
        bundled = _s.bundled_style_names(kind)
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
    rows, info = rust().compute_levels(_arrow(edges), method, [highway_col, layer_col, bridge_col, tunnel_col, junction_col],
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
    if format not in ("xyz", "pmtiles"):
        raise ValueError(f"format must be 'xyz' or 'pmtiles', got {format!r}")
    kwargs = dict(kwargs)
    name = kwargs.get("name") or "roads"
    kwargs.setdefault("view_3d", True)
    kwargs["tiles"] = True                                 # render's tiled look: the roads source draws (no lean mode)
    kwargs["export"] = True                                # an app with no road table: the arrows are numbered for its thinning (audit N2)
    lk = _look_of(kwargs)
    t = rust().Tiler(_arrow(edges), lk, None, name, "", [str(c) for c in edges.columns])   # every column: a click shows the data
    _warn()
    props = props_json(edges.drop(columns=[edges.geometry.name]))
    return _write_export(t, out_dir, base_url, format, name, tuple(float(v) for v in edges.total_bounds), props)


def props_json(df) -> str:
    """The fields of each road as JSON records, in row order (``props.json`` of export_style); an integer past 2**53 - 1 is text, as in a
    tile (JavaScript holds no more)."""
    big = [c for c in df.columns if str(df[c].dtype).lower().startswith(("int", "uint")) and df[c].abs().max() > 2 ** 53 - 1]
    return df.astype({c: str for c in big}).to_json(orient="records")


def _write_export(t, out_dir, base_url: str, format: str, name: str, bounds, props: str):
    """The files of ``export_style`` from the Tiler ``t`` (its style and its tiles): style.json with the tiles at ``base_url``, the tiles in
    ``bounds`` (lon / lat: the roads' box), the sprite and the popup's files, and ``props.json`` (``props``: the fields of each road as JSON records, in
    the order of the rows: a click on a piece reads its row, the feature id); the path of style.json."""
    import gzip  # noqa: F401  (the same imports as export.py)
    from pathlib import Path

    from . import _assets, _settings
    from .export import _camera, _plugin_css

    style, base = json.loads(t.style), base_url.rstrip("/")
    roads = style["sources"]["roads"]
    generation = style.get("metadata", {}).get("roadstyle:generation")           # a row is valid in one generation only: the URL carries it
    tiles_url = f"{base}/tiles/{{z}}/{{x}}/{{y}}{t.extension}" + (f"?g={generation}" if generation else "")
    at = {"tiles": [tiles_url]} if format == "xyz" else {"url": f"pmtiles://{base}/roads.pmtiles"}
    roads = style["sources"]["roads"] = {**{k: roads[k] for k in ("type", "minzoom", "maxzoom", "promoteId", "encoding") if k in roads}, **at, "bounds": list(bounds)}
    meta = style.pop("metadata", {})
    style = {k: style[k] for k in ("version", "sources", "layers", "glyphs") if k in style}     # Python's key order: the same bytes
    style["sprite"], style["name"] = f"{base}/sprite", name
    style["center"], style["zoom"] = _camera(bounds)
    style["metadata"] = meta
    for lyr in style["layers"]:                                         # Python tags a layer's group after its source-layer
        if "metadata" in lyr:
            lyr["metadata"] = lyr.pop("metadata")
    images = style.setdefault("metadata", {}).pop("roadstyle:images", None) or {}
    images.pop("oneway", None)                                          # export_style draws the arrow from the sprite
    if images:                                                          # the base map's textures and icons (a duckOSM map)
        style["metadata"]["roadstyle:images"] = images
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    if format == "pmtiles":
        names = sorted({lyr["source-layer"] for lyr in style["layers"] if "source-layer" in lyr})
        (d / "roads.pmtiles").write_bytes(_pmtiles(t, int(roads["minzoom"]), int(roads["maxzoom"]), bounds, names))
    if format == "xyz":                     # every tile with data, and an empty file for each other tile of the roads' bounds
        fallback = float(meta.get("roadstyle:tiles", {}).get("buffer_px", 80))
        t.write_xyz(str(d / "tiles"), list(bounds), t.extension, (json.dumps(style["layers"]), fallback))
    (d / "props.json").write_text(props)             # a click on a piece: its id is the row of the road in this file
    base_props = {}
    for layer, text in t.props_files():          # a layer's popup fields are not in its tiles: by row, the feature id
        (d / "props").mkdir(exist_ok=True)
        (d / "props" / f"{layer}.json").write_text(text)
        base_props[layer] = f"{base}/props/{layer}.json"
    (d / "popup.css").write_text(_plugin_css())
    (d / "popup.js").write_text(_assets.text("static/popup.js"))
    style["metadata"]["roadstyle:interaction"] = {**style["metadata"].get("roadstyle:interaction", {}), "css": f"{base}/popup.css",
                                                  "js": f"{base}/popup.js", "props": f"{base}/props.json",
                                                  **({"base_props": base_props} if base_props else {})}
    png = _assets.data("data/sprite.png")
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
    """``render_edges(backend="web")``: the page in one call of the Rust engine (roadstyle::page_options::page_from, audit
    R3): the roads' style (state "live"), the base map, the views and their palettes, the dashboard's options and the page. ``tiles=True``:
    the roads, their pieces and their names in an embedded PMTiles archive. Python gives what only it knows: the data steps (include,
    exclude, levels_db), the look's options, and the keys (base maps, Google Maps)."""
    from . import render_web as rw
    from .edges import as_edges
    from .filters import filter_edges

    for k in ("band_col", "order"):                     # inputs of the level step, not of the drawing (docs/design/level_input.md)
        if k in kwargs:
            raise ValueError(f"render_edges takes no {k}: compute the levels first (rs.compute_levels(edges, {k}=...), or rs.level_input + "
                             "rs.solve_levels) and pass casing_level_col / fill_level_col / casing_start_col / casing_end_col")
    for k, why in (("style", "a Styler object"), ("styler", "a Styler object")):
        if kwargs.get(k):
            raise ValueError(f"{k}= ({why}); use color_by, colors, cmap, vmin, vmax or width_by")
    g = as_edges(gdf, class_col=highway_col).gdf
    if include is not None or exclude is not None:
        g = filter_edges(g, include=include, exclude=exclude, highway_col=highway_col, match_links=match_links)
    if levels_db is not None:
        if any(kwargs.get(k) for k in ("casing_level_col", "fill_level_col", "casing_start_col", "casing_end_col")):
            raise ValueError("levels_db and level columns of your own (casing_level_col, fill_level_col, ...) are two drawing orders: use one")
        from .levels_store import stored_levels
        g, level_kw = stored_levels(levels_db, g, kwargs.get("edge_id_col", "edge_id"))
        kwargs = {**kwargs, **level_kw}
    lk, o = _look_and_options({**kwargs, "palette": palette, "profile": profile, "settings": settings, "highway_col": highway_col,
                               "state": "live"})
    html = rust().page_from(_arrow(g), lk, json.dumps(o), json.dumps(page_given(kwargs, palette, profile, settings, lk, o["args"])))
    _warn()
    return rw.WebMap(html)


def page_given(kwargs, palette=None, profile=None, settings=None, lk=None, args=None) -> dict:
    """The page's keys and what only Python knows of a page (roadstyle::page_options makes the rest): the page's keys of the call
    (roadstyle::page_options::given_of of the look ``lk`` and the call's ``args``, as the wasm page), the Google Maps key of the
    environment, and each base map key with its API key of roadstyle.json, of set_api_key or of the environment (basemaps.get_api_key,
    by provider), in force with the settings of the call as render_edges applies them."""
    import dataclasses

    from . import _settings as _s
    from . import render_web as rw
    from . import use_settings as _use

    a = {k: kwargs.get(k) for k in ("basemap", "basemaps", "api_key", "street_view_key")}
    pick = {k: v for k, v in (("profile", profile), ("palette", palette)) if v is not None and v != _s.theme()["active"][k]
            and (k == "profile" or v in _s.style_names("palettes"))}
    srcs = [*(settings if isinstance(settings, list) else [settings] if settings is not None else []), *([pick] if pick else [])]
    prev = list(_s._EXTRA)
    try:
        _use(*prev, *srcs)
        from .basemaps import DEFAULT_SWITCHER, get_basemap
        keys = list(dict.fromkeys(k for k in [a["basemap"] or rw.CONFIG.basemap, *(a["basemaps"] or DEFAULT_SWITCHER)] if isinstance(k, str)))
        resolved = [dataclasses.asdict(get_basemap(k, api_key=a["api_key"])) for k in keys]
    finally:
        _use(*prev)
    page = json.loads(rust().given_of(lk, json.dumps({"args": args or {}})))     # the page's keys: page_options::given_of, the one rule
    return {**page, "resolved_basemaps": resolved, "street_view_key": a["street_view_key"] or os.environ.get("GOOGLE_MAPS_KEY") or None}


def _pmtiles(t, z0, z1, bounds, names) -> bytes:
    """A PMTiles archive (gzipped tiles, as tiles.build_pmtiles) of the Tiler ``t``'s tiles in ``bounds`` (lon / lat), from its first to its
    last zoom (``z0``, ``z1``: the same); an empty tile is left out. ``names``: the tile layers, for the archive's metadata. The crate writes
    it (roadstyle_tiles::pmtiles), the format of the pmtiles package's Writer."""
    return t.archive([float(v) for v in bounds], list(names))

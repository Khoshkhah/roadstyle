"""The roads as a MapLibre style and vector tiles, for other apps (docs/design/style_export.md).

``export_style`` writes ``style.json``, the tiles (a ``tiles/{z}/{x}/{y}.pbf`` folder, or one ``roads.pmtiles``) and a
sprite with the one-way arrow. GeoLibre, RustGIS, QGIS and any MapLibre page open the style by its URL. The style is
the one ``render_edges(..., tiles=True)`` puts in its page; what the page's JavaScript does (popups, the rs* API, the
controls, Street View, Google 3D) is not in it.

Needs the ``tiles`` extra: ``pip install "roadstyle[tiles]"``.
"""
from __future__ import annotations

import gzip
import json
import math
import re
from importlib.resources import files
from pathlib import Path


def _camera(bounds, width=1024, height=768):
    """``(center, zoom)`` that fits ``bounds`` (lon/lat) in a ``width`` x ``height`` px view, as the page's fitBounds."""
    minx, miny, maxx, maxy = bounds
    def y(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(max(-85.0, min(85.0, lat))) / 2))
    zx = math.log2(width / 256 * 360 / max(maxx - minx, 1e-9))
    zy = math.log2(height / 256 * 2 * math.pi / max(y(maxy) - y(miny), 1e-9))
    return [(minx + maxx) / 2, (miny + maxy) / 2], round(max(0.0, min(18.0, min(zx, zy))), 2)


_LEVEL_COLS = {"casing_level_col": "casing_level", "fill_level_col": "fill_level", "casing_start_col": "casing_start",
               "casing_end_col": "casing_end", "head_start_m_col": "head_start_m", "head_end_m_col": "head_end_m",
               "cap_start_col": "cap_start", "cap_end_col": "cap_end"}


def export_geojson(edges, out_dir, *, format: str = "geojson", keep=None, **kwargs) -> dict:
    """Stage 1 of the Rust engine (docs/rust/architecture.md, "The three stages and the one call"): the style and its sources as files
    in ``out_dir``. ``style.json`` names each source's data by its file; there is one file for each source, ``<source>.geojson``
    (``format="geojson"``, for MapLibre and to read) or ``<source>.parquet`` (``format="geoparquet"``, smaller, for DuckDB and large
    areas); and ``road_table.parquet`` holds every field of each road, by its row. The roads' own file has their drawing values only
    (and the columns in ``keep``). ``kwargs``: the keywords of ``export_inline``. Returns {file name: size in bytes}.
    ``tile_geojson`` makes the vector tiles from these files. The Rust engine only."""
    from . import _engine
    return _engine.export_geojson(edges, out_dir, format=format, keep=keep, **kwargs)


def tile_geojson(src_dir, out, *, format: str = "pmtiles", keep=None, base_url: str = "") -> Path:
    """Stage 2 of the Rust engine: the vector tiles of ``export_geojson``'s files in ``src_dir`` (GeoJSON or GeoParquet, as its
    ``style.json`` names them); it needs neither the roads nor the look. ``format="pmtiles"`` writes ``out`` as one archive;
    ``"xyz"`` writes the folder ``out``: ``roads/{z}/{x}/{y}`` and ``style.json`` (the style with one vector source, at
    ``<base_url>/roads/{z}/{x}/{y}``). ``keep``: more columns in the road tiles. The tiles are the tiles of ``export_style``'s one
    call. Returns ``out``. The Rust engine only."""
    from . import _engine
    return _engine.tile_geojson(src_dir, out, format=format, keep=keep, base_url=base_url)


def export_style(edges, out_dir, *, base_url: str, format: str = "xyz", engine: str | None = None, **kwargs) -> Path:
    """Write the roads as ``style.json`` + vector tiles + a sprite into ``out_dir``; return the path of ``style.json``.

    ``edges``: a GeoDataFrame, or the path of a duckOSM GeoParquet file (``duckosm export-gis --format geoparquet``: the
    edges with their data and their drawing positions, docs/design/style_export.md version 2). A GeoParquet file without
    the positions is an error that says how to save them. ``base_url``: the URL where ``out_dir`` will be served. Every URL
    in the style is absolute (MapLibre does not say how it resolves a relative one). ``format``: ``"xyz"`` (default) writes
    a ``tiles/{z}/{x}/{y}.pbf`` folder, which every app and any static server can use; ``"pmtiles"`` writes one
    ``roads.pmtiles`` for MapLibre pages that register the ``pmtiles://`` protocol. The style holds the roads only: the base
    map comes from the app. The road tiles keep every column of the edges, so a click shows the data. ``kwargs``: the
    keywords of ``render_edges`` (profile, palette, overlays, ...); ``view_3d`` defaults to ``True`` here, so the style has
    the bridge decks for an app's own tilt.
    """
    if format not in ("xyz", "pmtiles"):
        raise ValueError(f"format must be 'xyz' or 'pmtiles', got {format!r}")
    if kwargs.get("views"):
        raise ValueError("export_style: views= are page-only (the page applies the first view at load); leave them out")
    if kwargs.get("color_active", 0):
        raise ValueError("export_style: color_active= is page-only (the style has the first colour option); leave it out")
    if kwargs.get("basemap") is not None:
        raise ValueError("export_style: the style holds the roads only, the base map comes from the app; leave basemap= out")
    from .render import render_edges

    name = kwargs.get("name") or (Path(edges).stem if isinstance(edges, (str, Path)) else "roads")
    if isinstance(edges, (str, Path)):
        import geopandas as gpd
        edges = gpd.read_parquet(edges)
        missing = [c for c in ("casing_level", "fill_level", "casing_start", "casing_end") if c not in edges.columns]
        if missing or edges[["casing_level", "fill_level"]].isna().any().any():
            raise ValueError("export_style: the GeoParquet file has no drawing positions for every edge "
                             f"({'no columns ' + ', '.join(missing) if missing else 'empty values'}). Save them into the duckOSM file first: "
                             "rs.save_levels(con, rs.compute_levels(edges)), then export it again (duckosm export-gis --format geoparquet).")
        for k, c in _LEVEL_COLS.items():
            if c in edges.columns:
                kwargs.setdefault(k, c)
    kwargs.setdefault("view_3d", True)        # the bridge decks: the page has a 3D button, an app has only its own tilt
    from . import _engine
    if _engine.engine(engine) == "rust":     # ``engine``: "python" (default) or "rust" (the style and the tiles of the Rust engine)
        return _engine.export_style(edges, out_dir, base_url=base_url, format=format, **{**kwargs, "name": name})
    out = render_edges(edges, **{**kwargs, "basemap": "blank", "tiles": True, "backend": "web", "_export": True})
    style, base = out["style"], base_url.rstrip("/")
    style["sources"].pop("bm", None)           # the roads only: no background, no base map
    style["layers"] = [lyr for lyr in style["layers"] if lyr["type"] not in ("background", "raster")]
    roads = style["sources"]["roads"]
    del roads["url"]
    if format == "xyz":
        roads["tiles"] = [f"{base}/tiles/{{z}}/{{x}}/{{y}}.pbf"]
    else:
        roads["url"] = f"pmtiles://{base}/roads.pmtiles"
    roads["bounds"] = list(out["bounds"])          # no requests for tiles outside the roads
    style["sprite"] = f"{base}/sprite"
    style["name"] = name                       # an app shows it (GeoLibre's Layers panel)
    _tag_groups(style, kwargs.get("overlays"))
    style["center"], style["zoom"] = _camera(out["bounds"])

    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    if format == "pmtiles":
        (d / "roads.pmtiles").write_bytes(out["pmtiles"])
    else:
        from pmtiles.reader import MemorySource, all_tiles

        # a static server sends a file as it is (no Content-Encoding), so the folder's tiles are not gzipped
        for (z, x, y), data in all_tiles(MemorySource(out["pmtiles"])):
            p = d / "tiles" / str(z) / str(x) / f"{y}.pbf"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(gzip.decompress(data))
        # an empty file for each tile in the roads' bounds that has no road: a request for it is not an error (404) in the app
        from .tiles import _merc, _tile_range
        lo, hi = _merc(*out["bounds"][:2]), _merc(*out["bounds"][2:])
        for z in range(int(roads["minzoom"]), int(roads["maxzoom"]) + 1):
            x0, x1, y0, y1 = _tile_range((lo[0], lo[1], hi[0], hi[1]), z)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    p = d / "tiles" / str(z) / str(x) / f"{y}.pbf"
                    if not p.exists():
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(b"")
    # the page's popup and hover tooltip (static/popup.css, popup.js) for the app's plugin; the CSS only for the plugin's popups
    # (.rs-plugin), so an app's own popups keep their look
    (d / "popup.css").write_text(_plugin_css())
    (d / "popup.js").write_text(files("roadstyle").joinpath("static/popup.js").read_text())
    style.setdefault("metadata", {})["roadstyle:interaction"] = {**out["interaction"], "css": f"{base}/popup.css", "js": f"{base}/popup.js"}
    if out.get("color_options"):     # the legend data, as in export_inline
        style["metadata"]["roadstyle:color_options"] = json.loads(json.dumps(out["color_options"]))
    png = files("roadstyle").joinpath("data/sprite.png").read_bytes()
    from . import _settings
    icon = _settings.theme_value("arrows.icon")          # the profile's arrow; sprite.png is drawn from the default path
    index = json.dumps({"oneway": {"x": 0, "y": 0, "width": icon["width"], "height": icon["height"], "pixelRatio": icon["pixel_ratio"], "sdf": True}})
    for name in ("sprite", "sprite@2x"):      # one 4x image serves both (pixelRatio 4), as the page's addImage
        (d / f"{name}.png").write_bytes(png)
        (d / f"{name}.json").write_text(index)
    path = d / "style.json"
    path.write_text(json.dumps(style, separators=(",", ":")))
    return path


def _mix(a, b, t):
    """``a`` moved toward ``b`` by ``t`` (0-1), ``"#rrggbb"``: the tunnel look's colour mix, baked for an app with no slider."""
    return "#" + "".join(f"{int(x * (1 - t) + y * t + 0.5):02x}" for x, y in zip(bytes.fromhex(a[1:7]), bytes.fromhex(b[1:7]), strict=True))


def _true_values(col, values):
    """A column read as yes / no from the values a raw OSM or duckOSM column can hold (true, "yes", 1, ...)."""
    return ["in", ["to-string", ["get", col]], ["literal", list(values)]]


def _tag_groups(style, overlays):
    """Each layer's group in its metadata (roadstyle:group): "roads", or the label of its overlay (source or tile layer ov<i>), so an
    app shows each as its own row."""
    labels = [getattr(o, "label", None) or f"overlay {i}" for i, o in enumerate(overlays or [])]
    for lyr in style["layers"]:
        m = re.fullmatch(r"ov(\d+)", lyr.get("source-layer") or lyr.get("source") or "")
        lyr.setdefault("metadata", {})["roadstyle:group"] = labels[int(m.group(1))] if m else "roads"


def export_inline(edges, *, engine: str | None = None, **kwargs) -> dict:
    """The style of ``export_style`` with the data inside (GeoJSON sources, no tiles, no files), for a plugin that makes the map in
    the browser (the roadstyle GeoLibre plugin runs roadstyle in Pyodide). The arrow icon is in the metadata (roadstyle:images), the
    page's popup, tooltip and hover settings in roadstyle:interaction. ``kwargs``: the keywords of ``render_edges``.

    ``engine``: "python" (default) or "rust" (roadstyle's Rust engine, the same style; ``ROADSTYLE_ENGINE`` sets the default)."""
    import base64

    from . import _engine
    if _engine.engine(engine) == "rust":
        return _engine.export_inline(edges, **kwargs)
    from . import _settings
    from .render import render_edges

    kwargs.setdefault("view_3d", True)
    out = render_edges(edges, **{**kwargs, "basemap": "blank", "tiles": False, "backend": "web", "_export": True})
    style = out["style"]
    style["sources"].pop("bm", None)           # the roads only: no background, no base map
    style["layers"] = [lyr for lyr in style["layers"] if lyr["type"] not in ("background", "raster")]
    _tag_groups(style, kwargs.get("overlays"))
    icon = _settings.theme_value("arrows.icon")
    png = files("roadstyle").joinpath("data/sprite.png").read_bytes()
    style.setdefault("metadata", {}).update({
        "roadstyle:interaction": out["interaction"],
        "roadstyle:images": {"oneway": {"url": "data:image/png;base64," + base64.b64encode(png).decode(), "sdf": True, "pixelRatio": icon["pixel_ratio"]}}})
    if out.get("color_options"):     # the legend data for the dashboard module (docs/design/dashboard_module.md, "The legend data")
        style["metadata"]["roadstyle:color_options"] = json.loads(json.dumps(out["color_options"]))   # as JSON: lists, not tuples
    style["center"], style["zoom"] = _camera(out["bounds"])
    style["name"] = kwargs.get("name") or "roads"   # an app shows it (GeoLibre's Layers panel)
    return style


def _plugin_css():
    """static/popup.css for the plugin: each rule only under .rs-plugin, so an app's own popups keep their look."""
    css = re.sub(r"/\*.*?\*/", "", files("roadstyle").joinpath("static/popup.css").read_text(), flags=re.S)
    css = re.sub(r"(^|})\s*([^{}]+?)\s*{", lambda m: m.group(1) + "\n" + ",".join(".rs-plugin " + x.strip() for x in m.group(2).split(",")) + "{", css)
    return css.strip() + "\n"


def export_look(path=None, *, profile=None, palette=None, edges=None, highway_col: str = "highway", oneway_col: str = "oneway",
                tunnel_col: str = "tunnel", bridge_col: str = "bridge", id_col: str = "edge_id", positions=None, engine: str | None = None) -> dict:
    """The simple look for a data layer that another app draws (approach 2 of docs/design/style_export.md): MapLibre layers with no
    source, made from the profile and the palette, that read the raw duckOSM columns: the class colours and widths, a casing, the
    drawing order from ``casing_level`` / ``fill_level`` (one casing and one fill layer per position, in order), tunnels faded with a
    dashed casing, bridges with their casing, the two directions of a two-way road side by side. The GeoLibre plugin puts them on a
    GeoLibre data layer's source. Not in it (they need the full export): casing pieces at the ends, names, arrows, 3D decks.

    ``positions``: the drawing positions to make layers for; else those of ``edges`` (a GeoDataFrame or a GeoParquet path), else -10
    to 10. ``boundary`` in the result is the look of the area's outline (duckOSM's boundary file). Writes the JSON to ``path``
    if given; returns it."""
    from . import _settings, use_settings
    from . import render_web as rw

    prev = list(_settings._EXTRA)
    pick = {k: v for k, v in (("profile", profile), ("palette", palette)) if v is not None}
    from . import _engine
    if _engine.engine(engine) == "rust":     # ``engine``: "python" (default) or "rust" (roadstyle_engine::export_look)
        if positions is None and edges is not None:
            import geopandas as gpd
            g = gpd.read_parquet(edges) if isinstance(edges, (str, Path)) else edges
            lv = [int(v) for c in ("casing_level", "fill_level") if c in g.columns for v in g[c].dropna().unique()]
            positions = range(min(lv, default=0), max(lv, default=0) + 1)
        lk = _engine._look_of({"palette": palette, "profile": profile})
        look = json.loads(_engine.rust().export_look(json.dumps(lk), [highway_col, oneway_col, tunnel_col, bridge_col, id_col],
                                                     [int(p) for p in (positions if positions is not None else range(-10, 11))]))
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(look, separators=(",", ":")))
        return look
    if pick:
        use_settings(*prev, pick)
    try:
        t = _settings.theme()
        pal_name = t["active"]["palette"]
        key = "+".join(pal_name) if isinstance(pal_name, list) else pal_name
        classes = t["palettes"][key]
        cfg = rw.CONFIG
        if positions is None and edges is not None:
            import geopandas as gpd
            g = gpd.read_parquet(edges) if isinstance(edges, (str, Path)) else edges
            lv = [int(v) for c in ("casing_level", "fill_level") if c in g.columns for v in g[c].dropna().unique()]
            positions = range(min(lv, default=0), max(lv, default=0) + 1)
        positions = list(positions if positions is not None else range(-10, 11))
        two = ["!", _true_values(oneway_col, ("true", "yes", "1", "-1"))]
        tun = _true_values(tunnel_col, ("true", "yes", "1", "building_passage", "culvert"))
        bri = _true_values(bridge_col, ("true", "yes", "1", "viaduct", "aqueduct", "boardwalk", "cantilever", "covered", "movable"))
        tw = ["to-boolean", ["get", "__rs_twoway"]]
        fb = t["roads"]["fallback"]

        def by_class(field, f=lambda c: c):
            vals = [x for c, e in classes.items() if e.get(field) for x in (c, f(e[field]))]
            default = f(fb["fill"] if field == "fill" else fb["casing"])
            return ["match", ["get", highway_col], *vals, default] if vals else default
        mix = lambda c: _mix(c, rw._tun_settings()[0], float(cfg.tunnel_strength) / 100) if c and c.startswith("#") else c  # noqa: E731
        fill = ["case", tun, by_class("fill", mix), by_class("fill")]
        pair = cfg.tunnel_palettes.get(cfg.tunnel_palette)
        tun_dash = mix(pair[0] if pair else rw._TUN_TO["dash"])
        casing = ["case", bri, cfg.bridge_casing_color, tun, tun_dash, by_class("casing")]
        no_casing = [c for c, e in classes.items() if not e.get("casing")] + sorted(cfg.minor_no_casing)     # a frozenset: in order, so the look is stable
        fw = rw._swap(rw._width_expr(highway_col), tw, two)
        cw = rw._swap(rw._width_expr(highway_col, casing=True), tw, two)
        bcw = rw._swap(rw._width_expr(highway_col, casing=True, scale=t["bridges"]["wing_scale"]), tw, two)
        cw = rw._by_feature([(bri, bcw)], cw)
        off = ["interpolate", ["linear"], ["zoom"], *[x for z in rw._ZSTOPS for x in (z, ["case", two, rw._offset_match(highway_col, z), 0])]]
        order = ["match", ["get", highway_col], *[x for c in rw._CLASSES for x in (c, rw.class_order(c))], rw._FB["order"]]
        mz = rw._minzoom_filter(highway_col, cfg.minzoom) if cfg.minzoom else None
        lay = {"line-cap": t["roads"]["cap"], "line-join": t["roads"]["join"], "line-sort-key": order}
        layers = []
        for p in sorted(positions):
            at = lambda col, p=p: ["==", ["coalesce", ["get", col], 0], p]  # noqa: E731
            flt = lambda f: ["all", f, mz] if mz else f  # noqa: E731
            layers.append({"id": f"casing-{p}", "type": "line", "metadata": {"roadstyle:position": p},
                           "filter": flt(["all", at("casing_level"), ["!", ["in", ["get", highway_col], ["literal", no_casing]]]]),
                           "layout": lay, "paint": {"line-color": casing, "line-width": cw, "line-offset": off, "line-opacity": t["casing"]["opacity"],
                                                    "line-dasharray": ["case", tun, ["literal", [float(x) for x in cfg.tunnel_casing_dash or [1, 1]]], ["literal", [1, 0]]]}})
            layers.append({"id": f"fill-{p}", "type": "line", "metadata": {"roadstyle:position": p}, "filter": flt(at("fill_level")),
                           "layout": lay, "paint": {"line-color": fill, "line-width": fw, "line-offset": off, "line-opacity": t["roads"]["fill_opacity"]}})
        bd, sel = t["boundary"], t["selection"]
        arw, lbl = t["arrows"], t["labels"]
        minor = ["any", ["!", ["match", ["get", highway_col], rw._MINOR, True, False]]]
        # the one-way arrows and the street names as the page's tiled map draws them (render_web's _arrow_layer and _label_layer:
        # arrows repeated along each one-way road, a name in the middle of its road), on top of the roads
        symbols = [
            {"id": "arrows", "type": "symbol", "minzoom": arw["minzoom"],
             "filter": ["all", ["==", ["get", oneway_col], True], [*minor, [">=", ["zoom"], arw["minor_minzoom"]]], *([mz] if mz else [])],
             "layout": {"symbol-placement": "line", "icon-image": "oneway", "icon-rotation-alignment": "map",
                        "symbol-spacing": ["interpolate", ["linear"], ["zoom"], *[x for zp in arw["spacing"] for x in zp]],
                        "symbol-sort-key": ["*", -1, rw._sort_key(highway_col)],
                        "icon-size": ["interpolate", ["exponential", arw["size"]["base"]], ["zoom"]] + [
                            part for z, base in arw["size"]["stops"]
                            for part in (z, ["*", base, ["match", ["get", highway_col], rw._MINOR, arw["size"]["minor"], 1.0]])]},
             "paint": {"icon-opacity": arw["opacity"], "icon-color": arw["color"]}},
            {"id": "labels", "type": "symbol", "minzoom": lbl["minzoom"],
             "filter": ["all", ["to-boolean", ["get", "name"]], [*minor, [">=", ["zoom"], lbl["minor_minzoom"]]], *([mz] if mz else []),
                        *([] if lbl.get("size") else [rw._label_readable_filter()])],
             "layout": {"symbol-placement": "line-center", "text-field": ["get", "name"], "text-font": lbl["font"],
                        "text-size": rw._label_size_expr(lbl.get("size")), "text-max-angle": lbl["max_angle"], "text-padding": lbl["padding"],
                        "symbol-sort-key": ["*", -1, rw._sort_key(highway_col)]},
             "paint": {"text-color": lbl["color"], "text-opacity": lbl.get("opacity", arw["opacity"]),
                       **({"text-halo-color": lbl["halo_color"], "text-halo-width": lbl["halo_width"]} if lbl["halo_color"] and lbl["halo_width"] else {})}}]
        import base64
        icon = arw["icon"]
        images = {"oneway": {"url": "data:image/png;base64," + base64.b64encode(files("roadstyle").joinpath("data/sprite.png").read_bytes()).decode(),
                             "sdf": True, "pixelRatio": icon["pixel_ratio"]}}
        import inspect
        dflt = inspect.signature(rw.render).parameters          # the page's own defaults: one rule for both
        look = {"name": f"{t['active']['profile']} / {key}", "columns": [highway_col, oneway_col, tunnel_col, bridge_col, "casing_level", "fill_level"],
                "layers": layers, "symbols": symbols, "images": images,
                # the road under the cursor, as on the page's roads-highlight: the plugin sets which id the filter keeps
                "hover": {"id": id_col, "layers": [{"id": "hover", "type": "line", "layout": {k: v for k, v in lay.items() if k != "line-sort-key"},
                                                    "paint": {"line-color": sel["hover"], "line-opacity": sel["opacity"], "line-width": fw, "line-offset": off}}]},
                # the click popup: the page's default fields (render_web.DEFAULT_ROAD_POPUP), the name as its title; a column in
                # only_true shows only when the road is one
                "popup": {"title": "name", "columns": [c for c in rw.DEFAULT_ROAD_POPUP if c != "name"], "only_true": [bridge_col, tunnel_col]},
                # the head length of a casing piece (render's head_m) and the mouse's rest before a road lights up (hover_delay_ms)
                "head_m": float(dflt["head_m"].default), "hover_delay_ms": int(dflt["hover_delay_ms"].default),
                # the area's outline (duckOSM's boundary file), as on roadstyle's page
                "boundary": {"columns": [], "layers": [{"id": "boundary", "type": "line", "paint": {
                    "line-color": bd["color"], "line-width": bd["width"], "line-opacity": bd["opacity"], "line-dasharray": bd["dash"]}}]}}
    finally:
        if pick:
            use_settings(*prev)
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(look, separators=(",", ":")))
    return look

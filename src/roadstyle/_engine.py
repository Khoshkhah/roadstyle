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
    ``format="xyz"`` only (PMTiles in Rust is phase P6)."""
    import gzip  # noqa: F401  (the same imports as export.py)
    from importlib.resources import files
    from pathlib import Path

    from . import _settings
    from .export import _camera, _plugin_css
    from .tiles import _merc, _tile_range

    if format != "xyz":
        raise ValueError("engine='rust': export_style writes format='xyz' only (PMTiles in Rust is phase P6); use engine='python'")
    kwargs = dict(kwargs)
    name = kwargs.get("name") or "roads"
    kwargs.setdefault("view_3d", True)
    kwargs["tiles"] = True                                 # render's tiled look: the roads source draws (no lean mode)
    lk = _look_of(kwargs)
    t = rust().Tiler(_geoparquet(edges), json.dumps(lk), None, name, "", [str(c) for c in edges.columns])   # every column: a click shows the data
    style, base = json.loads(t.style), base_url.rstrip("/")
    bounds = tuple(float(v) for v in edges.total_bounds)
    roads = style["sources"]["roads"]
    roads = style["sources"]["roads"] = {**{k: roads[k] for k in ("type", "minzoom", "maxzoom")}, "tiles": [f"{base}/tiles/{{z}}/{{x}}/{{y}}.pbf"],
                                        "bounds": list(bounds)}
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
    for z in range(int(roads["minzoom"]), int(roads["maxzoom"]) + 1):     # every tile in the roads' bounds; an empty one is an empty file
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

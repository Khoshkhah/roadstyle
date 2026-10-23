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
    palette, profile, settings = kwargs.pop("palette", None), kwargs.pop("profile", None), kwargs.pop("settings", None)
    features = kwargs.pop("features", None)
    kwargs.setdefault("view_3d", True)      # as export_inline
    lk = look(palette=palette, profile=profile, settings=settings, args=kwargs, features=features)
    text = rust().make_style(_geoparquet(edges), json.dumps(lk), None, None, kwargs.get("name"))
    return json.loads(text)

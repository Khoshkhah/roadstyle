"""Where roadstyle's built-in styling *data* lives, and how user overrides layer on top.

The palette tables and the :class:`~roadstyle.config.StyleConfig` / selection constants are no
longer hardcoded in Python — they are JSON data files shipped inside the package
(``roadstyle/data/``). This module is the single place that

  1. reads those **bundled defaults** (``data/palettes/*.json`` + ``data/style.json``), and
  2. discovers and **merges user overrides** on top of them.

Override sources, lowest precedence first (later ones win)::

    1. ``$XDG_CONFIG_HOME/roadstyle/roadstyle.json``  (or ``~/.config/roadstyle/roadstyle.json``)
    2. ``./roadstyle.json``                            (project-local, current working dir)
    3. ``$ROADSTYLE_CONFIG``                           (explicit file path)

An override file is JSON of the form::

    {
      "palettes": {
        "highsat": {"service": {"fill": "#EEEEEE"}},   # partial — merged per road class
        "mytheme": {"roads": {...}}                      # new palette (full class entries)
      },
      "config":    {"fill_opacity": 0.95},
      "selection": {"core": "#FF0000"}
    }

Palette overrides are **deep-merged per road class**, so you can retint a single class
(``service``) without restating the whole palette; ``config``/``selection`` overrides replace
individual keys. This module imports nothing from roadstyle (it returns only plain dicts), so
``palettes.py`` and ``config.py`` can import it without a cycle.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """Filesystem path to the bundled ``roadstyle/data`` directory (shipped as package data)."""
    return Path(__file__).resolve().parent / "data"


def _bundled_palettes() -> dict[str, dict]:
    """``{palette_name: {class: roadstyle_dict}}`` read from ``data/palettes/*.json``.

    Each file is the ``{"name", "roads"}`` form written by :func:`roadstyle.save_palette`
    (a bare ``{class: {...}}`` mapping is also accepted; the file stem is then the name).
    """
    out: dict[str, dict] = {}
    for f in sorted((data_dir() / "palettes").glob("*.json")):
        payload = _read_json(f)
        name = payload.get("name", f.stem)
        out[name] = payload.get("roads", payload)
    return out


def _bundled_style() -> dict:
    """``{"config": {...}, "selection": {...}}`` read from ``data/style.json``."""
    return _read_json(data_dir() / "style.json")


def override_files() -> list[Path]:
    """Existing user-override files, lowest precedence first (later ones win)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    home_cfg = Path(xdg) if xdg else Path.home() / ".config"
    candidates = [home_cfg / "roadstyle" / "roadstyle.json", Path.cwd() / "roadstyle.json"]
    env = os.environ.get("ROADSTYLE_CONFIG")
    if env:
        candidates.append(Path(env))
    return [p for p in candidates if p.is_file()]


def _norm_roads(value):
    """A palette-override value → its ``{class: {...}}`` mapping (accepts a ``roads`` wrapper)."""
    return value.get("roads", value) if isinstance(value, dict) else value


def _merged_overrides() -> dict:
    """Merge every override file into one ``{"palettes", "config", "selection"}`` dict."""
    merged: dict = {"palettes": {}, "config": {}, "selection": {}}
    for path in override_files():
        try:
            data = _read_json(path)
        except (OSError, ValueError):          # unreadable / malformed JSON → skip, don't crash
            continue
        for name, value in (data.get("palettes") or {}).items():
            dst = merged["palettes"].setdefault(name, {})
            for cls, fields in (_norm_roads(value) or {}).items():
                dst.setdefault(cls, {}).update(fields)       # deep-merge per class
        merged["config"].update(data.get("config") or {})
        merged["selection"].update(data.get("selection") or {})
    return merged


@lru_cache(maxsize=1)
def palettes() -> dict[str, dict]:
    """Bundled palettes with user overrides deep-merged per road class.

    Returns ``{name: {class: roadstyle_dict}}`` — raw dicts, ready for ``palette_from_dict``.
    """
    out = {name: {cls: dict(fields) for cls, fields in roads.items()}
           for name, roads in _bundled_palettes().items()}
    for name, roads in _merged_overrides()["palettes"].items():
        dst = out.setdefault(name, {})
        for cls, fields in roads.items():
            dst.setdefault(cls, {}).update(fields)
    return out


@lru_cache(maxsize=1)
def style() -> dict:
    """Bundled ``config`` / ``selection`` with user overrides applied per key."""
    base = _bundled_style()
    ov = _merged_overrides()
    return {
        "config": {**base.get("config", {}), **ov["config"]},
        "selection": {**base.get("selection", {}), **ov["selection"]},
    }


def refresh() -> None:
    """Drop cached data so the next access re-reads the files.

    Call after editing an override file in-process (or from tests that point
    ``$ROADSTYLE_CONFIG`` at a temp file). Note that ``palettes`` / ``config`` already imported
    elsewhere keep their import-time values; ``render_edges(palette=...)`` re-reads ``PALETTES``.
    """
    for fn in (data_dir, palettes, style):
        fn.cache_clear()

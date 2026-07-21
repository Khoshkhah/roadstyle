"""Where roadstyle's built-in styling *data* lives, and how user overrides layer on top.

EVERY styling setting ships in ONE bundled JSON file — ``roadstyle/data/defaults.json`` — with
four sections (same layout as a user override file):

    palettes   per-class colours/widths of each named palette (highsat / carto / mono)
    config     the StyleConfig knobs (opacities, casing, minzoom, labels, arrows, ...)
    selection  the click/hover highlight colours
    roads      the web renderer's road model: ``width`` (px by zoom, per width-group),
               ``width_zoom_rate``, ``casing_ratio``, ``group`` (class -> width-group),
               ``links``, ``zoom_stops``, ``z_order`` (draw priority)

This module is the single place that reads those bundled defaults and **merges user overrides**
on top. A user of the library never edits the package — they create their own file restating
only the parts they want changed. Override sources, lowest precedence first (later ones win)::

    1. ``$XDG_CONFIG_HOME/roadstyle/roadstyle.json``  (or ``~/.config/roadstyle/roadstyle.json``)
    2. ``./roadstyle.json``                            (project-local, current working dir)
    3. ``$ROADSTYLE_CONFIG``                           (explicit file path)

An override file is JSON of the form::

    {
      "palettes": {
        "highsat": {"service": {"fill": "#EEEEEE"}},   # partial — merged per road class
        "mytheme": {"roads": {...}}                      # new palette (full class entries)
      },
      "config":    {"fill_opacity": 0.95, "labels": {"color": "#8899aa"}},
      "selection": {"core": "#FF0000"},
      "roads":     {"z_order": {"service": 5}}           # partial — merged per table entry
    }

Palette overrides are **deep-merged per road class** and ``roads`` tables per entry, so one key
can change without restating its table; ``config``/``selection`` overrides replace individual
keys. This module imports nothing from roadstyle (it returns only plain dicts), so
``palettes.py``, ``config.py`` and ``render_web.py`` can import it without a cycle.
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


@lru_cache(maxsize=1)
def _bundled() -> dict:
    """The whole bundled default set — ``data/defaults.json`` (palettes/config/selection/roads)."""
    return _read_json(data_dir() / "defaults.json")


def _bundled_palettes() -> dict[str, dict]:
    """``{palette_name: {class: roadstyle_dict}}`` from the bundled defaults."""
    return _bundled().get("palettes", {})


def _bundled_style() -> dict:
    """``{"config": {...}, "selection": {...}}`` from the bundled defaults."""
    return _bundled()


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


#: programmatic override sources set via :func:`roadstyle.use_settings` — paths or dicts,
#: applied AFTER the discovered files (highest precedence)
_EXTRA: list = []


def set_extra(*sources) -> None:
    """Replace the programmatic override sources (the :func:`roadstyle.use_settings` backing) and
    drop caches so the next access sees them. ``None`` entries are ignored (reset with no args)."""
    _EXTRA[:] = [s for s in sources if s is not None]
    refresh()


def _merged_overrides() -> dict:
    """Merge every override source into one ``{"palettes", "config", "selection", "roads"}`` dict."""
    merged: dict = {"palettes": {}, "config": {}, "selection": {}, "roads": {}}
    for src in list(override_files()) + list(_EXTRA):
        if isinstance(src, dict):
            data = src
        else:
            try:
                data = _read_json(Path(src))
            except (OSError, ValueError):      # unreadable / malformed JSON → skip, don't crash
                continue
        for name, value in (data.get("palettes") or {}).items():
            dst = merged["palettes"].setdefault(name, {})
            for cls, fields in (_norm_roads(value) or {}).items():
                dst.setdefault(cls, {}).update(fields)       # deep-merge per class
        merged["config"].update(data.get("config") or {})
        merged["selection"].update(data.get("selection") or {})
        for table, value in (data.get("roads") or {}).items():
            if isinstance(value, dict):                      # deep-merge per table entry
                merged["roads"].setdefault(table, {}).update(value)
            else:                                            # lists (links, zoom_stops): replace
                merged["roads"][table] = value
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


@lru_cache(maxsize=1)
def roads() -> dict:
    """The web renderer's road model tables, with user overrides deep-merged per entry.

    Keys: ``width`` (px by zoom, per width-group — zoom keys are strings in JSON, the consumer
    coerces), ``width_zoom_rate``, ``casing_ratio``, ``group``, ``links``, ``zoom_stops``,
    ``z_order``.
    """
    base = _bundled().get("roads", {})
    out = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in base.items()}
    for table, value in _merged_overrides()["roads"].items():
        if isinstance(value, dict) and isinstance(out.get(table), dict):
            for k, v in value.items():                       # per-entry; width rows merge per zoom
                if isinstance(v, dict) and isinstance(out[table].get(k), dict):
                    out[table][k] = {**out[table][k], **v}
                else:
                    out[table][k] = v
        else:
            out[table] = value
    return out


def refresh() -> None:
    """Drop cached data so the next access re-reads the files.

    Call after editing an override file in-process (or from tests that point
    ``$ROADSTYLE_CONFIG`` at a temp file). Note that ``palettes`` / ``config`` already imported
    elsewhere keep their import-time values; ``render_edges(palette=...)`` re-reads ``PALETTES``.
    """
    for fn in (data_dir, _bundled, palettes, style, roads):
        fn.cache_clear()

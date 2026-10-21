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
from functools import cache, lru_cache
from pathlib import Path


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_settings(path: Path) -> dict:
    """A settings file: YAML (``.yaml`` / ``.yml``) or JSON (anything else), a mapping."""
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError("a settings file holds a mapping")
        return data
    return _read_json(path)


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """Filesystem path to the bundled ``roadstyle/data`` directory (shipped as package data)."""
    return Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=1)
def _bundled() -> dict:
    """The bundled settings that are not style values — ``data/defaults.json`` (``config``: base map, camera, slots, tiles)."""
    return _read_json(data_dir() / "defaults.json")


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
    drop caches so the next access sees them. ``None`` entries are ignored (reset with no args).
    A source that cannot be read raises, and the sources are left as they were."""
    old = list(_EXTRA)
    _EXTRA[:] = [s for s in sources if s is not None]
    try:
        refresh()
    except Exception:
        _EXTRA[:] = old
        refresh()
        raise


# The style is a profile and a palette (docs/design/style_config.md): data/profiles/<name>.yaml holds every value that is
# not a color, data/palettes/<name>.yaml every color. A settings source picks them by name ("profile", "palette"); its
# older keys of style values (config, selection, roads, palettes) are read for one release, by this table, with a warning.
_OLD_CONFIG = {           # config key -> theme path
    "fill_opacity": "roads.fill_opacity", "casing_opacity": "casing.opacity", "casing_extra": "casing.extra",
    "link_scale": "roads.links.width", "twin_end_caps": "roads.twin_end_caps", "twin_casing": "roads.twin_casing",
    "tunnel_opacity_scale": "tunnels.opacity_scale", "tunnel_casing_dash": "tunnels.casing_dash", "tunnel_fill_dash": "tunnels.fill_dash",
    "tunnel_fill_dash_color": "tunnels.fill_dash_color", "tunnel_strength": "tunnels.strength", "tunnel_toward": "tunnels.toward",
    "tunnel_towards": "tunnels.towards", "tunnel_palette": "tunnels.palette", "tunnel_palettes": "tunnels.palettes",
    "bridge_casing_color": "bridges.casing_color", "bridge_casing_extra": "bridges.casing_extra", "bridge_casing_m": "bridges.casing_m",
    "bridge_casing_px": "bridges.casing_px", "bridge_shadow": "bridges.shadow.show", "bridge_shadow_color": "bridges.shadow.color",
    "bridge_shadow_blur": "bridges.shadow.blur", "bridge_shadow_offset": "bridges.shadow.offset",
    "bridge_shadow_trim_m": "bridges.shadow.trim_m", "bridge_decks": "bridges.decks",
    "labels": "labels", "arrows": "arrows", "overlays": "overlays",
}
_OLD_CLASS_LISTS = {"minor_no_casing": "no_casing", "single_line_classes": "single_line"}   # config key -> class flag
_OLD_CLASS_TABLES = {"minzoom": "minzoom"}                                                  # config key -> class field
_OLD_ROAD_TABLES = {"group": "group", "z_order": "order"}                                   # roads key -> class field
_OLD_SELECTION = {"core": "select", "glow": "hover", "glow_opacity": "glow_opacity", "casing": "casing"}


def _deep_merge(dst: dict, src: dict) -> dict:
    """Merge ``src`` into ``dst`` key by key: a mapping merges, anything else (a list included) replaces."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _zoom_keys(t: dict) -> dict:
    """The rows of ``roads.width`` keyed by zoom numbers: YAML gives numbers, JSON gives strings ("18"), and one merged row must not
    hold both."""
    rows = (t.get("roads") or {}).get("width")
    if isinstance(rows, dict):
        t["roads"]["width"] = {g: {float(z) if "." in str(z) else int(z): w for z, w in row.items()} if isinstance(row, dict) else row
                               for g, row in rows.items()}
    return t


def _set_path(dst: dict, path: str, value) -> None:
    *head, last = path.split(".")
    for k in head:
        dst = dst.setdefault(k, {})
    if isinstance(value, dict) and isinstance(dst.get(last), dict):
        _deep_merge(dst[last], value)
    else:
        dst[last] = value


_BASE = {"profiles": "default", "palettes": "amber"}      # what an own profile / palette merges over


def _style_dirs(kind: str) -> list[Path]:
    """Where own profiles / palettes are found, first match wins: ./<kind>/ in the working directory, then the user config."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return [Path.cwd() / kind, (Path(xdg) if xdg else Path.home() / ".config") / "roadstyle" / kind]


def style_names(kind: str) -> list[str]:
    """The names of the profiles or palettes (``kind``: ``"profiles"`` / ``"palettes"``): bundled first, then own ones."""
    names = [f.stem for f in sorted((data_dir() / kind).glob("*.yaml"))]
    for d in _style_dirs(kind):
        names += [f.stem for f in sorted(d.glob("*.yaml")) if f.stem not in names] if d.is_dir() else []
    return names


@cache
def _style_file(kind: str, name: str) -> dict:
    """One profile or palette by name, merged over the bundled base (``default`` / ``amber``) unless it is that base itself."""
    import copy
    path = next((d / f"{name}.yaml" for d in _style_dirs(kind) if (d / f"{name}.yaml").is_file()), None)
    bundled = path is None
    path = path or data_dir() / kind / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"no {kind[:-1]} named {name!r}; there are: {', '.join(style_names(kind))}")
    try:
        data = _read_settings(path)
    except Exception as e:      # an error that names the file, never skipped silently
        raise ValueError(f"{kind[:-1]} {name} ({path}): {e}") from e
    if bundled and name == _BASE[kind]:
        return data
    return _deep_merge(copy.deepcopy(_style_file(kind, _BASE[kind])), data)


def _class_entries(colors: dict, classes: dict) -> dict:
    """A palette's road classes as the styler reads them: its colors (fill, casing, opacity) with the profile's widths and dash.
    A class the profile gives no width is left out (it is drawn as a class with no entry)."""
    return {c: {"fill": col["fill"], "width": classes[c]["width"], "casing_width": classes[c]["casing_width"],
                "dash": classes[c].get("dash"), "opacity": col.get("opacity", 1.0), "casing": col.get("casing")}
            for c, col in colors.items() if "width" in classes.get(c, {})}


def _old_style_keys(data: dict) -> dict:
    """The style values of a settings source written in the older layout, as a theme (and a warning that names the new keys)."""
    import warnings
    out: dict = {}
    moved = []
    if data.get("palettes"):
        out["palettes"] = {name: _norm_roads(value) for name, value in data["palettes"].items()}
    for k, v in (data.get("config") or {}).items():
        if k in _OLD_CONFIG:
            _set_path(out, _OLD_CONFIG[k], v)
            moved.append((f"config.{k}", _OLD_CONFIG[k]))
        elif k in _OLD_CLASS_LISTS:
            for cls in v or ():
                _set_path(out, f"roads.classes.{cls}.{_OLD_CLASS_LISTS[k]}", True)
            out.setdefault("_replace_flags", []).append(_OLD_CLASS_LISTS[k])
            moved.append((f"config.{k}", f"roads.classes.<class>.{_OLD_CLASS_LISTS[k]}"))
        elif k in _OLD_CLASS_TABLES:
            for cls, z in (v or {}).items():
                _set_path(out, f"roads.classes.{cls}.{_OLD_CLASS_TABLES[k]}", z)
            moved.append((f"config.{k}", f"roads.classes.<class>.{_OLD_CLASS_TABLES[k]}"))
    for k, v in (data.get("selection") or {}).items():
        _set_path(out, f"selection.{_OLD_SELECTION.get(k, k)}", v)
        moved.append((f"selection.{k}", f"selection.{_OLD_SELECTION.get(k, k)}"))
    for table, value in (data.get("roads") or {}).items():
        if table in _OLD_ROAD_TABLES:
            for cls, x in (value or {}).items():
                _set_path(out, f"roads.classes.{cls}.{_OLD_ROAD_TABLES[table]}", x)
            moved.append((f"roads.{table}", f"roads.classes.<class>.{_OLD_ROAD_TABLES[table]}"))
        elif table == "links" and isinstance(value, list):
            _set_path(out, "roads.links.classes", value)
            moved.append(("roads.links", "roads.links.classes"))
        else:
            _set_path(out, f"roads.{table}", value)
    if moved:
        warnings.warn("roadstyle settings: style values belong in a theme now (docs/design/style_config.md); "
                      + ", ".join(f"{a} -> theme {b}" for a, b in moved), DeprecationWarning, stacklevel=3)
    return out


def _sources() -> list[dict]:
    out = []
    for src in list(override_files()) + list(_EXTRA):
        if isinstance(src, dict):
            out.append(src)
            continue
        try:
            out.append(_read_settings(Path(src)))
        except Exception as e:      # missing, not JSON / YAML, not a mapping: an error that names the file, never skipped silently
            raise ValueError(f"settings file {src}: {e}") from e
    return out


@lru_cache(maxsize=1)
def theme() -> dict:
    """The style in force: the profile and the palette that the settings name (``default`` and ``amber`` when none does), merged,
    with ``palettes``: every palette's road classes at this profile's widths; then each source's style values of the older layout."""
    import copy
    sources = _sources()
    names = {"profiles": _BASE["profiles"], "palettes": _BASE["palettes"]}
    for data in sources:
        for kind in names:
            if data.get(kind[:-1]):
                names[kind] = data[kind[:-1]]
    out = _zoom_keys(copy.deepcopy(_style_file("profiles", names["profiles"])))
    pal = copy.deepcopy(_style_file("palettes", names["palettes"]))
    pal.pop("classes", None)
    _deep_merge(out, pal)
    classes = out["roads"]["classes"]
    out["palettes"] = {n: _class_entries(_style_file("palettes", n).get("classes", {}), classes) for n in style_names("palettes")}
    for data in sources:
        old = _old_style_keys(data)
        for flag in old.pop("_replace_flags", ()):            # an older class list replaces the whole list, as before
            for e in out["roads"]["classes"].values():
                e.pop(flag, None)
        _deep_merge(out, _zoom_keys(old))
    out["active"] = {"profile": names["profiles"], "palette": names["palettes"]}
    return out


def theme_value(path: str):
    """One value of the theme in force, by its dotted path (``"labels.minzoom"``)."""
    v = theme()
    for k in path.split("."):
        v = v[k]
    return v


def _merged_overrides() -> dict:
    """The settings that are not style values: ``config`` keys (base map, camera, slots, tiles, API keys)."""
    merged: dict = {"config": {}}
    old = set(_OLD_CONFIG) | set(_OLD_CLASS_LISTS) | set(_OLD_CLASS_TABLES)
    for data in _sources():
        merged["config"].update({k: v for k, v in (data.get("config") or {}).items() if k not in old})
    return merged


@lru_cache(maxsize=1)
def palettes() -> dict[str, dict]:
    """The theme's palettes: ``{name: {class: roadstyle_dict}}``, raw dicts, ready for ``palette_from_dict``."""
    return {name: {cls: dict(fields) for cls, fields in roads.items()} for name, roads in theme()["palettes"].items()}


def _classes() -> dict:
    return theme()["roads"]["classes"]


@lru_cache(maxsize=1)
def style() -> dict:
    """``config``: the StyleConfig values (from the theme, and the other settings); ``selection``: folium's selection colors."""
    t = theme()
    cfg = {k: theme_value(path) for k, path in _OLD_CONFIG.items()}
    cfg["minor_no_casing"] = [c for c, e in _classes().items() if e.get("no_casing")]
    cfg["single_line_classes"] = [c for c, e in _classes().items() if e.get("single_line")]
    cfg["minzoom"] = {c: e["minzoom"] for c, e in _classes().items() if "minzoom" in e}
    cfg.update(_bundled().get("config", {}))
    cfg.update(_merged_overrides()["config"])
    sel = t["selection"]
    return {"config": cfg, "selection": {old: sel[new] for old, new in _OLD_SELECTION.items()}}


@lru_cache(maxsize=1)
def roads() -> dict:
    """The web renderer's road model tables, from the theme's ``roads``: ``width`` (px by zoom, per width-group; zoom keys may
    be strings, the consumer coerces), ``width_zoom_rate``, ``casing_ratio``, ``group``, ``links``, ``zoom_stops``, ``z_order``."""
    r = theme()["roads"]
    return {"width": r["width"], "width_zoom_rate": r["width_zoom_rate"], "casing_ratio": r["casing_ratio"],
            "group": {c: e["group"] for c, e in r["classes"].items() if "group" in e},
            "links": list(r["links"]["classes"]), "zoom_stops": list(r["zoom_stops"]),
            "z_order": {c: e["order"] for c, e in r["classes"].items() if "order" in e}}


def refresh() -> None:
    """Drop cached data so the next access re-reads the files.

    Call after editing an override file in-process (or from tests that point
    ``$ROADSTYLE_CONFIG`` at a temp file). Note that ``palettes`` / ``config`` already imported
    elsewhere keep their import-time values; ``render_edges(palette=...)`` re-reads ``PALETTES``.
    """
    for fn in (data_dir, _bundled, _style_file, theme, palettes, style, roads):
        fn.cache_clear()

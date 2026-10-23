"""Make the golden looks of tests/look.rs: the look (look.json, src/look.rs) that roadstyle makes for render_edges' palette, profile and
settings, with no base-map part (mapstyle's "features"): each built-in profile x palette, and settings sources in the older and the
newer layout. The roadstyle half of geolibre-roadstyle's look_of (build.py). Run it in the conda environment roadstyle (roadstyle from
this repository's src/), with no roadstyle.json, ./palettes or ./profiles of your own:

    python rust/roadstyle-rs/tests/make_looks.py

It writes tests/data/looks.json.gz: [{"options": {palette, profile, settings}, "look": the look}, ...]."""
import gzip
import json
from pathlib import Path

import roadstyle as rs

DATA = Path(__file__).resolve().parent / "data"

def _json(o):
    """numpy values, sets and tuples that json cannot write (as geolibre-roadstyle's build.py writes the look)."""
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, (set, frozenset, tuple)):
        return sorted(o, key=str) if isinstance(o, (set, frozenset)) else list(o)
    raise TypeError(f"{type(o)} is not JSON")

def py_look(palette="amber", profile=None, settings=None, args=None):
    """The roadstyle half of geolibre-roadstyle's look_of (build.py): the look render_edges(palette=, profile=, settings=) renders with,
    with no base-map part (mapstyle's "features")."""
    import base64
    import dataclasses
    import inspect
    from importlib.resources import files

    from roadstyle import _settings
    from roadstyle import render_web as rw
    from roadstyle.palettes import FALLBACK, PALETTES
    from roadstyle.style import _apply
    from roadstyle.stylers import _dash_str

    active = _settings.theme()["active"]         # render_edges: a profile / palette by name is a settings source after settings=
    pick = {k: v for k, v in (("profile", profile), ("palette", palette)) if v is not None and v != active[k]
            and (k == "profile" or v in _settings.style_names("palettes"))}
    sources = ([settings] if settings is not None else []) + ([pick] if pick else [])
    prev = list(_settings._EXTRA)
    rs.use_settings(*prev, *sources)
    try:
        table = PALETTES[palette]

        def res(st):
            out = []
            for link in (False, True):
                q = _apply(st, link, False, False, rw.CONFIG)
                out.append({"fill": q.fill, "width": q.width, "casing": q.casing, "casing_width": q.casing_width, "dash": _dash_str(q.dash),
                            "opacity": q.opacity, "casing_opacity": q.casing_opacity})
            return out
        styles = {"classes": {c: res(st) for c, st in table.items()}, "fallback": res(table.get(FALLBACK) or next(iter(table.values())))}
        png = files("roadstyle").joinpath("data/sprite.png").read_bytes()
        look = {"palette": palette, "settings": settings, "args": args or {}, "theme": _settings.theme(), "config": dataclasses.asdict(rw.CONFIG),
                "styles": styles, "head_m": inspect.signature(rw.render).parameters["head_m"].default,
                "slots": {"z_order": dict(rw.ROAD_Z), "width_z20": {c: rw.class_width_px(c, 20) for c in rw._CLASSES},
                          "width_z20_fallback": rw.class_width_px(None, 20)},
                "roads_model": _settings.roads(),
                "oneway_image": {"url": "data:image/png;base64," + base64.b64encode(png).decode(), "sdf": True,
                                 "pixelRatio": _settings.theme_value("arrows.icon")["pixel_ratio"]},
                "interaction": {"popup": list(rw.DEFAULT_ROAD_POPUP), "hover_delay_ms": inspect.signature(rw.render).parameters["hover_delay_ms"].default}}
    finally:
        rs.use_settings(*prev)
    return json.loads(json.dumps(look, default=_json))

def write_looks():
    import warnings
    cases = [{"palette": pa, "profile": pr} for pr in ("default", "highsat") for pa in ("amber", "carto", "highsat", "mono")]
    cases += [
        # the older layout (as mapstyle writes it): a palette of its own under "palettes", config and selection keys, a roads table
        {"palette": "mine", "settings": {"palettes": {"mine": {"residential": {"fill": "#123456", "width": 2.5, "casing_width": 3.0, "casing": "#654321"},
                                                               "unclassified": {"fill": "#abcdef", "width": 2, "casing_width": 3, "dash": [4, 2]}}},
                                         "config": {"fill_opacity": 0.8, "minor_no_casing": ["footway"], "minzoom": {"service": 14}, "basemap": "osm"},
                                         "selection": {"core": "#ff0000"}, "roads": {"z_order": {"service": 3}}}},
        # the newer layout: a profile and a palette by name, and a style value
        {"settings": {"profile": "highsat", "palette": "carto", "labels": {"color": "#112233"}}, "palette": "carto"},
    ]
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)     # the older layout's warning
        for c in cases:
            out.append({"options": c, "look": py_look(**c)})
    (DATA / "looks.json.gz").write_bytes(gzip.compress(json.dumps(out, separators=(",", ":")).encode(), 9, mtime=0))
    print(f"looks: {len(out)} cases, {(DATA / 'looks.json.gz').stat().st_size // 1000} KB")

if __name__ == "__main__":
    write_looks()

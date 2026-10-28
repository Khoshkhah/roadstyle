"""The style in config files (docs/design/style_config.md): profiles (no colors) and palettes (only colors), picked by name."""
import io
import json
import re
import tokenize
import warnings
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString

SRC = Path(__file__).resolve().parents[1] / "src" / "roadstyle"
ASSETS = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-assets" / "files"     # the profiles and palettes
COLOR = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?\b|rgba?\(")


def _edges():
    return gpd.GeoDataFrame({"highway": ["primary", "residential", "footway"], "name": ["A", "B", "C"], "bridge": [None, "yes", None]},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.3), (18.0 + i * 1e-3, 59.302)]) for i in range(3)], crs=4326)


def _style(m):
    from road_table import roads_of
    line = next(ln for ln in m.html.splitlines() if ln.startswith("const style = "))
    style = json.JSONDecoder().raw_decode(line[len("const style = "):])[0]
    style["_roads"] = roads_of(m.html)        # the page's road table (a page in simple mode has no roads source)
    return style


def _layer(style, lid):
    return next(lyr for lyr in style["layers"] if lyr["id"] == lid)


@pytest.mark.parametrize("name", ["render_web.py", "style.py", "palettes.py", "colors.py", "stylers.py", "config.py",
                                  "levels.py", "render_lonboard.py", "overlays.py"])
def test_no_color_literal_in_python(name):
    """Python holds no style color: every one is in the theme. ``rgba(0,0,0,0)`` (invisible) is not a color choice."""
    prev, found = None, []
    for tok in tokenize.generate_tokens(io.StringIO((SRC / name).read_text()).readline):
        if tok.type == tokenize.STRING:
            doc = prev is None or prev.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
            if not doc and COLOR.search(tok.string) and "rgba(0,0,0,0)" not in tok.string and len(tok.string) < 400:
                found.append(f"{tok.start[0]}: {tok.string[:60]}")
        if tok.type not in (tokenize.COMMENT, tokenize.NL):
            prev = tok
    assert found == []


def test_default_theme_has_every_section():
    from roadstyle import _settings
    t = _settings.theme()
    for k in ("palettes", "roads", "casing", "labels", "arrows", "bridges", "tunnels", "selection", "data", "overlays", "boundary", "background"):
        assert k in t
    def keys(d):
        for k, v in d.items():
            yield k
            if isinstance(v, dict) and k != "width":         # roads.width rows are keyed by zoom numbers
                yield from keys(v)
    assert all(isinstance(k, str) for k in keys(t))        # YAML 1.1 reads on / off / yes / no keys as true / false


def test_palettes_hold_only_colors_and_profiles_none():
    import yaml
    color_keys = {"fill", "casing", "color", "halo_color", "casing_color", "underlay", "hover", "select", "nodata", "color_table",
                  "circle_stroke", "light", "dark", "toward", "towards", "palettes", "palette", "to", "palette_casing", "fill_dash_color"}

    def keys(d):          # the keys with a plain value (the profile's section "casing" holds casing widths, not a color)
        for k, v in d.items():
            if not isinstance(v, dict) or k in ("towards", "palettes", "to"):
                yield k
            if isinstance(v, dict) and k not in ("towards", "palettes", "to", "width"):
                yield from keys(v)
    for f in (ASSETS / "data" / "profiles").glob("*.yaml"):
        assert not set(keys(yaml.safe_load(f.read_text()))) & color_keys, f.name
    for f in (ASSETS / "data" / "palettes").glob("*.yaml"):
        pal = yaml.safe_load(f.read_text())
        assert all(set(e) <= {"fill", "casing", "opacity"} for e in pal["classes"].values()), f.name
        assert not {"width", "casing_width", "dash", "minzoom", "font"} & set(keys(pal)), f.name


def test_profile_and_palette_by_name_for_one_render(tmp_path, monkeypatch):
    import roadstyle as rs
    monkeypatch.chdir(tmp_path)
    (tmp_path / "palettes").mkdir()
    (tmp_path / "palettes" / "blue.yaml").write_text("# only what changes\nlabels: {color: '#0000ff'}\nbridges: {casing_color: '#abcdef'}\n")
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "late.yaml").write_text("labels: {minzoom: 15.5}\n")
    s = _style(rs.render_edges(_edges(), basemap="blank", palette="blue", profile="late"))
    assert _layer(s, "roads-labels")["paint"]["text-color"] == "#0000ff"          # the palette's colors
    assert "#abcdef" in json.dumps(_layer(s, "roads-simple")["paint"]["line-color"])
    assert _layer(s, "roads-labels")["minzoom"] == 15.5                            # the profile's rules
    s2 = _style(rs.render_edges(_edges(), basemap="blank"))                         # the next render: default and amber again
    assert _layer(s2, "roads-labels")["paint"]["text-color"] == "#5b5b5b" and _layer(s2, "roads-labels")["minzoom"] == 14


def test_unknown_name_is_an_error_that_lists_the_names():
    import roadstyle as rs
    with pytest.raises(ValueError, match="no profile named 'nope'; there are: default, highsat"):
        rs.render_edges(_edges(), basemap="blank", profile="nope")


def test_highsat_profile_gives_highsats_own_widths_and_dashes():
    import roadstyle as rs
    assert rs.PALETTES["highsat"]["cycleway"].dash == (3, 3)                      # palette alone: the default profile
    rs.use_settings({"profile": "highsat"})
    try:
        assert rs.PALETTES["highsat"]["cycleway"].dash == (6, 4) and rs.PALETTES["highsat"]["service"].casing_width == 0.0
    finally:
        rs.use_settings()


def test_older_settings_layout_still_works_and_warns():
    import roadstyle as rs
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        s = _style(rs.render_edges(_edges(), basemap="blank", settings={"config": {"bridge_casing_color": "#abcdef"},
                                                                         "selection": {"core": "#00ff00"}}))
    assert "#abcdef" in json.dumps(_layer(s, "roads-simple")["paint"]["line-color"])
    msg = " ".join(str(x.message) for x in w if issubclass(x.category, DeprecationWarning))
    assert "config.bridge_casing_color -> theme bridges.casing_color" in msg and "selection.core -> theme selection.select" in msg


def test_older_class_list_replaces_the_flags():
    """config.single_line_classes was one list: given in the older layout it replaces every class's single_line flag."""
    import roadstyle as rs
    from roadstyle import _settings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        rs.use_settings({"config": {"single_line_classes": ["service"]}})
        try:
            assert _settings.style()["config"]["single_line_classes"] == ["service"]
            assert rs.config.DEFAULT.single_line_classes == ["service"]
        finally:
            rs.use_settings()
    assert "footway" in _settings.style()["config"]["single_line_classes"]


def test_styleconfig_defaults_come_from_the_theme():
    import roadstyle as rs
    from roadstyle import _settings
    from roadstyle.config import StyleConfig
    assert StyleConfig().bridge_casing_color == _settings.theme_value("bridges.casing_color")
    rs.use_settings({"profile": "highsat"})       # a profile changes widths, not the tunnel look: the default's value stays
    try:
        assert StyleConfig().tunnel_strength == 60 and rs.config.DEFAULT.tunnel_strength == 60
    finally:
        rs.use_settings()



def test_a_view_switches_the_palette_in_the_browser(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    import roadstyle as rs
    path = tmp_path / "views.html"
    rs.render_edges(_edges(), basemap="blank", views={"Day": {"palette": "amber"}, "Night": {"palette": "mono"}}).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && document.getElementById('vw-select')", timeout=30_000)
        swatch = "getComputedStyle(document.querySelector('.flt-sw')).backgroundColor"
        day = page.evaluate(f"[map.getGlobalState().rs_palette, {swatch}]")
        page.evaluate("rsSetView('Night')")
        night = page.evaluate(f"[map.getGlobalState().rs_palette, {swatch}]")
        browser.close()
    assert errors == [] and day[0] == "amber" and night[0] == "mono" and day[1] != night[1]

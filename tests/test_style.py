"""Style resolution, palettes, and filtering."""
import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import (
    PALETTES,
    base_style,
    filter_edges,
    highway_types,
    normalize_highway,
    resolve,
    selection_style,
)


def test_both_palettes_present():
    assert set(PALETTES) == {"highsat", "carto"}
    # key classes exist in both
    for p in PALETTES.values():
        for k in ["motorway", "trunk", "primary", "residential", "service"]:
            assert k in p


def test_highsat_motorway_is_cyan():
    assert base_style("motorway", "highsat").fill == "#00E5FF"


def test_carto_motorway_is_carto_pink():
    assert base_style("motorway", "carto").fill == "#e892a2"


def test_unknown_highway_falls_back():
    assert base_style("teleporter", "highsat").fill == base_style("unclassified", "highsat").fill


def test_links_normalize_and_render_narrower():
    base, is_link = normalize_highway("primary_link")
    assert base == "primary" and is_link
    full = resolve("primary", theme="dark")
    link = resolve("primary_link", theme="dark")
    assert link.width < full.width and link.fill == full.fill


def test_theme_swaps_casing():
    assert resolve("tertiary", theme="light").casing == "#007A3E"
    assert resolve("tertiary", theme="dark").casing == "#000000"
    assert resolve("tertiary", theme="satellite").casing == "#000000"


def test_tunnel_and_bridge_overrides():
    base = resolve("primary", theme="dark")
    tun = resolve("primary", theme="dark", tunnel=True)
    bri = resolve("primary", theme="dark", bridge=True)
    assert tun.opacity < base.opacity and tun.dash is not None
    assert bri.casing == "#000000" and bri.casing_width == base.casing_width + 1.5


def test_selection_style_three_layers():
    s = selection_style("dark", base_width=4.0)
    assert set(s) == {"glow", "casing", "core"}
    assert s["core"]["color"] == "#EE00FF"
    assert s["glow"]["width"] == 12.0


def _edges():
    rows = [("motorway", LineString([(0, 0), (1, 1)])),
            ("residential", LineString([(1, 1), (2, 2)])),
            ("service", LineString([(2, 2), (3, 3)])),
            ("primary_link", LineString([(3, 3), (4, 4)]))]
    return gpd.GeoDataFrame({"highway": [r[0] for r in rows]},
                            geometry=[r[1] for r in rows], crs=4326)


def test_filter_include_exclude():
    g = _edges()
    assert set(filter_edges(g, include=["motorway", "residential"])["highway"]) == {
        "motorway",
        "residential",
    }
    assert "service" not in set(filter_edges(g, exclude="service")["highway"])
    # primary_link matches primary when match_links=True
    assert len(filter_edges(g, include="primary", match_links=True)) == 1
    assert len(filter_edges(g, include="primary", match_links=False)) == 0


def test_highway_types():
    assert set(highway_types(_edges())) == {"motorway", "residential", "service", "primary"}

"""Legends for data-driven maps (categorical swatches + continuous gradient)."""
from functools import partial as _partial

import geopandas as gpd
from shapely.geometry import LineString

from roadstyle import make_legend
from roadstyle import render_edges as _render_edges

# Legends render on the folium/JSON outputs, not the MapLibre "web" backend (now the default);
# pin folium here so these legend tests target the backend that draws them.
render_edges = _partial(_render_edges, backend="folium")


def _edges():
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "primary", "residential", "service"],
         "congestion": ["low", "moderate", "heavy", "severe"],
         "aadt": [25000, 8000, 1500, 100]},
        geometry=[LineString([(i, 0), (i + 1, 1)]) for i in range(4)], crs=4326)


def _html(m):
    return m.get_root().render()


def test_categorical_legend_rendered():
    m = render_edges(_edges(), color_by="congestion",
                     colors={"low": "#11D68F", "moderate": "#FFCF43",
                             "heavy": "#F24E42", "severe": "#A92727"})
    h = _html(m)
    assert "rs-legend" in h
    assert "#11D68F" in h and "low" in h


def test_continuous_legend_rendered():
    m = render_edges(_edges(), color_by="aadt", cmap="viridis")
    h = _html(m)
    assert "rs-legend" in h and "rs-bar" in h
    assert "linear-gradient" in h
    assert "25,000" in h          # vmax tick, formatted


def test_legend_can_be_disabled():
    m = render_edges(_edges(), color_by="aadt", cmap="viridis", legend=False)
    assert "rs-legend" not in _html(m)


def test_classic_path_has_no_datadriven_legend():
    m = render_edges(_edges())
    assert "rs-legend" not in _html(m)


def test_make_legend_specs():
    cat = make_legend({"kind": "categorical", "title": "x",
                       "entries": [("low", "#11D68F")]})
    assert cat is not None
    cont = make_legend({"kind": "continuous", "title": "aadt",
                        "vmin": 0, "vmax": 100, "ramp": ["#000", "#fff"]})
    assert cont is not None
    assert make_legend(None) is None
    assert make_legend({"kind": "categorical", "entries": []}) is None

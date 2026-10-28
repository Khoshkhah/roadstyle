"""render_dashboard(layout=..., toolbar=...): the options add a style and a script; the defaults leave the page as it was."""
import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import LineString  # noqa: E402

import roadstyle as rs  # noqa: E402


def _edges():
    g = gpd.GeoDataFrame({"edge_id": [1, 2], "highway": ["primary", "residential"], "name": ["A", "B"], "oneway": [False, False]},
                         geometry=[LineString([(0, 0), (0.001, 0)]), LineString([(0, 0), (0, 0.001)])], crs="EPSG:4326")
    return g


def test_default_page_is_unchanged():
    html = rs.render_dashboard(_edges()).html
    assert "window.rsLayout" not in html and "rs-toolbar" not in html


def test_overlay_adds_the_layout():
    html = rs.render_dashboard(_edges(), layout="overlay").html
    assert 'window.rsLayout={"layout": "overlay", "toolbar": false}' in html and "html.rs-overlay #map" in html
    assert "rsWindowRecentre = false" in html


@pytest.mark.parametrize("pos", ["right", "left", "top", "bottom"])
def test_toolbar_positions(pos):
    html = rs.render_dashboard(_edges(), toolbar=pos).html
    assert f'"toolbar": "{pos}"' in html and f"#rs-toolbar.rs-tb-{pos}" in html


def test_bad_values_stop():
    with pytest.raises(ValueError):
        rs.render_dashboard(_edges(), layout="float")
    with pytest.raises(ValueError):
        rs.render_dashboard(_edges(), toolbar="middle")

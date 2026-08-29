import os
import pytest
import shapely.geometry as sg
import geopandas as gpd

import roadstyle
from roadstyle.basemaps import (
    Basemap,
    get_api_key,
    get_basemap,
    set_api_key,
    _SESSION_API_KEYS,
)


@pytest.fixture(autouse=True)
def clean_api_keys(monkeypatch):
    """Ensure clean API key state before and after each test."""
    _SESSION_API_KEYS.clear()
    for k in list(os.environ.keys()):
        if "API_KEY" in k or "ACCESS_TOKEN" in k or "ROADSTYLE_" in k:
            monkeypatch.delenv(k, raising=False)
    yield
    _SESSION_API_KEYS.clear()


def _edges():
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "primary"], "name": ["M1", "Main St"]},
        geometry=[sg.LineString([(0, 0), (1, 1)]), sg.LineString([(1, 1), (2, 2)])],
        crs="EPSG:4326",
    )


def test_set_and_get_api_key():
    assert get_api_key("mapbox") is None
    assert get_api_key() is None

    # Set default
    set_api_key("default_token")
    assert get_api_key() == "default_token"
    assert get_api_key("mapbox") == "default_token"

    # Set provider-specific
    set_api_key("mb_token", provider="mapbox")
    assert get_api_key("mapbox") == "mb_token"
    assert get_api_key("stadia") == "default_token"


def test_get_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ROADSTYLE_API_KEY", "env_roadstyle_token")
    assert get_api_key("stadia") == "env_roadstyle_token"

    # Provider-specific env var takes precedence over ROADSTYLE_API_KEY
    monkeypatch.setenv("MAPBOX_API_KEY", "env_mapbox_token")
    assert get_api_key("mapbox") == "env_mapbox_token"
    assert get_api_key("stadia") == "env_roadstyle_token"


def test_carto_basemap_api_key_injection(monkeypatch):
    # Without key: returns standard url
    bm = get_basemap("voyager")
    assert "key=" not in bm.url

    # With explicit key: appends ?key=... for CARTO
    bm_keyed = get_basemap("voyager", api_key="my_carto_key")
    assert "key=my_carto_key" in bm_keyed.url

    # With env var: CARTO_API_KEY
    monkeypatch.setenv("CARTO_API_KEY", "env_carto_key")
    bm_env = get_basemap("voyager")
    assert "key=env_carto_key" in bm_env.url


def test_get_basemap_custom_url_with_placeholder():
    url_template = "https://tiles.example.com/{z}/{x}/{y}.png?api_key={api_key}"
    
    # Without key
    bm = get_basemap(url_template)
    assert bm.url == url_template

    # With explicit key
    bm2 = get_basemap(url_template, api_key="secret123")
    assert bm2.url == "https://tiles.example.com/{z}/{x}/{y}.png?api_key=secret123"

    # With session key
    set_api_key("session_key")
    bm3 = get_basemap(url_template)
    assert bm3.url == "https://tiles.example.com/{z}/{x}/{y}.png?api_key=session_key"


def test_xyzservices_token_required_error():
    try:
        import xyzservices.providers as xyz
    except ImportError:
        pytest.skip("xyzservices not installed")

    # MapBox requires token; calling without any key should raise an informative ValueError
    with pytest.raises(ValueError, match="requires an API key or access token"):
        get_basemap(xyz.MapBox)


def test_xyzservices_with_explicit_api_key():
    try:
        import xyzservices.providers as xyz
    except ImportError:
        pytest.skip("xyzservices not installed")

    bm = get_basemap(xyz.MapBox, api_key="my_mapbox_token")
    assert "access_token=my_mapbox_token" in bm.url
    assert "{accessToken}" not in bm.url

    bm_tf = get_basemap(xyz.Thunderforest.OpenCycleMap, api_key="my_tf_key")
    assert "apikey=my_tf_key" in bm_tf.url
    assert "{apikey}" not in bm_tf.url


def test_xyzservices_with_env_var(monkeypatch):
    try:
        import xyzservices.providers as xyz
    except ImportError:
        pytest.skip("xyzservices not installed")

    monkeypatch.setenv("MAPBOX_API_KEY", "env_tok_123")
    bm = get_basemap(xyz.MapBox)
    assert "access_token=env_tok_123" in bm.url


def test_render_edges_with_api_key():
    try:
        import xyzservices.providers as xyz
    except ImportError:
        pytest.skip("xyzservices not installed")

    g = _edges()

    # Web backend
    wm = roadstyle.render_edges(
        g, backend="web", basemap=xyz.MapBox, api_key="web_test_token"
    )
    assert "access_token=web_test_token" in wm.html

    # Folium backend
    fm = roadstyle.render_edges(
        g, backend="folium", basemap=xyz.MapBox, api_key="folium_test_token"
    )
    assert "access_token=folium_test_token" in fm.get_root().render()


def test_to_spec_with_api_key():
    try:
        import xyzservices.providers as xyz
    except ImportError:
        pytest.skip("xyzservices not installed")

    g = _edges()
    spec = roadstyle.to_spec(g, basemap=xyz.MapBox, api_key="spec_test_token")
    assert "access_token=spec_test_token" in spec["basemap"]["url"]

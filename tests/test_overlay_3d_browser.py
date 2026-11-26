"""An overlay of polygons with height_col is the page's own 3D buildings (noise-map, 2026-11-26: the blocks of its noise model, a building and its
parts): a fill-extrusion layer that the toolbox's buildings button shows, with the height and the base of each feature. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402


def _blocks():
    """A building of two blocks (a body of 16 m and a tower of 46 m on it) and a second building with no base."""
    import geopandas as gpd
    from shapely.geometry import box
    return gpd.GeoDataFrame({"BLOCK_PK": [1, 2, 3], "HEIGHT_M": [16.0, 46.0, 9.0], "BASE_M": [None, 16.0, None]},
                            geometry=[box(18.0, 59.301, 18.002, 59.302), box(18.0005, 59.3013, 18.001, 59.3017), box(18.003, 59.301, 18.004, 59.302)], crs=4326)


def test_an_overlay_with_height_col_is_the_pages_3d_buildings(tmp_path):
    path = tmp_path / "b.html"
    rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(_blocks(), label="Blocks", height_col="HEIGHT_M", base_col="BASE_M",
                                                                        popup=["BLOCK_PK", "HEIGHT_M"])]).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            layer = page.evaluate("map.getStyle().layers.find(l => l.type === 'fill-extrusion')")
            assert layer["id"] == "ov0-3d" and layer["paint"]["fill-extrusion-height"] == ["get", "HEIGHT_M"], layer
            assert layer["paint"]["fill-extrusion-base"] == ["coalesce", ["get", "BASE_M"], 0] and layer["layout"]["visibility"] == "none"
            assert page.evaluate("RS_OVERLAYS.find(o => o.label === 'Blocks').extrude") == "ov0-3d"
            page.evaluate("document.querySelector('[data-rs-tool=\"buildings\"] button, button[data-rs-tool=\"buildings\"]').click()")    # the buildings button
            page.wait_for_function("map.getLayoutProperty('ov0-3d', 'visibility') === 'visible'", timeout=10_000)
            assert page.evaluate("rsGetBuildings3D()") is True
            page.evaluate("map.jumpTo({center: [18.001, 59.3015], zoom: 17, pitch: 60})")
            page.wait_for_function("map.areTilesLoaded() && !map.isMoving()", timeout=20_000)
            heights = page.evaluate("map.queryRenderedFeatures({layers: ['ov0-3d']}).map(f => [f.properties.HEIGHT_M, f.properties.BASE_M ?? null])")
            assert sorted(set(map(tuple, heights))) == [(9.0, None), (16.0, None), (46.0, 16.0)], heights      # the tiles keep the height and the base
            page.evaluate("rsSetOverlay('Blocks', false)")                                                        # the Layers box hides them in 3D too
            page.wait_for_function("map.getLayoutProperty('ov0-3d', 'visibility') === 'none'", timeout=10_000)
        finally:
            browser.close()
    assert errors == []


def test_a_3d_overlay_needs_polygons_and_a_height_in_each_feature():
    import geopandas as gpd
    from shapely.geometry import LineString
    lines = gpd.GeoDataFrame({"h": [3.0]}, geometry=[LineString([(18.0, 59.3), (18.001, 59.301)])], crs=4326)
    with pytest.raises(ValueError, match="needs polygons"):
        rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(lines, height_col="h")])
    blocks = _blocks()
    blocks.loc[2, "HEIGHT_M"] = None
    with pytest.raises(ValueError, match="1 of 3 features have no height"):
        rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(blocks, height_col="HEIGHT_M")])

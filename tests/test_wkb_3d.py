"""Audit N19: a road whose line has a Z (LineString Z, as many files have it) draws as its 2D line in the Rust engine, as in Python: the
one WKB reader (roadstyle-model's wkb.rs) leaves out a Z or an M. Monaco's roads of the Rust goldens, with a height of 5 m on every point."""
from pathlib import Path

import pytest

import roadstyle as rs

ROADS = Path(__file__).resolve().parents[1] / "rust/roadstyle-rs/tests/data/monaco/roads.parquet"
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")


def test_a_3d_line_draws_as_its_2d_line():
    import geopandas as gpd
    import pandas as pd
    import shapely

    df = pd.read_parquet(ROADS)                 # the goldens' file has no `geo` metadata: its geometry is WKB in EPSG:4326
    flat = gpd.GeoDataFrame(df, geometry=gpd.GeoSeries.from_wkb(df["geometry"]), crs=4326)
    tall = flat.set_geometry(shapely.force_3d(flat.geometry.values, 5.0))
    assert tall.geometry.has_z.all() and not flat.geometry.has_z.any()
    assert rs.export_inline(tall, engine="rust") == rs.export_inline(flat, engine="rust")

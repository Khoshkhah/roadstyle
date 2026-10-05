"""Unit tests for roadstyle v2 Domain Adapters (GMNS and OSM)."""

import pandas as pd
from pathlib import Path
import pytest
from shapely.geometry import LineString, Point

import roadstyle.v2 as rs
from roadstyle.v2.adapters.gmns import GMNSAdapter, GMNSNetwork
from roadstyle.v2.adapters.osm import OSMAdapter
from roadstyle.v2.engine.compiler import WebMap


def test_gmns_adapter_from_dataframes():
    # 1. Links
    links_df = pd.DataFrame(
        {
            "link_id": [101, 102],
            "geometry": ["LINESTRING (0 0, 100 0)", "LINESTRING (100 0, 100 100)"],
            "lanes": [2, 1],
            "bridge": [False, True],
            "junction": ["none", "roundabout"],
        }
    )

    # 2. Lanes (Child lanes for link 101)
    lanes_df = pd.DataFrame(
        {
            "lane_id": ["101_1", "101_2"],
            "link_id": [101, 101],
            "width_m": [3.5, 3.5],
            "mode": ["driving", "bus"],
            "connector": [False, False],
            "geometry": ["LINESTRING (0 -1.75, 100 -1.75)", "LINESTRING (0 1.75, 100 1.75)"],
        }
    )

    # 3. Movements
    movements_df = pd.DataFrame(
        {
            "movement_id": ["m1"],
            "from_link": [101],
            "to_link": [102],
            "movement_type": ["turn-left"],
            "geometry": ["POINT (95 0)"],
        }
    )

    net = GMNSAdapter.from_dataframes(links=links_df, lanes=lanes_df, movements=movements_df)
    assert isinstance(net, GMNSNetwork)
    assert len(net.corridors) == 2
    assert len(net.channels) == 2
    assert len(net.glyphs) == 1

    # Link 101 has child lanes -> corridor is hollow container (fill_visible=False)
    c101 = next(c for c in net.corridors if c.id == 101)
    assert c101.fill_visible is False
    assert c101.width_m == 7.0

    # Link 102 has no child lanes -> corridor is filled (fill_visible=True), bridge=1, priority=100
    c102 = next(c for c in net.corridors if c.id == 102)
    assert c102.fill_visible is True
    assert c102.band == 1
    assert c102.junction_priority == 100.0

    # Lane 101_2 is bus mode -> cyan-blue color
    bus_lane = next(ch for ch in net.channels if ch.id == "101_2")
    assert bus_lane.fill_color == "#0284c7"

    # Movement glyph
    assert net.glyphs[0].symbol == "turn-left"

    # Preset attachment & compilation
    net.add_preset("Volume Bandwidth", width_mode="flow", width_by="volume")
    m = net.compile()
    assert isinstance(m, WebMap)
    assert "network" in m.to_dict()["sources"]


def test_gmns_adapter_from_csv(tmp_path: Path):
    links_file = tmp_path / "link.csv"
    lanes_file = tmp_path / "lane.csv"

    links_file.write_text(
        'link_id,geometry,lanes\n'
        '1,"LINESTRING (10 10, 20 20)",2\n',
        encoding="utf-8",
    )
    lanes_file.write_text(
        'lane_id,link_id,geometry,width_m\n'
        '1_1,1,"LINESTRING (10 10, 20 20)",3.5\n',
        encoding="utf-8",
    )

    net = GMNSAdapter.from_csv(tmp_path)
    assert len(net.corridors) == 1
    assert len(net.channels) == 1


def test_osm_adapter_from_dataframe():
    df = pd.DataFrame(
        {
            "osm_id": [1001, 1002, 1003],
            "highway": ["motorway", "primary", "residential"],
            "lanes": [4, 3, 2],
            "bridge": ["yes", None, None],
            "junction": [None, "roundabout", None],
            "geometry": [
                LineString([(0, 0), (100, 0)]),
                LineString([(100, 0), (200, 0)]),
                LineString([(200, 0), (300, 0)]),
            ],
        }
    )

    corridors = OSMAdapter.from_dataframe(df)
    assert len(corridors) == 3

    # Motorway: width=14, band=1, casing_left=0.4
    m_cor = corridors[0]
    assert m_cor.width_m == 14.0
    assert m_cor.band == 1
    assert m_cor.casing_left_m == 0.40
    assert m_cor.fill_color == "#e11d48"
    assert m_cor.split_start == 15.0
    assert m_cor.split_end == 15.0

    # Primary roundabout: priority=100
    p_cor = corridors[1]
    assert p_cor.junction_priority == 100.0

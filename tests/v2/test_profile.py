import json

import pytest
from shapely.geometry import LineString

from roadstyle.v2.adapters.osm import OSMAdapter
from roadstyle.v2.profile import bundled_profiles, load_profile


def _service(**extra):
    return [{"highway": "service", "lanes": 1, "geometry": LineString([(0, 0), (50, 0)]), **extra}]


def test_default_profile_keeps_lane_width():
    assert OSMAdapter.from_dataframe(_service())[0].width_m == 3.5


def test_bundled_compact_profile_narrows_service_lane():
    assert "compact" in bundled_profiles()
    assert OSMAdapter.from_dataframe(_service(), profile="compact")[0].width_m == 3.0


def test_profile_file_overrides_only_what_it_states(tmp_path):
    path = tmp_path / "mine.json"
    path.write_text(json.dumps({
        "lane_width_m": 3.0,
        "casing_m": {"service": [0.1, 0.3]},
        "colors": {"service": "#123456"},
        "roundabout_priority": 50,
    }))
    corridor = OSMAdapter.from_dataframe(_service(junction="roundabout"), profile=path)[0]
    assert corridor.width_m == 3.0
    assert (corridor.casing_left_m, corridor.casing_right_m) == (0.1, 0.3)
    assert corridor.fill_color == "#123456"
    assert corridor.junction_priority == 50.0
    assert load_profile(path).color("primary") == load_profile().color("primary")


def test_width_sources_order_and_width_tag():
    rows = _service(width="2.4 m")
    assert OSMAdapter.from_dataframe(rows)[0].width_m == 2.4
    assert OSMAdapter.from_dataframe(rows, profile={"width_sources": ["class"]})[0].width_m == 4.5


def test_bad_profiles_fail_clearly():
    with pytest.raises(FileNotFoundError):
        load_profile("nope")
    with pytest.raises(ValueError):
        load_profile({"width_sources": ["lanez"]})

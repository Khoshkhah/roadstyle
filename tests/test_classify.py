"""rs.classify: where to cut the numbers into classes and which colour each class gets."""
import numpy as np
import pytest

import roadstyle as rs


def test_natural_breaks_follow_the_gap_in_the_data():
    x = [1, 2, 2, 3, 3, 4, 50, 51, 52, 53, 100, 101, 102]
    assert rs.natural_breaks(x, 3) == [50.0, 100.0]


def test_quantile_classes_have_the_same_size_and_equal_classes_the_same_width():
    x = np.arange(100.0)
    q = rs.classify(x, "quantile", k=4)
    assert [q.labels.count(l) for l in q.colors] == [25, 25, 25, 25]
    e = rs.classify(x, "equal", k=4)
    assert np.allclose(np.diff(e.breaks), np.diff(e.breaks)[0])


def test_a_pivot_is_a_cut_and_a_missing_value_has_its_own_grey_class():
    x = np.array([0.1, 0.3, 0.5, 0.7, 0.79, 0.81, 0.9, 0.95, np.nan])
    c = rs.classify(x, "natural", k=4, pivot=0.8, palette="rdylgn", fmt="{:.0%}")
    assert 0.8 in c.breaks
    assert c.labels[-1] == "not counted" and c.colors["not counted"] == "#e2e8f0" and list(c.colors)[0] == "not counted"
    assert c.labels[5] != c.labels[4]                      # 0.79 and 0.81 are on two sides of the promise
    assert c.option("cov")["color_by"] == "cov" and set(c.option("cov")["colors"]) == set(c.colors)


def test_fixed_needs_its_breaks_and_a_ramp_has_k_colours():
    with pytest.raises(ValueError):
        rs.classify([1, 2, 3], "fixed")
    with pytest.raises(ValueError):
        rs.classify([1, 2, 3], "nope")
    assert len(rs.ramp("viridis", 7)) == 7 and rs.ramp("blues", 1) == ["#deebf7"]
    c = rs.classify([1, 2, 3, 4], "fixed", breaks=[2.5])
    assert c.labels == ["under 2.5", "under 2.5", "2.5+", "2.5+"]

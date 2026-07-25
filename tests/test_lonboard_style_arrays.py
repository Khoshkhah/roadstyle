"""The vectorised lonboard style arrays must be exactly what the per-row loops produced.

`_arrays` now resolves once per distinct (highway, tunnel, bridge) key and broadcasts;
`_arrays_from_frame` caches the hex→RGBA conversion. Neither is allowed to change a single
byte of output, so both are compared against verbatim copies of the old per-row loops.
"""
import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

from roadstyle.render_lonboard import _arrays, _arrays_from_frame, _hex_to_rgb, _truthy
from roadstyle.style import resolve

HIGHWAYS = [
    "motorway", "motorway_link", "trunk", "primary", "primary_link", "secondary",
    "tertiary", "residential", "living_street", "service", "unclassified", "pedestrian",
    "footway", "cycleway", "path", "steps", "track", "construction", "no_such_class", None,
]


def _fixture_gdf():
    """Every highway class × plain / bridge / tunnel / both — 80 rows."""
    rows = []
    for hw in HIGHWAYS:
        for tunnel, bridge in ((None, None), (None, "yes"), ("yes", None), ("yes", "yes")):
            rows.append({"highway": hw, "tunnel": tunnel, "bridge": bridge})
    g = gpd.GeoDataFrame(rows, geometry=[LineString([(0, i), (1, i)]) for i in range(len(rows))],
                         crs=4326)
    return g


# ---- verbatim pre-vectorisation reference implementations ---------------------------------
def _arrays_ref(gdf, palette, highway_col, tunnel_col, bridge_col, which):
    colors, widths = [], []
    for _, row in gdf.iterrows():
        rs = resolve(
            row.get(highway_col), palette=palette,
            tunnel=_truthy(row.get(tunnel_col)) if tunnel_col else False,
            bridge=_truthy(row.get(bridge_col)) if bridge_col else False,
        )
        if which == "casing":
            if rs.casing is None or rs.casing_width <= 0:
                colors.append([0, 0, 0, 0])
                widths.append(0.0)
            else:
                colors.append(_hex_to_rgb(rs.casing, int(255 * rs.casing_opacity)))
                widths.append(rs.casing_width)
        else:
            colors.append(_hex_to_rgb(rs.fill, int(255 * rs.opacity)))
            widths.append(rs.width)
    return np.array(colors, dtype="uint8"), np.array(widths, dtype="float32")


def _arrays_from_frame_ref(rf, which):
    colors, widths = [], []
    for i in range(len(rf)):
        if which == "casing":
            casing = rf.casing[i]
            if not casing or rf.casing_width[i] <= 0:
                colors.append([0, 0, 0, 0])
                widths.append(0.0)
            else:
                colors.append(_hex_to_rgb(casing, int(255 * rf.casing_opacity[i])))
                widths.append(rf.casing_width[i])
        else:
            colors.append(_hex_to_rgb(rf.fill[i], int(255 * rf.opacity[i])))
            widths.append(rf.width[i])
    return np.array(colors, dtype="uint8"), np.array(widths, dtype="float32")


# ---- classic path --------------------------------------------------------------------------
@pytest.mark.parametrize("palette", ["highsat", "carto", "mono"])
@pytest.mark.parametrize("which", ["casing", "fill"])
def test_arrays_match_per_row_reference(palette, which):
    g = _fixture_gdf()
    ref_c, ref_w = _arrays_ref(g, palette, "highway", "tunnel", "bridge", which)
    new_c, new_w = _arrays(g, palette, "highway", "tunnel", "bridge", which)
    np.testing.assert_array_equal(new_c, ref_c)
    np.testing.assert_array_equal(new_w, ref_w)


def test_arrays_missing_optional_columns():
    """No tunnel/bridge columns passed — the render() pre-nulled path."""
    g = _fixture_gdf().drop(columns=["tunnel", "bridge"])
    for which in ("casing", "fill"):
        ref = _arrays_ref(g, "highsat", "highway", None, None, which)
        new = _arrays(g, "highsat", "highway", None, None, which)
        np.testing.assert_array_equal(new[0], ref[0])
        np.testing.assert_array_equal(new[1], ref[1])


# ---- data-driven (ResolvedFrame) path -------------------------------------------------------
class _FakeFrame:
    """Duck-typed ResolvedFrame: only what _arrays_from_frame reads."""

    def __init__(self, n):
        rng = np.random.default_rng(7)
        hexes = [f"#{v:06x}" for v in rng.integers(0, 0xFFFFFF, n)]
        self.fill = hexes
        self.opacity = [round(o, 2) for o in rng.uniform(0.2, 1.0, n)]
        self.width = list(rng.uniform(0.5, 8.0, n).astype("float32"))
        # every third edge has no casing; every fifth a zero casing width
        self.casing = [None if i % 3 == 0 else h for i, h in enumerate(hexes)]
        self.casing_width = [0.0 if i % 5 == 0 else 2.0 for i in range(n)]
        self.casing_opacity = [1.0] * n

    def __len__(self):
        return len(self.fill)


@pytest.mark.parametrize("which", ["casing", "fill"])
def test_arrays_from_frame_match_reference(which):
    rf = _FakeFrame(200)
    ref_c, ref_w = _arrays_from_frame_ref(rf, which)
    new_c, new_w = _arrays_from_frame(rf, which)
    np.testing.assert_array_equal(new_c, ref_c)
    np.testing.assert_array_equal(new_w, ref_w)


def test_empty_frame():
    g = _fixture_gdf().iloc[0:0]
    c, w = _arrays(g, "highsat", "highway", "tunnel", "bridge", "fill")
    assert len(c) == 0 and len(w) == 0

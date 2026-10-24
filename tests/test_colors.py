"""The colour ramps (colors.py) read data/cmaps.json, the one file of both engines: they give the colours of the old branca and
matplotlib ramps, to 1/255, for every name of the file (269 branca schemes, 180 matplotlib colormaps) and for lists of colours."""
import pytest

from roadstyle.colors import ColorRamp, _cmaps

bcm = pytest.importorskip("branca.colormap")

AT = [i / 20 for i in range(21)]       # 0, 0.05, ..., 1: the stops and the points between them


def rgb(h):
    return [int(h[k:k + 2], 16) for k in (1, 3, 5)]


def near(ours, theirs, what):
    for x, a, b in zip(AT, ours, theirs, strict=True):
        assert all(abs(p - q) <= 1 for p, q in zip(rgb(a), rgb(b), strict=True)), f"{what} at {x}: {a} against branca's {b}"


def branca_linear(cmap):
    """colors.py's _branca_linear before 2026-10-24: branca's scheme (exact, then by case or prefix), else matplotlib at 9 stops."""
    name, lower = str(cmap), str(cmap).lower()
    scheme = getattr(bcm.linear, name, None)
    if scheme is not None:
        return scheme.scale(0.0, 1.0)
    for n in [n for n in dir(bcm.linear) if not n.startswith("_")]:
        if n.lower() == lower or n.lower().startswith(lower + "_"):
            return getattr(bcm.linear, n).scale(0.0, 1.0)
    import matplotlib
    from matplotlib import colors as mcolors
    return bcm.LinearColormap([mcolors.to_hex(matplotlib.colormaps[name](i / 8.0)) for i in range(9)], vmin=0.0, vmax=1.0)


def test_every_ramp_is_the_old_one():
    pytest.importorskip("matplotlib")
    c = _cmaps()
    assert len(c["branca"]) == len([n for n in dir(bcm.linear) if not n.startswith("_")])
    for n in sorted(set(c["branca"]) | set(c["matplotlib"])):
        theirs = branca_linear(n)
        near([ColorRamp(n)._base.rgb_hex_str(x) for x in AT], [theirs.rgb_hex_str(x) for x in AT], n)


def test_a_name_is_found_as_branca_finds_it():
    # case-insensitive, then the first name in sorted order with the prefix "<name>_" (colors.py's rule, as before)
    assert ColorRamp("ylorrd").stops(3) == ColorRamp("YlOrRd_03").stops(3)
    with pytest.raises(ValueError, match="unknown cmap 'no such ramp'"):
        ColorRamp("no such ramp")


def test_a_list_of_colours_and_a_colour_name():
    for stops in (["#000000", "white"], ["red", "#00ff00", (0.0, 0.0, 1.0)], list(_cmaps()["css"])):
        theirs = bcm.LinearColormap(stops, vmin=0.0, vmax=1.0)
        near([ColorRamp(stops)._base.rgb_hex_str(x) for x in AT], [theirs.rgb_hex_str(x) for x in AT], str(stops)[:40])
    with pytest.raises(ValueError, match="Unknown color 'nocolour'"):
        ColorRamp(["#000000", "nocolour"])
    with pytest.raises(ValueError, match="at least 2 colors"):
        ColorRamp(["#000000"])

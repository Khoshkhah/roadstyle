"""Colour-mapping helpers: the colour ramps and (optionally, with ``mapclassify``) the class breaks.

The ramps are data, one file for both engines (``data/cmaps.json``): branca's 269 named ramps (viridis, magma, YlOrRd, …) and its
colour names, and the matplotlib colormaps at 9 stops. A ramp interpolates as branca's LinearColormap does. ``mapclassify`` (optional,
the ``[numeric]`` extra) provides statistical class breaks (quantiles, equal interval, natural breaks). This module turns a user's
``cmap=``/``scheme=`` request into concrete per-edge hex colours.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from functools import lru_cache

from . import _assets


@lru_cache(maxsize=1)
def _cmaps() -> dict:
    """The ramps' data (data/cmaps.json, the same file as the Rust engine's): branca's schemes and colour names, and each matplotlib
    colormap at 9 stops (made from branca and matplotlib by rust/roadstyle-rs/tests/make_goldens.py)."""
    return json.loads(_assets.text("data/cmaps.json"))


def _parse_color(x):
    """branca's _parse_color: an RGB(A) tuple of floats (0 to 1), "#rrggbb" or a colour name; as RGBA floats."""
    if isinstance(x, (tuple, list)):
        return tuple(tuple(x) + (1.0,))[:4]
    if isinstance(x, str):
        h = x if x.startswith("#") and len(x) == 7 else _cmaps()["css"].get(x.lower())
        if h is not None:
            return tuple(int(h[k:k + 2], 16) / 255.0 for k in (1, 3, 5)) + (1.0,)
    raise ValueError(f"Unknown color {x!r}.")


class _Linear:
    """branca's LinearColormap over [0, 1]: the colours at even steps, interpolated in RGBA."""

    def __init__(self, colors):
        if len(colors) < 2:
            raise ValueError("You must provide at least 2 colors.")
        self.colors = [_parse_color(c) for c in colors]
        n = len(colors)
        self.index = [i * 1.0 / (n - 1) for i in range(n)]

    def rgb_hex_str(self, x: float) -> str:
        ix, cs = self.index, self.colors
        if x <= ix[0]:
            c = cs[0]
        elif x >= ix[-1]:
            c = cs[-1]
        else:
            i = len([u for u in ix if u < x])
            p = (x - ix[i - 1]) * 1.0 / (ix[i] - ix[i - 1]) if ix[i - 1] < ix[i] else 1.0
            c = tuple((1.0 - p) * cs[i - 1][j] + p * cs[i][j] for j in range(4))
        return "#" + "".join(f"{int(u * 255.9999):02x}" for u in c[:3])


def _linear(cmap) -> _Linear:
    """The ramp of a name or a list of stops: a branca scheme (exact, then the first name in sorted order that is the same ignoring case
    or starts with "<name>_"), else a matplotlib colormap (9 stops); or a list of colours (hex, a colour name or an RGB tuple)."""
    if isinstance(cmap, (list, tuple)):
        return _Linear(list(cmap))
    name, c = str(cmap), _cmaps()
    lower = name.lower()
    found = c["branca"].get(name) or next((c["branca"][n] for n in sorted(c["branca"])
                                           if n.lower() == lower or n.lower().startswith(lower + "_")), None) or c["matplotlib"].get(name)
    if found is None:
        raise ValueError(f"unknown cmap {cmap!r}; use a branca scheme name (e.g. 'viridis', 'YlOrRd'), a list of hex colour stops, "
                         "or a matplotlib colormap name")
    return _Linear(found)


class ColorRamp:
    """A continuous value→hex mapper over ``[vmin, vmax]`` on a ramp of data/cmaps.json (branca's LinearColormap).

    Also exposes the ordered hex ``stops`` so a legend (or a web frontend) can draw the gradient.
    """

    def __init__(self, cmap="viridis", vmin: float = 0.0, vmax: float = 1.0):
        self.cmap_name = cmap if isinstance(cmap, str) else "custom"
        self.vmin = float(vmin)
        self.vmax = float(vmax)
        self._base = _linear(cmap)               # normalised 0..1
        self._span = (self.vmax - self.vmin) or 1.0

    def __call__(self, value, *, nan_color: str = None) -> str:
        if nan_color is None:                    # the theme's data.nodata (docs/design/style_config.md)
            from . import _settings
            nan_color = _settings.theme_value("data.nodata")
        if value is None:
            return nan_color
        try:
            v = float(value)
        except (TypeError, ValueError):
            return nan_color
        if v != v:                                # NaN
            return nan_color
        t = (v - self.vmin) / self._span
        t = 0.0 if t < 0 else 1.0 if t > 1 else t
        return self._base.rgb_hex_str(t)

    def stops(self, n: int = 9) -> list[str]:
        """``n`` evenly spaced hex colours across the ramp (for a gradient legend)."""
        if n < 2:
            n = 2
        return [self._base.rgb_hex_str(i / (n - 1)) for i in range(n)]


def classify(values: Sequence[float], scheme: str = "quantiles", k: int = 5):
    """Return upper-bin edges for ``values`` using a ``mapclassify`` scheme.

    Falls back to equal-interval (computed here) if ``mapclassify`` is not installed.
    Supported scheme names map to mapclassify: ``quantiles``, ``equal_interval``,
    ``fisher_jenks``/``natural_breaks``, ``std_mean``.
    """
    import numpy as np

    arr = np.asarray([v for v in values if v is not None], dtype="float64")
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return []

    try:
        import mapclassify as mc

        name = scheme.lower()
        cls_map = {
            "quantiles": mc.Quantiles,
            "equal_interval": mc.EqualInterval,
            "fisher_jenks": mc.FisherJenks,
            "natural_breaks": mc.NaturalBreaks,
            "std_mean": mc.StdMean,
        }
        klass = cls_map.get(name, mc.Quantiles)
        return [float(b) for b in klass(arr, k=k).bins]
    except Exception:
        # equal-interval fallback (no mapclassify): k evenly spaced edges
        lo, hi = float(arr.min()), float(arr.max())
        if hi == lo:
            return [hi]
        step = (hi - lo) / k
        return [lo + step * (i + 1) for i in range(k)]

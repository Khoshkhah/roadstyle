"""Colour-mapping helpers — a thin adapter over ``branca`` (and optionally ``mapclassify``).

We do **not** reinvent colormaps. ``branca`` (which ships with folium) provides 269 named colour
ramps (viridis, magma, YlOrRd, …) plus continuous interpolation; ``mapclassify`` (optional, the
``[numeric]`` extra) provides statistical class breaks (quantiles, equal interval, natural breaks).
This module just turns a user's ``cmap=``/``scheme=`` request into concrete per-edge hex colours.
"""
from __future__ import annotations

from typing import Sequence


def _branca_linear(cmap):
    """Return a branca ``LinearColormap`` (vmin=0, vmax=1) for a name or list of stops.

    ``cmap`` may be a branca scheme name (``"viridis"``), a matplotlib colormap name, or an
    explicit list of hex stops (``["#000", "#fff"]``).
    """
    import branca.colormap as bcm

    if isinstance(cmap, (list, tuple)):
        return bcm.LinearColormap([*cmap], vmin=0.0, vmax=1.0)

    name = str(cmap)
    # 1. exact branca scheme (e.g. "viridis", "YlOrRd_09")
    scheme = getattr(bcm.linear, name, None)
    if scheme is not None:
        return scheme.scale(0.0, 1.0)
    # 2. case-insensitive / prefix match among branca's 269 schemes (e.g. "ylorrd" -> a YlOrRd_*)
    lower = name.lower()
    candidates = [n for n in dir(bcm.linear) if not n.startswith("_")]
    for n in candidates:
        if n.lower() == lower or n.lower().startswith(lower + "_"):
            return getattr(bcm.linear, n).scale(0.0, 1.0)
    # 3. matplotlib fallback (the [numeric] extra) — sample the colormap into stops
    try:
        import matplotlib
        from matplotlib import colors as mcolors

        mpl_cmap = matplotlib.colormaps[name]
        stops = [mcolors.to_hex(mpl_cmap(i / 8.0)) for i in range(9)]
        return bcm.LinearColormap(stops, vmin=0.0, vmax=1.0)
    except Exception:
        pass
    raise ValueError(
        f"unknown cmap {cmap!r}; use a branca scheme name (e.g. 'viridis', 'YlOrRd'), "
        "a list of hex colour stops, or install the [numeric] extra for matplotlib colormaps"
    )


class ColorRamp:
    """A continuous value→hex mapper over ``[vmin, vmax]`` backed by a branca colormap.

    Also exposes the ordered hex ``stops`` so a legend (or a web frontend) can draw the gradient.
    """

    def __init__(self, cmap="viridis", vmin: float = 0.0, vmax: float = 1.0):
        self.cmap_name = cmap if isinstance(cmap, str) else "custom"
        self.vmin = float(vmin)
        self.vmax = float(vmax)
        self._base = _branca_linear(cmap)        # normalised 0..1
        self._span = (self.vmax - self.vmin) or 1.0

    def __call__(self, value, *, nan_color: str = "#cccccc") -> str:
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

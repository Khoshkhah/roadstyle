"""Discrete colour classes for roads, from data: where to cut the numbers, and which colour each class gets.

    cls = rs.classify(gdf["coverage"], method="natural", k=5, pivot=0.8, palette="rdylgn", fmt="{:.0%}")
    gdf["cov_class"] = cls.labels
    rs.render_dashboard(gdf, color_options={"Coverage": cls.option("cov_class")})

Methods: `natural` (Fisher-Jenks: the cuts fall in the gaps of the data, so the classes have different widths and sizes), `quantile` (the same
number of roads in each class), `equal` (the same width), `fixed` (the cuts are `breaks`). A `pivot` is always one of the cuts (the promised 80 %,
zero): the nearest cut moves to it. A missing value (NaN) gets its own grey class, `missing_label`.
"""
from __future__ import annotations

import numpy as np

# anchor colours of the ramps, low to high; a ramp of k classes is read from them (light and dark themes both read these: they are mid-tone)
PALETTES = {
    "blues": ["#deebf7", "#9ecae1", "#3182bd", "#08519c"],
    "viridis": ["#fde725", "#5ec962", "#21918c", "#3b528b", "#440154"],
    "heat": ["#ffffb2", "#fecc5c", "#fd8d3c", "#e31a1c", "#800026"],
    "rdylgn": ["#b91c1c", "#e2673b", "#f6b64b", "#a3c957", "#15803d"],         # a diverging one: bad to good
}
_MAXP = 800


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def ramp(palette, k):
    """`k` colours (hex), evenly along the anchors of `palette` (a name of PALETTES or a list of hex colours)."""
    anchors = PALETTES[palette] if isinstance(palette, str) else list(palette)
    pts = np.array([_hex(c) for c in anchors], float)
    t = np.linspace(0, len(pts) - 1, k) if k > 1 else np.array([0.0])
    out = []
    for x in t:
        i = min(int(x), len(pts) - 2); f = x - i
        out.append("#%02x%02x%02x" % tuple(int(round(v)) for v in pts[i] * (1 - f) + pts[i + 1] * f))
    return out


def natural_breaks(values, k):
    """The `k - 1` cut points of Fisher-Jenks natural breaks: the smallest value of each class after the first."""
    x = np.sort(np.asarray(values, float)); x = x[np.isfinite(x)]
    u, w = np.unique(x, return_counts=True)
    if len(u) > _MAXP:                                  # merge into groups of about the same size, as the JavaScript `rs.naturalBreaks` does
        g = np.array_split(np.arange(len(x)), _MAXP)
        lo = np.array([x[i[0]] for i in g]); w = np.array([len(i) for i in g], float); u = np.array([x[i].mean() for i in g])
    else:
        lo = u
    n = len(u)
    if k >= n:
        return [float(v) for v in lo[1:]]
    w = w.astype(float)
    s0, s1, s2 = (np.concatenate([[0], np.cumsum(a)]) for a in (w, w * u, w * u * u))
    def cost(i, j):                                     # the spread of points i..j (j included), for every i at once
        c0 = s0[j + 1] - s0[i]; c1 = s1[j + 1] - s1[i]
        return (s2[j + 1] - s2[i]) - c1 * c1 / c0
    dp = np.full((k, n), np.inf); back = np.zeros((k, n), int)
    dp[0] = [cost(np.array([0]), j)[0] for j in range(n)]
    for c in range(1, k):
        for j in range(c, n):
            i = np.arange(c, j + 1)
            t = dp[c - 1][i - 1] + cost(i, j)
            m = int(np.argmin(t)); dp[c, j] = t[m]; back[c, j] = i[m]
    cuts, j = [], n - 1
    for c in range(k - 1, 0, -1):
        i = back[c, j]; cuts.append(float(lo[i])); j = i - 1
    return cuts[::-1]


class Classes:
    """The result: `labels` (one per value), `breaks`, `colors` (label -> hex, in class order) and `option(column)`."""

    def __init__(self, labels, breaks, colors):
        self.labels, self.breaks, self.colors = labels, breaks, colors

    def option(self, column):
        """The entry for `color_options`: colour the roads by the class labels that you put in `column`."""
        return {"color_by": column, "colors": dict(self.colors)}


def classify(values, method="natural", k=5, *, breaks=None, pivot=None, palette="viridis", reverse=False, fmt="{:g}",
             missing_label="not counted", missing_color="#e2e8f0"):
    v = np.asarray(values, float)
    ok = np.isfinite(v)
    if method == "fixed":
        if breaks is None:
            raise ValueError("classify: method 'fixed' needs `breaks`")
        cuts = sorted(float(b) for b in breaks)
    elif method == "natural":
        cuts = natural_breaks(v[ok], k)
    elif method == "quantile":
        cuts = sorted(set(float(c) for c in np.quantile(v[ok], np.linspace(0, 1, k + 1)[1:-1])))
    elif method == "equal":
        lo, hi = float(v[ok].min()), float(v[ok].max()); cuts = [lo + (hi - lo) * i / k for i in range(1, k)]
    else:
        raise ValueError(f"classify: unknown method {method!r} (natural, quantile, equal, fixed)")
    if pivot is not None and cuts and v[ok].min() < pivot <= v[ok].max():
        cuts[int(np.argmin([abs(c - pivot) for c in cuts]))] = float(pivot)
        cuts = sorted(set(cuts))
    n = len(cuts) + 1
    f = fmt.format
    names = [f"under {f(cuts[0])}"] + [f"{f(cuts[i - 1])} - {f(cuts[i])}" for i in range(1, n - 1)] + [f"{f(cuts[-1])}+"] if cuts else ["all"]
    cols = ramp(palette, n)
    if reverse:
        cols = cols[::-1]
    idx = np.searchsorted(cuts, v, side="right")
    labels = [names[i] if good else missing_label for i, good in zip(idx, ok)]
    colors = dict(zip(names, cols))
    if not ok.all():
        colors = {missing_label: missing_color, **colors}
    return Classes(labels, cuts, colors)

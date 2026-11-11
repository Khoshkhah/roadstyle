"""Makes docs/img/bridge-height/profile.png, the figure of "How the height of a 3D bridge is calculated" (docs/guides/bridge-height.md): the deck of
one straight bridge of four lengths, as the Rust engine makes it with the default look. Run it again after a change of the height rules:

    python docs/img/bridge-height/make.py

Each deck piece has its start and end lift (`__rs_lift0`, `__rs_lift1`) and its place along the bridge (`__rs_s0`, `__rs_s1`); the underside of the deck
is the group height `__rs_full` times the lift. The page makes the deck thin out to nothing at the ground: the top is `thickness_m` x min(1, 2 x lift) above the underside."""
import json
import math
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import LineString

import roadstyle as rs

HERE = Path(__file__).resolve().parent
LENGTHS = (40, 120, 330, 800)           # metres: a short, a medium, a long and a very long bridge
LAT = 43.74


def deck_pieces(length_m):
    """The deck pieces of one straight bridge of `length_m` metres (a road of the class primary, level 1), in order along it."""
    dlon = length_m / (111320 * math.cos(math.radians(LAT)))
    g = gpd.GeoDataFrame({"highway": ["primary"], "bridge": ["yes"], "layer": ["1"], "edge_id": [1]},
                         geometry=[LineString([(7.42, LAT), (7.42 + dlon, LAT)])], crs=4326)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        html = rs.render_edges(g, backend="web", view_3d=True).html
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + len("const style = "))[0]
    feats = [f["properties"] for f in style["sources"]["decks"]["data"]["features"] if not f["properties"].get("__rs_casing_slab")]
    return sorted(feats, key=lambda p: p["__rs_s0"])


def main():
    fig, axes = plt.subplots(2, len(LENGTHS), figsize=(12.5, 6.2), gridspec_kw={"height_ratios": [3, 1.6]})
    steepest = []
    for col, length in enumerate(LENGTHS):
        ax, ax2 = axes[0][col], axes[1][col]
        pieces = deck_pieces(length)
        full, thick = pieces[0]["__rs_full"], pieces[0]["__rs_thick"]
        xs, under, top = [], [], []
        for p in pieces:
            for s, lift in ((p["__rs_s0"], p["__rs_lift0"]), (p["__rs_s1"], p["__rs_lift1"])):
                xs.append(s * length)
                under.append(full * lift)
                top.append(full * lift + thick * min(1.0, 2.0 * lift))
        ax.fill_between(xs, under, top, color="#f28c28", linewidth=0)
        ax.plot(xs, top, color="#9a4f00", linewidth=1.2)
        ax.axhline(0, color="#64748b", linewidth=1.5)
        ax.axhline(full, color="#64748b", linewidth=0.8, linestyle=(0, (4, 3)))
        peak = max(under)
        ax.set_title(f"{length} m long\ngroup height {full:.1f} m" + ("" if peak > full - 0.05 else f"\nthe deck reaches {peak:.1f} m"), fontsize=10)
        ax.set_xlim(0, length)
        ax.set_ylim(-1, 25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8)
        # the true slope in percent, from the underside of the deck
        grid = np.arange(0, length + 0.25, 0.5)
        z = np.interp(grid, xs, under)
        slope = np.abs(np.gradient(z, grid)) * 100
        steepest.append(float(slope.max()))
        ax2.fill_between(grid, slope, color="#64748b", alpha=0.35, linewidth=0)
        ax2.plot(grid, slope, color="#475569", linewidth=1.0)
        ax2.set_xlim(0, length)
        ax2.set_ylim(0, 25)
        ax2.spines[["top", "right"]].set_visible(False)
        ax2.tick_params(labelsize=8)
        ax2.set_xlabel("metres along the bridge", fontsize=9)
        ax2.text(0.97, 0.9, f"steepest {slope.max():.1f} %", transform=ax2.transAxes, ha="right", va="top", fontsize=8)
    axes[0][0].set_ylabel("metres above the ground", fontsize=9)
    axes[1][0].set_ylabel("slope, in percent", fontsize=9)
    fig.tight_layout()
    for col, length in enumerate(LENGTHS):               # how much larger the vertical scale is than the horizontal scale, in each picture
        pos = axes[0][col].get_position()
        exaggeration = (length / (pos.width * 12.5)) / (26 / (pos.height * 6.2))
        axes[0][col].set_xlabel(f"the vertical scale is {exaggeration:.0f} times larger", fontsize=8, color="#9a4f00")
    fig.savefig(HERE / "profile.png", dpi=130)
    print("wrote", HERE / "profile.png", "| steepest slopes:", [round(v, 1) for v in steepest])


if __name__ == "__main__":
    main()

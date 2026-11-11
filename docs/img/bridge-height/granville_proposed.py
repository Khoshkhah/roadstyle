"""The prototype of the proposed edit step (docs/design/bridge_profile_edit.md), on the Granville Bridge: what the engine's profile would be with measured heights as input,
for each chain, next to the profile that the engine makes today and the LiDAR heights (docs/samples/bridge-profile/granville_lidar_samples.json). It is a prototype in Python of the changed formulas of step 5
and of the height line of stage 2. It is not the engine. Run it again after a change of the proposal:

    python docs/img/bridge-height/granville_proposed.py

Stage 1 input for a chain: the height at its two end nodes (`deck_m`) and its top (`top_m`). Stage 2 input: the height line of the chain (`points`)."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parents[1] / "samples" / "bridge-profile"
sys.path.insert(0, str(HERE))
from granville import chains_of  # noqa: E402
from granville_vs_lidar import matched  # noqa: E402

GRADE = 8.0          # metres of ramp for 1 m of height: ramp_m / base_m


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lift_of(x, ell, ramp, lift_head, lift_tail):
    """Step 5 of the guide: the lift at the distance x along a chain, with the node lifts of its two ends and its full ramp."""
    a, b = lift_head + x / ramp, lift_tail + (ell - x) / ramp
    cross = (ell + ramp * (lift_tail - lift_head)) / 2
    k = clamp(2 * min(cross, ell - cross) / ramp, 0, 0.4)
    if k > 0:
        h = max(k - abs(a - b), 0) / k
        t = min(a, b) - h * h * k / 4
    else:
        t = min(a, b)
    t = clamp(t, 0, 1)
    return t * t * (3 - 2 * t)


def stage1(x, ell, z_head, z_tail, top):
    """The proposed formulas: the chain's own top P (`top_m`) in place of the group height H, and the heights at the two end nodes (`deck_m`) in place of the node lifts."""
    ramp = top * GRADE
    return top * lift_of(x, ell, ramp, z_head / top, z_tail / top)


def stage2(x, points):
    """The height line of the chain (`points`: [s, z] in order of s), straight between the points."""
    s, z = zip(*points, strict=True)
    return float(np.interp(x, s, z))


def compute():
    """For each chain (numbered from the longest): its stage 1 input (the heights at its two ends and its top), the largest error of the profile of today, of stage 1 and of stage 2
    against the LiDAR stations of the chain, and the four lines of the figure."""
    chains = chains_of(gpd.read_parquet(SAMPLES / "granville_bridge_edges.parquet"))
    lidar = json.loads((SAMPLES / "granville_lidar_samples.json").read_text())
    full = chains[0]["pieces"][0]["properties"]["__rs_full"]
    rows = []
    for c, axis, _ in matched(chains, lidar):
        ell = c["length"]
        s_all, z_all = (np.array(v) for v in zip(*axis["samples"], strict=True))
        inside = s_all <= ell
        xs, zs = s_all[inside], z_all[inside]
        z_head, z_tail, top = float(np.interp(0, s_all, z_all)), float(np.interp(ell, s_all, z_all)), float(zs.max())
        props = [f["properties"] for f in c["pieces"]]
        today = np.interp(xs, [p["__rs_s0"] * ell for p in props], [full * p["__rs_lift0"] for p in props])
        one = np.array([stage1(float(x), ell, z_head, z_tail, top) for x in xs])
        line = [(s, z) for s, z in axis["points"] if s <= ell] + [(ell, z_tail)]
        two = np.array([stage2(float(x), line) for x in xs])
        errors = [float(np.abs(v - zs).max()) for v in (today, one, two)]
        rows.append({"length": ell, "inputs": (z_head, z_tail, top), "errors": errors, "lines": (xs, zs, today, one, two)})
    return rows


def main():
    rows = compute()
    print("| Chain | Input of stage 1: ends, top | Largest error today | Largest error, stage 1 | Largest error, stage 2 |\n|---|---|---|---|---|")
    fig, axes = plt.subplots(3, 4, figsize=(12.5, 7.6), sharey=True)
    for n, (r, ax) in enumerate(zip(rows, axes.flat, strict=False), 1):
        xs, zs, today, one, two = r["lines"]
        z_head, z_tail, top = r["inputs"]
        e = r["errors"]
        print(f"| {n} | {z_head:.1f} m, {z_tail:.1f} m, {top:.1f} m | {e[0]:.1f} m | {e[1]:.1f} m | {e[2]:.1f} m |")
        ax.plot(xs, zs, color="#2563eb", linewidth=2.2, label="LiDAR")
        ax.plot(xs, today, color="#f28c28", linewidth=1.4, label="engine today")
        ax.plot(xs, one, color="#16a34a", linewidth=1.4, linestyle=(0, (5, 2)), label="stage 1")
        ax.plot(xs, two, color="#7c3aed", linewidth=1.2, linestyle=(0, (1, 1.5)), label="stage 2")
        ax.axhline(0, color="#64748b", linewidth=1.0)
        ax.set_title(f"Chain {n}: {r['length']:.0f} m", fontsize=9)
        ax.set_xlim(0, r["length"])
        ax.set_ylim(-1, 42)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8)
        if n > 8:
            ax.set_xlabel("metres along the chain", fontsize=8)
        if n % 4 == 1:
            ax.set_ylabel("metres above the ground", fontsize=8)
    axes.flat[0].legend(fontsize=7, loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(HERE / "granville_proposed.png", dpi=120)


if __name__ == "__main__":
    main()

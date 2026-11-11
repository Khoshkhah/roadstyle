"""The prototype of the design rules for the height of a bridge (docs/design/bridge_height_design.md). It calculates, from road design rules and not from fitted data: the stopping
sight distance and the vertical curve constants K for a design speed, the vertical profile of a bridge (ramps at a design grade, parabolic vertical curves, a flat top) for a height
that the clearance needs, and the length that the clearance needs. It is a prototype in Python, not the engine. Run it again after a change of the rules:

    python docs/img/bridge-height/design_rules.py

The rules (the sources are in the note): L = K x A for a vertical curve (A is the change of grade in percent); K from the stopping sight distance S: crest K = S^2 / 658,
sag K = S^2 / (120 + 3.5 S) (S in metres); S = 0.278 V t + V^2 / (254 (a / 9.81)) on level ground (V in km/h, t = 2.5 s, a = 3.4 m/s^2); the least curve length is 0.6 V metres."""
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REACTION_S = 2.5          # perception-reaction time of the AASHTO stopping sight distance
DECEL_MS2 = 3.4           # the deceleration of the AASHTO stopping sight distance


def stopping_sight_distance(v_kmh):
    """S in metres on level ground."""
    return 0.278 * v_kmh * REACTION_S + v_kmh**2 / (254 * (DECEL_MS2 / 9.81))


def k_values(v_kmh):
    """(crest K, sag K) in metres of curve for each percent of change of grade."""
    s = stopping_sight_distance(v_kmh)
    return s**2 / 658, s**2 / (120 + 3.5 * s)


def curve_length(v_kmh, change_percent, crest):
    """The length of a vertical curve for a change of grade of `change_percent`: K x A, and at least 0.6 V."""
    k = k_values(v_kmh)[0 if crest else 1]
    return max(k * change_percent, 0.6 * v_kmh)


def vertical_profile(pvis, curves, step=0.5):
    """The deck height z(x) through the points of vertical intersection `pvis` ([x, z]), with a parabolic vertical curve of `curves[i]` metres at each point. Returns x and z arrays."""
    xs = np.arange(pvis[0][0], pvis[-1][0] + step / 2, step)
    p = np.array(pvis, dtype=float)
    grades = np.diff(p[:, 1]) / np.diff(p[:, 0])
    z = np.empty_like(xs)
    for n, x in enumerate(xs):
        i = int(np.searchsorted(p[:, 0], x, side="right")) - 1          # the segment of x
        i = min(max(i, 0), len(grades) - 1)
        for j in (i, i + 1):                                            # a curve at the start or at the end of the segment can hold x
            if 0 < j < len(p) - 1 and curves[j] > 0 and abs(x - p[j, 0]) <= curves[j] / 2:
                u = x - (p[j, 0] - curves[j] / 2)
                z[n] = p[j, 1] - grades[j - 1] * curves[j] / 2 + grades[j - 1] * u + (grades[j] - grades[j - 1]) / (2 * curves[j]) * u * u
                break
        else:
            z[n] = p[i, 1] + grades[i] * (x - p[i, 0])
    return xs, z


def design_profile(ell, top, grade, v_kmh):
    """The profile of a bridge chain of `ell` metres with its two ends on the ground, with a deck that must reach the height `top`, at the design `grade` (0.05 = 5 %) and the design speed
    `v_kmh`. The ramp rises at `grade` from a sag curve on the ground. If the chain is long enough (2 ramps and one crest curve), the deck stays level at `top` after a crest curve.
    If it is not, the two ramps meet at one crest, and the deck reaches `top` only when the chain is long enough for that crest. Returns x, z, the highest point of the deck, and the lengths of the curves."""
    cf = curve_length(v_kmh, grade * 100, crest=False)                  # the sag curve at the foot of a ramp: the grade goes from 0 to `grade`
    ct = curve_length(v_kmh, grade * 100, crest=True)                   # the crest curve at the top of a ramp: the grade goes from `grade` to 0
    x_top = cf / 2 + top / grade                                        # where the tangent of the ramp reaches `top`
    if ell - 2 * x_top >= ct:                                           # a flat part needs the length of one crest curve, or the two crest curves overlap
        pvis = [(0, 0), (cf / 2, 0), (x_top, top), (ell - x_top, top), (ell - cf / 2, 0), (ell, 0)]
        curves = [0, cf, ct, ct, cf, 0]
    else:
        cm = curve_length(v_kmh, 2 * grade * 100, crest=True)           # one crest: the grade goes from +grade to -grade
        pvis = [(0, 0), (cf / 2, 0), (ell / 2, grade * (ell / 2 - cf / 2)), (ell - cf / 2, 0), (ell, 0)]
        curves = [0, cf, cm, cf, 0]
    xs, z = vertical_profile(pvis, curves)
    return xs, z, float(z.max()), curves


def minimum_length(top, grade, v_kmh):
    """The shortest chain with both ends on the ground that reaches `top` (the two ramps meet at the top, with the crest curve): found by search."""
    lo, hi = 1.0, 20000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if design_profile(mid, top, grade, v_kmh)[2] >= top - 0.005:
            hi = mid
        else:
            lo = mid
    return hi


def smoothstep_profile(ell, height, ramp_per_metre=8.0, step=0.5):
    """The deck of today's engine for a chain of `ell` metres with both ends on the ground: the formulas of step 5 of the guide, with the crest rounding of the engine."""
    xs = np.arange(0, ell + step / 2, step)
    r = height * ramp_per_metre
    a, b = xs / r, (ell - xs) / r
    cross = ell / 2
    k = float(np.clip(2 * min(cross, ell - cross) / r, 0, 0.4))
    h = np.maximum(k - np.abs(a - b), 0) / k if k > 0 else 0 * a
    t = np.clip(np.minimum(a, b) - h * h * k / 4, 0, 1)
    return xs, height * t * t * (3 - 2 * t)


def main():
    print("| Design speed | Stopping sight distance | K, crest | K, sag | Least curve length |\n|---|---|---|---|---|")
    for v in (30, 40, 50, 60, 70, 80, 100):
        kc, ks = k_values(v)
        print(f"| {v} km/h | {stopping_sight_distance(v):.0f} m | {kc:.1f} | {ks:.1f} | {0.6 * v:.0f} m |")

    print("\n| Height | Grade 4 % | Grade 5 % | Grade 6 % | Grade 8 % |\n|---|---|---|---|---|")
    for h in (5.8, 10, 20):
        print(f"| {h} m | " + " | ".join(f"{h / g:.0f} m" for g in (0.04, 0.05, 0.06, 0.08)) + " |")

    # the example: a bridge over a road. Clearance 5.0 m (16 ft and 6 in for a new surface), span 20 m, depth of the structure span / 25 (at least 0.8 m).
    span, clearance = 20.0, 5.0
    top = clearance + max(0.8, span / 25)
    v, grade = 50, 0.05
    print(f"\nexample: over a road of {span:.0f} m: top {top:.1f} m, design speed {v} km/h, grade {grade:.0%}")
    need = minimum_length(top, grade, v)
    print(f"  the shortest chain that reaches {top:.1f} m at {grade:.0%}: {need:.0f} m")
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.4))
    for ax, (ell, height, g) in zip(axes, ((300.0, top, 0.05), (200.0, top, 0.05), (1200.0, 19.8, 0.04)), strict=True):
        xs, z, apex, curves = design_profile(ell, height, g, v)
        ex, ez = smoothstep_profile(ell, 5 + 17 * min(max((ell - 60) / 540, 0), 1))
        slope = np.abs(np.gradient(z, xs)).max() * 100
        today_slope = np.abs(np.gradient(ez, ex)).max() * 100
        ax.fill_between(xs, z, z + 1.0, color="#f28c28", linewidth=0)
        ax.plot(ex, ez, color="#64748b", linewidth=1.3, linestyle=(0, (4, 2)), label=f"today (the length rule): steepest {today_slope:.0f} %")
        ax.axhline(height, color="#2563eb", linewidth=0.8, linestyle=(0, (1, 2)))
        ax.axhline(0, color="#64748b", linewidth=1.0)
        ax.set_title(f"{ell:.0f} m long, needs {height:.1f} m at {g:.0%}\nreaches {apex:.1f} m, steepest {slope:.1f} %", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(fontsize=7, loc="lower center", bbox_to_anchor=(0.5, -0.42), frameon=False)
        print(f"  {ell:.0f} m (needs {height:.1f} m, grade {g:.0%}): the deck reaches {apex:.2f} m, steepest {slope:.2f} %, curves {[round(c) for c in curves]}; today's engine: {today_slope:.1f} %")
    axes[0].set_ylabel("metres above the ground", fontsize=8)
    fig.tight_layout()
    for ax, ell in zip(axes, (300.0, 200.0, 1200.0), strict=True):          # how much larger the vertical scale is than the horizontal scale
        pos, (low, high) = ax.get_position(), ax.get_ylim()
        exaggeration = (ell / (pos.width * 12.5)) / ((high - low) / (pos.height * 4.4))
        ax.set_xlabel(f"metres along the bridge (the vertical scale is {exaggeration:.0f} times larger)", fontsize=8)
    fig.savefig(HERE / "design_rules.png", dpi=120)


if __name__ == "__main__":
    main()

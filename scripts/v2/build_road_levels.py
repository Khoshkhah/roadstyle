"""Build the original pair table and the solved level table for the driving map.

The original pairs are discovered from the DuckOSM driving edges with 15 m heads (the head
length of ``docs/v2/monaco_roads_v2.html``). The level table is solved from those pairs plus
the user-owned overrides CSV, which is read and never written.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_duckosm_solver_input import load_duckosm_corridors  # noqa: E402

from roadstyle.v2.engine.pairs import (  # noqa: E402
    discover_pair_table,
    read_pair_table,
    write_pair_table,
)
from roadstyle.v2.engine.compiler import compile_map  # noqa: E402
from roadstyle.v2.engine.pairs import merge_pair_overrides  # noqa: E402
from roadstyle.v2.engine.solver import solve_stacking, write_level_table  # noqa: E402

DEFAULT_DATABASE = ROOT.parent / "duckOSM" / "monaco.duckdb"
DEFAULT_DIR = ROOT / "data" / "v2"


def load_driving_corridors(database: Path, head_m: float, profile: Any = None) -> list[Any]:
    import duckdb

    with duckdb.connect(str(database), read_only=True) as connection:
        connection.execute("LOAD spatial")
        corridors, _ = load_duckosm_corridors(
            connection, only_modes=("driving",), plain_refs=True, profile=profile
        )
    for corridor in corridors:
        corridor.split_start = corridor.split_end = head_m
    return corridors


def build(
    corridors: list[Any],
    original: Path,
    overrides: Path,
    levels: Path,
    *,
    band_dist: float = 10.0,
    head_m: float = 15.0,
) -> None:
    """Write ``original`` (rediscovered) and ``levels`` (original + overrides)."""
    original_rows = discover_pair_table(corridors, band_dist=band_dist)
    original.parent.mkdir(parents=True, exist_ok=True)
    write_pair_table(original, original_rows)
    override_rows = read_pair_table(overrides, overrides=True) if overrides.exists() else []
    solution = solve_stacking(
        corridors,
        pair_table=original_rows,
        pair_overrides=override_rows,
        band_dist=band_dist,
        head_m=head_m,
        priority_tiers=True,
    )
    write_level_table(corridors, solution, levels)


_LEVEL_KEYS = {"_type", "part", "level", "casing_start", "casing_level", "casing_end", "fill_level", "band"}
_CASING_KEYS = ("casing_m", "casing_left_m", "casing_right_m", "casing_color")


def _style_by_edge(base_features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Visual properties of each road in the original map, so a re-solve keeps its look."""
    styles: dict[str, dict[str, Any]] = {}
    for feature in base_features:
        props = feature.get("properties", {})
        ref = props.get("edge_ref")
        if not ref:
            continue
        style = styles.setdefault(str(ref), {})
        if props.get("_type") == "corridor_fill":
            style.update({k: v for k, v in props.items() if k not in _LEVEL_KEYS})
        else:
            style.update({k: props[k] for k in _CASING_KEYS if k in props})
    return styles


class RoadLevelModel:
    """Solve original pairs + overrides and turn the levels into map features."""

    def __init__(
        self,
        corridors: list[Any],
        original: Path,
        base_features: list[dict[str, Any]],
        *,
        band_dist: float = 10.0,
        head_m: float = 15.0,
        smooth: int = 0,
    ) -> None:
        self.smooth = smooth
        self.corridors = corridors
        self.original_rows = read_pair_table(original)
        self.styles = _style_by_edge(base_features)
        self.band_dist = band_dist
        self.head_m = head_m

    def from_saved(self, levels_path: Path) -> dict[str, Any] | None:
        """Features styled with the levels already saved in the CSV, without solving."""
        from roadstyle.v2.engine.pairs import _corridor_refs

        if not levels_path.is_file():
            return None
        with levels_path.open(newline="", encoding="utf-8") as source:
            saved = {row["edge_ref"]: row for row in csv.DictReader(source)}
        refs = _corridor_refs(self.corridors)
        if any(ref not in saved for ref in refs):
            return None
        for corridor, ref in zip(self.corridors, refs, strict=True):
            row = saved[ref]
            corridor.casing_levels = (int(row["cs"]), int(row["cm"]), int(row["ce"]))
            corridor.fill_level = int(row["fl"])
        return self._features(self.original_rows)

    def recalculate(
        self, overrides: list[dict[str, str]], levels_path: Path | None = None
    ) -> dict[str, Any]:
        solution = solve_stacking(
            self.corridors,
            pair_table=self.original_rows,
            pair_overrides=overrides,
            band_dist=self.band_dist,
            head_m=self.head_m,
            priority_tiers=True,
        )
        if levels_path is not None:
            write_level_table(self.corridors, solution, levels_path)
        for corridor, casing, fill in zip(
            self.corridors, solution.casing_levels, solution.fill_levels, strict=True
        ):
            corridor.casing_levels = tuple(casing)
            corridor.fill_level = fill
        return self._features(merge_pair_overrides(self.original_rows, overrides))

    def _features(self, active: list[dict[str, str]]) -> dict[str, Any]:
        style = compile_map(corridors=self.corridors, auto_solve=False, basemap=None, smooth=self.smooth).style
        features = style["sources"]["network"]["data"]["features"]
        for feature in features:
            props = feature["properties"]
            props.update(self.styles.get(str(props.get("edge_ref")), {}))
        return {
            "type": "FeatureCollection",
            "features": features,
            "summary": {
                "roads": len(self.corridors),
                "pairs": sum(r["enabled"].lower() in {"true", "1", "yes"} for r in active),
                "levels": sorted({int(c.fill_level) for c in self.corridors}),
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--original", type=Path, default=DEFAULT_DIR / "road_pairs_original.csv")
    parser.add_argument("--overrides", type=Path, default=DEFAULT_DIR / "road_pairs_overrides.csv")
    parser.add_argument("--levels", type=Path, default=DEFAULT_DIR / "road_levels.csv")
    parser.add_argument("--band-dist", type=float, default=10.0)
    parser.add_argument("--head-m", type=float, default=15.0)
    parser.add_argument("--style", default=None, help="v2 style profile: bundled name or JSON path")
    args = parser.parse_args()
    corridors = load_driving_corridors(args.database, args.head_m, args.style)
    build(
        corridors, args.original, args.overrides, args.levels,
        band_dist=args.band_dist, head_m=args.head_m,
    )
    print(f"{len(corridors)} roads -> {args.original}, {args.levels}")


if __name__ == "__main__":
    main()

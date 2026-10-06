"""Persistent, editable road-pair tables for stacking constraints."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from shapely.geometry import LineString

from ...levels import _class_order, _discover_interval_pairs
from .primitives import Corridor

PAIR_FIELDS = (
    "pair_id",
    "relation",
    "edge_a",
    "edge_b",
    "node_ref",
    "endpoint_a",
    "endpoint_b",
    "upper_edge_ref",
    "lower_edge_ref",
    "enabled",
)
OVERRIDE_FIELDS = ("action", *PAIR_FIELDS)
RELATIONS = {"near", "cross", "connect", "order"}
OVERRIDE_ACTIONS = {"add", "replace", "remove"}


def _pair_id(relation: str, values: tuple[str, ...]) -> str:
    payload = json.dumps([relation, *values], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _corridor_refs(corridors: list[Corridor]) -> list[str]:
    return [
        str(c.properties.get("edge_ref") or c.properties.get("ref") or c.id
            or c.properties.get("edge_id") or c.properties.get("id") or f"@index:{i}")
        for i, c in enumerate(corridors)
    ]


def discover_pair_table(
    corridors: list[Corridor],
    *,
    band_dist: float = 10.0,
) -> list[dict[str, str]]:
    """Build original near/cross/connect/order rows for corridors, suitable for CSV."""
    refs = _corridor_refs(corridors)
    if len(set(refs)) != len(refs):
        raise ValueError("discover_pair_table: edge references must be unique")

    first_coords = [c.geometry.coords[0] for c in corridors]
    is_lonlat = bool(first_coords) and all(
        -180 <= coord[0] <= 180 and -90 <= coord[1] <= 90 for coord in first_coords
    )
    lon0 = sum(coord[0] for coord in first_coords) / len(first_coords) if is_lonlat else 0.0
    lat0 = sum(coord[1] for coord in first_coords) / len(first_coords) if is_lonlat else 0.0
    kx = 111320.0 * math.cos(math.radians(lat0)) if is_lonlat else 1.0
    ky = 110540.0 if is_lonlat else 1.0
    geometries = [c.geometry for c in corridors]
    if is_lonlat:
        metres = [
            LineString([((x - lon0) * kx, (y - lat0) * ky) for x, y in c.geometry.coords])
            for c in corridors
        ]
    else:
        metres = geometries

    endpoint_coords = sorted({(g.coords[0][0], g.coords[0][1]) for g in geometries} |
                             {(g.coords[-1][0], g.coords[-1][1]) for g in geometries})
    node_ids = {coord: i for i, coord in enumerate(endpoint_coords)}
    ends = [
        (node_ids[(g.coords[0][0], g.coords[0][1])], node_ids[(g.coords[-1][0], g.coords[-1][1])])
        for g in geometries
    ]

    bands = [int(c.band) for c in corridors]
    priorities = []
    for c in corridors:
        priority = c.junction_priority
        highway = c.properties.get("highway")
        priorities.append(float(priority) if priority != 0.0 or highway is None else _class_order(highway))

    discovered = _discover_interval_pairs(metres, ends, bands, priorities, band_dist)
    rows: list[dict[str, str]] = []

    def add(relation: str, *, edge_a: str, edge_b: str, node_ref: str = "",
            endpoint_a: str = "", endpoint_b: str = "", upper: str = "", lower: str = "") -> None:
        identity = (edge_a, edge_b, node_ref, endpoint_a, endpoint_b, upper, lower)
        rows.append({
            "pair_id": _pair_id(relation, identity),
            "relation": relation,
            "edge_a": edge_a,
            "edge_b": edge_b,
            "node_ref": node_ref,
            "endpoint_a": endpoint_a,
            "endpoint_b": endpoint_b,
            "upper_edge_ref": upper,
            "lower_edge_ref": lower,
            "enabled": "true",
        })

    for upper, lower in discovered["stack_pairs"]:
        relation = "cross" if geometries[upper].intersects(geometries[lower]) else "near"
        upper_ref, lower_ref = refs[upper], refs[lower]
        add(relation, edge_a=upper_ref, edge_b=lower_ref, upper=upper_ref, lower=lower_ref)

    for a, side_a, b, side_b, node in discovered["connect_pairs"]:
        lon, lat = endpoint_coords[node]
        node_ref = f"{lon:.7f},{lat:.7f}"
        edge_a, edge_b = refs[a], refs[b]
        if edge_a > edge_b:
            edge_a, edge_b = edge_b, edge_a
            side_a, side_b = side_b, side_a
        add("connect", edge_a=edge_a, edge_b=edge_b, node_ref=node_ref,
            endpoint_a=side_a, endpoint_b=side_b)

    for upper, lower in discovered["order_pairs"]:
        upper_ref, lower_ref = refs[upper], refs[lower]
        add("order", edge_a=upper_ref, edge_b=lower_ref,
            upper=upper_ref, lower=lower_ref)

    return sorted(rows, key=lambda row: (row["relation"], row["pair_id"]))


def merge_pair_overrides(
    original_pairs: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Apply sparse add/replace/remove override rows to the discovered table."""
    effective = {str(row["pair_id"]): {field: str(row.get(field, "")) for field in PAIR_FIELDS}
                 for row in original_pairs}
    if len(effective) != len(original_pairs):
        raise ValueError("pair table contains duplicate pair_id values")

    for override in overrides:
        pair_id = str(override.get("pair_id", "")).strip()
        action = str(override.get("action", "")).strip().lower()
        if not pair_id or action not in OVERRIDE_ACTIONS:
            raise ValueError("each pair override needs a pair_id and action: add, replace, or remove")
        if action == "remove":
            if pair_id not in effective:
                raise ValueError(f"cannot remove unknown pair_id {pair_id!r}")
            effective[pair_id]["enabled"] = "false"
            continue
        if action == "add":
            if pair_id in effective:
                raise ValueError(f"cannot add existing pair_id {pair_id!r}")
            row = {field: str(override.get(field, "")).strip() for field in PAIR_FIELDS}
            row["pair_id"] = pair_id
            if not row["enabled"]:
                row["enabled"] = "true"
            if not row["relation"] or not row["edge_a"] or not row["edge_b"]:
                raise ValueError(f"added pair {pair_id!r} needs relation, edge_a, and edge_b")
            effective[pair_id] = row
            continue

        if pair_id not in effective:
            raise ValueError(f"cannot replace unknown pair_id {pair_id!r}")
        row = effective[pair_id]
        for field in PAIR_FIELDS:
            value = str(override.get(field, "")).strip()
            if field != "pair_id" and value:
                row[field] = value

    for pair_id, row in effective.items():
        if row["relation"] not in RELATIONS:
            raise ValueError(f"pair {pair_id!r} has unsupported relation {row['relation']!r}")
        if row["enabled"].lower() not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError(f"pair {pair_id!r} enabled must be true or false")
        required = {
            "near": ("upper_edge_ref", "lower_edge_ref"),
            "cross": ("upper_edge_ref", "lower_edge_ref"),
            "connect": ("edge_a", "edge_b", "endpoint_a", "endpoint_b"),
            "order": ("upper_edge_ref", "lower_edge_ref"),
        }[row["relation"]]
        if any(not row[field] for field in required):
            raise ValueError(f"pair {pair_id!r} relation {row['relation']!r} needs {', '.join(required)}")
        if row["relation"] == "connect" and any(
            row[field] not in {"start", "end"}
            for field in ("endpoint_a", "endpoint_b")
        ):
            raise ValueError(
                f"pair {pair_id!r} relation 'connect' endpoints must be start or end"
            )
    return sorted(effective.values(), key=lambda row: (row["relation"], row["pair_id"]))


def read_pair_table(path: str | Path, *, overrides: bool = False) -> list[dict[str, str]]:
    """Read an original or override CSV table."""
    fields = OVERRIDE_FIELDS if overrides else PAIR_FIELDS
    with Path(path).open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing = set(fields) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing pair-table columns: {', '.join(sorted(missing))}")
        return [{field: str(row.get(field) or "").strip() for field in fields} for row in reader]


def write_pair_table(path: str | Path, rows: list[dict[str, Any]], *, overrides: bool = False) -> None:
    """Write pair rows to a CSV file."""
    fields = OVERRIDE_FIELDS if overrides else PAIR_FIELDS
    with Path(path).open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

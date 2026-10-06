"""Prepare combined roadstyle v2 solver inputs from a DuckOSM database."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from shapely import from_wkb, from_wkt
from shapely.geometry import LineString, mapping

from roadstyle.v2.adapters.osm import OSMAdapter
from roadstyle.v2.engine.primitives import Corridor
from roadstyle.v2.engine.solver import write_pair_tables

MODE_SCHEMAS = ("driving", "walking", "cycling")
_REFERENCE_COLUMNS = ("edge_ref", "ref", "edge_id", "id")
_PHYSICAL_ID_COLUMNS = ("physical_road_id", "road_id", "way_id", "osm_id", "osmid")
_REVERSE_REF = re.compile(r"^(.*)#(\d+)[fr]$")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    if isinstance(value, (list, tuple, dict)):
        return True
    missing = pd.isna(value)
    return not bool(missing)


def _scalar_text(value: Any) -> str:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value).strip()


def _rows_for_mode(connection: Any, schema: str) -> list[dict[str, Any]]:
    column_types = connection.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = 'edges'
        """,
        [schema],
    ).fetchall()
    columns = {str(row[0]): str(row[1]) for row in column_types}
    if not columns:
        return []
    columns_by_lower = {name.lower(): name for name in columns}
    geometry_column = next(
        (columns_by_lower[name] for name in ("geom", "geometry") if name in columns_by_lower),
        None,
    )
    if geometry_column is None:
        raise ValueError(f"DuckOSM table {schema}.edges has no geom or geometry column")

    geometry_type = columns[geometry_column].upper()
    if "GEOMETRY" in geometry_type:
        geometry_expression = f"ST_AsWKB({_quote_identifier(geometry_column)})"
    else:
        geometry_expression = _quote_identifier(geometry_column)
    query = (
        f"SELECT *, {geometry_expression} AS {_quote_identifier('__roadstyle_wkb')} "
        f"FROM {_quote_identifier(schema)}.edges"
    )
    frame = connection.execute(query).fetchdf()
    if frame.empty:
        return []
    geometry_values = frame.pop("__roadstyle_wkb")
    frame = frame.drop(columns=[geometry_column])
    records = frame.to_dict("records")
    for row, geometry_wkb in zip(records, geometry_values, strict=True):
        if geometry_wkb is None:
            geometry = None
        elif isinstance(geometry_wkb, str):
            geometry = from_wkt(geometry_wkb)
        else:
            geometry = from_wkb(bytes(geometry_wkb))
        row["geometry"] = geometry
    return records


def _stable_references(records: list[dict[str, Any]], schema: str) -> list[str]:
    for column in _REFERENCE_COLUMNS:
        values = [row.get(column) for row in records]
        if all(_has_value(value) for value in values):
            refs = [_scalar_text(value) for value in values]
            if all(refs) and len(set(refs)) == len(refs):
                return [f"{schema}:{column}:{ref}" for ref in refs]

    raise ValueError(
        f"{schema}.edges needs a non-null, unique reference column; "
        f"tried {', '.join(_REFERENCE_COLUMNS)}"
    )


def _physical_reference(row: dict[str, Any], edge_ref: str, schema: str) -> str | None:
    for column in _PHYSICAL_ID_COLUMNS:
        value = row.get(column)
        if _has_value(value):
            text = _scalar_text(value)
            if text:
                return f"{schema}:{column}:{text}"

    # Some prepared OSM tables encode the source way and segment in edge_ref.
    match = _REVERSE_REF.match(edge_ref)
    return f"{schema}:segment:{match.group(1)}#{match.group(2)}" if match else None


def load_duckosm_corridors(
    connection: Any,
    *,
    only_modes: tuple[str, ...] | None = None,
    plain_refs: bool = False,
    profile: Any = None,
) -> tuple[list[Corridor], list[str]]:
    """Read the available modes' edges tables into one solver input list.

    ``plain_refs`` keeps the bare ``edge_ref`` column value (as the rendered map does)
    instead of ``mode:column:value``; use it with a single mode.
    ``profile`` is a v2 style profile (name, JSON path or dict) for widths, casings and colours.
    """
    schemas = {
        str(row[0])
        for row in connection.execute(
            "SELECT schema_name FROM information_schema.schemata"
        ).fetchall()
    }
    modes = [
        schema for schema in MODE_SCHEMAS
        if schema in schemas and (only_modes is None or schema in only_modes)
    ]
    if plain_refs and len(modes) != 1:
        raise ValueError("plain_refs needs exactly one mode")
    if not modes:
        raise ValueError(
            "DuckOSM database has none of the expected mode schemas: "
            + ", ".join(MODE_SCHEMAS)
        )

    corridors: list[Corridor] = []
    loaded_modes: list[str] = []
    for schema in modes:
        records = _rows_for_mode(connection, schema)
        if not records:
            continue
        refs = _stable_references(records, schema)
        if plain_refs:
            refs = [ref.split(":", 2)[2] for ref in refs]
        road_records: list[dict[str, Any]] = []
        road_refs: list[str] = []
        physical_refs: list[str | None] = []
        for record, ref in zip(records, refs, strict=True):
            geometry = record.get("geometry")
            if not isinstance(geometry, LineString) or geometry.is_empty:
                continue
            road_records.append(record)
            road_refs.append(ref)
            physical_refs.append(_physical_reference(record, ref, schema))

        if not road_records:
            continue

        adapter_records = []
        for record in road_records:
            adapter_record = {}
            for key, value in record.items():
                if key == "geometry":
                    adapter_record[key] = value
                elif _has_value(value):
                    adapter_record[key] = _scalar_text(value) if isinstance(
                        value, (list, tuple, dict)
                    ) or hasattr(value, "tolist") else value
            if "layer" not in adapter_record and "band" in adapter_record:
                adapter_record["layer"] = adapter_record["band"]
            adapter_records.append(adapter_record)

        mode_corridors = OSMAdapter.from_dataframe(adapter_records, profile=profile)
        if len(mode_corridors) != len(road_records):
            raise ValueError(f"{schema}.edges contains rows that cannot be converted to corridors")
        for corridor, _record, ref, physical_ref in zip(
            mode_corridors, road_records, road_refs, physical_refs, strict=True,
        ):
            corridor.id = ref
            corridor.properties["edge_ref"] = ref
            corridor.properties["mode"] = schema
            if physical_ref is not None:
                corridor.properties["physical_road_id"] = physical_ref
            corridors.append(corridor)
        loaded_modes.append(schema)

    if not corridors:
        raise ValueError("DuckOSM mode edge tables contain no LineString roads")
    return corridors, loaded_modes


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"cannot encode {type(value).__name__} in corridor GeoJSON")


def write_corridor_geojson(corridors: list[Corridor], path: str | Path) -> None:
    """Write corridors in solver-ready GeoJSON, preserving normalized and source fields."""
    features = []
    for corridor in corridors:
        props = dict(corridor.properties)
        props["_roadstyle"] = {
            "id": str(corridor.id),
            "width_m": corridor.width_m,
            "casing_left_m": corridor.casing_left_m,
            "casing_right_m": corridor.casing_right_m,
            "split_mode": corridor.split_mode,
            "split_start": corridor.split_start,
            "split_end": corridor.split_end,
            "band": corridor.band,
            "junction_priority": corridor.junction_priority,
            "bridge_deck": corridor.bridge_deck,
            "tunnel": corridor.tunnel,
        }
        features.append({
            "type": "Feature",
            "geometry": mapping(corridor.geometry),
            "properties": props,
        })
    collection = {"type": "FeatureCollection", "features": features}
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as output:
        json.dump(collection, output, ensure_ascii=False, default=_json_default)


def read_corridor_geojson(path: str | Path) -> list[Corridor]:
    """Load corridor objects exported by :func:`write_corridor_geojson`."""
    from shapely.geometry import shape

    collection = json.loads(Path(path).read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{path}: expected a GeoJSON FeatureCollection")

    corridors = []
    for feature in collection.get("features", []):
        props = dict(feature.get("properties") or {})
        settings = props.pop("_roadstyle", None)
        if not isinstance(settings, dict):
            raise ValueError(f"{path}: feature is missing _roadstyle solver properties")
        geometry_data = feature.get("geometry")
        if geometry_data is None:
            raise ValueError(f"{path}: corridor feature is missing geometry")
        corridors.append(Corridor(
            id=settings.get("id"),
            geometry=shape(geometry_data),
            width_m=float(settings.get("width_m", 8.0)),
            casing_left_m=float(settings.get("casing_left_m", 0.20)),
            casing_right_m=float(settings.get("casing_right_m", 0.20)),
            split_mode=str(settings.get("split_mode", "setbacks")),
            split_start=float(settings.get("split_start", 5.0)),
            split_end=float(settings.get("split_end", 5.0)),
            band=int(settings.get("band", 0)),
            junction_priority=float(settings.get("junction_priority", 0.0)),
            bridge_deck=bool(settings.get("bridge_deck", False)),
            tunnel=bool(settings.get("tunnel", False)),
            properties=props,
        ))
    return corridors


def create_solver_inputs(
    database: str | Path,
    output_dir: str | Path,
    *,
    band_dist: float = 10.0,
    read_only: bool = True,
) -> tuple[list[Corridor], list[str], Path, Path, Path]:
    """Export combined solver corridors and pair tables from a DuckOSM database."""
    try:
        import duckdb
    except ImportError as error:
        raise RuntimeError(
            "Reading DuckOSM databases requires DuckDB; install roadstyle[duckdb]"
        ) from error

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    corridor_path = destination / "corridors.geojson"
    pair_path = destination / "road_pairs_original.csv"
    override_path = destination / "road_pairs_overrides.csv"
    with duckdb.connect(str(database), read_only=read_only) as connection:
        connection.execute("LOAD spatial")
        corridors, modes = load_duckosm_corridors(connection)
        write_corridor_geojson(corridors, corridor_path)
        write_pair_tables(corridors, pair_path, override_path, band_dist=band_dist)
    return corridors, modes, corridor_path, pair_path, override_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Path to the DuckOSM .duckdb file")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/v2/duckosm_solver_input"),
        help="Output directory (default: data/v2/duckosm_solver_input)",
    )
    parser.add_argument("--band-dist", type=float, default=10.0)
    args = parser.parse_args()
    corridors, modes, corridor_path, pair_path, override_path = create_solver_inputs(
        args.database,
        args.output,
        band_dist=args.band_dist,
    )
    print(f"Prepared modes together: {', '.join(modes)}")
    print(f"Corridors: {len(corridors)} -> {corridor_path}")
    print(f"Original solver pairs -> {pair_path}")
    print(f"Pair override template -> {override_path}")


if __name__ == "__main__":
    main()

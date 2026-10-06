"""Serve a local MapLibre editor for v2 solver pair overrides.

Run with:
    python scripts/v2/pair_override_dashboard.py
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from roadstyle.v2.engine.pairs import (  # noqa: E402
    OVERRIDE_FIELDS,
    merge_pair_overrides,
    read_pair_table,
    write_pair_table,
)

DEFAULT_DATA_DIR = ROOT / "data/v2"
DEFAULT_ORIGINAL = DEFAULT_DATA_DIR / "road_pairs_original.csv"
DEFAULT_OVERRIDES = DEFAULT_DATA_DIR / "road_pairs_overrides.csv"
DEFAULT_MAP_HTML = ROOT / "docs/v2/monaco_roads_v2.html"
DEFAULT_LEVELS = DEFAULT_DATA_DIR / "road_levels.csv"
DEFAULT_DATABASE = ROOT.parent / "duckOSM" / "monaco.duckdb"
EDITOR_DIR = Path(__file__).resolve().parent
RELATIONS = {"near", "cross", "connect", "order"}


def _load_all_features(path: Path) -> list[dict[str, Any]]:
    html = path.read_text(encoding="utf-8")
    marker = "const styleSpec = "
    style_spec, _ = json.JSONDecoder().raw_decode(html[html.index(marker) + len(marker):])
    return style_spec["sources"]["network"]["data"]["features"]


def _load_map_features(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Map HTML does not exist: {path}")
    html = path.read_text(encoding="utf-8")
    marker = "const styleSpec = "
    if html.count(marker) != 1:
        raise ValueError(f"{path}: expected one embedded MapLibre styleSpec")
    start = html.index(marker) + len(marker)
    style_spec, _ = json.JSONDecoder().raw_decode(html[start:])
    features = style_spec.get("sources", {}).get("network", {}).get("data", {}).get("features")
    if not isinstance(features, list):
        raise ValueError(f"{path}: embedded network source has no GeoJSON features")
    return [
        feature
        for feature in features
        if feature.get("geometry")
        and feature.get("geometry", {}).get("type") in {"LineString", "MultiLineString"}
        and feature.get("properties", {}).get("_type") == "corridor_fill"
        and feature.get("properties", {}).get("edge_ref")
    ]


def _render_editor_page(map_path: Path) -> str:
    html = map_path.read_text(encoding="utf-8")
    marker = "const styleSpec = "
    map_marker = "const map = new maplibregl.Map({"
    if html.count(marker) != 1 or html.count(map_marker) != 1:
        raise ValueError(f"{map_path}: unexpected roadstyle map template structure")
    html = html.replace(marker, "const styleSpec = window.__pairEditorStyleSpec = ", 1)
    html = html.replace(
        map_marker,
        "const map = window.__pairEditorMap = new maplibregl.Map({",
        1,
    )
    if html.count("</head>") != 1 or html.count("</body>") != 1:
        raise ValueError(f"{map_path}: expected one head and body end tag")
    html = html.replace(
        "</head>",
        '  <link rel="stylesheet" href="/pair_override_editor.css">\n</head>',
        1,
    )
    editor_mount = """
<aside id="pair-editor">
  <header class="editor-header">
    <div class="editor-brand">
      <p class="eyebrow">ROADSTYLE V2</p>
      <h1>Pair override editor</h1>
    </div>
    <button id="toggle-panel" class="panel-toggle" type="button"
      aria-label="Collapse pair editor" aria-expanded="true" title="Collapse panel">›</button>
  </header>
  <div id="editor-main">
  <div class="editor-toolbar">
  <p class="editor-help">Click two roads on the map, then describe their relationship.</p>
  <button id="clear-selection" class="quiet-button" type="button">Clear selection</button>
  </div>
  <p id="editor-status" class="status" role="status">Loading pair tables…</p>
  <label class="field-label" for="road-search">Find a road</label>
  <input id="road-search" type="search" placeholder="Street name, class, or edge reference">
  <div id="road-results" class="road-results" aria-live="polite"></div>
  <section class="selection-section">
    <div class="section-heading">
      <h2>Selected roads</h2>
      <span id="selection-count" class="count-pill">0 / 2</span>
    </div>
    <div id="selected-roads" class="selected-roads"></div>
  </section>
  <section id="relationship-form" class="relationship-form" hidden>
    <label class="field-label" for="relation">Relationship</label>
    <select id="relation">
      <option value="near">Near — stack by band</option>
      <option value="cross">Crossing — stack by band</option>
      <option value="connect">Connect — relate two heads</option>
      <option value="order">Junction order — priority</option>
    </select>
    <div id="upper-wrap">
      <label class="field-label" for="upper-road">Upper / preferred road</label>
      <select id="upper-road"></select>
      <p id="lower-road" class="field-hint"></p>
    </div>
    <div id="endpoint-wrap" hidden>
      <label class="field-label" for="endpoint-a">Connected head on road A</label>
      <select id="endpoint-a"></select>
      <label class="field-label" for="endpoint-b">Connected head on road B</label>
      <select id="endpoint-b"></select>
      <p id="endpoint-hint" class="field-hint">
        Select the two heads to relate. No shared point or geometry change is required.
      </p>
    </div>
    <div id="replacement-wrap" hidden>
      <label class="field-label" for="replacement-mode">Existing relationship</label>
      <select id="replacement-mode"></select>
    </div>
    <button id="save-pair" class="save-button" type="button" disabled>Save pair override</button>
  </section>
  <details class="saved-overrides" open>
    <summary>Saved overrides <span id="override-count"></span></summary>
    <div id="override-list"></div>
    <button id="download-overrides" class="quiet-button" type="button">Download CSV</button>
  </details>
  </div>
</aside>
<script src="/pair_override_editor.js"></script>
"""
    html = html.replace("</body>", editor_mount + "\n</body>", 1)
    return html


def _same_point(a: str | None, b: str) -> bool:
    # Map geometry is stored with 6 decimals, node_ref with 7, so compare with a tolerance.
    try:
        ax, ay = (float(v) for v in str(a).split(","))
        bx, by = (float(v) for v in b.split(","))
    except ValueError:
        return False
    return abs(ax - bx) <= 1e-6 and abs(ay - by) <= 1e-6


def _validate_overrides(
    original: list[dict[str, str]],
    overrides: list[dict[str, str]],
    *,
    known_refs: set[str] | None = None,
    features: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Raise for unknown roads; return warnings for suspicious but saveable rows."""
    warnings: list[str] = []
    effective = merge_pair_overrides(original, overrides)
    for row in effective:
        refs = {
            ref
            for ref in (
                row.get("edge_a", ""),
                row.get("edge_b", ""),
                row.get("upper_edge_ref", ""),
                row.get("lower_edge_ref", ""),
            )
            if ref
        }
        if known_refs is not None:
            unknown = sorted(refs - known_refs)
            if unknown:
                raise ValueError(
                    f"Pair {row['pair_id']} references unknown edge(s): {', '.join(unknown)}"
                )

    if features:
        endpoints: dict[str, dict[str, str]] = {}
        for feature in features:
            props = feature.get("properties", {})
            ref = str(props.get("edge_ref", "")).strip()
            geometry_data = feature.get("geometry")
            if not ref or not geometry_data:
                continue
            geometry = shape(geometry_data)
            lines = (
                list(geometry.geoms)
                if geometry.geom_type == "MultiLineString"
                else [geometry]
            )
            endpoints[ref] = {
                "start": f"{lines[0].coords[0][0]:.7f},{lines[0].coords[0][1]:.7f}",
                "end": f"{lines[-1].coords[-1][0]:.7f},{lines[-1].coords[-1][1]:.7f}",
            }
        # Rows of the original table are solver output; only check what the user wrote.
        touched = {row.get("pair_id", "") for row in overrides}
        for row in effective:
            if row["relation"] != "connect" or row["pair_id"] not in touched:
                continue
            if not row["node_ref"]:
                continue
            for edge_field, endpoint_field in (
                ("edge_a", "endpoint_a"),
                ("edge_b", "endpoint_b"),
            ):
                ref = row[edge_field]
                side = row[endpoint_field]
                if ref in endpoints and not _same_point(endpoints[ref].get(side), row["node_ref"]):
                    warnings.append(
                        f"Connection {row['pair_id']}: node_ref does not match "
                        f"{side} of {ref}."
                    )
    return warnings


def _new_pair_override(
    relation: str,
    edge_a: str,
    edge_b: str,
    *,
    upper: str = "",
    lower: str = "",
    node_ref: str = "",
    endpoint_a: str = "",
    endpoint_b: str = "",
) -> dict[str, str]:
    if edge_a == edge_b:
        raise ValueError("Select two different roads to create a pair override.")
    row = {field: "" for field in OVERRIDE_FIELDS}
    row.update({
        "action": "add",
        "pair_id": uuid.uuid4().hex[:20],
        "relation": relation,
        "edge_a": edge_a,
        "edge_b": edge_b,
        "enabled": "true",
    })
    if relation in {"near", "cross", "order"}:
        row["upper_edge_ref"] = upper
        row["lower_edge_ref"] = lower
    if relation == "connect":
        row.update({
            "node_ref": node_ref,
            "endpoint_a": endpoint_a,
            "endpoint_b": endpoint_b,
        })
    return row


def _pair_override_from_selection(
    relation: str,
    edge_a: str,
    edge_b: str,
    *,
    upper: str = "",
    lower: str = "",
    node_ref: str = "",
    endpoint_a: str = "",
    endpoint_b: str = "",
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    if existing is None:
        return _new_pair_override(
            relation,
            edge_a,
            edge_b,
            upper=upper,
            lower=lower,
            node_ref=node_ref,
            endpoint_a=endpoint_a,
            endpoint_b=endpoint_b,
        )
    row = {field: "" for field in OVERRIDE_FIELDS}
    row["action"] = "replace"
    row["pair_id"] = existing["pair_id"]
    row["relation"] = relation
    changes = {
        "edge_a": edge_a,
        "edge_b": edge_b,
        "upper_edge_ref": upper,
        "lower_edge_ref": lower,
        "node_ref": node_ref,
        "endpoint_a": endpoint_a,
        "endpoint_b": endpoint_b,
    }
    for field, value in changes.items():
        if value and value != existing.get(field, ""):
            row[field] = value
    return row


def _save_overrides(
    path: Path,
    original: list[dict[str, str]],
    overrides: list[dict[str, str]],
    *,
    known_refs: set[str] | None = None,
    features: list[dict[str, Any]] | None = None,
) -> None:
    _validate_overrides(
        original,
        overrides,
        known_refs=known_refs,
        features=features,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_pair_table(path, overrides, overrides=True)


def _read_data(original_path: Path, overrides_path: Path) -> dict[str, Any]:
    original = read_pair_table(original_path)
    overrides = (
        read_pair_table(overrides_path, overrides=True)
        if overrides_path.exists()
        else []
    )
    effective = merge_pair_overrides(original, overrides)
    return {
        "original": original,
        "overrides": overrides,
        "effective_count": sum(
            row["enabled"].lower() in {"true", "1", "yes"} for row in effective
        ),
    }


def _save_override(
    row: dict[str, Any],
    original_path: Path,
    overrides_path: Path,
    known_refs: set[str],
    features: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> list[dict[str, str]]:
    action = str(row.get("action", "")).strip().lower()
    if action not in {"add", "replace"}:
        raise ValueError("Only add and replace overrides can be saved here.")
    normalized = {
        field: str(row.get(field, "")).strip()
        for field in OVERRIDE_FIELDS
    }
    if action == "add" and (not normalized["edge_a"] or not normalized["edge_b"]):
        raise ValueError("Choose two roads before saving.")
    if normalized["edge_a"] and normalized["edge_a"] == normalized["edge_b"]:
        raise ValueError("A pair must contain two different roads.")
    if normalized["relation"] not in RELATIONS:
        raise ValueError(f"Unsupported relationship: {normalized['relation']!r}")

    original = read_pair_table(original_path)
    overrides = (
        read_pair_table(overrides_path, overrides=True)
        if overrides_path.exists()
        else []
    )
    if action == "replace" and normalized["pair_id"] not in {
        item["pair_id"] for item in original
    }:
        raise ValueError("The discovered pair selected for replacement no longer exists.")
    if action == "add" and normalized["pair_id"] in {
        item["pair_id"] for item in original + overrides
    }:
        raise ValueError("This pair ID already exists; reload the editor and try again.")
    overrides = [
        item for item in overrides if item["pair_id"] != normalized["pair_id"]
    ]
    overrides.append(normalized)
    found = _validate_overrides(
        original,
        overrides,
        known_refs=known_refs,
        features=features,
    )
    if action == "add":
        pair = {normalized["edge_a"], normalized["edge_b"]}
        for item in original:
            if {item["edge_a"], item["edge_b"]} == pair:
                found.append(
                    f"The original table already has a {item['relation']} pair for these "
                    f"roads ({item['pair_id']}); this override adds a second relationship."
                )
    if warnings is not None:
        warnings.extend(found)
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    write_pair_table(overrides_path, overrides, overrides=True)
    return overrides


def _delete_override(
    pair_id: str,
    overrides_path: Path,
) -> list[dict[str, str]]:
    overrides = (
        read_pair_table(overrides_path, overrides=True)
        if overrides_path.exists()
        else []
    )
    remaining = [row for row in overrides if row["pair_id"] != pair_id]
    if len(remaining) == len(overrides):
        raise ValueError(f"Override {pair_id!r} does not exist.")
    write_pair_table(overrides_path, remaining, overrides=True)
    return remaining


class PairEditorServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        *,
        original_path: Path,
        overrides_path: Path,
        map_path: Path,
        features: list[dict[str, Any]],
        model: Any | None = None,
        levels_path: Path | None = None,
    ) -> None:
        super().__init__(address, PairEditorHandler)
        self.model = model
        self.solve_lock = threading.Lock()
        self.levels_path = levels_path
        self.original_path = original_path
        self.overrides_path = overrides_path
        self.map_path = map_path
        self.features = features
        self.known_refs = {
            str(feature["properties"]["edge_ref"])
            for feature in features
        }


    def saved_network(self) -> dict[str, Any] | None:
        """The map with the levels already saved in the CSV; falls back to solving."""
        if self.model is None:
            return None
        saved = self.model.from_saved(self.levels_path) if self.levels_path else None
        return saved if saved is not None else self.recalculate()

    def recalculate(self) -> dict[str, Any] | None:
        """Solve original + saved overrides, rewrite the level CSV, return the map features."""
        if self.model is None:
            return None
        overrides = (
            read_pair_table(self.overrides_path, overrides=True)
            if self.overrides_path.exists()
            else []
        )
        with self.solve_lock:
            return self.model.recalculate(overrides, self.levels_path)


class PairEditorHandler(BaseHTTPRequestHandler):
    server: PairEditorServer

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route in {"/", "/index.html"}:
            self._send(200, _render_editor_page(self.server.map_path), "text/html; charset=utf-8")
        elif route == "/api/data":
            data = _read_data(self.server.original_path, self.server.overrides_path)
            self._send(200, json.dumps(data), "application/json; charset=utf-8")
        elif route == "/api/network":
            try:
                self._send(200, json.dumps(self.server.saved_network()), "application/json; charset=utf-8")
            except (OSError, ValueError, RuntimeError) as error:
                self._send(500, json.dumps({"error": str(error)}), "application/json; charset=utf-8")
        elif route == "/pair_override_editor.js":
            self._send_file("pair_override_editor.js", "text/javascript; charset=utf-8")
        elif route == "/pair_override_editor.css":
            self._send_file("pair_override_editor.css", "text/css; charset=utf-8")
        else:
            self._send(404, "Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route not in {"/api/overrides", "/api/overrides/delete"}:
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        warnings: list[str] = []
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 64_000:
                raise ValueError("Request body must be between 1 and 64,000 bytes.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object.")
            if route == "/api/overrides/delete":
                pair_id = str(payload.get("pair_id", "")).strip()
                if not pair_id:
                    raise ValueError("Choose an override row to delete.")
                overrides = _delete_override(pair_id, self.server.overrides_path)
            else:
                if not isinstance(payload.get("row"), dict):
                    raise ValueError("Expected a JSON object containing one override row.")
                overrides = _save_override(
                    payload["row"],
                    self.server.original_path,
                    self.server.overrides_path,
                    self.server.known_refs,
                    self.server.features,
                    warnings,
                )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._send(400, json.dumps({"error": str(error)}), "application/json; charset=utf-8")
            return
        try:
            network = self.server.recalculate()
        except (OSError, ValueError, RuntimeError) as error:
            self._send(500, json.dumps({"error": f"Saved, but levels failed: {error}"}),
                       "application/json; charset=utf-8")
            return
        self._send(
            200,
            json.dumps({"overrides": overrides, "network": network, "warnings": warnings}),
            "application/json; charset=utf-8",
        )

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[pair-editor] {self.address_string()} - {format % args}")

    def _send_file(self, name: str, content_type: str) -> None:
        path = EDITOR_DIR / name
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            self._send(500, str(error), "text/plain; charset=utf-8")
            return
        self._send(200, content, content_type)

    def _send(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument(
        "--map-html",
        type=Path,
        default=DEFAULT_MAP_HTML,
    )
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--head-m", type=float, default=15.0)
    parser.add_argument("--smooth", type=int, default=0, help="Display-only smoothing iterations (0 = off)")
    args = parser.parse_args()
    features = _load_map_features(args.map_html)
    model = None
    database = args.database.expanduser()
    if database.is_file():
        from build_road_levels import RoadLevelModel, load_driving_corridors

        model = RoadLevelModel(
            load_driving_corridors(database, args.head_m),
            args.original.expanduser(),
            _load_all_features(args.map_html),
            head_m=args.head_m,
            smooth=args.smooth,
        )
    else:
        print(f"No DuckOSM database at {database}: showing the map's own levels.")
    server = PairEditorServer(
        (args.host, args.port),
        original_path=args.original.expanduser(),
        overrides_path=args.overrides.expanduser(),
        map_path=args.map_html.expanduser(),
        features=features,
        model=model,
        levels_path=args.levels.expanduser(),
    )
    print(f"Pair override editor: http://{args.host}:{server.server_port}")
    print(f"Overrides will be saved to: {args.overrides.expanduser()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping pair override editor.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

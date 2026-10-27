"""The Python binding gives the Rust engine's output unchanged (2026-10-24: the Rust API is the design, Python a thin binding): on Monaco,
the style, the road table and the page that the binding gives are the texts that the Rust facade makes, byte for byte. The facade's
texts are in the Rust goldens (rust/roadstyle-rs/tests/data/monaco/rust_style.json, rust_page.json: their size and the first 16 hex
characters of their SHA-256; tests/areas.rs makes them with ROADSTYLE_BLESS=1), from the same inputs: roads.parquet and the look of
golden_options.json.gz. The wasm package in Node gives the same texts too (the last test): one fixture, three languages, one hash."""
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from roadstyle import _engine

DATA = Path(__file__).resolve().parents[1] / "rust/roadstyle-rs/tests/data"


def _text(t):
    b = t.encode() if isinstance(t, str) else bytes(t)
    return {"bytes": len(b), "sha16": hashlib.sha256(b).hexdigest()[:16]}


def _look():
    """areas.rs's look: the area's options, resolved, as an export (args.export = true after the resolution)."""
    o = json.loads(gzip.decompress((DATA / "monaco/golden_options.json.gz").read_bytes()))
    return _engine.rust().resolve_look(json.dumps(o)).with_arg("export", "true")


def test_the_binding_gives_the_facades_style_and_road_table():
    want = json.loads((DATA / "monaco/rust_style.json").read_text())
    s = _engine.rust().make_sources(pq.read_table(DATA / "monaco/roads.parquet"), _look())
    assert _text(s.style()) == want["text"]
    assert _text(s.road_table(lines=True)) == want["road_table"]["text"]



def test_a_lean_road_table_has_only_the_fields_given():
    """road_table(fields): each road's row with only these fields (the level editor's table: what its page reads), the same rows."""
    s = _engine.rust().make_sources(pq.read_table(DATA / "monaco/roads.parquet"), _look())
    full, lean = json.loads(s.road_table(lines=True)), json.loads(s.road_table(["name", "highway", "__rs_twoway"], lines=True))
    assert len(lean["props"]) == len(full["props"]) and lean["lines"] == full["lines"] and lean["bboxes"] == full["bboxes"]
    assert all(set(p) <= {"name", "highway", "__rs_twoway"} for p in lean["props"])
    assert [p.get("name") for p in lean["props"]] == [p.get("name") for p in full["props"]]


def test_a_road_table_without_lines_gives_them_by_road_lines():
    """road_table() has no lines (the page asks for one with road_lines); road_lines(rows) gives the table's lines, null out of range."""
    s = _engine.rust().make_sources(pq.read_table(DATA / "monaco/roads.parquet"), _look())
    full, bare = json.loads(s.road_table(lines=True)), json.loads(s.road_table())
    assert "lines" not in bare and {k: v for k, v in full.items() if k != "lines"} == bare
    n = len(full["lines"])
    assert json.loads(s.road_lines([0, n - 1, n])) == [full["lines"][0], full["lines"][n - 1], None]

def test_the_binding_gives_the_facades_page():
    want = json.loads((DATA / "monaco/rust_page.json").read_text())
    # the page's keys come from the call (the area's options), as the facade's test gives them (areas.rs)
    given = {**json.loads(gzip.decompress((DATA / "monaco/golden_options.json.gz").read_bytes()))["args"], "export": True, "state": "live"}
    html = _engine.rust().page_from(pq.read_table(DATA / "monaco/roads.parquet"), _look().with_arg("state", '"live"'), "{}", json.dumps(given))
    assert _text(html) == want["page"]


def test_the_wasm_package_gives_the_same_style_and_road_table():
    """The third language (docs/design/target_architecture.md, (i) item 6): the wasm package in Node gives the same golden
    (rust/roadstyle-wasm/cross_language.mjs; CI runs it in the Rust job). Needs Node and the editor package
    (rust/roadstyle-wasm/build_editor.sh)."""
    root = Path(__file__).resolve().parents[1]
    pkg = Path(os.environ.get("CARGO_TARGET_DIR") or root / "rust" / "target") / "editor-pkg" / "roadstyle_wasm.js"
    if shutil.which("node") is None or not pkg.exists():
        pytest.skip("no node or no editor package (rust/roadstyle-wasm/build_editor.sh)")
    r = subprocess.run(["node", str(root / "rust/roadstyle-wasm/cross_language.mjs"), str(pkg)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

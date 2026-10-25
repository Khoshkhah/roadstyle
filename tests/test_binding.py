"""The Python binding gives the Rust engine's output unchanged (2026-10-24: the Rust API is the design, Python a thin binding): on Monaco,
the style, the road table and the page that the binding gives are the texts that the Rust facade makes, byte for byte. The facade's
texts are in the Rust goldens (rust/roadstyle-rs/tests/data/monaco/rust_style.json, rust_page.json: their size and the first 16 hex
characters of their SHA-256; tests/areas.rs makes them with ROADSTYLE_BLESS=1), from the same inputs: roads.parquet and the look of
golden_options.json.gz."""
import gzip
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

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
    assert _text(s.road_table()) == want["road_table"]["text"]


def test_the_binding_gives_the_facades_page():
    want = json.loads((DATA / "monaco/rust_page.json").read_text())
    html = _engine.rust().page_from(pq.read_table(DATA / "monaco/roads.parquet"), _look().with_arg("state", '"live"'), "{}", "{}")
    assert _text(html) == want["page"]

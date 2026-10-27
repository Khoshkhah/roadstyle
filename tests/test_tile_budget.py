"""The tile size standard (docs/design/tile_contract.md): the Python binding gives Monaco's tiles within the budget of
rust/roadstyle-rs/tests/data/tile_budget.json (the Rust test tile_budget.rs measures the same views), and scripts/tile_budget.py only
lowers limits unless it has --raise and a reason."""
import gzip
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rust/roadstyle-rs/tests/data"
BUDGET = json.loads((DATA / "tile_budget.json").read_text())

spec = importlib.util.spec_from_file_location("tile_budget_script", ROOT / "scripts/tile_budget.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def _fields(b):
    """The fields of a protobuf message: (number, wire type, varint value, bytes)."""
    i, out = 0, []
    while i < len(b):
        k, i = _varint(b, i)
        w = k & 7
        if w == 0:
            v, i = _varint(b, i)
            out.append((k >> 3, w, v, b""))
        elif w == 2:
            n, i = _varint(b, i)
            out.append((k >> 3, w, 0, b[i:i + n]))
            i += n
        else:
            n = 8 if w == 1 else 4
            out.append((k >> 3, w, 0, b[i:i + n]))
            i += n
    return out


def _varint(b, i):
    v = s = 0
    while True:
        x = b[i]
        i += 1
        v |= (x & 0x7F) << s
        s += 7
        if x < 0x80:
            return v, i


def _layers(tile):
    """(name, features, bytes, keys, values) of each layer; the bytes are the layer's share of the tile (tag, length, message)."""
    out = []
    for f, _, _, layer in _fields(tile):
        if f != 3:
            continue
        name, n = "", [0, 0, 0]
        for g, _, _, d in _fields(layer):
            if g == 1:
                name = d.decode()
            elif g in (2, 3, 4):
                n[g - 2] += 1
        head = 1 + math.ceil((len(layer) | 1).bit_length() / 7)
        out.append((name, n[0], head + len(layer), n[1], n[2]))
    return out


def _square(z, lon, lat):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return [(z, x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


@pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")
def test_the_binding_tiles_of_monaco_are_within_the_budget():
    import pyarrow.parquet as pq

    from roadstyle import _engine

    o = json.loads(gzip.decompress((DATA / "monaco/golden_options.json.gz").read_bytes()))
    look = _engine.rust().resolve_look(json.dumps(o)).with_arg("export", "false")
    tiler = _engine.rust().Tiler(pq.read_table(DATA / "monaco/roads.parquet"), look, None, None, "rs://", [])
    budget = BUDGET["areas"]["monaco"]
    lon, lat = budget["center"]
    over = []
    for z in range(12, 16):
        limit, biggest, view_bytes, view_features, layers = budget[f"z{z}"], 0, 0, 0, {}
        most = 0
        for tile in (tiler.tile(*t) for t in _square(z, lon, lat)):
            view_bytes += len(tile)
            biggest = max(biggest, len(tile))
            most = max(most, sum(layer[1] for layer in _layers(tile)))
            for name, f, b, k, v in _layers(tile):
                view_features += f
                e = layers.setdefault(name, [0, 0, 0, 0])
                layers[name] = [max(e[0], f), max(e[1], b), max(e[2], v), max(e[3], k)]
        got = {"view_bytes": view_bytes, "view_features": view_features, "max_tile_bytes": biggest, "max_tile_features": most}
        over += [f"z{z}.{k}: {v} > {limit[k]}" for k, v in got.items() if v > limit[k]]
        assert set(layers) == set(limit["layers"]), f"z{z}: the tile layers are not the budget's"
        for name, nums in layers.items():
            for key, v in zip(("features", "bytes", "values", "keys"), nums, strict=True):
                if v > limit["layers"][name][key]:
                    over.append(f"z{z}.{name}.{key}: {v} > {limit['layers'][name][key]}")
    assert not over, "the binding's tiles are over the budget (docs/design/tile_contract.md):\n" + "\n".join(over)


def test_the_ratchet_lowers_a_limit_and_never_raises_one_alone():
    old = {"areas": {"a": {"z12": {"bytes": 1000, "features": 100}}}}
    new, log = script.update({"a": {"z12": {"bytes": 800, "features": 100}}}, old, False, "")
    assert new["areas"]["a"]["z12"] == {"bytes": script.limit(800), "features": 100}, "lower, and the margin does not creep up"
    assert log["lowered"] and not log["missing"]
    new, log = script.update({"a": {"z12": {"bytes": 1500, "features": 100}}}, old, False, "")
    assert new["areas"]["a"]["z12"]["bytes"] == 1000, "a number over its limit does not raise it"
    assert len(log["missing"]) == 1 and new["raises"] == []
    new, log = script.update({"a": {"z12": {"bytes": 900, "features": 100, "keys": 20}}}, old, False, "")
    assert "keys" not in new["areas"]["a"]["z12"], "a new number needs a raise too"
    assert len(log["missing"]) == 1


def test_a_raise_is_in_the_file_with_its_reason():
    old = {"areas": {"a": {"z12": {"bytes": 1000}}}, "raises": []}
    new, log = script.update({"a": {"z12": {"bytes": 1500}}}, old, True, "a new layer")
    assert new["areas"]["a"]["z12"]["bytes"] == script.limit(1500)
    assert new["raises"][0]["why"] == "a new layer" and new["raises"][0]["changes"] == log["raised"]
    with pytest.raises(SystemExit):
        script.main(["--raise", "--measured", "/dev/null"])          # no --why


def test_a_new_hard_violation_needs_a_raise_and_a_fixed_one_leaves_the_list():
    old = {"areas": {}, "known_over": ["a.z12.max_tile_bytes", "b.z12.max_tile_bytes"]}
    new, log = script.update({"a": {}, "hard_violations": ["a.z13.max_tile_bytes"]}, old, False, "")
    assert new["known_over"] == ["b.z12.max_tile_bytes"], "a is measured: its fixed violation leaves; b was not measured: it stays"
    assert len(log["missing"]) == 1, "a new violation is not added without a raise"
    new, _ = script.update({"a": {}, "hard_violations": ["a.z13.max_tile_bytes"]}, old, True, "a new view")
    assert "a.z13.max_tile_bytes" in new["known_over"]


def test_a_budget_limit_has_a_margin_over_nothing_else():
    assert script.limit(10) == 11 and script.limit(1000) == 1020

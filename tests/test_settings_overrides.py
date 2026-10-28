"""Bundled palette/config data files + user-override layering (roadstyle._settings)."""
import json

import pytest

from roadstyle import _settings


@pytest.fixture
def fresh():
    """Yield, then drop _settings caches so one test's override file can't leak into the next."""
    _settings.refresh()
    yield
    _settings.refresh()


def test_bundled_palettes_present_and_complete(fresh):
    pals = _settings.palettes()
    assert {"highsat", "carto"} <= set(pals)
    # every class entry carries the RoadStyle-required keys (so palette_from_dict won't raise)
    for roads in pals.values():
        for cls, fieldset in roads.items():
            assert {"fill", "width", "casing_width"} <= set(fieldset), cls


def test_bundled_style_has_config_and_selection(fresh):
    st = _settings.style()
    assert "fill_opacity" in st["config"] and "minor_no_casing" in st["config"]
    assert "core" in st["selection"]




def test_user_override_retints_one_class(tmp_path, monkeypatch, fresh):
    # a *partial* per-class override: only service.fill — width/casing_width come from the bundle
    override = tmp_path / "roadstyle.json"
    override.write_text(json.dumps({"palettes": {"highsat": {"service": {"fill": "#123456"}}}}))
    monkeypatch.setenv("ROADSTYLE_CONFIG", str(override))
    _settings.refresh()

    svc = _settings.palettes()["highsat"]["service"]
    assert svc["fill"] == "#123456"          # overridden
    assert "casing_width" in svc and "width" in svc   # merged, not replaced


def test_user_override_config_and_selection(tmp_path, monkeypatch, fresh):
    override = tmp_path / "roadstyle.json"
    override.write_text(json.dumps(
        {"config": {"fill_opacity": 0.5}, "selection": {"core": "#FF0000"}}))
    monkeypatch.setenv("ROADSTYLE_CONFIG", str(override))
    _settings.refresh()

    st = _settings.style()
    assert st["config"]["fill_opacity"] == 0.5
    assert st["selection"]["core"] == "#FF0000"
    assert "casing_opacity" in st["config"]   # untouched keys survive




def test_user_override_roads_tables_deep_merge(tmp_path, monkeypatch, fresh):
    """One defaults.json carries EVERY setting; an override restates only what changes. A roads
    override merges per table entry (and per zoom stop inside a width row) — nothing restated."""
    override = tmp_path / "roadstyle.json"
    override.write_text(json.dumps({"roads": {
        "z_order": {"service": 9},                 # lift one class's draw priority
        "width": {"service": {"18": 8.0}},         # widen one zoom stop of one group
    }}))
    monkeypatch.setenv("ROADSTYLE_CONFIG", str(override))
    _settings.refresh()

    r = _settings.roads()
    assert r["z_order"]["service"] == 9
    assert r["z_order"]["motorway"] == 9           # untouched entries survive
    assert r["width"]["service"][18] == 8.0        # zoom keys are numbers, whatever the file wrote (the theme, 2026-10-19)
    assert r["width"]["service"][15] == 2          # untouched zoom stops survive
    assert "18" not in r["width"]["service"]
    assert r["group"]["motorway"] == "major"       # untouched tables survive



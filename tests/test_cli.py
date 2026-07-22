"""End-to-end smoke tests for the ``roadstyle`` command-line interface."""
import json
from pathlib import Path

import pytest

from roadstyle.cli import main

SAMPLE = Path(__file__).resolve().parent.parent / "notebooks" / "data" / "sundbyberg_edges.gpkg"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample gpkg not present")


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert "roadstyle" in capsys.readouterr().out


def test_missing_input_returns_2(tmp_path):
    assert main([str(tmp_path / "nope.gpkg"), "-o", str(tmp_path / "out.html")]) == 2


@pytest.mark.parametrize("fmt", ["web", "folium", "rsjs", "spec", "geojson"])
def test_each_format_writes_a_file(tmp_path, fmt):
    out = tmp_path / f"map_{fmt}"
    assert main([str(SAMPLE), "-o", str(out), "-f", fmt, "--basemap", "dark_matter"]) == 0


def test_cli_view_3d(tmp_path):
    from roadstyle.cli import main
    out = tmp_path / "m3d.html"
    assert main([str(SAMPLE), "-o", str(out), "-f", "web", "--view-3d", "--bearing", "-20"]) == 0
    html = out.read_text()
    assert "pitch:55" in html and "bearing:-20" in html
    assert out.exists() and out.stat().st_size > 0


def test_spec_output_is_valid_roadstyle_spec(tmp_path):
    out = tmp_path / "spec.json"
    assert main([str(SAMPLE), "-f", "spec", "-o", str(out)]) == 0
    spec = json.loads(out.read_text())
    assert spec["roadstyle"].startswith("spec/")
    assert spec["geojson"]["type"] == "FeatureCollection"


def test_default_output_name_derives_from_input(tmp_path):
    src = tmp_path / "edges.gpkg"
    src.write_bytes(SAMPLE.read_bytes())
    assert main([str(src), "-f", "spec"]) == 0
    assert (tmp_path / "edges.json").exists()


def test_filtering_reduces_edge_count(tmp_path, capsys):
    full = tmp_path / "full.json"
    main([str(SAMPLE), "-f", "spec", "-o", str(full)])
    n_full = len(json.loads(full.read_text())["geojson"]["features"])

    one = tmp_path / "one.json"
    main([str(SAMPLE), "-f", "spec", "-o", str(one), "--include", "residential"])
    n_one = len(json.loads(one.read_text())["geojson"]["features"])
    assert 0 < n_one <= n_full


def test_bad_colors_json_returns_2(tmp_path):
    out = tmp_path / "x.html"
    assert main([str(SAMPLE), "-o", str(out), "--color-by", "highway",
                 "--colors", "{not json}"]) == 2

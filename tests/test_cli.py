"""End-to-end smoke tests for the ``roadstyle`` command-line interface."""
from pathlib import Path

import pytest

from roadstyle.cli import main

SAMPLE = Path(__file__).resolve().parent.parent / "notebooks" / "data" / "sodermalm_edges.gpkg"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample gpkg not present")



def _in(needle, html):
    """A JSON fragment in a page, in either engine's spacing: Python's json.dumps (", ", ": ") or serde_json's compact text."""
    return needle in html or needle.replace(": ", ":").replace(", ", ",") in html


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert "roadstyle" in capsys.readouterr().out


def test_missing_input_returns_2(tmp_path):
    assert main([str(tmp_path / "nope.gpkg"), "-o", str(tmp_path / "out.html")]) == 2


@pytest.mark.parametrize("fmt", ["web"])
def test_each_format_writes_a_file(tmp_path, fmt):
    out = tmp_path / f"map_{fmt}"
    assert main([str(SAMPLE), "-o", str(out), "-f", fmt, "--basemap", "dark_matter"]) == 0


@pytest.mark.parametrize("page,marker", [("dashboard", '<div id="sb"'), ("report", '<div id="rp"'),
                                         ("street-view", '<div id="sv"')])
def test_page_writes_that_page(tmp_path, page, marker):
    out = tmp_path / "page.html"
    assert main([str(SAMPLE), "-o", str(out), "--page", page]) == 0
    assert marker in out.read_text()


def test_street_view_page_flags(tmp_path):
    out = tmp_path / "sv.html"
    assert main([str(SAMPLE), "-o", str(out), "--page", "street-view",
                 "--panel-width", "55", "--no-resize"]) == 0
    h = out.read_text()
    assert "--sv-w: 55%;" in h and '<div id="sv-drag"' not in h
    assert main([str(SAMPLE), "-o", str(out), "--page", "street-view", "--layout", "below"]) == 0
    assert 'data-layout="below"' in out.read_text()



def test_cli_view_3d(tmp_path):
    from roadstyle.cli import main
    out = tmp_path / "m3d.html"
    assert main([str(SAMPLE), "-o", str(out), "-f", "web", "--view-3d", "--bearing", "-20"]) == 0
    html = out.read_text()
    assert _in('"pitch": 55, "bearing": -20', html)
    assert out.exists() and out.stat().st_size > 0



def test_default_output_name_derives_from_input(tmp_path):
    src = tmp_path / "edges.gpkg"
    src.write_bytes(SAMPLE.read_bytes())
    assert main([str(src)]) == 0
    assert (tmp_path / "edges.html").exists()



def test_bad_colors_json_returns_2(tmp_path):
    out = tmp_path / "x.html"
    assert main([str(SAMPLE), "-o", str(out), "--color-by", "highway",
                 "--colors", "{not json}"]) == 2

"""studio.common sample resolution — repo copy from a checkout, full-set download from a wheel."""
import urllib.request
from pathlib import Path

from roadstyle.studio import common


def test_source_checkout_uses_repo_copy_no_download(monkeypatch):
    """Running from this clone: the sample resolves to the repo file, no network touched."""
    def boom(*a, **k):
        raise AssertionError("must not download when the repo copy exists")

    monkeypatch.setattr(urllib.request, "urlretrieve", boom)
    p = common.sample_path("zones.geojson")
    assert p == common._REPO_SAMPLES / "zones.geojson"
    assert p.exists()


def test_wheel_install_downloads_full_set_once(tmp_path, monkeypatch):
    """No repo copy (wheel install): first use pulls the FULL package, each file once, then caches."""
    monkeypatch.setattr(common, "_REPO_SAMPLES", tmp_path / "absent")   # simulate a wheel layout
    monkeypatch.setattr(common, "_CACHE", tmp_path / "cache")
    calls = []

    def fake_urlretrieve(url, dest):
        calls.append(url)
        Path(dest).write_text("{}")

    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

    p = common.sample_path("zones.geojson")
    assert p == tmp_path / "cache" / "zones.geojson"
    assert sorted(calls) == sorted(common._RAW + fn for fn in common.ALL_SAMPLES)

    calls.clear()
    common.sample_path("sodermalm_walking.geojson")     # all cached now → no re-download
    assert calls == []

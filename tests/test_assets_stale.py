"""roadstyle._assets.stale: the files whose copy in the Rust extension is not the checkout's, and the warning of the first file read.
A page takes the dashboard's files from the extension, so an extension built before a pull or an edit gives an old dashboard."""
import warnings

import pytest

from roadstyle import _assets

NAME = "static/popup.js"


def _folder(tmp_path, data: bytes, name: str = NAME):
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_bytes(data)
    return tmp_path


def test_the_same_file_is_not_stale(tmp_path):
    assert _assets.stale(_folder(tmp_path, _assets.data(NAME))) == []


def test_a_changed_file_is_stale(tmp_path):
    assert _assets.stale(_folder(tmp_path, _assets.data(NAME) + b"\n// changed")) == [NAME]


def test_a_file_the_extension_does_not_have_is_stale(tmp_path):
    assert _assets.stale(_folder(tmp_path, b"x", "static/dashboard/new_part.js")) == ["static/dashboard/new_part.js"]


def test_no_folder_no_check(tmp_path):
    assert _assets.stale(tmp_path / "no such folder") == []


def test_the_first_read_warns_once(tmp_path, monkeypatch):
    monkeypatch.setattr(_assets, "FILES", _folder(tmp_path, _assets.data(NAME) + b"\n// changed"))
    monkeypatch.setattr(_assets, "_checked", False)
    with pytest.warns(UserWarning, match=r"older files .*popup\.js.*build\.py"):
        _assets._rust()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _assets._rust()       # a second time: no warning


def test_this_checkout_is_not_stale():
    """The extension of this checkout is built from its files (CI builds it; locally: python rust/roadstyle-py/build.py)."""
    if not _assets.FILES.is_dir():
        pytest.skip("an installed wheel: no source folder")
    assert _assets.stale() == []

"""roadstyle's files: the look's profiles and palettes, the base map's files, ``cmaps.json``, ``basemaps.json``, the dashboard's JS and
CSS, the popup files, the page templates and MapLibre. Their one copy is the Rust crate roadstyle-assets
(``rust/roadstyle-assets/files/``); Python has no copy and asks the extension for a file by its name, the path under that folder
(``"data/cmaps.json"``, ``"static/popup.js"``)."""
from __future__ import annotations

import os
import warnings
from functools import cache
from pathlib import Path

#: ``rust/roadstyle-assets/files`` of a source checkout. An installed wheel has no such folder, and then nothing is compared.
FILES = Path(__file__).resolve().parents[2] / "rust" / "roadstyle-assets" / "files"
_checked = False


def _ext():
    try:
        from . import _rust as r
    except ImportError as e:
        raise ImportError("roadstyle's files are in its Rust extension (roadstyle._rust), which is not built: pip install roadstyle, or "
                          "in a source checkout: python rust/roadstyle-py/build.py") from e
    return r


def _rust():
    """The extension. The first call of a process in a source checkout compares the extension's files with the checkout's (``stale``)
    and warns when they differ: a page takes the dashboard's files from the extension, so an extension built before a pull or an edit
    gives a page with the old dashboard, and nothing else tells."""
    global _checked
    r = _ext()
    if not _checked:
        _checked = True
        old = stale()
        if old:
            warnings.warn(f"roadstyle: the Rust extension (roadstyle._rust) was built from older files than {FILES}: {len(old)} differ or "
                          f"are missing ({', '.join(old[:3])}{', ...' if len(old) > 3 else ''}). Pages get the old files, an old dashboard. "
                          "Rebuild it: python rust/roadstyle-py/build.py", stacklevel=3)
    return r


def stale(files: str | os.PathLike | None = None) -> list[str]:
    """The names of the files whose copy in the extension differs from the file in ``files`` (default ``FILES``, the checkout's
    folder), then the names of the files in ``files`` that the extension does not have. Empty when the folder does not exist (an
    installed wheel)."""
    root = FILES if files is None else Path(files)
    if not root.is_dir():
        return []
    r = _ext()
    have = r.asset_names()
    known = set(have)
    differ = [n for n in sorted(have) if (root / n).is_file() and r.asset(n) != (root / n).read_bytes()]
    new = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.relative_to(root).as_posix() not in known)
    return differ + new


@cache
def data(name: str) -> bytes:
    """The bytes of a file; a ValueError for a name that is not a file."""
    return _rust().asset(name)


@cache
def text(name: str) -> str:
    """The text of a UTF-8 file."""
    return data(name).decode("utf-8")


def names(prefix: str = "") -> list[str]:
    """The names of the files that start with ``prefix``, sorted."""
    return [n for n in _rust().asset_names() if n.startswith(prefix)]

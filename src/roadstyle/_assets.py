"""roadstyle's files: the look's profiles and palettes, the base map's files, ``cmaps.json``, ``basemaps.json``, the dashboard's JS and
CSS, the popup files, the page templates and MapLibre. Their one copy is the Rust crate roadstyle-assets
(``rust/roadstyle-assets/files/``); Python has no copy and asks the extension for a file by its name, the path under that folder
(``"data/cmaps.json"``, ``"static/popup.js"``)."""
from __future__ import annotations

from functools import cache


def _rust():
    try:
        from . import _rust as r
    except ImportError as e:
        raise ImportError("roadstyle's files are in its Rust extension (roadstyle._rust), which is not built: pip install roadstyle, or "
                          "in a source checkout: python rust/roadstyle-py/build.py") from e
    return r


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

"""Themes: the casing variant to use + a default base map. Base maps live in basemaps.py."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    casing: str              # "light" or "dark" — which RoadStyle casing colour to use
    default_basemap: str     # key into basemaps.BASEMAPS


THEMES: dict[str, Theme] = {
    "light": Theme("light", "light", "voyager"),
    "dark": Theme("dark", "dark", "dark_matter"),
    "satellite": Theme("satellite", "dark", "satellite"),
}


def get_theme(theme: str | Theme) -> Theme:
    if isinstance(theme, Theme):
        return theme
    try:
        return THEMES[theme]
    except KeyError as err:
        raise ValueError(f"unknown theme {theme!r}; choose from {list(THEMES)}") from err


def register_theme(theme: Theme) -> None:
    """Register (or replace) a theme, keyed by its ``name``."""
    if not isinstance(theme, Theme):
        raise TypeError(f"expected a Theme, got {type(theme).__name__}")
    THEMES[theme.name] = theme

"""Themes: the casing variant to use + a default base map. Base maps live in basemaps.py."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    casing: str              # "light" or "dark" — which RoadStyle casing colour to use
    default_basemap: str     # key into basemaps.BASEMAPS


THEMES: dict[str, Theme] = {
    "light": Theme("light", "light", "positron"),
    "dark": Theme("dark", "dark", "dark_matter"),
    "satellite": Theme("satellite", "dark", "satellite"),
}


def get_theme(theme: str | Theme) -> Theme:
    if isinstance(theme, Theme):
        return theme
    try:
        return THEMES[theme]
    except KeyError:
        raise ValueError(f"unknown theme {theme!r}; choose from {list(THEMES)}")

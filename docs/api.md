# API

## `render_edges(gdf, *, …)`
Filter (by `include`/`exclude`) then render. Returns a `folium.Map` or `lonboard.Map`.
See [Usage](usage.md) for all parameters.

## Filtering — `roadstyle.filters`
- `filter_edges(gdf, include=None, exclude=None, highway_col="highway", match_links=True)` —
  subset by highway type. `include` applied before `exclude`. Returns a copy.
- `highway_types(gdf, highway_col="highway", normalize=True)` — sorted unique types present.

## Style resolution — `roadstyle.style`
- `resolve(highway, palette="highsat", theme="dark", tunnel=False, bridge=False) -> ResolvedStyle`
  — the concrete style for one edge.
- `base_style(highway, palette="highsat") -> RoadStyle` — the palette entry (before theme/overrides).
- `normalize_highway(highway) -> (base_class, is_link)`.
- `selection_style(theme="dark", base_width=4.0) -> dict` — `{"glow", "casing", "core"}` layers.

```python
@dataclass
class ResolvedStyle:
    fill: str
    width: float
    casing: str | None
    casing_width: float
    dash: tuple[int, int] | None
    opacity: float
```

## Palettes & themes
- `PALETTES: dict[str, dict[str, RoadStyle]]` — `"highsat"` and `"carto"`.
- `HIGHSAT`, `CARTO` — the individual palette dicts.
- `SELECTION` — neon-violet selection colours/widths.
- `RoadStyle` — `(fill, width, casing_width, casing_light, casing_dark, dash, opacity)`.
- `THEMES: dict[str, Theme]`, `Theme`, `get_theme(name)`.
- `BASEMAPS: dict[str, Basemap]`, `Basemap`, `get_basemap(key)` — tile providers
  (`positron`, `dark_matter`, `voyager`, `osm`, `esri_gray`, `satellite`). Use via
  `render_edges(..., basemap=...)` or `basemaps=[...]` (folium toggleable layers).

## Renderers (called via `render_edges`)
- `roadstyle.render_folium.render(gdf, palette, theme, highway_col, tunnel_col, bridge_col, tooltip, selected, name, **map_kwargs)`
- `roadstyle.render_lonboard.render(gdf, palette, theme, highway_col, tunnel_col, bridge_col, **map_kwargs)`

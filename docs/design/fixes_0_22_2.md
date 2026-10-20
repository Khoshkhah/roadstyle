# Fixes for 0.22.2

**Status:** done on branch `fix-0.22.2` (2026-10-20), not released. They come from the work on duckOSM's level tables and mapstyle's one-mode map.

## What goes into 0.22.2

| # | Fix | Why |
|---|---|---|
| A | The level tables of a database (`b326169`: `visualization.level_edits`, `level_heads`, `level_caps`, `restore_area_inputs`) | duckOSM needs them: the database holds all your edits |
| 1 | A solve keeps a table when the folder has no file for it | A folder without `heads.csv` deleted `level_heads`: your edits were lost |
| 3 | `load_area_levels(subset=True)` | A map of one mode reads the order solved for all modes |
| 2 | The arrow scale comes from the zoom and the latitude | The 3D view kept a few arrows (9 flat, 0 tilted in the test) |
| 4 | `__version__` of a source tree is its `pyproject.toml` version | `edge_levels_meta.roadstyle_version` and bug reports said 0.17.1 |
| 8 | A test that needs `mapbox_vector_tile` skips without it | Two tests failed on a clean install |

## Not in 0.22.2

- **Tables are text on purpose** (the text as it was, ids BIGINT): `level_heads.start_m` is `'23.2'`. Not changed.
- **An overlay hover that highlights every feature with the same number** (the editor with mapstyle's layers: all buildings turned violet). The cause is not found; mapstyle sets `popup=[]` on its layers.
- **A colour base that `rsColor` keeps** (the editor's picked-road colour replaces other colours). mapstyle wraps `rsColor` in the page.
- The config files (5 commits), the style export (3) and the GeoLibre plugin (12) stay on the branch `geolibre`.

## After the release (other projects)

- mapstyle: `stored_levels` can use `subset=True`, and `layers.js` can drop its arrow-scale code (the `_RS_ARROW` thresholds on `move`).
- duckOSM: `levels` extra `roadstyle>=0.22.2`.

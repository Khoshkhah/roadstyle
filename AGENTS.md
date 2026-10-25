# roadstyle — guide for AI coding agents

roadstyle turns a GeoDataFrame of road edges into one self-contained, interactive HTML map
(MapLibre, data inlined, works offline), with a `window.rs*` JavaScript API for host pages.

**Using the library** (the one call, the data contract, the JS API, the traps):
[skills/roadstyle/SKILL.md](skills/roadstyle/SKILL.md). Read it before writing code that calls
roadstyle. Every keyword with its default: `docs/reference/parameters.md`; the full JS API:
`docs/reference/javascript.md`. This file covers working *on* the repo.

## Setup and tests

```bash
conda activate roadstyle            # or: pip install -e ".[dev]"
pytest                              # ~200 tests, ~20 s; browser tests need `pip install playwright`
```

A consumer project that does not install it runs with `PYTHONPATH=<this repo>/src`.

## Changing the library

- roadstyle's files (the profiles and palettes, the base map's files, `cmaps.json`, `basemaps.json`, the dashboard, the popup, the
  page templates, MapLibre) have one copy: `rust/roadstyle-assets/files/`, the crate roadstyle-assets. A crate takes a file with
  `roadstyle_assets::text!("data/cmaps.json")` (a wrong name does not compile); Python asks `roadstyle._assets.text(name)`, which
  needs the built extension (`python rust/roadstyle-py/build.py`). Edit the files there. After an edit in `files/static/`, run
  `python rust/roadstyle-assets/sync_old_paths.py`: it writes the old paths that duckosm-rust copies (until 0.27.0).
- `src/roadstyle/render_web.py` — `render(...)`: Python keywords become the `page` dict, which `_page_html` writes as one
  JSON object `RS_OPTIONS` (the placeholder `__RS_OPTIONS__` of `rust/roadstyle-assets/files/static/web_template.html`).
- The page's controls and road interaction are ES modules in `rust/roadstyle-assets/files/static/dashboard/` (one file for each control,
  `index.js` is the entry `rsDashboard(map, options)`); the Rust-engine pages import them, and `render_web.py` puts them in the
  page as one script (in the order of `static/dashboard/files.txt`, which the Rust page writer reads too, without `import` lines and
  `export` words). A new module: a line in `files.txt`. A top-level name must be unique in the folder.
  Design: `docs/design/dashboard_module.md`.
- A new web option = the keyword + a key in `render`'s `page` dict and in `PageOptions` (`rust/roadstyle/src/page.rs`, built by
  `page_options::page_from`; a page-only keyword's default goes in its `DEFAULTS`) + its default in
  `dashboard/index.js` + the module that reads `O.<key>` + a test in `tests/test_render_web.py` (`_opt(html, key)`) + a row in
  `docs/reference/parameters.md`, `docs/reference/javascript.md` and `docs/design/dashboard_module.md` + CHANGELOG. If agents
  calling the library need to know it, also `skills/roadstyle/SKILL.md`.
- `render_edges` takes `**kwargs`, so a misspelt keyword is silently ignored: look for the key in `RS_OPTIONS`
  (`_opt(html, key)`) when a new option seems to do nothing.
- The road popup and hover tooltip text: `_rfields` (popup/tooltip, `static/popup.js`) and `_rrows` (docked panel,
  `dashboard/select.js`); Street View: `_svMeasure` / `_svAt` (the spot on the edge, metres along it), `_svPick` / `_svUrl` / `_svUrlOf`, the marker `_svMark` / `_svMarkPlace` / `_svLanePx`, the window `rsSetStreetView`.
- Google's script is loaded once for every window by `_gmLoad(key)`; a floating window (drag, size, place, remembered)
  is `_rsFloat(w, bar, name, left)`. Google 3D (`google_3d=True`, `dashboard/google3d.js`): `toGoogle` / `toMap` convert the
  cameras (zoom <-> range from MapLibre's camera distance), `there` stops echo loops, the map is the judge (it clamps,
  Google goes back), `ground` reads the ground height from Terrain Tiles (Google's center is above sea level), `pad`
  moves the map's center beside the window. Check a change on a hill (Monaco), not only on flat Södermalm.
- Every style value is in a config file (docs/design/style_config.md): colors in `rust/roadstyle-assets/files/data/palettes/*.yaml`, all else in
  `rust/roadstyle-assets/files/data/profiles/default.yaml`. Read them merged with `THEME[...]` in `render_web.py` or `_settings.theme_value(path)`
  elsewhere, never as a literal. `tests/test_theme.py` fails on a color literal and on a color in a profile. A new style value = a
  key in the profile or in every palette (with its comment) + the code that reads it.
- The JS side has no unit tests. Check a rendering change in a real browser: `rs.snapshot(m,
  "x.png")` and look at the PNG, or drive the page with Playwright.
- Gallery and README images: screenshots taken by hand (see `docs/build_gallery.py`, which still makes the report picture).

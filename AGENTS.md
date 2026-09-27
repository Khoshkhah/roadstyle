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

- `src/roadstyle/render_web.py` — `render(...)`: Python keywords become `__PLACEHOLDER__`
  replacements in `src/roadstyle/static/web_template.html` (one `.replace` chain near the end).
- A new web option = the keyword + its `.replace` + a `const` in the template + a test in
  `tests/test_render_web.py` + a row in `docs/reference/parameters.md` and `docs/reference/javascript.md` +
  CHANGELOG. If agents calling the library need to know it, also `skills/roadstyle/SKILL.md`.
- `render_edges` takes `**kwargs`, so a misspelt keyword is silently ignored: grep the template
  for its placeholder when a new option seems to do nothing.
- The road popup and hover tooltip text: `_rfields` (popup/tooltip) and `_rrows` (docked panel)
  in the template; Street View: `_svMeasure` / `_svAt` (the spot on the edge, metres along it), `_svPick` / `_svUrl` / `_svUrlOf`, the marker `_svMark` / `_svMarkPlace` / `_svLanePx`, the window `rsSetStreetView`.
- The JS side has no unit tests. Check a rendering change in a real browser: `rs.snapshot(m,
  "x.png")` and look at the PNG, or drive the page with Playwright.
- Gallery and README images: `python docs/build_gallery.py`.

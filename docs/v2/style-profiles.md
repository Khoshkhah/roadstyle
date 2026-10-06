# v2 style profiles

A style profile sets the widths, casings and colours of a v2 visualization. Use a different
profile per use (a lane-accurate pair editor, a wide presentation map, ...) without touching code.

Choose one with a bundled name (`default`, `compact`), a path to your own JSON file, or a dict:

```bash
python scripts/v2/pair_override_dashboard.py --style compact
python scripts/v2/build_road_levels.py --style my_style.json
```

```python
OSMAdapter.from_dataframe(df, profile="compact")
```

A file restates only what it changes; the rest comes from `default`
(`src/roadstyle/v2/profiles/default.json`).

| Key | Meaning |
|---|---|
| `lane_width_m` | metres per lane when a way has `lanes` but no `width` tag (3.5) |
| `lane_width_by_class` | per-highway override, e.g. `{"service": 3.0}` |
| `width_sources` | order tried to size a road: `width` (OSM tag), `lanes`, `class` |
| `class_width_m`, `default_width_m` | width by highway class, used when no earlier source applies |
| `casing_m` | `{"default": [left, right], "motorway": [0.4, 0.2]}` in metres |
| `colors`, `default_color` | fill colour by highway class |
| `roundabout_priority` | junction priority value for roundabout ways |
| `priority_order` | drawing tiers, highest first: `roundabout`, `tunnel`, `highway` |
| `split_m` | casing head length at each road end |

With the default `width_sources`, a road with a `lanes` tag uses `lanes × lane width` and the class
table only applies to roads without `lanes`. Put `class` first to size by class instead.
`priority_order` is applied to derived casing and fill levels after solving; it does not change the
input `band`. Highway classes keep their within-tier class order.

Widths do not change the solved levels (they depend on geometry and pair tables), so a profile can
be switched without rebuilding `road_levels.csv`.

## One source of truth

When you pass `--style`, width, casing and colour come from that profile. The saved map HTML
(`--map-html`) contributes non-visual tags (`name`, `lanes`, `layer`, ...) while its visual
properties are ignored. With `--style` omitted, the dashboard keeps the saved map HTML's visual
properties so it opens with the same appearance as the source map.

A profile may set `"extends": "<bundled name or path>"` and override only what differs
(default: `default`). Bundled: `default` (the generic palette), `map` (the palette and
0.25 m casing of the saved Monaco map) and `compact`
(`map` with narrower service and residential lanes), `night` (bright palette for dark basemaps) and `realistic` (real-world lane widths per class, thin casings, wider left casing on motorways). The profile also takes `casing_color`.

The pair dashboard keeps the map HTML's existing appearance when `--style` is omitted. Pass
`--style map`, a bundled profile name, or a JSON path to explicitly use a profile.

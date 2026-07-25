# Emit GeoJSON from DuckDB instead of GeoPandas

## Problem

Every GeoJSON-consuming backend builds its payload the same way:

```python
gj = bake_props(json.loads(g.to_json()), rf)
```

`g.to_json()` walks a GeoDataFrame through shapely objects and writes the text in Python;
`json.loads` then parses that text straight back into Python dicts so `bake_props` can staple the
per-edge `__rs_*` style properties onto each feature.

Six call sites: `render_web.py:913,922`, `emit.py:93,101`, `render_folium.py:88`,
`overlays.py:61` (plus `mapstyle/render_folium.py:34,65`).

## Data

Measured 2026-07-24, `stockholm_county.duckdb` / `driving.edges`, 456,813 edges:

| step | cost |
|------|------|
| DuckDB query + fetch | 190 ms |
| WKB → shapely → GeoDataFrame | 225 ms |
| `gdf.to_json()` | **7,144 ms** |
| `json.loads(...)` on the result | **1,650 ms** |
| **DuckDB `ST_AsGeoJSON` + `json_group_array` (C++)** | **920 ms** |

7.8× on the serialisation step, producing the same GeoJSON. Payload is 148 MB either way.

## Approach (as shipped)

**Swap only the serialiser.** `fastjson.fc_dict(gdf)` is a drop-in for
`json.loads(gdf.to_json())`: DuckDB gets the frame's WKB + attribute columns and emits **one
feature string per row** (a plain `ORDER BY` guarantees feature order), Python joins them and
parses once. `bake_props` / `bake_color_options` keep mutating the parsed dict exactly as before
— zero contract change, which removes the risk this doc originally flagged as its biggest.

Equivalence corners found while pinning `fc_dict == json.loads(gdf.to_json())`:

- **float32 must be upcast to float64 before registration** — GeoPandas emits
  `float(np.float32(94.2))` = `94.19999694824219`; DuckDB would print the shorter REAL repr.
- feature `id` is `str(index)` (any index type), features carry no bbox, NaN/None/`pd.NA` → null.
- `to_json(list(... ORDER BY ...))` (the json_group_array route) builds one 309 MB string in one
  thread — 3 s slower than per-row emit + Python join.
- GeoPandas `to_json` **crashes on datetime columns** (`TypeError: Timestamp is not JSON
  serializable`), so there is no datetime behaviour to mirror.
- `duckdb` stays an optional extra: `fc_dict` falls back to GeoPandas on ImportError silently,
  and on any fast-path error with a RuntimeWarning — a render can never break because of it.

Measured, county (456,813 edges, all columns): old 19.7 s → new ~6.4 s (**~3×**). Remaining
floor is `json.loads` of a ~300 MB payload (~4 s) — see Rejected.

## Rejected

- **Props as columns before the query** (this doc's original approach) — pointless once the
  consumers are read: `_mark_twoway`, `_mark_lvl`, `_stringify_unsafe_ints`, `build_pmtiles` and
  the spec dict all need the parsed dict anyway, so the parse cannot disappear. Moving `__rs_*`
  attachment into columns would rewrite the `bake_props` contract for zero additional saving.
- **Dropping the parse by making consumers accept raw JSON strings** — would recover the last
  ~4 s but rewrites every downstream consumer. Not worth the blast radius; recorded as the known
  ceiling.
- **Skip only `json.loads`, keep `to_json()`** — forfeits the 7 s serialiser win for the 1.6 s
  parse; backwards.
- **Vector tiles instead** — `tiles.py` solves the *client-side* problem and composes with this:
  `build_pmtiles(fc: dict)` consumes the same parsed FeatureCollection, so the tile path gains
  the same ~3× on its input build.

## Impact

- New module `src/roadstyle/fastjson.py`; call sites swapped in `emit.py` (×2), `render_web.py`
  (×2), `render_folium.py` (×1). `overlays.py:61` left on GeoPandas deliberately — arbitrary
  small user gdfs, not a bottleneck. mapstyle's two copies are a separate repo change.
- `bake_props` / `bake_color_options` and everything downstream untouched.

## Test

`tests/test_fastjson.py` — `fc_dict(g) == json.loads(g.to_json())` pinned on: hostile column
names/values, float32/NaN/None/`pd.NA`/bool/BIGINT/list columns, non-range mixed index (feature
ids), full-precision random coordinates, mixed geometry types, empty frame; plus fallback
behaviour (fast-path failure warns and still returns the GeoPandas result).

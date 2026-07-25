# Vectorise style resolution (drop the per-row `iterrows` loops)

## Problem

`render_lonboard._arrays` resolves style **per row**, with `gdf.iterrows()`:

```python
for _, row in gdf.iterrows():
    rs = resolve(row.get(highway_col), palette=palette, tunnel=..., bridge=...)
```

It is called twice per render (casing, then fill), so an N-edge map performs `2N` `iterrows`
materialisations and `2N` `resolve()` calls. `_arrays_from_frame` (the data-driven path) has the
same shape — a Python `for i in range(n)` over the ResolvedFrame.

## Data

Measured 2026-07-24, `stockholm_county.duckdb` / `driving.edges`:

| edges | style (`iterrows` ×2) | geometry (`PathLayer.from_geopandas`) | ratio |
|-------|----------------------|---------------------------------------|-------|
| 5,000 | 205 ms | 46 ms | 4× |
| 50,000 | 2,030 ms | 92 ms | 22× |
| 456,813 (extrapolated, linear) | **~18.5 s** | ~500 ms | ~37× |

Styling is linear in edge count; geometry is nearly flat. The lonboard backend is dominated by
style resolution, not by moving geometry.

The decisive fact: `resolve()` depends only on `(highway, tunnel_truthy, bridge_truthy)` and the
palette. **The entire county contains 44 distinct such keys.** We currently make 913,626 calls to
produce 44 distinct answers.

## Approach

Resolve once per distinct key, then map back:

1. Build a key Series from the three columns (`highway`, truthy `tunnel`, truthy `bridge`).
2. `resolve()` once per unique key (≤ ~50 calls in practice, bounded by palette × 4).
3. Map each unique key to its `(rgba, width)` for casing and fill.
4. Materialise the two numpy arrays by indexing, not appending.

`_arrays_from_frame` cannot use the key trick — data-driven values (continuous colormaps) can
differ per edge — so it instead caches the hex→RGBA conversion per distinct (colour, opacity)
pair and writes into preallocated arrays. Categorical styling collapses to a handful of cache
entries; a fully continuous ramp degrades gracefully to one entry per edge, no worse than before.

Behaviour is unchanged by construction: same `resolve()`, same inputs, same outputs — only the
number of calls changes. That makes it testable as an exact equality against the current
implementation.

## Rejected

- **`PathLayer.from_duckdb()`** — this was the original proposal. It removes the GeoDataFrame
  from the geometry path and measured 1.8× end-to-end *in isolation*. But geometry is 92 ms of a
  2,122 ms render at 50k edges; fixing it cannot yield more than ~4%. It also forces an API change
  (callers hold a GeoDataFrame, not a DuckDB relation) and the styling loops need the frame in
  Python anyway. Not worth it, and not the bottleneck.
- **Caching `resolve()` with `functools.lru_cache`** — a one-line change that would capture most of
  the win, since the key space is tiny. Rejected because the `iterrows()` materialisation itself is
  a large part of the cost (it builds a Series per row); caching leaves that in place. Worth
  measuring as a fallback if the vectorised version proves fiddly.

## Impact

- `src/roadstyle/render_lonboard.py` only. No API change, no change to any other backend.
- The web and folium backends resolve style through different code and are untouched.
- Risk is low and bounded: identical inputs to `resolve()`, verified by an equality test against
  the current output on a real network.

## Test

`tests/test_lonboard_style_arrays.py` — build both arrays the old way and the new way on a fixture
with every `highway` class plus bridge/tunnel variants, assert exact `numpy` equality for casing
and fill, colours and widths.

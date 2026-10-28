# The Rust engine

<p class="lead">roadstyle has one engine, written in Rust. Python is only a thin binding to it.</p>

The Rust engine makes the style of a map, its vector tiles, the drawing levels and the HTML page. It is in the roadstyle wheel
on PyPI, so `pip install roadstyle` gives it to you. A source install needs a Rust toolchain.

```python
rs.render_edges(edges)
```

The same engine is also a WebAssembly package for the browser, and a set of Rust crates.

<div class="grid cards" markdown>

-   :material-school-outline:{ .lg .middle } **Tutorial**

    ---

    Draw Monaco and put its roads in vector tiles.

    [:octicons-arrow-right-24: Your first map with the Rust engine](first-map.md)

-   :material-swap-horizontal:{ .lg .middle } **How-to guides**

    ---

    [Use roadstyle in the browser](browser.md) ·
    [Make tiles and PMTiles](tiles.md) ·
    [Build from source](build.md)

-   :material-table:{ .lg .middle } **Reference**

    ---

    [The `rs` object](../reference/javascript.md#the-rs-object) ·
    [Interaction contract](../reference/contract.md) ·
    [Inputs and outputs](../reference/formats.md)

-   :material-lightbulb-outline:{ .lg .middle } **Explanation**

    ---

    [Architecture of the Rust version](architecture.md) ·
    [How a map is drawn](drawing.md) ·
    [How the levels are solved](levels-solver.md)

</div>

## What it is good for

- **Large networks.** On Tartu (64,828 roads) the page takes 6.1 s. With `tiles=True` it takes 13.4 s.
- **Nightly pages.** The output is the same for the same input: the same style, options and data.
- **The browser.** A page can make the style and the tiles itself, from a duckOSM file or a GeoParquet file, with no Python.

The `folium` and `lonboard` backends are not part of the engine: they draw with Python. A `Styler` object (`style=`) is for them only.

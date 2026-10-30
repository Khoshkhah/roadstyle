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
    [Tiling: one algorithm and one protocol](../design/tiling.md) ·
    [How the levels are solved](levels-solver.md)

</div>

## What it is good for

- **Large networks.** The page keeps the roads as vector tiles by default (MLT, one rule for every path). On Nacka (22,191 roads) the tiled page is 20 MB, and the page with GeoJSON roads draws 2.4 to 2.6 times the triangles at zoom 11 to 13.
- **Nightly pages.** The output is the same for the same input: the same style, options and data.
- **The browser.** A page can make the style and the tiles itself, from a duckOSM file or a GeoParquet file, with no Python.


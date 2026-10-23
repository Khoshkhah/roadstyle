# The Rust engine

<p class="lead">roadstyle 0.25 has a second engine, written in Rust. It makes the same maps as the Python engine, 3 to 12 times faster.</p>

The Rust engine makes the style of a map, its vector tiles, the drawing levels and the HTML page. It is in the roadstyle wheel
on PyPI, so `pip install roadstyle` gives you both engines. The default engine is Python. You select the Rust engine for each
call or for the whole process:

```python
rs.render_edges(edges, engine="rust")     # one call
```

```bash
export ROADSTYLE_ENGINE=rust              # every call in this process
```

The same engine is also a WebAssembly package for the browser, and a set of Rust crates.

<div class="grid cards" markdown>

-   :material-school-outline:{ .lg .middle } **Tutorial**

    ---

    Draw Monaco with the Rust engine, compare it with the Python engine and measure the time.

    [:octicons-arrow-right-24: Your first map with the Rust engine](first-map.md)

-   :material-swap-horizontal:{ .lg .middle } **How-to guides**

    ---

    [Switch the engine](switch-engine.md) ·
    [Use roadstyle in the browser](browser.md) ·
    [Make tiles and PMTiles](tiles.md) ·
    [Build from source](build.md)

-   :material-table:{ .lg .middle } **Reference**

    ---

    [Keywords by engine](keywords.md) ·
    [The `rs` object](../reference/javascript.md#the-rs-object) ·
    [Interaction contract](../reference/contract.md)

-   :material-lightbulb-outline:{ .lg .middle } **Explanation**

    ---

    [Architecture of the Rust version](architecture.md) ·
    [Parity and speed](parity.md)

</div>

## When to use it

- **Large networks.** On Tartu (64,828 roads) the page takes 6.2 s with Rust and 19.1 s with Python. With `tiles=True` it takes
  12.2 s and 147.5 s ([Parity and speed](parity.md)).
- **Nightly pages.** The output is the same as the Python output, byte for byte, so you can change the engine without a change
  to your pages.
- **The browser.** A page can make the style and the tiles itself, from a duckOSM file or a GeoParquet file, with no Python.

The Rust engine does not do everything that the Python engine does. For example, the `folium` and `lonboard` backends and a
`Styler` object (`style=`) stay in Python. [Keywords by engine](keywords.md) gives the state of each keyword.

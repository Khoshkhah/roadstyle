# Which road is on top

<p class="lead">Every edge gets two numbers, the position where its outline is drawn and the position where its road is drawn, and the map is drawn by those two numbers alone.</p>

![A secondary road on a bridge, drawn over a primary road](../img/levels-bridge.png)

The yellow secondary road crosses the orange primary road on a bridge. By road class the primary road would win; by position the
bridge does. Nothing else decides.

=== "Python"

    ```python
    rs.render_edges(edges).save("map.html")    # the positions are computed for you
    ```

## The rule

- Every edge has a **casing position** and a **fill position**: whole numbers, 0 is the ground, null counts as 0.
  If the casing number is higher than the fill number, they are swapped.
- The map is drawn position by position, lowest first. **At each position every outline is drawn first, then every road.**
- So two edges that share a node, whose `[casing, fill]` ranges overlap, merge without a ring: each outline lies under the other's road.
- An edge whose positions are all higher than another's is drawn completely over it, outline included: an overpass.
- An edge with a low casing position and a higher fill position (a bridge edge that touches the ground) has its outline with the ground roads it joins, and its road over them.

**Nothing else orders the drawing**: not the road class, not `layer`, `bridge` or `tunnel`. They are only inputs of the program that
computes the positions. A bridge keeps its look (heavier black casing), a tunnel its look (faded, dashed). Two edges at the *same*
position are drawn in no set order.

## Where the positions come from

`render_edges(edges)` calls `rs.compute_levels(edges, method="solve", order="class")`: a minimum-cost flow (OR-tools; HiGHS through scipy when a wish must be given up)
over the `layer`, `bridge` and `tunnel` tags, overpasses found from the geometry, and the road class at junctions. To give the solver
your own band per edge (a sidewalk -1 under its street, a crossing 1 over it), pass `band_col="band"`.

Computing takes seconds for a district and longer for a big network. Compute it once, and draw with the columns:

```python
levels = rs.compute_levels(edges, method="solve", order="class")
rs.save_levels(con, levels)                # duckOSM file, schema visualization; rs.load_levels reads it back
rs.render_edges(levels, casing_level_col="casing_level", fill_level_col="fill_level",
                casing_start_col="casing_start", casing_end_col="casing_end").save("map.html")
```

`compute_levels(edges)` is this method. `method="tags"` is a closed-form rule on the tags alone, with no search. How both methods work, with every argument and the output:
[Divided casing and one band](../design/levels_split_casing.md).

## Your own numbers

`compute_levels` is one way to fill the columns. Anything that gives two integers per edge works, for example a sidewalk at -1 under
a street at 0 and a crossing at 1 over it:

```python
edges["casing_level"] = edges["fill_level"] = edges["kind"].map({"sidewalk": -1, "street": 0, "crossing": 1})
```

## Good to know

- One casing layer and one fill layer are made for each position that occurs, so keep the range small.
- `rsColor` and colour-by reach every position. `rsColor` still lifts its painted roads to the top *inside* their position.
- `tiles=True` works with positions.

See also: the [full specification](../design/levels_split_casing.md) and every keyword in the [parameters table](../reference/parameters.md).

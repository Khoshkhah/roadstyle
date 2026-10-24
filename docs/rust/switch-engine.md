# Switch the engine

<p class="lead">Select the Rust engine for one call with a keyword, or for a whole process with an environment variable.</p>

!!! warning "Experimental"
    The Rust engine is experimental in 0.25. The Python API that selects it (`engine="rust"`, `ROADSTYLE_ENGINE`) is stable.
    The engine's inside, the `roadstyle:*` metadata in the style and the `__rs_*` property names can change in the next
    versions. The default engine stays Python.

## Select the engine for one call

Give `engine="rust"` to the functions that take it:

```python
import roadstyle as rs

rs.render_edges(edges, engine="rust").save("map.html")
rs.render_dashboard(edges, engine="rust")            # also render_report, render_street_view
rs.export_inline(edges, engine="rust")
rs.export_style(edges, "out", base_url="https://example.org/tiles", engine="rust")
rs.export_look(engine="rust")
rs.compute_levels(edges, engine="rust")
```

`engine="python"` selects the Python engine. Another value is an error:

```text
ValueError: engine='go': use one of python, rust
```

## Select the engine for a process

Set `ROADSTYLE_ENGINE` before Python starts:

```bash
ROADSTYLE_ENGINE=rust python make_maps.py
```

Each call with no `engine` keyword then uses the Rust engine. A keyword in a call has priority over the variable.

## Know what happens when the Rust engine cannot do a part

Some parts are only in Python, for example a `Styler` object (`style=`) or `compute_levels` with keywords that are not the
defaults. [Keywords by engine](keywords.md) lists them. The result depends on how you selected the engine:

| You selected Rust with | A part that only Python has |
|---|---|
| the keyword `engine="rust"` | stops with a `ValueError` that names the part |
| the variable `ROADSTYLE_ENGINE=rust` | the Python engine makes this call, and Python writes a `UserWarning` |

roadstyle never changes the engine without a message. The error, for example:

```text
ValueError: engine='rust': a Styler object (style=) is Python's; use engine='python'
```

The warning, for the same call with `ROADSTYLE_ENGINE=rust`:

```text
UserWarning: roadstyle: a Styler object (style=) is Python's: the Python engine makes this one (ROADSTYLE_ENGINE=rust)
```

To make every such warning an error, so that a nightly job stops, add this line before the calls:

```python
import warnings
warnings.filterwarnings("error", message="roadstyle: .* the Python engine makes this one")
```

## The folium and lonboard backends

`backend="folium"` and `backend="lonboard"` are other renderers, and the Rust engine does not make them:

- With `engine="rust"`, the call stops: `ValueError: engine='rust' makes the web page only, not backend='folium'`.
- With `ROADSTYLE_ENGINE=rust`, the call uses the Python renderer, with no warning.

## If the Rust module is missing

The wheels on PyPI have the Rust module `roadstyle._rust`. An install from a source checkout with `PYTHONPATH=src` does not
have it. Then a call with the Rust engine stops with an `ImportError` that tells you how to build it. See
[Build from source](build.md).

**See also:** [Keywords by engine](keywords.md) · [Your first map with the Rust engine](first-map.md)

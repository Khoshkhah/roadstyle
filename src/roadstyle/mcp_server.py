"""roadstyle as tools for AI agents: an MCP server (``pip install "roadstyle[mcp]"``, ``roadstyle-mcp``).

Three tools, each a thin wrapper over the public API. A map is saved to a file and only its path goes
back to the agent (a page is megabytes and would flood the agent's context), together with a PNG
preview so the agent can look at what it made. Design: ``docs/design/agent-tools.md``.

Runs over stdio: nothing here may print to stdout, which carries the protocol. Warnings go to the
tool result instead, where the agent can act on them.
"""
from __future__ import annotations

import difflib
import functools
import inspect
import re
import warnings
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import as_edges, get_api_key, load_edges, render_edges
from . import snapshot as _snapshot
from .render_web import render as _render_web

OUT_DIR = Path.home() / "roadstyle-maps"
OSMNX_CACHE = Path.home() / ".cache" / "roadstyle" / "osmnx"
#: tried in order when a download can't connect; osmnx pins one server IP and never fails over,
#: and overpass-api.de refused every connection for hours on 2026-09-29 while this mirror answered
OVERPASS_URLS = ("https://overpass-api.de/api", "https://maps.mail.ru/osm/tools/overpass/api")

INSTRUCTIONS = """\
roadstyle draws road networks as styled, interactive, offline HTML maps (MapLibre, one file).
- render_place: any place name -> OpenStreetMap roads (osmnx) -> map. render_file: a road file.
- Each returns the saved .html path and a PNG preview. Look at the preview before reporting back.
- Street names show from zoom 14 and one-way arrows on minor streets from zoom 16; the preview is
  zoomed out, so use snapshot(html_path, lon, lat, zoom=17) to check them.
- options = render_edges keywords, e.g. {"color_by": "maxspeed", "legend": true},
  {"include": ["primary", "secondary"]}, {"basemap": "osm"}, {"palette": "carto"}, {"view_3d": true}.
- Edges are directed: a two-way street is two edges drawn side by side. Don't merge them.
Docs: https://khoshkhah.github.io/roadstyle/ (every keyword: /reference/parameters/)."""

mcp = MCPServer("roadstyle", instructions=INSTRUCTIONS)


def _tool(fn):
    """Register a tool whose errors reach the agent with their message.

    The SDK passes only ToolError text through and reduces anything else to "Error executing tool";
    the agent then can't fix a wrong path, a missing column or a misspelt option. This server runs
    on the user's own machine, so there is nothing to hide.
    """
    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return mcp.tool()(run)


def _option_names() -> set[str]:
    kinds = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    names = set()
    for f in (render_edges, _render_web):
        names |= {p.name for p in inspect.signature(f).parameters.values() if p.kind in kinds}
    return names - {"gdf", "backend"}


def _check_options(options: dict | None) -> dict:
    """render_edges silently ignores a misspelt keyword; an agent needs to hear about it."""
    options = dict(options or {})
    valid = _option_names()
    bad = sorted(set(options) - valid)
    if bad:
        hints = [f"{k!r} (did you mean {', '.join(map(repr, m))}?)" if (m := difflib.get_close_matches(k, valid, 3))
                 else repr(k) for k in bad]
        raise ValueError(f"unknown option(s): {'; '.join(hints)}. Valid options: {', '.join(sorted(valid))}")
    return options


def _out_path(output_path: str | None, stem: str) -> Path:
    if output_path:
        p = Path(output_path).expanduser().resolve()
        p = p if p.suffix == ".html" else p.with_suffix(".html")
    else:
        slug = re.sub(r"[^\w-]+", "_", stem).strip("_").lower() or "map"
        p = OUT_DIR / f"{slug}.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _preview(html_path: Path, **camera) -> list:
    png = html_path.with_suffix(".png")
    try:
        _snapshot(str(html_path), str(png), **{k: v for k, v in camera.items() if v is not None})
    except Exception as e:                          # no Playwright / no Chromium: the map still stands
        return [f"(no preview: {e}. Install it with: pip install playwright && playwright install chromium)"]
    return [Image(path=png)]


def _render(gdf, options: dict | None, output_path: str | None, stem: str) -> list:
    opts = _check_options(options)
    notes = []
    if "basemap" not in opts and not get_api_key("carto"):
        # the default CARTO tiles come back stamped "API KEY REQUIRED" without a key
        opts["basemap"] = "esri_street"
        notes.append("basemap: esri_street (the default CARTO map needs CARTO_API_KEY)")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        e = as_edges(gdf, class_col=opts.get("highway_col", "highway"))
        out = _out_path(output_path, stem)
        render_edges(e, **opts).save(str(out))
    g = e.gdf
    classes = g[e.class_col].astype(str).value_counts()
    lines = [f"Saved {out}",
             f"{len(g):,} edges; classes: " + ", ".join(f"{k} {v}" for k, v in classes.head(8).items()),
             "bounds (w, s, e, n): " + ", ".join(f"{b:.5f}" for b in g.total_bounds)]
    msgs = dict.fromkeys(str(w.message) for w in caught)       # once each, in order
    if notes:     # we picked a keyless map; CARTO's warning is about the switcher's other entries
        msgs = [m for m in msgs if not m.startswith("CARTO base map requested")]
    lines += notes + [f"warning: {m}" for m in msgs]
    return ["\n".join(lines), *_preview(out)]


@_tool
def render_place(place: str, network_type: str = "drive", options: dict | None = None,
                 output_path: str | None = None) -> list:
    """Download the OpenStreetMap road network of a place and draw it as an interactive HTML map.

    place: any name OpenStreetMap's geocoder knows, e.g. "Södermalm, Stockholm" or "Tartu, Estonia".
    Keep it to a district or a city: a county takes minutes to download.
    network_type: "drive", "walk", "bike", "all", "drive_service" or "all_public".
    options: render_edges keywords, e.g. {"color_by": "maxspeed", "legend": true}.
    output_path: where to save the .html (default ~/roadstyle-maps/<place>.html).
    Returns the saved path, a summary and a PNG preview.
    """
    import osmnx as ox

    ox.settings.cache_folder = str(OSMNX_CACHE)
    for url in OVERPASS_URLS:
        ox.settings.overpass_url = url
        try:
            G = ox.graph_from_place(place, network_type=network_type, simplify=False)
            break
        except OSError as e:                        # requests' ConnectionError is an OSError
            err = e
    else:
        raise RuntimeError(
            f"could not reach the OpenStreetMap servers ({', '.join(OVERPASS_URLS)}): {err}. "
            "The public Overpass servers are sometimes down or busy; retry later.") from err
    # merged ways must not span a bridge/tunnel boundary, or the whole tunnel is drawn as a bridge
    G = ox.simplify_graph(G, edge_attrs_differ=["bridge", "tunnel"])
    return _render(ox.graph_to_gdfs(G, nodes=False), options, output_path, place)


@_tool
def render_file(path: str, options: dict | None = None, output_path: str | None = None) -> list:
    """Draw the road edges in a file (GeoPackage, GeoJSON, Shapefile, ...) as an interactive HTML map.

    The file needs line geometry (any CRS) and a road-class column, "highway" by default
    (another name: options={"highway_col": "..."}).
    options: render_edges keywords, e.g. {"color_by": "speed", "cmap": "viridis", "legend": true}.
    output_path: where to save the .html (default ~/roadstyle-maps/<file name>.html).
    Returns the saved path, a summary and a PNG preview.
    """
    src = Path(path).expanduser()
    edges = load_edges(src, class_col=(options or {}).get("highway_col", "highway"))
    return _render(edges, options, output_path, src.stem)


@_tool
def snapshot(html_path: str, lon: float | None = None, lat: float | None = None,
             zoom: float | None = None, bearing: float | None = None,
             pitch: float | None = None) -> list:
    """PNG of a saved roadstyle map, optionally with a camera (centre lon/lat, zoom 0-22).

    Street names appear from zoom 14, one-way arrows on minor streets from zoom 16.
    Without a camera the map's own opening view is captured.
    """
    center = (lon, lat) if lon is not None and lat is not None else None
    return _preview(Path(html_path).expanduser().resolve(), center=center, zoom=zoom,
                    bearing=bearing, pitch=pitch)


def main():
    mcp.run()


if __name__ == "__main__":
    main()

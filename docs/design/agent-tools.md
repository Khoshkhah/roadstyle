# Agent tools: osmnx input and an MCP server

Status: Parts 1 and 2 **implemented** 2026-09-29 (unreleased); Part 3 open.

Changes from the proposal, all found by running it:

- **Error text reaches the agent.** mcp 2.x passes only `ToolError` messages through and reduces
  any other exception to "Error executing tool X". The tools re-raise every error as `ToolError`
  with its type and message: the server runs on the user's own machine, and the agent needs the
  text to fix a wrong path, a missing column or a misspelt option.
- **Overpass fallback.** `render_place` tries overpass-api.de, then maps.mail.ru. On 2026-09-29 the
  first refused every connection for hours while the mirror answered (kumi.systems and
  private.coffee timed out).
- **Keyless base map by default.** With no CARTO key and no `basemap` option, the map uses
  `esri_street` and the summary says so; the default CARTO tiles would come back watermarked.

## Problem

Two things stop AI agents from using roadstyle.

1. **The most common input crashes.** When someone asks an agent for "a map of the roads in X", the
   agent downloads the network with osmnx and passes the edges to `render_edges`. roadstyle 0.8.6
   raises `TypeError: unhashable type: 'list'` on raw osmnx edges. An agent that fails on its first
   call tends to give up on the library.
2. **Agents without a Python environment can't use roadstyle at all.** Claude Desktop, claude.ai,
   Cursor chat and most hosted agents can call tools but can't `pip install`. Agents that *can* run
   Python still can't see the map they made, so mistakes like a tunnel drawn as a bridge go unnoticed.

The skill (`skills/roadstyle/SKILL.md`), `AGENTS.md`, the CLI and `docs/llms.txt` already serve
agents that write code. This proposal covers the two gaps above.

## Data

Measured 2026-09-29 with roadstyle 0.8.6 and osmnx 2.0.7 on Södermalm (`network_type="drive"`):

| Finding | Detail |
|---|---|
| Crash | `render_web.py:202` `_annotation_slots` groups by `name`, and osmnx gives lists there |
| List-valued columns | `osmid, highway, lanes, maxspeed, name, reversed, width, tunnel, access`, from osmnx merging OSM ways when it simplifies the graph |
| Index | osmnx edges carry a `(u, v, key)` MultiIndex, so the fast GeoJSON path falls back to GeoPandas with a warning |
| Tunnel drawn as bridge | Default simplification merges Söderledstunneln and Centralbron into one 1.5 km edge tagged `tunnel=yes` and `bridge=yes`. `_mark_lvl` checks bridge first, so the whole tunnel is drawn as a bridge. `simplify=False` followed by `ox.simplify_graph(G, edge_attrs_differ=["bridge", "tunnel"])` leaves 0 such edges (1,470 edges instead of 1,361) |
| Direction | osmnx graphs are directed, with two-way streets as twin edges. That is already roadstyle's contract, so no conversion is needed |
| Workaround | Resetting the index and keeping the first item of each list renders correctly (`notebooks/10_osmnx.ipynb`, `flatten()`) |
| MCP SDK | `mcp` 2.2.0 (Python ≥ 3.10). In 2.x, `FastMCP` was renamed `MCPServer` (`from mcp.server.mcpserver import MCPServer, Image`) |
| MCP prototype | A tool returning `[str, Image(path=...)]` over stdio reaches a real `ClientSession` as one text item and one image item (1.1 MB PNG) |
| Overpass | osmnx pins one server IP per lookup and does not fail over. On 2026-09-29, 65.109.112.52 refused connections while 162.55.144.139 answered, so every download failed until the server recovered |

## Part 1: accept osmnx edges directly

Fix it where every input passes: `RoadEdges.from_geodataframe` (`edges.py:60`). `render_edges`
and the emitters both reach it through `as_edges`.

- **Index.** Reset a MultiIndex (`reset_index()`), so `u`, `v` and `key` become ordinary columns.
- **List cells.** In object-dtype columns only, replace each list with its first non-null item.
  "Non-null" matters: a merged `tunnel` can be `[nan, 'yes']`, and taking the first item would
  lose the tunnel.
- **Tunnel and bridge on the same edge.** Warn with the count and the fix
  (`ox.simplify_graph(..., edge_attrs_differ=["bridge", "tunnel"])`). Don't guess which part is
  which: the merged edge has no information about where the tunnel ends.
- **Cost.** Scanning object columns is a Python loop per cell. Measure it on `stockholm_county`
  (456,813 edges) and keep it under 5 % of the render time. If it's slower, check each column's
  dtype and first values before scanning it.

Tests (no network): an osmnx-shaped GeoDataFrame fixture with a `(u, v, key)` MultiIndex, list
`name` and `highway` values, a `[nan, 'yes']` tunnel, and one edge tagged both tunnel and bridge.
Check that `render_edges` succeeds, the tunnel survives, and the warning is raised.

Afterwards, remove `flatten()` from `notebooks/10_osmnx.ipynb`.

## Part 2: an MCP server

### Where it lives

In this package, as an optional extra. It is not a separate repository.

```toml
[project.optional-dependencies]
mcp = ["mcp>=2.2,<3", "osmnx", "playwright"]

[project.scripts]
roadstyle-mcp = "roadstyle.mcp_server:main"
```

One new module, `src/roadstyle/mcp_server.py`, with about 120 lines of thin wrappers around the
public API. Users who don't install the extra get nothing new.

### Tools

Keep it to three tools. Each returns a short text summary (absolute HTML path, edge count,
classes present, bounds) plus a PNG preview, so the agent can check its own result.

| Tool | Does |
|---|---|
| `render_place(place, network_type="drive", options=None, output_path=None)` | osmnx download (Part 1's bridge and tunnel-safe simplification) → `render_edges` → save → preview |
| `render_file(path, options=None, output_path=None)` | any file `load_edges` reads → `render_edges` → save → preview |
| `snapshot(html_path, center=None, zoom=None, bearing=None, pitch=None)` | PNG of a saved map with a chosen camera, so the agent can check street names and arrows at zoom 16 and above |

- **`options`** is a dict passed to `render_edges` (`color_by`, `basemap`, `palette`, `include`,
  …). It's validated against the real signatures of `render_edges` and `render_web.render`. An
  unknown key returns an error listing the closest valid names (`difflib.get_close_matches`).
  `render_edges` silently ignores misspelt keywords (see `AGENTS.md`), and agents misspell.
- **Output path.** The server's working directory is arbitrary (Claude Desktop starts it anywhere),
  so the default is `~/roadstyle-maps/<slug>.html`, returned as an absolute path.
- **osmnx cache** goes in `~/.cache/roadstyle/osmnx`, not the working directory. Network failures
  come back as tool errors that say the Overpass server may be down and to retry.
- **Preview without Chromium.** `rs.snapshot` needs `playwright install chromium`, which pip
  can't do. If Chromium is missing, return the text only, plus that install command.
- **Instructions.** Pass a short version of the SKILL.md data contract and traps as the server's
  `instructions`.
- **Transport:** stdio only.

### Install (for the README and docs)

```bash
claude mcp add roadstyle -- uvx --from "roadstyle[mcp]" roadstyle-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{"mcpServers": {"roadstyle": {"command": "uvx", "args": ["--from", "roadstyle[mcp]", "roadstyle-mcp"]}}}
```

### Tests

`tests/test_mcp_server.py` starts the server over stdio with the SDK's `ClientSession`, as in the
prototype. It lists the tools, runs `render_file` on `notebooks/data/sodermalm_edges.gpkg`, and
checks the path and the image item. It also checks that a misspelt option returns the close-match
error. Preview assertions are skipped without Chromium. `render_place` is not tested in CI because
it needs the network.

## Part 3: distribution (after Parts 1 and 2 ship)

- **Claude Code plugin.** Add a plugin manifest that bundles `skills/roadstyle` and the MCP
  server, so it installs in one command. Check the manifest format against the current Claude
  Code docs when implementing.
- **MCP Registry.** Publish a `server.json` with the registry's publisher tool. For PyPI packages
  the registry verifies ownership with an `mcp-name:` line in the README. Check the current
  registry docs when publishing.
- Submit a PR to the awesome-mcp-servers lists.

## Rejected

- **A separate `roadstyle-mcp` repository.** Two release trains and version drift. Its only
  benefit, keeping `mcp` out of a plain install, is already covered by the extra.
- **One typed tool parameter per render keyword.** That's about 45 keywords, giving a huge tool
  schema that drifts from the library. A validated `options` dict gives the same reach and stays
  correct.
- **Returning the HTML in the tool result.** A page is 0.5 to 2+ MB and would flood the agent's
  context. Return the path plus a PNG.
- **An HTTP (streamable-http) server.** The output is a local file and the preview needs local
  Chromium. Desktop agents use stdio. Add HTTP when someone wants to host it.
- **Fixing osmnx input only in the notebook or the MCP layer.** Every other `render_edges` caller
  with osmnx data would still crash.
- **Automatically picking bridge or tunnel for a mixed edge.** The data can't tell which part is
  which. Warn and point to the osmnx setting instead.

## Impact

- `edges.py`: about 20 lines and one new warning. Inputs that crashed before now render, and inputs
  that worked before are unchanged.
- New: `mcp_server.py`, the `mcp` extra, the `roadstyle-mcp` script, two test files, and an
  "AI agents" docs page. Updates: README ("For AI coding agents" section), `SKILL.md` (osmnx input,
  MCP server), `CHANGELOG`, and `notebooks/10_osmnx.ipynb` (remove `flatten()`).
- Release as 0.9.0: a new feature and a new extra, no breaking changes.

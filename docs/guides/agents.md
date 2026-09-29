# AI agents

roadstyle works with AI agents two ways: as tools any MCP-capable app can call, or as a library an
agent writes code against.

## Tools, no code: the MCP server

Lets any MCP-capable AI app (Claude Code, Claude Desktop, Cursor, …) draw road maps
without writing code: `render_place("Tartu, Estonia")`, `render_file("roads.gpkg")` and `snapshot`.
Each saves an HTML map and returns its path plus a PNG preview the agent can look at.
```bash
claude mcp add roadstyle -- uvx roadstyle-mcp
```
Claude Desktop (`claude_desktop_config.json`):
```json
{"mcpServers": {"roadstyle": {"command": "uvx", "args": ["roadstyle-mcp"]}}}
```
Maps go to `~/roadstyle-maps/`. The preview needs Chromium once: `uvx --from roadstyle-mcp playwright install chromium`.

| Tool | Does |
|---|---|
| `render_place(place, network_type="drive", options, output_path)` | downloads the OpenStreetMap roads of a place with osmnx and draws them |
| `render_file(path, options, output_path)` | draws a road file (GeoPackage, GeoJSON, Shapefile, …) |
| `snapshot(html_path, lon, lat, zoom, bearing, pitch)` | a PNG of a saved map, e.g. to check street names (zoom 14+) and arrows (zoom 16+) |

`options` takes any [`render_edges` keyword](../reference/parameters.md), such as
`{"color_by": "maxspeed", "legend": true}`. A misspelt one is an error naming the closest valid
keyword. Without a CARTO key the map uses the keyless `esri_street` base map.

**Claude Code plugin.** The MCP server and the skill in one install:

```text
/plugin marketplace add Khoshkhah/roadstyle
/plugin install roadstyle@roadstyle
```

## Code: the agent skill

Agents that write Python (Claude Code, Codex, Cursor's agent) do best with the
[skill](https://github.com/Khoshkhah/roadstyle/blob/main/skills/roadstyle/SKILL.md): the one call,
the data contract, the JavaScript API and the traps, in one page. Install it for Claude Code:

```bash
mkdir -p ~/.claude/skills/roadstyle && curl -fsSL -o ~/.claude/skills/roadstyle/SKILL.md \
  https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/skills/roadstyle/SKILL.md
```

The whole documentation as a link list for LLMs: [llms.txt](../llms.txt).

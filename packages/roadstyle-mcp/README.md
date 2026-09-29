# roadstyle-mcp

The MCP server of [roadstyle](https://github.com/Khoshkhah/roadstyle): lets any MCP-capable AI app
(Claude Code, Claude Desktop, Cursor, …) draw styled, interactive, offline road maps without writing
code.

<!-- mcp-name: io.github.Khoshkhah/roadstyle -->

| Tool | Does |
|---|---|
| `render_place(place, network_type, options, output_path)` | downloads the OpenStreetMap roads of a place (osmnx) and draws them |
| `render_file(path, options, output_path)` | draws a road file (GeoPackage, GeoJSON, Shapefile, …) |
| `snapshot(html_path, lon, lat, zoom, bearing, pitch)` | a PNG of a saved map, e.g. to check street names and arrows up close |

Each saves an HTML map (default `~/roadstyle-maps/`) and returns its path, a summary and a PNG
preview the agent can look at.

## Install

Claude Code:

```bash
claude mcp add roadstyle -- uvx roadstyle-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{"mcpServers": {"roadstyle": {"command": "uvx", "args": ["roadstyle-mcp"]}}}
```

The PNG preview needs Chromium, once: `uvx --from roadstyle-mcp playwright install chromium`.

This package has no code of its own: it installs `roadstyle[mcp]` and provides the `roadstyle-mcp`
command. Documentation: [AI agents](https://khoshkhah.github.io/roadstyle/guides/agents/).

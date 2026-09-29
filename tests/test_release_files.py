"""Checks on what gets published: no API keys in notebooks, one version everywhere."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parents[1]

# a key or token as a URL parameter (?key=…, &api_key=…), or a Google browser key: exactly "AIza"
# plus 35 characters, not inside a longer base64 run (the maps' compressed data is base64)
_KEY = re.compile(r"(?i:[?&](?:key|api_?key|access_token|token)=)(?!\{)[\w-]{8,}"
                  r"|(?<![\w+/])AIza[\w-]{35}(?![\w+/])")


def test_notebooks_hold_no_api_keys():
    # A notebook run with CARTO_API_KEY set saves the key inside every map it outputs; the repo is
    # public. Remove it with: sed -i 's/?key=<the key>//g' notebooks/<name>.ipynb
    found = {nb.name: sorted(set(_KEY.findall(nb.read_text(encoding="utf-8"))))[:3]
             for nb in sorted((ROOT / "notebooks").glob("*.ipynb"))}
    assert not {k: v for k, v in found.items() if v}


def _toml_value(path, key):
    return re.search(rf'^{key} = "([^"]+)"', (ROOT / path).read_text(), re.M).group(1)


def test_one_version_everywhere():
    # roadstyle-mcp is released with roadstyle and pins it exactly; the MCP Registry entry and
    # the Claude Code plugin name the same version.
    v = _toml_value("pyproject.toml", "version")
    shim = (ROOT / "packages/roadstyle-mcp/pyproject.toml").read_text()
    server = json.loads((ROOT / "server.json").read_text())
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert {
        "roadstyle-mcp version": _toml_value("packages/roadstyle-mcp/pyproject.toml", "version"),
        "roadstyle-mcp pin": re.search(r'"roadstyle\[mcp\]==([^"]+)"', shim).group(1),
        "server.json version": server["version"],
        "server.json package": server["packages"][0]["version"],
        "plugin.json version": plugin["version"],
    } == dict.fromkeys(["roadstyle-mcp version", "roadstyle-mcp pin", "server.json version",
                        "server.json package", "plugin.json version"], v)

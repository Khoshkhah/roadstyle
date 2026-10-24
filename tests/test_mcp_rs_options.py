"""The Rust MCP server (rust/roadstyle-mcp) checks the options against its own list (STAGE1) until the page writer (R3) gives the
typed list. Each name in it must be a render_edges keyword, as the Python server's check reads them (mcp_server._option_names)."""
import inspect
import pathlib
import re

from roadstyle import render_edges
from roadstyle.render_web import render


def test_rust_server_options_are_render_edges_keywords():
    kinds = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    valid = {p.name for f in (render_edges, render) for p in inspect.signature(f).parameters.values() if p.kind in kinds}
    src = (pathlib.Path(__file__).parents[1] / "rust/roadstyle-mcp/src/main.rs").read_text()
    names = re.findall(r'"(\w+)"', re.search(r"const STAGE1: &\[&str\] = &\[(.*?)\];", src, re.S).group(1))
    assert names and set(names) <= valid - {"gdf", "backend"}, set(names) - valid

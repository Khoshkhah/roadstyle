"""The MCP server, driven the way an agent's app drives it: a client over stdio."""
import asyncio
import os
import pathlib
import sys

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

DATA = pathlib.Path(__file__).parents[1] / "notebooks" / "data" / "sodermalm_edges.gpkg"
SRC = str(pathlib.Path(__file__).parents[1] / "src")


def _call(tool, args):
    async def run():
        env = {**os.environ, "PYTHONPATH": SRC + os.pathsep + os.environ.get("PYTHONPATH", "")}
        params = StdioServerParameters(command=sys.executable, args=["-m", "roadstyle.mcp_server"],
                                       env=env)
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            return tools, await s.call_tool(tool, args)
    return asyncio.run(run())


def test_render_file_saves_map_and_reports(tmp_path):
    out = tmp_path / "sod.html"
    tools, res = _call("render_file", {"path": str(DATA), "output_path": str(out),
                                       "options": {"basemap": "blank"}})
    assert sorted(tools) == ["render_file", "render_place", "snapshot"]
    assert not res.is_error, res.content
    text = res.content[0].text
    assert f"Saved {out}" in text and "edges; classes:" in text
    assert out.stat().st_size > 10_000
    # the preview is a PNG when Chromium is available, else a note saying how to get it
    assert res.content[1].type == "image" or "no preview" in res.content[1].text


def test_misspelt_option_is_an_error_with_a_suggestion(tmp_path):
    _, res = _call("render_file", {"path": str(DATA), "output_path": str(tmp_path / "x.html"),
                                   "options": {"colour_by": "highway"}})
    assert res.is_error
    assert "'colour_by' (did you mean 'color_by'" in res.content[0].text
    assert not (tmp_path / "x.html").exists()

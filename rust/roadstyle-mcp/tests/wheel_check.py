"""The Rust roadstyle-mcp wheel as an MCP client starts it (release.yml, mcp-wheel-test): `uvx --from <wheel> roadstyle-mcp`, then
initialize, tools/list and render_file over stdio (JSON-RPC, one message on each line).

    python3 rust/roadstyle-mcp/tests/wheel_check.py <the wheel> <a roads GeoParquet file>
"""
import json
import pathlib
import subprocess
import sys
import tempfile

wheel, roads = sys.argv[1], str(pathlib.Path(sys.argv[2]).resolve())
p = subprocess.Popen(["uvx", "--from", wheel, "roadstyle-mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)


def send(m):
    p.stdin.write(json.dumps(m) + "\n")
    p.stdin.flush()


def answer(i):
    for line in p.stdout:
        m = json.loads(line)
        if m.get("id") == i:
            return m["result"]
    raise SystemExit("the server stopped")


send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "ci", "version": "0"}}})
assert answer(1)["serverInfo"]["name"] == "roadstyle"
send({"jsonrpc": "2.0", "method": "notifications/initialized"})
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
tools = sorted(t["name"] for t in answer(2)["tools"])
assert tools == ["render_file", "render_place", "snapshot"], tools
out = pathlib.Path(tempfile.mkdtemp()) / "monaco.html"
send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
      "params": {"name": "render_file", "arguments": {"path": roads, "output_path": str(out), "options": {"basemap": "blank"}}}})
res = answer(3)
p.stdin.close()
p.terminate()
text = res["content"][0]["text"]
assert not res.get("isError") and text.startswith("Saved ") and out.stat().st_size > 10_000, res
print(f"ok: {tools}; {text.splitlines()[1]}; {out.stat().st_size:,} bytes")

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
    # roadstyle-mcp is released with roadstyle and pins it exactly; the MCP Registry entry, the
    # Claude Code plugin, the Rust crates (one workspace version, rust_library.md decision 7) and
    # the npm packages (roadstyle-dashboard, roadstyle-wasm) name the same version.
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
        "Rust crates version": _toml_value("rust/Cargo.toml", "version"),
        "roadstyle-dashboard version": json.loads((ROOT / "src/roadstyle/static/package.json").read_text())["version"],
        "roadstyle-wasm version": json.loads((ROOT / "rust/roadstyle-wasm/package.json").read_text())["version"],
    } == dict.fromkeys(["roadstyle-mcp version", "roadstyle-mcp pin", "server.json version",
                        "server.json package", "plugin.json version", "Rust crates version",
                        "roadstyle-dashboard version", "roadstyle-wasm version"], v)


def test_every_dashboard_module_is_in_its_list():
    """static/dashboard/files.txt is the one list of the dashboard's modules (render_web.py and the Rust page writer read it): a module
    file that is not in it would be left out of every page."""
    d = ROOT / "src/roadstyle/static/dashboard"
    listed = [ln.strip() for ln in (d / "files.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert sorted(listed) == sorted(p.stem for p in d.glob("*.js")) and len(set(listed)) == len(listed)


def test_dashboard_modules_bundle_as_one_script():
    """render_web.py and the Rust page writer put the modules in one script by line rules: they drop each line that starts with
    `import ` and the word `export ` at a line's start. So an import must be on one line, and two modules must not declare the same
    top-level name (in one script the second one is a syntax error, or silently replaces the first)."""
    import re
    d = ROOT / "src/roadstyle/static/dashboard"
    seen, dup, multi = {}, [], []
    for p in sorted(d.glob("*.js")):
        lines = p.read_text().splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("import ") and not re.search(r"from\s+[\"'][^\"']+[\"'];\s*$", ln):
                multi.append(f"{p.name}:{i + 1}")
            m = re.match(r"(?:export )?(?:async )?(function\*?|class|let|const|var) (.*)", ln)
            if not m:
                continue
            if m.group(1).startswith("function") or m.group(1) == "class":
                names = [re.match(r"\s*([A-Za-z_$][\w$]*)", m.group(2)).group(1)]
            else:     # let a = 1, b = [x, y], c;  -> a, b, c (the names before "=" or "," at the top level of the statement)
                body, depth, cur, names = m.group(2).split(";")[0], 0, "", []
                for ch in body + ",":
                    if ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        depth -= 1
                    if ch == "," and depth == 0:
                        names.append(re.match(r"\s*([A-Za-z_$][\w$]*)", cur).group(1))
                        cur = ""
                    else:
                        cur += ch
            for n in names:
                if n in seen and seen[n] != p.name:
                    dup.append(f"{n}: {seen[n]} and {p.name}")
                seen.setdefault(n, p.name)
    assert not multi, f"an import over more than one line: {multi}"
    assert not dup, f"a top-level name in two modules: {dup}"


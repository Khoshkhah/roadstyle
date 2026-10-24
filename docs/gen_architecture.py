"""The facts of docs/rust/architecture.md, made from the code: the crates and their dependencies (rust/*/Cargo.toml), the modules
with their line counts and their first doc line, the public API, the metadata keys, the JS files and the numbers of the known design
gaps. Each fact goes between the page's markers <!-- gen:NAME --> and <!-- /gen:NAME -->.

    python docs/gen_architecture.py            # write the facts into the page
    python docs/gen_architecture.py --check    # exit 1 if the page in git is not the code's

mkdocs.yml runs this file as a hook (on_page_markdown), so the site always has the facts of the code it is built from.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUST = ROOT / "rust"
PAGE = ROOT / "docs" / "rust" / "architecture.md"
PY = {p.stem for p in (ROOT / "src" / "roadstyle").glob("*.py")}


def lines(p: Path) -> int:
    return len(p.read_text(encoding="utf-8").splitlines())


def clean(s: str) -> str:
    """The first sentence of a text, without the design-doc links and the port notes in parentheses."""
    s = re.sub(r"\s*\((?:[^()]*(?:docs/|\.md|full port|step \d|phase P\d|v2's)[^()]*)\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"(.+?\.)(\s|$)", s)
    return (m.group(1) if m else s).rstrip(".")


def first_doc(p: Path, mark: str) -> str:
    """The first sentence of a file's top comment (`//!` or `//`)."""
    text = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.startswith(mark):
            break
        text.append(ln[len(mark):].strip())
    return clean(" ".join(text))


def doc_block(p: Path) -> str:
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("//!"):
            break
        out.append(ln[3:])
    return " ".join(out)


def python_peers(p: Path) -> list[str]:
    """The modules of Python roadstyle that the module's doc names (``render_web._page_html``, ``tiles.py``): its Python counterparts."""
    found, doc = [], doc_block(p)
    for m in re.finditer(r"\b([a-z_]+)(\.py\b|\._?[a-z][a-z_]*)?", doc):
        name, rest = m.group(1), m.group(2)
        named = rest == ".py" or (rest and rest != ".md") or "_" in name.strip("_")    # a bare name only when it is not a word
        if name in PY and named and f"`{name}.py`" not in found:
            found.append(f"`{name}.py`")
    if "mapstyle.map" in doc:
        found.append("mapstyle's `map.py`")
    return found


def crates() -> dict[str, dict]:
    ws = tomllib.loads((RUST / "Cargo.toml").read_text())
    wdeps = ws["workspace"]["dependencies"]
    out = {}
    for member in ws["workspace"]["members"]:
        t = tomllib.loads((RUST / member / "Cargo.toml").read_text())
        deps = {**t.get("dependencies", {})}
        for tgt in t.get("target", {}).values():
            deps.update(tgt.get("dependencies", {}))
        inner, outer = [], []
        for name, spec in deps.items():
            is_path = isinstance(spec, dict) and ("path" in spec or (spec.get("workspace") and "path" in (wdeps.get(name) or {})))
            (inner if is_path else outer).append(name)
        src = RUST / member / "src"
        kinds = t.get("lib", {}).get("crate-type", ["lib"])
        kind = "cdylib" if "cdylib" in kinds else "library"
        if (src / "main.rs").exists():
            kind += " and program"
        out[t["package"]["name"]] = {
            "dir": member, "description": t["package"].get("description", ""), "kind": kind,
            "inner": sorted(inner), "outer": sorted(outer), "src": src,
            "lines": sum(lines(f) for f in src.rglob("*.rs")),
        }
    return out


def public_api(c: dict) -> list[str]:
    lib = (c["src"] / "lib.rs").read_text(encoding="utf-8")
    names = re.findall(r"js_name\s*=\s*(\w+)", lib)                                          # wasm-bindgen
    names += re.findall(r"#\[pyfunction\][^\n]*\n(?:#\[[^\n]*\n)*fn (\w+)", lib)               # PyO3
    names += re.findall(r"#\[pyclass[^\n]*\]\s*\n(?:#\[[^\n]*\n)*(?:pub )?struct (\w+)", lib)
    names += re.findall(r"#\[wasm_bindgen\]\s*\n\s*pub struct (\w+)", lib)
    if not names:                                                                           # a Rust library: its top-level pub items
        names = re.findall(r"^pub (?:fn|struct|enum|mod|const|trait|type) (\w+)", lib, re.M)
        for alias, path in re.findall(r"^pub use [\w:]+ as (\w+);|^pub use ([\w:{}*, ]+);", lib, re.M):
            names += [alias] if alias else [path] if path.endswith("*") else re.findall(r"(\w+)(?=[,}]|$)", path.split("::", 1)[-1])
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen


def table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def gen_crate_graph(cs) -> str:
    ids = {n: n.replace("-", "_") for n in cs}
    out = ["```mermaid", "flowchart TB"]
    for n, c in cs.items():
        out.append(f'    {ids[n]}["{n}<br/>{c["lines"]:,} lines"]')
    for n, c in cs.items():
        for d in c["inner"]:
            out.append(f"    {ids[d]} --> {ids[n]}")
    out.append("```")
    return "\n".join(out)


def gen_crates(cs) -> str:
    rows = []
    for n, c in cs.items():
        dep = ", ".join([f"`{d}`" for d in c["inner"]] + [d for d in c["outer"]]) or "(none)"
        rows.append([f"[`{n}`](#{n})", clean(c["description"]), f'{c["lines"]:,}', dep])
    total = sum(c["lines"] for c in cs.values())
    return table(["Crate", "Job", "Lines", "Dependencies"], rows) + f"\n\nAll crates: {total:,} lines of Rust in `rust/*/src/`."


def gen_modules(cs) -> str:
    out = []
    for n, c in cs.items():
        files = sorted(c["src"].rglob("*.rs"), key=lambda f: (f.name != "lib.rs", str(f)))
        rows = []
        for f in files:
            mod = str(f.relative_to(c["src"]).with_suffix("")).replace("/", "::")
            rows.append([f"`{mod}`", f"{lines(f):,}", first_doc(f, "//!") or "", ", ".join(python_peers(f))])
        for j in sorted(c["src"].rglob("*.json")):                                              # data built into the crate
            rows.append([f"`{j.name}`", "(data)", "data read when the crate is built", ""])
        api = ", ".join(f"`{a}`" for a in public_api(c)) or "(none)"
        out.append(f"#### `{n}` {{ #{n} }}\n\n{c['kind'].capitalize()}, in `rust/{c['dir']}/`. Public API: {api}.\n\n"
                   + table(["Module", "Lines", "What it does", "Python counterpart"], rows))
    return "\n\n".join(out)


def gen_metadata() -> str:
    keys: dict[str, list[str]] = {}
    for f in sorted(RUST.glob("*/src/**/*.rs")):
        for k in re.findall(r"roadstyle:[a-z_]+", f.read_text(encoding="utf-8")):
            where = f"`{f.parent.parent.name}::{f.stem}`"
            keys.setdefault(k, [])
            if where not in keys[k]:
                keys[k].append(where)
    return table(["Metadata key", "Written or read by"], [[f"`{k}`", ", ".join(v)] for k, v in sorted(keys.items())])


def gen_js() -> str:
    dash = ROOT / "src" / "roadstyle" / "static" / "dashboard"
    rows = []
    for f in sorted(dash.glob("*.js")):
        t = f.read_text(encoding="utf-8")
        api = sorted(set(re.findall(r"window\.((?:rs|RS_)\w+)\s*=", t)))
        rows.append([f"`{f.name}`", f"{lines(f):,}", first_doc(f, "//"), ", ".join(f"`{a}`" for a in api)])
    sql = []
    for f in sorted((RUST / "roadstyle-wasm" / "js").glob("*.js")):
        ex = re.findall(r"^export (?:async )?function (\w+)\(([^)]*)\)", f.read_text(encoding="utf-8"), re.M)
        sql.append([f"`{f.name}`", f"{lines(f):,}", ", ".join(f"`{n}({a})`" for n, a in ex)])
    wasm = (RUST / "roadstyle-wasm" / "src" / "lib.rs").read_text(encoding="utf-8")
    calls = []
    for doc, name in re.findall(r"((?:[ \t]*///[^\n]*\n)+)[ \t]*#\[wasm_bindgen\((?:js_name\s*=\s*(\w+)|constructor)\)\]", wasm):
        first = re.sub(r"\s+", " ", " ".join(l.strip()[3:].strip() for l in doc.strip().splitlines()))
        calls.append([f"`{name or 'new Tiler'}`", first.replace("|", "\\|")])
    for doc in re.findall(r"((?:[ \t]*///[^\n]*\n)+)[ \t]*#\[wasm_bindgen\]\s*\n[ \t]*pub struct Tiler", wasm):
        calls.append(["`new Tiler`", re.sub(r"\s+", " ", " ".join(l.strip()[3:].strip() for l in doc.strip().splitlines())).replace("|", "\\|")])
    for doc, name in re.findall(r"((?:[ \t]*///[^\n]*\n)+)[ \t]*pub fn (\w+)\(&self", wasm):
        first = re.sub(r"\s+", " ", " ".join(l.strip()[3:].strip() for l in doc.strip().splitlines()))
        calls.append([f"`tiler.{name}`", first.replace("|", "\\|")])
    return ("**The dashboard modules** (`src/roadstyle/static/dashboard/`):\n\n"
            + table(["File", "Lines", "What it does", "Window API"], rows)
            + "\n\n**The worker SQL** (`rust/roadstyle-wasm/js/`):\n\n" + table(["File", "Lines", "Exports"], sql)
            + "\n\n**The WebAssembly API** (`rust/roadstyle-wasm/src/lib.rs`):\n\n" + table(["Call", "Its doc comment"], calls))


def gen_gaps(cs) -> str:
    src = [f for f in RUST.glob("*/src/**/*.rs")]
    text = {f: f.read_text(encoding="utf-8") for f in src}
    string_err = sum(len(re.findall(r"Result<[^;{=]*?,\s*String>", t)) for t in text.values())
    err_enums = sorted({m for t in text.values() for m in re.findall(r"\benum (\w*Error)\b", t)})
    engine = [f for f in src if "roadstyle-engine" in str(f)]
    value = sum(len(re.findall(r"\bValue\b", text[f])) for f in engine)
    rs_names = sorted({m for t in text.values() for m in re.findall(r"__rs_[A-Za-z0-9_]+", t)})
    eng = cs["roadstyle-engine"]
    rows = [
        ["The core has no I/O: the engine does not depend on a reader", "`roadstyle-engine` depends on: " + ", ".join(f"`{d}`" for d in eng["inner"]),
         "no" if "roadstyle-io" in eng["inner"] else "yes"],
        ["A crate `roadstyle-look` for the typed, versioned look", "the look is the module `roadstyle-engine::look` (JSON)" if "roadstyle-look" not in cs
         else "`roadstyle-look` exists", "yes" if "roadstyle-look" in cs else "no"],
        ["One error enum for each crate", f"`Result<_, String>`: {string_err} places; error enums: {', '.join(err_enums) or 'none'}",
         "yes" if err_enums and not string_err else "no"],
        ["A typed render model in place of JSON trees", f"`Value` (serde_json) in `roadstyle-engine`: {value} times", "no" if value else "yes"],
        ["Typed fields in place of the `__rs_*` properties", f"{len(rs_names)} distinct `__rs_*` names in `rust/`", "no" if rs_names else "yes"],
    ]
    # the stages (docs/rust/architecture.md, "The three stages"): stage 2 alone in each binding, and a typed border into stage 2
    stage2 = {b: [n for n in public_api(cs[b]) if re.search(r"(?i)make_?tiles|tile_?sources", n)] for b in ("roadstyle-py", "roadstyle-wasm")}
    found = "; ".join(f"`{b}`: " + (", ".join(f"`{n}`" for n in v) or "none") for b, v in stage2.items())
    rows.append(["Stage 2 (the tiles) has its own public call in Python and in the browser", found, "yes" if all(stage2.values()) else "no"])
    # one road table for the fields in every form (stage 1's second output): a call that gives it, in each binding
    table_calls = {b: [n for n in public_api(cs[b]) if re.search(r"(?i)road_?table", n)] for b in ("roadstyle-py", "roadstyle-wasm")}
    found_t = "; ".join(f"`{b}`: " + (", ".join(f"`{n}`" for n in v) or "none") for b, v in table_calls.items())
    rows.append(["One road table for the fields, in GeoJSON and in tiles alike", "a call for the road table: " + found_t
                 + ". Today GeoJSON has the fields in its source `roads`, the tiled page in the side table", "yes" if all(table_calls.values()) else "no"])
    tiles = [f for f in src if "roadstyle-tiles" in str(f)]
    tv = sum(len(re.findall(r"\bValue\b", text[f])) for f in tiles)
    rows.append(["Stage 2 takes the typed pieces, not JSON", f"`Value` (serde_json) in `roadstyle-tiles`: {tv} times", "no" if tv else "yes"])
    return table(["The plan expects", "The code now", "Done"], rows)


SECTIONS = {"crate-graph": gen_crate_graph, "crates": gen_crates, "modules": gen_modules, "metadata": lambda cs: gen_metadata(),
            "js": lambda cs: gen_js(), "gaps": gen_gaps}


def fill(markdown: str) -> str:
    cs = crates()
    for name, make in SECTIONS.items():
        pat = re.compile(rf"(<!-- gen:{name} -->\n).*?(<!-- /gen:{name} -->)", re.S)
        if not pat.search(markdown):
            raise ValueError(f"{PAGE.name}: no markers <!-- gen:{name} --> ... <!-- /gen:{name} -->")
        body = make(cs)
        markdown = pat.sub(lambda m: m.group(1) + body + "\n" + m.group(2), markdown)
    return markdown


def on_page_markdown(markdown, page, **kwargs):
    """The mkdocs hook: the facts of the code in the page, at each build."""
    return fill(markdown) if page.file.src_uri == "rust/architecture.md" else markdown


if __name__ == "__main__":
    old = PAGE.read_text(encoding="utf-8")
    new = fill(old)
    if "--check" in sys.argv:
        if new != old:
            sys.exit(f"{PAGE.relative_to(ROOT)} is not the code's: run python docs/gen_architecture.py")
    else:
        PAGE.write_text(new, encoding="utf-8")

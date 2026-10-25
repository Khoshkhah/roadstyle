"""The key tables of docs/reference/formats.md, made from the bundled profile and palette (rust/roadstyle-assets/files/data/): each key to two
levels, its value in the file and its comment. Each table goes between the page's markers <!-- gen:NAME --> and <!-- /gen:NAME -->.

    python docs/gen_formats.py            # write the tables into the page
    python docs/gen_formats.py --check    # exit 1 if the page in git is not the files'

mkdocs.yml runs this file as a hook (on_page_markdown), so the site always has the keys of the files it is built from.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rust" / "roadstyle-assets" / "files" / "data"
PAGE = ROOT / "docs" / "reference" / "formats.md"
KEY = re.compile(r"^( *)([A-Za-z0-9_]+):")
COMMENT = re.compile(r"\s{2,}#\s?(.*)$")        # a trailing comment: two spaces or more, then '#' (a color '#rrggbb' is in quotes)


def short(v, limit=70) -> str:
    """The value as compact JSON; a long one cut, and a mapping of many entries as its count and first keys."""
    if isinstance(v, dict) and len(v) > 6:
        keys = ", ".join(list(map(str, v))[:4])
        return f"{len(v)} entries: {keys}, ..."
    s = json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
    return s if len(s) <= limit else s[:limit - 1] + "…"


def header_notes(text: str) -> dict[str, str]:
    """The file's first comment block, where a line `# key.path: text` (and the lines after it) explains that key."""
    notes, key = {}, None
    for ln in text.splitlines():
        if not ln.startswith("#"):
            break
        body = ln.lstrip("#").strip()
        m = re.match(r"([a-z_]+(?:\.[a-z_]+)+): (.*)", body)
        if m:
            key = m.group(1)
            notes[key] = m.group(2)
        elif key and body and not body[0].isupper():      # a line that starts a new sentence is a note of the whole file
            notes[key] += " " + body
        else:
            key = None
    return notes


def rows(path: Path) -> list[list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    notes = header_notes(path.read_text(encoding="utf-8"))
    out, above, stack = [], [], []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            above = []
            continue
        if ln.lstrip().startswith("#"):
            above.append(ln.strip().lstrip("#").strip())
            continue
        m = KEY.match(ln)
        if not m:
            above = []
            continue
        depth = len(m.group(1)) // 2
        stack[depth:] = [m.group(2)]
        if depth <= 1:
            c = COMMENT.search(ln)
            note = " ".join([notes.get(".".join(stack), "")] + above + ([c.group(1).strip()] if c else [])).strip()
            v = data
            for k in stack:
                v = v[k]
            out.append(["`" + ".".join(stack) + "`", "`" + short(v).replace("|", "\\|") + "`", note.replace("|", "\\|")])
        above = []
    return out


def table(path: Path) -> str:
    head = ["Key", f"Value in `{path.relative_to(ROOT / 'src' / 'roadstyle')}`", "Comment in the file"]
    lines = ["| " + " | ".join(head) + " |", "|---|---|---|"] + ["| " + " | ".join(r) + " |" for r in rows(path)]
    names = ", ".join(f"`{p.stem}`" for p in sorted(path.parent.glob("*.yaml")))
    return f"Bundled: {names}. The table shows `{path.stem}`; the others state only what they change.\n\n" + "\n".join(lines)


SECTIONS = {"profile": lambda: table(DATA / "profiles" / "default.yaml"), "palette": lambda: table(DATA / "palettes" / "amber.yaml")}


def fill(markdown: str) -> str:
    for name, make in SECTIONS.items():
        pat = re.compile(rf"(<!-- gen:{name} -->\n).*?(<!-- /gen:{name} -->)", re.S)
        if not pat.search(markdown):
            raise ValueError(f"{PAGE.name}: no markers <!-- gen:{name} --> ... <!-- /gen:{name} -->")
        body = make()
        markdown = pat.sub(lambda m: m.group(1) + body + "\n" + m.group(2), markdown)
    return markdown


def on_page_markdown(markdown, page, **kwargs):
    """The mkdocs hook: the keys of the bundled files in the page, at each build."""
    return fill(markdown) if page.file.src_uri == "reference/formats.md" else markdown


if __name__ == "__main__":
    old = PAGE.read_text(encoding="utf-8")
    new = fill(old)
    if "--check" in sys.argv:
        if new != old:
            sys.exit(f"{PAGE.relative_to(ROOT)} is not the files': run python docs/gen_formats.py")
    else:
        PAGE.write_text(new, encoding="utf-8")

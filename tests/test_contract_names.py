"""The names of the interaction contract (docs/reference/contract.md) and the names in the code are the same: the global state rs_*, the
feature properties __rs_*, the metadata keys roadstyle:*, the page's placeholders, the browser storage keys and the CSS variables."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "reference" / "contract.md"
# a name with a number in it is one row: __rs_fill__1 is __rs_fill__<i>, rs_ov_ (the code joins the number) is rs_ov_<i>
KINDS = {"state": r"\brs_[a-z0-9_]+", "property": r"__rs_[A-Za-z0-9_]+", "metadata": r"roadstyle:[a-z_]+", "placeholder": r"__[A-Z][A-Z0-9_]+__"}


def _norm(n):
    return re.sub(r"^(__rs_fill__)\d+$", r"\1<i>", re.sub(r"^rs_ov_$", "rs_ov_<i>", n))


def _code_names():
    out = {k: set() for k in KINDS}
    files = [p for p in (ROOT / "src").rglob("*") if p.suffix in (".py", ".js", ".html", ".css")]
    files += [p for p in (ROOT / "rust").rglob("*.rs") if "target" not in p.parts]
    for p in files:
        text = p.read_text(errors="ignore")
        out["state"] |= {_norm(m) for m in re.findall(r'"(rs_[a-z0-9_]+)"|(rs_ov_)', text) for m in m if m}
        out["property"] |= {_norm(m) for m in re.findall(KINDS["property"], text)}
        out["metadata"] |= set(re.findall(KINDS["metadata"], text))
    out["placeholder"] = set(re.findall(KINDS["placeholder"], (ROOT / "src/roadstyle/static/web_template.html").read_text()))
    return out


def _doc_names():
    text = DOC.read_text().split("## Planned names")[0]
    ticks = " ".join(re.findall(r"`([^`]+)`", text))
    out = {k: {_norm(n) for n in re.findall(p, ticks)} for k, p in KINDS.items()}
    # the doc writes a numbered name with <i>, and a property like __rs_fill@<palette>: the names before < and @
    out["state"] |= set(re.findall(r"\brs_[a-z0-9_]+<i>", ticks))
    out["property"] |= set(re.findall(r"__rs_[A-Za-z0-9_]+<i>", ticks))
    return out


def test_every_name_of_the_code_is_in_the_reference():
    code, doc = _code_names(), _doc_names()
    for kind in KINDS:
        missing = sorted(code[kind] - doc[kind])
        assert not missing, f"{kind} names in the code that docs/reference/contract.md does not have: {missing}"


def test_every_name_of_the_reference_is_in_the_code():
    code, doc = _code_names(), _doc_names()
    for kind in KINDS:
        extra = sorted(doc[kind] - code[kind])
        assert not extra, f"{kind} names in docs/reference/contract.md that the code does not have: {extra}"


def test_the_storage_keys_and_css_variables():
    code = " ".join(p.read_text() for p in (ROOT / "src/roadstyle/static/dashboard").glob("*.[jc]s*"))
    doc = DOC.read_text()
    for name in ("rs-street-view-mode", "rs-street-view-window", "rs-google-3d-window", "rs-host-panel:", "--rs-side"):
        assert name in code and name in doc, name


def test_the_page_reads_only_declared_properties():
    """R1: every __rs_* property that a dashboard module or a page script reads is in its declaration, static/dashboard/reads.json (a
    piece's or a road table row's). The layers' own reads are collected from their expressions (props::reads in Rust); the window's own
    __rs_* names (the page's checks) are not properties."""
    import json

    declared = json.loads((ROOT / "src/roadstyle/static/dashboard/reads.json").read_text())
    known = {k for part in ("pieces", "decks", "slots", "table") for k in declared[part]} | {"__rs_fill", "__rs_fill__<i>"}      # the colour options' fills
    scripts = [*(ROOT / "src/roadstyle/static/dashboard").glob("*.js"), *(ROOT / "src/roadstyle/static/page").glob("*.html"),
               ROOT / "src/roadstyle/static/popup.js"]
    read = set()
    for p in scripts:
        text = re.sub(r"window\.__rs_[a-z]+", "", p.read_text())
        read |= {_norm(m) for m in re.findall(KINDS["property"], text)}
    assert read - known == set(), f"read by the page but not declared in reads.json: {sorted(read - known)}"


def test_a_missing_flag_is_false_for_the_page():
    """A tile has no __rs_* flag that is false (2026-10-25), so the page's scripts read a flag as true or not: no comparison of a __rs_*
    property with false, undefined or null, and no test that the key is there (the layers: tests/sources.rs in rust/roadstyle-rs)."""
    # the flags: each __rs_* property that the engines set to true or false
    code = [p.read_text(errors="ignore") for p in [*(ROOT / "src").rglob("*.py"), *(ROOT / "rust").rglob("*.rs")] if "target" not in p.parts]
    flags = {m for t in code for m in re.findall(r"[\"'](__rs_\w+)[\"'][\]:,]\s*(?:\w+\(|\.?into\(\)\s*,?)?\s*(?:True|False|true|false)\b", t)}
    flags |= {m for t in code for m in re.findall(r"flag\(&mut out, \"(__rs_\w+)\"", t)}       # draw.rs: the road's flags
    assert {"__rs_bridge", "__rs_twoway", "__rs_seam"} <= flags, flags
    f = "(?:" + "|".join(sorted(flags)) + r")\b"
    bad = []
    for p in (ROOT / "src" / "roadstyle" / "static").rglob("*"):
        if p.suffix not in (".js", ".html"):
            continue
        for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if re.search(f + r"\s*[!=]==?\s*(false|undefined|null)\b|\b(false|undefined|null)\s*[!=]==?\s*\S*" + f
                         + r"|[\"']" + f + r"[\"']\s+in\b|hasOwnProperty\(\s*[\"']" + f, line):
                bad.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
    assert not bad, "\n".join(bad)

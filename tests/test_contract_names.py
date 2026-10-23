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

"""The shared dashboard parts (help, hover, tabs, kpi, svg) write no colour of their own in their code: colours come from the CSS tokens, so they follow both themes.
A colour literal in one of these modules fails here. (The CSS has its own check in tests/test_theme.py for the theme files.)"""
import re
from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-assets" / "files" / "static" / "dashboard"
_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")


def test_the_shared_parts_have_no_colour_literal():
    bad = {}
    for name in ("help", "hover", "tabs", "kpi", "svg"):
        text = (_DIR / f"{name}.js").read_text()
        hits = [m.group(0) for line in text.splitlines() if not line.lstrip().startswith("//") for m in _COLOUR.finditer(line)]
        if hits:
            bad[name] = hits
    assert bad == {}, bad

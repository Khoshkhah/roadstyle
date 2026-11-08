"""The dashboard is loaded as ES modules by a page that imports it (duckOSM Studio) and as one script by roadstyle's own pages. In the script every
name is global, so a missing `import` shows only in the modules: the call throws a ReferenceError inside a promise and nothing says why (Street
View on Mapillary stayed on "Looking for photos..." in Studio, 2026-11-08). This test checks that every private name (`_x`) that a module takes from
another module is imported there."""
import pathlib
import re

DASH = pathlib.Path(__file__).resolve().parents[1] / "rust/roadstyle-assets/files/static/dashboard"
_EXPORT = re.compile(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+(_[A-Za-z0-9_$]*)")
_IMPORT = re.compile(r"import\s*\{([^}]*)\}", re.S)


def _code(text):
    """The text without comments and strings, so that a word in a comment or a message is not a use."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)(^|[^:\\'\"`])//.*$", r"\1", text)
    return re.sub(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", '""', text)


def test_private_names_of_other_modules_are_imported():
    files = {p.name: p.read_text() for p in DASH.glob("*.js")}
    owners = {n: f for f, t in files.items() for n in _EXPORT.findall(t)}
    missing = []
    for f, text in files.items():
        got = {x.split(" as ")[-1].strip() for m in _IMPORT.finditer(text) for x in m.group(1).split(",")}
        code = _code(text)
        for name, owner in owners.items():
            if owner == f or name in got:
                continue
            if re.search(r"(?<![\w$.])" + re.escape(name) + r"(?![\w$])", code) and not re.search(r"\b(?:function|const|let|var|class)\s+" + re.escape(name) + r"\b", code):
                missing.append(f"{f} uses {name} from {owner}")
    assert not missing, "\n".join(missing)

"""The settings have three transparency sliders (the bar and the panel, the boxes with the popup and the tooltip, the card behind the text): they set the tokens
--rs-tb-bg, --rs-box-bg and --rs-card-bg (static/popup.css). So no surface of the dashboard has a translucent background of its own: a `background` that is a
colour with an alpha (rgba, hsla) in the CSS and the templates of the assets is a failure, whatever it is for; a surface uses one of the three tokens."""
import pathlib
import re

ROOT = pathlib.Path(__file__).parents[1] / "rust" / "roadstyle-assets" / "files"


def _files():
    return [*ROOT.glob("static/dashboard/*.css"), *ROOT.glob("static/*.css"), *ROOT.glob("templates/*.html")]


def test_no_surface_has_a_translucent_background_of_its_own():
    own = []
    for f in _files():
        text = f.read_text()
        for m in re.finditer(r"background(?:-color)?\s*:\s*([^;}]+)", text):
            top = re.sub(r"var\((?:[^()]|\([^()]*\))*\)", "VAR", m.group(1).strip())          # a var() with a fallback is the token's
            if re.search(r"(rgba|hsla)\(", top) or re.search(r"(rgb|hsl)\([^)]*/", top):
                own.append(f"{f.name}:{text[:m.start()].count(chr(10)) + 1} {m.group(1).strip()[:60]}")
    assert not own, "use --rs-tb-bg, --rs-box-bg or --rs-card-bg: " + "; ".join(own)


def test_the_three_tokens_are_the_ones_that_the_settings_move():
    css = (ROOT / "static" / "popup.css").read_text()
    for token, alpha in (("--rs-tb-bg", "--rs-a-tb"), ("--rs-box-bg", "--rs-a-box"), ("--rs-card-bg", "--rs-a-card")):
        assert re.search(token + r":rgba\([^)]*var\(" + alpha + r"\)\)", css), token
    settings = (ROOT / "static" / "dashboard" / "settings.js").read_text()
    for key in ('["tb",', '["box",', '["card",'):
        assert key in settings, key

"""The dashboard's CSS has no `vh` unit. On a phone, 100vh is the height of the window with the address bar hidden: it is taller than the visible
screen, so the full sheet's grip went under the tool bar and the person could not lower the sheet. `dvh` follows the visible screen. A
headless browser has no address bar, so no browser test can show this fault; this test reads the file."""
import pathlib
import re

CSS = pathlib.Path(__file__).parents[1] / "rust/roadstyle-assets/files/static/dashboard/dashboard.css"


def test_the_dashboard_css_has_no_vh_unit():
    assert not re.findall(r"[0-9.]+vh\b", CSS.read_text()), "use dvh: vh is taller than the visible screen on a phone"

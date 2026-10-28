"""The Google 3D window re-centres the map into its free part by default; a page switches that off with
window.rsWindowRecentre = false (simready's review page does: a drag of the window never moves the map)."""
import pathlib


def test_switch_is_read_by_the_window_padding():
    src = (pathlib.Path(__file__).resolve().parent.parent / "src/roadstyle/static/dashboard/google3d.js").read_text()
    assert "window.rsWindowRecentre!==false" in src

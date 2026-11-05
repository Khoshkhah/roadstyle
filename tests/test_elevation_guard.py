"""Guards of the elevation feature that need no browser (so they run in every CI job):
the DEM is one rule in the config (no module has its own tile address), and every place that offers the 3D terrain says its limit."""
import pathlib
import re

ROOT = pathlib.Path(__file__).parents[1]
DASH = ROOT / "rust/roadstyle-assets/files/static/dashboard"


def test_no_dashboard_module_has_its_own_dem_address():
    """The hillshade, the terrain and the Google 3D window's ground heights read `ontop.dem` of data/basemaps.json: a second tile address would be
    a second rule, which can differ."""
    own = [f.name for f in DASH.glob("*.js") if re.search(r"elevation-tiles|terrarium/|World_Hillshade", f.read_text())]
    assert not own, f"{own}: read the DEM from O.ontop.dem"


def test_every_place_that_offers_the_terrain_says_that_a_tunnel_is_not_under_the_hill():
    """With the terrain on, every layer lies on the DEM (MapLibre has no height for a line): a tunnel is drawn on the hill, a bridge on the valley."""
    for path, key in (("docs/reference/parameters.md", "`terrain`"), ("docs/reference/javascript.md", "`rsTerrain(on)`"), ("docs/guides/dashboard-layout.md", "3D terrain"),
                      ("skills/roadstyle/SKILL.md", "terrain=True"), ("rust/roadstyle-assets/files/static/dashboard/elevation.js", "THE LIMIT")):
        lines = [ln for ln in (ROOT / path).read_text().splitlines() if key in ln]
        assert lines, (path, key)
        text = " ".join(lines).lower() if path.endswith(".md") else (ROOT / path).read_text().lower()
        assert "tunnel" in text and "bridge" in text, f"{path} names the terrain but not its limit (tunnels and bridges)"

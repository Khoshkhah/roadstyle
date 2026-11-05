"""The ready themes of the design panel that copy a roadstyle palette or base-map theme (dashboard/design/themes.json) have the road colours of its file:
a change of a palette shows here, so the two do not drift apart. Only the classes that the file names are compared; a class with no casing in the file
has its fill as casing (design.js, THEME_DATA's comment)."""
import json
from pathlib import Path

import pytest
import yaml

DATA = Path(__file__).resolve().parents[1] / "rust/roadstyle-assets/files/data"
THEMES = {t["id"]: t for t in json.loads((DATA.parent / "static/dashboard/design/themes.json").read_text())["themes"]}
# the theme's id, its file and the path to the classes in it
FILES = [("amber", "palettes/amber.yaml", ("classes",)), ("cartoroads", "palettes/carto.yaml", ("classes",)),
         ("highsat", "palettes/highsat.yaml", ("classes",)), ("monoroads", "palettes/mono.yaml", ("classes",)),
         ("google", "basemap/themes/google.yaml", ("roads", "colors")), ("grey", "basemap/themes/grey.yaml", ("roads", "colors")),
         ("roadstyle", "basemap/themes/roadstyle.yaml", ("roads", "colors")), ("osmcarto", "basemap/osm_carto.yaml", ("roads", "colors"))]
CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "pedestrian",
           "cycleway", "footway", "path", "track"]          # design.js CLASSES: the classes with a colour of their own in the panel


@pytest.mark.parametrize("theme,file,path", FILES)
def test_a_theme_has_the_road_colours_of_its_file(theme, file, path):
    classes = yaml.safe_load((DATA / file).read_text())
    for k in path:
        classes = classes[k]
    t = THEMES[theme]["roads"]
    of = lambda part, c: (t[part].get(c) or t[part].get("*") or "").lower()       # noqa: E731
    wrong = {}
    for c in CLASSES:
        if c not in classes:
            continue
        fill = classes[c]["fill"].lower()
        casing = (classes[c].get("casing") or classes[c]["fill"]).lower()
        if (of("fill", c), of("casing", c)) != (fill, casing):
            wrong[c] = {"theme": [of("fill", c), of("casing", c)], "file": [fill, casing]}
    assert not wrong, wrong

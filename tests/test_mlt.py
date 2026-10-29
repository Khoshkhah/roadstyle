"""MLT as the second tile format (rust/roadstyle-tiles/src/mlt.rs): ``export_style(..., tile_format="mlt")`` writes the same tiles in MapLibre
Tile, and MapLibre GL JS draws them with the same pixels as the MVT tiles. The browser test is skipped when playwright is not installed."""
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest

import roadstyle as rs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rust" / "roadstyle-rs" / "tests" / "data"
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")

# Monaco's centre; the views are flat and tilted, from the low zooms to the overzoomed ones
VIEWS = [(12, 0, 0), (15, 0, 0), (16.5, 0, 0), (15.5, 45, 30)]
CENTER = (7.4243, 43.7384)


@pytest.fixture(scope="module")
def monaco():
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    df = pq.read_table(DATA / "monaco" / "roads.parquet").to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")


@pytest.fixture(scope="module")
def keywords():
    look = json.loads((DATA / "look.json").read_text())
    args = {k: v for k, v in look["args"].items() if k not in ("basemap", "basemaps", "legend", "views")}      # an export holds the roads only
    return {"palette": look["palette"], "settings": look["settings"], **args, "arrows": True, "labels": True}


@pytest.fixture(scope="module")
def served(tmp_path_factory, monaco, keywords):
    """A folder with both exports (``mvt/``, ``mlt/``), MapLibre, and a server for it; the URL base."""
    root = tmp_path_factory.mktemp("mlt")
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    for f in ("mvt", "mlt"):
        rs.export_style(monaco, root / f, base_url=f"{base}/{f}", tile_format=f, **keywords)
    for f in ("maplibre-gl.js", "maplibre-gl.css"):
        shutil.copy(ROOT / "rust/roadstyle-assets/files/vendor" / f, root / f)
    yield root, base
    server.shutdown()


def test_an_mlt_export_has_the_encoding_the_extension_and_the_same_tiles(served):
    root, base = served
    text = {f: (root / f / "style.json").read_text().replace(f"{base}/{f}", "BASE") for f in ("mvt", "mlt")}
    mvt, mlt = (json.loads(text[f]) for f in ("mvt", "mlt"))
    assert "encoding" not in mvt["sources"]["roads"] and mlt["sources"]["roads"]["encoding"] == "mlt"
    assert mvt["sources"]["roads"]["tiles"][0].split("?")[0].endswith("{y}.pbf") and mlt["sources"]["roads"]["tiles"][0].split("?")[0].endswith("{y}.mlt")
    files = {f: {p.relative_to(root / f / "tiles").with_suffix(""): p.stat().st_size for p in (root / f / "tiles").rglob("*.*")} for f in ("mvt", "mlt")}
    assert files["mvt"].keys() == files["mlt"].keys() and len(files["mvt"]) > 50, "a file for the same tiles in both"
    assert all((files["mvt"][k] == 0) == (files["mlt"][k] == 0) for k in files["mvt"]), "an empty file in one is empty in the other"
    assert sum(files["mlt"].values()) < sum(files["mvt"].values()), "MLT is smaller"
    mvt["sources"].pop("roads"), mlt["sources"].pop("roads")
    assert mvt == mlt, "the style is the same but for the source"


def test_a_pmtiles_export_has_the_tile_type_of_its_format(monaco, keywords, tmp_path):
    for f, type_byte in (("mvt", 1), ("mlt", 6)):
        rs.export_style(monaco, tmp_path / f, base_url="http://x", format="pmtiles", tile_format=f, **keywords)
        head = (tmp_path / f / "roads.pmtiles").read_bytes()[:127]
        assert head[:7] == b"PMTiles" and head[99] == type_byte, f


def test_an_unknown_tile_format_is_an_error(monaco, keywords, tmp_path):
    with pytest.raises(Exception, match="mvt.*mlt"):
        rs.export_style(monaco, tmp_path, base_url="http://x", tile_format="pbf", **keywords)


def test_maplibre_draws_the_mlt_tiles_as_the_mvt_tiles(served):
    """The same pixels: a screenshot of each export at the views of VIEWS differs in 0 pixels."""
    pw = pytest.importorskip("playwright.sync_api")
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    import io

    root, base = served
    (root / "view.html").write_text("""<!doctype html><meta charset=utf-8><link rel=stylesheet href="maplibre-gl.css"><script src="maplibre-gl.js"></script>
<body style="margin:0"><div id=m style="width:800px;height:600px"></div>""")
    shots = {}
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        for f in ("mvt", "mlt"):
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.goto(f"{base}/view.html")
            page.evaluate("""async f => {
              const style = await (await fetch('/' + f + '/style.json')).json();
              delete style.glyphs; delete style.sprite;                       // no labels and no arrows: they need the network
              style.layers = style.layers.filter(l => l.type !== 'symbol');
              window.map = new maplibregl.Map({container: 'm', style, center: [7.4243, 43.7384], zoom: 12, fadeDuration: 0, attributionControl: false,
                                               canvasContextAttributes: {preserveDrawingBuffer: true}});
              window.errors = []; map.on('error', e => window.errors.push(String(e.error && e.error.message)));
              await new Promise(r => map.once('load', r)); }""", f)
            for z, pitch, bearing in VIEWS:
                page.evaluate("""async ([c, z, pitch, bearing]) => { map.jumpTo({center: c, zoom: z, pitch, bearing});
                  await new Promise(r => setTimeout(r, 100));
                  while (!map.loaded()) await new Promise(r => setTimeout(r, 20));
                  await new Promise(r => setTimeout(r, 300)); }""", [list(CENTER), z, pitch, bearing])
                shots[f, z] = np.asarray(Image.open(io.BytesIO(page.screenshot())).convert("RGB"), dtype=int)
            assert page.evaluate("window.errors") == [], f
            page.close()
        browser.close()
    for z, *_ in VIEWS:
        a, b = shots["mvt", z], shots["mlt", z]
        drawn = int((a != 255).any(axis=2).sum())
        print(f"z{z}: {drawn} drawn pixels, {int((a != b).any(axis=2).sum())} changed")
        assert drawn > 1000, f"z{z}: the map has roads"
        changed = int((a != b).any(axis=2).sum())
        assert changed == 0, f"z{z}: {changed} pixels differ between MVT and MLT"

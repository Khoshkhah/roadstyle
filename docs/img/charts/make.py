"""Makes the pictures of the guide "Charts" (docs/guides/charts.md): one chart card of each kind, and the panel of the first example, from a dashboard
of Monaco in Playwright, in the light theme. Run it again after a change of the chart's look:

    PROJ_DATA=<the proj folder of the env> python docs/img/charts/make.py

The roads are rust/roadstyle-rs/tests/data/monaco/roads.parquet. The page's own rows (the counts of a sensor) are made here, with a fixed seed."""
from pathlib import Path

import numpy as np
import pandas as pd

import roadstyle as rs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]


def roads():
    import geopandas as gpd
    import shapely
    d = pd.read_parquet(ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "monaco" / "roads.parquet")
    g = gpd.GeoDataFrame(d, geometry=shapely.from_wkb(d.pop("geometry")), crs=4326)
    g["length_m"] = g.to_crs(32632).length.round(1)
    return g


def counts():
    """The counts of one sensor: vehicles and trucks for each hour, the vehicles for each day, and 400 speed readings with their flow."""
    rng = np.random.default_rng(7)
    h = np.arange(24)
    day = 120 + 520 * np.exp(-((h - 8) ** 2) / 6) + 430 * np.exp(-((h - 17.5) ** 2) / 8) + 60 * np.exp(-((h - 13) ** 2) / 10)
    hours = pd.DataFrame({"hour": h, "vehicles": day.round(), "trucks": (day * 0.12 + 15 * (h > 5) * (h < 20)).round()})
    days = pd.DataFrame({"day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "vehicles": [9120, 9480, 9310, 9655, 10240, 7120, 5880]})
    flow = rng.uniform(80, 1800, 400)
    speed = (52 - flow / 60 + rng.normal(0, 3.5, 400)).clip(8, 60).round(1)
    return hours, days, pd.DataFrame({"flow": flow.round(), "speed_kmh": speed})


def main():
    from playwright.sync_api import sync_playwright
    hours, days, speeds = counts()
    first = [
        {"id": "classes", "label": "Roads by class", "part": "chart", "chart": {"kind": "pie", "x": "highway"}},
        {"id": "km", "label": "km by class", "part": "chart", "chart": {"kind": "bar", "x": "highway", "y": "length_m", "scale": 0.001}},
        {"id": "flow", "label": "Vehicles per hour", "part": "chart", "chart": {"kind": "line", "x": "hour", "y": "vehicles", "data": hours}},
    ]
    kinds = [
        ("bar", {"label": "Vehicles per day", "chart": {"kind": "bar", "x": "day", "y": "vehicles", "data": days}}),
        ("bar-horizontal", {"label": "km by class", "chart": {"kind": "bar", "x": "highway", "y": "length_m", "scale": 0.001, "height": 300}}),
        ("line", {"label": "Vehicles and trucks per hour", "chart": {"kind": "line", "x": "hour", "y": ["vehicles", "trucks"], "data": hours}}),
        ("histogram", {"label": "Speeds", "chart": {"kind": "histogram", "x": "speed_kmh", "data": speeds}}),
        ("scatter", {"label": "Speed and flow", "chart": {"kind": "scatter", "x": "flow", "y": "speed_kmh", "data": speeds}}),
        ("pie", {"label": "Roads by class", "chart": {"kind": "pie", "x": "highway"}}),
    ]
    g = roads()
    pages = {"panel": first, "kinds": [{"id": k, "part": "chart", **s} for k, s in kinds]}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        for name, secs in pages.items():
            path = HERE / f"_{name}.html"
            rs.render_dashboard(g, name="Monaco", basemap="blank", dashboard={"panel": {"sections": secs, "width_px": 340}}).save(path)
            page = browser.new_page(viewport={"width": 1280, "height": 1500}, device_scale_factor=2)
            page.goto(path.resolve().as_uri())
            page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
            page.evaluate("rsSetTheme('light')")
            page.wait_for_timeout(600)
            if name == "panel":
                page.locator("#sb").screenshot(path=HERE / "panel.png")
            else:
                for k, _ in kinds:
                    page.locator(f'[data-rs-section="{k}"]').screenshot(path=HERE / f"{k}.png")
            page.close()
            path.unlink()
        browser.close()


if __name__ == "__main__":
    main()

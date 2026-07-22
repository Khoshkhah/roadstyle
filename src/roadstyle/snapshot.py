"""Static images from roadstyle maps — headless-browser screenshots as a one-liner.

The web maps are living pages (MapLibre, tiles, fonts); a faithful static image needs a real
browser. :func:`snapshot` wraps headless Chromium via Playwright (an *optional* dependency) —
the same pipeline used to verify every rendering change in this project — so a paper figure or
report image is::

    wm = rs.render_edges(edges, basemap="dark_matter", view_3d=True)
    rs.snapshot(wm, "fig.png", center=(18.076, 59.308), zoom=16, pitch=60)

Needs ``pip install playwright`` once, plus ``playwright install chromium``.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def snapshot(map_or_html, out_path, *, center=None, zoom=None, pitch=None, bearing=None,
             width: int = 1200, height: int = 800, settle: float = 2.5, timeout: float = 40.0):
    """Render a map to a PNG via headless Chromium and return the output path.

    Parameters
    ----------
    map_or_html : a :class:`~roadstyle.render_web.WebMap`, an HTML string, or a path to an
        HTML file (any roadstyle output; the camera options need the web backend).
    out_path : the ``.png`` to write.
    center / zoom / pitch / bearing : optional camera for the shot (web backend maps); by
        default the map's own opening view (the fitted bounds) is captured.
    width / height : viewport size in px.
    settle : seconds to wait after loading for tiles/labels to finish drawing.
    timeout : seconds to wait for the map to finish loading before shooting anyway.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as err:                     # pragma: no cover - exercised without extra
        raise ImportError(
            "rs.snapshot needs Playwright: pip install playwright && playwright install chromium"
        ) from err

    html = getattr(map_or_html, "html", None)
    tmp = None
    if html is not None:
        pass                                        # a WebMap
    elif isinstance(map_or_html, (str, os.PathLike)) and Path(map_or_html).is_file():
        html = None                                 # serve the existing file directly
    elif isinstance(map_or_html, str) and "<html" in map_or_html[:200].lower():
        html = map_or_html
    else:
        raise TypeError("snapshot: pass a WebMap, an HTML string, or a path to an HTML file")

    if html is not None:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w",
                                          encoding="utf-8")
        tmp.write(html)
        tmp.close()
        url = Path(tmp.name).resolve().as_uri()
    else:
        url = Path(map_or_html).resolve().as_uri()

    cam = {k: v for k, v in
           (("pitch", pitch), ("bearing", bearing), ("zoom", zoom)) if v is not None}
    if center is not None:
        cam["center"] = list(center)

    def _shoot():
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url)
            try:                                    # web backend: wait for MapLibre to finish
                page.wait_for_function(
                    "window.map && typeof window.map.loaded === 'function' && window.map.loaded()",
                    timeout=timeout * 1000)
                if cam:
                    page.evaluate("cam => window.map.jumpTo(cam)", cam)
            except Exception:                       # folium/other pages: just let them settle
                pass
            page.wait_for_timeout(int(settle * 1000))
            page.screenshot(path=str(out_path))
            browser.close()

    try:
        # Playwright's sync API refuses to run inside a live asyncio loop (e.g. a Jupyter
        # kernel); a worker thread has no loop, so the same code runs everywhere.
        import asyncio
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False
        if in_loop:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(_shoot).result()
        else:
            _shoot()
    finally:
        if tmp is not None:
            os.unlink(tmp.name)
    return out_path

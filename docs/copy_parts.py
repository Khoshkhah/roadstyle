"""The files of the live parts (docs/parts/gallery.html and docs/parts/host.html): the real dashboard files, copied into the site at each build.

mkdocs.yml runs this file as a hook (on_post_build). It copies from rust/roadstyle-assets/files, the files that every roadstyle page gets, so the
gallery shows the parts as they are now and has no copy of its own that can drift:

    site/parts/static/     files/static (dashboard/*.js, dashboard/dashboard.css, popup.css)
    site/parts/vendor/     files/vendor (MapLibre, for the host page)
    site/parts/data/       files/data/host_options.json (the dashboard options of a host page)
    site/parts/template.css  the <style> of files/templates/dashboard.html: the look of a plain button, select and label in the panel

It also makes the live editors (Edit design, Edit levels), laid out as `roadstyle design edit` and `roadstyle levels edit` serve them:

    site/live/             files/static (design_editor/, level_editor/, dashboard/, ...) and host_options.json
    site/live/level_editor/pkg/   the engine: the WebAssembly package of rust/roadstyle-wasm/build_editor.sh (the docs workflow builds it)
    site/live/area/        the roads and the level area of docs/build_maps.py (sodermalm.parquet; roads.parquet, pairs.csv, levels.csv, ...)

The pages save nothing on GitHub Pages: a change stays in the visitor's browser. A missing package or roads file is a warning, so the strict
build (the docs workflow) fails on it.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FILES = REPO / "rust" / "roadstyle-assets" / "files"
log = logging.getLogger("mkdocs.plugins.copy_parts")


def on_post_build(config, **kwargs):
    out = Path(config["site_dir"]) / "parts"
    for part in ("static", "vendor"):
        shutil.copytree(FILES / part, out / part, dirs_exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(FILES / "data" / "host_options.json", out / "data" / "host_options.json")
    style = re.search(r"<style>(.*?)</style>", (FILES / "templates" / "dashboard.html").read_text(encoding="utf-8"), re.S)
    (out / "template.css").write_text(style.group(1) if style else "", encoding="utf-8")
    live(Path(config["site_dir"]) / "live", Path(config["docs_dir"]))


def live(out, docs):
    shutil.copytree(FILES / "static", out, dirs_exist_ok=True)
    shutil.copy(FILES / "data" / "host_options.json", out / "host_options.json")
    target = Path(os.environ.get("CARGO_TARGET_DIR") or REPO / "rust" / "target")
    pkg = target / "editor-pkg"
    if (pkg / "roadstyle_wasm.js").exists():
        shutil.copytree(pkg, out / "level_editor" / "pkg", dirs_exist_ok=True)
    else:
        log.warning(f"the live editors have no engine: {pkg} has no roadstyle_wasm.js (run rust/roadstyle-wasm/build_editor.sh)")
    (out / "area").mkdir(exist_ok=True)
    roads, levels = docs / "maps" / "sodermalm.parquet", docs / "maps" / "levels_area"
    for src in (roads, levels):
        if not src.exists():
            log.warning(f"the live editors have no {src.name}: {src} is missing (run docs/build_maps.py)")
        elif src.is_dir():
            shutil.copytree(src, out / "area", dirs_exist_ok=True)
        else:
            shutil.copy(src, out / "area" / src.name)

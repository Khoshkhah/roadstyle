"""The files of the live parts (docs/parts/gallery.html and docs/parts/host.html): the real dashboard files, copied into the site at each build.

mkdocs.yml runs this file as a hook (on_post_build). It copies from rust/roadstyle-assets/files, the files that every roadstyle page gets, so the
gallery shows the parts as they are now and has no copy of its own that can drift:

    site/parts/static/     files/static (dashboard/*.js, dashboard/dashboard.css, popup.css)
    site/parts/vendor/     files/vendor (MapLibre, for the host page)
    site/parts/data/       files/data/host_options.json (the dashboard options of a host page)
    site/parts/template.css  the <style> of files/templates/dashboard.html: the look of a plain button, select and label in the panel
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

FILES = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-assets" / "files"


def on_post_build(config, **kwargs):
    out = Path(config["site_dir"]) / "parts"
    for part in ("static", "vendor"):
        shutil.copytree(FILES / part, out / part, dirs_exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(FILES / "data" / "host_options.json", out / "data" / "host_options.json")
    style = re.search(r"<style>(.*?)</style>", (FILES / "templates" / "dashboard.html").read_text(encoding="utf-8"), re.S)
    (out / "template.css").write_text(style.group(1) if style else "", encoding="utf-8")

"""The report page's picture (docs/img/gallery/report.png), the one gallery-side image still taken by script.

The gallery, the README pictures and the top picture (docs/img/hero.jpg) are screenshots taken by hand from roadstyle pages
(2026-10-07): a page opened at the spot with ``filter_control=False, road_popup=False``, the browser bar cropped off, saved as
JPEG at most 1600 px wide. Södermalm is the bundled sample; Monaco is duckOSM's Monaco build drawn with its levels.csv.
Build ui/report first (its build.py writes the .html)::

    python docs/build_gallery.py
"""
from __future__ import annotations

from pathlib import Path

import roadstyle as rs

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    rs.snapshot(ROOT / "ui" / "report" / "report.html", ROOT / "docs" / "img" / "gallery" / "report.png", width=960, height=640, settle=4.0)
    print("wrote report")

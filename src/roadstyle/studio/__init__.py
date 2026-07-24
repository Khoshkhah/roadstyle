"""roadstyle studio — the bundled Streamlit workbench. Launch with ``roadstyle studio``.

The pages (``app``/``map``/``dashboard``/``report``/``common``) are run by Streamlit as scripts,
not imported as submodules, so they use bare ``import common``. Sample networks live in the repo
(``ui/studio/samples/``), not the wheel — ``common.sample_path`` downloads them on first use.
"""

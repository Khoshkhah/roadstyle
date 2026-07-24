"""roadstyle studio — the whole library behind a few knobs.

A Streamlit workbench with three pages: **Map** (point it at a road file, click through the
looks, get the map + the exact ``render_edges`` code), **Dashboard** (the same, but the product
is the ``ui/dashboard`` query-sidebar page), and **Report** (the ``ui/report`` stats-sidebar
page: headline counts, a by-class breakdown, search, and a selected-road read-out). Run::

    roadstyle studio                 # or: streamlit run <this file> [streamlit args…]

Needs the ``studio`` extra — ``pip install "roadstyle[studio]"`` (the map itself is plain roadstyle).
"""
import streamlit as st

st.set_page_config(page_title="roadstyle studio", page_icon="🛣️", layout="wide")
st.navigation([st.Page("map.py", title="Map", icon="🗺️", default=True),
               st.Page("dashboard.py", title="Dashboard", icon="📊"),
               st.Page("report.py", title="Report", icon="📋")]).run()

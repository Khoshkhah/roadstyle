"""roadstyle studio — the whole library behind a few knobs.

A Streamlit workbench with two pages: **Map** (point it at a road file, click through the
looks, get the map + the exact ``render_edges`` code) and **Dashboard** (the same, but the
product is the ``ui/dashboard`` sidebar-dashboard page). Run::

    streamlit run ui/studio/app.py

Needs ``pip install streamlit`` (the map itself is plain roadstyle).
"""
import streamlit as st

st.set_page_config(page_title="roadstyle studio", page_icon="🛣️", layout="wide")
st.navigation([st.Page("map.py", title="Map", icon="🗺️", default=True),
               st.Page("dashboard.py", title="Dashboard", icon="📊")]).run()

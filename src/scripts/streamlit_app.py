import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from tabs import TABS
from tabs.home import render as home_render
from theme import apply_theme

st.set_page_config(
    page_title="NOCCCD Ad-Hoc Visualization Board",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

def _go_home():
    st.session_state["project_selectbox"] = "Home"


# Sidebar
st.sidebar.image("src/static/NOCCCD Logo.jpg", width="stretch")
st.sidebar.markdown("---")
st.sidebar.markdown("**Author:** Jihoon Ahn <jahn@nocccd.edu>")
st.sidebar.markdown("---")

st.sidebar.button("Home", on_click=_go_home, use_container_width=True)

# Navigation
labels = ["Home"] + [label for label, _ in TABS]
selected = st.sidebar.selectbox("Project", labels, key="project_selectbox")
st.sidebar.markdown("---")

# Title
st.title("Ad-Hoc Visualization Board")

# Render
if selected == "Home":
    home_render()
else:
    for label, render_fn in TABS:
        if label == selected:
            render_fn()
            break

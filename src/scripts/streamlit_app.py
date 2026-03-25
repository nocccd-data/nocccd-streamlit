import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from tabs import TABS
from tabs.home import render as home_render
from theme import apply_theme
from auth import is_admin_tab, render_admin_gate, render_admin_hub

st.set_page_config(
    page_title="ESIE Ad-Hoc Visualization Board",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# Split tabs into public and admin
public_tabs = [(label, fn) for label, fn in TABS if not is_admin_tab(label)]
admin_tabs = [(label, fn) for label, fn in TABS if is_admin_tab(label)]


def _go_home():
    st.session_state["project_selectbox"] = "Home"
    st.session_state.pop("_admin_selected_tab", None)
    st.session_state.pop("_admin_mode", None)


def _go_admin():
    st.session_state["_admin_mode"] = True
    st.session_state.pop("_admin_selected_tab", None)


def _on_project_change():
    """Exit admin mode whenever the user interacts with the project dropdown."""
    st.session_state.pop("_admin_mode", None)
    st.session_state.pop("_admin_selected_tab", None)


# Sidebar
st.sidebar.image("src/static/NOCCCD Logo.jpg", width="stretch")
st.sidebar.markdown("---")
st.sidebar.markdown("**Author:** Jihoon Ahn <jahn@nocccd.edu>")
if admin_tabs:
    st.sidebar.button("Admin", on_click=_go_admin)
st.sidebar.markdown("---")

st.sidebar.button("Home", on_click=_go_home, use_container_width=True)

# Navigation — public tabs only
labels = ["Home"] + [label for label, _ in public_tabs]
selected = st.sidebar.selectbox("Project", labels, key="project_selectbox", on_change=_on_project_change)
st.sidebar.markdown("---")

# Title
st.title("ESIE Ad-Hoc Visualization Board")

admin_mode = st.session_state.get("_admin_mode", False)
admin_selected = st.session_state.get("_admin_selected_tab")

if admin_mode:
    if not render_admin_gate():
        pass  # password prompt shown
    elif admin_selected:
        # Render the specific admin tab
        for label, render_fn in admin_tabs:
            if label == admin_selected:
                render_fn()
                break
    else:
        # Show admin hub with cards
        render_admin_hub(admin_tabs)
elif selected == "Home":
    home_render()
else:
    for label, render_fn in public_tabs:
        if label == selected:
            render_fn()
            break

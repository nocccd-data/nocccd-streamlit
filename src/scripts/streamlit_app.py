import streamlit as st
from tabs import TABS

st.set_page_config(
    page_title="NOCCCD Ad-Hoc Visualization Board",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar
st.sidebar.image("src/static/NOCCCD Logo.jpg", use_container_width=True)
st.sidebar.markdown("---")
st.sidebar.markdown("**Author:** Jihoon Ahn <jahn@nocccd.edu>")
st.sidebar.markdown("---")

# Title
st.title("Ad-Hoc Visualization Board")

# Tabs
if len(TABS) == 1:
    # Single tab — no need for tab UI
    TABS[0][1]()
else:
    tab_objects = st.tabs([label for label, _ in TABS])
    for tab_obj, (_, render_fn) in zip(tab_objects, TABS):
        with tab_obj:
            render_fn()

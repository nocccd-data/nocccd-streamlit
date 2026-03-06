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

# Navigation
labels = [label for label, _ in TABS]
selected = st.sidebar.selectbox("Project", labels)
st.sidebar.markdown("---")

# Render selected tab
for label, render_fn in TABS:
    if label == selected:
        render_fn()
        break

"""Home landing page — displays project cards with search and sort."""

import streamlit as st

from home_config import PROJECTS


def render():
    # Search and sort controls
    c1, c2 = st.columns([3, 1])
    search = c1.text_input("Search projects", placeholder="Type to filter...", key="home_search")
    sort_order = c2.selectbox("Sort", ["Default", "A-Z", "Z-A"], key="home_sort")

    # Filter projects by search term
    filtered = PROJECTS
    if search:
        q = search.lower()
        filtered = [
            p for p in PROJECTS
            if q in p["tab_label"].lower()
            or q in p["description"].lower()
            or any(q in m.lower() for m in p.get("metrics", []))
        ]

    # Sort
    if sort_order == "A-Z":
        filtered = sorted(filtered, key=lambda p: p["tab_label"])
    elif sort_order == "Z-A":
        filtered = sorted(filtered, key=lambda p: p["tab_label"], reverse=True)

    if not filtered:
        st.info("No projects match your search.")
        return

    # Render cards
    cols = st.columns(3)
    for idx, proj in enumerate(filtered):
        col = cols[idx % 3]
        with col:
            with st.container(border=True):
                st.subheader(proj["tab_label"])
                st.caption(proj["description"])

                # Metrics list
                metrics = proj.get("metrics", [])
                if metrics:
                    with st.expander("Metrics"):
                        for m in metrics:
                            st.markdown(f"- {m}")

                # Navigate button
                st.button(
                    "Open",
                    key=f"home_open_{idx}",
                    on_click=_navigate,
                    args=(proj["tab_label"],),
                )


def _navigate(tab_label: str):
    st.session_state["project_selectbox"] = tab_label

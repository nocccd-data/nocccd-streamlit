"""Home landing page — displays project cards with progress tracking."""

from datetime import date, datetime

import streamlit as st

from home_config import PROJECTS


def render():
    cols = st.columns(3)
    for idx, proj in enumerate(PROJECTS):
        col = cols[idx % 3]
        with col:
            with st.container(border=True):
                st.subheader(proj["tab_label"])
                st.caption(proj["description"])

                # Due date with color coding
                due_str = proj.get("due_date")
                if due_str:
                    due = datetime.strptime(due_str, "%Y-%m-%d").date()
                    days_left = (due - date.today()).days
                    if days_left < 0:
                        st.markdown(f":red[**Due: {due_str}** (overdue)]")
                    elif days_left <= 7:
                        st.markdown(f":orange[**Due: {due_str}** ({days_left}d left)]")
                    else:
                        st.markdown(f"**Due:** {due_str} ({days_left}d left)")
                else:
                    st.markdown("**Due:** No due date")

                # Progress bar from milestones
                milestones = proj["milestones"]
                done_count = sum(1 for m in milestones if m["done"])
                total = len(milestones)
                st.progress(done_count / total if total else 0, text=f"{done_count}/{total} milestones")

                # Milestone checklist
                with st.expander("Milestones"):
                    for m in milestones:
                        icon = ":white_check_mark:" if m["done"] else ":white_large_square:"
                        st.markdown(f"{icon} {m['label']}")

                # Navigate button
                st.button(
                    "Open",
                    key=f"home_open_{idx}",
                    on_click=_navigate,
                    args=(proj["tab_label"],),
                )


def _navigate(tab_label: str):
    st.session_state["project_selectbox"] = tab_label

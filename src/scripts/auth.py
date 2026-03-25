"""Tab-level password gate for admin-protected tabs.

The admin flow:
1. User clicks "Admin" button in sidebar
2. Password prompt appears
3. On success, admin hub shows cards for all protected tabs
4. User clicks "Open" to navigate to the specific admin tab
"""

import streamlit as st

from admin_config import PROTECTED_TABS


def is_admin_tab(tab_label: str) -> bool:
    """Return True if the tab is in the protected set."""
    return tab_label in PROTECTED_TABS


def check_admin_auth() -> bool:
    """Return True if the admin has already authenticated this session."""
    return bool(st.session_state.get("_admin_authenticated"))


def render_admin_gate() -> bool:
    """Show password prompt. Returns True if authenticated."""
    if check_admin_auth():
        return True

    admin_password = st.secrets.get("admin", {}).get("password", "")
    if not admin_password:
        st.error("Admin password not configured. Add `[admin]` section to `secrets.toml`.")
        return False

    st.markdown("### Admin Access")
    st.markdown("Enter the admin password to access administrative tools.")
    entered = st.text_input("Password", type="password", key="_admin_pw_input")

    if st.button("Unlock", key="_admin_unlock_btn"):
        if entered == admin_password:
            st.session_state["_admin_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    return False


def render_admin_hub(admin_tabs: list[tuple[str, callable]]):
    """Render the admin landing page with cards for each protected tab."""
    st.header("Admin Tools")

    cols = st.columns(min(len(admin_tabs), 3))
    for i, (label, _render_fn) in enumerate(admin_tabs):
        col = cols[i % 3]
        with col:
            with st.container(border=True):
                st.subheader(label)
                if st.button("Open", key=f"_admin_open_{label}", use_container_width=True):
                    st.session_state["_admin_selected_tab"] = label
                    st.rerun()

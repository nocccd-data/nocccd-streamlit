"""Admin configuration — defines which tabs require password authentication.

Add tab labels to PROTECTED_TABS to require the admin password before
the tab renders. The password is stored in .streamlit/secrets.toml
under [admin].password.
"""

PROTECTED_TABS = {
    "Mail Admin",
}

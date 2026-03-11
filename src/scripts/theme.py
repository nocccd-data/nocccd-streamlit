import streamlit as st

NAVY = "#003056"

THEME_CSS = """\
<style>
/* Main headings */
[data-testid="stApp"] h1,
[data-testid="stApp"] h2,
[data-testid="stApp"] h3,
[data-testid="stApp"] h4 {
    color: light-dark(#003056, #FFFFFF) !important;
}

/* Home card backgrounds & borders */
[data-testid="stColumn"] [data-testid="stVerticalBlock"] {
    background-color: light-dark(#E8E8E8, #000000) !important;
    border-color: light-dark(#AAAAAA, #333333) !important;
}

/* Card text */
[data-testid="stColumn"] [data-testid="stVerticalBlock"] p,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] span,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] label,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] h1,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] h2,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] h3,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] h4 {
    color: light-dark(#000000, #FFFFFF) !important;
}

/* Expander inside cards */
[data-testid="stColumn"] [data-testid="stVerticalBlock"] [data-testid="stExpander"] {
    background-color: light-dark(#E8E8E8, #000000) !important;
    border-color: light-dark(#AAAAAA, #333333) !important;
}
[data-testid="stColumn"] [data-testid="stVerticalBlock"] [data-testid="stExpander"] summary {
    background-color: light-dark(#D0D0D0, #111111) !important;
    color: light-dark(#000000, #FFFFFF) !important;
}
[data-testid="stColumn"] [data-testid="stVerticalBlock"] [data-testid="stExpander"] summary span,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] [data-testid="stExpander"] summary p,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] [data-testid="stExpander"] summary svg {
    color: light-dark(#000000, #FFFFFF) !important;
    fill: light-dark(#000000, #FFFFFF) !important;
}

/* Progress bar */
[data-testid="stProgress"] > div {
    background-color: light-dark(transparent, #000000) !important;
}
[data-testid="stProgress"] [role="progressbar"] {
    background-color: light-dark(#003056, #FFFFFF) !important;
}

/* Buttons inside cards */
[data-testid="stColumn"] [data-testid="stVerticalBlock"] button[kind="secondary"] {
    background-color: light-dark(#003056, #111111) !important;
    color: #FFFFFF !important;
    border-color: light-dark(#003056, #555555) !important;
}
[data-testid="stColumn"] [data-testid="stVerticalBlock"] button[kind="secondary"] p {
    color: #FFFFFF !important;
}

/* Sidebar widgets */
[data-testid="stSidebar"] button[kind="secondary"] {
    background-color: rgba(255,255,255,0.1);
    color: #FFFFFF;
    border-color: rgba(255,255,255,0.3);
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"],
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background-color: light-dark(rgba(255,255,255,0.15), rgba(255,255,255,0.1)) !important;
    border-color: rgba(255,255,255,0.3) !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] span,
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] div,
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] svg {
    color: #FFFFFF !important;
    fill: #FFFFFF !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.2);
}
</style>"""


def apply_theme():
    """Apply NOCCCD theme overrides. Uses light-dark() CSS function
    which resolves automatically from Streamlit's color-scheme property."""
    st.html(THEME_CSS)

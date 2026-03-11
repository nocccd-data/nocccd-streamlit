import streamlit as st

# NOCCCD brand colors
NAVY = "#003056"
GOLD = "#F0AB00"

LIGHT_CSS = f"""
<style>
/* ── Sidebar: NOCCCD dark navy ── */
[data-testid="stSidebar"] {{ background-color: {NAVY}; }}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4 {{ color: #FFFFFF; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.2); }}
[data-testid="stSidebar"] button[kind="secondary"] {{
    background-color: rgba(255,255,255,0.1); color: #FFFFFF; border-color: rgba(255,255,255,0.3);
}}
[data-testid="stSidebar"] [data-baseweb="select"] {{ background-color: rgba(255,255,255,0.1); color: #FFFFFF; }}
/* ── Main pane: white with dark text ── */
[data-testid="stApp"] {{ background-color: #FFFFFF; color: #333333; }}
[data-testid="stHeader"] {{ background-color: #FFFFFF; }}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] h1,
[data-testid="stApp"] [data-testid="stMainBlockContainer"] h2,
[data-testid="stApp"] [data-testid="stMainBlockContainer"] h3,
[data-testid="stApp"] [data-testid="stMainBlockContainer"] h4 {{ color: {NAVY}; }}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] p,
[data-testid="stApp"] [data-testid="stMainBlockContainer"] span,
[data-testid="stApp"] [data-testid="stMainBlockContainer"] label,
[data-testid="stApp"] [data-testid="stMainBlockContainer"] .stMarkdown {{ color: #333333; }}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] .stCaption {{ color: #666666; }}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] [data-testid="stMetricLabel"] {{ color: #666666; }}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] [data-testid="stMetricValue"] {{ color: #333333; }}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] button[kind="secondary"] {{
    background-color: {NAVY}; color: #FFFFFF !important; border-color: {NAVY};
}}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] button[kind="secondary"] p {{
    color: #FFFFFF !important;
}}
[data-testid="stApp"] [data-testid="stMainBlockContainer"] [data-testid="stProgress"] p {{ color: #666666; }}
/* ── Home cards: light grey background ── */
[data-testid="stColumn"] [data-testid="stVerticalBlock"] {{
    background-color: #E8E8E8 !important; border-color: #D0D0D0 !important;
}}
</style>
"""

DARK_CSS = """
<style>
/* ── App shell ── */
[data-testid="stApp"] { background-color: #000000; color: #FFFFFF; }
[data-testid="stHeader"] { background-color: #000000; }
[data-testid="stSidebar"] { background-color: #0A0A0A; color: #FFFFFF; }

/* ── Text elements ── */
[data-testid="stApp"] h1, h2, h3, h4, h5, h6,
[data-testid="stApp"] p, span, label, .stMarkdown { color: #FFFFFF; }
[data-testid="stApp"] .stCaption { color: #CCCCCC; }

/* ── Inputs (selectbox, multiselect, text input, number input) ── */
[data-testid="stApp"] [data-baseweb="select"],
[data-testid="stApp"] [data-baseweb="input"] {
    background-color: #111111; color: #FFFFFF;
}
[data-testid="stApp"] [data-baseweb="tag"] { background-color: #333333; }

/* ── Buttons ── */
[data-testid="stApp"] button[kind="secondary"] {
    background-color: #111111; color: #FFFFFF; border-color: #555555;
}

/* ── Radio ── */
[data-testid="stApp"] [role="radiogroup"] label { color: #FFFFFF; }

/* ── Dataframe ── */
[data-testid="stApp"] [data-testid="stDataFrame"] {
    background-color: #0A0A0A;
}

/* ── Metric ── */
[data-testid="stApp"] [data-testid="stMetric"] {
    background-color: #0A0A0A; border-radius: 0.5rem; padding: 0.75rem;
}
[data-testid="stApp"] [data-testid="stMetricLabel"] { color: #CCCCCC; }
[data-testid="stApp"] [data-testid="stMetricValue"] { color: #FFFFFF; }

/* ── Expander ── */
[data-testid="stApp"] [data-testid="stExpander"] {
    background-color: #0A0A0A; border-color: #333333;
}

/* ── Container with border (home cards) ── */
[data-testid="stColumn"] [data-testid="stVerticalBlock"] {
    background-color: #0A0A0A !important; border-color: #333333 !important;
}

/* ── Alerts (info, warning) ── */
[data-testid="stApp"] [data-testid="stAlert"] { color: #FFFFFF; }

/* ── Divider ── */
[data-testid="stApp"] hr { border-color: #333333; }

/* ── Progress bar ── */
[data-testid="stApp"] [data-testid="stProgress"] p { color: #CCCCCC; }
</style>
"""


def render_theme_toggle():
    """Render the dark-mode toggle at the bottom of the sidebar."""
    st.sidebar.toggle(":moon: Dark mode", key="_dark_mode")


def apply_theme():
    """Apply NOCCCD light theme by default; layer dark CSS if toggled."""
    if st.session_state.get("_dark_mode", False):
        st.markdown(DARK_CSS, unsafe_allow_html=True)
    else:
        st.markdown(LIGHT_CSS, unsafe_allow_html=True)

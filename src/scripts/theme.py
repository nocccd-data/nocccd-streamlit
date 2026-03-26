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

/* Home card backgrounds */
[data-testid="stColumn"] [data-testid="stVerticalBlock"] {
    background-color: light-dark(#E8E8E8, #000000) !important;
}

/* Metric card borders (COI tab totals — not Home cards) */
[data-testid="stColumn"] [data-testid="stVerticalBlock"]:has([data-testid="stMetric"]) {
    border: 1px solid light-dark(#AAAAAA, rgba(255, 255, 255, 0.2)) !important;
    border-radius: 0.5rem !important;
    padding: 1rem !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    display: flex !important;
    justify-content: center !important;
    width: 100% !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] > div {
    width: 100% !important;
    text-align: center !important;
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
    border-color: light-dark(#AAAAAA, rgba(255, 255, 255, 0.2)) !important;
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
[data-testid="stProgress"] [role="progressbar"] > div > div > div {
    background-color: light-dark(#003056, #3D9DF3) !important;
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
/* Expander borders — darker in light mode */
[data-testid="stExpander"] details {
    border-color: light-dark(#AAAAAA, rgba(255, 255, 255, 0.2)) !important;
}

/* Expandable crosstab headers (MIS SP tabs) */
.grid-row.header,
.sub-table thead th {
    background: light-dark(#E8E8E8, #555) !important;
    color: light-dark(#000000, #FFFFFF) !important;
}

/* Ensure dropdown shows all options without scrolling */
[data-testid="stSelectboxVirtualDropdown"] {
    max-height: 500px !important;
}

/* Selectbox dropdown menu (portaled outside sidebar — no ancestor scope) */
[data-testid="stSelectboxVirtualDropdown"] li[role="option"],
[data-testid="stSelectboxVirtualDropdown"] li[role="option"] div,
[data-testid="stSelectboxVirtualDropdown"] li[role="option"] span {
    color: light-dark(#000000, #FFFFFF) !important;
}
/* Separator after "Home" in project dropdown (applied via JS) */
.project-dropdown-sep {
    border-bottom: 1px solid light-dark(#444444, #AAAAAA) !important;
}

/* Seat count banded report */
.sc-banded { width: 100%; border-collapse: collapse; font-size: 13px; }
.sc-banded th {
    background: light-dark(#003056, #1A3A5C) !important;
    color: #FFFFFF !important;
    padding: 6px 10px; text-align: center; position: sticky; top: 0;
    border: 1px solid light-dark(#002040, #0D2137);
}
.sc-banded td {
    padding: 4px 10px;
    border: 1px solid light-dark(#DDDDDD, #333333);
    color: light-dark(#000000, #FFFFFF) !important;
}
.sc-banded .dept-header td {
    background: light-dark(#D6E4F0, #1A3A5C) !important;
    font-weight: bold; font-size: 14px;
    color: light-dark(#003056, #FFFFFF) !important;
    border-bottom: 2px solid light-dark(#003056, #3D9DF3) !important;
}
.sc-banded .course-header td {
    background: light-dark(#F0F4F8, #2D3748) !important;
    font-weight: 600; font-style: italic;
    color: light-dark(#003056, #CBD5E0) !important;
}
.sc-banded .subtotal-row td {
    font-weight: bold;
    border-top: 2px solid light-dark(#888888, #AAAAAA) !important;
    background: light-dark(#F5F5F5, #1A1A2E) !important;
}
.sc-banded .dept-total td {
    font-weight: bold;
    border-top: 3px double light-dark(#003056, #3D9DF3) !important;
    background: light-dark(#E8EEF4, #0F2A3E) !important;
}
.sc-banded tr:hover td { background: light-dark(#FFFDE7, #2C2C00) !important; }
.sc-fillrate-high { background: light-dark(#D4EDDA, #1B4D3E) !important; }
.sc-fillrate-med  { background: light-dark(#FFF3CD, #4D3F00) !important; }
.sc-fillrate-low  { background: light-dark(#F8D7DA, #4D1F24) !important; }
</style>"""


# Propagate color-scheme from stApp to <html> so portaled elements
# (e.g. selectbox dropdowns) inherit it and light-dark() resolves correctly.
_COLOR_SCHEME_SYNC = """\
<script>
(function() {
  if (window.__nocccdThemeObs) return;
  function sync() {
    var app = document.querySelector('[data-testid="stApp"]');
    if (app) {
      var cs = getComputedStyle(app).colorScheme;
      if (cs && cs !== 'normal') document.documentElement.style.colorScheme = cs;
    }
  }
  sync();
  var app = document.querySelector('[data-testid="stApp"]');
  if (app) {
    new MutationObserver(sync).observe(app, {attributes: true, attributeFilter: ['class']});
  }
  window.__nocccdThemeObs = true;

  // Add separator only to the project dropdown (first option = "Home")
  new MutationObserver(function() {
    document.querySelectorAll('[data-testid="stSelectboxVirtualDropdown"]').forEach(function(dd) {
      var first = dd.querySelector('li[role="option"]:first-child');
      if (first && first.textContent.trim() === 'Home') {
        first.classList.add('project-dropdown-sep');
      }
    });
  }).observe(document.body, {childList: true, subtree: true});
})();
</script>"""


def apply_theme():
    """Apply NOCCCD theme overrides. Uses light-dark() CSS function
    which resolves automatically from Streamlit's color-scheme property.
    A small JS snippet propagates color-scheme to <html> so portaled
    elements (selectbox dropdowns) also respond to light-dark()."""
    st.html(THEME_CSS)
    st.html(_COLOR_SCHEME_SYNC, unsafe_allow_javascript=True)

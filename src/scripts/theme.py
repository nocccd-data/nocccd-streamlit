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
[data-testid="stProgress"] [data-testid="stProgressBarTrack"] > div {
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
/* Selectbox (React Aria): a div[role="group"] holding the combobox input */
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="group"] {
    background-color: rgba(255,255,255,0.1) !important;
    border-color: rgba(255,255,255,0.3) !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="group"] input,
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="group"] svg {
    color: #FFFFFF !important;
    fill: #FFFFFF !important;
}
/* Sidebar multiselect in light mode: the box is white, but its typed text,
   placeholder and "Clear all" / "Open" icons take the sidebar's white text.
   (Chip remove buttons sit deeper, inside stMultiSelectTagsContainer.) */
html[data-app-scheme="light"] [data-testid="stSidebar"] [data-testid="stMultiSelect"] div[role="group"] input {
    color: #000000 !important;
}
html[data-app-scheme="light"] [data-testid="stSidebar"] [data-testid="stMultiSelect"] div[role="group"] input::placeholder {
    color: rgba(0,0,0,0.6) !important;
}
html[data-app-scheme="light"] [data-testid="stSidebar"] [data-testid="stMultiSelect"] div[role="group"] > button svg {
    color: rgba(0,0,0,0.6) !important;
    fill: rgba(0,0,0,0.6) !important;
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
[data-testid="stSelectboxVirtualDropdown"] [role="option"],
[data-testid="stSelectboxVirtualDropdown"] [role="option"] div,
[data-testid="stSelectboxVirtualDropdown"] [role="option"] span {
    color: light-dark(#000000, #FFFFFF) !important;
}
/* Hovered/keyboard-focused option: a sidebar dropdown takes the sidebar's
   white tint, invisible on the white list. Use the main-area highlight. */
[data-testid="stSelectboxVirtualDropdown"] [role="option"][data-focused] [data-item-hl] {
    background-color: light-dark(rgba(166,166,166,0.15), rgba(158,158,158,0.15)) !important;
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

/* Student Headcount by Type cards (kpi_styp_headcount.py). Container keys:
   ksh_grid_* a card grid, ksh_card_* plain card, ksh_hl_* highlighted card,
   ksh_head_* the title row, ksh_up_* / ksh_down_* / ksh_flat_* the change figure. Every
   block inside a ksh_ container is transparent, which clears the grid's empty
   slots; the card rules carry one more selector so they still paint the
   cards. The stColumn prefix outranks the
   Home card and card text rules above, which would otherwise paint every
   block in a column grey and every span black. */
[data-testid="stColumn"] [data-testid="stVerticalBlock"][class*="st-key-ksh_card_"] {
    background-color: light-dark(#FFFFFF, #0A0A0A) !important;
    border-color: light-dark(#C9D3E0, rgba(255, 255, 255, 0.2)) !important;
}
[data-testid="stColumn"] [data-testid="stVerticalBlock"][class*="st-key-ksh_hl_"] {
    background-color: light-dark(#FFF6EA, rgba(224, 137, 43, 0.12)) !important;
    border: 2px solid #E0892B !important;
}
[class*="st-key-ksh_"] [data-testid="stVerticalBlock"] {
    background-color: transparent !important;
}
[class*="st-key-ksh_head_"] {
    border-left: 4px solid #9DB2CE;
    padding-left: 0.6rem;
}
[class*="st-key-ksh_head_hl_"] {
    border-left-color: #E0892B;
}
[data-testid="stColumn"] [class*="st-key-ksh_head_"] [data-testid="stMarkdownContainer"] strong {
    color: light-dark(#003056, #FFFFFF) !important;
}
[data-testid="stColumn"] [class*="st-key-ksh_up_"] [data-testid="stMarkdownContainer"] p,
[data-testid="stColumn"] [class*="st-key-ksh_down_"] [data-testid="stMarkdownContainer"] p,
[data-testid="stColumn"] [class*="st-key-ksh_flat_"] [data-testid="stMarkdownContainer"] p {
    font-size: 1.35rem;
    line-height: 1.2;
}
[data-testid="stColumn"] [class*="st-key-ksh_up_"] [data-testid="stMarkdownContainer"] strong {
    color: light-dark(#1B7F30, #66BB6A) !important;
}
[data-testid="stColumn"] [class*="st-key-ksh_down_"] [data-testid="stMarkdownContainer"] strong {
    color: light-dark(#C62828, #EF5350) !important;
}
[data-testid="stColumn"] [class*="st-key-ksh_flat_"] [data-testid="stMarkdownContainer"] strong {
    color: light-dark(#555555, #AAAAAA) !important;
}
/* Its sidebar "Highlight fastest-growing" toggle: the "on" track defaults to
   primaryColor navy, invisible on the navy light-mode sidebar. Orange matches
   the highlighted cards and shows on both sidebars. The track is the div right
   after the visually-hidden input's span (Streamlit 1.66 DOM). */
.st-key-ksh_highlight [data-testid="stCheckbox"][data-selected="true"] label > span + div {
    background-color: #E0892B !important;
}
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
      if (cs && cs !== 'normal') {
        document.documentElement.style.colorScheme = cs;
        // The sidebar is always color-scheme: dark, so light-dark() inside it
        // can't see the app theme; CSS keys on this attribute instead.
        document.documentElement.dataset.appScheme = cs;
      }
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
      var first = dd.querySelector('[role="option"]:first-child');
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

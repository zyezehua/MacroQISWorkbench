import streamlit as st

# Shared global styling. Injected once per page (and on the home page) so the
# look is consistent and we only maintain one copy of the CSS.
#
# Goals:
#  - Smaller, denser typography (the default Streamlit sizing was too large and
#    caused frequent "..." truncation in metric labels and headers).
#  - Allow metric labels/values to wrap instead of being ellipsis-clipped.
_GLOBAL_CSS = """<style>
/* ---- Base typography: tighten the default Streamlit sizing ---- */
section[data-testid="stMain"] { font-size: 0.92rem; }
section[data-testid="stMain"] h1 { font-size: 1.6rem !important; }
section[data-testid="stMain"] h2 { font-size: 1.25rem !important; }
section[data-testid="stMain"] h3 { font-size: 1.05rem !important; }
[data-testid="stSidebar"] { font-size: 0.88rem; }

/* ---- Metrics: smaller and, crucially, no ellipsis truncation ---- */
[data-testid="stMetricValue"] {
    font-size: 1rem !important;
    overflow: visible !important;
    text-overflow: clip !important;
    white-space: normal !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    overflow: visible !important;
}
[data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] div {
    overflow: visible !important;
    text-overflow: clip !important;
    white-space: normal !important;
}
[data-testid="stMetricDelta"] { font-size: 0.72rem !important; }
</style>"""


def inject_global_css():
    """Inject the shared global stylesheet. Call once near the top of each page."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

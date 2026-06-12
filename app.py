import streamlit as st

from ui.style import inject_global_css

st.set_page_config(
    page_title="Macro QIS Workbench",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()

st.title("📊 Macro QIS Workbench")
st.markdown("**Structurer toolkit · Proof of Concept**")
st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    ### 🔍 Idea Scanner
    Screen the current macro environment against 6 product classes.
    Get a structured scorecard with regime signals, product suitability,
    liquidity checks, and indicative xVA flags.

    → **Pages › Idea Scanner**
    """)

with col2:
    st.markdown("""
    ### 💹 Pricing Calculator
    Indicative pricing and greeks for:
    Swaptions · Bond futures options · Equity vanilla strategies ·
    Autocall notes · Vol products · Systematic strategies.

    → **Pages › Pricing**
    """)

with col3:
    st.markdown("""
    ### 📈 Backtest & Scenarios
    Historical P&L simulation in both payoff and delta-hedged modes.
    Stress-test against 2008, 2020, 2022 rate-hiking cycle scenarios.
    P&L attribution: delta / vega / theta / residual.

    → **Pages › Backtest**
    """)

st.divider()
st.caption(
    "Data: yfinance (live) · FRED (macro, requires `FRED_API_KEY` env var) · "
    "All outputs are indicative only. Internal data integration preserved for future build-out."
)

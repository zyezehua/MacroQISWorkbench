import streamlit as st


_REGIME_LABELS = {
    # yield curve
    "steep": ("Steep", "🟢"),
    "flat": ("Flat", "🟡"),
    "mildly_inverted": ("Mildly Inverted", "🟠"),
    "deeply_inverted": ("Deeply Inverted", "🔴"),
    # vol level
    "suppressed": ("Suppressed", "🟢"),
    "low": ("Low", "🟢"),
    "normal": ("Normal", "🟡"),
    "elevated": ("Elevated", "🟠"),
    "spike": ("Vol Spike", "🔴"),
    # vol term structure
    "contango": ("Contango", "🟢"),
    "flat": ("Flat TS", "🟡"),
    "backwardation": ("Backwardation", "🔴"),
    "unknown": ("N/A", "⚪"),
    # rate level
    "low": ("Low Rates", "🟢"),
    "moderate": ("Moderate", "🟡"),
    "high": ("High", "🟠"),
    "very_high": ("Very High", "🔴"),
    # rv/iv
    "rv_rich": ("RV > IV", "🟠"),
    "iv_rich": ("IV > RV", "🟢"),
    "fairly_priced": ("Fairly Priced", "🟡"),
    "unknown": ("N/A", "⚪"),
}


def _label(key):
    entry = _REGIME_LABELS.get(key)
    if entry:
        return f"{entry[1]} {entry[0]}"
    return key.replace("_", " ").title()


def render_regime(regime):
    st.subheader("Market Regime")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Yield Curve", _label(regime.get("yield_curve", "unknown")),
                  delta=f"{regime.get('curve_spread_2s10s', 0):+.2f}%  2s10s")
    with c2:
        st.metric("Vol Level (VIX)", _label(regime.get("vol_level", "unknown")),
                  delta=f"{regime.get('vix', 0):.1f}")
    with c3:
        st.metric("Vol Term Structure", _label(regime.get("vol_term_structure", "unknown")),
                  delta=f"slope {regime.get('ts_slope', 0):+.2%}")
    with c4:
        st.metric("Rate Level (10Y)", _label(regime.get("rate_level", "unknown")),
                  delta=f"{regime.get('us10y', 0):.2f}%")
    with c5:
        st.metric("RV / IV", _label(regime.get("rv_iv_rel", "unknown")),
                  delta=f"ratio {regime.get('rv_iv_ratio') or 0:.2f}" if regime.get("rv_iv_ratio") else "N/A")


def render_market_snapshot(snapshot):
    st.subheader("Market Snapshot")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Equity**")
        for name in ("SPX", "SX5E", "NDX"):
            val = snapshot.get(f"spot_{name}")
            if val:
                st.metric(name, f"{val:,.0f}")

    with col2:
        st.markdown("**Volatility**")
        for name in ("VIX", "VIX3M", "VVIX"):
            val = snapshot.get(name)
            if val:
                st.metric(name, f"{val:.2f}")
        rv = snapshot.get("rv_21d")
        if rv:
            st.metric("SPX RV 1M", f"{rv*100:.1f}%")

    with col3:
        st.markdown("**Rates**")
        for label, key in [("2Y", "US2Y"), ("5Y", "US5Y"), ("10Y", "US10Y"), ("30Y", "US30Y")]:
            val = snapshot.get(key)
            if val:
                st.metric(f"US {label}", f"{val:.2f}%")
        spread = snapshot.get("2s10s")
        if spread is not None:
            st.metric("2s10s Spread", f"{spread:+.2f}%")

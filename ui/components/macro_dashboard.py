import streamlit as st
import pandas as pd


_REGIME_LABELS = {
    "steep":            ("Steep",           "🟢"),
    "flat":             ("Flat",            "🟡"),
    "mildly_inverted":  ("Mildly Inverted", "🟠"),
    "deeply_inverted":  ("Deeply Inverted", "🔴"),
    "suppressed":       ("Suppressed",      "🟢"),
    "low":              ("Low",             "🟢"),
    "normal":           ("Normal",          "🟡"),
    "elevated":         ("Elevated",        "🟠"),
    "spike":            ("Vol Spike",       "🔴"),
    "contango":         ("Contango",        "🟢"),
    "backwardation":    ("Backwardation",   "🔴"),
    "moderate":         ("Moderate",        "🟡"),
    "high":             ("High",            "🟠"),
    "very_high":        ("Very High",       "🔴"),
    "rv_rich":          ("RV > IV",         "🟠"),
    "iv_rich":          ("IV > RV",         "🟢"),
    "fairly_priced":    ("Fairly Priced",   "🟡"),
    "unknown":          ("N/A",             "⚪"),
}


def _label(key):
    entry = _REGIME_LABELS.get(key)
    if entry:
        return f"{entry[1]} {entry[0]}"
    return str(key).replace("_", " ").title()


def render_regime(regime):
    st.subheader("Market Regime")
    # Row 1: curve, vol level, vol term structure
    c1, c2, c3 = st.columns(3)
    with c1:
        spread = regime.get("curve_spread_2s10s", 0) or 0
        st.metric("Yield Curve", _label(regime.get("yield_curve", "unknown")),
                  f"2s10s {spread:+.2f}%", delta_color="off")
    with c2:
        vix = regime.get("vix", 0) or 0
        st.metric("Vol Level (VIX)", _label(regime.get("vol_level", "unknown")),
                  f"VIX {vix:.1f}", delta_color="off")
    with c3:
        slope = regime.get("ts_slope", 0) or 0
        st.metric("Vol Term Structure", _label(regime.get("vol_term_structure", "unknown")),
                  f"slope {slope:+.2%}", delta_color="off")

    # Row 2: rate level, RV/IV
    c4, c5 = st.columns(2)
    with c4:
        us10y = regime.get("us10y", 0) or 0
        st.metric("Rate Level (10Y)", _label(regime.get("rate_level", "unknown")),
                  f"US10Y {us10y:.2f}%", delta_color="off")
    with c5:
        ratio = regime.get("rv_iv_ratio")
        ratio_str = f"ratio {ratio:.2f}" if ratio else "N/A"
        st.metric("RV / IV", _label(regime.get("rv_iv_rel", "unknown")),
                  ratio_str, delta_color="off")


def render_market_snapshot(snapshot):
    st.subheader("Market Snapshot")

    # Determine as-of date from snapshot or fallback to today
    as_of = snapshot.get("as_of_date")
    if as_of:
        st.caption(f"As of: {pd.Timestamp(as_of).strftime('%Y-%m-%d')}")
    else:
        st.caption("As of: latest available trading day")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Equity**")
        any_equity = False
        for name in ("SPX", "NDX", "SX5E"):
            val = snapshot.get(f"spot_{name}") or snapshot.get(name)
            if val and val > 0:
                st.metric(name, f"{val:,.0f}", delta_color="off")
                any_equity = True
        if not any_equity:
            st.caption("No equity data — check connection")

    with col2:
        st.markdown("**Volatility**")
        for name, key in [("VIX", "VIX"), ("VIX 3M", "VIX3M"), ("VVIX", "VVIX")]:
            val = snapshot.get(key)
            if val and val > 0:
                st.metric(name, f"{val:.2f}", delta_color="off")
        rv = snapshot.get("rv_21d")
        if rv and rv > 0:
            st.metric("SPX RV 21d", f"{rv*100:.1f}%", delta_color="off")
        rv63 = snapshot.get("rv_63d")
        if rv63 and rv63 > 0:
            st.metric("SPX RV 63d", f"{rv63*100:.1f}%", delta_color="off")

    with col3:
        st.markdown("**Rates**")
        for label, key in [("3M", "US3M"), ("2Y", "US2Y"), ("5Y", "US5Y"),
                            ("10Y", "US10Y"), ("30Y", "US30Y")]:
            val = snapshot.get(key)
            if val and val > 0:
                st.metric(f"US {label}", f"{val:.2f}%", delta_color="off")
        spread = snapshot.get("2s10s")
        if spread is not None:
            st.metric("2s10s Spread", f"{spread:+.2f}%", delta_color="off")
        spread_3m = snapshot.get("3m10y")
        if spread_3m is not None and spread is None:
            st.metric("3m10y Spread", f"{spread_3m:+.2f}%", delta_color="off")

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from config import CLIENT_TYPES, SCORECARD_DIMENSIONS, PRODUCTS
from modules.idea_scanner.scanner import run_scan
from ui.components.macro_dashboard import render_regime, render_market_snapshot
from ui.components.scorecard_table import render_scorecard, render_top_idea

st.set_page_config(page_title="Idea Scanner · Macro QIS", page_icon="🔍", layout="wide")

st.markdown("""<style>
[data-testid="stMetricValue"] { font-size: 1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.72rem !important; }
</style>""", unsafe_allow_html=True)

st.title("🔍 Idea Scanner")
st.caption("Macro regime → product scorecard with compliance and liquidity flags")

# ── Session state defaults ─────────────────────────────────────────────────────
if "overrides" not in st.session_state:
    st.session_state.overrides = {}
if "result" not in st.session_state:
    st.session_state.result = None
if "scanner_reset" not in st.session_state:
    st.session_state.scanner_reset = 0

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Parameters")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        run_btn = st.button("▶ Run Scan", type="primary", use_container_width=True)
    with col_r2:
        if st.button("↺ Reset", use_container_width=True):
            st.session_state.overrides = {}
            st.session_state.result = None
            st.session_state.scanner_reset += 1
            st.rerun()

    reset_key = st.session_state.scanner_reset

    client_type = st.selectbox("Client Type", CLIENT_TYPES, index=1,
                                key=f"client_{reset_key}")

    st.markdown("---")
    st.markdown("**Scorecard Weights**")
    weights = {}
    for dim, default_w in SCORECARD_DIMENSIONS.items():
        weights[dim] = st.slider(
            dim.replace("_", " ").title(),
            min_value=0.0, max_value=1.0,
            value=float(default_w), step=0.05,
            key=f"w_{dim}_{reset_key}",
        )

    st.markdown("---")
    st.markdown("**Manual Market Overrides**")
    st.caption("Leave at 0 / 0.0 to use live data")
    ov_vix   = st.number_input("VIX override", min_value=0.0, max_value=100.0,
                                value=0.0, step=0.5, key=f"ov_vix_{reset_key}")
    ov_us10y = st.number_input("US 10Y override (%)", min_value=0.0, max_value=15.0,
                                value=0.0, step=0.1, key=f"ov_10y_{reset_key}")
    ov_2s10s = st.number_input("2s10s override (%)", min_value=-5.0, max_value=5.0,
                                value=0.0, step=0.05, key=f"ov_2s10s_{reset_key}")

    st.markdown("---")
    st.markdown("**Score Overrides (per product)**")
    st.caption("Override individual scorecard cells")
    override_prod = st.selectbox("Product", list(PRODUCTS.keys()),
                                  format_func=lambda k: PRODUCTS[k],
                                  key=f"ov_prod_{reset_key}")
    override_dim  = st.selectbox("Dimension", list(SCORECARD_DIMENSIONS.keys()),
                                  format_func=lambda d: d.replace("_", " ").title(),
                                  key=f"ov_dim_{reset_key}")
    override_val  = st.slider("Override Score", 0.0, 10.0, 5.0, step=0.5,
                               key=f"ov_val_{reset_key}")
    if st.button("Apply Override"):
        if override_prod not in st.session_state.overrides:
            st.session_state.overrides[override_prod] = {}
        st.session_state.overrides[override_prod][override_dim] = override_val
        st.success(f"Applied: {PRODUCTS[override_prod]} / {override_dim} = {override_val}")

    if st.session_state.overrides:
        st.markdown("**Active overrides:**")
        for pid, dims in st.session_state.overrides.items():
            for dim, val in dims.items():
                st.caption(f"{PRODUCTS[pid]} · {dim} → {val}")

# ── Run ────────────────────────────────────────────────────────────────────────
if run_btn or st.session_state.result is None:
    with st.spinner("Fetching live data and running scan..."):
        from data.market_snapshot import get_market_snapshot
        snapshot_overrides = {}
        if ov_vix   > 0:     snapshot_overrides["VIX"]   = ov_vix
        if ov_us10y > 0:     snapshot_overrides["US10Y"] = ov_us10y
        if ov_2s10s != 0:    snapshot_overrides["2s10s"] = ov_2s10s

        live_snap = get_market_snapshot(overrides=snapshot_overrides if snapshot_overrides else None)
        result = run_scan(
            client_type=client_type,
            weights=weights,
            overrides=st.session_state.overrides if st.session_state.overrides else None,
            snapshot=live_snap,
        )
        st.session_state.result = result

result = st.session_state.result

# ── Display ────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Scorecard", "🌐 Market Snapshot", "🔎 Regime Detail"])

with tab1:
    render_top_idea(result["scorecard"], result["signals"])
    st.divider()
    st.subheader("Full Scorecard")
    render_scorecard(result["scorecard"])

    with st.expander("Rationale Details"):
        for _, row in result["scorecard"].iterrows():
            sig = result["signals"].get(row["product_id"], {})
            st.markdown(f"**{row['Product']}** — *{sig.get('signal','—')}*")
            st.caption(sig.get("rationale", "—"))

with tab2:
    render_market_snapshot(result["snapshot"])

with tab3:
    render_regime(result["regime"])
    st.divider()
    st.json(result["regime"])

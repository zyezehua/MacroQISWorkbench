import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

from config import CLIENT_TYPES
from data.fetchers.rates_fetcher import get_current_rates
from data.fetchers.equity_fetcher import get_current_spot, get_historical_vol

from modules.pricing.structures.swaption import price_swaption
from modules.pricing.structures.bond_futures_options import price_bond_futures_option
from modules.pricing.structures.vanilla_strategies import (
    call, put, call_spread, put_spread, straddle, strangle,
    risk_reversal, covered_call, collar,
)
from modules.pricing.structures.autocall import price_autocall
from modules.pricing.structures.vol_products import price_var_swap, price_vol_swap, vix_roll_down
from modules.pricing.structures.structured_notes import (
    price_capital_protection_note, price_yield_enhancement_note,
)
from modules.pricing.xva_proxy import total_xva
from data.fetchers.equity_fetcher import get_vix_term_structure

st.set_page_config(page_title="Pricing · Macro QIS", page_icon="💹", layout="wide")
st.title("💹 Pricing Calculator")
st.caption("Indicative pricing · Black / Black-76 / Analytical approximation · PoC level")

# ── Sidebar global inputs ──────────────────────────────────────────────────────
with st.sidebar:
    st.header("Global Parameters")
    client_type = st.selectbox("Client Type", CLIENT_TYPES, index=1)
    notional = st.number_input("Notional", value=1_000_000, step=100_000, format="%d")

    st.markdown("---")
    st.markdown("**Market Rates (live or override)**")
    live_rates = {}
    with st.spinner("Fetching rates..."):
        try:
            live_rates = get_current_rates()
        except Exception:
            pass

    r_default = live_rates.get("US10Y", 4.5) / 100
    r = st.number_input("Risk-Free Rate (%)", value=round(live_rates.get("US10Y", 4.5), 2),
                         step=0.05, format="%.2f") / 100
    q = st.number_input("Dividend Yield / Repo (%)", value=1.5, step=0.1, format="%.2f") / 100

    st.markdown("---")
    st.markdown("**xVA Parameters**")
    cds_override = st.number_input("CDS Spread Override (bps, 0=default)", value=0, step=5)
    funding_spread = st.number_input("Funding Spread (bps)", value=50, step=5)

# ── Product tabs ───────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📐 Rate Swaption",
    "📊 Bond Futures Option",
    "📈 Equity Vanilla",
    "🌀 Vol Products",
    "🎯 Autocall",
    "🛡️ Structured Note",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: RATE SWAPTION
# ─────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Rate Swaption — Black-76")
    c1, c2, c3 = st.columns(3)
    with c1:
        opt_type = st.radio("Type", ["payer", "receiver"], horizontal=True)
        T_exp = st.number_input("Option Expiry (Y)", value=1.0, step=0.5, min_value=0.1)
        tenor = st.number_input("Swap Tenor (Y)", value=10.0, step=1.0, min_value=0.5)
    with c2:
        fwd_rate_pct = st.number_input("Forward Swap Rate (%)", value=4.30, step=0.05)
        fwd_rate = fwd_rate_pct / 100
        otm_bps = st.number_input("OTM Shift (bps, 0=ATM)", value=0, step=25)
        strike = fwd_rate + otm_bps / 10_000
        st.metric("Strike", f"{strike*100:.3f}%")
    with c3:
        sigma_sw = st.number_input("Swaption Vol (%)", value=22.0, step=1.0, min_value=0.1) / 100

    if st.button("Price Swaption", type="primary"):
        result = price_swaption(fwd_rate, strike, T_exp, tenor, sigma_sw,
                                notional=notional, option_type=opt_type)
        xva = total_xva("RATE_SWPN", T_exp + tenor, notional, client_type,
                        cds_override or None, funding_spread)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Price", f"{result['price_bps']:.1f} bps",
                    f"${result['price_amount']:,.0f}")
        col2.metric("Delta (DV01)", f"{result['delta_dv01_bps']:.1f} bps")
        col3.metric("Vega", f"{result['vega_bps']:.2f} bps / vol pt")
        col4.metric("Break-Even", f"{result['break_even_bps']:.1f} bps move")

        st.divider()
        col5, col6, col7 = st.columns(3)
        col5.metric("Theta", f"{result['theta_bps_day']:.3f} bps/day")
        col6.metric("xVA (CVA+FVA)", f"{xva['total_xva_bps']:.1f} bps",
                    f"${xva['total_xva_amount']:,.0f}")
        col7.metric("Net After xVA", f"{result['price_bps'] - xva['total_xva_bps']:.1f} bps")

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

        # Vol sensitivity chart
        vols = np.linspace(sigma_sw * 0.5, sigma_sw * 1.5, 30)
        prices = [price_swaption(fwd_rate, strike, T_exp, tenor, v,
                                  notional=notional, option_type=opt_type)["price_bps"] for v in vols]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=vols * 100, y=prices, mode="lines",
                                  line=dict(color="#4FC3F7", width=2)))
        fig.add_vline(x=sigma_sw * 100, line_dash="dash", line_color="#FFD600",
                       annotation_text=f"Current vol {sigma_sw*100:.1f}%")
        fig.update_layout(title="Price vs Vol", xaxis_title="Vol (%)",
                           yaxis_title="Price (bps)", template="plotly_dark",
                           height=300, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: BOND FUTURES OPTION
# ─────────────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("Bond Futures Option — Black-76")
    c1, c2 = st.columns(2)
    with c1:
        bfo_type = st.radio("Option Type", ["call", "put"], horizontal=True, key="bfo_type")
        futures_px = st.number_input("Futures Price (% par)", value=110.50, step=0.25)
        strike_bfo = st.number_input("Strike (% par)", value=110.50, step=0.25)
        T_bfo = st.number_input("Expiry (Y)", value=0.25, step=0.083, min_value=0.02)
    with c2:
        sigma_bfo = st.number_input("Vol (%)", value=8.0, step=0.5, min_value=0.1, key="sig_bfo") / 100

    if st.button("Price Bond Futures Option", type="primary"):
        result = price_bond_futures_option(futures_px, strike_bfo, T_bfo, sigma_bfo,
                                            r=r, notional=notional, option_type=bfo_type)
        xva = total_xva("RATE_BFO", T_bfo, notional, client_type, cds_override or None, funding_spread)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Price", f"{result['price_pct']:.4f}% par",
                    f"${result['price_amount']:,.0f}")
        col2.metric("Delta", f"{result['delta']:.4f}")
        col3.metric("Vega", f"${result['vega_per_vol_pt']:,.0f} / vol pt")
        col4.metric("Moneyness", f"{result['moneyness_pct']:+.2f}%")

        col5, col6 = st.columns(2)
        col5.metric("Theta", f"${result['theta_per_day']:,.0f} / day")
        col6.metric("xVA", f"{xva['total_xva_bps']:.1f} bps")

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: EQUITY VANILLA STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("Equity Vanilla Strategies — Black-Scholes")

    c1, c2 = st.columns([1, 2])
    with c1:
        strategy = st.selectbox("Strategy", [
            "Call", "Put", "Call Spread", "Put Spread",
            "Straddle", "Strangle", "Risk Reversal", "Covered Call", "Collar",
        ])
        underlying = st.selectbox("Underlying", ["SPX (^GSPC)", "SX5E (^STOXX50E)", "Custom"])
        spot_default = 5300.0
        if underlying != "Custom":
            sym = "^GSPC" if "SPX" in underlying else "^STOXX50E"
            with st.spinner("Fetching spot..."):
                fetched = get_current_spot(sym)
                if fetched:
                    spot_default = fetched

        S = st.number_input("Spot", value=spot_default, step=10.0)
        T_eq = st.number_input("Expiry (Y)", value=0.25, step=0.083, min_value=0.01)
        sigma_eq = st.number_input("ATM Vol (%)", value=18.0, step=1.0, min_value=0.1) / 100

    with c2:
        if strategy in ("Call", "Put"):
            K = st.number_input("Strike", value=float(round(S)), step=10.0)
        elif strategy in ("Call Spread", "Risk Reversal"):
            K_lo = st.number_input("Lower Strike", value=float(round(S)), step=10.0)
            K_hi = st.number_input("Upper Strike", value=float(round(S * 1.05)), step=10.0)
        elif strategy in ("Put Spread", "Collar"):
            K_put = st.number_input("Put Strike", value=float(round(S * 0.95)), step=10.0)
            K_call = st.number_input("Call Strike", value=float(round(S * 1.05)), step=10.0)
        elif strategy == "Straddle":
            K = st.number_input("Strike", value=float(round(S)), step=10.0)
        elif strategy == "Strangle":
            K_put = st.number_input("Put Strike", value=float(round(S * 0.95)), step=10.0)
            K_call = st.number_input("Call Strike", value=float(round(S * 1.05)), step=10.0)
        elif strategy == "Covered Call":
            K = st.number_input("Call Strike", value=float(round(S * 1.03)), step=10.0)

        sigma_skew = st.number_input("OTM Vol Skew (pts per 5% OTM)", value=2.0, step=0.5) / 100

    def _skew_vol(strike, spot, atm_vol, skew):
        moneyness = (strike - spot) / spot
        return max(0.01, atm_vol - skew * moneyness * 20)

    if st.button("Price Strategy", type="primary"):
        result = None
        try:
            if strategy == "Call":
                result = call(S, K, T_eq, r, sigma_eq)
            elif strategy == "Put":
                result = put(S, K, T_eq, r, sigma_eq)
            elif strategy == "Call Spread":
                result = call_spread(S, K_lo, K_hi, T_eq, r, sigma_eq,
                                      _skew_vol(K_hi, S, sigma_eq, sigma_skew))
            elif strategy == "Put Spread":
                result = put_spread(S, K_put, K_call, T_eq, r, sigma_eq,
                                     _skew_vol(K_call, S, sigma_eq, sigma_skew))
            elif strategy == "Straddle":
                result = straddle(S, K, T_eq, r, sigma_eq)
            elif strategy == "Strangle":
                result = strangle(S, K_put, K_call, T_eq, r, sigma_eq,
                                   _skew_vol(K_put, S, sigma_eq, sigma_skew))
            elif strategy == "Risk Reversal":
                result = risk_reversal(S, K_lo, K_hi, T_eq, r, sigma_eq,
                                        _skew_vol(K_hi, S, sigma_eq, sigma_skew))
            elif strategy == "Covered Call":
                result = covered_call(S, K, T_eq, r, sigma_eq)
            elif strategy == "Collar":
                result = collar(S, K_put, K_call, T_eq, r, sigma_eq,
                                 _skew_vol(K_put, S, sigma_eq, sigma_skew))
        except Exception as e:
            st.error(f"Pricing error: {e}")
            result = None

        if result:
            xva = total_xva("EQ_VANILLA", T_eq, notional, client_type, cds_override or None, funding_spread)

            col1, col2, col3, col4 = st.columns(4)
            prem = result.get("net_premium", result.get("net_cost", result.get("call_premium_collected", 0)))
            prem_pct = result.get("net_premium_pct", result.get("net_cost_pct", result.get("premium_pct", 0)))
            col1.metric("Net Premium", f"{prem:.4f}", f"{prem_pct:.3f}% spot")
            col2.metric("Delta", f"{result.get('net_delta', result.get('put_delta', '—'))}")
            col3.metric("Vega", f"{result.get('net_vega', '—')}")
            col4.metric("xVA", f"{xva['total_xva_bps']:.1f} bps")

            if "break_even_up" in result:
                st.info(f"Break-evens: ↑ {result['break_even_up']:.1f}  |  ↓ {result['break_even_down']:.1f}")
            elif "break_even" in result and result["break_even"]:
                st.info(f"Break-even: {result['break_even']:.2f}")

            st.caption("Legs: " + " | ".join(result.get("legs", [])))

            with st.expander("Full Output"):
                st.json({**result, "xva": xva})

            # Payoff diagram
            spot_range = np.linspace(S * 0.7, S * 1.3, 200)
            payoffs = []
            for s in spot_range:
                try:
                    if strategy == "Call":
                        p = call(s, K, 0.001, r, sigma_eq)
                    elif strategy == "Put":
                        p = put(s, K, 0.001, r, sigma_eq)
                    elif strategy == "Call Spread":
                        p = call_spread(s, K_lo, K_hi, 0.001, r, sigma_eq, sigma_eq)
                    elif strategy == "Straddle":
                        p = straddle(s, K, 0.001, r, sigma_eq)
                    elif strategy == "Covered Call":
                        p = {"net_premium": covered_call(s, K, 0.001, r, sigma_eq)["call_premium_collected"] + (s - S)}
                    else:
                        p = result
                    payoff = p.get("net_premium", p.get("net_cost", 0)) - prem
                    payoffs.append(float(payoff))
                except Exception:
                    payoffs.append(0.0)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=list(spot_range), y=payoffs, mode="lines",
                                      fill="tozeroy",
                                      line=dict(color="#4FC3F7", width=2),
                                      fillcolor="rgba(79,195,247,0.15)"))
            fig.add_hline(y=0, line_color="#9E9E9E", line_dash="dash")
            fig.add_vline(x=S, line_color="#FFD600", line_dash="dot",
                           annotation_text="Current spot")
            fig.update_layout(title="At-Expiry Payoff", xaxis_title="Spot at Expiry",
                               yaxis_title="P&L", template="plotly_dark",
                               height=320, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: VOL PRODUCTS
# ─────────────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("Vol Products — Var/Vol Swap & VIX Roll")
    prod_choice = st.radio("Product", ["Variance Swap", "Vol Swap", "VIX Roll-Down"], horizontal=True)

    if prod_choice == "Variance Swap":
        c1, c2 = st.columns(2)
        with c1:
            atm_vol_vs = st.number_input("ATM Implied Vol (%)", value=18.0, step=0.5) / 100
            rv_input = st.number_input("Realized Vol to Date (%, 0=forward start)", value=0.0, step=0.5) / 100
            mat_vs = st.number_input("Maturity (Y)", value=0.5, step=0.083, min_value=0.01)
            pos_vs = st.radio("Position", ["short", "long"], horizontal=True)
        with c2:
            skew_vs = st.number_input("Skew Slope (d_vol/d_lnK)", value=-0.10, step=0.01)
            vega_notional = st.number_input("Vega Notional ($)", value=100_000, step=10_000)

        if st.button("Price Var Swap", type="primary"):
            rv = rv_input if rv_input > 0 else None
            result = price_var_swap(atm_vol_vs, rv, mat_vs, vega_notional, skew_vs, pos_vs)
            xva = total_xva("VOL_PROD", mat_vs, notional, client_type, cds_override or None, funding_spread)

            c1, c2, c3 = st.columns(3)
            c1.metric("Fair Var Strike (as vol)", f"{result['fair_var_strike_pct']:.2f}%")
            c2.metric("Fair Vol Strike", f"{result['fair_vol_strike_pct']:.2f}%")
            c3.metric("Break-even RV", f"{result['break_even_rv_pct']:.2f}%")
            if "pnl" in result:
                st.metric("MtM P&L", f"${result['pnl']:,.0f}")

            st.caption(f"Var Notional: ${result['var_notional']:,.0f}  |  xVA: {xva['total_xva_bps']:.1f} bps")
            with st.expander("Full Output"):
                st.json({**result, "xva": xva})

    elif prod_choice == "Vol Swap":
        atm_vol_vlsw = st.number_input("ATM Vol (%)", value=18.0, step=0.5, key="vs2") / 100
        mat_vlsw = st.number_input("Maturity (Y)", value=0.5, step=0.083, key="vs_mat")
        pos_vlsw = st.radio("Position", ["short", "long"], horizontal=True, key="vs_pos")

        if st.button("Price Vol Swap", type="primary"):
            result = price_vol_swap(atm_vol_vlsw, mat_vlsw, notional, pos_vlsw)
            c1, c2 = st.columns(2)
            c1.metric("Fair Vol Strike", f"{result['fair_vol_strike_pct']:.2f}%")
            c2.metric("Convexity Correction", f"{result['convexity_correction_bps']:.1f} bps")
            st.caption(f"Var vs Vol premium: {result['var_vs_vol_premium_bps']:.1f} bps")

    elif prod_choice == "VIX Roll-Down":
        with st.spinner("Fetching VIX..."):
            vix_ts = get_vix_term_structure()
        vix_spot_def = vix_ts.get("VIX") or 20.0
        vix3m_def = vix_ts.get("VIX3M") or 23.0

        c1, c2 = st.columns(2)
        with c1:
            vix_spot_in = st.number_input("VIX Spot", value=vix_spot_def, step=0.5)
            vix3m_in = st.number_input("VIX 3M", value=vix3m_def, step=0.5)
        with c2:
            roll_days = st.number_input("Rolling Horizon (days)", value=30, step=5)

        if st.button("Compute Roll-Down", type="primary"):
            result = vix_roll_down(vix_spot_in, vix3m_in, roll_days)
            c1, c2, c3 = st.columns(3)
            c1.metric("Contango", f"{result.get('contango_pct', 0):+.2f}%")
            c2.metric(f"Roll Carry ({roll_days}d)", f"{result.get('roll_carry_per_month', 0):.2f} vol pts")
            c3.metric("Ann. Carry", f"{result.get('annualised_carry_pct', 0):.2f}% / vix")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: AUTOCALL
# ─────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Autocall — Analytical Approximation (Single-Factor Gaussian)")
    st.caption("Indicative only. Path-dependent features approximated via survival probability decomposition.")

    c1, c2, c3 = st.columns(3)
    with c1:
        ac_sigma = st.number_input("Underlying Vol (%)", value=20.0, step=1.0, min_value=1.0) / 100
        ac_r = st.number_input("Risk-Free Rate (%)", value=round(r * 100, 2), step=0.05) / 100
        ac_q = st.number_input("Div Yield (%)", value=round(q * 100, 2), step=0.1) / 100
    with c2:
        ac_barrier = st.slider("Autocall Barrier (% initial)", 80, 120, 100) / 100
        ac_ki = st.slider("Knock-In Barrier (% initial)", 40, 85, 60) / 100
        ac_coupon = st.number_input("Annual Coupon (%)", value=8.0, step=0.5, min_value=0.0) / 100
    with c3:
        ac_maturity = st.selectbox("Maturity", [1, 2, 3, 5], index=2)
        ac_obs = st.selectbox("Observation", [4, 12, 1], index=0,
                               format_func=lambda x: {4: "Quarterly", 12: "Monthly", 1: "Annual"}[x])

    if st.button("Price Autocall", type="primary"):
        result = price_autocall(
            spot=100, barrier_pct=ac_barrier, coupon_barrier_pct=ac_barrier,
            ki_barrier_pct=ac_ki, coupon_pa=ac_coupon,
            maturity_years=ac_maturity, obs_per_year=ac_obs,
            sigma=ac_sigma, r=ac_r, q=ac_q, notional=notional,
        )
        xva = total_xva("STRUCT_AC", ac_maturity, notional, client_type, cds_override or None, funding_spread)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Indicative Price", f"{result['indicative_price_pct']:.2f}% par",
                    f"${result['indicative_price_amount']:,.0f}")
        col2.metric("Fair Coupon", f"{result['fair_coupon_pa_pct']:.2f}% p.a.")
        col3.metric("P(Survive to Mat.)", f"{result['prob_survive_to_maturity_pct']:.1f}%")
        col4.metric("P(KI Breach)", f"{result['prob_ki_breach_pct']:.2f}%")

        st.divider()
        col5, col6, col7 = st.columns(3)
        col5.metric("Coupon PV", f"${result['coupon_pv']:,.0f}")
        col6.metric("Autocall Redemption PV", f"${result['autocall_redemption_pv']:,.0f}")
        col7.metric("xVA (CVA+FVA)", f"{xva['total_xva_bps']:.1f} bps")

        # Vol sensitivity
        vols = np.linspace(0.10, 0.50, 20)
        prices = []
        fair_coupons = []
        for v in vols:
            r_ac = price_autocall(100, ac_barrier, ac_barrier, ac_ki, ac_coupon,
                                   ac_maturity, ac_obs, v, ac_r, ac_q, notional)
            prices.append(r_ac["indicative_price_pct"])
            fair_coupons.append(r_ac["fair_coupon_pa_pct"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[v * 100 for v in vols], y=fair_coupons,
                                  mode="lines", name="Fair Coupon (%pa)",
                                  line=dict(color="#00C853", width=2)))
        fig.add_vline(x=ac_sigma * 100, line_dash="dash", line_color="#FFD600",
                       annotation_text=f"Input vol {ac_sigma*100:.0f}%")
        fig.update_layout(title="Fair Coupon vs Vol", xaxis_title="Vol (%)",
                           yaxis_title="Coupon (% p.a.)", template="plotly_dark",
                           height=300, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

# ─────────────────────────────────────────────────────────────────────────────
# TAB 6: STRUCTURED NOTES
# ─────────────────────────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Structured Notes — Capital Protection & Yield Enhancement")
    note_type = st.radio("Note Type",
                          ["Capital Protection Note", "Yield Enhancement (Reverse Convertible)"],
                          horizontal=True)

    c1, c2 = st.columns(2)
    with c1:
        sn_spot = st.number_input("Spot / Reference Level", value=100.0, step=1.0)
        sn_mat = st.number_input("Maturity (Y)", value=3.0, step=0.5, min_value=0.5, key="sn_mat")
        sn_sigma = st.number_input("Vol (%)", value=18.0, step=1.0, key="sn_sig") / 100
        sn_r = st.number_input("Risk-Free Rate (%)", value=round(r * 100, 2), step=0.05, key="sn_r") / 100
        sn_q = st.number_input("Div Yield (%)", value=round(q * 100, 2), step=0.1, key="sn_q") / 100
    with c2:
        if note_type == "Capital Protection Note":
            protection = st.slider("Protection Level (%)", 80, 100, 100) / 100
            participation = st.slider("Participation Rate (%)", 50, 200, 100) / 100
            strike_ratio = st.slider("Call Strike (% of initial)", 90, 120, 100) / 100
        else:
            sn_strike_ratio = st.slider("Put Strike (% of spot)", 70, 105, 95) / 100

    if st.button("Price Note", type="primary"):
        if note_type == "Capital Protection Note":
            result = price_capital_protection_note(
                sn_spot, strike_ratio, participation, sn_mat,
                sn_r, sn_q, sn_sigma, protection, notional,
            )
            xva = total_xva("STRUCT_AC", sn_mat, notional, client_type, cds_override or None, funding_spread)

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Cost", f"{result['total_cost_pct']:.2f}%",
                        "✅ Feasible" if result["feasible"] else "❌ Over par")
            col2.metric("ZC Bond Cost", f"{result['zc_bond_cost_pct']:.2f}%")
            col3.metric("Call Option Cost", f"{result['call_cost_pct']:.2f}%")

            col4, col5, col6 = st.columns(3)
            col4.metric("Issuer Margin", f"{result['residual_margin_pct']:.2f}%")
            col5.metric("xVA", f"{xva['total_xva_bps']:.1f} bps")
            col6.metric("Protection", f"{result['protection_level_pct']:.0f}%",
                        f"Participation {result['participation_pct']:.0f}%")

        else:
            result = price_yield_enhancement_note(
                sn_spot, sn_strike_ratio, sn_mat, sn_r, sn_q, sn_sigma, notional,
            )
            xva = total_xva("STRUCT_AC", sn_mat, notional, client_type, cds_override or None, funding_spread)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Yield", f"{result['total_yield_pct']:.2f}%",
                        f"{result['annualised_yield_pct']:.2f}% p.a.")
            col2.metric("Put Premium", f"{result['premium_collected_pct']:.3f}%")
            col3.metric("Break-Even", f"{result['break_even_pct_of_spot']:.2f}% of spot")
            col4.metric("Max Loss", f"{result['max_loss_pct']:.2f}%")

            col5, col6 = st.columns(2)
            col5.metric("xVA", f"{xva['total_xva_bps']:.1f} bps")
            col6.metric("Put Delta", f"{result['put_delta']:.4f}")

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

st.markdown("""<style>
[data-testid="stMetricValue"] { font-size: 1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.72rem !important; }
</style>""", unsafe_allow_html=True)

st.title("💹 Pricing Calculator")
st.caption("Indicative pricing · Black / Black-76 / Analytical approximation · PoC level")

# ── Reset counter ──────────────────────────────────────────────────────────────
if "pricing_reset" not in st.session_state:
    st.session_state.pricing_reset = 0

# ── Sidebar global inputs ──────────────────────────────────────────────────────
with st.sidebar:
    st.header("Global Parameters")

    col_r1, col_r2 = st.columns(2)
    with col_r2:
        if st.button("↺ Reset", use_container_width=True):
            st.session_state.pricing_reset += 1
            st.rerun()

    rk = st.session_state.pricing_reset  # reset key

    client_type = st.selectbox("Client Type", CLIENT_TYPES, index=1, key=f"cl_{rk}")
    notional = st.number_input("Notional", value=1_000_000, step=100_000,
                                format="%d", key=f"notional_{rk}")

    st.markdown("---")
    st.markdown("**Market Rates (live or override)**")
    live_rates = {}
    with st.spinner("Fetching rates..."):
        try:
            live_rates = get_current_rates()
        except Exception:
            pass

    r = st.number_input("Risk-Free Rate (%)",
                         value=round(live_rates.get("US10Y", 4.5), 2),
                         step=0.05, format="%.2f", key=f"r_{rk}") / 100
    q = st.number_input("Dividend Yield / Repo (%)", value=1.5, step=0.1,
                         format="%.2f", key=f"q_{rk}") / 100

    st.markdown("---")
    st.markdown("**xVA Parameters**")
    cds_override  = st.number_input("CDS Spread Override (bps, 0=default)", value=0,
                                     step=5, key=f"cds_{rk}")
    funding_spread = st.number_input("Funding Spread (bps)", value=50, step=5,
                                      key=f"fs_{rk}")

_DARK = dict(template="plotly_dark", height=280, margin=dict(t=36, b=20, l=40, r=10))


def _sens_chart(x, y, xlabel, ylabel, title, vline=None, color="#4FC3F7"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines",
                              line=dict(color=color, width=2)))
    if vline is not None:
        fig.add_vline(x=vline, line_dash="dash", line_color="#FFD600")
    fig.update_layout(title=title, xaxis_title=xlabel,
                       yaxis_title=ylabel, **_DARK)
    return fig


# ── Product tabs ───────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📐 Rate Swaption",
    "📊 Bond Futures Option",
    "📈 Equity Vanilla",
    "🌀 Vol Products",
    "🎯 Autocall",
    "🛡️ Structured Note",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: RATE SWAPTION
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Rate Swaption — Black-76")
    c1, c2, c3 = st.columns(3)
    with c1:
        opt_type   = st.radio("Type", ["payer", "receiver"], horizontal=True, key=f"swpn_type_{rk}")
        T_exp      = st.number_input("Option Expiry (Y)", value=1.0, step=0.5, min_value=0.1, key=f"swpn_T_{rk}")
        tenor      = st.number_input("Swap Tenor (Y)", value=10.0, step=1.0, min_value=0.5, key=f"swpn_ten_{rk}")
    with c2:
        fwd_rate_pct = st.number_input("Forward Swap Rate (%)", value=4.30, step=0.05, key=f"swpn_fwd_{rk}")
        fwd_rate   = fwd_rate_pct / 100
        otm_bps    = st.number_input("OTM Shift (bps, 0=ATM)", value=0, step=25, key=f"swpn_otm_{rk}")
        strike     = fwd_rate + otm_bps / 10_000
        st.metric("Strike", f"{strike*100:.3f}%")
    with c3:
        sigma_sw      = st.number_input("Swaption Vol (%)", value=22.0, step=1.0,
                                         min_value=0.1, key=f"swpn_vol_{rk}") / 100
        swpn_notional = st.number_input("Notional ($)", value=notional,
                                         step=1_000_000, format="%d", key=f"swpn_N_{rk}")

    if st.button("Price Swaption", type="primary"):
        result = price_swaption(fwd_rate, strike, T_exp, tenor, sigma_sw,
                                notional=swpn_notional, option_type=opt_type)
        xva = total_xva("RATE_SWPN", T_exp + tenor, swpn_notional, client_type,
                        cds_override or None, funding_spread)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Price", f"{result['price_bps']:.1f} bps",
                    f"${result['price_amount']:,.0f}", delta_color="off")
        col2.metric("DV01 (swap conv.)", f"{result['dv01_bps']:.4f} bps/bp",
                    f"${result['dv01_amount']:,.0f}/bp", delta_color="off")
        col3.metric("Vega", f"{result['vega_bps']:.2f} bps/vol pt",
                    f"${result['vega_amount']:,.0f}/vol pt", delta_color="off")
        col4.metric("Break-Even", f"{result['break_even_bps']:.1f} bps")

        col5, col6, col7 = st.columns(3)
        col5.metric("Theta", f"{result['theta_bps_day']:.3f} bps/day",
                    f"${result['theta_amount_day']:,.0f}/day", delta_color="off")
        col6.metric("xVA (CVA+FVA)", f"{xva['total_xva_bps']:.1f} bps",
                    f"${xva['total_xva_amount']:,.0f}", delta_color="off")
        col7.metric("Net After xVA", f"{result['price_bps'] - xva['total_xva_bps']:.1f} bps")

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

        # ── Sensitivity charts ─────────────────────────────────────────────
        st.markdown("##### Sensitivity Charts")
        rates  = np.linspace(max(fwd_rate * 0.5, 0.005), fwd_rate * 1.8, 40)
        vols   = np.linspace(sigma_sw * 0.4, sigma_sw * 2.0, 40)

        def _sw(F=fwd_rate, K=strike, T=T_exp, ten=tenor, s=sigma_sw, ot=opt_type):
            return price_swaption(F, K, T, ten, s, notional=notional, option_type=ot)

        price_vs_rate  = [_sw(F=f)["price_bps"] for f in rates]
        delta_vs_rate  = [_sw(F=f)["dv01_bps"] for f in rates]
        vega_vs_rate   = [_sw(F=f)["vega_bps"] for f in rates]
        gamma_vs_rate  = [_sw(F=f)["gamma"] for f in rates]
        price_vs_vol   = [_sw(s=v)["price_bps"] for v in vols]
        delta_vs_vol   = [_sw(s=v)["dv01_bps"] for v in vols]
        vega_vs_vol    = [_sw(s=v)["vega_bps"] for v in vols]

        ra = rates * 100  # percent
        va = vols  * 100

        r1c1, r1c2, r1c3 = st.columns(3)
        r1c1.plotly_chart(_sens_chart(ra, price_vs_rate, "Rate (%)", "Price (bps)",
                                       "Price vs Rate", fwd_rate*100), use_container_width=True)
        r1c2.plotly_chart(_sens_chart(ra, delta_vs_rate, "Rate (%)", "DV01 (bps/bp)",
                                       "DV01 vs Rate", fwd_rate*100, "#a78bfa"), use_container_width=True)
        r1c3.plotly_chart(_sens_chart(ra, gamma_vs_rate, "Rate (%)", "Gamma",
                                       "Gamma vs Rate", fwd_rate*100, "#fb923c"), use_container_width=True)

        r2c1, r2c2, r2c3 = st.columns(3)
        r2c1.plotly_chart(_sens_chart(ra, vega_vs_rate, "Rate (%)", "Vega (bps/vol pt)",
                                       "Vega vs Rate", fwd_rate*100, "#34d399"), use_container_width=True)
        r2c2.plotly_chart(_sens_chart(va, delta_vs_vol, "Vol (%)", "DV01 (bps/bp)",
                                       "DV01 vs Vol", sigma_sw*100, "#a78bfa"), use_container_width=True)
        r2c3.plotly_chart(_sens_chart(va, vega_vs_vol, "Vol (%)", "Vega (bps/vol pt)",
                                       "Vega vs Vol", sigma_sw*100, "#34d399"), use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: BOND FUTURES OPTION
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Bond Futures Option — Black-76")
    c1, c2 = st.columns(2)
    with c1:
        bfo_type   = st.radio("Option Type", ["call", "put"], horizontal=True, key=f"bfo_type_{rk}")
        futures_px = st.number_input("Futures Price (% par)", value=110.50, step=0.25, key=f"bfo_F_{rk}")
        strike_bfo = st.number_input("Strike (% par)", value=110.50, step=0.25, key=f"bfo_K_{rk}")
        T_bfo      = st.number_input("Expiry (Y)", value=0.25, step=0.083, min_value=0.02, key=f"bfo_T_{rk}")
    with c2:
        sigma_bfo        = st.number_input("Vol (%)", value=8.0, step=0.5, min_value=0.1,
                                            key=f"bfo_vol_{rk}") / 100
        bfo_contracts    = st.number_input("# Contracts", value=1, step=1, min_value=1,
                                            key=f"bfo_cnt_{rk}")
        bfo_par_notional = st.number_input("Notional per Contract ($)", value=100_000,
                                            step=100_000, format="%d", key=f"bfo_N_{rk}")

    bfo_notional = bfo_contracts * bfo_par_notional

    if st.button("Price Bond Futures Option", type="primary"):
        result = price_bond_futures_option(futures_px, strike_bfo, T_bfo, sigma_bfo,
                                            r=r, notional=bfo_notional, option_type=bfo_type)
        xva = total_xva("RATE_BFO", T_bfo, bfo_notional, client_type,
                        cds_override or None, funding_spread)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Price", f"{result['price_pct']:.4f}% par",
                    f"${result['price_amount']:,.0f}", delta_color="off")
        col2.metric("Delta", f"{result['delta']:.4f}",
                    f"${result['delta'] * bfo_notional / 100:,.0f} equiv.", delta_color="off")
        col3.metric("Vega", f"${result['vega_per_vol_pt']:,.0f}/vol pt")
        col4.metric("DV01", f"${result['dv01_per_bp']:,.0f}/bp")

        col5, col6, col7 = st.columns(3)
        col5.metric("Theta", f"${result['theta_per_day']:,.0f}/day")
        col6.metric("Moneyness", f"{result['moneyness_pct']:+.2f}%")
        col7.metric("xVA", f"{xva['total_xva_bps']:.1f} bps")

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: EQUITY VANILLA STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Equity Vanilla Strategies — Black-Scholes")

    c1, c2 = st.columns([1, 2])
    with c1:
        strategy   = st.selectbox("Strategy", [
            "Call", "Put", "Call Spread", "Put Spread",
            "Straddle", "Strangle", "Risk Reversal", "Covered Call", "Collar",
        ], key=f"eq_strat_{rk}")
        underlying = st.selectbox("Underlying",
                                   ["SPX (^GSPC)", "SX5E (^STOXX50E)", "Custom"],
                                   key=f"eq_ul_{rk}")
        spot_default = 5300.0
        if underlying != "Custom":
            sym = "^GSPC" if "SPX" in underlying else "^STOXX50E"
            with st.spinner("Fetching spot..."):
                fetched = get_current_spot(sym)
                if fetched:
                    spot_default = fetched

        S             = st.number_input("Spot", value=float(round(spot_default)), step=10.0, key=f"eq_S_{rk}")
        T_eq          = st.number_input("Expiry (Y)", value=0.25, step=0.083, min_value=0.01, key=f"eq_T_{rk}")
        sigma_eq      = st.number_input("ATM Vol (%)", value=18.0, step=1.0,
                                         min_value=0.1, key=f"eq_vol_{rk}") / 100
        eq_contracts  = st.number_input("# Contracts", value=1, step=1, min_value=1, key=f"eq_cnt_{rk}")
        eq_multiplier = st.number_input("Contract Multiplier", value=100, step=1, min_value=1, key=f"eq_mult_{rk}")

    with c2:
        if strategy in ("Call", "Put", "Straddle"):
            K = st.number_input("Strike", value=float(round(S)), step=10.0, key=f"eq_K_{rk}")
        elif strategy in ("Call Spread", "Risk Reversal"):
            K_lo = st.number_input("Lower Strike", value=float(round(S)),       step=10.0, key=f"eq_Klo_{rk}")
            K_hi = st.number_input("Upper Strike", value=float(round(S * 1.05)), step=10.0, key=f"eq_Khi_{rk}")
        elif strategy in ("Put Spread", "Collar", "Strangle"):
            K_put  = st.number_input("Put Strike",  value=float(round(S * 0.95)), step=10.0, key=f"eq_Kp_{rk}")
            K_call = st.number_input("Call Strike", value=float(round(S * 1.05)), step=10.0, key=f"eq_Kc_{rk}")
        elif strategy == "Covered Call":
            K = st.number_input("Call Strike", value=float(round(S * 1.03)), step=10.0, key=f"eq_K2_{rk}")

        sigma_skew = st.number_input("OTM Vol Skew (pts per 5% OTM)", value=2.0,
                                      step=0.5, key=f"eq_skew_{rk}") / 100

    def _skew_vol(strike, spot, atm_vol, skew):
        return max(0.01, atm_vol - skew * ((strike - spot) / spot) * 20)

    def _price_eq(S_in, sig_in):
        try:
            if strategy == "Call":
                return call(S_in, K, T_eq, r, sig_in)
            elif strategy == "Put":
                return put(S_in, K, T_eq, r, sig_in)
            elif strategy == "Call Spread":
                return call_spread(S_in, K_lo, K_hi, T_eq, r, sig_in,
                                   _skew_vol(K_hi, S_in, sig_in, sigma_skew))
            elif strategy == "Put Spread":
                return put_spread(S_in, K_put, K_call, T_eq, r, sig_in,
                                  _skew_vol(K_call, S_in, sig_in, sigma_skew))
            elif strategy == "Straddle":
                return straddle(S_in, K, T_eq, r, sig_in)
            elif strategy == "Strangle":
                return strangle(S_in, K_put, K_call, T_eq, r, sig_in,
                                _skew_vol(K_put, S_in, sig_in, sigma_skew))
            elif strategy == "Risk Reversal":
                return risk_reversal(S_in, K_lo, K_hi, T_eq, r, sig_in,
                                     _skew_vol(K_hi, S_in, sig_in, sigma_skew))
            elif strategy == "Covered Call":
                return covered_call(S_in, K, T_eq, r, sig_in)
            elif strategy == "Collar":
                return collar(S_in, K_put, K_call, T_eq, r, sig_in,
                              _skew_vol(K_put, S_in, sig_in, sigma_skew))
        except Exception:
            return None

    if st.button("Price Strategy", type="primary"):
        result = _price_eq(S, sigma_eq)

        if result:
            position_size = eq_contracts * eq_multiplier
            pos_notional  = position_size * S
            xva = total_xva("EQ_VANILLA", T_eq, pos_notional, client_type,
                            cds_override or None, funding_spread)

            prem      = result.get("net_premium", result.get("net_cost",
                        result.get("call_premium_collected", 0)))
            prem_pct  = result.get("net_premium_pct", result.get("net_cost_pct",
                        result.get("premium_pct", 0)))
            net_delta = float(result.get("net_delta", result.get("put_delta", 0)) or 0)
            net_vega  = float(result.get("net_vega", 0) or 0)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Net Premium", f"{prem:.4f}",
                        f"${prem * position_size:,.0f} total", delta_color="off")
            col2.metric("Delta", f"{net_delta:.4f}",
                        f"{net_delta * position_size:.1f} shares equiv.", delta_color="off")
            col3.metric("Vega", f"{net_vega:.4f}",
                        f"${net_vega * position_size:,.0f}/1%vol", delta_color="off")
            col4.metric("Size", f"{eq_contracts}c × {eq_multiplier}x",
                        f"${pos_notional:,.0f} equiv.", delta_color="off")

            if "break_even_up" in result:
                st.info(f"Break-evens: ↑ {result['break_even_up']:.1f}  |  ↓ {result['break_even_down']:.1f}")
            elif "break_even" in result and result["break_even"]:
                st.info(f"Break-even: {result['break_even']:.2f}")

            st.caption("Legs: " + " | ".join(result.get("legs", [])))

            with st.expander("Full Output"):
                st.json({**result, "xva": xva})

            # ── Payoff diagram ─────────────────────────────────────────────
            spot_range = np.linspace(S * 0.7, S * 1.3, 200)
            payoffs = []
            for s in spot_range:
                try:
                    p = _price_eq(s, sigma_eq)
                    p_prem = p.get("net_premium", p.get("net_cost", 0)) if p else 0
                    payoffs.append(float(p_prem) - float(prem))
                except Exception:
                    payoffs.append(0.0)

            payoffs_pos = [y * position_size for y in payoffs]
            fig_payoff = go.Figure()
            fig_payoff.add_trace(go.Scatter(x=list(spot_range), y=payoffs_pos, mode="lines",
                                             fill="tozeroy", line=dict(color="#4FC3F7", width=2),
                                             fillcolor="rgba(79,195,247,0.12)"))
            fig_payoff.add_hline(y=0, line_color="#9E9E9E", line_dash="dash")
            fig_payoff.add_vline(x=S, line_color="#FFD600", line_dash="dot",
                                  annotation_text="Current spot")
            fig_payoff.update_layout(
                title=f"At-Expiry P&L  ({eq_contracts}c × {eq_multiplier}x = {position_size:,} shares)",
                xaxis_title="Spot at Expiry", yaxis_title="P&L ($)", **_DARK)
            st.plotly_chart(fig_payoff, use_container_width=True)

            # ── Sensitivity charts ─────────────────────────────────────────
            st.markdown("##### Sensitivity Charts")
            spots = np.linspace(S * 0.7, S * 1.3, 50)
            vols_eq = np.linspace(max(sigma_eq * 0.4, 0.02), sigma_eq * 2.2, 40)
            eps = S * 0.001  # for numerical greeks

            def _prem(res):
                return float(res.get("net_premium", res.get("net_cost",
                             res.get("call_premium_collected", 0)))) if res else 0.0

            prem_vs_spot = [_prem(_price_eq(s, sigma_eq)) * position_size for s in spots]
            prem_vs_vol  = [_prem(_price_eq(S, v))        * position_size for v in vols_eq]

            # numerical delta and gamma vs spot (position-scaled)
            delta_vs_spot, gamma_vs_spot, vega_vs_spot = [], [], []
            for s in spots:
                p0  = _prem(_price_eq(s, sigma_eq))
                pp  = _prem(_price_eq(s + eps, sigma_eq))
                pm  = _prem(_price_eq(s - eps, sigma_eq))
                pv  = _prem(_price_eq(s, min(sigma_eq + 0.01, 4.0)))
                delta_vs_spot.append((pp - pm) / (2 * eps)       * position_size)
                gamma_vs_spot.append((pp - 2*p0 + pm) / eps**2   * position_size)
                vega_vs_spot.append((pv - p0) / 0.01             * position_size)

            rc1, rc2, rc3 = st.columns(3)
            rc1.plotly_chart(_sens_chart(spots, prem_vs_spot, "Spot", "Premium ($)",
                                          "Premium vs Spot", S), use_container_width=True)
            rc2.plotly_chart(_sens_chart(vols_eq*100, prem_vs_vol, "Vol (%)", "Premium ($)",
                                          "Premium vs Vol", sigma_eq*100), use_container_width=True)
            rc3.plotly_chart(_sens_chart(spots, delta_vs_spot, "Spot", "Delta (shares)",
                                          "Delta vs Spot", S, "#a78bfa"), use_container_width=True)

            rc4, rc5, _ = st.columns(3)
            rc4.plotly_chart(_sens_chart(spots, vega_vs_spot, "Spot", "Vega ($/1%vol)",
                                          "Vega vs Spot", S, "#34d399"), use_container_width=True)
            rc5.plotly_chart(_sens_chart(spots, gamma_vs_spot, "Spot", "Gamma ($/pt²)",
                                          "Gamma vs Spot", S, "#fb923c"), use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: VOL PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Vol Products — Var/Vol Swap & VIX Roll")
    prod_choice = st.radio("Product", ["Variance Swap", "Vol Swap", "VIX Roll-Down"],
                            horizontal=True, key=f"vp_{rk}")

    if prod_choice == "Variance Swap":
        c1, c2 = st.columns(2)
        with c1:
            atm_vol_vs   = st.number_input("ATM Implied Vol (%)", value=18.0, step=0.5, key=f"vs_atm_{rk}") / 100
            rv_input     = st.number_input("Realized Vol to Date (%, 0=forward start)",
                                            value=0.0, step=0.5, key=f"vs_rv_{rk}") / 100
            mat_vs       = st.number_input("Maturity (Y)", value=0.5, step=0.083,
                                            min_value=0.01, key=f"vs_mat_{rk}")
            pos_vs       = st.radio("Position", ["short", "long"], horizontal=True, key=f"vs_pos_{rk}")
        with c2:
            skew_vs      = st.number_input("Skew Slope", value=-0.10, step=0.01, key=f"vs_skew_{rk}")
            vega_notional = st.number_input("Vega Notional ($)", value=100_000, step=10_000, key=f"vs_vn_{rk}")

        if st.button("Price Var Swap", type="primary"):
            rv = rv_input if rv_input > 0 else None
            result = price_var_swap(atm_vol_vs, rv, mat_vs, vega_notional, skew_vs, pos_vs)
            xva    = total_xva("VOL_PROD", mat_vs, notional, client_type,
                               cds_override or None, funding_spread)

            c1, c2, c3 = st.columns(3)
            c1.metric("Fair Var Strike (as vol)", f"{result['fair_var_strike_pct']:.2f}%")
            c2.metric("Fair Vol Strike",          f"{result['fair_vol_strike_pct']:.2f}%")
            c3.metric("Break-even RV",            f"{result['break_even_rv_pct']:.2f}%")
            if "pnl" in result:
                st.metric("MtM P&L", f"${result['pnl']:,.0f}")
            st.caption(f"Var Notional: ${result['var_notional']:,.0f}  |  xVA: {xva['total_xva_bps']:.1f} bps")
            with st.expander("Full Output"):
                st.json({**result, "xva": xva})

    elif prod_choice == "Vol Swap":
        atm_vol_vlsw = st.number_input("ATM Vol (%)", value=18.0, step=0.5, key=f"vlsw_atm_{rk}") / 100
        mat_vlsw     = st.number_input("Maturity (Y)", value=0.5, step=0.083, key=f"vlsw_mat_{rk}")
        pos_vlsw     = st.radio("Position", ["short", "long"], horizontal=True, key=f"vlsw_pos_{rk}")

        if st.button("Price Vol Swap", type="primary"):
            result = price_vol_swap(atm_vol_vlsw, mat_vlsw, notional, pos_vlsw)
            c1, c2 = st.columns(2)
            c1.metric("Fair Vol Strike",      f"{result['fair_vol_strike_pct']:.2f}%")
            c2.metric("Convexity Correction", f"{result['convexity_correction_bps']:.1f} bps")
            st.caption(f"Var vs Vol premium: {result['var_vs_vol_premium_bps']:.1f} bps")

    elif prod_choice == "VIX Roll-Down":
        with st.spinner("Fetching VIX..."):
            vix_ts = get_vix_term_structure()
        vix_spot_def = vix_ts.get("VIX") or 20.0
        vix3m_def    = vix_ts.get("VIX3M") or 23.0

        c1, c2 = st.columns(2)
        with c1:
            vix_spot_in = st.number_input("VIX Spot", value=float(vix_spot_def), step=0.5, key=f"vix_s_{rk}")
            vix3m_in    = st.number_input("VIX 3M",   value=float(vix3m_def),    step=0.5, key=f"vix_3m_{rk}")
        with c2:
            roll_days = st.number_input("Rolling Horizon (days)", value=30, step=5, key=f"vix_rd_{rk}")

        if st.button("Compute Roll-Down", type="primary"):
            result = vix_roll_down(vix_spot_in, vix3m_in, roll_days)
            c1, c2, c3 = st.columns(3)
            c1.metric("Contango",          f"{result.get('contango_pct', 0):+.2f}%")
            c2.metric(f"Roll ({roll_days}d)", f"{result.get('roll_carry_per_month', 0):.2f} vol pts")
            c3.metric("Ann. Carry",        f"{result.get('annualised_carry_pct', 0):.2f}%/vix")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: AUTOCALL
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Autocall — Analytical Approximation (Single-Factor Gaussian)")
    st.caption("Indicative only. Path-dependent features approximated via survival probability decomposition.")

    c1, c2, c3 = st.columns(3)
    with c1:
        ac_sigma   = st.number_input("Underlying Vol (%)", value=20.0, step=1.0,
                                      min_value=1.0, key=f"ac_vol_{rk}") / 100
        ac_r       = st.number_input("Risk-Free Rate (%)", value=round(r * 100, 2),
                                      step=0.05, key=f"ac_r_{rk}") / 100
        ac_q       = st.number_input("Div Yield (%)", value=round(q * 100, 2),
                                      step=0.1, key=f"ac_q_{rk}") / 100
    with c2:
        ac_barrier = st.slider("Autocall Barrier (% initial)", 80, 120, 100, key=f"ac_bar_{rk}") / 100
        ac_ki      = st.slider("Knock-In Barrier (% initial)", 40, 85, 60, key=f"ac_ki_{rk}") / 100
        ac_coupon  = st.number_input("Annual Coupon (%)", value=8.0, step=0.5,
                                      min_value=0.0, key=f"ac_cpn_{rk}") / 100
    with c3:
        ac_maturity = st.selectbox("Maturity", [1, 2, 3, 5], index=2, key=f"ac_mat_{rk}")
        ac_obs      = st.selectbox("Observation", [4, 12, 1], index=0,
                                    format_func=lambda x: {4: "Quarterly", 12: "Monthly", 1: "Annual"}[x],
                                    key=f"ac_obs_{rk}")
        ac_notional = st.number_input("Notional ($)", value=notional,
                                       step=1_000_000, format="%d", key=f"ac_N_{rk}")

    def _price_ac(spot=100, vol=None, barrier=None):
        # spot is % of initial (100 = at initial level).
        # price_autocall works in normalised space (S0=1) so we must rescale
        # the absolute barriers to be relative to current spot.
        b = barrier if barrier is not None else ac_barrier
        barrier_rel = b * 100.0 / spot
        ki_rel      = ac_ki * 100.0 / spot
        return price_autocall(
            spot=spot,
            barrier_pct=barrier_rel,
            coupon_barrier_pct=barrier_rel,
            ki_barrier_pct=ki_rel,
            coupon_pa=ac_coupon,
            maturity_years=ac_maturity,
            obs_per_year=ac_obs,
            sigma=vol if vol is not None else ac_sigma,
            r=ac_r, q=ac_q, notional=ac_notional,
        )

    if st.button("Price Autocall", type="primary"):
        result = _price_ac()
        xva    = total_xva("STRUCT_AC", ac_maturity, ac_notional, client_type,
                           cds_override or None, funding_spread)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Indicative Price",   f"{result['indicative_price_pct']:.2f}% par",
                    f"${result['indicative_price_amount']:,.0f}", delta_color="off")
        col2.metric("Fair Coupon",        f"{result['fair_coupon_pa_pct']:.2f}% p.a.")
        col3.metric("P(Survive to Mat.)", f"{result['prob_survive_to_maturity_pct']:.1f}%")
        col4.metric("P(KI Breach)",       f"{result['prob_ki_breach_pct']:.2f}%")

        col5, col6, col7 = st.columns(3)
        col5.metric("Coupon PV",           f"${result['coupon_pv']:,.0f}")
        col6.metric("Autocall Redemption", f"${result['autocall_redemption_pv']:,.0f}")
        col7.metric("xVA (CVA+FVA)",       f"{xva['total_xva_bps']:.1f} bps")

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

        # ── Sensitivity charts ─────────────────────────────────────────────
        st.markdown("##### Sensitivity Charts")

        spots_ac = np.linspace(70, 130, 40)   # % of initial (autocall uses spot=100 base)
        vols_ac  = np.linspace(0.08, 0.55, 40)
        eps_s    = 1.0  # 1% spot move

        prices_vs_spot, prices_vs_vol = [], []
        deltas_vs_spot, gammas_vs_spot, vegas_vs_spot = [], [], []

        for s in spots_ac:
            p0  = _price_ac(spot=s)["indicative_price_pct"]
            pp  = _price_ac(spot=s + eps_s)["indicative_price_pct"]
            pm  = _price_ac(spot=s - eps_s)["indicative_price_pct"]
            pv  = _price_ac(spot=s, vol=min(ac_sigma + 0.01, 0.99))["indicative_price_pct"]
            prices_vs_spot.append(p0)
            deltas_vs_spot.append((pp - pm) / (2 * eps_s))
            gammas_vs_spot.append((pp - 2*p0 + pm) / (eps_s**2))
            vegas_vs_spot.append((pv - p0) / 0.01)

        for v in vols_ac:
            prices_vs_vol.append(_price_ac(vol=v)["indicative_price_pct"])

        ac1, ac2 = st.columns(2)
        ac1.plotly_chart(_sens_chart(spots_ac, prices_vs_spot, "Spot (% initial)", "Price (% par)",
                                      "Price vs Spot", 100), use_container_width=True)
        ac2.plotly_chart(_sens_chart(vols_ac*100, prices_vs_vol, "Vol (%)", "Price (% par)",
                                      "Price vs Vol", ac_sigma*100), use_container_width=True)

        ac3, ac4, ac5 = st.columns(3)
        ac3.plotly_chart(_sens_chart(spots_ac, deltas_vs_spot, "Spot (% initial)",
                                      "Δ Price / Δ Spot", "Delta vs Spot", 100, "#a78bfa"),
                          use_container_width=True)
        ac4.plotly_chart(_sens_chart(spots_ac, gammas_vs_spot, "Spot (% initial)",
                                      "Δ² Price / Δ Spot²", "Gamma vs Spot", 100, "#fb923c"),
                          use_container_width=True)
        ac5.plotly_chart(_sens_chart(spots_ac, vegas_vs_spot, "Spot (% initial)",
                                      "Δ Price / Δ1%vol", "Vega vs Spot", 100, "#34d399"),
                          use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6: STRUCTURED NOTES
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Structured Notes — Capital Protection & Yield Enhancement")
    st.caption("""
    **Capital Protection Note (CPN):** Investor buys a zero-coupon bond (guaranteeing principal return)
    + a call option on the underlying. The issuer margin = 100% − ZC bond cost − call cost.
    Price = ZC bond + participation × call; risk = convexity/vega on the embedded call.

    **Yield Enhancement / Reverse Convertible:** Investor sells a put on the underlying and
    collects the premium as enhanced yield. If the underlying falls below the put strike,
    they receive shares instead of cash at maturity. Risk = short put delta + vega.
    """)

    note_type = st.radio("Note Type",
                          ["Capital Protection Note", "Yield Enhancement (Reverse Convertible)"],
                          horizontal=True, key=f"sn_type_{rk}")

    c1, c2 = st.columns(2)
    with c1:
        sn_spot     = st.number_input("Spot / Reference Level", value=100.0, step=1.0, key=f"sn_spot_{rk}")
        sn_mat      = st.number_input("Maturity (Y)", value=3.0, step=0.5, min_value=0.5, key=f"sn_mat_{rk}")
        sn_sigma    = st.number_input("Vol (%)", value=18.0, step=1.0, key=f"sn_sig_{rk}") / 100
        sn_r        = st.number_input("Risk-Free Rate (%)", value=round(r * 100, 2),
                                       step=0.05, key=f"sn_r_{rk}") / 100
        sn_q        = st.number_input("Div Yield (%)", value=round(q * 100, 2),
                                       step=0.1, key=f"sn_q_{rk}") / 100
        sn_notional = st.number_input("Notional ($)", value=notional,
                                       step=1_000_000, format="%d", key=f"sn_N_{rk}")
    with c2:
        if note_type == "Capital Protection Note":
            protection    = st.slider("Protection Level (%)", 80, 100, 100, key=f"sn_prot_{rk}") / 100
            participation = st.slider("Participation Rate (%)", 50, 200, 100, key=f"sn_part_{rk}") / 100
            strike_ratio  = st.slider("Call Strike (% of initial)", 90, 120, 100, key=f"sn_str_{rk}") / 100
        else:
            sn_strike_ratio = st.slider("Put Strike (% of spot)", 70, 105, 95, key=f"sn_put_{rk}") / 100

    if st.button("Price Note", type="primary"):
        if note_type == "Capital Protection Note":
            result = price_capital_protection_note(
                sn_spot, strike_ratio, participation, sn_mat,
                sn_r, sn_q, sn_sigma, protection, sn_notional,
            )
            xva = total_xva("STRUCT_AC", sn_mat, sn_notional, client_type,
                            cds_override or None, funding_spread)

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Cost", f"{result['total_cost_pct']:.2f}%",
                        f"${result['total_cost_pct'] / 100 * sn_notional:,.0f}  "
                        + ("✅ Feasible" if result["feasible"] else "❌ Over par"),
                        delta_color="off")
            col2.metric("ZC Bond Cost",    f"{result['zc_bond_cost_pct']:.2f}%",
                        f"${result['zc_bond_cost_pct'] / 100 * sn_notional:,.0f}", delta_color="off")
            col3.metric("Call Option Cost", f"{result['call_cost_pct']:.2f}%",
                        f"${result['call_cost_pct'] / 100 * sn_notional:,.0f}", delta_color="off")

            col4, col5, col6 = st.columns(3)
            col4.metric("Issuer Margin",  f"{result['residual_margin_pct']:.2f}%",
                        f"${result['residual_margin_pct'] / 100 * sn_notional:,.0f}", delta_color="off")
            col5.metric("xVA",            f"{xva['total_xva_bps']:.1f} bps")
            col6.metric("Protection",     f"{result['protection_level_pct']:.0f}%",
                        f"Participation {result['participation_pct']:.0f}%",
                        delta_color="off")

        else:
            result = price_yield_enhancement_note(
                sn_spot, sn_strike_ratio, sn_mat, sn_r, sn_q, sn_sigma, sn_notional,
            )
            xva = total_xva("STRUCT_AC", sn_mat, sn_notional, client_type,
                            cds_override or None, funding_spread)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Yield",  f"{result['total_yield_pct']:.2f}%",
                        f"${result['total_yield_pct'] / 100 * sn_notional:,.0f}  "
                        f"({result['annualised_yield_pct']:.2f}% p.a.)", delta_color="off")
            col2.metric("Put Premium",  f"{result['premium_collected_pct']:.3f}%",
                        f"${result['premium_collected_pct'] / 100 * sn_notional:,.0f}", delta_color="off")
            col3.metric("Break-Even",   f"{result['break_even_pct_of_spot']:.2f}% of spot")
            col4.metric("Max Loss",     f"{result['max_loss_pct']:.2f}%",
                        f"${result['max_loss_pct'] / 100 * sn_notional:,.0f}", delta_color="off")

            col5, col6 = st.columns(2)
            col5.metric("xVA",      f"{xva['total_xva_bps']:.1f} bps")
            col6.metric("Put Delta", f"{result['put_delta']:.4f}")

        with st.expander("Full Output"):
            st.json({**result, "xva": xva})

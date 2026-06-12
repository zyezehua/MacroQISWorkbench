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
from utils.tearsheet import build_excel, build_pdf
from ui.style import inject_global_css

st.set_page_config(page_title="Pricing · Macro QIS", page_icon="💹", layout="wide")
inject_global_css()

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


_TENOR_UNITS = ["Days", "Weeks", "Months", "Years"]
_TENOR_TO_YR = {"Days": 1/365, "Weeks": 7/365, "Months": 1/12, "Years": 1.0}


def _tenor_input(label, default_years, key, min_years=0.1):
    """Render a (value, unit) pair and return duration in years."""
    def_unit = "Months" if default_years < 1.0 else "Years"
    def_val  = float(round(default_years * 12)) if default_years < 1.0 else float(default_years)
    vc, uc = st.columns([2, 1])
    unit = uc.selectbox("", _TENOR_UNITS, index=_TENOR_UNITS.index(def_unit),
                         key=f"{key}_unit", label_visibility="collapsed")
    fmt  = "%.0f" if unit in ("Days", "Weeks", "Months") else "%.2f"
    step = 1.0    if unit in ("Days", "Weeks", "Months") else 0.5
    minv = 1.0    if unit in ("Days", "Weeks", "Months") else min_years
    val  = vc.number_input(label, value=def_val, step=step, min_value=minv,
                            key=f"{key}_val", format=fmt)
    return float(val) * _TENOR_TO_YR[unit]


def _dl_buttons(pname: str, inputs: dict, result: dict, xva: dict):
    """Render the Excel + PDF download buttons for a pricing run."""
    safe = pname.replace(" ", "_").replace("/", "-").replace("×", "x")
    dc1, dc2, _ = st.columns([1, 1, 5])
    dc1.download_button(
        "⬇ Excel", build_excel(pname, inputs, result, xva),
        file_name=f"tearsheet_{safe}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    dc2.download_button(
        "⬇ PDF", build_pdf(pname, inputs, result, xva),
        file_name=f"tearsheet_{safe}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )


# ── Scenario library ───────────────────────────────────────────────────────────
_SCENARIOS = {
    "Baseline (Live)": None,
    "GFC 2008 (Oct–Dec)": {
        "desc": "VIX 80  ·  US10Y 2.5%  ·  EQ vol 70%  ·  Near-zero Fed funds",
        "r": 0.50, "q": 1.50,
        "swpn_fwd": 2.50, "swpn_vol": 60.0,
        "bfo_vol": 15.0,
        "eq_vol": 70.0,
        "vs_atm": 70.0, "vlsw_atm": 70.0,
        "vix": 80.0, "vix3m": 72.0,
        "ac_r": 0.50, "ac_q": 1.50, "ac_vol": 65.0,
        "sn_r": 0.50, "sn_q": 1.50, "sn_vol": 65.0,
    },
    "COVID Mar 2020": {
        "desc": "VIX 85  ·  US10Y 0.8%  ·  EQ vol 75%  ·  Emergency rate cuts",
        "r": 0.10, "q": 1.50,
        "swpn_fwd": 0.80, "swpn_vol": 45.0,
        "bfo_vol": 18.0,
        "eq_vol": 75.0,
        "vs_atm": 75.0, "vlsw_atm": 75.0,
        "vix": 85.0, "vix3m": 75.0,
        "ac_r": 0.10, "ac_q": 1.50, "ac_vol": 70.0,
        "sn_r": 0.10, "sn_q": 1.50, "sn_vol": 70.0,
    },
    "Rate Spike 2022": {
        "desc": "VIX 35  ·  US10Y 4.2%  ·  Swaption vol 130bpn  ·  Fastest hike cycle",
        "r": 4.00, "q": 1.20,
        "swpn_fwd": 4.20, "swpn_vol": 130.0,
        "bfo_vol": 12.0,
        "eq_vol": 30.0,
        "vs_atm": 30.0, "vlsw_atm": 30.0,
        "vix": 35.0, "vix3m": 32.0,
        "ac_r": 4.00, "ac_q": 1.20, "ac_vol": 28.0,
        "sn_r": 4.00, "sn_q": 1.20, "sn_vol": 28.0,
    },
    "Deep Inversion 2023": {
        "desc": "VIX 17  ·  US10Y 5.0%  ·  2s10s −100 bps  ·  Soft-landing narrative",
        "r": 5.25, "q": 1.50,
        "swpn_fwd": 5.00, "swpn_vol": 80.0,
        "bfo_vol": 8.0,
        "eq_vol": 17.0,
        "vs_atm": 17.0, "vlsw_atm": 17.0,
        "vix": 17.0, "vix3m": 19.0,
        "ac_r": 5.25, "ac_q": 1.50, "ac_vol": 16.0,
        "sn_r": 5.25, "sn_q": 1.50, "sn_vol": 16.0,
    },
}

# Maps scenario dict keys → widget key templates (values are in % where widgets expect %)
_SC_KEY_MAP = {
    "r":        "r_{rk}",
    "q":        "q_{rk}",
    "swpn_fwd": "swpn_fwd_{rk}",
    "swpn_vol": "swpn_vol_{rk}",
    "bfo_vol":  "bfo_vol_{rk}",
    "eq_vol":   "eq_vol_{rk}",
    "vs_atm":   "vs_atm_{rk}",
    "vlsw_atm": "vlsw_atm_{rk}",
    "vix":      "vix_s_{rk}",
    "vix3m":    "vix_3m_{rk}",
    "ac_r":     "ac_r_{rk}",
    "ac_q":     "ac_q_{rk}",
    "ac_vol":   "ac_vol_{rk}",
    "sn_r":     "sn_r_{rk}",
    "sn_q":     "sn_q_{rk}",
    "sn_vol":   "sn_sig_{rk}",
}

# ── Scenario selector banner ───────────────────────────────────────────────────
_sc_c1, _sc_c2, _sc_c3 = st.columns([3, 1, 5])
with _sc_c1:
    sc_choice = st.selectbox(
        "Stress Scenario", list(_SCENARIOS.keys()),
        key="scenario_select",
        label_visibility="collapsed",
        help="Pre-fill all pricing inputs with a historical stress scenario",
    )
with _sc_c2:
    sc_apply = st.button("⚡ Apply", use_container_width=True,
                          help="Inject scenario parameters into all pricing tabs")

active_sc = st.session_state.get("active_scenario")
if active_sc and active_sc != "Baseline (Live)":
    sc_desc = (_SCENARIOS.get(active_sc) or {}).get("desc", "")
    _sc_c3.info(f"⚡ **{active_sc}** — {sc_desc}")

if sc_apply:
    sc_data = _SCENARIOS.get(sc_choice)
    new_rk = st.session_state.pricing_reset + 1
    if sc_data:
        for sc_key, tpl in _SC_KEY_MAP.items():
            if sc_key in sc_data:
                st.session_state[tpl.format(rk=new_rk)] = sc_data[sc_key]
        st.session_state["active_scenario"] = sc_choice
    else:
        st.session_state["active_scenario"] = None
    st.session_state.pricing_reset = new_rk
    st.rerun()

st.markdown("---")

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
        T_exp      = _tenor_input("Option Expiry", 1.0, f"swpn_T_{rk}")
        tenor      = _tenor_input("Swap Tenor", 10.0, f"swpn_ten_{rk}", min_years=0.5)
    with c2:
        fwd_rate_pct = st.number_input("Forward Swap Rate (%)", value=4.30, step=0.05, key=f"swpn_fwd_{rk}")
        fwd_rate   = fwd_rate_pct / 100
        otm_bps    = st.number_input("OTM Shift (bps, 0=ATM)", value=0, step=25, key=f"swpn_otm_{rk}")
        strike     = fwd_rate + otm_bps / 10_000
        st.metric("Strike", f"{strike*100:.3f}%")
    with c3:
        sigma_sw      = st.number_input("Swaption Vol (%)", value=22.0, step=1.0,
                                         min_value=0.1, key=f"swpn_vol_{rk}") / 100
        swpn_notional = st.number_input("Notional ($)", value=1_000_000,
                                         step=1_000_000, format="%d", key=f"swpn_N_{rk}")

    if st.button("Price Swaption", type="primary"):
        _res = price_swaption(fwd_rate, strike, T_exp, tenor, sigma_sw,
                              notional=swpn_notional, option_type=opt_type)
        _xva = total_xva("RATE_SWPN", T_exp + tenor, swpn_notional, client_type,
                         cds_override or None, funding_spread)

        # sensitivity data (compute at price-time, store for persistent display)
        _rates = np.linspace(max(fwd_rate * 0.5, 0.005), fwd_rate * 1.8, 40)
        _vols  = np.linspace(sigma_sw * 0.4, sigma_sw * 2.0, 40)
        def _sw(F=fwd_rate, K=strike, T=T_exp, ten=tenor, s=sigma_sw, ot=opt_type):
            return price_swaption(F, K, T, ten, s, notional=swpn_notional, option_type=ot)
        _sens = dict(
            ra=_rates * 100, va=_vols * 100,
            p_rate=[_sw(F=f)["price_bps"] for f in _rates],
            d_rate=[_sw(F=f)["dv01_bps"]  for f in _rates],
            g_rate=[_sw(F=f)["gamma"]      for f in _rates],
            v_rate=[_sw(F=f)["vega_bps"]   for f in _rates],
            d_vol= [_sw(s=v)["dv01_bps"]  for v in _vols],
            v_vol= [_sw(s=v)["vega_bps"]  for v in _vols],
            fwd_pct=fwd_rate * 100, vol_pct=sigma_sw * 100,
        )
        st.session_state.update({
            "_sw_r": _res, "_sw_x": _xva, "_sw_s": _sens, "_sw_rk": rk,
            "_sw_i": {
                "Option Type": opt_type.capitalize(),
                "Forward Rate": f"{fwd_rate*100:.3f}%",
                "Strike": f"{strike*100:.3f}%",
                "OTM Shift": f"{otm_bps} bps",
                "Expiry": f"{T_exp:.2f}Y",
                "Swap Tenor": f"{tenor:.2f}Y",
                "Vol": f"{sigma_sw*100:.1f}%",
                "Notional": f"${swpn_notional:,.0f}",
                "Client Type": client_type,
            },
            "_sw_n": f"Rate Swaption — {opt_type.capitalize()} {T_exp:.1f}Y×{tenor:.0f}Y",
        })

    if st.session_state.get("_sw_rk") == rk:
        result = st.session_state["_sw_r"]
        xva    = st.session_state["_sw_x"]
        sens   = st.session_state["_sw_s"]

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

        st.markdown("##### Sensitivity Charts")
        r1c1, r1c2, r1c3 = st.columns(3)
        r1c1.plotly_chart(_sens_chart(sens["ra"], sens["p_rate"], "Rate (%)", "Price (bps)",
                                       "Price vs Rate", sens["fwd_pct"]), use_container_width=True)
        r1c2.plotly_chart(_sens_chart(sens["ra"], sens["d_rate"], "Rate (%)", "DV01 (bps/bp)",
                                       "DV01 vs Rate", sens["fwd_pct"], "#a78bfa"), use_container_width=True)
        r1c3.plotly_chart(_sens_chart(sens["ra"], sens["g_rate"], "Rate (%)", "Gamma",
                                       "Gamma vs Rate", sens["fwd_pct"], "#fb923c"), use_container_width=True)

        r2c1, r2c2, r2c3 = st.columns(3)
        r2c1.plotly_chart(_sens_chart(sens["ra"], sens["v_rate"], "Rate (%)", "Vega (bps/vol pt)",
                                       "Vega vs Rate", sens["fwd_pct"], "#34d399"), use_container_width=True)
        r2c2.plotly_chart(_sens_chart(sens["va"], sens["d_vol"], "Vol (%)", "DV01 (bps/bp)",
                                       "DV01 vs Vol", sens["vol_pct"], "#a78bfa"), use_container_width=True)
        r2c3.plotly_chart(_sens_chart(sens["va"], sens["v_vol"], "Vol (%)", "Vega (bps/vol pt)",
                                       "Vega vs Vol", sens["vol_pct"], "#34d399"), use_container_width=True)

        _dl_buttons(st.session_state["_sw_n"],
                    st.session_state["_sw_i"], result, xva)

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
        T_bfo      = _tenor_input("Expiry", 0.25, f"bfo_T_{rk}")
    with c2:
        sigma_bfo        = st.number_input("Vol (%)", value=8.0, step=0.5, min_value=0.1,
                                            key=f"bfo_vol_{rk}") / 100
        bfo_contracts    = st.number_input("# Contracts", value=1, step=1, min_value=1,
                                            key=f"bfo_cnt_{rk}")
        bfo_par_notional = st.number_input("Notional per Contract ($)", value=100_000,
                                            step=100_000, format="%d", key=f"bfo_N_{rk}")

    bfo_notional = bfo_contracts * bfo_par_notional

    if st.button("Price Bond Futures Option", type="primary"):
        _res = price_bond_futures_option(futures_px, strike_bfo, T_bfo, sigma_bfo,
                                          r=r, notional=bfo_notional, option_type=bfo_type)
        _xva = total_xva("RATE_BFO", T_bfo, bfo_notional, client_type,
                         cds_override or None, funding_spread)
        st.session_state.update({
            "_bfo_r": _res, "_bfo_x": _xva, "_bfo_rk": rk,
            "_bfo_i": {
                "Option Type": bfo_type.capitalize(),
                "Futures Price": f"{futures_px:.2f}% par",
                "Strike": f"{strike_bfo:.2f}% par",
                "Expiry": f"{T_bfo:.2f}Y",
                "Vol": f"{sigma_bfo*100:.1f}%",
                "# Contracts": str(bfo_contracts),
                "Notional / Contract": f"${bfo_par_notional:,.0f}",
                "Total Notional": f"${bfo_notional:,.0f}",
                "Client Type": client_type,
            },
            "_bfo_n": f"Bond Futures {bfo_type.capitalize()} {T_bfo:.2f}Y",
        })

    if st.session_state.get("_bfo_rk") == rk:
        result = st.session_state["_bfo_r"]
        xva    = st.session_state["_bfo_x"]

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

        _dl_buttons(st.session_state["_bfo_n"],
                    st.session_state["_bfo_i"], result, xva)

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
        T_eq          = _tenor_input("Expiry", 0.25, f"eq_T_{rk}")
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
        _res = _price_eq(S, sigma_eq)
        if _res:
            position_size = eq_contracts * eq_multiplier
            pos_notional  = position_size * S
            _xva = total_xva("EQ_VANILLA", T_eq, pos_notional, client_type,
                             cds_override or None, funding_spread)
            prem = _res.get("net_premium", _res.get("net_cost",
                   _res.get("call_premium_collected", 0)))

            # payoff diagram data
            spot_range = np.linspace(S * 0.7, S * 1.3, 200)
            payoffs_pos = []
            for s in spot_range:
                try:
                    p = _price_eq(s, sigma_eq)
                    p_prem = p.get("net_premium", p.get("net_cost", 0)) if p else 0
                    payoffs_pos.append((float(p_prem) - float(prem)) * position_size)
                except Exception:
                    payoffs_pos.append(0.0)

            # sensitivity data
            spots_s = np.linspace(S * 0.7, S * 1.3, 50)
            vols_s  = np.linspace(max(sigma_eq * 0.4, 0.02), sigma_eq * 2.2, 40)
            eps = S * 0.001

            def _prem(res):
                return float(res.get("net_premium", res.get("net_cost",
                             res.get("call_premium_collected", 0)))) if res else 0.0

            prem_vs_spot, prem_vs_vol = [], []
            delta_vs_spot, gamma_vs_spot, vega_vs_spot = [], [], []
            for s in spots_s:
                p0 = _prem(_price_eq(s, sigma_eq))
                pp = _prem(_price_eq(s + eps, sigma_eq))
                pm = _prem(_price_eq(s - eps, sigma_eq))
                pv = _prem(_price_eq(s, min(sigma_eq + 0.01, 4.0)))
                prem_vs_spot.append(p0 * position_size)
                delta_vs_spot.append((pp - pm) / (2 * eps)       * position_size)
                gamma_vs_spot.append((pp - 2*p0 + pm) / eps**2   * position_size)
                vega_vs_spot.append((pv - p0) / 0.01             * position_size)
            for v in vols_s:
                prem_vs_vol.append(_prem(_price_eq(S, v)) * position_size)

            # build strike info for inputs dict
            if strategy in ("Call", "Put", "Straddle", "Covered Call"):
                k_str = f"K={K:.0f}"
            elif strategy in ("Call Spread", "Risk Reversal"):
                k_str = f"K_lo={K_lo:.0f} / K_hi={K_hi:.0f}"
            else:
                k_str = f"K_put={K_put:.0f} / K_call={K_call:.0f}"

            st.session_state.update({
                "_eq_r": _res, "_eq_x": _xva, "_eq_rk": rk,
                "_eq_ps": position_size, "_eq_pn": pos_notional,
                "_eq_prem": prem, "_eq_S": S, "_eq_sig": sigma_eq,
                "_eq_payoff_x": list(spot_range), "_eq_payoff_y": payoffs_pos,
                "_eq_sens": dict(
                    spots=spots_s, vols=vols_s,
                    prem_vs_spot=prem_vs_spot, prem_vs_vol=prem_vs_vol,
                    delta_vs_spot=delta_vs_spot, gamma_vs_spot=gamma_vs_spot,
                    vega_vs_spot=vega_vs_spot,
                ),
                "_eq_i": {
                    "Strategy": strategy,
                    "Underlying": underlying,
                    "Spot": f"{S:.1f}",
                    "Strikes": k_str,
                    "Expiry": f"{T_eq:.2f}Y",
                    "ATM Vol": f"{sigma_eq*100:.1f}%",
                    "OTM Skew": f"{sigma_skew*100:.1f} pts/5%OTM",
                    "# Contracts": str(eq_contracts),
                    "Multiplier": str(eq_multiplier),
                    "Client Type": client_type,
                },
                "_eq_n": f"EQ {strategy} {underlying.split()[0]} {T_eq:.2f}Y",
            })

    if st.session_state.get("_eq_rk") == rk:
        result = st.session_state["_eq_r"]
        xva    = st.session_state["_eq_x"]
        position_size = st.session_state["_eq_ps"]
        pos_notional  = st.session_state["_eq_pn"]
        prem          = st.session_state["_eq_prem"]
        sens          = st.session_state["_eq_sens"]

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

        # payoff diagram
        fig_payoff = go.Figure()
        fig_payoff.add_trace(go.Scatter(
            x=st.session_state["_eq_payoff_x"], y=st.session_state["_eq_payoff_y"],
            mode="lines", fill="tozeroy",
            line=dict(color="#4FC3F7", width=2), fillcolor="rgba(79,195,247,0.12)"))
        fig_payoff.add_hline(y=0, line_color="#9E9E9E", line_dash="dash")
        fig_payoff.add_vline(x=st.session_state["_eq_S"], line_color="#FFD600",
                              line_dash="dot", annotation_text="Current spot")
        fig_payoff.update_layout(
            title=f"At-Expiry P&L  ({eq_contracts}c × {eq_multiplier}x = {position_size:,} shares)",
            xaxis_title="Spot at Expiry", yaxis_title="P&L ($)", **_DARK)
        st.plotly_chart(fig_payoff, use_container_width=True)

        st.markdown("##### Sensitivity Charts")
        rc1, rc2, rc3 = st.columns(3)
        rc1.plotly_chart(_sens_chart(sens["spots"], sens["prem_vs_spot"], "Spot", "Premium ($)",
                                      "Premium vs Spot", st.session_state["_eq_S"]),
                          use_container_width=True)
        rc2.plotly_chart(_sens_chart(sens["vols"]*100, sens["prem_vs_vol"], "Vol (%)", "Premium ($)",
                                      "Premium vs Vol", st.session_state["_eq_sig"]*100),
                          use_container_width=True)
        rc3.plotly_chart(_sens_chart(sens["spots"], sens["delta_vs_spot"], "Spot", "Delta (shares)",
                                      "Delta vs Spot", st.session_state["_eq_S"], "#a78bfa"),
                          use_container_width=True)

        rc4, rc5, _ = st.columns(3)
        rc4.plotly_chart(_sens_chart(sens["spots"], sens["vega_vs_spot"], "Spot", "Vega ($/1%vol)",
                                      "Vega vs Spot", st.session_state["_eq_S"], "#34d399"),
                          use_container_width=True)
        rc5.plotly_chart(_sens_chart(sens["spots"], sens["gamma_vs_spot"], "Spot", "Gamma ($/pt²)",
                                      "Gamma vs Spot", st.session_state["_eq_S"], "#fb923c"),
                          use_container_width=True)

        _dl_buttons(st.session_state["_eq_n"],
                    st.session_state["_eq_i"], result, xva)

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
            mat_vs       = _tenor_input("Maturity", 0.5, f"vs_mat_{rk}")
            pos_vs       = st.radio("Position", ["short", "long"], horizontal=True, key=f"vs_pos_{rk}")
        with c2:
            skew_vs      = st.number_input("Skew Slope", value=-0.10, step=0.01, key=f"vs_skew_{rk}")
            vega_notional = st.number_input("Vega Notional ($)", value=100_000, step=10_000, key=f"vs_vn_{rk}")

        if st.button("Price Var Swap", type="primary"):
            rv = rv_input if rv_input > 0 else None
            _res = price_var_swap(atm_vol_vs, rv, mat_vs, vega_notional, skew_vs, pos_vs)
            _xva = total_xva("VOL_PROD", mat_vs, vega_notional, client_type,
                             cds_override or None, funding_spread)
            st.session_state.update({
                "_vs_r": _res, "_vs_x": _xva, "_vs_rk": rk,
                "_vs_i": {
                    "ATM Implied Vol": f"{atm_vol_vs*100:.1f}%",
                    "RV to Date": f"{rv_input*100:.1f}%" if rv_input > 0 else "Forward start",
                    "Maturity": f"{mat_vs:.2f}Y",
                    "Position": pos_vs.capitalize(),
                    "Skew Slope": str(skew_vs),
                    "Vega Notional": f"${vega_notional:,.0f}",
                    "Client Type": client_type,
                },
                "_vs_n": f"Variance Swap {mat_vs:.2f}Y {pos_vs.capitalize()}",
            })

        if st.session_state.get("_vs_rk") == rk:
            result = st.session_state["_vs_r"]
            xva    = st.session_state["_vs_x"]

            c1, c2, c3 = st.columns(3)
            c1.metric("Fair Var Strike (as vol)", f"{result['fair_var_strike_pct']:.2f}%")
            c2.metric("Fair Vol Strike",          f"{result['fair_vol_strike_pct']:.2f}%")
            c3.metric("Break-even RV",            f"{result['break_even_rv_pct']:.2f}%")
            if "pnl" in result:
                st.metric("MtM P&L", f"${result['pnl']:,.0f}")
            st.caption(f"Var Notional: ${result['var_notional']:,.0f}  |  xVA: {xva['total_xva_bps']:.1f} bps")
            with st.expander("Full Output"):
                st.json({**result, "xva": xva})

            _dl_buttons(st.session_state["_vs_n"],
                        st.session_state["_vs_i"], result, xva)

    elif prod_choice == "Vol Swap":
        atm_vol_vlsw  = st.number_input("ATM Vol (%)", value=18.0, step=0.5, key=f"vlsw_atm_{rk}") / 100
        mat_vlsw      = _tenor_input("Maturity", 0.5, f"vlsw_mat_{rk}")
        pos_vlsw      = st.radio("Position", ["short", "long"], horizontal=True, key=f"vlsw_pos_{rk}")
        vlsw_notional = st.number_input("Notional ($)", value=1_000_000, step=100_000,
                                         format="%d", key=f"vlsw_N_{rk}")

        if st.button("Price Vol Swap", type="primary"):
            _res = price_vol_swap(atm_vol_vlsw, mat_vlsw, vlsw_notional, pos_vlsw)
            _xva = total_xva("VOL_PROD", mat_vlsw, vlsw_notional, client_type,
                             cds_override or None, funding_spread)
            st.session_state.update({
                "_vlsw_r": _res, "_vlsw_x": _xva, "_vlsw_rk": rk,
                "_vlsw_i": {
                    "ATM Vol": f"{atm_vol_vlsw*100:.1f}%",
                    "Maturity": f"{mat_vlsw:.2f}Y",
                    "Position": pos_vlsw.capitalize(),
                    "Notional": f"${vlsw_notional:,.0f}",
                    "Client Type": client_type,
                },
                "_vlsw_n": f"Vol Swap {mat_vlsw:.2f}Y {pos_vlsw.capitalize()}",
            })

        if st.session_state.get("_vlsw_rk") == rk:
            result = st.session_state["_vlsw_r"]
            xva    = st.session_state["_vlsw_x"]

            c1, c2 = st.columns(2)
            c1.metric("Fair Vol Strike",      f"{result['fair_vol_strike_pct']:.2f}%")
            c2.metric("Convexity Correction", f"{result['convexity_correction_bps']:.1f} bps")
            st.caption(f"Var vs Vol premium: {result['var_vs_vol_premium_bps']:.1f} bps  |  xVA: {xva['total_xva_bps']:.1f} bps")
            with st.expander("Full Output"):
                st.json({**result, "xva": xva})

            _dl_buttons(st.session_state["_vlsw_n"],
                        st.session_state["_vlsw_i"], result, xva)

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
            _res = vix_roll_down(vix_spot_in, vix3m_in, roll_days)
            st.session_state.update({
                "_vix_r": _res, "_vix_rk": rk,
                "_vix_i": {
                    "VIX Spot": f"{vix_spot_in:.1f}",
                    "VIX 3M": f"{vix3m_in:.1f}",
                    "Roll Horizon": f"{roll_days} days",
                },
                "_vix_n": f"VIX Roll-Down {roll_days}d",
            })

        if st.session_state.get("_vix_rk") == rk:
            result = st.session_state["_vix_r"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Contango",            f"{result.get('contango_pct', 0):+.2f}%")
            c2.metric(f"Roll ({roll_days}d)", f"{result.get('roll_carry_per_month', 0):.2f} vol pts")
            c3.metric("Ann. Carry",          f"{result.get('annualised_carry_pct', 0):.2f}%/vix")

            _dl_buttons(st.session_state["_vix_n"],
                        st.session_state["_vix_i"], result, {})

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
        ac_maturity = _tenor_input("Maturity", 3.0, f"ac_mat_{rk}", min_years=0.5)
        ac_obs      = st.selectbox("Observation", [4, 12, 1], index=0,
                                    format_func=lambda x: {4: "Quarterly", 12: "Monthly", 1: "Annual"}[x],
                                    key=f"ac_obs_{rk}")
        ac_notional = st.number_input("Notional ($)", value=1_000_000,
                                       step=1_000_000, format="%d", key=f"ac_N_{rk}")

    def _price_ac(spot=100, vol=None, barrier=None):
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
        _res = _price_ac()
        _xva = total_xva("STRUCT_AC", ac_maturity, ac_notional, client_type,
                         cds_override or None, funding_spread)

        spots_ac = np.linspace(70, 130, 40)
        vols_ac  = np.linspace(0.08, 0.55, 40)
        eps_s    = 1.0
        p_spot, d_spot, g_spot, v_spot, p_vol = [], [], [], [], []
        for s in spots_ac:
            p0 = _price_ac(spot=s)["indicative_price_pct"]
            pp = _price_ac(spot=s + eps_s)["indicative_price_pct"]
            pm = _price_ac(spot=s - eps_s)["indicative_price_pct"]
            pv = _price_ac(spot=s, vol=min(ac_sigma + 0.01, 0.99))["indicative_price_pct"]
            p_spot.append(p0)
            d_spot.append((pp - pm) / (2 * eps_s))
            g_spot.append((pp - 2*p0 + pm) / eps_s**2)
            v_spot.append((pv - p0) / 0.01)
        for v in vols_ac:
            p_vol.append(_price_ac(vol=v)["indicative_price_pct"])

        obs_label = {4: "Quarterly", 12: "Monthly", 1: "Annual"}[ac_obs]
        st.session_state.update({
            "_ac_r": _res, "_ac_x": _xva, "_ac_rk": rk,
            "_ac_sens": dict(spots=spots_ac, vols=vols_ac, vols_pct=vols_ac*100,
                             ac_vol_pct=ac_sigma*100,
                             p_spot=p_spot, d_spot=d_spot, g_spot=g_spot,
                             v_spot=v_spot, p_vol=p_vol),
            "_ac_i": {
                "Underlying Vol": f"{ac_sigma*100:.1f}%",
                "Risk-Free Rate": f"{ac_r*100:.2f}%",
                "Div Yield": f"{ac_q*100:.1f}%",
                "Autocall Barrier": f"{ac_barrier*100:.0f}% initial",
                "KI Barrier": f"{ac_ki*100:.0f}% initial",
                "Annual Coupon": f"{ac_coupon*100:.1f}%",
                "Maturity": f"{ac_maturity:.2f}Y",
                "Observation": obs_label,
                "Notional": f"${ac_notional:,.0f}",
                "Client Type": client_type,
            },
            "_ac_n": f"Autocall {ac_maturity:.1f}Y {ac_coupon*100:.1f}%cpn",
        })

    if st.session_state.get("_ac_rk") == rk:
        result = st.session_state["_ac_r"]
        xva    = st.session_state["_ac_x"]
        sens   = st.session_state["_ac_sens"]

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

        st.markdown("##### Sensitivity Charts")
        ac1, ac2 = st.columns(2)
        ac1.plotly_chart(_sens_chart(sens["spots"], sens["p_spot"], "Spot (% initial)", "Price (% par)",
                                      "Price vs Spot", 100), use_container_width=True)
        ac2.plotly_chart(_sens_chart(sens["vols_pct"], sens["p_vol"], "Vol (%)", "Price (% par)",
                                      "Price vs Vol", sens["ac_vol_pct"]), use_container_width=True)

        ac3, ac4, ac5 = st.columns(3)
        ac3.plotly_chart(_sens_chart(sens["spots"], sens["d_spot"], "Spot (% initial)",
                                      "Δ Price / Δ Spot", "Delta vs Spot", 100, "#a78bfa"),
                          use_container_width=True)
        ac4.plotly_chart(_sens_chart(sens["spots"], sens["g_spot"], "Spot (% initial)",
                                      "Δ² Price / Δ Spot²", "Gamma vs Spot", 100, "#fb923c"),
                          use_container_width=True)
        ac5.plotly_chart(_sens_chart(sens["spots"], sens["v_spot"], "Spot (% initial)",
                                      "Δ Price / Δ1%vol", "Vega vs Spot", 100, "#34d399"),
                          use_container_width=True)

        _dl_buttons(st.session_state["_ac_n"],
                    st.session_state["_ac_i"], result, xva)

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
        sn_mat      = _tenor_input("Maturity", 3.0, f"sn_mat_{rk}", min_years=0.5)
        sn_sigma    = st.number_input("Vol (%)", value=18.0, step=1.0, key=f"sn_sig_{rk}") / 100
        sn_r        = st.number_input("Risk-Free Rate (%)", value=round(r * 100, 2),
                                       step=0.05, key=f"sn_r_{rk}") / 100
        sn_q        = st.number_input("Div Yield (%)", value=round(q * 100, 2),
                                       step=0.1, key=f"sn_q_{rk}") / 100
        sn_notional = st.number_input("Notional ($)", value=1_000_000,
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
            _res = price_capital_protection_note(
                sn_spot, strike_ratio, participation, sn_mat,
                sn_r, sn_q, sn_sigma, protection, sn_notional,
            )
            _xva = total_xva("STRUCT_AC", sn_mat, sn_notional, client_type,
                             cds_override or None, funding_spread)
            _inp = {
                "Note Type": "Capital Protection Note",
                "Spot": f"{sn_spot:.1f}",
                "Call Strike": f"{strike_ratio*100:.0f}% of initial",
                "Participation": f"{participation*100:.0f}%",
                "Protection Level": f"{protection*100:.0f}%",
                "Maturity": f"{sn_mat:.2f}Y",
                "Vol": f"{sn_sigma*100:.1f}%",
                "Risk-Free Rate": f"{sn_r*100:.2f}%",
                "Div Yield": f"{sn_q*100:.1f}%",
                "Notional": f"${sn_notional:,.0f}",
                "Client Type": client_type,
            }
            _name = f"CPN {sn_mat:.1f}Y {protection*100:.0f}%prot {participation*100:.0f}%part"
        else:
            _res = price_yield_enhancement_note(
                sn_spot, sn_strike_ratio, sn_mat, sn_r, sn_q, sn_sigma, sn_notional,
            )
            _xva = total_xva("STRUCT_AC", sn_mat, sn_notional, client_type,
                             cds_override or None, funding_spread)
            _inp = {
                "Note Type": "Yield Enhancement (Reverse Convertible)",
                "Spot": f"{sn_spot:.1f}",
                "Put Strike": f"{sn_strike_ratio*100:.0f}% of spot",
                "Maturity": f"{sn_mat:.2f}Y",
                "Vol": f"{sn_sigma*100:.1f}%",
                "Risk-Free Rate": f"{sn_r*100:.2f}%",
                "Div Yield": f"{sn_q*100:.1f}%",
                "Notional": f"${sn_notional:,.0f}",
                "Client Type": client_type,
            }
            _name = f"YEN {sn_mat:.1f}Y {sn_strike_ratio*100:.0f}%strike"

        st.session_state.update({
            "_sn_r": _res, "_sn_x": _xva, "_sn_rk": rk,
            "_sn_i": _inp, "_sn_n": _name, "_sn_type": note_type,
        })

    if st.session_state.get("_sn_rk") == rk:
        result    = st.session_state["_sn_r"]
        xva       = st.session_state["_sn_x"]
        note_type_disp = st.session_state["_sn_type"]

        if note_type_disp == "Capital Protection Note":
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

        _dl_buttons(st.session_state["_sn_n"],
                    st.session_state["_sn_i"], result, xva)

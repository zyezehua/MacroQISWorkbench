"""
P&L attribution for backtest results.

Payoff mode: decompose terminal P&L into:
  - Delta contribution: delta_entry × ΔS
  - Vega contribution:  vega_entry × Δvol
  - Theta:              theta_entry × tenor_days
  - Residual:           total - above components

Delta-hedged mode: aggregate daily attribution already computed in engine.
"""
import numpy as np
import pandas as pd
from modules.pricing import black_scholes as bs
from modules.backtest.engine import _price_strategy


def payoff_attribution(trade_df, strategy):
    """
    Add attribution columns to payoff trade DataFrame.
    Requires: S_entry, S_exit, vol_entry, vol_exit, entry_date, exit_date columns.
    """
    if trade_df.empty:
        return trade_df

    records = []
    for _, row in trade_df.iterrows():
        S0    = row["S_entry"]
        S_T   = row["S_exit"]
        sigma = row["vol_entry"]
        r     = 0.04          # approximate; full version would use per-trade rate
        tenor = (pd.Timestamp(row["exit_date"]) - pd.Timestamp(row["entry_date"])).days
        # Use the engine's T (business-day tenor) if stored; fall back to calendar/365
        T     = max(row.get("T_entry", tenor / 365.0), 1e-6)

        try:
            _, legs = _price_strategy(strategy, S0, T, r, sigma)
            g = _strategy_greeks(strategy, S0, T, r, sigma, legs)

            # All contributions normalised by S0 to match trade_df pnl units (% of spot)
            delta_pnl = g["delta"] * (S_T - S0) / S0
            # g["vega"] is $/vol-point; vol values are decimal → multiply by 100 to convert
            vega_pnl  = g["vega"]  * (row.get("vol_exit", sigma) - sigma) * 100 / S0
            theta_pnl = g["theta"] * tenor / S0
            residual  = row["pnl"] - delta_pnl - vega_pnl - theta_pnl
        except Exception:
            delta_pnl = vega_pnl = theta_pnl = residual = np.nan

        records.append({
            "entry_date": row["entry_date"],
            "pnl":        row["pnl"],
            "delta_pnl":  delta_pnl,
            "vega_pnl":   vega_pnl,
            "theta_pnl":  theta_pnl,
            "residual":   residual,
        })

    attr_df = pd.DataFrame(records)
    return trade_df.merge(
        attr_df[["entry_date", "delta_pnl", "vega_pnl", "theta_pnl", "residual"]],
        on="entry_date", how="left",
    )


def _strategy_greeks(strategy, S, T, r, sigma, legs):
    """Aggregate net greeks for a strategy at entry."""
    def _g(K, ot):
        g = bs.greeks(S, K, T, r, sigma, ot)
        return g["delta"], g["vega"], g["theta"]

    delta = vega = theta = 0.0

    if strategy == "long_straddle":
        d1, v1, t1 = _g(legs["call_K"], "call")
        d2, v2, t2 = _g(legs["put_K"],  "put")
        delta, vega, theta = d1 + d2, v1 + v2, t1 + t2
    elif strategy == "short_straddle":
        d1, v1, t1 = _g(legs["call_K"], "call")
        d2, v2, t2 = _g(legs["put_K"],  "put")
        delta, vega, theta = -(d1 + d2), -(v1 + v2), -(t1 + t2)
    elif strategy == "long_call":
        delta, vega, theta = _g(legs["call_K"], "call")
    elif strategy == "long_put":
        delta, vega, theta = _g(legs["put_K"], "put")
    elif strategy == "call_spread":
        d1, v1, t1 = _g(legs["long_call_K"],  "call")
        d2, v2, t2 = _g(legs["short_call_K"], "call")
        delta, vega, theta = d1 - d2, v1 - v2, t1 - t2
    elif strategy == "put_spread":
        d1, v1, t1 = _g(legs["long_put_K"],  "put")
        d2, v2, t2 = _g(legs["short_put_K"], "put")
        delta, vega, theta = d1 - d2, v1 - v2, t1 - t2
    elif strategy == "risk_reversal":
        d1, v1, t1 = _g(legs["long_call_K"],  "call")
        d2, v2, t2 = _g(legs["short_put_K"], "put")
        delta, vega, theta = d1 - d2, v1 - v2, t1 - t2
    elif strategy == "covered_call":
        d1, v1, t1 = _g(legs["short_call_K"], "call")
        delta, vega, theta = 1.0 - d1, -v1, -t1
    elif strategy == "long_strangle":
        d1, v1, t1 = _g(legs["put_K"],  "put")
        d2, v2, t2 = _g(legs["call_K"], "call")
        delta, vega, theta = d1 + d2, v1 + v2, t1 + t2

    return {"delta": delta, "vega": vega, "theta": theta}


def attribution_summary(attr_df):
    """Aggregate attribution across all trades."""
    cols = ["delta_pnl", "vega_pnl", "theta_pnl", "residual", "pnl"]
    summary = attr_df[[c for c in cols if c in attr_df.columns]].sum()
    total = summary.get("pnl", 1)
    pct   = summary / abs(total) * 100 if abs(total) > 1e-10 else summary * 0
    return pd.DataFrame({
        "Total P&L": summary.round(6),
        "% of Total": pct.round(1),
    })

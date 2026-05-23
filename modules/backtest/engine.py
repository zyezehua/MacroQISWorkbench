"""
Backtest engine — two modes:

  payoff        : entry premium vs terminal intrinsic payoff per trade.
                  Clean and intuitive — "did this strategy make money?"

  delta_hedged  : daily delta rebalancing. P&L = option value change
                  minus cost of delta hedge. Isolates vol carry (IV - RV).

Strategies are identified by string key; pricing is done via Black-Scholes
on historical spot + VIX-proxy vol, so results are model-dependent.
"""
import numpy as np
import pandas as pd
from modules.pricing import black_scholes as bs


# ── Strategy registry ──────────────────────────────────────────────────────────
# Each entry: (legs, description)
# Leg format: (option_type, strike_offset_sigma, qty)
#   strike_offset_sigma: fraction of ATM vol * sqrt(T) OTM; 0 = ATM

STRATEGIES = {
    "long_straddle":    "Long Straddle (ATM call + put)",
    "short_straddle":   "Short Straddle (sell ATM call + put)",
    "long_call":        "Long Call (ATM)",
    "long_put":         "Long Put (ATM)",
    "call_spread":      "Call Spread (+5% / +10% OTM)",
    "put_spread":       "Put Spread (-5% / -10% OTM)",
    "risk_reversal":    "Risk Reversal (short -5% put / long +5% call)",
    "covered_call":     "Covered Call (+5% OTM short call)",
    "long_strangle":    "Long Strangle (±5% OTM)",
}


def _price_strategy(strategy, S, T, r, sigma):
    """Return (net_premium, legs_dict) for a given strategy at entry."""
    K_atm = S
    K_c5  = S * 1.05
    K_c10 = S * 1.10
    K_p5  = S * 0.95
    K_p10 = S * 0.90

    # Skew proxy: put vol slightly higher
    sv_p = sigma * 1.08
    sv_c = sigma * 0.97

    if strategy == "long_straddle":
        c = bs.price(S, K_atm, T, r, sigma, "call")
        p = bs.price(S, K_atm, T, r, sigma, "put")
        premium = c + p
        legs = {"call_K": K_atm, "put_K": K_atm, "call_p": c, "put_p": p}

    elif strategy == "short_straddle":
        c = bs.price(S, K_atm, T, r, sigma, "call")
        p = bs.price(S, K_atm, T, r, sigma, "put")
        premium = -(c + p)   # collect premium
        legs = {"call_K": K_atm, "put_K": K_atm, "call_p": -c, "put_p": -p}

    elif strategy == "long_call":
        premium = bs.price(S, K_atm, T, r, sigma, "call")
        legs = {"call_K": K_atm}

    elif strategy == "long_put":
        premium = bs.price(S, K_atm, T, r, sigma, "put")
        legs = {"put_K": K_atm}

    elif strategy == "call_spread":
        lo = bs.price(S, K_c5,  T, r, sv_c, "call")
        hi = bs.price(S, K_c10, T, r, sv_c * 0.95, "call")
        premium = lo - hi
        legs = {"long_call_K": K_c5, "short_call_K": K_c10}

    elif strategy == "put_spread":
        hi = bs.price(S, K_p5,  T, r, sv_p, "put")
        lo = bs.price(S, K_p10, T, r, sv_p * 1.05, "put")
        premium = hi - lo
        legs = {"long_put_K": K_p5, "short_put_K": K_p10}

    elif strategy == "risk_reversal":
        p = bs.price(S, K_p5, T, r, sv_p, "put")
        c = bs.price(S, K_c5, T, r, sv_c, "call")
        premium = c - p   # net cost (usually small)
        legs = {"short_put_K": K_p5, "long_call_K": K_c5}

    elif strategy == "covered_call":
        c = bs.price(S, K_c5, T, r, sv_c, "call")
        premium = -c   # collect call premium; long stock is implicit
        legs = {"short_call_K": K_c5}

    elif strategy == "long_strangle":
        p = bs.price(S, K_p5, T, r, sv_p, "put")
        c = bs.price(S, K_c5, T, r, sv_c, "call")
        premium = p + c
        legs = {"put_K": K_p5, "call_K": K_c5}

    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    return premium, legs


def _terminal_payoff(strategy, S0, S_T, legs):
    """Compute terminal intrinsic payoff at S_T."""
    def _call_pay(K): return max(S_T - K, 0)
    def _put_pay(K):  return max(K - S_T, 0)

    if strategy == "long_straddle":
        return _call_pay(legs["call_K"]) + _put_pay(legs["put_K"])
    if strategy == "short_straddle":
        return -(_call_pay(legs["call_K"]) + _put_pay(legs["put_K"]))
    if strategy == "long_call":
        return _call_pay(legs["call_K"])
    if strategy == "long_put":
        return _put_pay(legs["put_K"])
    if strategy == "call_spread":
        return _call_pay(legs["long_call_K"]) - _call_pay(legs["short_call_K"])
    if strategy == "put_spread":
        return _put_pay(legs["long_put_K"]) - _put_pay(legs["short_put_K"])
    if strategy == "risk_reversal":
        return _call_pay(legs["long_call_K"]) - _put_pay(legs["short_put_K"])
    if strategy == "covered_call":
        return (S_T - S0) - _call_pay(legs["short_call_K"])   # includes stock P&L
    if strategy == "long_strangle":
        return _call_pay(legs["call_K"]) + _put_pay(legs["put_K"])
    return 0.0


def _net_delta(strategy, S, T, r, sigma, legs):
    """Net delta of strategy at given market state."""
    def _cg(K, otype): return bs.greeks(S, K, T, r, sigma, otype)["delta"]

    K_atm = S  # For strategies with fixed strikes, use legs dict
    if strategy == "long_straddle":
        return _cg(legs["call_K"], "call") + _cg(legs["put_K"], "put")
    if strategy == "short_straddle":
        return -(_cg(legs["call_K"], "call") + _cg(legs["put_K"], "put"))
    if strategy == "long_call":
        return _cg(legs["call_K"], "call")
    if strategy == "long_put":
        return _cg(legs["put_K"], "put")
    if strategy == "call_spread":
        return _cg(legs["long_call_K"], "call") - _cg(legs["short_call_K"], "call")
    if strategy == "put_spread":
        return _cg(legs["long_put_K"], "put") - _cg(legs["short_put_K"], "put")
    if strategy == "risk_reversal":
        return _cg(legs["long_call_K"], "call") - _cg(legs["short_put_K"], "put")
    if strategy == "covered_call":
        return 1.0 - _cg(legs["short_call_K"], "call")
    if strategy == "long_strangle":
        return _cg(legs["call_K"], "call") + _cg(legs["put_K"], "put")
    return 0.0


def _option_value(strategy, S, T, r, sigma, legs):
    """Mark-to-market option value (not including stock leg)."""
    def _cp(K, ot): return bs.price(S, K, max(T, 1e-6), r, sigma, ot)

    if strategy == "long_straddle":
        return _cp(legs["call_K"], "call") + _cp(legs["put_K"], "put")
    if strategy == "short_straddle":
        return -(_cp(legs["call_K"], "call") + _cp(legs["put_K"], "put"))
    if strategy == "long_call":
        return _cp(legs["call_K"], "call")
    if strategy == "long_put":
        return _cp(legs["put_K"], "put")
    if strategy == "call_spread":
        return _cp(legs["long_call_K"], "call") - _cp(legs["short_call_K"], "call")
    if strategy == "put_spread":
        return _cp(legs["long_put_K"], "put") - _cp(legs["short_put_K"], "put")
    if strategy == "risk_reversal":
        return _cp(legs["long_call_K"], "call") - _cp(legs["short_put_K"], "put")
    if strategy == "covered_call":
        return -_cp(legs["short_call_K"], "call")
    if strategy == "long_strangle":
        return _cp(legs["call_K"], "call") + _cp(legs["put_K"], "put")
    return 0.0


# ── Main engine ────────────────────────────────────────────────────────────────

class BacktestEngine:

    def __init__(self, data):
        """data: pd.DataFrame with columns spot, vol, rate, log_ret."""
        self.data = data.copy()

    def run(self, strategy, tenor_days=21, roll_freq_days=21, mode="payoff", normalise=True):
        """
        Parameters
        ----------
        strategy       : key from STRATEGIES dict
        tenor_days     : option tenor in calendar days (approx business days / 252)
        roll_freq_days : rolling frequency in business days
        mode           : 'payoff' | 'delta_hedged'
        normalise      : normalise premium by spot (makes P&L % of spot)

        Returns
        -------
        trade_df : pd.DataFrame, one row per trade
        daily_df : pd.DataFrame, daily P&L (delta_hedged only; empty for payoff)
        """
        if mode == "payoff":
            return self._run_payoff(strategy, tenor_days, roll_freq_days, normalise)
        if mode == "delta_hedged":
            return self._run_delta_hedged(strategy, tenor_days, roll_freq_days, normalise)
        raise ValueError(f"Unknown mode: {mode}")

    def _run_payoff(self, strategy, tenor_days, roll_freq_days, normalise):
        df = self.data.dropna(subset=["spot", "vol", "rate"])
        dates = df.index.tolist()
        T_years = tenor_days / 252.0
        results = []

        entry_indices = range(0, len(dates) - tenor_days, roll_freq_days)
        for i in entry_indices:
            entry_date = dates[i]
            row = df.loc[entry_date]
            S0, sigma, r = row["spot"], row["vol"], row["rate"]
            if sigma < 0.01:
                sigma = 0.20

            premium, legs = _price_strategy(strategy, S0, T_years, r, sigma)

            exit_idx = min(i + tenor_days, len(dates) - 1)
            exit_date = dates[exit_idx]
            S_T = df.loc[exit_date, "spot"]
            sigma_T = df.loc[exit_date, "vol"]

            payoff = _terminal_payoff(strategy, S0, S_T, legs)
            pnl = payoff - premium
            spot_ret = (S_T - S0) / S0

            if normalise:
                pnl_norm = pnl / S0
                premium_norm = premium / S0
            else:
                pnl_norm = pnl
                premium_norm = premium

            results.append({
                "entry_date": entry_date,
                "exit_date":  exit_date,
                "S_entry": S0,
                "S_exit":  S_T,
                "spot_ret_pct": spot_ret * 100,
                "vol_entry": sigma,
                "vol_exit":  sigma_T,
                "premium": premium_norm,
                "payoff":  payoff / S0 if normalise else payoff,
                "pnl":     pnl_norm,
                "win":     pnl > 0,
            })

        trade_df = pd.DataFrame(results)
        return trade_df, pd.DataFrame()

    def _run_delta_hedged(self, strategy, tenor_days, roll_freq_days, normalise):
        df = self.data.dropna(subset=["spot", "vol", "rate"])
        dates = df.index.tolist()
        T_years = tenor_days / 252.0
        daily_records = []
        trade_records = []

        entry_indices = range(0, len(dates) - tenor_days, roll_freq_days)
        for i in entry_indices:
            entry_date = dates[i]
            row0 = df.loc[entry_date]
            S0, sigma0, r0 = row0["spot"], row0["vol"], row0["rate"]
            if sigma0 < 0.01:
                sigma0 = 0.20

            premium, legs = _price_strategy(strategy, S0, T_years, r0, sigma0)
            delta_prev = _net_delta(strategy, S0, T_years, r0, sigma0, legs)
            val_prev   = _option_value(strategy, S0, T_years, r0, sigma0, legs)
            hedge_pnl_total = 0.0
            option_pnl_total = 0.0

            for j in range(1, tenor_days + 1):
                if i + j >= len(dates):
                    break
                curr_date = dates[i + j]
                row = df.loc[curr_date]
                S, sigma, r = row["spot"], row["vol"], row["rate"]
                if sigma < 0.01:
                    sigma = 0.20
                T_rem = max((tenor_days - j) / 252.0, 1e-6)

                val_curr = _option_value(strategy, S, T_rem, r, sigma, legs)
                option_chg = val_curr - val_prev

                # Delta hedge P&L: short delta_prev shares at S_prev, close at S
                S_prev = df.loc[dates[i + j - 1], "spot"]
                hedge_chg = -delta_prev * (S - S_prev)

                daily_pnl = option_chg + hedge_chg
                hedge_pnl_total  += hedge_chg
                option_pnl_total += option_chg

                # Update delta for next day
                delta_curr = _net_delta(strategy, S, T_rem, r, sigma, legs)
                daily_records.append({
                    "date": curr_date,
                    "entry_date": entry_date,
                    "S": S,
                    "vol": sigma,
                    "T_rem": T_rem,
                    "delta": delta_curr,
                    "option_val": val_curr,
                    "daily_pnl": daily_pnl / S0 if normalise else daily_pnl,
                    "option_chg": option_chg / S0 if normalise else option_chg,
                    "hedge_chg":  hedge_chg  / S0 if normalise else hedge_chg,
                })
                delta_prev = delta_curr
                val_prev   = val_curr

            total_pnl = option_pnl_total + hedge_pnl_total
            trade_records.append({
                "entry_date": entry_date,
                "exit_date":  dates[min(i + tenor_days, len(dates) - 1)],
                "S_entry": S0,
                "S_exit":  df.loc[dates[min(i + tenor_days, len(dates) - 1)], "spot"],
                "vol_entry": sigma0,
                "premium": premium / S0 if normalise else premium,
                "pnl_option": option_pnl_total / S0 if normalise else option_pnl_total,
                "pnl_hedge":  hedge_pnl_total  / S0 if normalise else hedge_pnl_total,
                "pnl":        total_pnl / S0 if normalise else total_pnl,
                "win":        total_pnl > 0,
            })

        trade_df = pd.DataFrame(trade_records)
        daily_df = pd.DataFrame(daily_records)
        return trade_df, daily_df

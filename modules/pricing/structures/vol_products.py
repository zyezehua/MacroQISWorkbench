"""
Vol products: variance swaps and vol swaps (simplified replication / approximation).
Var swap fair strike ≈ implied vol^2 with log-moneyness skew correction.
Vol swap fair strike ≈ var_strike^0.5 * convexity_correction.
"""
import numpy as np


def fair_var_strike(atm_vol, skew_slope=0.0, excess_kurtosis=0.0):
    """
    Fair variance strike (annualised) using moment approximation.
    K_var ≈ sigma_atm^2 * (1 + skew_correction + kurtosis_correction)

    Parameters
    ----------
    atm_vol        : ATM implied vol (decimal)
    skew_slope     : d(vol)/d(log-moneyness) — typically negative for equity
    excess_kurtosis: fourth moment correction (typically 0 for PoC)

    Returns
    -------
    variance_strike (decimal^2), vol_strike (decimal)
    """
    variance_strike = atm_vol ** 2 * (1 + skew_slope ** 2 + excess_kurtosis / 4)
    vol_strike_approx = np.sqrt(variance_strike)
    return variance_strike, vol_strike_approx


def price_var_swap(
    atm_vol,
    realized_vol=None,
    maturity_years=0.5,
    notional_vega=100_000,
    skew_slope=0.0,
    position="short",
):
    """
    Indicative var swap P&L and mark-to-market.

    Position 'short': sell var (collect premium if RV < IV).
    Position 'long':  buy  var (profit if RV > IV).

    Parameters
    ----------
    atm_vol        : current ATM implied vol
    realized_vol   : realized vol to date (None = not yet started)
    maturity_years : swap maturity
    notional_vega  : vega notional (e.g. 100k per vol point)
    skew_slope     : for fair strike computation
    position       : 'long' | 'short'
    """
    var_strike, vol_strike = fair_var_strike(atm_vol, skew_slope)
    var_notional = notional_vega / (2 * vol_strike)  # convert vega to var notional

    sign = -1 if position == "short" else +1

    mtm = {}
    if realized_vol is not None:
        rv_var = realized_vol ** 2
        pnl = sign * var_notional * (rv_var - var_strike)
        mtm = {
            "pnl": round(pnl, 0),
            "pnl_per_vol_pt": round(pnl / notional_vega, 4),
        }

    break_even_rv = vol_strike  # short var breaks even at strike

    return {
        "product": f"{'Short' if position == 'short' else 'Long'} Var Swap {maturity_years:.1f}Y",
        "fair_var_strike_pct": round(var_strike ** 0.5 * 100, 2),  # display as vol
        "fair_vol_strike_pct": round(vol_strike * 100, 2),
        "var_notional": round(var_notional, 0),
        "vega_notional": notional_vega,
        "break_even_rv_pct": round(break_even_rv * 100, 2),
        "daily_theta_approx": round(-var_notional * var_strike / 252, 0),
        "position": position,
        **mtm,
    }


def price_vol_swap(
    atm_vol,
    maturity_years=0.5,
    notional_vega=100_000,
    position="short",
):
    """
    Vol swap approximation: fair vol strike ≈ var_strike^0.5 * (1 - kappa/8)
    where kappa = variance of variance (simplified: use atm_vol as proxy).
    """
    var_strike, vol_strike = fair_var_strike(atm_vol)
    convexity_correction = atm_vol ** 2 / (8 * vol_strike + 1e-10)
    fair_vol = vol_strike * (1 - convexity_correction)

    sign = -1 if position == "short" else +1

    return {
        "product": f"{'Short' if position == 'short' else 'Long'} Vol Swap {maturity_years:.1f}Y",
        "fair_vol_strike_pct": round(fair_vol * 100, 2),
        "convexity_correction_bps": round(convexity_correction * 10_000, 1),
        "var_vs_vol_premium_bps": round((vol_strike - fair_vol) * 10_000, 1),
        "vega_notional": notional_vega,
        "position": position,
    }


def vix_roll_down(vix_spot, vix3m, days_to_roll=30):
    """
    Estimate carry from VIX contango roll-down.
    Assumes linear interpolation between spot and 3M.
    """
    if vix3m is None or vix3m <= 0:
        return {}
    slope_per_day = (vix3m - vix_spot) / 63.0  # ~63 trading days to 3M
    roll_carry = slope_per_day * days_to_roll
    return {
        "vix_spot": vix_spot,
        "vix_3m": vix3m,
        "contango_pct": round((vix3m - vix_spot) / vix_spot * 100, 2),
        "roll_carry_per_month": round(roll_carry, 2),
        "annualised_carry_pct": round(roll_carry * 12 / vix_spot * 100, 2),
    }

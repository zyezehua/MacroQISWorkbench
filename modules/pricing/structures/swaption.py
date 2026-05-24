"""
Swaption pricing via Black-76 model.
Payer swaption = call on swap rate (long rates, pay fixed).
Receiver swaption = put on swap rate (short rates, receive fixed).
"""
from modules.pricing.black_model import price as black_price, greeks as black_greeks, approx_annuity


def price_swaption(
    forward_rate,
    strike_rate,
    T_expiry,
    tenor_years,
    sigma,
    notional=1_000_000,
    option_type="payer",
    annuity=None,
):
    """
    Parameters
    ----------
    forward_rate  : forward swap rate (decimal)
    strike_rate   : strike (decimal); ATM = forward_rate
    T_expiry      : option expiry in years (e.g. 1.0 for 1Y expiry)
    tenor_years   : underlying swap tenor (e.g. 10.0 for 10Y swap)
    sigma         : Black lognormal vol (decimal)
    notional      : notional in currency units
    option_type   : 'payer' | 'receiver'
    annuity       : override annuity factor; None = compute from forward_rate

    Returns
    -------
    dict with price_bps, price_amount, greeks, break_even
    """
    if annuity is None:
        annuity = approx_annuity(forward_rate, tenor_years)

    opt = "call" if option_type == "payer" else "put"
    raw = black_price(forward_rate, strike_rate, T_expiry, sigma, df=1.0, option_type=opt)
    g   = black_greeks(forward_rate, strike_rate, T_expiry, sigma, df=1.0, option_type=opt)

    price_bps    = raw * annuity * 10_000
    price_amount = raw * annuity * notional
    dv01_bps     = g["delta"] * annuity * 10_000       # price sensitivity per 100% rate move
    dv01_per_bp  = g["delta"] * annuity                # price_bps change per 1bp rate move
    break_even   = abs(price_bps / (dv01_per_bp + 1e-10))  # bps move to recover premium

    return {
        "product": f"{option_type.capitalize()} Swaption {T_expiry:.0f}Y x {tenor_years:.0f}Y",
        "price_bps": round(price_bps, 2),
        "price_amount": round(price_amount, 2),
        "delta_dv01_bps": round(dv01_bps, 2),
        "gamma": round(g["gamma"], 6),
        "vega_bps": round(g["vega"] * annuity * 10_000, 2),
        "theta_bps_day": round(g["theta"] * annuity * 10_000, 4),
        "break_even_bps": round(break_even, 1),
        "annuity": round(annuity, 4),
        "forward_rate_pct": round(forward_rate * 100, 3),
        "strike_pct": round(strike_rate * 100, 3),
        "option_type": option_type,
    }


def atm_strike(forward_rate):
    return forward_rate


def otm_strike(forward_rate, shift_bps, option_type="payer"):
    shift = shift_bps / 10_000
    return forward_rate + shift if option_type == "payer" else forward_rate - shift

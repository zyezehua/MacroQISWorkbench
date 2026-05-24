"""
Bond futures options pricing via Black-76.
Quoted as % of par (consistent with bond futures convention).
"""
from modules.pricing.black_model import price as black_price, greeks as black_greeks


def price_bond_futures_option(
    futures_price,
    strike,
    T_expiry,
    sigma,
    r=0.0,
    notional=100_000,
    option_type="call",
):
    """
    Parameters
    ----------
    futures_price : current futures price (% of par, e.g. 110.5)
    strike        : option strike (% of par)
    T_expiry      : expiry in years
    sigma         : lognormal vol (decimal, e.g. 0.08 for 8%)
    r             : risk-free rate for discounting (usually close to 0 for futures)
    notional      : contract notional
    option_type   : 'call' | 'put'

    Returns
    -------
    dict with price (% of par), price_amount, greeks
    """
    import numpy as np
    df = np.exp(-r * T_expiry)
    raw = black_price(futures_price, strike, T_expiry, sigma, df=df, option_type=option_type)
    g   = black_greeks(futures_price, strike, T_expiry, sigma, df=df, option_type=option_type)

    price_pct    = raw           # in same units as futures_price (% of par)
    price_amount = raw / 100 * notional
    # 1bp of futures price = ΔF=0.01 in %-par space; ∂price_amount/∂F = delta × N/100
    dv01_per_bp  = g["delta"] * notional / 10_000       # $ per 1bp futures price move

    moneyness = (futures_price - strike) / strike
    break_even_pts = abs(price_pct / (g["delta"] + 1e-8))

    return {
        "product": f"Bond Futures {option_type.capitalize()} {T_expiry:.2f}Y",
        "price_pct": round(price_pct, 4),
        "price_amount": round(price_amount, 2),
        "delta": round(g["delta"], 4),
        "dv01_per_bp": round(dv01_per_bp, 2),
        "gamma": round(g["gamma"], 6),
        "vega_per_vol_pt": round(g["vega"] * notional / 100, 2),
        "theta_per_day": round(g["theta"] * notional / 100, 2),
        "break_even_pts": round(break_even_pts, 3),
        "moneyness_pct": round(moneyness * 100, 2),
        "futures_price": futures_price,
        "strike": strike,
        "option_type": option_type,
    }

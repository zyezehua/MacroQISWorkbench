"""
Black-76 model for options on futures / swaptions / bond futures options.
F = forward price/rate, K = strike, T = option expiry (years),
sigma = lognormal vol (decimal), df = discount factor to option expiry.
"""
import numpy as np
from utils.math_utils import norm_cdf, norm_pdf


def _d1d2(F, K, T, sigma):
    d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def price(F, K, T, sigma, df, option_type="call"):
    """Black-76 option price."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(F - K, 0) if option_type == "call" else max(K - F, 0)
        return df * intrinsic
    d1, d2 = _d1d2(F, K, T, sigma)
    if option_type == "call":
        return df * (F * norm_cdf(d1) - K * norm_cdf(d2))
    return df * (K * norm_cdf(-d2) - F * norm_cdf(-d1))


def greeks(F, K, T, sigma, df, option_type="call"):
    """Black-76 greeks (delta w.r.t. forward, vega, theta, gamma)."""
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    d1, d2 = _d1d2(F, K, T, sigma)
    pdf_d1 = norm_pdf(d1)
    sign = 1 if option_type == "call" else -1

    delta = df * sign * norm_cdf(sign * d1)
    gamma = df * pdf_d1 / (F * sigma * np.sqrt(T))
    vega = df * F * pdf_d1 * np.sqrt(T) / 100
    theta = (
        -df * F * pdf_d1 * sigma / (2 * np.sqrt(T))
    ) / 365

    return {
        "delta": round(delta, 6),
        "gamma": round(gamma, 8),
        "vega": round(vega, 6),
        "theta": theta,  # not rounded — callers multiply by annuity*10000 before display
    }


def swaption_price_bps(
    forward_rate, strike_rate, T_expiry, tenor_years,
    annuity, sigma, option_type="payer"
):
    """
    Swaption price via Black model, expressed in bps of notional.

    Parameters
    ----------
    forward_rate  : forward swap rate (decimal, e.g. 0.045)
    strike_rate   : swaption strike rate (decimal)
    T_expiry      : option expiry in years
    tenor_years   : underlying swap tenor in years
    annuity       : PV01 annuity factor (sum of discount factors * payment freq)
                    For indicative: approximate as tenor / (1 + fwd_rate)^(tenor/2)
    sigma         : Black lognormal vol (decimal)
    option_type   : 'payer' (long rate) | 'receiver' (short rate)

    Returns
    -------
    price in bps of notional, and greeks dict
    """
    opt = "call" if option_type == "payer" else "put"
    raw_price = price(forward_rate, strike_rate, T_expiry, sigma, df=1.0, option_type=opt)
    price_bps = raw_price * annuity * 10_000

    g = greeks(forward_rate, strike_rate, T_expiry, sigma, df=1.0, option_type=opt)
    g["delta_dv01"] = round(g["delta"] * annuity * 10_000, 2)  # DV01 in bps

    return round(price_bps, 2), g


def approx_annuity(forward_rate, tenor_years, payment_freq=2):
    """Indicative annuity factor (semi-annual payments assumed)."""
    n = int(tenor_years * payment_freq)
    freq = 1 / payment_freq
    annuity = sum(freq / (1 + forward_rate * freq) ** i for i in range(1, n + 1))
    return annuity

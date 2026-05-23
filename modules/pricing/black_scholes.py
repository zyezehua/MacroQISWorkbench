"""
Black-Scholes pricing for European options on spot underlyings.
All inputs in consistent units: S/K in price, T in years, r/sigma as decimals.
"""
import numpy as np
from utils.math_utils import norm_cdf, norm_pdf, bs_d1, bs_d2


def price(S, K, T, r, sigma, option_type="call"):
    """Return option price. option_type: 'call' | 'put'."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0) if option_type == "call" else max(K - S, 0)
        return intrinsic
    d1 = bs_d1(S, K, T, r, sigma)
    d2 = bs_d2(S, K, T, r, sigma)
    df = np.exp(-r * T)
    if option_type == "call":
        return S * norm_cdf(d1) - K * df * norm_cdf(d2)
    return K * df * norm_cdf(-d2) - S * norm_cdf(-d1)


def greeks(S, K, T, r, sigma, option_type="call"):
    """Return dict of greeks."""
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
    d1 = bs_d1(S, K, T, r, sigma)
    d2 = bs_d2(S, K, T, r, sigma)
    df = np.exp(-r * T)
    pdf_d1 = norm_pdf(d1)
    sign = 1 if option_type == "call" else -1

    delta = sign * norm_cdf(sign * d1)
    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    vega = S * pdf_d1 * np.sqrt(T) / 100          # per 1 vol point
    theta_call = (
        -S * pdf_d1 * sigma / (2 * np.sqrt(T))
        - r * K * df * norm_cdf(d2)
    ) / 365
    theta = theta_call if option_type == "call" else (
        theta_call + r * K * df
    ) / 365 * 365
    if option_type == "put":
        theta = (-S * pdf_d1 * sigma / (2 * np.sqrt(T)) + r * K * df * norm_cdf(-d2)) / 365
    rho = sign * K * T * df * norm_cdf(sign * d2) / 100  # per 1% rate move

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "vega": round(vega, 4),
        "theta": round(theta, 4),
        "rho": round(rho, 4),
    }


def implied_vol(market_price, S, K, T, r, option_type="call", tol=1e-6, max_iter=100):
    """Newton-Raphson implied vol solver."""
    if T <= 0:
        return None
    sigma = 0.20
    for _ in range(max_iter):
        p = price(S, K, T, r, sigma, option_type)
        vega_val = S * norm_pdf(bs_d1(S, K, T, r, sigma)) * np.sqrt(T)
        if vega_val < 1e-10:
            break
        diff = p - market_price
        if abs(diff) < tol:
            return round(sigma, 6)
        sigma -= diff / vega_val
        sigma = max(1e-4, min(sigma, 5.0))
    return round(sigma, 6)

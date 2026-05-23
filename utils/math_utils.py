import numpy as np
from scipy.stats import norm
from scipy.interpolate import RegularGridInterpolator


def norm_cdf(x):
    return norm.cdf(x)


def norm_pdf(x):
    return norm.pdf(x)


def bs_d1(S, K, T, r, sigma):
    return (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))


def bs_d2(S, K, T, r, sigma):
    return bs_d1(S, K, T, r, sigma) - sigma * np.sqrt(T)


def annualize_vol(daily_vol):
    return daily_vol * np.sqrt(252)


def daily_from_annual_vol(annual_vol):
    return annual_vol / np.sqrt(252)


def interp_1d(x_pts, y_pts, x_query):
    return float(np.interp(x_query, x_pts, y_pts))


def interp_2d(x_pts, y_pts, z_grid, x_query, y_query):
    interp = RegularGridInterpolator(
        (x_pts, y_pts), z_grid, method="linear", bounds_error=False, fill_value=None
    )
    return float(interp([[x_query, y_query]]))


def bps_to_decimal(bps):
    return bps / 10_000


def decimal_to_bps(decimal):
    return decimal * 10_000


def tenor_to_years(tenor_str):
    t = tenor_str.strip().upper()
    if t.endswith("Y"):
        return float(t[:-1])
    if t.endswith("M"):
        return float(t[:-1]) / 12
    if t.endswith("W"):
        return float(t[:-1]) / 52
    if t.endswith("D"):
        return float(t[:-1]) / 252
    raise ValueError(f"Unrecognised tenor format: {tenor_str}")

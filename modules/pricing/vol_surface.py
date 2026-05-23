"""
Simplified vol surface for PoC: linear interpolation on ATM term structure
+ moneyness adjustment via put-call parity implied skew proxy.

Interface is designed to be swappable with SVI or internal data later.
"""
import numpy as np
import pandas as pd
from utils.math_utils import interp_1d
from modules.pricing import black_scholes


class VolSurface:
    """
    Holds a vol surface built from (expiry_years, strike_ratio) → implied_vol.
    strike_ratio = K / S (moneyness).
    """

    def __init__(self, expiry_years, atm_vols, skew_slope=None):
        """
        Parameters
        ----------
        expiry_years : list/array of expiry points in years
        atm_vols     : ATM implied vols (decimal) per expiry
        skew_slope   : d(vol)/d(moneyness) — negative for equity skew
                       None → flat (no skew adjustment)
        """
        self.expiry_years = np.array(expiry_years, dtype=float)
        self.atm_vols = np.array(atm_vols, dtype=float)
        self.skew_slope = skew_slope  # e.g. -0.10 means 10 vol pts per unit moneyness

    def get_atm_vol(self, expiry_years):
        """ATM vol at given expiry, linearly interpolated."""
        return interp_1d(self.expiry_years, self.atm_vols, expiry_years)

    def get_vol(self, strike_ratio, expiry_years):
        """Implied vol for given moneyness and expiry."""
        atm = self.get_atm_vol(expiry_years)
        if self.skew_slope is None:
            return atm
        adjustment = self.skew_slope * (strike_ratio - 1.0)
        return max(0.01, atm + adjustment)

    def term_structure_df(self):
        return pd.DataFrame({
            "Expiry (Y)": self.expiry_years,
            "ATM Vol (%)": (self.atm_vols * 100).round(2),
        })


def build_from_options_chain(chain, spot, r=0.05):
    """
    Build a VolSurface from yfinance options chain dict.
    chain: { expiry_str: {"calls": df, "puts": df} }
    Returns a VolSurface or None if chain is empty.
    """
    from datetime import date
    import pandas as pd

    expiry_years = []
    atm_vols = []

    for exp_str, legs in chain.items():
        try:
            exp_date = pd.to_datetime(exp_str).date()
            T = (exp_date - date.today()).days / 365.0
            if T <= 0:
                continue

            calls = legs.get("calls", pd.DataFrame())
            if calls.empty or "strike" not in calls.columns:
                continue

            atm_idx = (calls["strike"] - spot).abs().idxmin()
            atm_call = calls.loc[atm_idx]
            mid = (atm_call.get("bid", 0) + atm_call.get("ask", 0)) / 2
            K = atm_call["strike"]

            if mid > 0:
                iv = black_scholes.implied_vol(mid, spot, K, T, r, "call")
                if iv and 0.01 < iv < 3.0:
                    expiry_years.append(T)
                    atm_vols.append(iv)
        except Exception:
            continue

    if len(expiry_years) < 2:
        return None

    order = np.argsort(expiry_years)
    return VolSurface(
        np.array(expiry_years)[order],
        np.array(atm_vols)[order],
        skew_slope=-0.08,   # equity skew proxy
    )


def flat_surface(atm_vol, expiries=(0.083, 0.25, 0.5, 1.0, 2.0)):
    """Convenience: flat vol surface for manual/override input."""
    return VolSurface(
        expiry_years=list(expiries),
        atm_vols=[atm_vol] * len(expiries),
        skew_slope=-0.08,
    )

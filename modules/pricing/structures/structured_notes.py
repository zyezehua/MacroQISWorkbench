"""
Structured notes: capital protection notes and yield-enhancement notes.
All prices as % of notional.
"""
import numpy as np
from modules.pricing import black_scholes as bs


def price_capital_protection_note(
    spot,
    strike_ratio=1.00,
    participation=1.00,
    maturity_years=3.0,
    r=0.04,
    q=0.02,
    sigma=0.18,
    protection_pct=1.00,
    notional=1_000_000,
):
    """
    Capital Protection Note = Zero-coupon bond + Call option.

    Parameters
    ----------
    spot             : current spot
    strike_ratio     : call strike as fraction of spot (e.g. 1.0 = ATM)
    participation    : upside participation rate (e.g. 1.0 = 100%)
    maturity_years   : note maturity
    r                : risk-free rate
    q                : dividend yield
    sigma            : implied vol
    protection_pct   : capital guarantee level (e.g. 1.0 = 100% protection)
    notional         : notional amount

    Returns
    -------
    dict with note price, component breakdown, max upside
    """
    df = np.exp(-r * maturity_years)
    K = spot * strike_ratio

    # Zero-coupon bond cost (funds capital protection)
    zc_cost_pct = protection_pct * df * 100

    # Call option cost (funds participation)
    call_price = bs.price(spot, K, maturity_years, r, sigma, "call")
    call_cost_pct = participation * call_price / spot * 100

    total_cost_pct = zc_cost_pct + call_cost_pct

    # Residual budget (positive = issuer margin, negative = can't fund at par)
    residual_pct = 100 - total_cost_pct

    # Max upside: participation * (max_underlying_return)
    # At maturity, max meaningful upside for display is ~3x sigma
    fwd = spot * np.exp((r - q) * maturity_years)
    expected_upside_pct = participation * max(fwd - K, 0) / spot * 100

    return {
        "product": f"Capital Protection Note {maturity_years:.0f}Y {protection_pct*100:.0f}% Protection",
        "total_cost_pct": round(total_cost_pct, 3),
        "zc_bond_cost_pct": round(zc_cost_pct, 3),
        "call_cost_pct": round(call_cost_pct, 3),
        "residual_margin_pct": round(residual_pct, 3),
        "protection_level_pct": round(protection_pct * 100, 1),
        "participation_pct": round(participation * 100, 1),
        "strike": K,
        "expected_upside_pct": round(expected_upside_pct, 2),
        "discount_factor": round(df, 4),
        "feasible": total_cost_pct <= 100,
        "notional": notional,
    }


def price_yield_enhancement_note(
    spot,
    strike_ratio=1.00,
    maturity_years=1.0,
    r=0.04,
    q=0.02,
    sigma=0.20,
    notional=1_000_000,
    downside_barrier=None,
):
    """
    Yield Enhancement Note = Short put + T-bill (cash-secured put / reverse convertible).
    If downside_barrier is set, models a barrier put (cheaper premium).

    Returns
    -------
    dict with yield, max loss, break-even
    """
    K = spot * strike_ratio
    put_premium = bs.price(spot, K, maturity_years, r, sigma, "put")
    tbill_yield = r * maturity_years

    total_yield_pct = (put_premium / spot + tbill_yield) * 100
    break_even = K - put_premium
    max_loss_pct = (K - put_premium) / spot * 100  # if underlying goes to zero

    annualised_yield = total_yield_pct / maturity_years

    return {
        "product": f"Yield Enhancement Note {maturity_years:.1f}Y",
        "premium_collected_pct": round(put_premium / spot * 100, 3),
        "tbill_yield_pct": round(tbill_yield * 100, 3),
        "total_yield_pct": round(total_yield_pct, 3),
        "annualised_yield_pct": round(annualised_yield, 3),
        "break_even": round(break_even, 4),
        "break_even_pct_of_spot": round(break_even / spot * 100, 2),
        "max_loss_pct": round(max_loss_pct, 2),
        "strike": K,
        "put_delta": round(bs.greeks(spot, K, maturity_years, r, sigma, "put")["delta"], 4),
        "notional": notional,
    }

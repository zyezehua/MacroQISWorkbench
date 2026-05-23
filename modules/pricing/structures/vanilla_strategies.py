"""
Equity vanilla option strategies. Each function returns a standardised result dict.
Prices in same currency as spot (e.g. USD). Greeks are net across legs.
"""
from modules.pricing import black_scholes as bs


def _leg(S, K, T, r, sigma, opt_type, qty):
    p = bs.price(S, K, T, r, sigma, opt_type)
    g = bs.greeks(S, K, T, r, sigma, opt_type)
    return p * qty, {k: v * qty for k, v in g.items()}


def _net(legs):
    net_price = sum(p for p, _ in legs)
    net_greeks = {}
    for _, g in legs:
        for k, v in g.items():
            net_greeks[k] = net_greeks.get(k, 0) + v
    return net_price, {k: round(v, 4) for k, v in net_greeks.items()}


def _result(name, S, K, T, net_price, net_greeks, legs_desc):
    return {
        "product": name,
        "spot": S,
        "net_premium": round(net_price, 4),
        "net_premium_pct": round(net_price / S * 100, 3),
        "break_even": _break_even(S, net_price, net_greeks.get("delta", 0)),
        "legs": legs_desc,
        **{f"net_{k}": v for k, v in net_greeks.items()},
    }


def _break_even(S, premium, delta):
    if abs(delta) < 1e-6:
        return None
    return round(S + premium / delta, 4)


# ── Individual legs ────────────────────────────────────────────────────────────

def call(S, K, T, r, sigma):
    legs = [_leg(S, K, T, r, sigma, "call", +1)]
    p, g = _net(legs)
    return _result(f"Long Call K={K}", S, K, T, p, g, [f"Long Call @ {K}"])


def put(S, K, T, r, sigma):
    legs = [_leg(S, K, T, r, sigma, "put", +1)]
    p, g = _net(legs)
    return _result(f"Long Put K={K}", S, K, T, p, g, [f"Long Put @ {K}"])


# ── Spreads ────────────────────────────────────────────────────────────────────

def call_spread(S, K_lo, K_hi, T, r, sigma_lo, sigma_hi=None):
    if sigma_hi is None:
        sigma_hi = sigma_lo
    legs = [
        _leg(S, K_lo, T, r, sigma_lo, "call", +1),
        _leg(S, K_hi, T, r, sigma_hi, "call", -1),
    ]
    p, g = _net(legs)
    max_profit = (K_hi - K_lo) - p
    return {
        **_result(f"Call Spread {K_lo}/{K_hi}", S, K_lo, T, p, g,
                  [f"Long Call @ {K_lo}", f"Short Call @ {K_hi}"]),
        "max_profit": round(max_profit, 4),
        "max_loss": round(p, 4),
        "risk_reward": round(max_profit / (p + 1e-8), 2),
    }


def put_spread(S, K_hi, K_lo, T, r, sigma_hi, sigma_lo=None):
    if sigma_lo is None:
        sigma_lo = sigma_hi
    legs = [
        _leg(S, K_hi, T, r, sigma_hi, "put", +1),
        _leg(S, K_lo, T, r, sigma_lo, "put", -1),
    ]
    p, g = _net(legs)
    max_profit = (K_hi - K_lo) - p
    return {
        **_result(f"Put Spread {K_hi}/{K_lo}", S, K_hi, T, p, g,
                  [f"Long Put @ {K_hi}", f"Short Put @ {K_lo}"]),
        "max_profit": round(max_profit, 4),
        "max_loss": round(p, 4),
        "risk_reward": round(max_profit / (p + 1e-8), 2),
    }


# ── Vol strategies ─────────────────────────────────────────────────────────────

def straddle(S, K, T, r, sigma):
    legs = [
        _leg(S, K, T, r, sigma, "call", +1),
        _leg(S, K, T, r, sigma, "put", +1),
    ]
    p, g = _net(legs)
    be_up   = round(K + p, 4)
    be_down = round(K - p, 4)
    return {
        **_result(f"Straddle K={K}", S, K, T, p, g,
                  [f"Long Call @ {K}", f"Long Put @ {K}"]),
        "break_even_up": be_up,
        "break_even_down": be_down,
        "required_move_pct": round(p / S * 100, 2),
    }


def strangle(S, K_put, K_call, T, r, sigma_put, sigma_call=None):
    if sigma_call is None:
        sigma_call = sigma_put
    legs = [
        _leg(S, K_put,  T, r, sigma_put,  "put",  +1),
        _leg(S, K_call, T, r, sigma_call, "call", +1),
    ]
    p, g = _net(legs)
    return {
        **_result(f"Strangle {K_put}/{K_call}", S, K_put, T, p, g,
                  [f"Long Put @ {K_put}", f"Long Call @ {K_call}"]),
        "break_even_up": round(K_call + p, 4),
        "break_even_down": round(K_put - p, 4),
    }


# ── Carry strategies ───────────────────────────────────────────────────────────

def risk_reversal(S, K_put, K_call, T, r, sigma_put, sigma_call=None):
    """Buy call, sell put (bullish skew trade)."""
    if sigma_call is None:
        sigma_call = sigma_put
    legs = [
        _leg(S, K_put,  T, r, sigma_put,  "put",  -1),
        _leg(S, K_call, T, r, sigma_call, "call", +1),
    ]
    p, g = _net(legs)
    return _result(f"Risk Reversal {K_put}/{K_call}", S, K_put, T, p, g,
                   [f"Short Put @ {K_put}", f"Long Call @ {K_call}"])


def covered_call(S, K, T, r, sigma):
    """Long underlying + short call (yield enhancement)."""
    short_call_p = bs.price(S, K, T, r, sigma, "call")
    short_call_g = bs.greeks(S, K, T, r, sigma, "call")
    net_delta = 1.0 - short_call_g["delta"]
    annualised_yield = short_call_p / S * (1 / T) * 100 if T > 0 else 0
    return {
        "product": f"Covered Call K={K}",
        "spot": S,
        "call_premium_collected": round(short_call_p, 4),
        "premium_pct": round(short_call_p / S * 100, 3),
        "annualised_yield_pct": round(annualised_yield, 2),
        "net_delta": round(net_delta, 4),
        "upside_cap": K,
        "downside_protection_pct": round(short_call_p / S * 100, 3),
        "net_vega": round(-short_call_g["vega"], 4),
        "net_theta": round(-short_call_g["theta"], 4),
        "legs": [f"Long Stock @ {S}", f"Short Call @ {K}"],
    }


def collar(S, K_put, K_call, T, r, sigma_put, sigma_call=None):
    """Long put + short call + long underlying."""
    if sigma_call is None:
        sigma_call = sigma_put
    put_cost  = bs.price(S, K_put,  T, r, sigma_put,  "put")
    call_prem = bs.price(S, K_call, T, r, sigma_call, "call")
    net_cost  = put_cost - call_prem
    return {
        "product": f"Collar {K_put}/{K_call}",
        "spot": S,
        "net_cost": round(net_cost, 4),
        "net_cost_pct": round(net_cost / S * 100, 3),
        "downside_floor": K_put,
        "upside_cap": K_call,
        "protected_range_pct": round((K_call - K_put) / S * 100, 2),
        "legs": [f"Long Stock @ {S}", f"Long Put @ {K_put}", f"Short Call @ {K_call}"],
    }

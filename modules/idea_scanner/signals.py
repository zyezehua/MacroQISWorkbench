"""
Maps macro regime to directional trade signals for each product class.
Signals are opinionated but overridable — structurer review is always expected.
"""

from modules.idea_scanner.macro_regime import MacroRegime


def generate_signals(regime=None, snapshot=None):
    """
    Returns dict of:
      { product_id: { "signal": str, "rationale": str, "strength": float [0,1] } }
    """
    if regime is None:
        regime = MacroRegime(snapshot).full_regime()

    curve = regime["yield_curve"]
    vol = regime["vol_level"]
    ts = regime["vol_term_structure"]
    rate_lvl = regime["rate_level"]
    rv_iv = regime["rv_iv_rel"]
    vix = regime["vix"]
    spread = regime["curve_spread_2s10s"]

    signals = {}

    # ── RATE_SWPN: Rate Swaptions ─────────────────────────────────────────────
    if curve in ("deeply_inverted", "mildly_inverted") and rate_lvl in ("high", "very_high"):
        signals["RATE_SWPN"] = {
            "signal": "receiver_swaption",
            "rationale": f"Inverted curve ({spread:+.2f}%) + high rates ({regime['us10y']:.2f}%) "
                         f"→ rate cut cycle risk; receiver swaption captures rally.",
            "strength": 0.82,
        }
    elif curve == "steep" and vol in ("elevated", "spike"):
        signals["RATE_SWPN"] = {
            "signal": "payer_swaption_spread",
            "rationale": "Steep curve + elevated rate vol → sell elevated payer vol via spread.",
            "strength": 0.65,
        }
    elif curve in ("flat",) and vol in ("normal", "low", "suppressed"):
        signals["RATE_SWPN"] = {
            "signal": "straddle_on_pivot",
            "rationale": "Flat curve with low vol → long gamma via swaption straddle ahead of policy pivots.",
            "strength": 0.58,
        }
    else:
        signals["RATE_SWPN"] = {
            "signal": "neutral",
            "rationale": "No dominant rate directionality; monitor for curve shape shift.",
            "strength": 0.35,
        }

    # ── RATE_BFO: Bond Futures Options ────────────────────────────────────────
    if curve in ("deeply_inverted", "mildly_inverted") and rate_lvl in ("high", "very_high"):
        signals["RATE_BFO"] = {
            "signal": "long_bond_call",
            "rationale": "High rates + inversion → duration longs via bond futures call as rates normalise.",
            "strength": 0.75,
        }
    elif vol in ("elevated", "spike"):
        signals["RATE_BFO"] = {
            "signal": "sell_rate_vol_strangle",
            "rationale": "Elevated rate vol → sell OTM strangle on bond futures, collect premium.",
            "strength": 0.60,
        }
    else:
        signals["RATE_BFO"] = {
            "signal": "neutral",
            "rationale": "Stable rate environment; limited directional edge.",
            "strength": 0.38,
        }

    # ── EQ_VANILLA: Equity Vanilla Strategies ─────────────────────────────────
    if vol in ("suppressed", "low"):
        signals["EQ_VANILLA"] = {
            "signal": "long_vol_spread",
            "rationale": f"VIX at {vix:.1f} (suppressed) → cheap vol; buy call spread or straddle.",
            "strength": 0.78,
        }
    elif vol in ("spike",):
        signals["EQ_VANILLA"] = {
            "signal": "put_spread_sell",
            "rationale": f"VIX spike ({vix:.1f}) → sell elevated put spread; collect rich premium.",
            "strength": 0.70,
        }
    elif rv_iv == "iv_rich":
        signals["EQ_VANILLA"] = {
            "signal": "covered_overwrite",
            "rationale": "IV trades above realised vol → yield enhancement via covered call overwrite.",
            "strength": 0.65,
        }
    else:
        signals["EQ_VANILLA"] = {
            "signal": "risk_reversal_carry",
            "rationale": "Normal vol environment → skew carry via risk reversal (sell put / buy call).",
            "strength": 0.52,
        }

    # ── VOL_PROD: VIX strategies, var swaps ──────────────────────────────────
    if ts == "contango" and vol in ("suppressed", "low", "normal"):
        signals["VOL_PROD"] = {
            "signal": "short_vix_roll_down",
            "rationale": "VIX contango + low spot vol → short VIX futures; capture roll-down carry.",
            "strength": 0.72,
        }
    elif ts == "backwardation":
        signals["VOL_PROD"] = {
            "signal": "long_vol_hedge",
            "rationale": "VIX backwardation → stress signal; long vol as tail hedge.",
            "strength": 0.68,
        }
    elif rv_iv == "rv_rich":
        signals["VOL_PROD"] = {
            "signal": "short_var_swap",
            "rationale": "Realised vol exceeds implied → sell variance; collect vol premium.",
            "strength": 0.60,
        }
    else:
        signals["VOL_PROD"] = {
            "signal": "neutral",
            "rationale": "Flat vol term structure; no dominant carry signal.",
            "strength": 0.38,
        }

    # ── STRUCT_AC: Autocall / Structured Notes ────────────────────────────────
    if vol in ("elevated", "spike"):
        signals["STRUCT_AC"] = {
            "signal": "autocall_coupon_rich",
            "rationale": f"VIX {vix:.1f} → elevated vol richens autocall coupons significantly.",
            "strength": 0.80,
        }
    elif vol in ("suppressed", "low") and rate_lvl in ("high", "very_high", "moderate"):
        signals["STRUCT_AC"] = {
            "signal": "capital_protection_note",
            "rationale": "Low vol + reasonable rates → capital-protected structured note with rate kicker.",
            "strength": 0.62,
        }
    else:
        signals["STRUCT_AC"] = {
            "signal": "moderate_autocall",
            "rationale": "Moderate vol → selective autocall; screen carefully on coupon vs barrier.",
            "strength": 0.48,
        }

    # ── SYS_STRAT: Systematic / carry-momentum strategies ────────────────────
    if abs(spread) > 0.60:
        signals["SYS_STRAT"] = {
            "signal": "rates_carry_rolldown",
            "rationale": f"Significant curve slope ({spread:+.2f}%) → rates carry / roll-down strategy.",
            "strength": 0.68,
        }
    elif vol in ("suppressed", "low") and ts == "contango":
        signals["SYS_STRAT"] = {
            "signal": "vol_carry_systematic",
            "rationale": "Low vol + contango → systematic short-vol carry basket.",
            "strength": 0.62,
        }
    else:
        signals["SYS_STRAT"] = {
            "signal": "cross_asset_momentum",
            "rationale": "Mixed regime → cross-asset momentum overlay on rates + equity.",
            "strength": 0.50,
        }

    return signals

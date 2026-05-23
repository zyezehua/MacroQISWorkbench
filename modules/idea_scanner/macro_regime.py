class MacroRegime:
    """
    Classifies current macro/market regime from a market snapshot dict.
    All thresholds are calibrated for indicative PoC use — not trade-level.
    """

    def __init__(self, snapshot):
        self.s = snapshot

    def yield_curve_regime(self):
        """Returns (label, 2s10s_spread_pct). Falls back to 3m10y if 2s10s unavailable."""
        spread = self.s.get("2s10s") or self.s.get("3m10y") or 0.0
        if spread > 0.75:
            label = "steep"
        elif spread > 0.10:
            label = "flat"
        elif spread > -0.25:
            label = "mildly_inverted"
        else:
            label = "deeply_inverted"
        return label, round(spread, 3)

    def vol_regime(self):
        """Returns (label, vix_level)."""
        vix = self.s.get("VIX", 20.0) or 20.0
        if vix < 13:
            label = "suppressed"
        elif vix < 18:
            label = "low"
        elif vix < 25:
            label = "normal"
        elif vix < 35:
            label = "elevated"
        else:
            label = "spike"
        return label, round(vix, 2)

    def vol_term_structure(self):
        """Returns (label, slope) where slope = (VIX3M - VIX) / VIX."""
        vix = self.s.get("VIX", 20.0) or 20.0
        vix3m = self.s.get("VIX3M")
        if not vix3m or vix == 0:
            return "unknown", 0.0
        slope = (vix3m - vix) / vix
        if slope > 0.08:
            label = "contango"
        elif slope > -0.05:
            label = "flat"
        else:
            label = "backwardation"
        return label, round(slope, 4)

    def rate_level_regime(self):
        """Returns (label, us10y_pct)."""
        us10y = self.s.get("US10Y", 4.0) or 4.0
        if us10y > 5.0:
            label = "very_high"
        elif us10y > 3.5:
            label = "high"
        elif us10y > 2.0:
            label = "moderate"
        else:
            label = "low"
        return label, round(us10y, 3)

    def realized_vs_implied(self):
        """Rough RV/IV relationship using 1M realised vol vs VIX."""
        rv_21d = self.s.get("rv_21d")
        vix = self.s.get("VIX", 20.0) or 20.0
        vix_decimal = vix / 100.0
        if rv_21d is None:
            return "unknown", None
        ratio = rv_21d / vix_decimal if vix_decimal > 0 else 1.0
        if ratio > 1.15:
            label = "rv_rich"       # realized > implied → vol selling looks rich
        elif ratio < 0.85:
            label = "iv_rich"       # implied > realized → vol buying looks cheap
        else:
            label = "fairly_priced"
        return label, round(ratio, 3)

    def full_regime(self):
        curve_lbl, curve_spread = self.yield_curve_regime()
        vol_lbl, vix = self.vol_regime()
        ts_lbl, ts_slope = self.vol_term_structure()
        rate_lbl, us10y = self.rate_level_regime()
        rv_iv_lbl, rv_iv_ratio = self.realized_vs_implied()

        return {
            "yield_curve": curve_lbl,
            "curve_spread_2s10s": curve_spread,
            "vol_level": vol_lbl,
            "vix": vix,
            "vol_term_structure": ts_lbl,
            "ts_slope": ts_slope,
            "rate_level": rate_lbl,
            "us10y": us10y,
            "rv_iv_rel": rv_iv_lbl,
            "rv_iv_ratio": rv_iv_ratio,
        }

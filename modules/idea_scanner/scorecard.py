import pandas as pd
from config import SCORECARD_DIMENSIONS, PRODUCTS

# Static product characteristics — hedgeability and liquidity are structural facts,
# not market-dependent. Client suitability reflects typical regulatory / mandate fit.
PRODUCT_STATIC = {
    "RATE_SWPN": {
        "hedgeability": 8.5,
        "liquidity_base": 8.0,
        "client_suitability": {"Private Bank": 6.0, "Pension Fund": 9.0, "Insurance": 9.0},
        "xva_drag_base": "medium",
        "capacity_note": "High dealer capacity in rates; good warehouse-ability.",
    },
    "RATE_BFO": {
        "hedgeability": 8.0,
        "liquidity_base": 7.5,
        "client_suitability": {"Private Bank": 5.0, "Pension Fund": 8.0, "Insurance": 7.0},
        "xva_drag_base": "low",
        "capacity_note": "Exchange-listed — minimal counterparty xVA.",
    },
    "EQ_VANILLA": {
        "hedgeability": 7.5,
        "liquidity_base": 7.0,
        "client_suitability": {"Private Bank": 8.5, "Pension Fund": 7.0, "Insurance": 6.0},
        "xva_drag_base": "medium",
        "capacity_note": "Capacity varies by underlying; SPX/SX5E deep.",
    },
    "VOL_PROD": {
        "hedgeability": 5.5,
        "liquidity_base": 6.0,
        "client_suitability": {"Private Bank": 5.0, "Pension Fund": 7.0, "Insurance": 5.5},
        "xva_drag_base": "medium",
        "capacity_note": "Var swap capacity manageable; VIX futures liquid.",
    },
    "STRUCT_AC": {
        "hedgeability": 5.0,
        "liquidity_base": 4.5,
        "client_suitability": {"Private Bank": 9.0, "Pension Fund": 6.0, "Insurance": 7.5},
        "xva_drag_base": "high",
        "capacity_note": "Path-dependent; requires delta + barrier warehousing.",
    },
    "SYS_STRAT": {
        "hedgeability": 7.0,
        "liquidity_base": 6.5,
        "client_suitability": {"Private Bank": 6.0, "Pension Fund": 8.5, "Insurance": 7.0},
        "xva_drag_base": "low",
        "capacity_note": "Rule-based and scalable; low structural xVA.",
    },
}

_XVA_SCORE = {"low": 8.5, "medium": 5.5, "high": 2.5}


def _vol_env_score(prod_id, vix):
    """How favourable is the current vol level for this product (0–10)."""
    if prod_id == "STRUCT_AC":
        # Autocall thrives on high vol (richer coupons)
        return min(10.0, max(2.0, 2.0 + (vix - 12) * 0.32))
    if prod_id == "VOL_PROD":
        # Short-vol products prefer low/normal vol
        return max(1.0, 10.0 - max(0, vix - 13) * 0.28)
    if prod_id in ("RATE_SWPN", "RATE_BFO"):
        # Rate vol products — use equity vol as rough proxy
        return min(9.0, 4.0 + (vix - 15) * 0.18)
    # EQ_VANILLA and SYS_STRAT are flexible
    return 6.0


def build_scorecard(signals, snapshot, client_type="Pension Fund", weights=None, overrides=None):
    """
    Parameters
    ----------
    signals  : output of idea_scanner.signals.generate_signals()
    snapshot : market snapshot dict
    client_type : "Private Bank" | "Pension Fund" | "Insurance"
    weights  : {dimension: weight} — defaults to SCORECARD_DIMENSIONS
    overrides: {product_id: {dimension: score}} — manual override per cell

    Returns
    -------
    pd.DataFrame sorted by total_score descending
    """
    if weights is None:
        weights = SCORECARD_DIMENSIONS.copy()
    if overrides is None:
        overrides = {}

    vix = snapshot.get("VIX", 20.0) or 20.0
    rows = []

    for prod_id, static in PRODUCT_STATIC.items():
        sig = signals.get(prod_id, {})
        strength = sig.get("strength", 0.5)

        scores = {
            "macro_alignment": round(strength * 10, 2),
            "vol_environment": round(_vol_env_score(prod_id, vix), 2),
            "liquidity": static["liquidity_base"],
            "hedgeability": static["hedgeability"],
            "client_suitability": static["client_suitability"].get(client_type, 6.0),
            "xva_drag": _XVA_SCORE[static["xva_drag_base"]],
        }

        if prod_id in overrides:
            scores.update(overrides[prod_id])

        total_w = sum(weights.get(dim, 0) for dim in scores)
        total = sum(scores[dim] * weights.get(dim, 0) for dim in scores) / total_w if total_w > 0 else 0

        rows.append({
            "product_id": prod_id,
            "Product": PRODUCTS[prod_id],
            "Signal": sig.get("signal", "neutral"),
            "Rationale": sig.get("rationale", ""),
            **scores,
            "Total Score": round(total, 2),
            "xVA Flag": static["xva_drag_base"],
            "Capacity Note": static["capacity_note"],
        })

    df = (
        pd.DataFrame(rows)
        .sort_values("Total Score", ascending=False)
        .reset_index(drop=True)
    )
    df.index += 1  # rank starts at 1
    return df

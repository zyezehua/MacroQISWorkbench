from data.market_snapshot import get_market_snapshot
from modules.idea_scanner.macro_regime import MacroRegime
from modules.idea_scanner.signals import generate_signals
from modules.idea_scanner.scorecard import build_scorecard
from modules.idea_scanner.filters import compliance_flag, liquidity_flag, capacity_flag


def run_scan(client_type="Pension Fund", weights=None, overrides=None, snapshot=None):
    """
    Main Idea Scanner entry point.

    Parameters
    ----------
    client_type : "Private Bank" | "Pension Fund" | "Insurance"
    weights     : {dimension: weight} for scorecard — None uses defaults
    overrides   : {product_id: {dimension: score}} for manual cell overrides
    snapshot    : pre-fetched market snapshot dict (None = fetch live)

    Returns
    -------
    {
        "snapshot"  : dict,
        "regime"    : dict,
        "signals"   : dict,
        "scorecard" : pd.DataFrame,
    }
    """
    if snapshot is None:
        snapshot = get_market_snapshot()

    regime = MacroRegime(snapshot).full_regime()
    signals = generate_signals(regime=regime, snapshot=snapshot)
    scorecard = build_scorecard(
        signals, snapshot,
        client_type=client_type,
        weights=weights,
        overrides=overrides,
    )

    scorecard["Compliance"] = scorecard["product_id"].apply(
        lambda pid: compliance_flag(pid, client_type)
    )
    scorecard["Liq Flag"] = scorecard["product_id"].apply(
        lambda pid: liquidity_flag(pid, snapshot)
    )
    scorecard["Capacity"] = scorecard["product_id"].apply(
        lambda pid: capacity_flag(pid, snapshot)
    )

    return {
        "snapshot": snapshot,
        "regime": regime,
        "signals": signals,
        "scorecard": scorecard,
    }

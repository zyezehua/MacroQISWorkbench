from data.fetchers.equity_fetcher import (
    get_current_spot,
    get_vix_term_structure,
    get_historical_vol,
)
from data.fetchers.rates_fetcher import get_current_rates, get_curve_spreads
from data.fetchers.macro_fetcher import get_latest_macro
from config import EQUITY_TICKERS


def get_market_snapshot(overrides=None):
    """
    Aggregate single-call market snapshot consumed by Idea Scanner.
    overrides: dict of {key: value} for manual user overrides.
    """
    snapshot = {}

    for name, sym in EQUITY_TICKERS.items():
        val = get_current_spot(sym)
        if val is not None:
            snapshot[f"spot_{name}"] = val

    vix = get_vix_term_structure()
    snapshot.update({k: v for k, v in vix.items() if v is not None})

    rv = get_historical_vol("^GSPC")
    snapshot.update(rv)

    rates = get_current_rates()
    snapshot.update(rates)

    spreads = get_curve_spreads()
    snapshot.update(spreads)

    macro = get_latest_macro()
    snapshot.update(macro)

    if overrides:
        snapshot.update(overrides)

    return snapshot

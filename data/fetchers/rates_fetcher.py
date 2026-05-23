import os
import pandas as pd
import yfinance as yf
from data.cache import get_cache, set_cache
from config import RATES_YF_TICKERS, FRED_RATES_SERIES


def _fred_client():
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from fredapi import Fred
        return Fred(api_key=api_key)
    except Exception:
        return None


def get_yield_curve(period_start="2020-01-01"):
    key = f"yield_curve_{period_start}"
    cached = get_cache(key)
    if cached is not None:
        return cached

    fred = _fred_client()
    if fred:
        data = {}
        for name, sid in FRED_RATES_SERIES.items():
            try:
                data[name] = fred.get_series(sid, observation_start=period_start)
            except Exception:
                pass
        df = pd.DataFrame(data).dropna(how="all")
    else:
        # yfinance fallback — note ^IRX is quoted as annualised %
        syms = list(RATES_YF_TICKERS.values())
        raw = yf.download(syms, start=period_start, auto_adjust=True, progress=False)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        df = closes.rename(columns={v: k for k, v in RATES_YF_TICKERS.items()})
        # yfinance rate tickers are already in % (e.g. 4.25 = 4.25%)
        df = df.dropna(how="all")

    set_cache(key, df)
    return df


def get_current_rates():
    df = get_yield_curve()
    if df.empty:
        return {}
    return df.ffill().iloc[-1].dropna().to_dict()


def get_curve_spreads():
    rates = get_current_rates()
    if not rates:
        return {}

    def _spread(key_long, key_short):
        long = rates.get(key_long)
        short = rates.get(key_short)
        if long is None or short is None:
            return None
        return long - short

    spreads = {
        "2s10s": _spread("US10Y", "US2Y"),
        "5s30s": _spread("US30Y", "US5Y"),
        "2s30s": _spread("US30Y", "US2Y"),
        "3m10y": _spread("US10Y", "US3M"),
    }
    # Drop None values so snapshot stays clean
    return {k: v for k, v in spreads.items() if v is not None}


def get_yield_curve_history(period_start="2018-01-01"):
    """Full historical yield curve for backtest / scenario analysis."""
    return get_yield_curve(period_start=period_start)

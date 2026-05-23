import os
import pandas as pd
from data.cache import get_cache, set_cache
from config import FRED_MACRO_SERIES


def _fred_client():
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from fredapi import Fred
        return Fred(api_key=api_key)
    except Exception:
        return None


def get_macro_indicators(period_start="2018-01-01"):
    key = f"macro_{period_start}"
    cached = get_cache(key)
    if cached is not None:
        return cached

    fred = _fred_client()
    if not fred:
        return pd.DataFrame()

    data = {}
    for name, sid in FRED_MACRO_SERIES.items():
        try:
            s = fred.get_series(sid, observation_start=period_start)
            if name in ("CPI_YOY", "CORE_CPI"):
                s = s.pct_change(12) * 100
            data[name] = s
        except Exception:
            pass

    df = pd.DataFrame(data).dropna(how="all")
    set_cache(key, df)
    return df


def get_latest_macro():
    df = get_macro_indicators()
    if df.empty:
        return {}
    return df.ffill().iloc[-1].dropna().to_dict()

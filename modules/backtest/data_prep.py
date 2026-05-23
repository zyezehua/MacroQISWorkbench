"""
Historical data preparation for backtesting.
Returns aligned daily series: spot, implied_vol_proxy, risk_free_rate.
Vol proxy: VIX / 100 (annualised ATM implied vol proxy for SPX).
Rate proxy: ^IRX (13-week T-bill, annualised %).
"""
import numpy as np
import pandas as pd
import yfinance as yf
from data.cache import get_cache, set_cache


_UNDERLYING_MAP = {
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "SX5E": "^STOXX50E",
}

_VOL_PROXY_MAP = {
    "SPX": "^VIX",
    "NDX": "^VIX",     # use VIX as proxy; VOLQ rarely has long history
    "SX5E": "^VIX",   # use VIX as proxy; VSTOXX not on yfinance
}

_RATE_TICKER = "^IRX"   # 13-week T-bill, annualised %


def load_backtest_data(underlying="SPX", start="2015-01-01", end=None):
    """
    Returns pd.DataFrame with columns:
      spot, vol, rate (all decimal)
    indexed by business day.
    """
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    key = f"bt_data_{underlying}_{start}_{end}"
    cached = get_cache(key)
    if cached is not None:
        return cached

    spot_sym = _UNDERLYING_MAP.get(underlying, underlying)
    vol_sym  = _VOL_PROXY_MAP.get(underlying, "^VIX")
    tickers  = list({spot_sym, vol_sym, _RATE_TICKER})

    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw

    df = pd.DataFrame(index=closes.index)
    df["spot"] = closes.get(spot_sym, pd.Series(dtype=float))
    df["vol"]  = closes.get(vol_sym,  pd.Series(dtype=float)) / 100.0  # VIX → decimal
    df["rate"] = closes.get(_RATE_TICKER, pd.Series(dtype=float)) / 100.0

    # Forward-fill rates and vol (they have gaps on holidays etc.)
    df = df.ffill().dropna(subset=["spot"])
    df["vol"]  = df["vol"].fillna(0.20)
    df["rate"] = df["rate"].fillna(0.04)

    # Add log-returns and rolling realised vol
    df["log_ret"] = np.log(df["spot"] / df["spot"].shift(1))
    df["rv_21d"]  = df["log_ret"].rolling(21).std() * np.sqrt(252)
    df["rv_63d"]  = df["log_ret"].rolling(63).std() * np.sqrt(252)

    set_cache(key, df)
    return df

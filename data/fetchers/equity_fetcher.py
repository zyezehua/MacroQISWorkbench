import numpy as np
import pandas as pd
import yfinance as yf
from data.cache import get_cache, set_cache
from config import EQUITY_TICKERS, VIX_TICKERS


def get_spot_prices(tickers=None, period="1y"):
    if tickers is None:
        tickers = list(EQUITY_TICKERS.values()) + list(VIX_TICKERS.values())
    key = f"spots_{'_'.join(sorted(tickers))}_{period}"
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)
        data = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        set_cache(key, data)
        return data
    except Exception:
        return pd.DataFrame()


def get_current_spot(ticker_symbol):
    """Return latest spot price. Falls back to last close from history on weekends/holidays."""
    key = f"spot_{ticker_symbol}"
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        info = yf.Ticker(ticker_symbol).fast_info
        price = float(info.get("last_price") or info.get("regularMarketPrice") or 0)
        if price > 0:
            set_cache(key, price)
            return price
    except Exception:
        pass
    try:
        hist = yf.download(ticker_symbol, period="5d", auto_adjust=True, progress=False)
        if not hist.empty:
            price = float(hist["Close"].squeeze().dropna().iloc[-1])
            set_cache(key, price)
            return price
    except Exception:
        pass
    return None


def get_last_trading_day(reference_symbol="^GSPC"):
    """Date of the most recent available close for the reference index.

    Used to stamp the market snapshot with an honest "as of" date so weekend /
    holiday runs show the last business day rather than implying live data.
    Returns a pandas.Timestamp (date) or None if unavailable.
    """
    key = f"last_trading_day_{reference_symbol}"
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        hist = yf.download(reference_symbol, period="5d", auto_adjust=True, progress=False)
        idx = hist["Close"].squeeze().dropna().index
        if len(idx) > 0:
            as_of = pd.Timestamp(idx[-1]).normalize()
            set_cache(key, as_of)
            return as_of
    except Exception:
        pass
    return None


def get_vix_term_structure():
    key = "vix_ts"
    cached = get_cache(key)
    if cached is not None:
        return cached
    result = {}
    for name, sym in VIX_TICKERS.items():
        val = get_current_spot(sym)
        result[name] = val
    set_cache(key, result)
    return result


def get_options_chain(underlying_symbol, max_expiries=6):
    key = f"options_{underlying_symbol}"
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        ticker = yf.Ticker(underlying_symbol)
        expiries = ticker.options[:max_expiries]
        chain = {}
        for exp in expiries:
            opt = ticker.option_chain(exp)
            chain[exp] = {"calls": opt.calls, "puts": opt.puts}
        set_cache(key, chain)
        return chain
    except Exception:
        return {}


def get_historical_vol(ticker_symbol, windows=(21, 63, 126, 252), period="2y"):
    key = f"hist_vol_{ticker_symbol}_{period}"
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        raw = yf.download(ticker_symbol, period=period, auto_adjust=True, progress=False)
        prices = raw["Close"].squeeze()
        log_rets = np.log(prices / prices.shift(1)).dropna()
        result = {
            f"rv_{w}d": float(log_rets.rolling(w).std().iloc[-1] * np.sqrt(252))
            for w in windows
            if len(log_rets) >= w
        }
        set_cache(key, result)
        return result
    except Exception:
        return {}


def get_equity_returns(ticker_symbol, period="1y"):
    key = f"returns_{ticker_symbol}_{period}"
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        raw = yf.download(ticker_symbol, period=period, auto_adjust=True, progress=False)
        prices = raw["Close"].squeeze()
        rets = prices.pct_change().dropna()
        set_cache(key, rets)
        return rets
    except Exception:
        return pd.Series(dtype=float)

"""Performance metrics for backtest results."""
import numpy as np
import pandas as pd


def compute_metrics(trade_df, pnl_col="pnl", annualise_factor=252 / 21):
    """
    Parameters
    ----------
    trade_df        : one row per trade with 'pnl' column
    pnl_col         : column name for per-trade P&L
    annualise_factor: trades per year (default: 252/21 ≈ 12 monthly trades)

    Returns
    -------
    dict of performance statistics
    """
    if trade_df.empty or pnl_col not in trade_df.columns:
        return {}

    pnl = trade_df[pnl_col].dropna()
    if len(pnl) == 0:
        return {}

    n = len(pnl)
    mean_pnl  = pnl.mean()
    std_pnl   = pnl.std(ddof=1)
    downside   = pnl[pnl < 0].std(ddof=1) if (pnl < 0).any() else 1e-10
    cum_pnl    = pnl.cumsum()
    rolling_max = cum_pnl.cummax()
    drawdown    = cum_pnl - rolling_max
    max_dd      = drawdown.min()

    sharpe   = mean_pnl / std_pnl * np.sqrt(annualise_factor) if std_pnl > 1e-10 else 0
    sortino  = mean_pnl / downside * np.sqrt(annualise_factor) if downside > 1e-10 else 0
    calmar   = (mean_pnl * annualise_factor) / abs(max_dd) if abs(max_dd) > 1e-10 else 0
    hit_rate = (pnl > 0).mean()

    # Win/loss ratio
    wins  = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    avg_win  = wins.mean()  if len(wins)   > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0
    pl_ratio = abs(avg_win / avg_loss) if abs(avg_loss) > 1e-10 else np.nan

    # Kelly fraction (simplified)
    p = hit_rate
    q = 1 - p
    b = abs(avg_win / avg_loss) if abs(avg_loss) > 1e-10 else 1
    kelly = (p * b - q) / b if b > 0 else 0

    return {
        "n_trades": n,
        "total_pnl": round(float(pnl.sum()), 6),
        "mean_pnl_per_trade": round(float(mean_pnl), 6),
        "std_pnl": round(float(std_pnl), 6),
        "sharpe_ratio": round(float(sharpe), 3),
        "sortino_ratio": round(float(sortino), 3),
        "calmar_ratio": round(float(calmar), 3),
        "hit_rate_pct": round(float(hit_rate) * 100, 1),
        "avg_win": round(float(avg_win), 6),
        "avg_loss": round(float(avg_loss), 6),
        "pl_ratio": round(float(pl_ratio), 2) if not np.isnan(pl_ratio) else None,
        "kelly_fraction_pct": round(float(kelly) * 100, 1),
        "max_drawdown": round(float(max_dd), 6),
        "best_trade": round(float(pnl.max()), 6),
        "worst_trade": round(float(pnl.min()), 6),
    }


def cumulative_pnl(trade_df, pnl_col="pnl", date_col="entry_date"):
    """Return pd.Series of cumulative P&L indexed by entry_date."""
    if trade_df.empty:
        return pd.Series(dtype=float)
    df = trade_df[[date_col, pnl_col]].dropna().set_index(date_col)
    return df[pnl_col].cumsum()


def rolling_sharpe(trade_df, window=12, pnl_col="pnl"):
    """Rolling annualised Sharpe over trailing window of trades."""
    pnl = trade_df[pnl_col].dropna()
    mean_r = pnl.rolling(window).mean()
    std_r  = pnl.rolling(window).std(ddof=1)
    return (mean_r / std_r * np.sqrt(12)).rename("rolling_sharpe")


def underwater_series(trade_df, pnl_col="pnl", date_col="entry_date"):
    """Drawdown from peak as a series indexed by entry_date."""
    if trade_df.empty:
        return pd.Series(dtype=float)
    pnl  = trade_df.set_index(date_col)[pnl_col].cumsum()
    peak = pnl.cummax()
    return (pnl - peak).rename("drawdown")

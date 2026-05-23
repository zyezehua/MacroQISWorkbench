import os

PRODUCTS = {
    "RATE_SWPN": "Rate Swaptions",
    "RATE_BFO": "Bond Futures Options",
    "EQ_VANILLA": "Equity Vanilla Strategies",
    "VOL_PROD": "Vol Products",
    "STRUCT_AC": "Autocall / Structured Notes",
    "SYS_STRAT": "Systematic Strategies",
}

SCORECARD_DIMENSIONS = {
    "macro_alignment": 0.25,
    "vol_environment": 0.20,
    "liquidity": 0.20,
    "hedgeability": 0.15,
    "client_suitability": 0.10,
    "xva_drag": 0.10,
}

CLIENT_TYPES = ["Private Bank", "Pension Fund", "Insurance"]

EQUITY_TICKERS = {
    "SPX": "^GSPC",
    "SX5E": "^STOXX50E",
    "NDX": "^NDX",
}

VIX_TICKERS = {
    "VIX": "^VIX",
    "VIX3M": "^VIX3M",
    "VVIX": "^VVIX",
}

# yfinance fallback tickers for rates (no FRED key needed)
RATES_YF_TICKERS = {
    "US3M": "^IRX",
    "US5Y": "^FVX",
    "US10Y": "^TNX",
    "US30Y": "^TYX",
}

FRED_RATES_SERIES = {
    "US3M": "DGS3MO",
    "US2Y": "DGS2",
    "US5Y": "DGS5",
    "US10Y": "DGS10",
    "US30Y": "DGS30",
    "SOFR": "SOFR",
}

FRED_MACRO_SERIES = {
    "CPI_YOY": "CPIAUCSL",
    "CORE_CPI": "CPILFESL",
    "UNEMPLOYMENT": "UNRATE",
    "NONFARM_PAYROLL": "PAYEMS",
}

DATA_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")
CACHE_EXPIRY_HOURS = 4

THEME = {
    "score_high": "#00C853",
    "score_mid": "#FFD600",
    "score_low": "#D50000",
    "flag_green": "#00C853",
    "flag_yellow": "#FFD600",
    "flag_red": "#D50000",
}

"""
Named historical scenario slices for stress-testing.
"""
import pandas as pd

SCENARIOS = {
    "Full History":         (None, None),
    "GFC (2008–2009)":      ("2007-06-01", "2009-06-30"),
    "Post-GFC Recovery":    ("2009-07-01", "2011-12-31"),
    "Low-Vol Bull (2013–2017)": ("2013-01-01", "2017-12-31"),
    "COVID Crash (2020)":   ("2020-01-01", "2020-12-31"),
    "Rate Hike Cycle (2022)": ("2022-01-01", "2023-06-30"),
    "AI Bull Run (2023–2024)": ("2023-01-01", "2024-12-31"),
    "Custom":               (None, None),
}


def slice_data(df, scenario_name, custom_start=None, custom_end=None):
    """Slice a DataFrame to a named scenario date range."""
    if scenario_name == "Custom":
        start, end = custom_start, custom_end
    else:
        start, end = SCENARIOS.get(scenario_name, (None, None))

    df = df.copy()
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    return df


def slice_trades(trade_df, scenario_name, custom_start=None, custom_end=None, date_col="entry_date"):
    """Slice a trade DataFrame to a named scenario."""
    if scenario_name == "Custom":
        start, end = custom_start, custom_end
    else:
        start, end = SCENARIOS.get(scenario_name, (None, None))

    df = trade_df.copy()
    if start:
        df = df[df[date_col] >= pd.Timestamp(start)]
    if end:
        df = df[df[date_col] <= pd.Timestamp(end)]
    return df


def describe_scenario(name):
    """Short context note for each scenario."""
    notes = {
        "GFC (2008–2009)":      "SPX −57% peak-to-trough; VIX peaked at 80. Extreme tail event.",
        "Post-GFC Recovery":    "Fed QE1/2, sustained vol compression, strong equity recovery.",
        "Low-Vol Bull (2013–2017)": "VIX sub-15 for extended periods; vol-selling strategies thrived.",
        "COVID Crash (2020)":   "Fastest bear market in history; VIX > 80; swift V-shaped recovery.",
        "Rate Hike Cycle (2022)": "Fed hiked 525bps; rates/equity correlation flipped negative.",
        "AI Bull Run (2023–2024)": "Mega-cap tech rally; vol suppressed; carry strategies outperformed.",
        "Full History":         "Complete available data history.",
        "Custom":               "User-defined date range.",
    }
    return notes.get(name, "")

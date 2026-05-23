import pandas as pd
import streamlit as st


_DIM_COLS = [
    "macro_alignment",
    "vol_environment",
    "liquidity",
    "hedgeability",
    "client_suitability",
    "xva_drag",
]

_DIM_DISPLAY = {
    "macro_alignment": "Macro",
    "vol_environment": "Vol Env",
    "liquidity": "Liquidity",
    "hedgeability": "Hedgeability",
    "client_suitability": "Client Fit",
    "xva_drag": "xVA",
}

_FLAG_HTML = {
    "green": '<span style="color:#00C853">●</span>',
    "yellow": '<span style="color:#FFD600">●</span>',
    "red": '<span style="color:#D50000">●</span>',
}


def _score_bg(val):
    """Pandas Styler background colour for numeric score cells."""
    if not isinstance(val, (int, float)):
        return ""
    if val >= 7.5:
        return "background-color:#1B5E2088; color:#E8F5E9"
    if val >= 5.5:
        return "background-color:#F57F1788; color:#FFF8E1"
    return "background-color:#B71C1C88; color:#FFEBEE"


def _total_bg(val):
    if not isinstance(val, (int, float)):
        return ""
    if val >= 7.0:
        return "background-color:#00C853; color:#000; font-weight:bold"
    if val >= 5.0:
        return "background-color:#FFD600; color:#000; font-weight:bold"
    return "background-color:#D50000; color:#fff; font-weight:bold"


def render_scorecard(df: pd.DataFrame):
    """Render the full scorecard table with colour-coded cells."""

    display_cols = ["Product", "Signal"] + _DIM_COLS + ["Total Score", "xVA Flag", "Compliance", "Liq Flag"]
    available = [c for c in display_cols if c in df.columns]
    view = df[available].copy().reset_index(drop=True)

    # Rename dimension columns for display
    view = view.rename(columns=_DIM_DISPLAY)

    dim_subset = [_DIM_DISPLAY[d] for d in _DIM_COLS if _DIM_DISPLAY[d] in view.columns]
    styler = view.style

    # pandas 3.0 removed Styler.applymap; use Styler.map
    _apply = styler.map if hasattr(styler, "map") else styler.applymap
    styler = _apply(_score_bg, subset=dim_subset)
    if "Total Score" in view.columns:
        _apply2 = styler.map if hasattr(styler, "map") else styler.applymap
        styler = _apply2(_total_bg, subset=["Total Score"])

    fmt = {col: "{:.1f}" for col in _DIM_DISPLAY.values() if col in view.columns}
    if "Total Score" in view.columns:
        fmt["Total Score"] = "{:.2f}"
    styled = styler.format(fmt)

    st.dataframe(styled, use_container_width=True, height=280)


def render_top_idea(df: pd.DataFrame, signals: dict):
    """Expanded detail panel for the top-ranked idea."""
    if df.empty:
        return
    top = df.iloc[0]
    prod_id = top["product_id"]
    sig = signals.get(prod_id, {})

    st.markdown(f"### 🥇 Top Idea: {top['Product']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Score", f"{top['Total Score']:.2f} / 10")
    c2.metric("Signal", sig.get("signal", "—").replace("_", " ").title())
    c3.metric("xVA Drag", top.get("xVA Flag", "—").capitalize())

    st.info(f"**Rationale:** {sig.get('rationale', '—')}")
    st.caption(f"**Capacity note:** {top.get('Capacity Note', '—')}")

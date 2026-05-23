import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from modules.backtest.data_prep import load_backtest_data
from modules.backtest.engine import BacktestEngine, STRATEGIES
from modules.backtest.metrics import compute_metrics, cumulative_pnl, rolling_sharpe, underwater_series
from modules.backtest.scenarios import SCENARIOS, slice_trades, describe_scenario
from modules.backtest.attribution import payoff_attribution, attribution_summary

st.set_page_config(page_title="Backtest · Macro QIS", page_icon="📈", layout="wide")
st.title("📈 Backtest & Historical Analysis")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Strategy Setup")

    strategy = st.selectbox(
        "Strategy",
        list(STRATEGIES.keys()),
        format_func=lambda k: STRATEGIES[k],
    )

    underlying = st.selectbox("Underlying", ["SPX", "NDX", "SX5E"])

    col1, col2 = st.columns(2)
    with col1:
        tenor_days = st.number_input("Tenor (days)", min_value=5, max_value=252, value=21, step=1)
    with col2:
        roll_freq = st.number_input("Roll freq (days)", min_value=1, max_value=63, value=21, step=1)

    mode = st.radio("Backtest mode", ["payoff", "delta_hedged"],
                    format_func=lambda m: "Payoff" if m == "payoff" else "Delta-Hedged")

    st.subheader("Date Range")
    start_date = st.date_input("Start", value=pd.Timestamp("2010-01-01"))
    end_date   = st.date_input("End",   value=pd.Timestamp.today())

    run_btn = st.button("Run Backtest", type="primary", use_container_width=True)

# ── Session state ──────────────────────────────────────────────────────────────
if "bt_result" not in st.session_state:
    st.session_state.bt_result = None
if "bt_params" not in st.session_state:
    st.session_state.bt_params = {}

# ── Run engine ─────────────────────────────────────────────────────────────────
params = dict(strategy=strategy, underlying=underlying, tenor_days=tenor_days,
              roll_freq=roll_freq, mode=mode,
              start=str(start_date), end=str(end_date))

if run_btn or (st.session_state.bt_result is None):
    with st.spinner("Loading market data and running backtest…"):
        try:
            data = load_backtest_data(underlying, start=str(start_date), end=str(end_date))
            engine = BacktestEngine(data)
            trade_df, daily_df = engine.run(strategy, tenor_days, roll_freq, mode)
            st.session_state.bt_result = (trade_df, daily_df, data)
            st.session_state.bt_params = params
        except Exception as e:
            st.error(f"Backtest failed: {e}")
            st.stop()

if st.session_state.bt_result is None:
    st.info("Configure parameters in the sidebar and click **Run Backtest**.")
    st.stop()

trade_df, daily_df, market_data = st.session_state.bt_result
current_params = st.session_state.bt_params

if trade_df.empty:
    st.warning("No trades generated — try extending the date range or reducing tenor.")
    st.stop()

metrics = compute_metrics(trade_df)

# ── Top KPIs ───────────────────────────────────────────────────────────────────
st.subheader(f"{STRATEGIES[current_params['strategy']]} · {current_params['underlying']} · "
             f"{current_params['mode'].replace('_', '-')} mode")

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Trades", metrics.get("n_trades", 0))
k2.metric("Total P&L", f"{metrics.get('total_pnl', 0):.3%}")
k3.metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
k4.metric("Hit Rate", f"{metrics.get('hit_rate_pct', 0):.1f}%")
k5.metric("Max DD", f"{metrics.get('max_drawdown', 0):.3%}")
k6.metric("Calmar", f"{metrics.get('calmar_ratio', 0):.2f}")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_pnl, tab_dist, tab_scenario, tab_metrics, tab_attr = st.tabs([
    "P&L Timeseries", "Trade Distribution", "Scenario Analysis", "Metrics", "Attribution"
])

# ════════════════════════════════════════════════════════════════════════════════
# Tab 1: P&L Timeseries
# ════════════════════════════════════════════════════════════════════════════════
with tab_pnl:
    cum = cumulative_pnl(trade_df)
    uw  = underwater_series(trade_df)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cum.index, y=cum.values * 100,
        mode="lines", name="Cumulative P&L (%)",
        line=dict(color="#00B4D8", width=2),
        fill="tozeroy", fillcolor="rgba(0,180,216,0.08)",
    ))
    fig.update_layout(
        title="Cumulative P&L (% of spot, normalised)",
        yaxis_title="P&L (%)", xaxis_title="",
        hovermode="x unified", height=360,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
    )
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=uw.index, y=uw.values * 100,
        mode="lines", name="Drawdown (%)",
        line=dict(color="#ef4444", width=1.5),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.15)",
    ))
    fig2.update_layout(
        title="Underwater / Drawdown",
        yaxis_title="DD (%)", height=240,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
    )
    st.plotly_chart(fig2, use_container_width=True)

    if len(trade_df) >= 12:
        rs = rolling_sharpe(trade_df, window=12)
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=trade_df["entry_date"].iloc[rs.notna().values],
            y=rs.dropna().values,
            marker_color=["#22c55e" if v > 0 else "#ef4444" for v in rs.dropna().values],
            name="Rolling Sharpe (12T)",
        ))
        fig3.add_hline(y=0, line_dash="dash", line_color="gray")
        fig3.update_layout(
            title="Rolling 12-Trade Sharpe",
            yaxis_title="Sharpe", height=260,
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
        )
        st.plotly_chart(fig3, use_container_width=True)

    with st.expander("Trade log"):
        disp_cols = [c for c in ["entry_date", "exit_date", "S_entry", "S_exit",
                                  "vol_entry", "premium", "payoff", "pnl", "win"]
                     if c in trade_df.columns]
        st.dataframe(trade_df[disp_cols].style.format({
            "pnl": "{:.3%}", "premium": "{:.3%}", "payoff": "{:.3%}",
            "S_entry": "{:.1f}", "S_exit": "{:.1f}", "vol_entry": "{:.1%}",
        }), use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# Tab 2: Trade Distribution
# ════════════════════════════════════════════════════════════════════════════════
with tab_dist:
    col_a, col_b = st.columns([2, 1])

    with col_a:
        pnl_vals = trade_df["pnl"].dropna() * 100
        fig = px.histogram(
            pnl_vals, nbins=40,
            color_discrete_sequence=["#00B4D8"],
            labels={"value": "P&L (%)", "count": "Trades"},
            title="Per-Trade P&L Distribution",
        )
        fig.add_vline(x=0, line_dash="dash", line_color="white", annotation_text="Break-even")
        fig.add_vline(x=float(pnl_vals.mean()), line_dash="dot",
                      line_color="#facc15", annotation_text="Mean")
        fig.update_layout(
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#fafafa"), height=360,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        wins  = int((trade_df["pnl"] > 0).sum())
        total = len(trade_df)
        fig_pie = go.Figure(go.Pie(
            labels=["Win", "Loss"],
            values=[wins, total - wins],
            marker_colors=["#22c55e", "#ef4444"],
            hole=0.5,
        ))
        fig_pie.update_layout(
            title="Win / Loss",
            height=280,
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        st.metric("Avg win",  f"{metrics.get('avg_win', 0):.3%}")
        st.metric("Avg loss", f"{metrics.get('avg_loss', 0):.3%}")
        st.metric("P/L ratio", f"{metrics.get('pl_ratio') or 0:.2f}x")

    # P&L vs spot return scatter
    if "spot_ret_pct" in trade_df.columns:
        fig_sc = px.scatter(
            trade_df, x="spot_ret_pct", y=trade_df["pnl"] * 100,
            color=trade_df["win"].map({True: "Win", False: "Loss"}),
            color_discrete_map={"Win": "#22c55e", "Loss": "#ef4444"},
            labels={"x": "Spot Return (%)", "y": "Trade P&L (%)", "color": ""},
            title="P&L vs Spot Return",
            trendline="ols",
        )
        fig_sc.update_layout(
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#fafafa"), height=320,
        )
        st.plotly_chart(fig_sc, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# Tab 3: Scenario Analysis
# ════════════════════════════════════════════════════════════════════════════════
with tab_scenario:
    st.caption("Compare strategy performance across named historical regimes.")

    scenario_names = [s for s in SCENARIOS if s != "Custom" and s != "Full History"]
    selected_scenarios = st.multiselect(
        "Scenarios to compare",
        ["Full History"] + scenario_names,
        default=["Full History", "GFC (2008–2009)", "COVID Crash (2020)", "Rate Hike Cycle (2022)"],
    )

    if not selected_scenarios:
        st.info("Select at least one scenario.")
    else:
        rows = []
        for sc_name in selected_scenarios:
            sliced = slice_trades(trade_df, sc_name)
            if sliced.empty:
                continue
            m = compute_metrics(sliced)
            m["scenario"] = sc_name
            m["note"] = describe_scenario(sc_name)
            rows.append(m)

        if rows:
            sc_df = pd.DataFrame(rows).set_index("scenario")

            # Bar chart: Sharpe across scenarios
            display_metrics = ["sharpe_ratio", "hit_rate_pct", "total_pnl", "max_drawdown"]
            metric_labels = {"sharpe_ratio": "Sharpe", "hit_rate_pct": "Hit Rate (%)",
                             "total_pnl": "Total P&L", "max_drawdown": "Max DD"}

            chart_metric = st.selectbox("Chart metric", display_metrics,
                                        format_func=lambda k: metric_labels[k])

            colors = ["#22c55e" if v >= 0 else "#ef4444"
                      for v in sc_df[chart_metric].values]
            fig_sc = go.Figure(go.Bar(
                x=sc_df.index.tolist(),
                y=sc_df[chart_metric].values,
                marker_color=colors,
                text=[f"{v:.2f}" for v in sc_df[chart_metric].values],
                textposition="outside",
            ))
            fig_sc.update_layout(
                title=f"{metric_labels[chart_metric]} by Scenario",
                yaxis_title=metric_labels[chart_metric],
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font=dict(color="#fafafa"), height=360,
            )
            st.plotly_chart(fig_sc, use_container_width=True)

            # Summary table
            show_cols = ["n_trades", "total_pnl", "sharpe_ratio", "hit_rate_pct",
                         "max_drawdown", "calmar_ratio", "note"]
            show_cols = [c for c in show_cols if c in sc_df.columns]
            fmt = {
                "total_pnl": "{:.3%}",
                "max_drawdown": "{:.3%}",
                "sharpe_ratio": "{:.2f}",
                "calmar_ratio": "{:.2f}",
                "hit_rate_pct": "{:.1f}%",
            }
            st.dataframe(sc_df[show_cols].style.format(fmt), use_container_width=True)

            # Cumulative P&L overlay per scenario
            st.subheader("Cumulative P&L by Scenario")
            fig_ov = go.Figure()
            palette = px.colors.qualitative.Set2
            for idx, sc_name in enumerate(selected_scenarios):
                sliced = slice_trades(trade_df, sc_name)
                if sliced.empty:
                    continue
                c = cumulative_pnl(sliced) * 100
                fig_ov.add_trace(go.Scatter(
                    x=c.index, y=c.values, mode="lines",
                    name=sc_name,
                    line=dict(color=palette[idx % len(palette)], width=2),
                ))
            fig_ov.update_layout(
                yaxis_title="Cumulative P&L (%)",
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font=dict(color="#fafafa"), height=380, hovermode="x unified",
            )
            st.plotly_chart(fig_ov, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# Tab 4: Metrics
# ════════════════════════════════════════════════════════════════════════════════
with tab_metrics:
    st.subheader("Full Metrics Summary")

    metric_data = {
        "Metric": [
            "Number of Trades", "Total P&L", "Mean P&L / Trade",
            "Std Dev P&L", "Sharpe Ratio", "Sortino Ratio", "Calmar Ratio",
            "Hit Rate", "Avg Win", "Avg Loss", "P/L Ratio",
            "Kelly Fraction", "Max Drawdown", "Best Trade", "Worst Trade",
        ],
        "Value": [
            metrics.get("n_trades"),
            f"{metrics.get('total_pnl', 0):.3%}",
            f"{metrics.get('mean_pnl_per_trade', 0):.3%}",
            f"{metrics.get('std_pnl', 0):.3%}",
            f"{metrics.get('sharpe_ratio', 0):.3f}",
            f"{metrics.get('sortino_ratio', 0):.3f}",
            f"{metrics.get('calmar_ratio', 0):.3f}",
            f"{metrics.get('hit_rate_pct', 0):.1f}%",
            f"{metrics.get('avg_win', 0):.3%}",
            f"{metrics.get('avg_loss', 0):.3%}",
            f"{metrics.get('pl_ratio') or 0:.2f}x",
            f"{metrics.get('kelly_fraction_pct', 0):.1f}%",
            f"{metrics.get('max_drawdown', 0):.3%}",
            f"{metrics.get('best_trade', 0):.3%}",
            f"{metrics.get('worst_trade', 0):.3%}",
        ],
    }
    st.dataframe(pd.DataFrame(metric_data), use_container_width=True, hide_index=True)

    if not daily_df.empty:
        st.subheader("Daily P&L Decomposition (Delta-Hedged)")
        agg = daily_df.groupby("entry_date")[["option_chg", "hedge_chg", "daily_pnl"]].sum()
        agg.columns = ["Option Chg", "Hedge Chg", "Net Daily P&L"]
        fig_d = go.Figure()
        for col, color in [("Option Chg", "#00B4D8"), ("Hedge Chg", "#f97316"), ("Net Daily P&L", "#a3e635")]:
            fig_d.add_trace(go.Scatter(
                x=agg.index, y=agg[col] * 100,
                mode="lines", name=col,
                line=dict(color=color, width=1.5),
            ))
        fig_d.update_layout(
            title="Option vs Hedge P&L (per trade cohort, % of spot)",
            yaxis_title="P&L (%)", hovermode="x unified", height=360,
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
        )
        st.plotly_chart(fig_d, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# Tab 5: Attribution
# ════════════════════════════════════════════════════════════════════════════════
with tab_attr:
    st.subheader("P&L Attribution")

    if current_params.get("mode") == "delta_hedged":
        st.info("Attribution is computed for **payoff mode** only. "
                "Re-run in payoff mode to see delta/vega/theta decomposition.")
    else:
        with st.spinner("Computing attribution…"):
            try:
                attr_df = payoff_attribution(trade_df, current_params["strategy"])
                summary = attribution_summary(attr_df)
            except Exception as e:
                st.error(f"Attribution error: {e}")
                attr_df = pd.DataFrame()
                summary = pd.DataFrame()

        if not summary.empty:
            col_s, col_w = st.columns([1, 2])

            with col_s:
                st.dataframe(summary.style.format({
                    "Total P&L": "{:.6f}",
                    "% of Total": "{:.1f}%",
                }), use_container_width=True)

            with col_w:
                labels = ["Delta", "Vega", "Theta", "Residual"]
                keys   = ["delta_pnl", "vega_pnl", "theta_pnl", "residual"]
                values = [float(attr_df[k].sum()) * 100 for k in keys if k in attr_df.columns]
                labels = labels[:len(values)]

                colors_attr = ["#00B4D8", "#a78bfa", "#fb923c", "#6b7280"]
                fig_attr = go.Figure(go.Bar(
                    x=labels, y=values,
                    marker_color=colors_attr[:len(values)],
                    text=[f"{v:.3f}%" for v in values],
                    textposition="outside",
                ))
                fig_attr.update_layout(
                    title="Attribution Waterfall (sum over all trades, % of spot)",
                    yaxis_title="P&L (%)",
                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                    font=dict(color="#fafafa"), height=360,
                )
                st.plotly_chart(fig_attr, use_container_width=True)

            # Scatter: residual vs spot return
            if "residual" in attr_df.columns and "spot_ret_pct" in attr_df.columns:
                fig_res = px.scatter(
                    attr_df, x="spot_ret_pct", y=attr_df["residual"] * 100,
                    color_discrete_sequence=["#6b7280"],
                    labels={"x": "Spot Return (%)", "y": "Residual P&L (%)"},
                    title="Residual P&L vs Spot Return",
                )
                fig_res.add_hline(y=0, line_dash="dash", line_color="white")
                fig_res.update_layout(
                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                    font=dict(color="#fafafa"), height=300,
                )
                st.plotly_chart(fig_res, use_container_width=True)

            with st.expander("Full attribution table"):
                attr_cols = [c for c in ["entry_date", "pnl", "delta_pnl", "vega_pnl",
                                          "theta_pnl", "residual"] if c in attr_df.columns]
                st.dataframe(attr_df[attr_cols].style.format({
                    c: "{:.4%}" for c in ["pnl", "delta_pnl", "vega_pnl", "theta_pnl", "residual"]
                    if c in attr_df.columns
                }), use_container_width=True)

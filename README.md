# Macro QIS Workbench — Technical Documentation (English)

> Version: PoC (Proof of Concept)
> Stack: Python · Streamlit · Black / Black-76 / Analytical Approximation

---

## 1. Overview

Macro QIS Workbench is a sell-side structuring and QIS (Quantitative Investment Strategies)
desk tool. It supports the end-to-end workflow from macro regime identification → product
idea generation → indicative pricing → historical backtest. It is designed as a PoC to
demonstrate the analytical framework and client-facing logic, not as a production trading system.

---

## 2. Features by Page

### 2.1 Home Dashboard (`app.py`)
- Live market snapshot: US Treasury yield curve (3M, 2Y, 5Y, 10Y, 30Y), VIX spot and
  VIX3M, 21-day realised vol (SPX)
- Yield curve chart and VIX term structure visualisation
- Macro indicator panel (CPI, unemployment — requires FRED API key)
- Regime summary card: yield curve label, vol regime, rate level, RV/IV relationship

### 2.2 Idea Scanner (`pages/1_Idea_Scanner.py`)
Three-stage pipeline:

**Stage 1 — Macro Regime Classification**
Reads the market snapshot and classifies five dimensions:
- Yield curve: steep / flat / mildly_inverted / deeply_inverted (threshold on 2s10s spread)
- Vol level: suppressed / low / normal / elevated / spike (VIX thresholds)
- Vol term structure: contango / flat / backwardation (VIX3M vs VIX slope)
- Rate level: low / moderate / high / very_high (US10Y thresholds)
- RV/IV relationship: rv_rich / fairly_priced / iv_rich (21d RV vs VIX ratio)

**Stage 2 — Signal Generation**
Rule-based mapping from regime to directional trade signals per product:
- Rate Swaption: receiver (inverted + high rates), payer spread (steep + high vol), straddle (flat + low vol)
- Bond Futures Option: long call (inverted + high rates), short strangle (elevated vol)
- Equity Vanilla: long vol spread (suppressed VIX), put spread sell (spike), covered overwrite (IV rich)
- Vol Products: short VIX roll-down (contango + low vol), long vol hedge (backwardation), short var swap (RV rich)
- Autocall: coupon_rich (elevated/spike vol), capital protection note (low vol + reasonable rates)
- Systematic Strategy: rates carry/roll-down (steep curve), vol carry basket (low vol + contango)

**Stage 3 — Scorecard**
Weighted average of 6 dimensions (all 0–10 scale):

| Dimension | Weight | Source |
|---|---|---|
| macro_alignment | 25% | signal.strength × 10 |
| vol_environment | 20% | VIX-based product-specific function |
| liquidity | 20% | Static per product |
| hedgeability | 15% | Static per product |
| client_suitability | 10% | Static lookup: product × client type |
| xva_drag | 10% | Static: low=8.5, medium=5.5, high=2.5 |

Client suitability rationale — see `docs/client_fit_score_logic.md`.

### 2.3 Pricing Calculator (`pages/2_Pricing.py`)
Six product tabs, each with per-product inputs, a price button, metric display,
sensitivity charts, and indicative xVA.

| Tab | Model | Key Inputs |
|---|---|---|
| Rate Swaption | Black-76 | Forward rate, strike, expiry, tenor, vol, notional |
| Bond Futures Option | Black-76 | Futures price, strike, expiry, vol, contracts × notional/contract |
| Equity Vanilla | Black-Scholes | Spot, strike(s), expiry, vol, contracts × multiplier |
| Vol Products | Analytical | ATM vol, maturity, vega notional, skew, position |
| Autocall | Single-factor Gaussian | Barrier, KI barrier, coupon, maturity, obs freq, vol, notional |
| Structured Notes | ZC bond + option | Spot, maturity, vol, protection/participation or put strike, notional |

Expiry/maturity inputs accept Days / Weeks / Months / Years.

Sensitivity charts: Price vs rate/spot/vol, DV01/Delta vs rate/spot, Vega vs rate/vol, Gamma vs spot.

xVA tab on each product: CVA + FVA in bps and $ amount, client-type-adjusted.

### 2.4 Backtest (`pages/3_Backtest.py`)
Historical simulation of equity option strategies on SPX / SX5E using daily close data.

**Two modes:**
- **Payoff mode**: at trade entry, price the strategy via Black-Scholes; at expiry,
  compute terminal intrinsic payoff. P&L = payoff − premium. Clean and intuitive.
- **Delta-hedged mode**: daily delta rebalancing. P&L = Δ option value + Δ hedge P&L.
  Isolates vol carry (realised vol vs implied vol).

**Strategies available**: Long/short straddle, long call/put, call spread, put spread,
risk reversal, covered call, long strangle.

**Performance metrics**: Sharpe, Sortino, Calmar, hit rate, P&L ratio, Kelly fraction,
max drawdown, best/worst trade.

**Charts**: Cumulative P&L, rolling Sharpe, drawdown series, trade P&L distribution.

---

## 3. Data Sources

| Data | Source | Fallback |
|---|---|---|
| US Treasury yields (3M–30Y) | FRED (DGS2, DGS5, DGS10, DGS30, DTB3) | yfinance (^IRX, ^FVX, ^TNX, ^TYX) |
| Macro indicators (CPI, unemployment) | FRED (CPIAUCSL, UNRATE) | None (FRED required) |
| Equity spot (SPX, SX5E) | yfinance (^GSPC, ^STOXX50E) | Last close from history |
| VIX spot & VIX3M | yfinance (^VIX, ^VIX3M) | Default: 20.0 |
| Historical prices (backtest) | yfinance | None |
| Realised vol (RV 21d/63d/126d/252d) | Computed: rolling std(log returns) × √252 | — |
| Curve spreads (2s10s etc.) | Derived from yield curve | — |
| CDS spreads | Hardcoded by client type (proxy) | Manual override in UI |
| Exposure factors (xVA) | Hardcoded by product type | — |

All fetched data is cached in memory (TTL within a Streamlit session) via `data/cache.py`
to avoid redundant API calls.

---

## 4. Models, Algorithms & Assumptions

### 4.1 Black-76 (Rate Swaption, Bond Futures Option)

$$C = df \cdot [F \cdot N(d_1) - K \cdot N(d_2)]$$
$$d_1 = \frac{\ln(F/K) + \frac{1}{2}\sigma^2 T}{\sigma\sqrt{T}}, \quad d_2 = d_1 - \sigma\sqrt{T}$$

- `df` = discount factor = exp(−r·T); for swaptions df=1 (rate already a forward)
- Lognormal vol assumed (not normal/shifted-lognormal)
- Annuity: approximate as sum of semi-annual discount factors at flat forward rate
- DV01 (swaption, swap convention): ∂price/∂rate = delta × annuity (bps/bp)
- DV01 (bond futures): ∂price_amount/∂F = delta × notional / 10,000 ($/bp)

### 4.2 Black-Scholes (Equity Vanilla)

Standard GBM with continuous dividend yield q:
$$C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)$$
$$d_1 = \frac{\ln(S/K) + (r - q + \frac{1}{2}\sigma^2)T}{\sigma\sqrt{T}}$$

- Greeks: analytical (delta, gamma, vega, theta)
- Skew proxy for OTM legs: `vol_atm − skew_slope × (K−S)/S × 20`
- Numerical delta/gamma/vega in sensitivity charts (finite difference, ε = 0.1% of spot)

### 4.3 Autocall — Single-Factor Gaussian Analytical Approximation

The model decomposes the autocall into:
1. **Autocall redemption PV**: Σ P(called at step i) × df_i × (notional + coupon)
2. **Coupon PV**: Σ P(survive to i) × P(above coupon barrier at i) × df_i × coupon
3. **Final redemption PV (above KI)**: P(survive) × P(S_T > KI) × df × notional
4. **Final redemption PV (below KI)**: P(survive) × P(S_T < KI) × df × E[S_T/S_0 | S_T < KI] × notional

Survival probability at time T with GBM:
$$P(S_T > B | S_0 = 1) = N\left(\frac{\ln(1/B) + \mu T}{\sigma\sqrt{T}}\right)$$
where μ = r − q − ½σ².

**Key assumptions**:
- Path dependency approximated by treating each observation period independently
  (actual autocalls are path-dependent; this is a conservative approximation)
- Single-factor: single lognormal underlying, no correlation
- Barrier breaches between observation dates are ignored
- Spot sensitivity: barriers are rescaled to current spot (barrier_rel = barrier_abs / spot)
  to reflect moneyness correctly as spot varies

### 4.4 Structured Notes

**Capital Protection Note (CPN):**
- Price = ZC bond cost + participation × call option cost
- ZC bond cost = protection_level × exp(−r × T) (continuously compounded)
- Issuer margin = 100% − ZC cost − call cost
- Call priced via Black-Scholes

**Yield Enhancement Note (Reverse Convertible):**
- The investor is short a put; premium collected = yield enhancement
- Break-even = strike × (1 − put_premium / notional)
- Max loss occurs if underlying falls through the put strike to zero

### 4.5 Vol Products

**Variance Swap:**
- Fair variance strike ≈ ATM_vol² × (1 + skew_adjustment)
- Skew adjustment: `2 × abs(skew_slope) × ATM_vol × T^0.5` (first-order approximation)
- Var notional: `vega_notional / (2 × ATM_vol)`
- P&L (if realised vol provided): `var_notional × (RV² − fair_var_strike²)`

**Vol Swap:**
- Fair vol strike ≈ ATM_vol − convexity_correction
- Convexity correction ≈ `var_vol_premium / (8 × ATM_vol)` (Jensen's inequality adjustment)

**VIX Roll-Down:**
- Carry = (VIX3M − VIX) / days_in_period × roll_days
- Annualised carry expressed as % of VIX level

### 4.6 xVA Proxy

**CVA (Credit Valuation Adjustment):**
$$\text{CVA} \approx \text{PD}_{\text{total}} \times \text{LGD} \times \text{EPE\_factor}$$
- PD from flat hazard rate: `PD_total = 1 − exp(−(CDS/LGD) × T)`
- LGD = 0.60 (recovery = 40%)
- EPE (Expected Positive Exposure) factor: product-specific constant (1–8% of notional)
- CDS spread: client-type proxy (PB=80bp, Pension=50bp, Insurance=60bp) or manual override

**FVA (Funding Valuation Adjustment):**
$$\text{FVA} \approx \text{funding\_spread} \times \text{EPE\_factor} \times T$$

Both expressed in bps of notional. Total xVA = CVA + FVA.

### 4.7 Backtest Engine

**Payoff mode:**
- Entry: price strategy at Black-Scholes with spot/VIX vol
- Exit: compute terminal intrinsic payoff at T
- P&L (normalised): (payoff − premium) / S_entry

**Delta-hedged mode:**
- Entry: price strategy; compute initial delta
- Daily: recompute option value and delta with updated spot/vol/T_remaining
- Daily P&L = Δ option_value + (−delta_prev × ΔS)  [short delta to hedge]
- Cumulates daily P&L over the tenor

Vol proxy: VIX/100 used as ATM implied vol for all pricing within the backtest.
Calendar: 252 business days/year; tenor_days are calendar-day approximations.
Skew proxy for OTM legs: put vol × 1.08, call vol × 0.97 (constant skew).

---

## 5. Current Limitations

### 5.1 Pricing
- **Flat yield curve**: a single risk-free rate r is used for discounting; no full curve
  bootstrapping, no OIS discounting, no tenor-specific discount factors
- **Lognormal only**: Black-76 / BS assume lognormal dynamics; no normal vol (Bachelier),
  no shifted-lognormal for near-zero/negative rates
- **Flat vol surface**: a single ATM vol is used per product; no implied vol smile/skew
  surface for autocall barriers or structured note strikes
- **Autocall path dependency ignored**: independent-period survival probability is
  a conservative approximation; a proper model requires Monte Carlo or PDE
- **Annuity approximation**: flat-rate semi-annual approximation; real annuities require
  a bootstrapped swap curve
- **No dividend term structure**: single q used; real equity products need term dividends

### 5.2 xVA
- **No netting**: each trade is treated independently; in practice xVA is computed at
  netting set level
- **No collateral (CSA)**: no margin or collateral agreement modelled
- **No dynamic EPE**: exposure profile is a single static factor; real EPE requires
  Monte Carlo simulation of the forward exposure
- **No DVA / KVA / MVA**: only CVA and FVA are modelled
- **No wrong-way risk**: correlation between counterparty default and exposure not modelled
- **Proxy CDS spreads**: hardcoded; in production these would come from credit desk data

### 5.3 Idea Scanner
- **Threshold-based regime**: all regime classifications use fixed numeric thresholds;
  no statistical model, no regime-switching Markov model, no ML classifier
- **Static signal rules**: signal-to-product mapping is hand-coded; no dynamic learning
  from historical signal performance
- **Static suitability scores**: client fit is a hardcoded lookup; not driven by actual
  client mandate data, regulatory limits, or live position data
- **Single-factor vol**: VIX used as a proxy for rate vol in the vol_environment score

### 5.4 Backtest
- **VIX as vol proxy**: VIX/100 used as ATM implied vol for all dates; no term structure,
  no smile, no per-strike vol
- **No transaction costs**: no bid-offer spread, no slippage, no funding cost of delta hedge
- **Equity-only**: backtest covers equity vanilla strategies only; rate products not included
- **Model-in / model-out**: pricing model used for both entry (P&L generation) and exit
  revaluation, which can create circularity; no independent market prices used
- **No corporate actions**: dividends, splits, spin-offs not adjusted in the backtest series
  (yfinance `auto_adjust=True` handles splits but not all corporate events)

---

## 6. Future Improvements

### 6.1 Near-term (analytical depth)
- **Curve bootstrapping**: build a proper OIS / SOFR swap curve for discounting; support
  multi-curve (projection vs discounting)
- **Normal vol model (Bachelier)**: add normal vol option for near-zero-rate environments
- **SABR vol surface**: fit SABR parameters to smile/skew for more realistic pricing of
  OTM options and structured products
- **Proper autocall Monte Carlo**: path-dependent simulation with daily monitoring; add
  local vol or SV dynamics for more accurate KI probabilities
- **Dividend term structure**: use equity forward curve with discrete dividends

### 6.2 xVA
- **Bilateral CVA (DVA)**: include own credit risk
- **netting and collateral**: ISDA netting sets with threshold / MTA modelling
- **Dynamic EPE via simulation**: Monte Carlo forward exposure profiles per product
- **SA-CCR (Basel IV)**: regulatory exposure-at-default calculation for capital estimation
- **KVA and MVA**: capital and margin valuation adjustments

### 6.3 Idea Scanner
- **Statistical regime model**: Hidden Markov Model or clustering-based regime detection
  on macro factors
- **Signal backtesting**: validate each signal rule against historical performance;
  dynamically adjust signal strength weights
- **Live mandate integration**: connect client mandate and limit data to make suitability
  scores dynamic and trade-level compliant
- **Multi-factor scoring**: add ESG constraints, sector/geography filters, concentration limits

### 6.4 Backtest
- **Transaction costs**: model bid-offer, slippage, and financing cost of stock legs
- **Vol surface backtest**: use historical options chain data (CBOE) for realistic entry/exit pricing
- **Rate strategy backtest**: extend to swaption, bond futures, and autocall strategies
- **Multi-asset / portfolio backtest**: correlation-aware portfolio construction with
  cross-product aggregation
- **Factor attribution**: Fama-French style attribution of P&L to vol carry, delta, gamma, etc.

### 6.5 Infrastructure
- **Real-time data**: integrate Bloomberg B-PIPE or Refinitiv for live market data
- **Database persistence**: store trade history and backtest results in a database
- **User authentication**: multi-user support with role-based access (structurer vs client-facing)
- **Scenario library**: pre-built stress scenarios (GFC 2008, COVID 2020, rate spike 2022)
  saved and replayable
- **PDF/Excel export**: client-ready tear sheets for each pricing run

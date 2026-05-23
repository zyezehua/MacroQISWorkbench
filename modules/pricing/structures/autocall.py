"""
Autocall / autocallable structured note pricing.
Analytical approximation: single-factor Gaussian, assumes log-normal underlying.

Key mechanics modelled:
  - Periodic autocall observation (e.g. monthly/quarterly)
  - Autocall trigger at barrier (e.g. 100% of initial)
  - Coupon paid if not called and above coupon barrier (same or lower)
  - Capital at risk below knock-in barrier (e.g. 60% of initial)
  - Final redemption: par if above KI barrier, otherwise (S_T / S_0) * notional
"""
import numpy as np
from utils.math_utils import norm_cdf


def _survival_prob(drift, sigma, T, barrier_ratio):
    """
    P(S_T > barrier | S_0=1) for GBM with log-normal approximation.
    drift = r - q - 0.5*sigma^2 (log-space drift).
    """
    if T <= 0:
        return 1.0 if 1.0 > barrier_ratio else 0.0
    d = (np.log(1.0 / barrier_ratio) + drift * T) / (sigma * np.sqrt(T))
    return norm_cdf(d)


def price_autocall(
    spot,
    barrier_pct=1.00,
    coupon_barrier_pct=1.00,
    ki_barrier_pct=0.60,
    coupon_pa=0.08,
    maturity_years=3,
    obs_per_year=4,
    sigma=0.20,
    r=0.04,
    q=0.02,
    notional=1_000_000,
):
    """
    Indicative autocall pricing via analytical approximation.

    Parameters
    ----------
    spot             : current spot level (used only for moneyness display)
    barrier_pct      : autocall trigger as fraction of initial (e.g. 1.00 = 100%)
    coupon_barrier_pct: coupon observation barrier (e.g. 1.00 = 100%)
    ki_barrier_pct   : knock-in (capital-at-risk) barrier (e.g. 0.60 = 60%)
    coupon_pa        : annual coupon rate (e.g. 0.08 = 8%)
    maturity_years   : product maturity in years
    obs_per_year     : observation frequency per year (4=quarterly, 12=monthly)
    sigma            : underlying annualised vol
    r                : risk-free rate
    q                : dividend yield (or repo)
    notional         : notional amount

    Returns
    -------
    dict with indicative price, coupon PV, redemption PV, key metrics
    """
    dt = 1 / obs_per_year
    drift = (r - q - 0.5 * sigma ** 2)
    log_drift = r - q  # for forward calculation
    coupon_amount = coupon_pa / obs_per_year * notional

    n_obs = int(maturity_years * obs_per_year)
    obs_times = [dt * i for i in range(1, n_obs + 1)]

    # Survival probability: P(not autocalled at or before obs t)
    # Approximation: treat each period independently (conservative — ignores path dep)
    # More accurate: prod of conditional survival probs
    coupon_pv = 0.0
    autocall_pv = 0.0

    prev_p_survive = 1.0
    for i, t in enumerate(obs_times):
        df_t = np.exp(-r * t)
        p_survive_to_t = _survival_prob(drift, sigma, t, barrier_pct)

        # P(called at step i) ≈ P(survive to i-1) - P(survive to i) [marginal]
        if i == 0:
            p_called_at_i = 1 - p_survive_to_t
        else:
            p_called_at_i = prev_p_survive - p_survive_to_t

        p_called_at_i = max(0.0, p_called_at_i)

        # Autocall redemption: par + coupon at call time
        autocall_pv += p_called_at_i * df_t * (notional + coupon_amount)

        # Coupon: paid if survived and above coupon barrier
        p_coupon = _survival_prob(drift, sigma, t, coupon_barrier_pct)
        coupon_pv += p_survive_to_t * p_coupon * df_t * coupon_amount

        prev_p_survive = p_survive_to_t

    # At maturity: if survived to final obs
    t_final = obs_times[-1]
    df_final = np.exp(-r * t_final)
    p_survive_to_maturity = prev_p_survive

    # Final redemption: above KI → par, below KI → (S_T/S_0) * notional (bear exposure)
    p_above_ki = _survival_prob(drift, sigma, t_final, ki_barrier_pct)
    p_below_ki = 1 - p_above_ki

    # Above KI: full redemption
    redemption_pv = p_survive_to_maturity * p_above_ki * df_final * notional

    # Below KI: partial redemption (expected value of S_T/S_0 below ki_barrier)
    # E[S_T/S_0 | S_T < ki * S_0] * P(S_T < ki) approximation
    forward = np.exp(log_drift * t_final)
    ki_log = np.log(ki_barrier_pct)
    d_ki = (np.log(forward / ki_barrier_pct)) / (sigma * np.sqrt(t_final))
    expected_loss_factor = forward * norm_cdf(-d_ki + sigma * np.sqrt(t_final)) / (p_below_ki + 1e-10)
    loss_redemption_pv = p_survive_to_maturity * p_below_ki * df_final * expected_loss_factor * notional

    total_pv = autocall_pv + coupon_pv + redemption_pv + loss_redemption_pv
    price_pct = total_pv / notional * 100

    # Indicative fair coupon: coupon that makes price_pct ≈ 100%
    # (linear approximation: adjust coupon proportionally)
    fair_coupon_pa = coupon_pa * notional / (total_pv + 1e-6)

    # Expected call date approximation
    avg_call_time = sum(
        (max(0, prev_p_survive - _survival_prob(drift, sigma, t, barrier_pct))) * t
        for prev_p_survive, t in zip(
            [1.0] + [_survival_prob(drift, sigma, obs_times[i], barrier_pct) for i in range(n_obs - 1)],
            obs_times
        )
    )

    return {
        "product": f"Autocall {maturity_years}Y {coupon_pa*100:.1f}%pa",
        "indicative_price_pct": round(price_pct, 3),
        "indicative_price_amount": round(total_pv, 0),
        "coupon_pv": round(coupon_pv, 0),
        "autocall_redemption_pv": round(autocall_pv, 0),
        "final_redemption_pv": round(redemption_pv + loss_redemption_pv, 0),
        "fair_coupon_pa_pct": round(fair_coupon_pa * 100, 2),
        "prob_survive_to_maturity_pct": round(prev_p_survive * 100, 2),
        "prob_ki_breach_pct": round(p_survive_to_maturity * p_below_ki * 100, 2),
        "autocall_barrier_pct": barrier_pct * 100,
        "ki_barrier_pct": ki_barrier_pct * 100,
        "sigma_pct": sigma * 100,
        "maturity_years": maturity_years,
        "obs_freq": obs_per_year,
    }

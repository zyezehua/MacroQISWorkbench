"""
Indicative xVA proxy using CDS spread approximation.
CVA ≈ PD * LGD * EPE  where  PD ≈ CDS_spread / LGD (flat hazard rate).
All outputs in bps of notional. PoC-level only.
"""
import numpy as np

RECOVERY_RATE = 0.40   # standard LGD = 1 - R = 0.60
LGD = 1 - RECOVERY_RATE

# Proxy CDS spreads by client type (bps) — to be overridden by internal data
DEFAULT_CDS_SPREADS = {
    "Private Bank": 80,
    "Pension Fund": 50,
    "Insurance": 60,
    "Corporate": 150,
}

# Exposure profile factor by product (avg exposure as % of notional over life)
EXPOSURE_FACTORS = {
    "RATE_SWPN": 0.03,
    "RATE_BFO":  0.01,
    "EQ_VANILLA": 0.05,
    "VOL_PROD":  0.04,
    "STRUCT_AC": 0.08,
    "SYS_STRAT": 0.02,
}


def estimate_cva(
    product_id,
    maturity_years,
    notional=1_000_000,
    client_type="Pension Fund",
    cds_override_bps=None,
):
    """
    Returns indicative CVA in bps of notional and absolute amount.

    Parameters
    ----------
    product_id      : one of the 6 product IDs
    maturity_years  : trade maturity in years
    notional        : notional amount
    client_type     : used to look up proxy CDS spread
    cds_override_bps: manual CDS spread override in bps
    """
    cds_bps = cds_override_bps or DEFAULT_CDS_SPREADS.get(client_type, 80)
    cds_decimal = cds_bps / 10_000
    pd_annual = cds_decimal / LGD
    total_pd = 1 - np.exp(-pd_annual * maturity_years)

    avg_exposure_pct = EXPOSURE_FACTORS.get(product_id, 0.05)
    cva_pct = total_pd * LGD * avg_exposure_pct
    cva_bps = cva_pct * 10_000
    cva_amount = cva_pct * notional

    return {
        "cva_bps": round(cva_bps, 2),
        "cva_amount": round(cva_amount, 2),
        "pd_total_pct": round(total_pd * 100, 3),
        "cds_spread_bps": cds_bps,
        "flag": "high" if cva_bps > 30 else ("medium" if cva_bps > 10 else "low"),
    }


def funding_cost(
    product_id,
    maturity_years,
    notional=1_000_000,
    funding_spread_bps=50,
):
    """Indicative FVA proxy — funding cost on net exposure."""
    import numpy as np
    avg_exposure_pct = EXPOSURE_FACTORS.get(product_id, 0.05)
    fva_bps = funding_spread_bps * avg_exposure_pct * maturity_years
    return {
        "fva_bps": round(fva_bps, 2),
        "fva_amount": round(fva_bps / 10_000 * notional, 2),
    }


def total_xva(product_id, maturity_years, notional, client_type, cds_override_bps=None, funding_spread_bps=50):
    cva = estimate_cva(product_id, maturity_years, notional, client_type, cds_override_bps)
    fva = funding_cost(product_id, maturity_years, notional, funding_spread_bps)
    total_bps = cva["cva_bps"] + fva["fva_bps"]
    return {
        "cva_bps": cva["cva_bps"],
        "fva_bps": fva["fva_bps"],
        "total_xva_bps": round(total_bps, 2),
        "total_xva_amount": round(total_bps / 10_000 * notional, 2),
        "flag": cva["flag"],
        "cds_spread_bps": cva["cds_spread_bps"],
    }

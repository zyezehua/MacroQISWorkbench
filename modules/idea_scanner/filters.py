"""
Compliance and liquidity flag rules.
These are deliberately conservative proxies for a PoC — structurer review required.
"""

_COMPLIANCE_RED = {
    "Private Bank": [],
    "Pension Fund": [],
    "Insurance": [],
}

_COMPLIANCE_YELLOW = {
    "Private Bank": ["VOL_PROD"],
    "Pension Fund": ["STRUCT_AC", "VOL_PROD"],
    "Insurance": ["VOL_PROD", "SYS_STRAT", "STRUCT_AC"],
}


def compliance_flag(product_id, client_type):
    """Returns 'green' | 'yellow' | 'red'."""
    if product_id in _COMPLIANCE_RED.get(client_type, []):
        return "red"
    if product_id in _COMPLIANCE_YELLOW.get(client_type, []):
        return "yellow"
    return "green"


def liquidity_flag(product_id, snapshot):
    """
    Flags reduced liquidity under stress (high VIX) for path-dependent products.
    Returns 'green' | 'yellow' | 'red'.
    """
    vix = snapshot.get("VIX", 20.0) or 20.0

    if vix > 50:
        # Extreme stress — structured products and vol very illiquid
        if product_id in ("STRUCT_AC", "VOL_PROD"):
            return "red"
        return "yellow"

    if vix > 30:
        if product_id in ("STRUCT_AC",):
            return "yellow"

    return "green"


def capacity_flag(product_id, snapshot):
    """
    Placeholder for warehouse capacity flag.
    Returns 'green' | 'yellow' | 'red'.
    Structurer should override manually once internal data is available.
    """
    # Default all green in PoC — override via scorecard UI
    return "green"

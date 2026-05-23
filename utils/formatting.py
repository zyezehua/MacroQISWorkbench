from config import THEME


def fmt_pct(val, decimals=2):
    return f"{val * 100:.{decimals}f}%"


def fmt_bps(val, decimals=1):
    return f"{val * 10_000:.{decimals}f} bps"


def fmt_price(val, decimals=4):
    return f"{val:.{decimals}f}"


def fmt_number(val, decimals=2):
    return f"{val:,.{decimals}f}"


def score_to_color(score, low=0.0, high=10.0):
    normalized = max(0.0, min(1.0, (score - low) / (high - low)))
    if normalized >= 0.65:
        return THEME["score_high"]
    if normalized >= 0.40:
        return THEME["score_mid"]
    return THEME["score_low"]


def flag_to_color(flag):
    mapping = {
        "green": THEME["flag_green"],
        "yellow": THEME["flag_yellow"],
        "red": THEME["flag_red"],
        "low": THEME["flag_green"],
        "medium": THEME["flag_mid"] if "flag_mid" in THEME else THEME["flag_yellow"],
        "high": THEME["flag_red"],
    }
    return mapping.get(str(flag).lower(), "#9E9E9E")


def flag_to_emoji(flag):
    mapping = {"green": "🟢", "yellow": "🟡", "red": "🔴", "low": "🟢", "medium": "🟡", "high": "🔴"}
    return mapping.get(str(flag).lower(), "⚪")

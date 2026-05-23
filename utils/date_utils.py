from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd


def parse_tenor(tenor_str, reference_date=None):
    if reference_date is None:
        reference_date = date.today()
    t = tenor_str.strip().upper()
    if t.endswith("Y"):
        return reference_date + relativedelta(years=int(t[:-1]))
    if t.endswith("M"):
        return reference_date + relativedelta(months=int(t[:-1]))
    if t.endswith("W"):
        return reference_date + timedelta(weeks=int(t[:-1]))
    if t.endswith("D"):
        return reference_date + timedelta(days=int(t[:-1]))
    raise ValueError(f"Unrecognised tenor format: {tenor_str}")


def years_between(start, end):
    """ACT/365 year fraction."""
    if isinstance(start, str):
        start = pd.to_datetime(start).date()
    if isinstance(end, str):
        end = pd.to_datetime(end).date()
    return (end - start).days / 365.0


def business_days_between(start, end):
    return len(pd.bdate_range(str(start), str(end)))


def next_business_day(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

"""
Demand analysis functions.

All functions are pure: they take DataFrames and return dicts or DataFrames.
No database access, no side effects.

Functions:
  compute_demand_rate(product_code, sales_df, window_days, as_of)
  detect_seasonality(product_code, sales_df)
  detect_slow_movers(sales_df, threshold_pct, as_of)
"""

from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Demand rate
# ---------------------------------------------------------------------------

def compute_demand_rate(
    product_code: str,
    sales_df: pd.DataFrame,
    window_days: int = 90,
    as_of: Optional[date] = None,
) -> dict:
    """
    Compute weighted average daily demand for a product.

    The window is split in two halves; the recent half is weighted 2x
    so the estimate adapts to trends without being too noisy.

    Returns:
        {
          "product_code":   str,
          "daily_demand":   float,   # weighted avg units/day
          "weekly_demand":  float,   # daily_demand × 7
          "std_dev_daily":  float,   # std dev of daily demand (for safety stock)
          "trend":          str,     # "rising" | "flat" | "falling"
          "trend_pct":      float,   # % change recent half vs older half
          "data_points":    int,     # number of days with at least one sale
          "window_days":    int,
        }
    """
    as_of = as_of or date.today()
    window_start = pd.Timestamp(as_of - timedelta(days=window_days))
    window_end   = pd.Timestamp(as_of)

    product_sales = sales_df[
        (sales_df["canonical_product_code"] == product_code)
        & (sales_df["invoice_date"] >= window_start)
        & (sales_df["invoice_date"] <  window_end)
    ].copy()

    # Daily aggregation — include credit notes (storno already netted in sales_df if used correctly,
    # but stornos are filtered out by the caller's sales_df which uses direction=issued, type=factura)
    if product_sales.empty:
        return _empty_demand(product_code, window_days)

    daily = (
        product_sales.groupby(product_sales["invoice_date"].dt.date)["quantity"]
        .sum()
        .reindex(
            pd.date_range(window_start, window_end - timedelta(days=1), freq="D").date,
            fill_value=0,
        )
    )

    # Triangular weights: recent half weighted 2x
    n = len(daily)
    half = n // 2
    weights = np.array([1.0] * (n - half) + [2.0] * half)
    values  = daily.values.astype(float)

    weighted_mean = float(np.average(values, weights=weights))

    # Trend: compare early third vs recent third
    third = max(1, n // 3)
    early_mean  = float(values[:third].mean())
    recent_mean = float(values[-third:].mean())

    if early_mean > 0:
        trend_pct = (recent_mean - early_mean) / early_mean
    else:
        trend_pct = 0.0

    if trend_pct > 0.10:
        trend = "rising"
    elif trend_pct < -0.10:
        trend = "falling"
    else:
        trend = "flat"

    return {
        "product_code":  product_code,
        "daily_demand":  round(weighted_mean, 4),
        "weekly_demand": round(weighted_mean * 7, 3),
        "std_dev_daily": round(float(values.std()), 4),
        "trend":         trend,
        "trend_pct":     round(trend_pct, 4),
        "data_points":   int((values > 0).sum()),
        "window_days":   window_days,
    }


def _empty_demand(product_code: str, window_days: int) -> dict:
    return {
        "product_code":  product_code,
        "daily_demand":  0.0,
        "weekly_demand": 0.0,
        "std_dev_daily": 0.0,
        "trend":         "flat",
        "trend_pct":     0.0,
        "data_points":   0,
        "window_days":   window_days,
    }


# ---------------------------------------------------------------------------
# Seasonality
# ---------------------------------------------------------------------------

def detect_seasonality(
    product_code: str,
    sales_df: pd.DataFrame,
) -> dict:
    """
    Compute monthly seasonal indices for a product.

    A monthly index > 1 means that month is above average;
    < 1 means below average.

    Requires at least 12 months of data to be meaningful.
    With 24 months, the same month is averaged across both years.

    Returns:
        {
          "product_code":     str,
          "indices":          {1: float, 2: float, ..., 12: float},
          "peak_month":       int,
          "trough_month":     int,
          "is_seasonal":      bool,   # True if any month is 1.5x+ the average
          "months_of_data":   int,
        }
    """
    product_sales = sales_df[sales_df["canonical_product_code"] == product_code].copy()

    if product_sales.empty:
        return _flat_seasonality(product_code)

    product_sales["month"] = product_sales["invoice_date"].dt.month
    product_sales["year"]  = product_sales["invoice_date"].dt.year

    # Monthly totals
    monthly = (
        product_sales.groupby(["year", "month"])["quantity"]
        .sum()
        .reset_index()
    )

    if monthly.empty:
        return _flat_seasonality(product_code)

    months_of_data = len(monthly)

    # Average across years for each calendar month
    avg_by_month = monthly.groupby("month")["quantity"].mean()

    # Fill missing months with the overall average
    overall_avg = avg_by_month.mean()
    indices = {}
    for m in range(1, 13):
        if m in avg_by_month.index and overall_avg > 0:
            indices[m] = round(float(avg_by_month[m]) / float(overall_avg), 3)
        else:
            indices[m] = 1.0

    peak_month   = max(indices, key=lambda m: indices[m])
    trough_month = min(indices, key=lambda m: indices[m])
    is_seasonal  = indices[peak_month] >= 1.5 or indices[trough_month] <= 0.5

    return {
        "product_code":   product_code,
        "indices":        indices,
        "peak_month":     peak_month,
        "trough_month":   trough_month,
        "is_seasonal":    is_seasonal,
        "months_of_data": months_of_data,
    }


def _flat_seasonality(product_code: str) -> dict:
    return {
        "product_code":   product_code,
        "indices":        {m: 1.0 for m in range(1, 13)},
        "peak_month":     1,
        "trough_month":   1,
        "is_seasonal":    False,
        "months_of_data": 0,
    }


# ---------------------------------------------------------------------------
# Slow mover detection
# ---------------------------------------------------------------------------

def detect_slow_movers(
    sales_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    threshold_pct: float = 0.40,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """
    Flag products whose demand dropped by more than threshold_pct
    comparing the last 90 days to the previous 90 days.

    Differentiates genuine decline from seasonal dips by checking
    whether the same calendar period last year was also low.

    Returns a DataFrame sorted by decline_pct descending:
        product_code, product_name, recent_daily, previous_daily,
        decline_pct, is_seasonal, status
    """
    as_of = as_of or date.today()
    t0 = pd.Timestamp(as_of)
    t1 = t0 - pd.Timedelta(days=90)
    t2 = t1 - pd.Timedelta(days=90)

    products = sales_df["canonical_product_code"].dropna().unique()
    rows = []

    for code in products:
        ps = sales_df[sales_df["canonical_product_code"] == code]

        recent_qty   = ps[ps["invoice_date"].between(t1, t0)]["quantity"].sum()
        previous_qty = ps[ps["invoice_date"].between(t2, t1)]["quantity"].sum()

        if previous_qty == 0:
            continue

        recent_daily   = recent_qty   / 90
        previous_daily = previous_qty / 90
        decline_pct    = (recent_daily - previous_daily) / previous_daily

        if decline_pct > -threshold_pct:
            continue  # not a slow mover

        # Seasonal check: look at the same 90-day window one year ago
        t_yr_recent   = t1 - pd.Timedelta(days=365)
        t_yr_previous = t2 - pd.Timedelta(days=365)
        year_ago_qty  = ps[ps["invoice_date"].between(t_yr_previous, t_yr_recent)]["quantity"].sum()
        year_ago_daily = year_ago_qty / 90 if year_ago_qty > 0 else None

        # If the same period last year was also low (< 70% of overall avg), it's seasonal
        overall_daily = ps["quantity"].sum() / max(
            1, (ps["invoice_date"].max() - ps["invoice_date"].min()).days
        )
        is_seasonal = (
            year_ago_daily is not None
            and overall_daily > 0
            and year_ago_daily < 0.7 * float(overall_daily)
        )

        # Get product name from inventory
        name_rows = inventory_df[inventory_df["canonical_product_code"] == code]["product_name"]
        product_name = name_rows.iloc[0] if not name_rows.empty else code

        rows.append({
            "product_code":   code,
            "product_name":   product_name,
            "recent_daily":   round(recent_daily, 4),
            "previous_daily": round(previous_daily, 4),
            "decline_pct":    round(decline_pct, 4),
            "is_seasonal":    is_seasonal,
            "status":         "seasonal_dip" if is_seasonal else "genuine_decline",
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("decline_pct").reset_index(drop=True)
    return result

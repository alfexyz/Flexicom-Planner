"""
Customer behaviour analysis.

Functions:
  detect_customer_pattern_deviation(customer_cui, sales_df, as_of)
  get_all_customer_deviations(sales_df, as_of)
"""

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd


def detect_customer_pattern_deviation(
    customer_cui: str,
    sales_df: pd.DataFrame,
    as_of: Optional[date] = None,
) -> dict:
    """
    Detect if a B2B customer's ordering pattern has deviated from their norm.

    Uses the customer's historical inter-order gaps (days between orders)
    to compute an expected order date. If the actual gap exceeds
    mean + 1.5 × std_dev, it's flagged as a deviation.

    Returns:
        {
          customer_cui, customer_name,
          avg_order_gap_days,      # historical average
          last_order_date,
          days_since_last_order,
          expected_next_order,     # last_order + avg_gap
          days_overdue,            # positive means late
          status,                  # "on_track" | "late" | "significantly_late" | "inactive"
          confidence               # "high" (≥10 orders) | "medium" (5-9) | "low" (<5)
        }
    """
    as_of = as_of or date.today()

    customer_sales = sales_df[sales_df["partner_cui"] == customer_cui].copy()
    if customer_sales.empty:
        return {"customer_cui": customer_cui, "error": "no sales data"}

    customer_name = str(customer_sales["partner_name"].iloc[0])

    # One date per invoice (not per line item)
    order_dates = (
        customer_sales.groupby("invoice_number")["invoice_date"]
        .min()
        .dt.date
        .sort_values()
        .tolist()
    )

    if len(order_dates) < 2:
        return {
            "customer_cui":        customer_cui,
            "customer_name":       customer_name,
            "avg_order_gap_days":  None,
            "last_order_date":     str(order_dates[-1]) if order_dates else None,
            "days_since_last_order": None,
            "expected_next_order": None,
            "days_overdue":        None,
            "status":              "insufficient_data",
            "confidence":          "low",
        }

    gaps = [
        (order_dates[i + 1] - order_dates[i]).days
        for i in range(len(order_dates) - 1)
    ]

    avg_gap  = float(np.mean(gaps))
    std_gap  = float(np.std(gaps)) if len(gaps) > 1 else avg_gap * 0.3
    threshold = avg_gap + 1.5 * std_gap

    last_order  = order_dates[-1]
    days_since  = (as_of - last_order).days
    expected    = last_order + pd.Timedelta(days=avg_gap).to_pytimedelta()
    days_overdue = days_since - avg_gap

    if len(order_dates) >= 10:
        confidence = "high"
    elif len(order_dates) >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    if days_since > threshold * 2:
        status = "inactive"
    elif days_since > threshold:
        status = "significantly_late"
    elif days_overdue > 0:
        status = "late"
    else:
        status = "on_track"

    return {
        "customer_cui":          customer_cui,
        "customer_name":         customer_name,
        "avg_order_gap_days":    round(avg_gap, 1),
        "last_order_date":       str(last_order),
        "days_since_last_order": days_since,
        "expected_next_order":   str(expected) if isinstance(expected, date) else str(expected.date()),
        "days_overdue":          round(days_overdue, 1),
        "status":                status,
        "confidence":            confidence,
        "total_orders":          len(order_dates),
    }


def get_all_customer_deviations(
    sales_df: pd.DataFrame,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """
    Run detect_customer_pattern_deviation for every customer.
    Returns a DataFrame of all customers, sorted by days_overdue descending.
    """
    as_of = as_of or date.today()
    customers = sales_df["partner_cui"].unique()

    rows = []
    for cui in customers:
        result = detect_customer_pattern_deviation(cui, sales_df, as_of=as_of)
        if "error" not in result and result.get("status") != "insufficient_data":
            rows.append(result)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("days_overdue", ascending=False).reset_index(drop=True)
    return df

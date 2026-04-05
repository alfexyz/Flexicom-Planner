"""
Margin and product ranking functions.

Functions:
  compute_margin(product_code, sales_df, purchases_df, as_of)
  rank_products(sales_df, purchases_df, inventory_df, metric, as_of)
  compute_customer_concentration(sales_df)
"""

from datetime import date, timedelta
from typing import Optional

import pandas as pd


def compute_margin(
    product_code: str,
    sales_df: pd.DataFrame,
    purchases_df: pd.DataFrame,
    as_of: Optional[date] = None,
    lookback_months: int = 12,
) -> dict:
    """
    Gross margin analysis for one product.

    Pairs selling price (from issued invoices) with purchase cost
    (from received invoices matched to the same canonical product code).

    Returns:
        {
          product_code, product_name,
          current_margin_pct,    # margin in most recent complete month
          avg_margin_pct,        # average over the lookback window
          margin_trend,          # "improving" | "stable" | "compressing"
          monthly_history: [{month, avg_sell_price, avg_buy_price, margin_pct}],
          cost_increase_alert: bool,
          cost_increase_pct: float | None,
        }
    """
    as_of = as_of or date.today()
    since = pd.Timestamp(as_of - timedelta(days=lookback_months * 30))

    product_sales = sales_df[
        (sales_df["canonical_product_code"] == product_code)
        & (sales_df["invoice_date"] >= since)
    ].copy()

    product_purchases = purchases_df[
        (purchases_df["canonical_product_code"] == product_code)
        & (purchases_df["invoice_date"] >= since)
    ].copy()

    if product_sales.empty:
        return {"product_code": product_code, "error": "no sales data"}

    product_name = str(product_sales["product_name"].iloc[0])

    # Monthly average sell and buy prices
    product_sales["month"]     = product_sales["invoice_date"].dt.to_period("M")
    product_purchases["month"] = product_purchases["invoice_date"].dt.to_period("M") if not product_purchases.empty else None

    sell_monthly = (
        product_sales.groupby("month")["unit_price"].mean()
        .rename("avg_sell")
    )

    if not product_purchases.empty:
        buy_monthly = (
            product_purchases.groupby("month")["unit_price"].mean()
            .rename("avg_buy")
        )
    else:
        buy_monthly = pd.Series(dtype=float, name="avg_buy")

    monthly = pd.concat([sell_monthly, buy_monthly], axis=1).dropna(subset=["avg_sell"])
    monthly["avg_buy"]    = monthly["avg_buy"].ffill().bfill()
    monthly["margin_pct"] = (
        (monthly["avg_sell"] - monthly["avg_buy"]) / monthly["avg_sell"] * 100
    ).round(2)

    if monthly.empty:
        return {"product_code": product_code, "product_name": product_name, "error": "insufficient data"}

    history = [
        {
            "month":          str(idx),
            "avg_sell_price": round(float(row["avg_sell"]), 2),
            "avg_buy_price":  round(float(row["avg_buy"]), 2) if pd.notna(row.get("avg_buy")) else None,
            "margin_pct":     round(float(row["margin_pct"]), 2) if pd.notna(row.get("margin_pct")) else None,
        }
        for idx, row in monthly.iterrows()
    ]

    current_margin = float(monthly["margin_pct"].iloc[-1]) if pd.notna(monthly["margin_pct"].iloc[-1]) else None
    avg_margin_raw = float(monthly["margin_pct"].mean())
    avg_margin     = avg_margin_raw if pd.notna(avg_margin_raw) else None

    # Trend: compare first third vs last third of the window
    n = len(monthly)
    third = max(1, n // 3)
    if pd.notna(monthly["margin_pct"]).sum() >= 4:
        early_margin  = monthly["margin_pct"].iloc[:third].mean()
        recent_margin = monthly["margin_pct"].iloc[-third:].mean()
        delta = recent_margin - early_margin
        if delta > 2:
            margin_trend = "improving"
        elif delta < -2:
            margin_trend = "compressing"
        else:
            margin_trend = "stable"
    else:
        margin_trend = "stable"

    # Cost increase alert: has buy price risen > 8% in the last 6 months?
    cost_increase_alert = False
    cost_increase_pct   = None
    if not product_purchases.empty and len(product_purchases) >= 4:
        recent_cutoff = pd.Timestamp(as_of - timedelta(days=180))
        old_cost    = product_purchases[product_purchases["invoice_date"] < recent_cutoff]["unit_price"].mean()
        recent_cost = product_purchases[product_purchases["invoice_date"] >= recent_cutoff]["unit_price"].mean()
        if pd.notna(old_cost) and pd.notna(recent_cost) and old_cost > 0:
            cost_increase_pct   = round((recent_cost - old_cost) / old_cost * 100, 2)
            cost_increase_alert = bool(cost_increase_pct > 5)

    return {
        "product_code":       product_code,
        "product_name":       product_name,
        "current_margin_pct": round(current_margin, 2) if current_margin is not None else None,
        "avg_margin_pct":     round(avg_margin, 2) if avg_margin is not None else None,
        "margin_trend":       margin_trend,
        "monthly_history":    history,
        "cost_increase_alert": cost_increase_alert,
        "cost_increase_pct":  cost_increase_pct,
    }


def rank_products(
    sales_df: pd.DataFrame,
    purchases_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    metric: str = "revenue",
    window_days: int = 365,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """
    Rank all products by a given metric.

    metric options:
      "volume"               — units sold
      "revenue"              — total revenue RON
      "margin_pct"           — gross margin %
      "margin_contribution"  — margin % × revenue (total RON margin earned)

    Returns a DataFrame with columns:
        rank, product_code, product_name, metric_value, volume, revenue, margin_pct
    Sorted descending by metric_value.
    """
    as_of    = as_of or date.today()
    since    = pd.Timestamp(as_of - timedelta(days=window_days))

    period_sales = sales_df[sales_df["invoice_date"] >= since].copy()

    if period_sales.empty:
        return pd.DataFrame()

    # Base aggregations
    by_product = (
        period_sales.groupby("canonical_product_code")
        .agg(
            volume  = ("quantity",    "sum"),
            revenue = ("total_value", "sum"),
        )
        .reset_index()
        .rename(columns={"canonical_product_code": "product_code"})
    )

    # Product names from inventory
    name_map = (
        inventory_df.drop_duplicates("canonical_product_code")
        .set_index("canonical_product_code")["product_name"]
        .to_dict()
    )
    by_product["product_name"] = by_product["product_code"].map(name_map).fillna("")

    # Margin per product using average prices
    margin_rows = []
    period_purchases = purchases_df[purchases_df["invoice_date"] >= since]

    for code in by_product["product_code"].unique():
        avg_sell = period_sales[period_sales["canonical_product_code"] == code]["unit_price"].mean()
        pp = period_purchases[period_purchases["canonical_product_code"] == code]
        avg_buy  = pp["unit_price"].mean() if not pp.empty else None

        if pd.notna(avg_sell) and pd.notna(avg_buy) and avg_sell > 0:
            margin_pct = (avg_sell - avg_buy) / avg_sell * 100
        else:
            margin_pct = None

        margin_rows.append({"product_code": code, "margin_pct": margin_pct})

    margin_df = pd.DataFrame(margin_rows)
    by_product = by_product.merge(margin_df, on="product_code", how="left")
    by_product["margin_contribution"] = (
        by_product["revenue"] * by_product["margin_pct"].fillna(0) / 100
    )

    # Sort by requested metric
    if metric == "volume":
        sort_col = "volume"
    elif metric == "revenue":
        sort_col = "revenue"
    elif metric == "margin_pct":
        sort_col = "margin_pct"
    elif metric == "margin_contribution":
        sort_col = "margin_contribution"
    else:
        raise ValueError(f"Unknown metric '{metric}'. Choose from: volume, revenue, margin_pct, margin_contribution")

    by_product = (
        by_product
        .sort_values(sort_col, ascending=False, na_position="last")
        .reset_index(drop=True)
    )
    by_product.insert(0, "rank", range(1, len(by_product) + 1))

    # Round for readability
    by_product["revenue"]              = by_product["revenue"].round(2)
    by_product["margin_pct"]           = by_product["margin_pct"].round(2)
    by_product["margin_contribution"]  = by_product["margin_contribution"].round(2)

    return by_product[["rank", "product_code", "product_name", "volume", "revenue", "margin_pct", "margin_contribution"]]


def compute_customer_concentration(sales_df: pd.DataFrame) -> dict:
    """
    Revenue concentration by customer.

    Returns:
        {
          total_revenue,
          top1_pct, top3_pct, top5_pct, top10_pct,
          concentration_risk: bool  (True if top1 >= 30%),
          customers: [{rank, partner_cui, partner_name, revenue, revenue_pct}]
        }
    """
    if sales_df.empty:
        return {"total_revenue": 0, "customers": []}

    by_customer = (
        sales_df.groupby(["partner_cui", "partner_name"])["total_value"]
        .sum()
        .reset_index()
        .sort_values("total_value", ascending=False)
        .reset_index(drop=True)
    )

    total = float(by_customer["total_value"].sum())
    by_customer["revenue_pct"] = (by_customer["total_value"] / total * 100).round(2)
    by_customer["rank"] = range(1, len(by_customer) + 1)

    def top_n_pct(n: int) -> float:
        return round(float(by_customer.head(n)["total_value"].sum() / total * 100), 2)

    records = by_customer.rename(columns={"total_value": "revenue"}).to_dict("records")

    return {
        "total_revenue":      round(total, 2),
        "top1_pct":           top_n_pct(1),
        "top3_pct":           top_n_pct(3),
        "top5_pct":           top_n_pct(5),
        "top10_pct":          top_n_pct(10),
        "concentration_risk": top_n_pct(1) >= 30.0,
        "customers":          records,
    }

"""
Inventory analysis functions.

Functions:
  compute_days_of_cover(product_code, inventory_df, sales_df, as_of)
  compute_reorder_point(product_code, inventory_df, sales_df, service_level, as_of)
  compute_dead_stock(inventory_df, sales_df, months_threshold, as_of)
  generate_supplier_order(supplier_cui, inventory_df, sales_df, as_of)
  compute_working_capital_breakdown(inventory_df, sales_df, as_of)
"""

import math
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from .demand import compute_demand_rate, detect_seasonality

# Z-scores for common service levels (no scipy needed)
_Z_SCORES = {0.90: 1.282, 0.95: 1.645, 0.98: 2.054, 0.99: 2.326}
_DEFAULT_SERVICE_LEVEL = 0.95


def compute_days_of_cover(
    product_code: str,
    inventory_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    as_of: Optional[date] = None,
) -> dict:
    """
    Days until stockout at current demand rate.

    Adjusts for seasonality: if we're entering a high-demand month,
    cover is shorter than a naive division would suggest.

    Returns:
        {
          product_code, product_name, current_stock,
          daily_demand, days_of_cover, adjusted_days_of_cover,
          color (green/amber/red), seasonal_note
        }
    """
    as_of = as_of or date.today()

    inv_row = inventory_df[inventory_df["canonical_product_code"] == product_code]
    if inv_row.empty:
        return {"product_code": product_code, "error": "not found in inventory"}

    inv_row      = inv_row.iloc[0]
    current_stock = float(inv_row.get("quantity_in_stock") or 0)
    product_name  = str(inv_row.get("product_name", product_code))

    demand = compute_demand_rate(product_code, sales_df, window_days=90, as_of=as_of)
    daily_demand = demand["daily_demand"]

    if daily_demand <= 0:
        return {
            "product_code":          product_code,
            "product_name":          product_name,
            "current_stock":         current_stock,
            "daily_demand":          0.0,
            "days_of_cover":         None,
            "adjusted_days_of_cover": None,
            "color":                 "green",
            "seasonal_note":         None,
        }

    # Simple days of cover
    simple_doc = current_stock / daily_demand

    # Seasonally adjusted: simulate forward day-by-day for 180 days
    seasonality = detect_seasonality(product_code, sales_df)
    indices      = seasonality["indices"]
    stock_left   = current_stock
    adjusted_doc = simple_doc  # fallback

    for day_offset in range(1, 181):
        future_date  = as_of + timedelta(days=day_offset)
        month_idx    = indices.get(future_date.month, 1.0)
        daily_demand_adj = daily_demand * month_idx
        stock_left  -= daily_demand_adj
        if stock_left <= 0:
            adjusted_doc = float(day_offset)
            break
    else:
        adjusted_doc = simple_doc  # still in stock after 180 days

    # Color coding
    if adjusted_doc >= 60:
        color = "green"
    elif adjusted_doc >= 15:
        color = "amber"
    else:
        color = "red"

    # Seasonal note
    next_month  = (as_of.month % 12) + 1
    next_idx    = indices.get(next_month, 1.0)
    seasonal_note = None
    if next_idx >= 1.5:
        seasonal_note = f"lună cu cerere ridicată urmează (indice={next_idx:.1f}x)"
    elif next_idx <= 0.6:
        seasonal_note = f"lună cu cerere scăzută urmează (indice={next_idx:.1f}x)"

    return {
        "product_code":           product_code,
        "product_name":           product_name,
        "current_stock":          current_stock,
        "daily_demand":           round(daily_demand, 4),
        "days_of_cover":          round(simple_doc, 1),
        "adjusted_days_of_cover": round(adjusted_doc, 1),
        "color":                  color,
        "seasonal_note":          seasonal_note,
    }


def compute_reorder_point(
    product_code: str,
    inventory_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    service_level: float = _DEFAULT_SERVICE_LEVEL,
    as_of: Optional[date] = None,
) -> dict:
    """
    Compute ROP, safety stock, and suggested order quantity.

    ROP           = avg_daily_demand × lead_time + safety_stock
    safety_stock  = Z × σ_demand × √lead_time
    suggested_qty = max(6-week demand + safety_stock, min_order_qty)

    Returns:
        {
          product_code, product_name, current_stock,
          rop, safety_stock, suggested_order_qty,
          lead_time_days, service_level,
          below_rop (bool), days_until_rop
        }
    """
    as_of = as_of or date.today()
    z = _Z_SCORES.get(service_level, 1.645)

    inv_row = inventory_df[inventory_df["canonical_product_code"] == product_code]
    if inv_row.empty:
        return {"product_code": product_code, "error": "not found in inventory"}

    inv_row       = inv_row.iloc[0]
    product_name  = str(inv_row.get("product_name", product_code))
    current_stock = float(inv_row.get("quantity_in_stock") or 0)
    lead_time     = float(inv_row.get("lead_time_days") or 7)
    moq           = float(inv_row.get("min_order_qty") or 1)
    unit_cost     = float(inv_row.get("purchase_price") or 0)

    demand = compute_demand_rate(product_code, sales_df, window_days=90, as_of=as_of)
    daily_demand = demand["daily_demand"]
    sigma        = demand["std_dev_daily"]

    if daily_demand <= 0:
        return {
            "product_code":       product_code,
            "product_name":       product_name,
            "current_stock":      current_stock,
            "rop":                0.0,
            "safety_stock":       0.0,
            "suggested_order_qty": moq,
            "lead_time_days":     lead_time,
            "service_level":      service_level,
            "below_rop":          False,
            "days_until_rop":     None,
            "estimated_cost_ron": 0.0,
        }

    safety_stock = z * sigma * math.sqrt(lead_time)
    rop          = daily_demand * lead_time + safety_stock

    # Suggested order: 6 weeks of demand + safety stock, rounded up to MOQ
    six_week_qty  = daily_demand * 42
    raw_suggested = six_week_qty + safety_stock
    suggested_qty = max(moq, math.ceil(raw_suggested / moq) * moq)

    below_rop      = current_stock <= rop
    days_until_rop = (current_stock - rop) / daily_demand if not below_rop and daily_demand > 0 else None

    return {
        "product_code":        product_code,
        "product_name":        product_name,
        "current_stock":       current_stock,
        "rop":                 round(rop, 1),
        "safety_stock":        round(safety_stock, 1),
        "suggested_order_qty": int(suggested_qty),
        "lead_time_days":      lead_time,
        "service_level":       service_level,
        "below_rop":           below_rop,
        "days_until_rop":      round(days_until_rop, 1) if days_until_rop else None,
        "estimated_cost_ron":  round(suggested_qty * unit_cost, 2),
    }


def compute_dead_stock(
    inventory_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    months_threshold: int = 6,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """
    Products with zero or near-zero sales in the last N months.

    Returns DataFrame sorted by capital_trapped descending:
        product_code, product_name, quantity_in_stock,
        units_sold_in_period, capital_trapped, last_sale_date, months_threshold
    """
    as_of     = as_of or date.today()
    since     = pd.Timestamp(as_of - timedelta(days=months_threshold * 30))

    rows = []
    for _, inv_row in inventory_df.iterrows():
        code  = inv_row.get("canonical_product_code")
        if not code:
            continue

        stock     = float(inv_row.get("quantity_in_stock") or 0)
        unit_cost = float(inv_row.get("purchase_price") or 0)

        if stock <= 0:
            continue

        ps = sales_df[
            (sales_df["canonical_product_code"] == code)
            & (sales_df["invoice_date"] >= since)
        ]
        units_sold    = float(ps["quantity"].sum())
        days_in_period = months_threshold * 30

        # Dead if current stock would last longer than 2× the threshold period at current rate
        # e.g. with months_threshold=6: flag if stock > 12 months of demand
        daily_demand = units_sold / days_in_period if days_in_period > 0 else 0
        if daily_demand > 0:
            days_of_cover = stock / daily_demand
            if days_of_cover <= months_threshold * 30 * 2:
                continue   # selling fast enough
        elif units_sold > 0:
            continue       # some sales, no demand rate calculable — skip

        all_sales = sales_df[sales_df["canonical_product_code"] == code]
        last_sale = (
            all_sales["invoice_date"].max().date()
            if not all_sales.empty
            else None
        )

        rows.append({
            "product_code":      code,
            "product_name":      str(inv_row.get("product_name", code)),
            "quantity_in_stock": stock,
            "units_sold_in_period": units_sold,
            "capital_trapped":   round(stock * unit_cost, 2),
            "last_sale_date":    str(last_sale) if last_sale else None,
            "months_threshold":  months_threshold,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("capital_trapped", ascending=False).reset_index(drop=True)
    return result


def generate_supplier_order(
    supplier_cui: str,
    inventory_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    as_of: Optional[date] = None,
) -> dict:
    """
    Consolidated order recommendation for all below-ROP products from one supplier.

    Returns:
        {
          supplier_cui, supplier_name, lead_time_days,
          lines: [{product_code, product_name, suggested_qty, unit_cost, line_total}],
          total_cost_ron, coverage_days
        }
    """
    as_of = as_of or date.today()

    supplier_inv = inventory_df[inventory_df["supplier_cui"] == supplier_cui]
    if supplier_inv.empty:
        return {"supplier_cui": supplier_cui, "error": "no products for this supplier"}

    supplier_name = str(supplier_inv.iloc[0].get("supplier_name", supplier_cui))
    lead_time     = float(supplier_inv.iloc[0].get("lead_time_days") or 7)

    lines    = []
    for _, inv_row in supplier_inv.iterrows():
        code = inv_row.get("canonical_product_code")
        if not code:
            continue

        rop_result = compute_reorder_point(code, inventory_df, sales_df, as_of=as_of)

        if not rop_result.get("below_rop", False):
            continue

        lines.append({
            "product_code":   code,
            "product_name":   str(inv_row.get("product_name", code)),
            "suggested_qty":  rop_result["suggested_order_qty"],
            "unit_cost":      float(inv_row.get("purchase_price") or 0),
            "line_total":     round(
                rop_result["suggested_order_qty"] * float(inv_row.get("purchase_price") or 0), 2
            ),
        })

    if not lines:
        return {
            "supplier_cui":  supplier_cui,
            "supplier_name": supplier_name,
            "lead_time_days": lead_time,
            "lines":         [],
            "total_cost_ron": 0.0,
            "coverage_days": None,
            "message":       "All products are above reorder point",
        }

    total_cost = round(sum(l["line_total"] for l in lines), 2)

    # Estimate coverage: average days of cover after order arrives
    demand_results = [
        compute_days_of_cover(l["product_code"], inventory_df, sales_df, as_of=as_of)
        for l in lines
    ]
    valid_docs = [
        d["adjusted_days_of_cover"]
        for d in demand_results
        if d.get("adjusted_days_of_cover") is not None and d["adjusted_days_of_cover"] > 0
    ]
    coverage_days = round(sum(valid_docs) / len(valid_docs), 0) if valid_docs else None

    return {
        "supplier_cui":   supplier_cui,
        "supplier_name":  supplier_name,
        "lead_time_days": lead_time,
        "lines":          lines,
        "total_cost_ron": total_cost,
        "coverage_days":  coverage_days,
    }


def compute_working_capital_breakdown(
    inventory_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    as_of: Optional[date] = None,
) -> dict:
    """
    Total inventory value at purchase cost, segmented by health.

    Segments:
      healthy  — days_of_cover > 60  (selling well)
      slow     — 15 ≤ days_of_cover ≤ 60  (needs monitoring)
      critical — days_of_cover < 15  (risk of stockout)
      dead     — no sales in last 6 months

    Returns:
        {
          total_ron, healthy_ron, slow_ron, critical_ron, dead_ron,
          breakdown: [{product_code, product_name, stock_value, segment, days_of_cover}]
        }
    """
    as_of = as_of or date.today()

    dead_result = compute_dead_stock(inventory_df, sales_df, months_threshold=6, as_of=as_of)
    dead_codes  = set(dead_result["product_code"].tolist()) if not dead_result.empty else set()

    totals = {"healthy": 0.0, "slow": 0.0, "critical": 0.0, "dead": 0.0}
    breakdown = []

    for _, inv_row in inventory_df.iterrows():
        code      = inv_row.get("canonical_product_code")
        stock     = float(inv_row.get("quantity_in_stock") or 0)
        unit_cost = float(inv_row.get("purchase_price") or 0)
        value     = round(stock * unit_cost, 2)

        if stock <= 0 or not code:
            continue

        if code in dead_codes:
            segment = "dead"
            doc     = None
        else:
            doc_result = compute_days_of_cover(code, inventory_df, sales_df, as_of=as_of)
            doc        = doc_result.get("adjusted_days_of_cover")
            if doc is None:
                segment = "healthy"   # no demand = not at risk
            elif doc < 15:
                segment = "critical"
            elif doc < 60:
                segment = "slow"
            else:
                segment = "healthy"

        totals[segment] += value
        breakdown.append({
            "product_code":  code,
            "product_name":  str(inv_row.get("product_name", code)),
            "stock_value":   value,
            "segment":       segment,
            "days_of_cover": round(doc, 1) if doc is not None else None,
        })

    total = sum(totals.values())
    return {
        "total_ron":    round(total, 2),
        "healthy_ron":  round(totals["healthy"], 2),
        "slow_ron":     round(totals["slow"], 2),
        "critical_ron": round(totals["critical"], 2),
        "dead_ron":     round(totals["dead"], 2),
        "breakdown":    sorted(breakdown, key=lambda r: r["stock_value"], reverse=True),
    }

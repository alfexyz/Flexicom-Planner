from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_engine
from backend.api.schemas import CustomerDetail, CustomerSummary
from backend.engine import Engine
from backend.engine.customers import detect_customer_pattern_deviation

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerSummary])
def list_customers(engine: Engine = Depends(get_engine)):
    deviations = engine.all_customer_deviations()
    if deviations.empty:
        return []

    results = []
    for _, row in deviations.iterrows():
        results.append(CustomerSummary(
            customer_cui          = row["customer_cui"],
            customer_name         = row["customer_name"],
            avg_order_gap_days    = row.get("avg_order_gap_days"),
            last_order_date       = row.get("last_order_date"),
            days_since_last_order = int(row["days_since_last_order"]) if row.get("days_since_last_order") is not None else None,
            days_overdue          = row.get("days_overdue"),
            status                = row["status"],
            confidence            = row["confidence"],
            total_orders          = int(row["total_orders"]) if row.get("total_orders") is not None else None,
        ))
    return results


@router.get("/{customer_cui}", response_model=CustomerDetail)
def get_customer(customer_cui: str, engine: Engine = Depends(get_engine)):
    sales = engine._da.sales()

    deviation = detect_customer_pattern_deviation(customer_cui, sales)
    if "error" in deviation:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_cui}' not found")

    # Revenue contribution
    concentration = engine.customer_concentration()
    total_revenue = concentration["total_revenue"]
    customer_revenue = next(
        (c["revenue"] for c in concentration["customers"] if c["partner_cui"] == customer_cui),
        0.0,
    )
    revenue_share = round(customer_revenue / total_revenue * 100, 2) if total_revenue > 0 else 0.0

    # Recent orders (last 10 invoices, one row per invoice)
    customer_sales = sales[sales["partner_cui"] == customer_cui].copy()
    recent = (
        customer_sales.groupby("invoice_number")
        .agg(
            invoice_date  = ("invoice_date", "min"),
            total_value   = ("total_value",  "sum"),
            line_items    = ("product_code", "count"),
        )
        .reset_index()
        .sort_values("invoice_date", ascending=False)
        .head(10)
    )
    recent_orders = [
        {
            "invoice_number": str(r["invoice_number"]),
            "invoice_date":   str(r["invoice_date"].date()),
            "total_value":    round(float(r["total_value"]), 2),
            "line_items":     int(r["line_items"]),
        }
        for _, r in recent.iterrows()
    ]

    return CustomerDetail(
        customer_cui          = deviation["customer_cui"],
        customer_name         = deviation["customer_name"],
        avg_order_gap_days    = deviation.get("avg_order_gap_days"),
        last_order_date       = deviation.get("last_order_date"),
        days_since_last_order = int(deviation["days_since_last_order"]) if deviation.get("days_since_last_order") is not None else None,
        expected_next_order   = deviation.get("expected_next_order"),
        days_overdue          = deviation.get("days_overdue"),
        status                = deviation["status"],
        confidence            = deviation["confidence"],
        total_orders          = deviation.get("total_orders"),
        total_revenue         = round(float(customer_revenue), 2),
        revenue_share_pct     = revenue_share,
        recent_orders         = recent_orders,
    )

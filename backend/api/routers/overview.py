from datetime import date

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_engine
from backend.api.schemas import AlertCounts, AlertEntry, InventoryHealth, OverviewResponse, RevenueSnapshot
from backend.engine import Engine

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", response_model=OverviewResponse)
def get_overview(engine: Engine = Depends(get_engine)):
    sales = engine._da.sales()

    # ---- Revenue snapshot ----
    today  = date.today()
    sales["month"] = sales["invoice_date"].dt.to_period("M")

    this_m      = today.strftime("%Y-%m")
    last_m      = (today.replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m")
    year_ago_m  = date(today.year - 1, today.month, 1).strftime("%Y-%m")

    def month_revenue(period_str: str) -> float:
        rows = sales[sales["month"].astype(str) == period_str]
        return round(float(rows["total_value"].sum()), 2)

    this_rev    = month_revenue(this_m)
    last_rev    = month_revenue(last_m)
    year_ago_rev = month_revenue(year_ago_m)
    trend_pct   = round((this_rev - last_rev) / last_rev * 100, 1) if last_rev > 0 else None

    revenue = RevenueSnapshot(
        this_month           = this_rev,
        last_month           = last_rev,
        same_month_last_year = year_ago_rev,
        trend_pct            = trend_pct,
    )

    # ---- Inventory health ----
    wc = engine.working_capital()
    total = wc["total_ron"] or 1  # avoid division by zero

    inventory = InventoryHealth(
        total_ron    = wc["total_ron"],
        healthy_ron  = wc["healthy_ron"],
        slow_ron     = wc["slow_ron"],
        critical_ron = wc["critical_ron"],
        dead_ron     = wc["dead_ron"],
        healthy_pct  = round(wc["healthy_ron"]  / total * 100, 1),
        slow_pct     = round(wc["slow_ron"]     / total * 100, 1),
        critical_pct = round(wc["critical_ron"] / total * 100, 1),
        dead_pct     = round(wc["dead_ron"]     / total * 100, 1),
    )

    # ---- Alert counts ----
    raw_alerts = engine.alerts()

    alert_counts = AlertCounts(
        critical           = len(raw_alerts["critical"]),
        order_now          = len(raw_alerts["order_now"]),
        watch              = len(raw_alerts["watch"]),
        dead_stock         = len(raw_alerts["dead_stock"]),
        declining          = len(raw_alerts["declining"]),
        customer_deviation = len(raw_alerts["customer_deviation"]),
        total              = sum(len(v) for v in raw_alerts.values()),
    )

    # ---- Top 3 most urgent (critical first, then order_now, then watch) ----
    top_raw = (
        raw_alerts["critical"][:3]
        + raw_alerts["order_now"][:max(0, 3 - len(raw_alerts["critical"]))]
        + raw_alerts["watch"][:max(0, 3 - len(raw_alerts["critical"]) - len(raw_alerts["order_now"]))]
    )[:3]

    top_alerts = [AlertEntry(**e) for e in top_raw]

    return OverviewResponse(
        revenue      = revenue,
        inventory    = inventory,
        alert_counts = alert_counts,
        top_alerts   = top_alerts,
    )

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_engine
from backend.api.schemas import ProductDetail, ProductSummary
from backend.engine import Engine
from backend.engine.demand import compute_demand_rate, detect_seasonality
from backend.engine.inventory import compute_days_of_cover, compute_dead_stock, compute_reorder_point
from backend.engine.margin import compute_margin

router = APIRouter(prefix="/products", tags=["products"])


def _status_badge(doc: float | None, below_rop: bool, lead_time: float, is_dead: bool, is_declining: bool) -> str:
    if is_dead:
        return "Dead"
    if doc is not None and doc < lead_time:
        return "Critical"
    if below_rop:
        return "OrderNow"
    if doc is not None and doc < 30:
        return "Watch"
    if is_declining:
        return "Declining"
    return "OK"


@router.get("", response_model=list[ProductSummary])
def list_products(engine: Engine = Depends(get_engine)):
    inventory = engine._da.inventory()
    sales     = engine._da.sales()
    purchases = engine._da.purchases()

    dead_codes     = set(engine.dead_stock()["product_code"].tolist()) if not engine.dead_stock().empty else set()
    declining_codes = set(
        engine.slow_movers()[engine.slow_movers()["status"] == "genuine_decline"]["product_code"].tolist()
    ) if not engine.slow_movers().empty else set()

    results = []
    for _, row in inventory.iterrows():
        code = row.get("canonical_product_code")
        if not code:
            continue

        doc_r    = compute_days_of_cover(code, inventory, sales)
        rop_r    = compute_reorder_point(code, inventory, sales)
        demand_r = compute_demand_rate(code, sales)
        margin_r = compute_margin(code, sales, purchases)

        doc      = doc_r.get("adjusted_days_of_cover")
        lead     = float(row.get("lead_time_days") or 7)
        below_rop = rop_r.get("below_rop", False)

        results.append(ProductSummary(
            product_code            = code,
            product_name            = str(row.get("product_name", code)),
            current_stock           = float(row.get("quantity_in_stock") or 0),
            days_of_cover           = doc_r.get("days_of_cover"),
            days_of_cover_adjusted  = doc,
            color                   = doc_r.get("color", "green"),
            daily_demand            = demand_r["daily_demand"],
            weekly_demand           = demand_r["weekly_demand"],
            trend                   = demand_r["trend"],
            margin_pct              = margin_r.get("current_margin_pct"),
            status                  = _status_badge(
                doc, below_rop, lead,
                code in dead_codes,
                code in declining_codes,
            ),
        ))

    return results


@router.get("/{product_code}", response_model=ProductDetail)
def get_product(product_code: str, engine: Engine = Depends(get_engine)):
    inventory = engine._da.inventory()
    sales     = engine._da.sales()
    purchases = engine._da.purchases()

    inv_rows = inventory[inventory["canonical_product_code"] == product_code]
    if inv_rows.empty:
        raise HTTPException(status_code=404, detail=f"Product '{product_code}' not found")

    inv_row = inv_rows.iloc[0]

    doc_r     = compute_days_of_cover(product_code, inventory, sales)
    rop_r     = compute_reorder_point(product_code, inventory, sales)
    demand_r  = compute_demand_rate(product_code, sales)
    season_r  = detect_seasonality(product_code, sales)
    margin_r  = compute_margin(product_code, sales, purchases)

    supplier = None
    if inv_row.get("supplier_cui"):
        supplier = {
            "supplier_cui":   str(inv_row["supplier_cui"]),
            "supplier_name":  str(inv_row.get("supplier_name", "")),
            "lead_time_days": float(inv_row.get("lead_time_days") or 7),
        }

    return ProductDetail(
        product_code   = product_code,
        product_name   = str(inv_row.get("product_name", product_code)),
        current_stock  = float(inv_row.get("quantity_in_stock") or 0),
        # inventory
        days_of_cover          = doc_r.get("days_of_cover"),
        days_of_cover_adjusted = doc_r.get("adjusted_days_of_cover"),
        color                  = doc_r.get("color", "green"),
        seasonal_note          = doc_r.get("seasonal_note"),
        rop                    = rop_r.get("rop"),
        safety_stock           = rop_r.get("safety_stock"),
        suggested_order_qty    = rop_r.get("suggested_order_qty"),
        below_rop              = rop_r.get("below_rop"),
        days_until_rop         = rop_r.get("days_until_rop"),
        estimated_cost_ron     = rop_r.get("estimated_cost_ron"),
        lead_time_days         = rop_r.get("lead_time_days"),
        # demand
        daily_demand   = demand_r["daily_demand"],
        weekly_demand  = demand_r["weekly_demand"],
        std_dev_daily  = demand_r["std_dev_daily"],
        trend          = demand_r["trend"],
        trend_pct      = demand_r["trend_pct"],
        # seasonality
        is_seasonal          = season_r["is_seasonal"],
        seasonality_indices  = season_r["indices"],
        peak_month           = season_r["peak_month"],
        trough_month         = season_r["trough_month"],
        # margin
        current_margin_pct   = margin_r.get("current_margin_pct"),
        avg_margin_pct       = margin_r.get("avg_margin_pct"),
        margin_trend         = margin_r.get("margin_trend"),
        cost_increase_alert  = margin_r.get("cost_increase_alert"),
        cost_increase_pct    = margin_r.get("cost_increase_pct"),
        monthly_margin_history = margin_r.get("monthly_history", []),
        # supplier
        supplier = supplier,
    )

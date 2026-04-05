import csv
import io
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.dependencies import get_engine
from backend.api.schemas import (
    AlertEntry, AlertsResponse, CustomerDeviationAlert,
    DeadStockEntry, DecliningEntry, SupplierOrderResponse, OrderLine,
)
from backend.engine import Engine
from backend.engine.inventory import generate_supplier_order

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertsResponse)
def get_alerts(engine: Engine = Depends(get_engine)):
    raw = engine.alerts()

    return AlertsResponse(
        critical   = [AlertEntry(**e) for e in raw["critical"]],
        order_now  = [AlertEntry(**e) for e in raw["order_now"]],
        watch      = [AlertEntry(**e) for e in raw["watch"]],
        dead_stock = [DeadStockEntry(**e) for e in raw["dead_stock"]],
        declining  = [DecliningEntry(**e) for e in raw["declining"]],
        customer_deviation = [
            CustomerDeviationAlert(
                customer_cui          = e["customer_cui"],
                customer_name         = e["customer_name"],
                avg_order_gap_days    = e.get("avg_order_gap_days"),
                last_order_date       = e.get("last_order_date"),
                days_since_last_order = e.get("days_since_last_order"),
                days_overdue          = e.get("days_overdue"),
                status                = e["status"],
            )
            for e in raw["customer_deviation"]
        ],
    )


@router.get("/orders", response_model=list[SupplierOrderResponse])
def get_order_recommendations(engine: Engine = Depends(get_engine)):
    inventory = engine._da.inventory()
    sales     = engine._da.sales()

    suppliers = inventory["supplier_cui"].dropna().unique()
    orders    = []

    for cui in suppliers:
        result = generate_supplier_order(cui, inventory, sales)
        if result.get("error"):
            continue
        orders.append(SupplierOrderResponse(
            supplier_cui   = result["supplier_cui"],
            supplier_name  = result["supplier_name"],
            lead_time_days = result["lead_time_days"],
            lines          = [OrderLine(**line) for line in result["lines"]],
            total_cost_ron = result["total_cost_ron"],
            coverage_days  = result.get("coverage_days"),
            message        = result.get("message"),
        ))

    # Only return suppliers that actually have lines to order
    return [o for o in orders if o.lines]


@router.get("/orders/export", response_class=StreamingResponse)
def export_orders_csv(engine: Engine = Depends(get_engine)):
    """
    Export recommended purchase orders as CSV.
    Only includes lines where the product is below its reorder point (confident orders).
    """
    inventory = engine._da.inventory()
    sales     = engine._da.sales()

    suppliers = inventory["supplier_cui"].dropna().unique()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "furnizor_cui", "furnizor_name", "termen_livrare_zile",
        "cod_produs", "denumire_produs", "cantitate_recomandata",
        "pret_unitar_ron", "total_linie_ron", "data_export",
    ])

    today = str(date.today())
    for cui in suppliers:
        result = generate_supplier_order(cui, inventory, sales)
        if result.get("error") or not result.get("lines"):
            continue
        for line in result["lines"]:
            writer.writerow([
                result["supplier_cui"],
                result["supplier_name"],
                result["lead_time_days"],
                line["product_code"],
                line["product_name"],
                line["suggested_qty"],
                line["unit_cost"],
                line["line_total"],
                today,
            ])

    output.seek(0)
    filename = f"comenzi_recomandate_{today}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

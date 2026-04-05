"""
Pydantic response models for all API endpoints.
"""

from typing import Any, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class SupplierInfo(BaseModel):
    supplier_cui:  str
    supplier_name: str
    lead_time_days: float


# ---------------------------------------------------------------------------
# /products
# ---------------------------------------------------------------------------

class ProductSummary(BaseModel):
    product_code:             str
    product_name:             str
    current_stock:            float
    days_of_cover:            Optional[float]
    days_of_cover_adjusted:   Optional[float]
    color:                    str              # green | amber | red
    daily_demand:             float
    weekly_demand:            float
    trend:                    str              # rising | flat | falling
    margin_pct:               Optional[float]
    status:                   str              # OK | Watch | OrderNow | Critical | Dead | Declining


class ProductDetail(BaseModel):
    product_code:    str
    product_name:    str
    current_stock:   float
    # inventory
    days_of_cover:           Optional[float]
    days_of_cover_adjusted:  Optional[float]
    color:                   str
    seasonal_note:           Optional[str]
    rop:                     Optional[float]
    safety_stock:            Optional[float]
    suggested_order_qty:     Optional[int]
    below_rop:               Optional[bool]
    days_until_rop:          Optional[float]
    estimated_cost_ron:      Optional[float]
    lead_time_days:          Optional[float]
    # demand
    daily_demand:    float
    weekly_demand:   float
    std_dev_daily:   float
    trend:           str
    trend_pct:       float
    # seasonality
    is_seasonal:         bool
    seasonality_indices: dict[int, float]
    peak_month:          int
    trough_month:        int
    # margin
    current_margin_pct:  Optional[float]
    avg_margin_pct:      Optional[float]
    margin_trend:        Optional[str]
    cost_increase_alert: Optional[bool]
    cost_increase_pct:   Optional[float]
    monthly_margin_history: list[dict]
    # supplier
    supplier: Optional[SupplierInfo]


# ---------------------------------------------------------------------------
# /alerts
# ---------------------------------------------------------------------------

class AlertEntry(BaseModel):
    product_code:  str
    product_name:  str
    days_of_cover: Optional[float]
    message:       str


class DeadStockEntry(BaseModel):
    product_code:       str
    product_name:       str
    quantity_in_stock:  float
    units_sold_in_period: float
    capital_trapped:    float
    last_sale_date:     Optional[str]


class DecliningEntry(BaseModel):
    product_code:   str
    product_name:   str
    recent_daily:   float
    previous_daily: float
    decline_pct:    float
    is_seasonal:    bool
    status:         str


class CustomerDeviationAlert(BaseModel):
    customer_cui:          str
    customer_name:         str
    avg_order_gap_days:    Optional[float]
    last_order_date:       Optional[str]
    days_since_last_order: Optional[int]
    days_overdue:          Optional[float]
    status:                str


class AlertsResponse(BaseModel):
    critical:           list[AlertEntry]
    order_now:          list[AlertEntry]
    watch:              list[AlertEntry]
    dead_stock:         list[DeadStockEntry]
    declining:          list[DecliningEntry]
    customer_deviation: list[CustomerDeviationAlert]


# ---------------------------------------------------------------------------
# /alerts/orders
# ---------------------------------------------------------------------------

class OrderLine(BaseModel):
    product_code:  str
    product_name:  str
    suggested_qty: int
    unit_cost:     float
    line_total:    float


class SupplierOrderResponse(BaseModel):
    supplier_cui:   str
    supplier_name:  str
    lead_time_days: float
    lines:          list[OrderLine]
    total_cost_ron: float
    coverage_days:  Optional[float]
    message:        Optional[str] = None


# ---------------------------------------------------------------------------
# /customers
# ---------------------------------------------------------------------------

class CustomerSummary(BaseModel):
    customer_cui:          str
    customer_name:         str
    avg_order_gap_days:    Optional[float]
    last_order_date:       Optional[str]
    days_since_last_order: Optional[int]
    days_overdue:          Optional[float]
    status:                str
    confidence:            str
    total_orders:          Optional[int]


class CustomerDetail(BaseModel):
    customer_cui:          str
    customer_name:         str
    avg_order_gap_days:    Optional[float]
    last_order_date:       Optional[str]
    days_since_last_order: Optional[int]
    expected_next_order:   Optional[str]
    days_overdue:          Optional[float]
    status:                str
    confidence:            str
    total_orders:          Optional[int]
    # revenue contribution
    total_revenue:         float
    revenue_share_pct:     float
    # recent orders
    recent_orders:         list[dict]


# ---------------------------------------------------------------------------
# /overview
# ---------------------------------------------------------------------------

class RevenueSnapshot(BaseModel):
    this_month:            float
    last_month:            float
    same_month_last_year:  float
    trend_pct:             Optional[float]   # vs last month


class InventoryHealth(BaseModel):
    total_ron:    float
    healthy_ron:  float
    slow_ron:     float
    critical_ron: float
    dead_ron:     float
    healthy_pct:  float
    slow_pct:     float
    critical_pct: float
    dead_pct:     float


class AlertCounts(BaseModel):
    critical:           int
    order_now:          int
    watch:              int
    dead_stock:         int
    declining:          int
    customer_deviation: int
    total:              int


class OverviewResponse(BaseModel):
    revenue:        RevenueSnapshot
    inventory:      InventoryHealth
    alert_counts:   AlertCounts
    top_alerts:     list[AlertEntry]   # top 3 most urgent


# ---------------------------------------------------------------------------
# /forecast
# ---------------------------------------------------------------------------

class ForecastWeek(BaseModel):
    week_start: str
    week_end:   str
    forecast:   float
    lower:      float
    upper:      float


class ForecastResponse(BaseModel):
    product_code:    str
    method:          str   # xgboost | croston | trend_seasonal | no_data
    horizon_days:    int
    as_of:           str
    weeks:           list[ForecastWeek]
    total_forecast:  float
    total_lower:     float
    total_upper:     float


# ---------------------------------------------------------------------------
# /upload
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    status:              str
    transactions:        Optional[int] = None
    inventory_rows:      Optional[int] = None
    sku_matches:         Optional[int] = None
    uncertain_matches:   Optional[int] = None
    unmatched:           Optional[int] = None
    elapsed_seconds:     Optional[float] = None
    message:             Optional[str] = None

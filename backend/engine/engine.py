"""
Engine facade — initialises DataAccess and exposes the full calculation API.

Usage:
    from backend.engine import Engine

    engine = Engine("data/flexicom.db")
    engine.demand_rate("P001")
    engine.days_of_cover("P001")
    engine.alerts()
"""

from datetime import date
from typing import Any, Optional

import pandas as pd

from .data_access import DataAccess
from .demand    import compute_demand_rate, detect_seasonality, detect_slow_movers
from .inventory import (
    compute_days_of_cover,
    compute_reorder_point,
    compute_dead_stock,
    generate_supplier_order,
    compute_working_capital_breakdown,
)
from .margin    import compute_margin, rank_products, compute_customer_concentration
from .customers import detect_customer_pattern_deviation, get_all_customer_deviations
from .forecast  import forecast_demand


class Engine:
    def __init__(self, db_path: str, as_of: Optional[date] = None):
        self._da    = DataAccess(db_path)
        self._as_of = as_of  # None → use date.today() in each function

    # ------------------------------------------------------------------
    # Demand
    # ------------------------------------------------------------------

    def demand_rate(self, product_code: str, window_days: int = 90) -> dict:
        return compute_demand_rate(product_code, self._da.sales(), window_days, self._as_of)

    def seasonality(self, product_code: str) -> dict:
        return detect_seasonality(product_code, self._da.sales())

    def slow_movers(self, threshold_pct: float = 0.40) -> pd.DataFrame:
        return detect_slow_movers(self._da.sales(), self._da.inventory(), threshold_pct, self._as_of)

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def days_of_cover(self, product_code: str) -> dict:
        return compute_days_of_cover(product_code, self._da.inventory(), self._da.sales(), self._as_of)

    def reorder_point(self, product_code: str, service_level: float = 0.95) -> dict:
        return compute_reorder_point(product_code, self._da.inventory(), self._da.sales(), service_level, self._as_of)

    def dead_stock(self, months_threshold: int = 6) -> pd.DataFrame:
        return compute_dead_stock(self._da.inventory(), self._da.sales(), months_threshold, self._as_of)

    def supplier_order(self, supplier_cui: str) -> dict:
        return generate_supplier_order(supplier_cui, self._da.inventory(), self._da.sales(), self._as_of)

    def working_capital(self) -> dict:
        return compute_working_capital_breakdown(self._da.inventory(), self._da.sales(), self._as_of)

    # ------------------------------------------------------------------
    # Margin & ranking
    # ------------------------------------------------------------------

    def margin(self, product_code: str, lookback_months: int = 12) -> dict:
        return compute_margin(product_code, self._da.sales(), self._da.purchases(), self._as_of, lookback_months)

    def product_rankings(self, metric: str = "revenue", window_days: int = 365) -> pd.DataFrame:
        return rank_products(self._da.sales(), self._da.purchases(), self._da.inventory(), metric, window_days, self._as_of)

    def customer_concentration(self) -> dict:
        return compute_customer_concentration(self._da.sales())

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    def customer_deviation(self, customer_cui: str) -> dict:
        return detect_customer_pattern_deviation(customer_cui, self._da.sales(), self._as_of)

    def all_customer_deviations(self) -> pd.DataFrame:
        return get_all_customer_deviations(self._da.sales(), self._as_of)

    # ------------------------------------------------------------------
    # Forecasting
    # ------------------------------------------------------------------

    def forecast(self, product_code: str, horizon_days: int = 90) -> dict:
        return forecast_demand(product_code, self._da.sales(), horizon_days, self._as_of)

    # ------------------------------------------------------------------
    # Aggregated alerts (for the Smart Alerts screen)
    # ------------------------------------------------------------------

    def alerts(self) -> dict[str, Any]:
        """
        Return a prioritised alert summary across all categories.

        {
          critical:           [{product_code, product_name, days_of_cover, message}]
          order_now:          [...]
          watch:              [...]
          dead_stock:         [...]
          declining:          [...]
          customer_deviation: [...]
        }
        """
        as_of     = self._as_of or date.today()
        inventory = self._da.inventory()
        sales     = self._da.sales()

        critical, order_now, watch = [], [], []

        for _, inv_row in inventory.iterrows():
            code = inv_row.get("canonical_product_code")
            if not code:
                continue

            rop_r = compute_reorder_point(code, inventory, sales, as_of=as_of)
            doc_r = compute_days_of_cover(code, inventory, sales, as_of=as_of)

            daily     = doc_r.get("daily_demand") or 0
            doc       = doc_r.get("adjusted_days_of_cover")
            lead      = rop_r.get("lead_time_days", 7)
            below_rop = rop_r.get("below_rop", False)

            if doc is None or daily == 0:
                continue

            name         = doc_r.get("product_name", code)
            stock        = doc_r.get("current_stock", 0)
            sugg_qty     = rop_r.get("suggested_order_qty", 0)
            est_cost     = rop_r.get("estimated_cost_ron", 0)
            stockout_date = str((pd.Timestamp(as_of) + pd.Timedelta(days=doc)).date())

            msg = (
                f"{stock:.0f} unități în stoc, cerere {daily*7:.1f}/săpt, "
                f"livrare în {lead:.0f} zile. "
                f"Stoc epuizat la {stockout_date}. "
                f"Comandă {sugg_qty} unități (~{est_cost:,.0f} RON)."
            )

            entry = {"product_code": code, "product_name": name, "days_of_cover": doc, "message": msg}

            if doc < lead:
                critical.append(entry)
            elif below_rop:
                order_now.append(entry)
            elif doc < 30:
                watch.append(entry)

        dead_df   = compute_dead_stock(inventory, sales, months_threshold=6, as_of=as_of)
        slow_df   = detect_slow_movers(sales, inventory, threshold_pct=0.40, as_of=as_of)
        cust_df   = get_all_customer_deviations(sales, as_of=as_of)

        return {
            "critical":   sorted(critical,  key=lambda x: x["days_of_cover"]),
            "order_now":  sorted(order_now,  key=lambda x: x["days_of_cover"]),
            "watch":      sorted(watch,      key=lambda x: x["days_of_cover"]),
            "dead_stock": dead_df.to_dict("records") if not dead_df.empty else [],
            "declining":  (
                slow_df[slow_df["status"] == "genuine_decline"].to_dict("records")
                if not slow_df.empty else []
            ),
            "customer_deviation": (
                cust_df[cust_df["status"].isin(["significantly_late", "inactive"])].to_dict("records")
                if not cust_df.empty else []
            ),
        }

"""Tests for margin.py — compute_margin, rank_products, compute_customer_concentration."""

import pytest
import pandas as pd

from backend.engine.margin import compute_margin, rank_products, compute_customer_concentration
from backend.engine.tests.conftest import AS_OF, NORMAL_PRODUCT, SEASONAL_PRODUCT, DOMINANT_CUSTOMER


class TestComputeMargin:

    def test_normal_product_has_positive_margin(self, sales, purchases):
        result = compute_margin(NORMAL_PRODUCT, sales, purchases, as_of=AS_OF)
        assert "current_margin_pct" in result
        assert result["current_margin_pct"] is not None
        assert result["current_margin_pct"] > 0, "Margin should be positive for a healthy product"
        assert result["avg_margin_pct"] > 0

    def test_margin_trend_is_valid_value(self, sales, purchases):
        result = compute_margin(NORMAL_PRODUCT, sales, purchases, as_of=AS_OF)
        assert result["margin_trend"] in ("improving", "stable", "compressing")

    def test_cost_increase_alert_fires_for_affected_product(self, sales, purchases):
        # P001 had Rulmenti SA price events (+11% Feb 2025, +7% Nov 2025)
        result = compute_margin(NORMAL_PRODUCT, sales, purchases, as_of=AS_OF)
        # Should have detected the cost spike
        assert result["cost_increase_alert"] is True, (
            f"Expected cost increase alert for P001 (Rulmenti raised prices), "
            f"cost_increase_pct={result.get('cost_increase_pct')}"
        )
        assert result["cost_increase_pct"] > 0

    def test_margin_history_is_monthly(self, sales, purchases):
        result = compute_margin(NORMAL_PRODUCT, sales, purchases, as_of=AS_OF)
        history = result["monthly_history"]
        assert len(history) >= 6
        for entry in history:
            assert "month" in entry
            assert "avg_sell_price" in entry
            assert "margin_pct" in entry

    def test_edge_case_unknown_product(self, sales, purchases):
        result = compute_margin("PXXX", sales, purchases, as_of=AS_OF)
        assert "error" in result

    def test_seasonal_product_has_valid_margin(self, sales, purchases):
        result = compute_margin(SEASONAL_PRODUCT, sales, purchases, as_of=AS_OF)
        assert "avg_margin_pct" in result
        assert result.get("avg_margin_pct") is not None


class TestRankProducts:

    def test_revenue_ranking_covers_all_products(self, sales, purchases, inventory):
        result = rank_products(sales, purchases, inventory, metric="revenue", as_of=AS_OF)
        assert len(result) == 26, f"Expected 26 products, got {len(result)}"

    def test_revenue_is_descending(self, sales, purchases, inventory):
        result = rank_products(sales, purchases, inventory, metric="revenue", as_of=AS_OF)
        revenues = result["revenue"].tolist()
        assert revenues == sorted(revenues, reverse=True)

    def test_volume_ranking_differs_from_revenue(self, sales, purchases, inventory):
        rev  = rank_products(sales, purchases, inventory, metric="revenue",  as_of=AS_OF)
        vol  = rank_products(sales, purchases, inventory, metric="volume",   as_of=AS_OF)
        # The top product by volume should not always equal the top product by revenue
        # (cheap high-volume vs expensive low-volume products)
        assert list(rev["product_code"]) != list(vol["product_code"]), (
            "Revenue and volume rankings should differ"
        )

    def test_rank_column_is_sequential(self, sales, purchases, inventory):
        result = rank_products(sales, purchases, inventory, metric="revenue", as_of=AS_OF)
        assert list(result["rank"]) == list(range(1, len(result) + 1))

    def test_invalid_metric_raises(self, sales, purchases, inventory):
        with pytest.raises(ValueError, match="Unknown metric"):
            rank_products(sales, purchases, inventory, metric="nonsense", as_of=AS_OF)

    def test_margin_contribution_uses_both_price_and_volume(self, sales, purchases, inventory):
        result = rank_products(sales, purchases, inventory, metric="margin_contribution", as_of=AS_OF)
        assert "margin_contribution" in result.columns
        assert (result["margin_contribution"] >= 0).all()


class TestCustomerConcentration:

    def test_concentration_risk_is_flagged(self, sales):
        result = compute_customer_concentration(sales)
        # Synthetic data has SC Agro Muntenia at ~33% — should trigger
        assert result["concentration_risk"] is True, (
            f"Expected concentration risk flag, top1={result['top1_pct']}%"
        )

    def test_top1_pct_is_above_30(self, sales):
        result = compute_customer_concentration(sales)
        assert result["top1_pct"] >= 30.0

    def test_top_n_pct_is_monotonically_increasing(self, sales):
        result = compute_customer_concentration(sales)
        assert result["top1_pct"] <= result["top3_pct"] <= result["top5_pct"] <= result["top10_pct"]

    def test_customer_list_sorted_by_revenue(self, sales):
        result = compute_customer_concentration(sales)
        revenues = [c["revenue"] for c in result["customers"]]
        assert revenues == sorted(revenues, reverse=True)

    def test_total_revenue_matches_sum(self, sales):
        result = compute_customer_concentration(sales)
        customer_sum = sum(c["revenue"] for c in result["customers"])
        assert abs(result["total_revenue"] - customer_sum) < 1.0

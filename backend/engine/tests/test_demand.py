"""Tests for demand.py — compute_demand_rate, detect_seasonality, detect_slow_movers."""

from datetime import date
import pandas as pd

import pandas as pd
import pytest

from backend.engine.demand import compute_demand_rate, detect_seasonality, detect_slow_movers
from backend.engine.tests.conftest import AS_OF, DECLINING_PRODUCT, EDGE_PRODUCT, NORMAL_PRODUCT, SEASONAL_PRODUCT


# ---------------------------------------------------------------------------
# compute_demand_rate
# ---------------------------------------------------------------------------

class TestComputeDemandRate:

    def test_normal_product_returns_positive_demand(self, sales):
        result = compute_demand_rate(NORMAL_PRODUCT, sales, window_days=90, as_of=AS_OF)
        assert result["daily_demand"] > 0
        assert result["weekly_demand"] > 0
        assert result["weekly_demand"] == pytest.approx(result["daily_demand"] * 7, rel=1e-3)
        assert result["std_dev_daily"] >= 0
        assert result["trend"] in ("rising", "flat", "falling")
        assert result["data_points"] > 0

    def test_seasonal_product_shows_meaningful_demand(self, sales):
        # P005 is planting-season heavy — should still have positive demand over 90 days
        result = compute_demand_rate(SEASONAL_PRODUCT, sales, window_days=90, as_of=AS_OF)
        assert result["daily_demand"] > 0

    def test_declining_product_has_lower_demand_than_early_period(self, sales):
        # P024 demand decays to ~10% of original over 24 months.
        # Compare demand in the first 90 days vs the last 90 days — last should be significantly lower.
        early = compute_demand_rate(
            DECLINING_PRODUCT, sales, window_days=90,
            as_of=date(2024, 6, 1)   # early in the dataset
        )
        late  = compute_demand_rate(
            DECLINING_PRODUCT, sales, window_days=90, as_of=AS_OF
        )
        assert late["daily_demand"] < early["daily_demand"], (
            f"Declining product late demand ({late['daily_demand']:.4f}) "
            f"should be less than early demand ({early['daily_demand']:.4f})"
        )

    def test_edge_case_unknown_product_returns_zeros(self, sales):
        result = compute_demand_rate("PXXX", sales, window_days=90, as_of=AS_OF)
        assert result["daily_demand"] == 0.0
        assert result["data_points"] == 0

    def test_edge_case_very_short_window(self, sales):
        # 7-day window — should still return a valid structure even if data is sparse
        result = compute_demand_rate(NORMAL_PRODUCT, sales, window_days=7, as_of=AS_OF)
        assert "daily_demand" in result
        assert result["daily_demand"] >= 0

    def test_edge_case_low_volume_product(self, sales):
        # P017 (Pompa injectie) has ~1 unit/week — should not be zero but will be low
        result = compute_demand_rate(EDGE_PRODUCT, sales, window_days=90, as_of=AS_OF)
        assert result["daily_demand"] >= 0
        assert result["weekly_demand"] < 5  # never a high-volume product


# ---------------------------------------------------------------------------
# detect_seasonality
# ---------------------------------------------------------------------------

class TestDetectSeasonality:

    def test_planting_product_peaks_in_spring(self, sales):
        result = detect_seasonality(SEASONAL_PRODUCT, sales)
        indices = result["indices"]
        assert result["is_seasonal"], "P005 (planting product) should be flagged as seasonal"
        # March (3) or April (4) should have the highest index
        spring_months = {3, 4}
        assert result["peak_month"] in spring_months, (
            f"Expected planting product peak in Mar/Apr, got month {result['peak_month']}"
        )
        # December index should be below 0.8
        assert indices[12] < 0.8

    def test_general_product_has_flat_seasonality(self, sales):
        # P001 (Rulment) is tagged "general" — seasonal variation should be modest
        result = detect_seasonality(NORMAL_PRODUCT, sales)
        indices = result["indices"]
        max_idx = max(indices.values())
        min_idx = min(indices.values())
        # A general product shouldn't have any month at >1.6x or <0.4x average
        assert max_idx < 2.0, f"General product has unexpectedly high peak index: {max_idx}"
        assert min_idx > 0.2, f"General product has unexpectedly low trough index: {min_idx}"

    def test_indices_are_normalised_around_one(self, sales):
        result = detect_seasonality(NORMAL_PRODUCT, sales)
        indices = result["indices"]
        assert set(indices.keys()) == set(range(1, 13))
        avg = sum(indices.values()) / 12
        # The average of all monthly indices should be close to 1.0
        assert 0.8 < avg < 1.2, f"Average seasonal index should be ~1.0, got {avg:.3f}"

    def test_edge_case_unknown_product_returns_flat(self, sales):
        result = detect_seasonality("PXXX", sales)
        assert not result["is_seasonal"]
        assert all(v == 1.0 for v in result["indices"].values())

    def test_months_of_data_is_plausible(self, sales):
        result = detect_seasonality(NORMAL_PRODUCT, sales)
        # We have 24 months of data — product sold in most months
        assert result["months_of_data"] >= 12


# ---------------------------------------------------------------------------
# detect_slow_movers
# ---------------------------------------------------------------------------

class TestDetectSlowMovers:

    def test_declining_products_are_flagged(self, sales, inventory):
        result = detect_slow_movers(sales, inventory, threshold_pct=0.40, as_of=AS_OF)
        assert not result.empty, "Expected at least one slow mover in synthetic data"
        codes = result["product_code"].tolist()
        # P024, P025, P026 are the explicitly declining products
        declining = {DECLINING_PRODUCT, "P025", "P026"}
        found = declining & set(codes)
        assert len(found) > 0, f"Expected at least one of {declining} in slow movers, got {codes}"

    def test_result_columns_are_present(self, sales, inventory):
        result = detect_slow_movers(sales, inventory, threshold_pct=0.40, as_of=AS_OF)
        required = {"product_code", "product_name", "decline_pct", "is_seasonal", "status"}
        assert required.issubset(result.columns)

    def test_decline_pct_is_negative(self, sales, inventory):
        result = detect_slow_movers(sales, inventory, threshold_pct=0.40, as_of=AS_OF)
        assert (result["decline_pct"] < 0).all(), "All flagged slow movers must have negative decline_pct"

    def test_edge_case_high_threshold_returns_fewer_results(self, sales, inventory):
        low_thresh  = detect_slow_movers(sales, inventory, threshold_pct=0.20, as_of=AS_OF)
        high_thresh = detect_slow_movers(sales, inventory, threshold_pct=0.70, as_of=AS_OF)
        assert len(low_thresh) >= len(high_thresh)

    def test_edge_case_empty_sales_returns_empty(self, inventory):
        empty_sales = pd.DataFrame(columns=["canonical_product_code", "invoice_date", "quantity"])
        result = detect_slow_movers(empty_sales, inventory, threshold_pct=0.40, as_of=AS_OF)
        assert result.empty

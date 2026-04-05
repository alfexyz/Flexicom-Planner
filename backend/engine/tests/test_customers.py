"""Tests for customers.py — detect_customer_pattern_deviation, get_all_customer_deviations."""

import pytest
import pandas as pd

from backend.engine.customers import detect_customer_pattern_deviation, get_all_customer_deviations
from backend.engine.tests.conftest import AS_OF, DOMINANT_CUSTOMER, CHURNED_CUSTOMER


class TestDetectCustomerPatternDeviation:

    def test_active_customer_is_on_track(self, sales):
        result = detect_customer_pattern_deviation(DOMINANT_CUSTOMER, sales, as_of=AS_OF)
        assert result["status"] in ("on_track", "late"), (
            f"Dominant active customer should be on_track or late, got {result['status']}"
        )
        assert result["avg_order_gap_days"] > 0
        assert result["total_orders"] > 0

    def test_churned_customer_is_flagged(self, sales):
        # RO22334455 last ordered late November 2025, as_of is March 2026 — ~120 days ago
        result = detect_customer_pattern_deviation(CHURNED_CUSTOMER, sales, as_of=AS_OF)
        assert result["status"] in ("significantly_late", "inactive"), (
            f"Churned customer should be significantly_late or inactive, got {result['status']}"
        )
        assert result["days_overdue"] > 0

    def test_days_since_last_order_is_positive(self, sales):
        result = detect_customer_pattern_deviation(DOMINANT_CUSTOMER, sales, as_of=AS_OF)
        assert result["days_since_last_order"] >= 0

    def test_confidence_reflects_order_count(self, sales):
        result = detect_customer_pattern_deviation(DOMINANT_CUSTOMER, sales, as_of=AS_OF)
        # Dominant customer orders frequently — should have high confidence
        assert result["confidence"] in ("high", "medium"), (
            f"Active customer with many orders should have medium/high confidence"
        )

    def test_unknown_customer_returns_error(self, sales):
        result = detect_customer_pattern_deviation("RO00000000", sales, as_of=AS_OF)
        assert "error" in result

    def test_result_has_expected_fields(self, sales):
        result = detect_customer_pattern_deviation(DOMINANT_CUSTOMER, sales, as_of=AS_OF)
        required = {
            "customer_cui", "customer_name", "avg_order_gap_days",
            "last_order_date", "days_since_last_order",
            "expected_next_order", "days_overdue", "status", "confidence",
        }
        assert required.issubset(result.keys())


class TestGetAllCustomerDeviations:

    def test_returns_all_customers(self, sales):
        result = get_all_customer_deviations(sales, as_of=AS_OF)
        # Should cover all 13 customers (minus any with insufficient data)
        assert len(result) >= 10

    def test_churned_customers_appear_near_top(self, sales):
        result = get_all_customer_deviations(sales, as_of=AS_OF)
        # Sorted by days_overdue descending — churned customers should be at the top
        top_5_cuis = set(result.head(5)["customer_cui"].tolist())
        churned = {CHURNED_CUSTOMER, "RO33445566"}
        overlap = churned & top_5_cuis
        assert len(overlap) > 0, (
            f"Expected churned customers in top 5 most overdue, got top 5: {top_5_cuis}"
        )

    def test_sorted_by_days_overdue_descending(self, sales):
        result = get_all_customer_deviations(sales, as_of=AS_OF)
        overdue = result["days_overdue"].tolist()
        assert overdue == sorted(overdue, reverse=True)

    def test_edge_case_empty_sales(self):
        empty = pd.DataFrame(columns=["partner_cui", "partner_name", "invoice_number", "invoice_date"])
        result = get_all_customer_deviations(empty, as_of=AS_OF)
        assert result.empty

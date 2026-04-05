"""
Smoke test for the ingestion pipeline.

Run from the repo root:
    python -m backend.ingestion.smoke_test

Exits 0 on success, 1 on any failure.
"""

import logging
import sqlite3
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.WARNING)  # suppress info noise during tests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.ingestion import run_pipeline

INVOICES = "data/invoices.csv"
STOCK    = "data/stock.csv"

VALID_CODES = {f"P{i:03d}" for i in range(1, 27)}


def check(condition: bool, msg: str) -> None:
    if not condition:
        print(f"  FAIL  {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  OK    {msg}")


def main() -> None:
    print("Running ingestion smoke tests …\n")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # ------------------------------------------------------------------ #
    # 1. Pipeline runs without raising
    # ------------------------------------------------------------------ #
    try:
        summary = run_pipeline(INVOICES, STOCK, db_path)
    except Exception as e:
        print(f"  FAIL  Pipeline raised: {e}", file=sys.stderr)
        sys.exit(1)
    check(True, "Pipeline completed without raising")

    with sqlite3.connect(db_path) as conn:

        # ------------------------------------------------------------------ #
        # 2. Row counts are plausible
        # ------------------------------------------------------------------ #
        tx_count  = conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
        inv_count = conn.execute("SELECT count(*) FROM inventory").fetchone()[0]
        check(tx_count > 1000, f"transactions has {tx_count} rows (expected > 1000)")
        check(inv_count == 26, f"inventory has {inv_count} rows (expected 26)")

        # ------------------------------------------------------------------ #
        # 3. Issued / received split preserved
        # ------------------------------------------------------------------ #
        issued   = conn.execute("SELECT count(*) FROM transactions WHERE direction='issued'").fetchone()[0]
        received = conn.execute("SELECT count(*) FROM transactions WHERE direction='received'").fetchone()[0]
        check(issued   > 0, f"issued rows = {issued}")
        check(received > 0, f"received rows = {received}")
        check(issued > received, f"issued ({issued}) > received ({received})")

        # ------------------------------------------------------------------ #
        # 4. Storno rows are negative
        # ------------------------------------------------------------------ #
        bad_storno = conn.execute(
            "SELECT count(*) FROM transactions WHERE invoice_type='storno' AND quantity >= 0"
        ).fetchone()[0]
        check(bad_storno == 0, f"All storno rows have negative quantity ({bad_storno} violations)")

        # ------------------------------------------------------------------ #
        # 5. SKU matching coverage for received invoices
        # ------------------------------------------------------------------ #
        unmatched_received = conn.execute(
            "SELECT count(*) FROM transactions WHERE direction='received' AND canonical_product_code IS NULL"
        ).fetchone()[0]
        if unmatched_received > 0:
            examples = conn.execute(
                "SELECT product_name, product_code FROM transactions "
                "WHERE direction='received' AND canonical_product_code IS NULL LIMIT 5"
            ).fetchall()
            print(f"  WARN  {unmatched_received} received rows have no canonical code. Examples:")
            for ex in examples:
                print(f"        {ex}")
        check(unmatched_received == 0, f"All received rows have canonical_product_code ({unmatched_received} unmatched)")

        # ------------------------------------------------------------------ #
        # 6. All canonical codes are valid
        # ------------------------------------------------------------------ #
        all_codes = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT canonical_product_code FROM transactions "
                "WHERE canonical_product_code IS NOT NULL"
            ).fetchall()
        }
        orphans = all_codes - VALID_CODES
        check(len(orphans) == 0, f"No orphan canonical codes (found: {orphans or 'none'})")

        # ------------------------------------------------------------------ #
        # 7. Inventory completeness
        # ------------------------------------------------------------------ #
        null_inv = conn.execute(
            "SELECT count(*) FROM inventory WHERE canonical_product_code IS NULL"
        ).fetchone()[0]
        check(null_inv == 0, f"All inventory rows have canonical_product_code ({null_inv} nulls)")

        # ------------------------------------------------------------------ #
        # 8. Match log populated
        # ------------------------------------------------------------------ #
        log_count = conn.execute("SELECT count(*) FROM sku_match_log").fetchone()[0]
        check(log_count > 0, f"sku_match_log has {log_count} entries")

        # ------------------------------------------------------------------ #
        # 9. Print match method breakdown
        # ------------------------------------------------------------------ #
        print("\nSKU match summary:")
        rows = conn.execute(
            "SELECT match_method, count(*) as n FROM sku_match_log GROUP BY match_method ORDER BY n DESC"
        ).fetchall()
        total_log = sum(r[1] for r in rows)
        for method, n in rows:
            print(f"  {method:<20s} {n:>4d}  ({100*n/total_log:.1f}%)")
        flagged = conn.execute("SELECT count(*) FROM sku_match_log WHERE flagged=1").fetchone()[0]
        print(f"  {'flagged for review':<20s} {flagged:>4d}")

        # ------------------------------------------------------------------ #
        # 10. Fuzzy matching works independently (name-only test)
        # ------------------------------------------------------------------ #
        _test_fuzzy_matching()

    print(f"\nAll checks passed.  Database at {db_path}")
    print(f"Pipeline summary: {summary}")


def _test_fuzzy_matching() -> None:
    """
    Verify the SKU normalizer resolves supplier names to canonical codes
    even when product_code is absent (simulates real-world supplier invoices
    that use the supplier's own part numbers).
    """
    import pandas as pd
    from backend.ingestion.sku_normalizer import normalize_skus

    # Minimal issued transactions DataFrame (canonical master)
    issued = pd.DataFrame([
        {"direction": "issued", "product_code": "P001", "product_name": "Rulment 6205-2RS SKF"},
        {"direction": "issued", "product_code": "P003", "product_name": "Filtru ulei hidraulic JCB"},
        {"direction": "issued", "product_code": "P009", "product_name": "Filtru aer motor John Deere"},
    ])

    # Received transactions with supplier names (no matching product_code)
    received = pd.DataFrame([
        {"direction": "received", "product_code": "SUP-001", "product_name": "RULMENT 6205-2RS/C3 DIN625"},
        {"direction": "received", "product_code": "SUP-002", "product_name": "FILTRU HIDRAULIC BT8459 / P550228"},
        {"direction": "received", "product_code": "SUP-003", "product_name": "FILTRU AER PRIMAR JD AR50041"},
    ])

    transactions = pd.concat([issued, received], ignore_index=True)
    inventory    = pd.DataFrame(columns=["product_code", "product_name"])

    tx_out, _, log = normalize_skus(transactions, inventory)

    received_out = tx_out[tx_out["direction"] == "received"]
    matched_codes = set(received_out["canonical_product_code"].dropna().tolist())

    check("P001" in matched_codes, "Fuzzy: 'RULMENT 6205-2RS/C3 DIN625' → P001")
    check("P003" in matched_codes, "Fuzzy: 'FILTRU HIDRAULIC BT8459 / P550228' → P003")
    check("P009" in matched_codes, "Fuzzy: 'FILTRU AER PRIMAR JD AR50041' → P009")


if __name__ == "__main__":
    main()

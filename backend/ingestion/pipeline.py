"""
Ingestion pipeline — orchestrates parsing, SKU normalisation, and DB write.

Usage:
    from backend.ingestion import run_pipeline

    summary = run_pipeline(
        invoices_path="data/invoices.csv",
        stock_path="data/stock.csv",
        db_path="data/flexicom.db",
    )
"""

import logging
import time
from pathlib import Path
from typing import Any

from . import invoice_parser, stock_parser, sku_normalizer, db_writer

logger = logging.getLogger(__name__)


def run_pipeline(
    invoices_path: str | Path,
    stock_path: str | Path,
    db_path: str | Path = "data/flexicom.db",
) -> dict[str, Any]:
    """
    Full ETL: parse → normalise → persist.

    Returns a summary dict with row counts and match statistics.
    Exceptions from sub-modules propagate to the caller.
    """
    t0 = time.perf_counter()

    # 1 — Parse invoices
    logger.info("Step 1/4  Parsing invoices from %s …", invoices_path)
    t1 = time.perf_counter()
    raw_transactions = invoice_parser.parse(invoices_path)
    logger.info("  → %d rows  (%.2fs)", len(raw_transactions), time.perf_counter() - t1)

    # 2 — Parse stock
    logger.info("Step 2/4  Parsing stock from %s …", stock_path)
    t2 = time.perf_counter()
    raw_inventory = stock_parser.parse(stock_path)
    logger.info("  → %d rows  (%.2fs)", len(raw_inventory), time.perf_counter() - t2)

    # 3 — SKU normalisation
    logger.info("Step 3/4  Normalising SKUs …")
    t3 = time.perf_counter()
    transactions, inventory, match_log = sku_normalizer.normalize_skus(
        raw_transactions, raw_inventory
    )
    logger.info("  → %d match log entries  (%.2fs)", len(match_log), time.perf_counter() - t3)

    # 4 — Write to database
    logger.info("Step 4/4  Writing to %s …", db_path)
    t4 = time.perf_counter()
    db_writer.write(transactions, inventory, match_log, db_path)
    logger.info("  → done  (%.2fs)", time.perf_counter() - t4)

    # Build summary
    uncertain = int((match_log["flagged"] == 1).sum()) if not match_log.empty else 0
    unmatched = int(
        match_log["matched_canonical_code"].isna().sum()
        + (match_log["matched_canonical_code"] == "").sum()
    ) if not match_log.empty else 0

    summary = {
        "transactions":      len(transactions),
        "inventory_rows":    len(inventory),
        "sku_matches":       len(match_log),
        "uncertain_matches": uncertain,
        "unmatched":         unmatched,
        "elapsed_seconds":   round(time.perf_counter() - t0, 2),
    }
    logger.info("Pipeline complete in %.2fs — %s", summary["elapsed_seconds"], summary)
    return summary

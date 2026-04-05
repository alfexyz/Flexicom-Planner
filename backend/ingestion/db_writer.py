"""
Database writer — persists the three normalized DataFrames to SQLite.

Tables created / replaced:
  transactions   — all invoice lines with canonical product codes
  inventory      — current stock snapshot with canonical product codes
  sku_match_log  — match audit trail for operator review

Indexes are created after each write for query performance.
"""

import logging
import sqlite3
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def write(
    transactions: pd.DataFrame,
    inventory: pd.DataFrame,
    match_log: pd.DataFrame,
    db_path: str | Path,
) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        _write_table(conn, transactions, "transactions")
        _write_table(conn, inventory,    "inventory")
        _write_table(conn, match_log,    "sku_match_log")
        _create_indexes(conn)

    logger.info(
        "Wrote to %s — transactions=%d, inventory=%d, sku_match_log=%d",
        db_path,
        len(transactions),
        len(inventory),
        len(match_log),
    )


def _write_table(conn: sqlite3.Connection, df: pd.DataFrame, table_name: str) -> None:
    df.to_sql(table_name, conn, if_exists="replace", index=True, index_label="id")
    logger.debug("Wrote %d rows to table '%s'", len(df), table_name)


def _create_indexes(conn: sqlite3.Connection) -> None:
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_tx_canonical_code ON transactions(canonical_product_code)",
        "CREATE INDEX IF NOT EXISTS idx_tx_date           ON transactions(invoice_date)",
        "CREATE INDEX IF NOT EXISTS idx_tx_direction      ON transactions(direction)",
        "CREATE INDEX IF NOT EXISTS idx_tx_partner_cui    ON transactions(partner_cui)",
        "CREATE INDEX IF NOT EXISTS idx_inv_canonical_code ON inventory(canonical_product_code)",
    ]
    for stmt in indexes:
        conn.execute(stmt)
    conn.commit()

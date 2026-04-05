"""
Data access layer — loads normalized tables from SQLite into DataFrames.

All DataFrames are loaded once and cached on the DataAccess instance.
Every engine function takes plain DataFrames, not a database handle,
so they can be unit-tested without a database.
"""

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd


class DataAccess:
    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._transactions: pd.DataFrame | None = None
        self._inventory: pd.DataFrame | None    = None

    # ------------------------------------------------------------------
    # Public accessors (lazy-loaded, cached)
    # ------------------------------------------------------------------

    def transactions(self) -> pd.DataFrame:
        if self._transactions is None:
            self._transactions = self._load("transactions")
            self._transactions["invoice_date"] = pd.to_datetime(
                self._transactions["invoice_date"], errors="coerce"
            )
        return self._transactions

    def inventory(self) -> pd.DataFrame:
        if self._inventory is None:
            self._inventory = self._load("inventory")
        return self._inventory

    def sales(self) -> pd.DataFrame:
        """Issued, non-storno invoice lines only (net positive sales)."""
        tx = self.transactions()
        return tx[(tx["direction"] == "issued") & (tx["invoice_type"] == "factura")].copy()

    def purchases(self) -> pd.DataFrame:
        """Received, non-storno invoice lines only."""
        tx = self.transactions()
        return tx[(tx["direction"] == "received") & (tx["invoice_type"] == "factura")].copy()

    def reload(self) -> None:
        """Force reload from disk (used after a new upload)."""
        self._transactions = None
        self._inventory    = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self, table: str) -> pd.DataFrame:
        with sqlite3.connect(self._db_path) as conn:
            return pd.read_sql(f"SELECT * FROM {table}", conn)

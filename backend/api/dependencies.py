"""
FastAPI dependency injection for the Engine singleton.

The Engine loads all DataFrames from SQLite into memory at first access
and caches them. After a data upload the engine must be reloaded so the
new data is picked up on the next request.
"""

from pathlib import Path
from backend.engine import Engine

DB_PATH     = Path("data/flexicom.db")
_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        if not DB_PATH.exists():
            raise RuntimeError(
                "Database not found. Run the ingestion pipeline first or upload data via POST /upload/invoices."
            )
        _engine = Engine(str(DB_PATH))
    return _engine


def reload_engine() -> None:
    """Force re-creation of the engine on the next request (called after uploads)."""
    global _engine
    _engine = None
